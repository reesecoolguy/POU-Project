# 08 - Testing and acceptance

Three kinds of evidence, never mixed up:

| Label | Meaning |
|---|---|
| **LOCAL** | Automated, runs on any PC with `scripts\7_rebuild_package.cmd` (or `python -m pytest`). Runs the generated flow definitions and Python tools against an **in-memory model of SharePoint** and a **home-made interpreter of the flow expression language**. Proves the logic; does **not** prove that SharePoint, Power Automate or Power Apps behave like the model. |
| **TENANT** | Must be run by you in Microsoft 365. Some have a script (`pou_tools.tenant_probe`, `pou_tools.permission_audit`), most are manual steps below. |
| **HARDWARE** | Must be run on a cabinet PC with the real scanner. |

Current LOCAL result for this package: **all passing** (`python -m pytest -q`; about 215 tests; the 5,300-row large-list test alone takes about 5 minutes). Re-run after any change.

"Required before go-live" = R. Record the date, who ran it and the result next to each in a copy of this table.

## A. Posting correctness (the ones that protect stock)

| ID | Scenario | LOCAL evidence | TENANT step (R) |
|---|---|---|---|
| T-RACE-01 | **Two operators withdraw the same last unit.** | `test_flow_concurrency.py::test_two_operators_withdraw_the_last_unit` (25 random interleavings: exactly one succeeds, the other is refused with "Only 0 on hand", stock never negative, one ledger row). `test_many_operators_race_for_limited_stock`. | Two PCs (or two browsers, two station accounts, two badges). Set an item to quantity 1. Both scan it and press REMOVE within about a second (count down aloud). Expect: one green, one red; On hand 0; exactly one ISSUE in the ledger. Repeat 10 times. **R** |
| T-RACE-02 | Same request processed by three workers at once (instant call + sweeper + retry). | `test_same_request_processed_by_three_workers_applies_once` | Create a request, press "Re-check" on History from two stations simultaneously; expect one ledger row. **R** |
| T-DUP-01 | **Double-click** ADD. | App: buttons disabled while busy; request id retained. Server: `test_double_processing_of_same_request_is_idempotent`, `test_duplicate_request_id_cannot_be_created_twice` | Double-click ADD quickly 10 times. Expect exactly one RECEIPT per intended entry. **R** |
| T-RETRY-01 | **Retry** after an error banner. | `test_fault_at_every_call_then_recovery` (crash/lost response at each of 16 calls) | Switch the PC's network off just after pressing REMOVE, back on after 20 s, press **Retry same request**. Expect: one movement, the same request number (first 8 characters shown on the button). **R** |
| T-LOST-01 | **Response lost** after the flow succeeded. | `test_fault_at_every_call_then_recovery[lose]` | As T-RETRY-01 but cut the network *after* the status shows Processing; on reconnect History must show `Succeeded` and the banner must be green **only** after the row says Succeeded. **R** |
| T-PART-01 | **Failure between writes** (stock updated, ledger/status not). | `test_fault_at_every_call_then_recovery[before/after]`, `test_applied_intent_is_finalised_not_voided_...`, `test_sweeper_completes_stock_applied_but_ledger_not_posted` | Cannot be forced from the UI. In the flow designer, temporarily add a Terminate (Failed) after `Apply_stock`; ADD 1; expect amber "quantity WAS updated... do not repeat"; remove the Terminate; within 5 minutes the sweeper finalises; ledger shows one Posted ADD; stock +1 once. **R** |
| T-SWEEP-01 | Recovery of lost instant calls. | `test_requests_whose_instant_call_was_lost_are_processed_by_the_sweeper`, `test_sweeper_resumes_a_run_that_died_after_writing_the_intent` | Create a request row by hand in SharePoint (type RECEIPT, a valid session) without calling the flow; within about 5-6 minutes it must become Succeeded. **R** |
| T-OOB-01 | Someone edits `OnHandQty` by hand. | `test_out_of_band_edit_is_detected_not_silently_overwritten`, `..._between_intent_and_apply_voids_the_intent` | As **site owner** change a quantity in SharePoint; try an ADD on it: expect red "does not match its history", a Critical row in `POUOpsEvents`, the e-mail from POU-Monitor; the nightly reconcile lists it. **R** |
| T-SHOW-01 | Never "success" unless proven; never "nothing changed" unless established. | `test_app_lint.py::test_success_is_only_shown_for_a_succeeded_request`; flow tests assert the `InventoryEffect` for every outcome | Review each banner message in T-RETRY/T-LOST/T-PART against the table in `06_Consistency_Limits.md`. **R** |

