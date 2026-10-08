# 09 - Controlled cutover, comparison period and rollback

## Rules that make this safe

1. **One authoritative system at any moment.** Until the cutover instant the workbook is the only live system. After it, SharePoint is. There is never a period in which staff enter the same movement into both. (Dual live posting is the classic way to end up with two different "truths" and no way to say which is right.)
2. **A comparison period uses shadow/replay, not double entry.** The workbook stays live; its recorded movements are *replayed by a tool* into a separate test copy of the new system, and the two are compared. Staff type each movement once.
3. **Opening balances are verified, not assumed.** A workbook figure is only a candidate until a person has counted it.
4. **Legacy history is history.** It is imported with `Origin=Legacy`, `AffectsBalance=No` and is never re-applied to any balance.
5. **Rollback must not lose post-cutover transactions.** Anything entered in SharePoint after cutover is exported and carried back (or forward again) - never discarded.

## Phase 0 - Gates (all must be true)

* `08_Testing_and_Acceptance.md`: every **R** test has a recorded PASS, including the scanner tests on the real cabinet PC(s) and T-RACE-01 on two PCs.
* Decision **D1** (licence/capacity) is made and the flow service account has the licence; T-CAP-01 timing is acceptable to the operators.
* Supervisors and admins exist in `POUEmployees` with `MicrosoftUPN`, and one of them has actually approved a test request end to end.
* Recipients are real (the daily/weekly reports and the Monitor e-mail go to people who will read them).
* A rehearsal has been done on a **test site** (below), including a rollback.

## Phase 1 - Rehearsal on a TEST site (repeat until boring)

1. Create a second SharePoint site (`POU-Test`), provision it exactly like production (`scripts\1_provision.cmd APPLY` with `SITE_URL` pointing at it), import reference data and the baseline openings (`3_import.cmd APPLY`), turn on **a copy of the flows** pointed at the test site (edit `Cfg_SiteUrl`), publish a test copy of the app (`POU-Test`).
2. Set `ServerSessionMaxIdleMinutes` to 720 in the test site's settings (replay requests are created in bursts).
3. Keep the **baseline extract**: `python -m pou_tools.extract "<copy of workbook>" --out migration\shadow\baseline.json` taken the same day as the import.

## Phase 2 - Comparison period (shadow/replay), typically 1-2 weeks

The workbook remains live. Each day (or at the end of the period):

1. Copy the live workbook (never open the live one in a way that could change it) and extract it: `python -m pou_tools.extract "<copy>" --out migration\shadow\current.json`.
2. `python -m pou_tools.shadow_replay plan --baseline migration\shadow\baseline.json --current migration\shadow\current.json` - lists the movements since the baseline and how each can be handled:
   `REPLAYABLE`, `AMBIGUOUS_LOCATION` (the workbook never recorded a location, so a movement of K102516, K102517 or K13471 cannot be attributed - it is **never guessed**), `UNKNOWN_ITEM`, `BAD_QUANTITY`, `BAD_TYPE`.
3. `... shadow_replay replay ... --site-url <TEST site>` (dry run) then `--apply`. It files one request per replayable movement (`RequestID = SHADOW-T-r<row>`, safe to re-run) under a "Replay" employee and session. The test site's sweeper posts them within minutes, with all the real rules.
4. `... shadow_replay compare ... --site-url <TEST site>` -> `migration\shadow\shadow_compare.csv`, one row per item/location:

| Status | Meaning | Action |
|---|---|---|
| `MATCH` | test site = workbook | none |
| `EXPLAINED_BY_AUDIT` | the difference equals the sum of workbook count variances (a count overwrote On Hand; counts are not replayed) | none |
| `AMBIGUOUS_ITEM` | the item is in several locations and had unattributable movements | physical count of those locations |
| `NOT_YET_PROCESSED` | requests still open | wait for the sweeper |
| `DIFF_UNREPLAYABLE_ROWS` | unknown item / bad rows were in the workbook log | fix the data, decide per row |
| `DIFF` | **unexplained** | investigate: this is the finding the exercise exists to produce |

The tool exits non-zero if there is any `DIFF`. **Exit criterion:** no `DIFF`, every `AMBIGUOUS_ITEM` resolved by a count, for the agreed number of days.

