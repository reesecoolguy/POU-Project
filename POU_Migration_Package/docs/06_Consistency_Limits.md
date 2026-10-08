# 06 - Why concurrency control is not enough, what happens when things fail, and where SharePoint stops

## 1. "Just use ETags" - and why that is not the answer

An ETag (`If-Match`) on the stock row stops two writers from silently overwriting each other's *quantity*. It does **not** give you any of the following, and each of them would lose or duplicate stock in a real cabinet:

| Problem | Why an ETag on the stock row does not solve it |
|---|---|
| **Four writes, not one.** A posting touches the request row, the ledger, the stock row, and the status. SharePoint has no transaction across items or lists. | The ETag only protects one item. A crash after the stock write and before the ledger write leaves a quantity change with no explanation. |
| **Retries, timeouts and lost responses.** The app sends a request, the connection dies, the user presses the button again. | Without a key that survives the retry, the second press is a *new* movement. The ETag cannot tell "retry of the same movement" from "a different movement". |
| **Lost response after success.** The server applied the change; the answer never arrived. | The app cannot know. Treating silence as failure double-posts; treating it as success may lie. A durable record keyed by request id is needed so the question "did request X apply?" always has an answer. |
| **Other writers.** An admin editing the list, a bulk import, another flow, Excel "edit in grid", a future second app. | An ETag only protects writers who send it. `If-Match: *` (the default for many tools) and the SharePoint UI do not. Permissions and a chain check are needed so such writes are *prevented* or *detected*. |
| **Derived fields touch the ETag.** A harmless edit (Min, LowStockFlag repair) changes the ETag. | Causes spurious 412s - safe, but the protocol must treat 412 as "re-read and decide", not as failure. |
| **The ledger.** The thing you actually need to trust is the history. | ETag says nothing about appending exactly one ledger row per movement, in order, once. |

### What the design uses instead (three independent keys)

1. **`RequestID` is unique** in `POURequests` and in `POULedger`. The app creates it once and keeps it across retries (and across an app restart, from its local outbox). The same id can never produce two movements.
2. **`LedgerKey = StockKey#SeqNo` is unique** and `SeqNo = StockVersion + 1`. Two operators taking the last unit both try to insert the same key; SharePoint's unique index lets one succeed. This - not the ETag - is the compare-and-swap that serialises movements per item/location. The loser re-reads, re-validates against the new quantity and is refused if nothing is left.
3. **`StockVersion` + stock ETag** guard the stock write and let recovery decide, from the stock row alone, whether an intent has been applied (`StockVersion >= SeqNo`), has not (`StockVersion = SeqNo - 1` and the quantity is still the "before"), or is an anomaly (anything else: an outside writer).

Plus: **write intent first** (ledger row in state `Intent` *before* touching stock), so there is always durable evidence of what was about to happen; **idempotent recovery** (`POU-Sweeper` runs the same core); **permissions** so that only the flow service account can write stock/ledger; and a **chain check** on every post and nightly (`QtyAfter` of the previous ledger row must equal `OnHandQty`).

## 2. What happens when something goes wrong

All of these were executed against the generated flow definitions in the local model - crash and lost-response injected at **every one of the 16 SharePoint calls** of an ADD/REMOVE, plus concurrent races (`tests/test_flow_faults.py`, `test_flow_concurrency.py`, `test_flow_sweeper.py`). That is *modelled* behaviour; the tenant run `T-RACE-*` repeats the important ones for real.

