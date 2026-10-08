# Source-to-target field mapping

Source: `POU_Inventory_Pilot Test _With_Badge.xlsm`. Every row below is implemented in `pou_tools/transform.py` and covered by `tests/test_transform.py`; the numbers for the real workbook are in `migration/RUN_SUMMARY.md`; every anomaly is in `migration/exceptions/exceptions.csv`.

| Source sheet | Source column | Target | Rule |
|---|---|---|---|
| Inventory | Item ID | `POUItems.ItemID  +  POUStockLocations.ItemID` | Text, exactly as stored. A numeric cell becomes its digits ('100416'); leading zeros cannot be recovered from a number and are reported (NUMERIC_ITEM_ID). Never zero-padded. |
| Inventory | Item ID + Location | `POUStockLocations.StockKey` | UPPER(TRIM(ItemID)) | UPPER(TRIM(Location)). One stock record per item per location. K102516, K102517 and K13471 therefore produce several stock records under ONE item. |
| Inventory | Item Name | `POUItems.ItemName  +  POUStockLocations.ItemName (copy)` | Master value taken from the first row of the item; differences between rows are reported (SAME_NAME_DIFFERENT_ID / MASTER_VALUE_FROM_SIBLING_ROW). |
| Inventory | Location | `POULocations.LocationCode  +  POUStockLocations.LocationCode` | Distinct spellings (22) become the location list. Non-standard codes are reported, never changed. |
| Inventory | Min Qty | `POUStockLocations.MinQty` | As is. Min = 0 reported (MIN_ZERO). |
| Inventory | Max Qty | `POUStockLocations.MaxQty` | As is. Max = 0 reported (MAX_ZERO). Never used to cap a quantity. |
| Inventory | On Hand Qty | `POURequests (OPENING) -> POULedger -> POUStockLocations.OnHandQty` | NOT written to the stock record by the import. Each numeric value becomes one OPENING request that the flow posts, so the ledger explains the balance. A BLANK value creates a stock record with BalanceStatus=NoBalance and NO opening request (BLANK_ONHAND). Blank is never zero. Values above Max are kept (ONHAND_ABOVE_MAX). |
| Inventory | Barcode | `(not migrated)` | Formula `="*"&A2&"*"`. Derived data. Existing printed tags keep working: the app removes * characters. |
| Inventory | Area: | `POUStockLocations.Area` | As is (single value in this workbook: AREA_SINGLE_VALUE). |
| Inventory | Description | `POUItems.Description` | Multi-line text kept. |
| Inventory | Manufacturer | `POUItems.Manufacturer` | As is; spelling variants reported, not merged (MANUFACTURER_SPELLING_VARIANTS). |
| Inventory | Notes / Priority / Lead Time / Cost per Unit | `POUItems.Notes / Priority / LeadTimeDays / UnitCost` | Carried when present; empty source columns reported (SOURCE_COLUMN_EMPTY). Nothing invented. |
| Inventory | (row number) | `POUStockLocations.LegacySourceRow, POUItems.LegacySourceRows` | Provenance back to the workbook row. |
| Users | Badge ID | `POUEmployees.BadgeID` | Text. Numeric badges keep their digits (NUMERIC_BADGE). |
| Users | Employee Name | `POUEmployees.EmployeeName` | As is. |
| Users | (none) | `POUEmployees.Active / Role / MicrosoftUPN` | The workbook has no such columns: everyone is imported Active, Role=Operator, MicrosoftUPN empty (EMPLOYEE_ROLES_UNKNOWN). Supervisors/Admins must be set up by hand (docs/07_Deployment.md). |
| Transactions | Timestamp | `POULedger.OccurredUtc (+ OccurredLocalText, LegacyTimestampText)` | Original timestamp kept. The workbook stores no time zone: America/Chicago is ASSUMED and converted to UTC; ambiguous/non-existent DST times are flagged (LEGACY_TIMEZONE_ASSUMED). |
| Transactions | Item ID | `POULedger.ItemID (+ LocationCode only if provable)` | Location was never recorded. LocationResolution = UniqueAtCutover only when the item is stocked in exactly ONE location; Unresolved otherwise. No location is guessed. |
| Transactions | Transaction Type / Quantity | `POULedger.LedgerType (ADD->RECEIPT, REMOVE->ISSUE), QtyDelta (signed)` | QtyBefore/QtyAfter stay BLANK: the workbook did not record them. |
| Transactions | User | `POULedger.LegacyUser / EmployeeName` | The NAME as typed in the workbook. No badge is attached and no employee identity is inferred. |
| InventoryAudit | Date/Time, Item ID, Previous Qty, Counted Qty, Variance, User | `POULedger (LedgerType=AUDIT)` | QtyBefore=Previous, QtyAfter=Counted, QtyDelta=Counted-Previous. If the recorded Variance disagrees both are preserved and flagged. Chain gaps between consecutive counts are reported (LEGACY_AUDIT_CHAIN_GAP). |
| (all legacy ledger rows) | - | `POULedger.Origin=Legacy, AffectsBalance=No, PostingState=Posted` | History only. These rows are NOT re-applied to any balance; the balance comes only from the verified OPENING at cutover. |
| ReorderQueue / ReorderReport / Usage Summary / Dashboard / Scanner / Launcher | - | `(not migrated)` | Derived or scratch sheets (SHEET_NOT_MIGRATED). Replaced by LowStockFlag, the daily low-stock report and the weekly 30/90-day usage report. |
