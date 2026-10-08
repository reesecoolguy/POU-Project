# POU-WeeklyHealth - POU - Weekly data-health check

Hourly tick; once per week: orphans, parameters, roles, placeholders; repairs the denormalised ItemName.

- **Trigger**: Recurrence 1 h (tick) - Weekly on WeeklyDayOfWeek / WeeklyHourLocal
- **Actions** (all levels): 85
- **Connections**: SharePoint (`shared_sharepointonline`) as the flow service account, Office 365 Outlook (`shared_office365`)
- **How to read this**: actions are listed in run order. Indented items are inside the parent scope / condition branch / loop. `Compose_*`, `Set_*` and `Result_*` actions are the decision points; each SharePoint call shows its exact URI and body. Expressions are the literal text to type into the Expression tab (without the leading `@` when you type into the editor's expression box).
- **Error handling model**: no step relies on a container's Succeeded/Failed status. Risky calls are followed by a step that runs after Succeeded/Failed/Skipped/TimedOut and inspects `actions('<call>')?['status']`. Outcome fields live in variable `vRes`; the Response action runs after everything and its defaults say 'Processing / UNCONFIRMED - do not repeat'.

## Trigger
```json
{
  "Recurrence": {
    "type": "Recurrence",
    "recurrence": {
      "frequency": "Hour",
      "interval": 1
    },
    "metadata": {
      "operationMetadataId": "00000000-0000-0000-0000-000000000000"
    }
  }
}
```

## Actions

- ### `Cfg_SiteUrl`
  - Run after: first action
  **Data Operation > Compose**
  ```json
  "https://CHANGE-ME.sharepoint.com/sites/POU"
  ```
- ### `Guard_site_url_configured`
  - Run after: after `Cfg_SiteUrl` Succeeded
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@contains(outputs('Cfg_SiteUrl'), 'CHANGE-ME')", true]}
  ```
  - Inside `Guard_site_url_configured`:
    - **`Stop_site_url_not_set`**
      - Run after: first action
      **Control > Terminate**
      ```json
      {
        "runStatus": "Failed",
        "runError": {
          "code": "POU_CONFIG",
          "message": "Edit the Cfg_SiteUrl action: it still contains CHANGE-ME."
        }
      }
      ```
- ### `Get_settings`
  - Run after: after `Guard_site_url_configured` Succeeded/Failed/Skipped/TimedOut
  **SharePoint > Send an HTTP request to SharePoint**  `GET`
  - Site Address: `@outputs('Cfg_SiteUrl')`
  - Uri: `@concat('/_api/web/lists/getbytitle(''POUSettings'')/items', '?', '$select=Id,SettingKey,SettingValue', '&', '$top=500')`
  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
- ### `Select_settings`
  - Run after: after `Get_settings` Succeeded
  **Data Operation > Select**
  ```json
  {
    "from": "@body('Get_settings')?['d']?['results']",
    "select": "@concat('\"', item()?['SettingKey'], '\":\"', replace(replace(coalesce(item()?['SettingValue'], ''), '\"', ''), '\\', '/'), '\"')"
  }
  ```
- ### `Compose_Settings`
  - Run after: after `Select_settings` Succeeded
  **Data Operation > Compose**
  ```json
  "@json(concat('{', join(body('Select_settings'), ','), '}'))"
  ```
- ### `Compose_LocalDate`
  - Run after: after `Compose_Settings` Succeeded
  **Data Operation > Compose**
  ```json
  "@convertFromUtc(utcNow(), coalesce(outputs('Compose_Settings')?['DisplayTimeZoneWindows'], 'Central Standard Time'), 'yyyy-MM-dd')"
  ```
- ### `Compose_LocalHour`
  - Run after: after `Compose_LocalDate` Succeeded
  **Data Operation > Compose**
  ```json
  "@int(convertFromUtc(utcNow(), coalesce(outputs('Compose_Settings')?['DisplayTimeZoneWindows'], 'Central Standard Time'), 'HH'))"
  ```
- ### `Compose_LocalDow`
  - Run after: after `Compose_LocalHour` Succeeded
  **Data Operation > Compose**
  ```json
  "@toLower(convertFromUtc(utcNow(), coalesce(outputs('Compose_Settings')?['DisplayTimeZoneWindows'], 'Central Standard Time'), 'dddd'))"
  ```
- ### `Compose_Due`
  - Run after: after `Compose_LocalDow` Succeeded
  **Data Operation > Compose**
  ```json
  "@and(and(greaterOrEquals(outputs('Compose_LocalHour'), int(coalesce(outputs('Compose_Settings')?['WeeklyHourLocal'], '7'))), not(equals(coalesce(outputs('Compose_Settings')?['LastWeeklyHealthDate'], ''), outputs('Compose_LocalDate')))), equals(outputs('Compose_LocalDow'), toLower(coalesce(outputs('Compose_Settings')?['WeeklyDayOfWeek'], 'monday'))))"
  ```
- ### `If_not_due`
  - Run after: after `Compose_Due` Succeeded
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@equals(outputs('Compose_Due'), false)", true]}
  ```
  - Inside `If_not_due`:
    - **`Stop_not_due`**
      - Run after: first action
      **Control > Terminate**
      ```json
      {
        "runStatus": "Succeeded"
      }
      ```
- ### `Init_vItems`
  - Run after: after `If_not_due` Succeeded/Failed/Skipped/TimedOut
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vItems",
        "type": "array",
        "value": []
      }
    ]
  }
  ```
- ### `Init_vItemsNext`
  - Run after: after `Init_vItems` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vItemsNext",
        "type": "string",
        "value": ""
      }
    ]
  }
  ```
