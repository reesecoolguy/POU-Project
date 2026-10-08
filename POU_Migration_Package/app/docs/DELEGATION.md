# Delegation matrix (generated)

Every query against a SharePoint list that the app makes, with its delegation expectation. **This table is generated from the app source and our reading of the Microsoft delegation rules; it was NOT produced by the Power Apps checker.** Open each screen in Studio and confirm there is no blue delegation warning on the formulas below (test T-APP-05).

Two different limits are involved and must not be confused:

* **App data row limit** (default 500, maximum 2,000): how many rows a *delegated* query hands back to the app. Every gallery here is `FirstN(..., N)`-bounded and the Low-stock screen prints a warning if the result reaches the limit.
* **SharePoint list view threshold** (5,000): a query that needs to *examine* more than 5,000 rows fails unless it can use an index. Every column filtered on the three large lists (Requests, Ledger, Stock) is indexed (checked by the linter); `ID`-ordered reads need no index.

Things the app deliberately does **not** do against SharePoint: `CountRows`/`Sum`/`Search`/`in`/`Len(column)`/`Lower(column)`/`Distinct`/`GroupBy`. Totals, usage (30/90 days) and reconciliation are computed by the flows (which page by ID) and delivered by email/report.

| Where | Query | Size | Expectation |
|---|---|---|---|
| `App.OnStart` | `LookUp(POUStations, Active = true , ExpectedAccountUPN = Lower(User().Email))` | small list | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns). WARNING unindexed: ['Active', 'ExpectedAccountUPN'] |
| `App.OnStart` | `LookUp(POUEmployees, MicrosoftUPN = Lower(User().Email) , Active = true)` | small list | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns). WARNING unindexed: ['Active'] |
| `scrScan.btnRunScan.OnSelect` | `LookUp(POURequests, RequestID = varReq.RequestID)` | yes | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrScan.btnRunScan.OnSelect` | `LookUp(POUStockLocations, StockKey = locSel.StockKey)` | yes | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrScan.btnFindScan.OnSelect` | `Filter(POUStockLocations, ItemID = scan , Active = true)` | yes | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrScan.btnFindScan.OnSelect` | `LookUp(POUItems, ItemID = scan)` | small list | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrAddItem.lblLocOkAddItem.Text` | `LookUp(POULocations, LocationCode = Upper(Trim(Substitute(txtLocCodeAddItem.Text, "*", ""))) , Active = true)` | small list | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns). WARNING unindexed: ['Active'] |
| `scrAddItem.lblAddWhyAddItem.Text` | `LookUp(POUItems, ItemID = Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))))` | small list | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrLowStock.galLowLow.Items` | `Filter(POUStockLocations, Active = true , LowStockFlag = true , StartsWith(ItemID, Upper(Trim(Substitute(txtFilterLow.Text, "*", "")))))` | yes | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrHistory.galReqHist.Items` | `Filter(POURequests, StationID = varStation)` | yes | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrHistory.galLedHist.Items` | `Filter(POULedger, ItemID = Upper(Trim(Substitute(txtHistItemHist.Text, "*", ""))))` | yes | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrHistory.galLedHist.Items` | `SortByColumns(POULedger, "ID" , SortOrder.Descending)` | yes | Delegable when the column is a plain column or ID (verify the blue-underline indicator in Studio) |
| `scrSupervisor.btnRunSup.OnSelect` | `LookUp(POURequests, RequestID = varReq.TargetRequestID)` | yes | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrSupervisor.galQueueSup.Items` | `Filter(POURequests, IsOpen = true , RequestStatus.Value = "AwaitingSupervisor")` | yes | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrSupervisor.galRevSup.Items` | `Filter(POULedger, StockKey = locSel.StockKey)` | yes | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrAdmin.galSetAdmin.Items` | `Filter(POUSettings, StartsWith(SettingKey, Trim(txtSetFilterAdmin.Text)))` | small list | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrAdmin.btnNewLocAdmin.OnSelect` | `LookUp(POULocations, LocationCode = Upper(Trim(Substitute(txtNewLocAdmin.Text, "*", ""))))` | small list | Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns) |
| `scrAdmin.galLocListAdmin.Items` | `SortByColumns(POULocations, "LocationCode" , SortOrder.Ascending)` | small list | Delegable when the column is a plain column or ID (verify the blue-underline indicator in Studio) |
| `scrAdmin.galStnAdmin.Items` | `SortByColumns(POUStations, "StationID" , SortOrder.Ascending)` | small list | Delegable when the column is a plain column or ID (verify the blue-underline indicator in Studio) |

Client-side (collection) operations such as `CountRows(colStock)` run on at most the rows already downloaded and are not a delegation concern.