## B. Validation, identity and permissions

| ID | Scenario | LOCAL evidence | TENANT step (R) |
|---|---|---|---|
| T-VAL-01 | **Invalid quantities**: 0, negative, 2.5, text, a scanned barcode, 10,000, over the ADD limit, more than on hand. | `test_invalid_quantities_rejected`, `test_receipt_over_limit_rejected`, `test_issue_more_than_on_hand_is_rejected_with_nothing_changed`; app: `test_quantity_inputs_are_validated_by_pattern_not_by_coercion` | In the app type each value into Quantity; the buttons must stay disabled with the explanation and nothing may be truncated. Then **bypass the app**: add a POURequests row by hand with Quantity 0 / 2.5 / -3 / 600 (RECEIPT) and run the flow; each must be Rejected with a message. **R** |
| T-ID-01 | Does the platform pass the caller's identity header (`x-ms-user-email-encoded`) to the app-triggered flow? | model only | Run POU-Session from the app; open the run in Power Automate -> Trigger outputs -> headers. Note the result in `11_Validation_Status.md`. Design remains safe either way (see doc 04). **R** |
| T-ID-02 | **Inactive badge**, unknown badge. | `test_login_rejects_unknown_and_inactive_badges`, `test_badge_deactivated_after_login_is_rejected` | Set a badge's `Active` to No; scan it: "This badge is not active". Deactivate while signed in; the next request is refused. **R** |
| T-ID-03 | Session bound to the Microsoft account / station. | `test_session_from_another_microsoft_account_is_rejected`, `test_station_expected_account_is_enforced`, `test_forged_or_missing_session_is_rejected` | Sign in on CAB-01; create a POURequests row by hand as another account quoting that session id: rejected `SESSION_ACCOUNT_MISMATCH`. **R** |
| T-ID-04 | Idle timeout 3 minutes (client) and 10 minutes (server). | `test_session_idle_expiry_enforced_on_server`; app timer wiring checked statically | Sit idle 3 minutes: back to the badge screen. Verify the timer runs while the window is not focused. **R** |
| T-PERM-01 | **Unauthorised adjustment / opening / approve** by an operator. | `test_unauthorized_adjustment_and_opening_and_approve_by_operator`, `test_approval_by_non_supervisor_account_or_self_is_ignored`, `test_adjustment_requires_reason_and_supervisor` | As an operator account, add an ADJUSTMENT request by hand: `NOT_AUTHORIZED`, quantity unchanged. **R** |
| T-PERM-02 | **Permissions matrix is real.** | `test_foundation.py` permission tests (model) | `scripts\6_permission_audit.cmd` as operators, supervisors, admins, flowservice: all OK. Then, signed in as an operator in the SharePoint UI: try to edit a quantity ("Edit in grid view") and delete a ledger row - both refused. **R** |
| T-PERM-03 | **Flow connection identity.** | model only | In `POUStockLocations` open an item changed by a test ADD -> Version history: *Modified By* must be the flow service account, never the operator. **R** |
| T-APPR-01 | Supervisor approval path, separation of duties. | `test_operator_audit_waits_then_supervisor_approval_releases_it`, `test_supervisor_rejection_blocks_the_request`, `test_supervisor_can_audit_directly_without_badge_session` | Operator counts an item -> amber "Waiting for a supervisor". Supervisor (own device, own account) -> Continue as supervisor -> Approvals -> APPROVE: the count posts. Try approving with the same account that filed it: refused. **R** |
| T-NEW-01 | New item needs a supervisor; creates no quantity; duplicate IDs and bad locations refused. | `test_item_create_needs_supervisor_and_creates_no_quantity`, `test_item_create_rejects_duplicates_bad_location_and_bad_input` | Operator files NEW ITEM -> waits; supervisor approves; item exists with `NoBalance`; ADD is refused until counted. **R** |