- ### `Init_vStock`
  - Run after: after `Init_vItemsNext` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vStock",
        "type": "array",
        "value": []
      }
    ]
  }
  ```
- ### `Init_vStockNext`
  - Run after: after `Init_vStock` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vStockNext",
        "type": "string",
        "value": ""
      }
    ]
  }
  ```
- ### `Init_vFindings`
  - Run after: after `Init_vStockNext` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vFindings",
        "type": "array",
        "value": []
      }
    ]
  }
  ```
- ### `Init_vNameFixed`
  - Run after: after `Init_vFindings` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vNameFixed",
        "type": "integer",
        "value": 0
      }
    ]
  }
  ```
- ### `Items_reset_rows`
  - Run after: after `Init_vNameFixed` Succeeded
  **Variable > Set variable**
  ```json
  {
    "name": "vItems",
    "value": []
  }
  ```
- ### `Items_first_uri`
  - Run after: after `Items_reset_rows` Succeeded
  **Variable > Set variable**
  ```json
  {
    "name": "vItemsNext",
    "value": "@concat('/_api/web/lists/getbytitle(''POUItems'')/items?$top=500&$select=Id,ItemID,ItemName,Active')"
  }
  ```
- ### `Items_until`
  - Run after: after `Items_first_uri` Succeeded
  **Control > Do until**  limit count 100, timeout PT1H
  - Condition: `@empty(variables('vItemsNext'))`
  - Inside `Items_until`:
    - **`Items_page`**
      - Run after: first action
      **SharePoint > Send an HTTP request to SharePoint**  `GET`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@variables('vItemsNext')`
      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
    - **`Items_append`**
      - Run after: after `Items_page` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vItems",
        "value": "@union(variables('vItems'), coalesce(body('Items_page')?['d']?['results'], createArray()))"
      }
      ```
    - **`Items_next`**
      - Run after: after `Items_append` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vItemsNext",
        "value": "@if(empty(coalesce(body('Items_page')?['d']?['__next'], '')), '', substring(body('Items_page')?['d']?['__next'], indexOf(body('Items_page')?['d']?['__next'], '/_api/')))"
      }
      ```
- ### `Stock_reset_rows`
  - Run after: after `Items_until` Succeeded/Failed/Skipped/TimedOut
  **Variable > Set variable**
  ```json
  {
    "name": "vStock",
    "value": []
  }
  ```
- ### `Stock_first_uri`
  - Run after: after `Stock_reset_rows` Succeeded
  **Variable > Set variable**
  ```json
  {
    "name": "vStockNext",
    "value": "@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items?$top=500&$select=Id,StockKey,ItemID,ItemName,OnHandQty,MinQty,MaxQty,BalanceStatus,Active')"
  }
  ```
- ### `Stock_until`
  - Run after: after `Stock_first_uri` Succeeded
  **Control > Do until**  limit count 100, timeout PT1H
  - Condition: `@empty(variables('vStockNext'))`
  - Inside `Stock_until`:
    - **`Stock_page`**
      - Run after: first action
      **SharePoint > Send an HTTP request to SharePoint**  `GET`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@variables('vStockNext')`
      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
    - **`Stock_append`**
      - Run after: after `Stock_page` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vStock",
        "value": "@union(variables('vStock'), coalesce(body('Stock_page')?['d']?['results'], createArray()))"
      }
      ```
    - **`Stock_next`**
      - Run after: after `Stock_append` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vStockNext",
        "value": "@if(empty(coalesce(body('Stock_page')?['d']?['__next'], '')), '', substring(body('Stock_page')?['d']?['__next'], indexOf(body('Stock_page')?['d']?['__next'], '/_api/')))"
      }
      ```
