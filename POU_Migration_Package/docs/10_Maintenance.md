# 10 - Maintenance and runbook

Who does what: **Supervisor** = reads alerts, approves, counts. **Admin** = settings and master data. **Site owner / IT** = connections, licences, break-glass edits.

## Routine

| When | What | Where |
|---|---|---|
| Every morning | Read the **low-stock e-mail** (suggestions to reorder - it does *not* know about open purchase orders) and any **ops alert** e-mail. | Mailbox |
| Every morning (2 minutes) | Open `POUOpsEvents` filtered `Resolved = No`. Nothing Critical may stay unresolved. | SharePoint list |
| Every morning | SharePoint view **"Open requests older than 15 minutes"** on `POURequests` (`IsOpen = Yes`, sorted by Created): must be empty or explained. This is the check that does *not* depend on the flows being alive. | SharePoint |
| Weekly | Read the **data-health** and **usage (30/90 day)** e-mails; fix the findings (missing roles, placeholders, items without stock, names). | Mailbox |
| Weekly | Export `POUStockLocations` and `POULedger` to Excel (list -> Export -> Excel) and store the files. | SharePoint |
| Monthly | Power Platform admin center -> Capacity -> Power Platform requests: compare the flow account's usage with `05_Platform_Facts_and_Capacity.md`. Check the Power Automate **failure notification** e-mails sent to the flow owner. Check each flow's connections are green. | Admin centers |
| Per quarter | Run `scripts\6_permission_audit.cmd` for each group; re-run `scripts\5_tenant_probe.cmd APPLY`. Review who is in the four groups. | Scripts |
| At each count | Post counts through the app (Count screen), never by editing `OnHandQty`. | App |

## Reading the ops events (`POUOpsEvents`)

An event is one row per distinct problem (`EventKey`), with an occurrence count - it does not multiply. Tick **Resolved** when dealt with (the row reopens itself if the problem recurs).

| EventType | Severity | Meaning | What to do |
|---|---|---|---|
| `DRIFT` | Critical | At posting time the stored quantity did not match the ledger's last row for that record. **Posting on that record is blocked** until fixed (this protects the ledger). | See *Repairing a drifted record* below. |
| `STOCK_ANOMALY` | Critical | While finishing a post, the stock row's version fitted neither "before" nor "after": someone/something else changed it. The intent was voided; the request failed `STOCK_CHANGED_OUTSIDE_PROTOCOL` (this request changed nothing). | Find who edited the record (version history of the stock row), then as for `DRIFT`. |
| `RECONCILE` (`BALANCE_MISMATCH`, `BALANCE_WITHOUT_LEDGER`, `LEDGER_ROW_MISSING`, `STOCK_BEHIND_LEDGER`, `STALE_INTENT`) | Critical | Nightly proof found `OnHandQty` != the ledger row for its `StockVersion`, or a half-finished post. | `STALE_INTENT`: the sweeper normally resolves it within minutes - if it persists the sweeper or its connection is broken (see below). The others: *Repairing a drifted record*. |
| `LEDGER_INTENT_STUCK` | Critical | A ledger row has been `Intent` for over 15 minutes. | Check POU-Sweeper's run history and connections; run it by hand; if it still does not clear, as `STOCK_ANOMALY`. |
| `REQUEST_FAILED` | Warning (Critical when `InventoryEffect = Unknown`) | A request ended `Failed`. The ResultCode says why; `Unknown` effect means a human must establish what happened. | Look at the request row (ResultMessage, LedgerKey) and the ledger rows for that StockKey; recount if in doubt. |
| `REQUEST_STUCK` | Warning | `Pending`/`Processing` longer than 15 minutes. | Sweeper/connection problem. Run POU-Sweeper; check the flow account's licence/throttling. |
| `REQUEST_WAITING_APPROVAL` | Warning | A supervisor request has waited over 8 hours (expires at 24 h with nothing changed). | A supervisor approves or rejects it. |
| `BADGE_FAILURES` | Warning | Unknown badges scanned at a station today. | Normal for a mistyped badge; repeated bursts may be someone guessing. |
| `CONFIG` | Warning | Report recipients are still the `CHANGE-ME` placeholder, so mail is not being sent. | Edit `POUSettings`. |

### Repairing a drifted record (break-glass; Site Owner only)

The aim is to make the stock row agree with the ledger again **without rewriting history**, then record the truth with a normal supervisor count.

1. Open the item in `POUStockLocations`, read `StockKey`, `OnHandQty`, `StockVersion`. Open `POULedger` filtered `StockKey eq '<key>'`, sorted by `SeqNo`.
2. Find the ledger row whose `SeqNo` = `StockVersion` (the "current" row) and look at its `QtyAfter`.
   * If the row exists and `OnHandQty` differs (someone edited the quantity): set `OnHandQty` **back to that row's `QtyAfter`**.
   * If `StockVersion` is higher than any existing ledger row (a row was deleted): set `StockVersion` to the highest existing `SeqNo` and `OnHandQty` to its `QtyAfter`.
   * If `StockVersion` = 0 but `OnHandQty` has a value (a quantity was typed into a new record): clear `OnHandQty` and leave `BalanceStatus = NoBalance`.
   * If an `Intent` row is stuck and the stock already shows its `QtyAfter` at `SeqNo`, let the sweeper finalise it; do not edit it.
   * `STOCK_BEHIND_LEDGER` (a *Posted* ledger row exists one version ahead of the stock row): set `StockVersion` to that row's `SeqNo` and `OnHandQty` to its `QtyAfter`.