## C. Data

| ID | Scenario | LOCAL evidence | TENANT step |
|---|---|---|---|
| T-DATA-01 | **Duplicate parts across locations** (K102516, K102517, K13471). | `test_repeated_item_id_at_two_locations_is_kept_as_two_stock_records`, `test_same_part_at_two_locations_posts_independently` | Scan K102516: the app lists its locations and asks which. REMOVE at one location changes only that location. **R** |
| T-DATA-02 | IDs as text, leading zeros, blank not zero, no cap above Max, no invented values. | `test_transform.py` (14 tests incl. golden numbers for the real workbook) | After import, open `POUItems`, `POUStockLocations`: spot-check 10 rows against the workbook, including a numeric ID and a blank On Hand. **R** |
| T-DATA-03 | Import is repeatable and does not overwrite. | `test_import.py` | Run `3_import.cmd` twice; second run reports all OK. |
| T-DATA-04 | Reconciliation: row counts and quantities by item/location. | `migration/reconciliation/*.csv`; `test_post_import_verification_states` | `4_verify_import.cmd` after openings: 252 matched, total 973. **R** |
| T-AUD-01 | **Stale audit** requires a recount. | `test_stale_audit_is_rejected_and_requires_recount` | Operator A starts a count on an item and enters the number; before pressing POST, operator B removes 1; A presses Review: red "STOCK MOVED... RECOUNT". Also test the case where the movement happens *after* Review but before approval: the server refuses with `STALE_COUNT`. **R** |
| T-AUD-02 | Variance >= 5 needs an extra confirmation. | app text/wiring checked statically | Count 5 more or 5 fewer than the system: the button reads "Variance is +5 - I recounted. POST COUNT" and is red. Count 4 off: plain green. |
| T-LOW-01 | Low-stock rule and flag. | `test_low_stock_flag_follows_rule`, `test_daily_low_stock_content_and_once_per_day` | Set `LowStockRule` to LT and LE; the flag and the next report change. |

## D. Large lists and reports

| ID | Scenario | LOCAL evidence | TENANT step |
|---|---|---|---|
| T-BIG-01 | **List view threshold** and completeness beyond 2,000 and 5,000 rows. | `test_reports_are_complete_beyond_2000_and_5000_rows` (5,300 rows: a filter matching >5,000 is refused by the model as SharePoint does; ID-paged jobs return every row) | `scripts\5_tenant_probe.cmd APPLY 5100` (checks L1-L4 on your tenant). Then run POU-Reconcile and POU-WeeklyUsage by hand against a copy of the site with >5,000 stock rows if you will ever have that many. **R** if lists may exceed 5,000 |
| T-BIG-02 | Delegation in the app. | `app/docs/DELEGATION.md`, `pou_app/lint.py` | Studio shows **no blue delegation warning** anywhere. **R** |
| T-REP-01 | Daily low-stock, weekly health, reconcile, usage 30/90, monitor, with configurable recipients/schedules/time zone. | `test_flow_reports.py` (10 tests) | Replace the recipients; set the hour to the current hour; check each e-mail arrives once; set the placeholder again and confirm an ops event instead of mail. **R** |
| T-REP-02 | Replenishment suggestions do not imply open orders. | text in reports; `test_daily_low_stock...` | Read one report: "Suggestions only... do not consider open purchase orders". |

## E. Scanner hardware (cabinet PC) - HARDWARE, all **R**