- ### `Get_employees`
  - Run after: after `Stock_until` Succeeded/Failed/Skipped/TimedOut
  **SharePoint > Send an HTTP request to SharePoint**  `GET`
  - Site Address: `@outputs('Cfg_SiteUrl')`
  - Uri: `@concat('/_api/web/lists/getbytitle(''POUEmployees'')/items', '?', '$select=BadgeID,Active,Role,MicrosoftUPN', '&', '$top=500')`
  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
- ### `Get_stations`
  - Run after: after `Get_employees` Succeeded/Failed/Skipped/TimedOut
  **SharePoint > Send an HTTP request to SharePoint**  `GET`
  - Site Address: `@outputs('Cfg_SiteUrl')`
  - Uri: `@concat('/_api/web/lists/getbytitle(''POUStations'')/items', '?', '$select=StationID,Active', '&', '$top=200')`
  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
- ### `Select_item_ids`
  - Run after: after `Get_stations` Succeeded
  **Data Operation > Select**
  ```json
  {
    "from": "@variables('vItems')",
    "select": "@toUpper(item()?['ItemID'])"
  }
  ```
- ### `Select_stock_item_ids`
  - Run after: after `Select_item_ids` Succeeded
  **Data Operation > Select**
  ```json
  {
    "from": "@variables('vStock')",
    "select": "@toUpper(item()?['ItemID'])"
  }
  ```
- ### `Filter_orphan_stock`
  - Run after: after `Select_stock_item_ids` Succeeded
  **Data Operation > Filter array**
  ```json
  {
    "from": "@variables('vStock')",
    "where": "@not(contains(body('Select_item_ids'), toUpper(item()?['ItemID'])))"
  }
  ```
- ### `Select_orphan_keys`
  - Run after: after `Filter_orphan_stock` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Select**
  ```json
  {
    "from": "@body('Filter_orphan_stock')",
    "select": "@item()?['StockKey']"
  }
  ```
- ### `If_orphan_stock`
  - Run after: after `Select_orphan_keys` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(body('Filter_orphan_stock')), 0)", true]}
  ```
  - Inside `If_orphan_stock`:
    - **`Find_orphan_stock`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Critical",
          "area": "Stock record without item master",
          "item": "@join(take(body('Select_orphan_keys'), 20), ', ')",
          "detail": "@concat(string(length(body('Filter_orphan_stock'))), ' stock record(s) have an ItemID missing from POUItems.')"
        }
      }
      ```
- ### `Filter_items_without_stock`
  - Run after: after `If_orphan_stock` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Filter array**
  ```json
  {
    "from": "@variables('vItems')",
    "where": "@and(equals(item()?['Active'], true), not(contains(body('Select_stock_item_ids'), toUpper(item()?['ItemID']))))"
  }
  ```
- ### `Select_items_without_stock`
  - Run after: after `Filter_items_without_stock` Succeeded
  **Data Operation > Select**
  ```json
  {
    "from": "@body('Filter_items_without_stock')",
    "select": "@item()?['ItemID']"
  }
  ```
- ### `If_items_without_stock`
  - Run after: after `Select_items_without_stock` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(body('Filter_items_without_stock')), 0)", true]}
  ```
  - Inside `If_items_without_stock`:
    - **`Find_items_without_stock`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Warning",
          "area": "Active item with no stock location",
          "item": "@join(take(body('Select_items_without_stock'), 20), ', ')",
          "detail": "@concat(string(length(body('Filter_items_without_stock'))), ' active item(s) have no stocking location.')"
        }
      }
      ```