3. Add a line to the item's `Notes`/version comment saying what you changed and why (SharePoint keeps the version history).
4. Tick the ops event **Resolved**. Next night's reconcile must show no finding for the record.
5. A supervisor then **counts** the item (Count screen): the count enters the ledger as a normal AUDIT, and the real difference becomes a visible ledger entry.

Never delete ledger rows. A row that was posted by mistake is cancelled by a REVERSAL (supervisor), not removed.

## When flows stop working

| Symptom | Likely cause | Fix |
|---|---|---|
| Every action shows UNCONFIRMED; requests stay `Pending` | Flow connection expired (password change, MFA/Conditional Access, account disabled) or the flow is off | Power Automate -> Connections: fix the SharePoint connection of the **service account**; turn the flow on; run POU-Sweeper by hand. |
| Throttling / very slow | Daily action allowance exceeded (see capacity doc) | Licence change (D1) or the cost-reduction options in the capacity doc. |
| `Stop_site_url_not_set` error in a run | `Cfg_SiteUrl` still holds the placeholder (e.g. after re-import) | Edit the `Cfg_SiteUrl` action in that flow. |
| No e-mails | Placeholder recipients (`CONFIG` event), or the Office 365 Outlook connection expired | Settings / reconnect. |
| Alerts themselves stopped | The alerting flow uses the same service account as everything else | The morning "open requests older than 15 minutes" view is the independent check; also keep Power Automate's own failure e-mails switched on for the flow owner. |
| A flow run shows "action X failed" | Read the run: the generated flows record the failing step; most are throttling (retry succeeded) or a permission change | If a permission changed, run `6_permission_audit.cmd flowservice`. |

## Everyday administration (no code changes)

| Task | How |
|---|---|
| Add a cabinet PC | Add a `POUStations` row (`StationID`, Active, optional `ExpectedAccountUPN`); add the station account to POU Operators (and the Entra group the app is shared with); open the app with `?StationID=<id>`. |
| Add a location | App -> Admin -> Locations (or the list). The location must exist before an item can be stocked there. |
| Add an employee / badge | `POUEmployees` row. `BadgeID` is **text** - type it as scanned; keep leading zeros. Role Operator for ordinary staff. |
| Make someone a supervisor/admin | Set `Role` and **`MicrosoftUPN`** (their real sign-in address) on their employee row, add their account to POU Supervisors (or Admins). Without `MicrosoftUPN` they cannot approve anything. |
| Remove someone | Set `Active = No`. **Never delete employees** (history refers to them). Their sessions stop working at the next request. |
| New item / new location for an item | App -> New item (supervisor approves). K102516-style multi-location items: use "ADD LOCATION" on the existing item. |
| Change Min / Max / Area | Supervisor screen -> Min/Max/Area. Quantities are never changed this way. |
| Deactivate an item/location | Supervisor screen -> deactivate. Refused while on hand > 0 (count it to zero first). |
| Change low-stock rule, timeouts, limits | Edit `POUSettings` (App -> Admin or the list). Takes effect on the next sign-in / next flow run, no republish. Rule change: also refresh the stored `LowStockFlag`s - clear the `LastReconcileDate` setting and run POU-Reconcile by hand (it runs once per day, so the date must be empty or old). |
| Change report recipients/hours/weekday | `POUSettings` (`ReportRecipients*`, `LowStockReportHourLocal`, `ReconcileHourLocal`, `WeeklyDayOfWeek`, `WeeklyHourLocal`). Hours are in `DisplayTimeZoneWindows` (default Central Standard Time). |
| Change time zone | `DisplayTimeZoneWindows` (Windows name) and `DisplayTimeZoneIana`. Stored times stay UTC. |
| Replace a `TEMP####` placeholder ID | **There is no in-place rename**: the Item ID is part of every stock and ledger key, and the ledger is append-only. Procedure: (1) NEW ITEM with the real ID at the same location, supervisor approves; (2) supervisor counts it (first count); (3) on the TEMP record post an ADJUSTMENT to 0 with reason "renamed to <real ID>"; (4) deactivate the TEMP record. History stays under the old ID; the reason text links them. |

## Growth, retention, backups

* `POURequests` older than `RequestRetentionDays` (90) that are finished, and `POUSessions` older than `SessionRetentionDays` (30), are purged nightly. **The ledger is never purged** and must not get a retention policy that deletes. `POUOpsEvents` is kept until you delete resolved rows.
* Ledger rows pass 5,000 within about a year at 20 movements a day. App and flow queries are safe (indexed / ID order). In the SharePoint web UI, sort and filter the ledger only by **indexed** columns (LedgerKey, RequestID, LedgerType, Origin, PostingState, StockKey, ItemID, OccurredUtc, ReversesLedgerKey) or you will get a "list view threshold" error.
* Version history is on for data lists (500 versions). SharePoint's recycle bin and your tenant's Microsoft 365 backup policy are the restore path; confirm the retention with IT. The weekly Excel export above is a cheap second copy.

## Changing the flows or the app safely

The flows and the app are generated from `schema/` and the `pou_flows/` / `pou_app/` sources. To change behaviour: change the source, run `scripts\7_rebuild_package.cmd` (rebuilds and runs the whole test suite), re-import/re-paste, and repeat the **R** tests that the change could affect. Do not hand-edit flows in the designer without writing the change back to the source, or the next regeneration will undo it and the documents will no longer match.

Tuning knobs that are safe to edit directly in the designer: the sweeper recurrence (5 minutes) and the tick recurrences (hourly) - see the capacity doc for the trade-off.
