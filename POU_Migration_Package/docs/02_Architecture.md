# 02 - Architecture, assumptions and decisions still open

## The shape of the system

```
  Cabinet PC (Windows)                          Microsoft 365 tenant
  ┌──────────────────────────┐   HTTPS   ┌──────────────────────────────────────────────────────┐
  │ Browser / Power Apps     │──────────▶│ SharePoint Online site "POU"                          │
  │ canvas app "POU"         │  (reads,  │   POUItems  POUStockLocations  POULedger (append-only)│
  │  - keyboard-wedge scanner│  add-only │   POURequests (add-only for operators)  POUSessions   │
  │  - runs as the STATION's │  request  │   POUEmployees POUStations POULocations POUSettings   │
  │    (or a named) Microsoft│  rows)    │   POUOpsEvents                                       │
  │    account               │           └───────────▲───────────────────────▲──────────────────┘
  └───────────┬──────────────┘                       │ writes stock/ledger   │ reads
              │ "run flow" (RequestID only)          │ as the FLOW SERVICE   │
              ▼                                      │ account only          │
  ┌──────────────────────────────────────────────────┴───────────────────────┴──────────────────┐
  │ Power Automate (flows owned by the POU Flow Service account)                                  │
  │  POU-Session   POU-ProcessRequest (the ONLY writer of stock+ledger)  POU-Sweeper (recovery)   │
  │  POU-Monitor  POU-Reconcile  POU-DailyLowStock  POU-WeeklyHealth  POU-WeeklyUsage             │
  └───────────────────────────────────────────────────────────────────────────────────────────────┘
```

Three different identities are always in play, and the design never confuses them:

| Identity | Who | Used for |
|---|---|---|
| **App account** | The Microsoft account signed in on the cabinet PC (a station account, or a named operator) | SharePoint stamps it as `Author` (Created By) on every request row. Cannot be forged by the app. |
| **Employee** | The person who scanned their badge | Recorded on the ledger. Looked up *by the flow* from the session, never taken from the request. |
| **Flow write identity** | The dedicated service account that owns the flow connections | The only principal with write access to `POUStockLocations` and `POULedger`. |

## One controlled path for every quantity change

Every change to a quantity - ADD, REMOVE, physical count, opening balance, adjustment, reversal - is a **request** (`POURequests`, add-only for operators) processed by **one** flow core. The app never writes `OnHandQty`; SharePoint permissions make that true, not politeness.