- ### `For_each_stock`
  - Run after: after `If_items_without_stock` Succeeded/Failed/Skipped/TimedOut
  **Control > Apply to each**  concurrency 1
  - Select an output: `@variables('vStock')`
  - Inside `For_each_stock`:
    - **`Filter_item_for_stock`**
      - Run after: first action
      **Data Operation > Filter array**
      ```json
      {
        "from": "@variables('vItems')",
        "where": "@equals(toUpper(item()?['ItemID']), toUpper(items('For_each_stock')?['ItemID']))"
      }
      ```
    - **`Compose_master_name`**
      - Run after: after `Filter_item_for_stock` Succeeded
      **Data Operation > Compose**
      ```json
      "@first(body('Filter_item_for_stock'))?['ItemName']"
      ```
    - **`If_name_differs`**
      - Run after: after `Compose_master_name` Succeeded
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(not(equals(outputs('Compose_master_name'), null)), not(equals(coalesce(items('For_each_stock')?['ItemName'], ''), outputs('Compose_master_name'))))", true]}
      ```
      - Inside `If_name_differs`:
        - **`Fix_name`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items(', items('For_each_stock')?['Id'], ')')`
          - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "@items('For_each_stock')?['__metadata']?['etag']"}`  (+ Accept: application/json;odata=verbose)
          - Body:
          ```json
          {
            "__metadata": {
              "type": "SP.Data.POUStockLocationsListItem"
            },
            "ItemName": "@outputs('Compose_master_name')"
          }
          ```
        - **`If_name_fixed`**
          - Run after: after `Fix_name` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@equals(actions('Fix_name')?['status'], 'Succeeded')", true]}
          ```
          - Inside `If_name_fixed`:
            - **`Count_name_fixed`**
              - Run after: first action
              **Variable > Increment variable**
              ```json
              {
                "name": "vNameFixed",
                "value": 1
              }
              ```
- ### `Filter_onhand_above_max`
  - Run after: after `For_each_stock` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Filter array**
  ```json
  {
    "from": "@variables('vStock')",
    "where": "@and(equals(item()?['Active'], true), not(equals(item()?['OnHandQty'], null)), greater(coalesce(item()?['OnHandQty'], 0), coalesce(item()?['MaxQty'], 0)))"
  }
  ```
- ### `Filter_min_gt_max`
  - Run after: after `Filter_onhand_above_max` Succeeded
  **Data Operation > Filter array**
  ```json
  {
    "from": "@variables('vStock')",
    "where": "@and(equals(item()?['Active'], true), greater(coalesce(item()?['MinQty'], 0), coalesce(item()?['MaxQty'], 0)))"
  }
  ```
- ### `Filter_max_zero`
  - Run after: after `Filter_min_gt_max` Succeeded
  **Data Operation > Filter array**
  ```json
  {
    "from": "@variables('vStock')",
    "where": "@and(equals(item()?['Active'], true), equals(coalesce(item()?['MaxQty'], 0), 0))"
  }
  ```
- ### `Filter_no_balance`
  - Run after: after `Filter_max_zero` Succeeded
  **Data Operation > Filter array**
  ```json
  {
    "from": "@variables('vStock')",
    "where": "@and(equals(item()?['Active'], true), equals(item()?['BalanceStatus'], 'NoBalance'))"
  }
  ```
- ### `Select_onhand_above_max_keys`
  - Run after: after `Filter_no_balance` Succeeded
  **Data Operation > Select**
  ```json
  {
    "from": "@body('Filter_onhand_above_max')",
    "select": "@item()?['StockKey']"
  }
  ```
- ### `If_onhand_above_max`
  - Run after: after `Select_onhand_above_max_keys` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(body('Filter_onhand_above_max')), 0)", true]}
  ```
  - Inside `If_onhand_above_max`:
    - **`Find_onhand_above_max`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Info",
          "area": "On hand above Max",
          "item": "@join(take(body('Select_onhand_above_max_keys'), 15), ', ')",
          "detail": "@concat(string(length(body('Filter_onhand_above_max'))), ' record(s) hold more than Max (not capped; review at next count).')"
        }
      }
      ```
- ### `Select_min_gt_max_keys`
  - Run after: after `If_onhand_above_max` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Select**
  ```json
  {
    "from": "@body('Filter_min_gt_max')",
    "select": "@item()?['StockKey']"
  }
  ```
