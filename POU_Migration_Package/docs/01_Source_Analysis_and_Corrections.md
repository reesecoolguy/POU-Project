# 01 - What the workbook really does, and what changed from the earlier proposal

Read this first if you want to know *why* the design looks the way it does. Everything here was found by reading the two files you supplied; nothing was assumed from their names.

## Files inspected

| File | What it is | Evidence |
|---|---|---|
| `POU_Inventory_Pilot Test _With_Badge.xlsm` (sha256 `b46a6239...f1397e`, 330,625 bytes) | The live pilot workbook. 10 sheets (3 hidden), table `Table1` = `Inventory!A1:N255` (254 stock rows), `Transactions` 13 rows, `InventoryAudit` 13 rows, `Users` 7 rows, VBA project with 4 forms and 5 standard modules. | `migration/source_extract/extract.json`, VBA re-read with `oletools` (macros were never executed). |
| `POU_Inventory_CodePack.zip` | A *VBA hardening pack* for the same workbook (11 files). It improves the Excel macros; it is not a migration and does not touch SharePoint. | Opened and read; treated as an unverified reference as you asked. |

## What the existing VBA does that matters for the migration

| # | Behaviour (where) | Consequence | How the new design handles it |
|---|---|---|---|
| 1 | Items are located **by Item ID only**, first match wins (`Range.Find ... LookAt:=xlWhole` in `btnSubmit_Click`, loop in `txtBarcode_AfterUpdate`). | 3 Item IDs are stocked in more than one location (**K102516, K102517, K13471**). Only the first row can ever be scanned; the others are unreachable. | Item master (`POUItems`, one row per Item ID) is separate from stock records (`POUStockLocations`, one row per item **and** location, unique `StockKey = ITEM|LOCATION`). The scan screen asks which location when an item has several. Nothing is merged, deleted, renumbered or rejected. |
| 2 | `txtQty_Change` / `cboTransaction_Change` silently **clamp** the typed quantity to the spin-button range (REMOVE: current on-hand, min 1; ADD: 100). | A part number scanned into the Quantity box is silently turned into some other number. | Quantity must match `^[1-9][0-9]{0,3}$`; anything else is refused with a message and never truncated. ADD limit is a central setting (default 500). The server re-checks. |
| 3 | A blank *On Hand* cell is read into a `Long` (`currentQty = foundCell.Offset(0,5).Value`) = **0**. | K102516 and K102517 at 2-A have blank On Hand; an ADD would turn "unknown" into a real-looking number. | Blank stays blank. Stock record is `BalanceStatus = NoBalance`; ISSUE/RECEIPT are refused until a supervisor counts it. Never zero-filled. |
| 4 | Two different low-stock rules: `ProcessScan` uses `<` Min, the form uses `<=` Min. The `ReorderQueue` sheet is stale (contains negative suggested quantities). | On this data `<=` flags 71 records and `<` flags 9. | One rule, central setting `LowStockRule` (default `LE`, i.e. On hand <= Min), computed by the server into `LowStockFlag`. |
| 5 | Inventory cell is updated, **then** a row is appended to `Transactions`. Two separate writes in a shared file. | A crash between them, or two operators, leaves quantity and log disagreeing; last writer wins. | One posting path with an append-only ledger and a stock-version compare-and-swap (see `02_Architecture.md`, `06_Consistency_Limits.md`). |
| 6 | The transaction log records time, Item ID, type, quantity, user **name**. No location, no before/after, no badge, no station. | History cannot be tied to a stock record or an identity. | New ledger records all of these. Legacy rows are imported as history with the fields the workbook never had left **blank** (not invented). |
| 7 | Badge = typed/scanned ID matched against `Users` sheet (name match). No roles, no active flag. Session timeout 15 minutes (`modSecurity`). | Anyone who can edit the file can add a badge; there is no supervisor concept. | Badge identifies the employee only; the session is bound server-side to the Microsoft account running the app and the station; supervisors authenticate with their **own** Microsoft sign-in. Idle timeout default 3 minutes (central). |
| 8 | `Barcode` column is a formula `="*"&A2&"*"` (Code-39 start/stop). | Derived data. | Not migrated. The app strips `*`, so existing printed tags keep working. |
| 9 | Two Item IDs (100416, 100674) and all 7 badge IDs are numeric cells; one stray note far down `Inventory` (`A1:P1378`). | Leading zeros may already have been lost by Excel. | IDs are text; digits kept exactly; no zero padding; reported as `NUMERIC_ITEM_ID` / `NUMERIC_BADGE` / `STRAY_CELL`. |

## Corrections to the earlier proposal (the CodePack and the thinking behind it)

1. **It hardens Excel; it does not migrate.** There is no data model, no SharePoint, no Power Apps, no flows. This package replaces it.
2. **It treats Item ID as unique.** `LoadItem` "refuses duplicates" and its health check tells you to fix duplicate IDs. For your data that would make K102516, K102517 and K13471 unusable and push you to renumber or merge them - which you ruled out.
3. **Authority came from a spreadsheet cell and a VBA variable.** `Users!C = ADMIN` and `CurrentUserRole` are editable by anyone with the file; the sheet password sits in source (`SHEET_PASSWORD = "ChangeMe!2026"`). Sheet protection is not access control. In the new design authority is the Microsoft sign-in of the request author, checked by the flow, enforced by SharePoint permissions.
4. **It cannot protect against two operators or a lost write.** Excel files have no atomic multi-step write. Concurrency control (ETag) alone would not have fixed this either - see `06_Consistency_Limits.md`.
5. **Blank quantities and "capping".** The pack continues to coerce blanks (`ToLong`) and clamp quantities. The new design refuses both.
6. **One shared account, one licence?** Earlier thinking that "the app runs as one account so licensing is covered" is wrong in general: the *running* Microsoft account, the *flow connection owner* and the *employee* are three different things, and licence/capacity is metered per flow owner. Quantified in `05_Platform_Facts_and_Capacity.md`; IT must confirm.
7. **"Success" shown when a request is queued.** The new app shows green only when the request row says `Succeeded`, and shows "NOT CONFIRMED - do not repeat" for anything it cannot prove.
8. **Replenishment.** The workbook's reorder queue mixed suggestion and purchasing. The new reports give *suggestions* only (Max - On hand), explicitly not considering open orders.
9. **The earlier idea of importing On Hand directly** is dropped: a balance with no ledger entry cannot be explained or reconciled. Balances arrive only as `OPENING` ledger entries posted through the same path as everything else.

## Open points found in the data (full list: `migration/exceptions/exceptions.csv`)

* 2 stock records with blank On Hand (`BLANK_ONHAND`): K102516 and K102517 at 2-A.
* 29 records above Max (`ONHAND_ABOVE_MAX`) - kept as is, confirm at the opening count.
* 142 `TEMP####` placeholder Item IDs (`TEMPORARY_ITEM_IDS`) - kept unchanged; renaming procedure in `10_Maintenance.md`.
* 28 records have Min = 0 (`MIN_ZERO`): under "On hand <= Min" they are low stock at zero.
* Priority, Lead Time and Cost per Unit are empty on every row (`SOURCE_COLUMN_EMPTY`): the columns exist but hold nothing. A stray note in the workbook asks for a report "to show on-hand inventory of priority 1 items": it cannot be produced until Priority is filled in (see `12_Continuation_Checklist.md`).
* No roles anywhere: nobody is a supervisor until you set one up (`EMPLOYEE_ROLES_UNKNOWN`).
* Workbook timestamps carry no time zone: America/Chicago assumed (`LEGACY_TIMEZONE_ASSUMED`).