Request types: `ISSUE` (REMOVE), `RECEIPT` (ADD), `AUDIT` (count), `OPENING`, `ADJUSTMENT`, `REVERSAL`, plus master-data requests `ITEM_CREATE`, `LOCATION_ADD`, `PARAM_UPDATE`, and `APPROVE` (a supervisor's decision on another request).

### The posting protocol (what `POU-ProcessRequest` does, in order)

1. **Triage and claim.** Read the request. Claim it by an ETag compare-and-swap (`If-Match`) setting `Processing` and a run id. Two flows racing for one request: one loses with HTTP 412 and stops.
2. **Resume check.** If a ledger row for this `RequestID` already exists (unique column), this is a retry: continue from where the earlier run stopped instead of starting over.
3. **Authorise on the server.** Session exists, active, not expired, same station, same Microsoft account as the request `Author`; employee still active; station active and (if configured) bound to the account. Supervisor-only types require the `Author` to be an active Supervisor/Admin in `POUEmployees` (or, for badge-session requests that need approval, a valid `APPROVE` request from a *different* supervisor account). `OPENING` requires an Admin author.
4. **Validate.** Item/location exists and is active; type; whole-number quantity; ADD limit; enough stock for REMOVE; balance exists (no blank-as-zero); audit `ExpectedVersion` equals the record's current `StockVersion` (**stale count refused**); reversal target is a posted, un-reversed movement on the same record, and so on.
5. **Chain check.** The previous ledger row's `QtyAfter` must equal the stock record's `OnHandQty`. If not, nothing is posted, a Critical ops event is raised (`DRIFT_DETECTED`).
6. **Create the ledger *intent*.** `LedgerKey = StockKey#SeqNo` where `SeqNo = StockVersion + 1`, and `LedgerKey` is a **unique** column. Two operators taking the last unit both try to create `K|1-A#7`; SharePoint lets exactly one succeed. The loser re-reads and re-validates against the new quantity (and is refused if nothing is left). This unique-key insert is the compare-and-swap that makes the last unit safe.
7. **Apply to stock** with `If-Match` on the stock row: sets `OnHandQty`, `StockVersion = SeqNo`, `LowStockFlag`, `BalanceStatus`, `LastLedgerKey`.
8. **Finalise** the ledger row (`Intent` → `Posted`), then the request (`Succeeded`/`Rejected`/`Failed`, `InventoryEffect`, message). The flow *answers the app with what it can prove*.

States: request `Pending → Processing → (AwaitingSupervisor) → Succeeded | Rejected | Failed`; ledger `Intent → Posted | Voided`; `InventoryEffect = NotApplied | Applied | Unknown`. "Applied" means `StockVersion >= SeqNo` of this request's intent.

### Recovery

`POU-Sweeper` (every 5 minutes) finds requests that are `Pending` for more than 30 seconds (their own instant call never arrived), or `Processing` with a stale claim, and runs the *same core* on them. Because every step is idempotent and keyed (request id, ledger key, stock version) the sweeper can safely finish a half-done post (intent written, stock not yet updated; stock updated, ledger not finalised; ledger finalised, request not) or void an intent when the stock record fits neither its before nor its after state (an outside writer). Outcomes are only ever stated when established: a request that fails *before* any ledger row exists after `MaxProcessAttempts` is `Failed / GAVE_UP` with `InventoryEffect = NotApplied` (nothing was written, provably). Once an intent exists, recovery reads the stock version and resolves it to *applied* (finalise the ledger) or *not applied* (apply it now); if the stock record shows neither version, the intent is voided, a **Critical** ops event (`STOCK_ANOMALY`) is raised for a human, and the request fails with `STOCK_CHANGED_OUTSIDE_PROTOCOL`. While a write is unconfirmed the app is told `Processing / UNCONFIRMED - do not repeat`, never success. `POU-Monitor` raises exactly one ops event (and one email) per failed request, or request/ledger intent stuck longer than the configured thresholds (`StaleIntentMinutes`); `POU-Reconcile` proves nightly that every `OnHandQty` equals its ledger row and repairs derived fields.

Full analysis of why this is needed, what each failure looks like, and where SharePoint stops being enough: `06_Consistency_Limits.md`.

## What the screens do (app/)

`scrLogin` badge/session - `scrScan` ADD/REMOVE - `scrAudit` physical count - `scrAddItem` new item / add stocking location - `scrLowStock` - `scrHistory` (requests with processing status + ledger) - `scrSupervisor` (approvals, adjustment, reversal, Min/Max/Area, opening) - `scrAdmin` (settings, locations, stations). Control names and every formula: `app/docs/CONTROL_REFERENCE.md`.

## Settings (central, in `POUSettings`; defaults in `schema/settings_defaults.json`)

Low stock rule `LE` (On hand <= Min) - idle timeout 3 min - server session max idle 10 min - logout after submit off - max single ADD 500 - audit variance confirmation at 5 - supervisor required for audits and new items - recipients, report hours and weekday - display time zone `America/Chicago` (all timestamps stored UTC) - scan debounce and minimum length - status polling. Stations, locations, employees are rows, not code.

## Assumptions (marked, because nobody has confirmed them)

| # | Assumption | If wrong |
|---|---|---|
| A1 | Cabinet PCs run Windows with a current Edge/Chrome; the app runs in the browser (Power Apps *web player*). | The Power Apps Windows app has the same behaviour; tablets/phones: layout is fixed 1366x768 landscape and needs a responsive pass. |
| A2 | Scanners are USB **keyboard-wedge** with an Enter *or* Tab suffix, typing as fast as a keyboard. | The scan debounce (`ScanCommitIdleMs`) copes with both suffixes and with none; see scanner tests in `08_Testing_and_Acceptance.md`. |
| A3 | Several stations operate at the same time. | The design assumes this; it is why the protocol exists. |
| A4 | The PC's Windows time zone is America/Chicago. | Only the fallback time display on `scrHistory` is affected; stored and ledger-displayed times come from the flow. |
| A5 | One physical cabinet = one `StationID`; `StationID` is passed in the app URL (`?StationID=CAB-01`) or derived from the Microsoft account assigned in `POUStations.ExpectedAccountUPN`. | Edit `POUStations`. No code change. |
| A6 | The pilot workbook's timestamps are America/Chicago local time. | Re-run the transform with `--source-timezone`. |
| A7 | Workbook quantities are **candidates** until counted. | Cutover plan has a verified-opening option (`09_Cutover_and_Rollback.md`). |

## Decisions that are yours (or IT's) and are NOT made for you

| # | Decision | Default in this package | Why it matters |
|---|---|---|---|
| D1 | **Licence for the flow service account** (Microsoft 365 seeded rights vs Power Automate Premium / per-flow). | Not decided. | Capacity: see `05_Platform_Facts_and_Capacity.md` - under the smallest plan the flows exhaust the daily action allowance in a few dozen transactions. **Blocking for go-live.** |
| D2 | Shared station accounts vs named operator accounts for the cabinet PCs. | Supported either way. | Sessions are bound to the signed-in account; shared accounts mean SharePoint's `Author` identifies the *station*, the badge identifies the person. |
| D3 | Who the supervisors and admins are, and their Microsoft accounts. | Nobody (`EMPLOYEE_ROLES_UNKNOWN`). | Until set, audits, new items, adjustments and approvals wait forever. |
| D4 | Allow REMOVE/ADD against a quantity that has been imported but not yet counted (`AllowIssueAgainstUnverified`). | `true` (cabinet keeps working; the screen says "not yet verified"). | `false` = strict: nothing moves until counted. |
| D5 | Cutover style: import workbook figures as `Unverified` openings and count over time, or start every record `NoBalance` and count first. | Option A (see cutover doc). | Business risk vs cutover effort. |
| D6 | Low-stock rule `LE` vs `LT`. | `LE`. | 71 vs 9 flagged records on today's data. |
| D7 | Whether SharePoint is acceptable given its limits (below), or the Dataverse / Azure SQL variant should be built. | SharePoint, with the protocol above. | `06_Consistency_Limits.md` says exactly when you should not. |
| D8 | Report recipients, schedules. | `CHANGE-ME@yourcompany.example` - mail is **not** sent until replaced. | A placeholder raises an ops event instead of sending. |
| D9 | Permanent IDs for the 142 `TEMP####` items. | Unchanged. | Needs a controlled rename (runbook). |
