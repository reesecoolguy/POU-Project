# Migration run summary

Source: `POU_Inventory_Pilot Test _With_Badge.xlsm`  sha256 `b46a6239b64183ed7fad9c1f44123dea10e2f78a70fba70a7e0004f1dfd1397e`

- **inventory_rows**: 254
- **stock_records_imported**: 254
- **stock_records_held**: 0
- **items**: 251
- **locations**: 22
- **items_with_multiple_locations**: 3
- **opening_requests**: 252
- **blank_or_invalid_onhand**: 2
- **sum_opening_quantity**: 973
- **employees**: 7
- **legacy_ledger_rows**: 26
- **legacy_rows_held**: 0
- **exceptions**: {'WARN': 33, 'INFO': 46}
- **low_stock_le_min**: 71
- **low_stock_lt_min**: 9
- **source_timezone_assumed**: America/Chicago

## Row-count reconciliation

| Check | Source | Target | Status | Note |
|---|---:|---:|---|---|
| Inventory rows -> stock-location records (+ held) | 254 | 254 | OK | 254 imported + 0 held in exceptions |
| Distinct Item IDs -> item master rows (+ ids wholly held) | 251 | 251 | OK |  |
| Stock records with a numeric On Hand -> OPENING requests | 252 | 252 | OK |  |
| Stock records with blank/invalid On Hand -> NoBalance (no opening request) | 2 | 2 | OK |  |
| Sum of source On Hand (imported rows) -> sum of OPENING quantities | 973 | 973 | OK |  |
| Sum of source On Hand (all rows) -> imported rows + held rows | 973 | 973 | OK |  |
| Users rows -> employees (+ held) | 7 | 7 | OK |  |
| Transactions rows -> legacy ledger rows (+ held) | 13 | 13 | OK |  |
| InventoryAudit rows -> legacy ledger rows (+ held) | 13 | 13 | OK |  |
| Locations: distinct normalised locations -> locations | 22 | 22 | OK |  |
| Duplicate StockKeys in import file | 0 | 0 | OK |  |
| Duplicate LedgerKeys in legacy ledger | 0 | 0 | OK |  |