| ID | Test | Pass criterion |
|---|---|---|
| T-HW-01 | Scanner suffix **Enter**: scan a badge, an item, a location. | Each scan commits by itself within about half a second; no manual click; no extra characters in the box. |
| T-HW-02 | Scanner suffix **Tab**. | Same. (Focus may move; the commit still happens.) |
| T-HW-03 | **No suffix** (type the code, wait). | Commits after the debounce; typing a 4-digit quantity is never committed as a scan (Quantity is a different box). |
| T-HW-04 | **Barcode into the Quantity box** (scan an item tag while Quantity is focused). | Red message "Was a barcode scanned into this box?"; ADD/REMOVE stay disabled; nothing is truncated or clamped. |
| T-HW-05 | **Previously scanned item**: scan item A, do not submit, scan item B. | Screen shows only B; quantity cleared; submitting posts B only. Repeat with a location scan. |
| T-HW-06 | Code-39 `*` start/stop and lower-case: scan a tag whose text is `*K102516*`. | Item found (asterisks and case ignored). |
| T-HW-07 | Very fast scanning of two items in a row (about 1 second apart). | No lost or merged scans. If merged scans appear, raise `ScanCommitIdleMs`. |
| T-HW-08 | Keyboard/language layout and Caps Lock on. | Item IDs still match. |
| T-HW-09 | Two stations: scan simultaneously. | Each shows its own identity bar (Station CAB-01 / CAB-02 and the employee). |
| T-HW-10 | Browser/window focus: click elsewhere, scan. | Scanner input goes to the focused box; if not, the box is re-focused after the next action. Note behaviour. |

## F. App behaviour that only Studio/the browser can show - TENANT, **R**

| ID | Test |
|---|---|
| T-APP-01 | Every screen opens with no red formula errors; the paste/assembly worked (`07_Deployment.md` step 10). |
| T-APP-02 | Name and Station are visible on every operator screen; they change when another badge signs in. |
| T-APP-03 | Network failure (Wi-Fi off) during lookup, during submit, during login: message says what is known; no green. |
| T-APP-04 | Hidden timers run (idle sign-out, scan commit, status polling). If a player stops invisible/tiny timers, enlarge them to 20x20. |
| T-APP-05 | No blue delegation warnings (compare with `DELEGATION.md`). |
| T-APP-06 | Logout-after-submit setting (`LogoutAfterSubmit`) true/false takes effect without republishing. |
| T-APP-07 | The Windows player and the browser both work; tablet/phone is **not** supported by the fixed layout. |
| T-APP-08 | Concurrent use: two stations, 20 movements each, then reconcile: ledger sums equal stock; POU-Reconcile reports no findings. |
| T-APP-09 | `SaveData/LoadData` outbox: file a request, close the browser tab before the answer, reopen, sign in: the "earlier request was never confirmed" banner appears with the same request number. If it does not (player lacks local storage), record it in `11_Validation_Status.md`. |

## G. Performance and capacity - TENANT

| ID | Test |
|---|---|
| T-CAP-01 | Time 20 consecutive ADDs: expected 5-15 s each (`05_Platform_Facts_and_Capacity.md`). Record the median. |
| T-CAP-02 | After a normal day, read the flow service account's request usage (Power Platform admin center -> Resources -> Capacity -> Power Platform requests) and compare with the estimate (about 2,950 + about 185 per sign-in-per-transaction movement). If throttled, decide D1 again. **R** |

## H. How to re-run the LOCAL suite

```
scripts\7_rebuild_package.cmd      (regenerates flows/app/docs and runs everything)
python -m pytest -q                (about 6 minutes; add --deselect tests/test_flow_reports.py::test_reports_are_complete_beyond_2000_and_5000_rows for 1 minute)
POU_LARGE_N=600 python -m pytest tests/test_flow_reports.py::test_reports_are_complete_beyond_2000_and_5000_rows   (quick scaled run)
```