| # | Failure | State left behind | What recovers it | What the operator sees |
|---|---|---|---|---|
| F1 | Browser/PC dies after the request row was created, before the flow was called | Request `Pending`; nothing else | Sweeper (<= 5 min) processes it | After restart: banner "an earlier request was never confirmed - press Retry same request" (local outbox). History shows `Pending`, then `Succeeded`. |
| F2 | Flow ran to the end but the response never reached the app | Request `Succeeded`, ledger `Posted`, stock updated | Nothing needed. The app re-reads the request row. | Green, from the **row**, not from the lost response. |
| F3 | Flow claimed the request then died | `Processing` with an old claim | After `StaleClaimSeconds` (120) any run may re-claim (ETag swap) | UNCONFIRMED (amber) until it completes. |
| F4 | Intent written, stock **not** updated | Ledger `Intent`; stock at "before" version | Recovery classifies "unapplied" (stock still at the version the intent was validated against) and applies it; if the stock shows a version that fits neither before nor after, the intent is voided and a Critical event raised | `Processing / APPLY_PENDING - do not repeat`. |
| F5 | Stock updated, ledger **not** finalised | Stock at "after"; ledger `Intent` | Recovery classifies "applied" (`StockVersion >= SeqNo`) and finalises the ledger | "The quantity **was** updated. Confirming the record. Do not repeat." (`InventoryEffect = Applied`) |
| F6 | Ledger finalised, request status not written | Ledger `Posted`; request `Processing` | Resume check finds the posted ledger row by `RequestID` and writes the request result | Success, from the stored ledger row. |
| F7 | **The quantity changed but logging/status fails** (any of F5/F6, or the request update throws) | Quantity is changed. Ledger `Intent`/`Posted` exists for it. | As F5/F6. The app is *never* told "nothing changed": `InventoryEffect` is `Applied` or `Unknown`, and the message says so. `POU-Monitor` emails if still unresolved after the stuck threshold. | Amber "Not confirmed / quantity was updated", or red "The quantity MAY have changed - tell a supervisor". |
| F8 | Two operators take the last unit | Exactly one ledger key wins | The loser's re-validation fails | Winner: green. Loser: red "Only 0 on hand - cannot remove 1. Nothing was changed." (established, because it was rejected before any intent). |
| F9 | Double-click | Same `RequestID`, same row | App: busy flag + disabled buttons + retained id; server: unique key | One movement. |
| F10 | Someone edits `OnHandQty` by hand (Site Owner / admin tool) | Stock disagrees with the ledger chain | Next post on that record is **blocked** (`DRIFT_DETECTED`, Critical ops event); nightly reconcile reports it | Red "stored quantity does not match its history. A supervisor has been alerted." |
| F11 | SharePoint throttles (429/503) mid-flow | Whatever was written so far | Connector retries; a step that still fails is treated as *unconfirmed* and recovered as F4-F6 | Amber UNCONFIRMED. |
| F12 | Flow service account disabled, password/MFA token expired, licence lapsed | Requests stay `Pending` | Nothing until fixed; requests are never lost | UNCONFIRMED then "STILL NOT CONFIRMED... check History". **Alerting uses the same flow identity** - see runbook for the independent check (a SharePoint view of open requests older than 15 minutes) and Power Automate's own failure e-mails. |
| F13 | App/PC time wrong | - | Server decides expiry with its own clock | Possible `SESSION_EXPIRED`; re-scan badge. |
| F14 | Operator keys the same movement twice after a restart, with no outbox | Two different request ids | **Nothing can detect this**: they are two legitimate requests | The unconfirmed-request banner exists for exactly this; it is a human-factors limit, not a protocol one. |

## 3. Candid limits of SharePoint for this job

* **No atomicity.** The protocol gives *recoverable* consistency, not a transaction. For some seconds (and, under failure, minutes) quantity, ledger and request status can disagree; the disagreement is always detectable and normally self-heals, but a person reading the lists directly can see it.
* **Append-only is enforced by permission, not by immutability.** Operators and admins cannot edit/delete the ledger. The flow account must be able to edit it (to move `Intent` to `Posted`), and Site Owners can do anything. Versioning keeps a history of edits. There is no cryptographic tamper evidence.
* **The one atomic primitive is the unique index** (and ETag). The design stands on those two; probes `U1`, `R1`, `R2` must pass on your tenant before go-live.
* **5,000-item list-view threshold.** The ledger will pass 5,000 rows (at ~20 movements/day: within a year). All app and flow queries use indexed columns or ID order, but **an administrator sorting or filtering the ledger by an unindexed column in the SharePoint UI will get an error** once it is big. Use the provided indexed columns.
* **Read consistency.** What the app shows can be stale by seconds. The server, not the screen, decides.
* **Latency and capacity.** About 16 SharePoint calls and 112 flow actions per movement: 5-15 s and a licence decision (`05_Platform_Facts_and_Capacity.md`).
* **Reads of "everything"** (reconcile, usage, health) page through the list by ID and filter in the flow; they are complete past 2,000 and 5,000 rows (proved at 5,300 rows in the model), but they are slow and cost actions in proportion to the size.
* **Purge**: `POURequests` and `POUSessions` are purged by age; the ledger never is. A replayed old request id is still answered from the ledger.

### When you should not use SharePoint for this

Move to Dataverse or SQL if any of these is true: more than roughly a hundred movements per day per cabinet; operators will not wait 5-15 s; you cannot license the flow account for the action volume; an auditor needs tamper-resistant or transactional guarantees; or more than a handful of stations hit the *same* item/location simultaneously.

## 4. The smallest Dataverse / SQL alternative

Keep everything else (badge sessions, request ids, approval rules, screens); change only the posting core.

* **Azure SQL (or SQL Server) + one stored procedure** - `docs/alt/PostMovement.sql`. One transaction: replay check on a unique `RequestID` -> lock the stock row -> validate -> `UPDATE ... StockVersion` -> append the ledger row -> commit. The last-unit race is serialised by the row lock; a crash between the two writes rolls both back, so "nothing changed" *is* established. The flow shrinks to roughly 5 actions per movement (look up session -> call procedure -> reply), so the capacity problem largely disappears. Cost: the SQL connector is a **premium** connector (licensing for the flow and, depending on how the app is built, its users - confirm), an Azure SQL database to run, and a DBA-style responsibility for backups. Pattern-tested on SQLite (`tests/test_sql_alternative.py`); the T-SQL itself is **unexecuted**.
* **Dataverse** - tables with alternate keys (unique `RequestID`, `StockKey`), row versioning (ETag) and the connector's *changeset* request (several writes in one all-or-nothing batch) give the same transaction semantics without writing SQL, and Power Apps can bind to the tables directly. Cost: Dataverse capacity and a Power Apps premium licence for every app user. Not implemented here beyond this description.

Either variant keeps the SharePoint design's *rules*; only the mechanism for "update stock and append ledger as one unit" changes.