- ### `If_min_gt_max`
  - Run after: after `Select_min_gt_max_keys` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(body('Filter_min_gt_max')), 0)", true]}
  ```
  - Inside `If_min_gt_max`:
    - **`Find_min_gt_max`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Warning",
          "area": "Min above Max",
          "item": "@join(take(body('Select_min_gt_max_keys'), 15), ', ')",
          "detail": "@concat(string(length(body('Filter_min_gt_max'))), ' record(s) have Min greater than Max.')"
        }
      }
      ```
- ### `Select_max_zero_keys`
  - Run after: after `If_min_gt_max` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Select**
  ```json
  {
    "from": "@body('Filter_max_zero')",
    "select": "@item()?['StockKey']"
  }
  ```
- ### `If_max_zero`
  - Run after: after `Select_max_zero_keys` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(body('Filter_max_zero')), 0)", true]}
  ```
  - Inside `If_max_zero`:
    - **`Find_max_zero`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Warning",
          "area": "Max is zero",
          "item": "@join(take(body('Select_max_zero_keys'), 15), ', ')",
          "detail": "@concat(string(length(body('Filter_max_zero'))), ' record(s) have Max = 0 so suggested order is always 0.')"
        }
      }
      ```
- ### `Select_no_balance_keys`
  - Run after: after `If_max_zero` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Select**
  ```json
  {
    "from": "@body('Filter_no_balance')",
    "select": "@item()?['StockKey']"
  }
  ```
- ### `If_no_balance`
  - Run after: after `Select_no_balance_keys` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(body('Filter_no_balance')), 0)", true]}
  ```
  - Inside `If_no_balance`:
    - **`Find_no_balance`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Warning",
          "area": "No verified balance",
          "item": "@join(take(body('Select_no_balance_keys'), 15), ', ')",
          "detail": "@concat(string(length(body('Filter_no_balance'))), ' record(s) have no counted quantity: they cannot be issued or received until a supervisor counts them.')"
        }
      }
      ```
- ### `Filter_approvers`
  - Run after: after `If_no_balance` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Filter array**
  ```json
  {
    "from": "@body('Get_employees')?['d']?['results']",
    "where": "@and(equals(item()?['Active'], true), not(equals(item()?['Role'], 'Operator')), not(empty(coalesce(item()?['MicrosoftUPN'], ''))))"
  }
  ```
- ### `If_no_approvers`
  - Run after: after `Filter_approvers` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@equals(length(body('Filter_approvers')), 0)", true]}
  ```
  - Inside `If_no_approvers`:
    - **`Find_no_approvers`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Critical",
          "area": "Nobody can approve",
          "item": "(all)",
          "detail": "No Active Supervisor/Admin has a MicrosoftUPN, so audits, new items and adjustments can never be approved."
        }
      }
      ```
- ### `Select_approver_upns`
  - Run after: after `If_no_approvers` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Select**
  ```json
  {
    "from": "@body('Filter_approvers')",
    "select": "@toLower(item()?['MicrosoftUPN'])"
  }
  ```
- ### `If_duplicate_upns`
  - Run after: after `Select_approver_upns` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(body('Select_approver_upns')), length(union(body('Select_approver_upns'), createArray())))", true]}
  ```
  - Inside `If_duplicate_upns`:
    - **`Find_duplicate_upns`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Warning",
          "area": "Duplicate MicrosoftUPN",
          "item": "(employees)",
          "detail": "Two approvers share the same Microsoft account."
        }
      }
      ```
- ### `Filter_active_stations`
  - Run after: after `If_duplicate_upns` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Filter array**
  ```json
  {
    "from": "@body('Get_stations')?['d']?['results']",
    "where": "@equals(item()?['Active'], true)"
  }
  ```
- ### `If_no_stations`
  - Run after: after `Filter_active_stations` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@equals(length(body('Filter_active_stations')), 0)", true]}
  ```
  - Inside `If_no_stations`:
    - **`Find_no_stations`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Critical",
          "area": "No active station",
          "item": "(all)",
          "detail": "No station is Active in POUStations; every login will be refused."
        }
      }
      ```