Also during this period: operators practise on the **test** app with the test site (training), and the reports run against test data so recipients see what they will receive.

## Phase 3 - Opening-balance options (decision D5)

| | A - import workbook figures, then count over time (default) | B - strict: count first |
|---|---|---|
| How | Import `openings` (252 requests). Each record becomes `Unverified` with the workbook figure; the app says "Quantity not yet verified by a count". Supervisors/counters verify location by location (AUDIT, supervisor approval). | Skip the `openings` stage. Every record is `NoBalance`; nothing can be ADDed or REMOVEd until its first count is posted (AUDIT; first count needs no previous balance). |
| Pros | Cabinet usable immediately; the count of record is traceable (a variance between the opening and the count is itself a ledger entry). | Nothing unverified ever circulates. |
| Cons | Unverified numbers are in use until counted. Set `AllowIssueAgainstUnverified` = false to forbid it. | Cutover day needs a full count (254 records) before use. |

Either way **the cutover count is the verification**: schedule it.

## Phase 4 - Cutover day

Do this at a quiet time, with a supervisor and an admin present. The cabinet is out of service while step 3 runs.

1. **Freeze the workbook**: announce; save a final copy as `POU_..._FINAL_<date>.xlsm`, set it read-only, record its sha256 (`certutil -hashfile <file> SHA256`). From this moment nobody types into it.
2. Re-extract and re-transform from the **final** copy (`2_extract_validate.cmd`); read `RUN_SUMMARY.md` and the exceptions again. If the transform changes the previous import (it will if movements happened since), use a fresh production import (production has no quantities yet, so nothing to roll back).
3. Import to **production**: `3_import.cmd APPLY locations,employees,items,stock,ledger`, set supervisors/admins in `POUEmployees`, then (option A) `3_import.cmd APPLY openings`; wait for the sweeper; `4_verify_import.cmd` -> **row counts and quantities reconcile by item/location** (252 matched, total as in `RUN_SUMMARY.md` for that day's file). Keep the reconciliation CSV.
4. Run a **smoke test** with the real scanner: one ADD and one REMOVE of a test item, each reverted by REVERSAL (supervisor), confirm the ledger shows all four rows and the quantity is back.
5. **Go**: tell operators; the SharePoint system is now authoritative. Remove the workbook's launcher (rename the file) so nobody uses it by habit.
6. First day: a supervisor watches `POUOpsEvents` and the Monitor e-mails; the 02:00 reconcile result is read the next morning.
7. Start the verification counts (option A) - e.g. N records a day, highest-value first. Every posted count turns that record `Verified`.

## Rollback

Decide beforehand the **trigger** (examples: more than N unexplained Critical ops events in a day; reconciliation finds drift on more than M records; flows cannot be restored within X hours) and **who** decides.

### Before the first real post-cutover movement
Nothing to carry back. Switch operators back to the workbook (still frozen and intact), mark the SharePoint site read-only (remove the app from the Operators group), investigate.

### After real movements have been posted in SharePoint
The goal is that **no movement entered since cutover is lost**:

1. **Stop posting**: turn off POU-ProcessRequest (and tell operators to stop). Run the sweeper once more by hand, wait until `POURequests` has no open rows, or list the open ones.
2. **Export what happened**: SharePoint `POULedger` filtered `Origin = Live` and `OccurredUtc >= <cutover time>` (export to Excel) plus every request that is not `Succeeded` (those never moved stock). This is the authoritative list of post-cutover movements.
3. **Bring the workbook forward**: take the FINAL frozen workbook, apply the exported movements per item/location (the ledger has location and before/after, so unlike the workbook's own log nothing is ambiguous), and verify the result against the SharePoint quantities by item/location (the reconciliation CSV from `4_verify_import` / `POU-Reconcile` shows the SharePoint side). Re-open the workbook for operators.
4. Keep the SharePoint site **intact and read-only** as evidence. Do not delete lists.
5. When the problem is fixed, repeat from Phase 2: a rollback does not lose the new system's ledger; roll *forward* by importing the post-rollback workbook movements the same way (a new baseline, or fresh production import if SharePoint is to be restarted).

This procedure is manual and was **not rehearsed here**; rehearse it in Phase 1 with test movements.