- ### `Filter_placeholder_settings`
  - Run after: after `If_no_stations` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Filter array**
  ```json
  {
    "from": "@body('Get_settings')?['d']?['results']",
    "where": "@contains(coalesce(item()?['SettingValue'], ''), 'CHANGE-ME')"
  }
  ```
- ### `Select_placeholder_keys`
  - Run after: after `Filter_placeholder_settings` Succeeded
  **Data Operation > Select**
  ```json
  {
    "from": "@body('Filter_placeholder_settings')",
    "select": "@item()?['SettingKey']"
  }
  ```
- ### `If_placeholders`
  - Run after: after `Select_placeholder_keys` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(body('Filter_placeholder_settings')), 0)", true]}
  ```
  - Inside `If_placeholders`:
    - **`Find_placeholders`**
      - Run after: first action
      **Variable > Append to array variable**
      ```json
      {
        "name": "vFindings",
        "value": {
          "severity": "Warning",
          "area": "Settings still placeholders",
          "item": "@join(body('Select_placeholder_keys'), ', ')",
          "detail": "Report recipients are not configured, so reports are not being emailed."
        }
      }
      ```
- ### `Compose_summary`
  - Run after: after `If_placeholders` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Compose**
  ```json
  "@concat(string(length(variables('vStock'))), ' stock records, ', string(length(variables('vItems'))), ' items checked; ', string(variables('vNameFixed')), ' item name(s) repaired; ', string(length(variables('vFindings'))), ' finding(s)')"
  ```
- ### `Table_findings`
  - Run after: after `Compose_summary` Succeeded
  **Data Operation > Create HTML/CSV table**
  ```json
  {
    "from": "@variables('vFindings')",
    "format": "HTML",
    "columns": [
      {
        "header": "Severity",
        "value": "@item()?['severity']"
      },
      {
        "header": "Area",
        "value": "@item()?['area']"
      },
      {
        "header": "Item(s)",
        "value": "@item()?['item']"
      },
      {
        "header": "Detail",
        "value": "@item()?['detail']"
      }
    ]
  }
  ```
- ### `Send_health_email_if_recipients`
  - Run after: after `Table_findings` Succeeded
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@and(not(empty(coalesce(outputs('Compose_Settings')?['ReportRecipientsDataHealth'], ''))), not(contains(coalesce(outputs('Compose_Settings')?['ReportRecipientsDataHealth'], ''), 'CHANGE-ME')))", true]}
  ```
  - Inside `Send_health_email_if_recipients`:
    - **`Send_health_email`**
      - Run after: first action
      **Office 365 Outlook > Send an email (V2)**
      ```json
      {
        "emailMessage/To": "@replace(coalesce(outputs('Compose_Settings')?['ReportRecipientsDataHealth'], ''), ',', ';')",
        "emailMessage/Subject": "@concat('POU weekly data health ', outputs('Compose_LocalDate'), ': ', outputs('Compose_summary'))",
        "emailMessage/Body": "@concat('<html><body style=''font-family:Segoe UI,Arial,sans-serif;font-size:13px''><h3>POU weekly data-health report</h3><p>Counts and findings from the whole item master and stock-location list.</p>', '<h4>Findings</h4>', body('Table_findings'), '<p style=\"color:#555\">Nothing is changed by this report except repairing the denormalised ItemName on stock records.</p></body></html>')",
        "emailMessage/Importance": "Normal"
      }
      ```
    - **`Send_health_email_if_sent`**
      - Run after: after `Send_health_email` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@equals(actions('Send_health_email')?['status'], 'Succeeded')", true]}
      ```
      - Inside `Send_health_email_if_sent`:
        - **`Find_setting_LastWeeklyHealthDate`**
          - Run after: first action
          **Data Operation > Filter array**
          ```json
          {
            "from": "@body('Get_settings')?['d']?['results']",
            "where": "@equals(item()?['SettingKey'], 'LastWeeklyHealthDate')"
          }
          ```
        - **`Save_setting_LastWeeklyHealthDate`**
          - Run after: after `Find_setting_LastWeeklyHealthDate` Succeeded
          **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUSettings'')/items(', first(body('Find_setting_LastWeeklyHealthDate'))?['Id'], ')')`
          - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
          - Body:
          ```json
          {
            "__metadata": {
              "type": "SP.Data.POUSettingsListItem"
            },
            "SettingValue": "@outputs('Compose_LocalDate')"
          }
          ```
