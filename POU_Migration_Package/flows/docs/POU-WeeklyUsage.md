# POU-WeeklyUsage - POU - Weekly usage by item/location (30 and 90 days)

Hourly tick; once per week. For every active stock record: units ISSUED in the last 30 and 90 days, from the ledger.

- **Flow name** (type it EXACTLY; the app refers to the two app-triggered flows by name): `POU-WeeklyUsage`
- **Trigger**: Recurrence 1 h (tick) - Weekly on WeeklyDayOfWeek / WeeklyHourLocal
- **Actions** (all levels): 44
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
  "@and(and(greaterOrEquals(outputs('Compose_LocalHour'), int(coalesce(outputs('Compose_Settings')?['WeeklyHourLocal'], '7'))), not(equals(coalesce(outputs('Compose_Settings')?['LastWeeklyUsageDate'], ''), outputs('Compose_LocalDate')))), equals(outputs('Compose_LocalDow'), toLower(coalesce(outputs('Compose_Settings')?['WeeklyDayOfWeek'], 'monday'))))"
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
- ### `Init_vStock`
  - Run after: after `If_not_due` Succeeded/Failed/Skipped/TimedOut
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
- ### `Init_vUsage`
  - Run after: after `Init_vStockNext` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vUsage",
        "type": "array",
        "value": []
      }
    ]
  }
  ```
- ### `Stock_reset_rows`
  - Run after: after `Init_vUsage` Succeeded
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
    "value": "@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items?$top=500&$select=StockKey,ItemID,ItemName,LocationCode,OnHandQty,MinQty,MaxQty,Active')"
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
- ### `Filter_active_stock`
  - Run after: after `Stock_until` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Filter array**
  ```json
  {
    "from": "@variables('vStock')",
    "where": "@equals(item()?['Active'], true)"
  }
  ```
- ### `Compose_d30`
  - Run after: after `Filter_active_stock` Succeeded
  **Data Operation > Compose**
  ```json
  "@addDays(utcNow(), -30, 'yyyy-MM-ddTHH:mm:ssZ')"
  ```
- ### `Compose_d90`
  - Run after: after `Compose_d30` Succeeded
  **Data Operation > Compose**
  ```json
  "@addDays(utcNow(), -90, 'yyyy-MM-ddTHH:mm:ssZ')"
  ```
- ### `For_each_usage_stock`
  - Run after: after `Compose_d90` Succeeded
  **Control > Apply to each**  concurrency 1
  - Select an output: `@body('Filter_active_stock')`
  - Inside `For_each_usage_stock`:
    - **`Get_issues90`**
      - Run after: first action
      **SharePoint > Send an HTTP request to SharePoint**  `GET`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items', '?', '$filter=', 'StockKey eq ''', uriComponent(replace(string(items('For_each_usage_stock')?['StockKey']), '''', '''''')), ''' and LedgerType eq ''ISSUE'' and PostingState eq ''Posted'' and OccurredUtc ge datetime''', outputs('Compose_d90'), '''', '&', '$select=QtyDelta,OccurredUtc,Origin', '&', '$top=500')`
      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
    - **`Compose_rows90`**
      - Run after: after `Get_issues90` Succeeded
      **Data Operation > Compose**
      ```json
      "@body('Get_issues90')?['d']?['results']"
      ```
    - **`Filter_rows90`**
      - Run after: after `Compose_rows90` Succeeded
      **Data Operation > Filter array**
      ```json
      {
        "from": "@outputs('Compose_rows90')",
        "where": "@or(equals(toLower(coalesce(outputs('Compose_Settings')?['UsageIncludeLegacy'], 'true')), 'true'), equals(item()?['Origin'], 'Live'))"
      }
      ```
    - **`Filter_rows30`**
      - Run after: after `Filter_rows90` Succeeded
      **Data Operation > Filter array**
      ```json
      {
        "from": "@body('Filter_rows90')",
        "where": "@greaterOrEquals(item()?['OccurredUtc'], outputs('Compose_d30'))"
      }
      ```
    - **`Select_q90`**
      - Run after: after `Filter_rows30` Succeeded
      **Data Operation > Select**
      ```json
      {
        "from": "@body('Filter_rows90')",
        "select": "@sub(0, int(coalesce(item()?['QtyDelta'], 0)))"
      }
      ```
    - **`Select_q30`**
      - Run after: after `Select_q90` Succeeded
      **Data Operation > Select**
      ```json
      {
        "from": "@body('Filter_rows30')",
        "select": "@sub(0, int(coalesce(item()?['QtyDelta'], 0)))"
      }
      ```
    - **`Compose_sum90`**
      - Run after: after `Select_q30` Succeeded
      **Data Operation > Compose**
      ```json
      "@xpath(xml(json(concat('{\"r\":{\"q\":', string(body('Select_q90')), '}}'))), 'sum(//q)')"
      ```
    - **`Compose_sum30`**
      - Run after: after `Compose_sum90` Succeeded
      **Data Operation > Compose**
      ```json
      "@xpath(xml(json(concat('{\"r\":{\"q\":', string(body('Select_q30')), '}}'))), 'sum(//q)')"
      ```
    - **`Compose_usage_row`**
      - Run after: after `Compose_sum30` Succeeded
      **Data Operation > Compose**
      ```json
      {
        "stockKey": "@items('For_each_usage_stock')?['StockKey']",
        "item": "@items('For_each_usage_stock')?['ItemID']",
        "name": "@coalesce(items('For_each_usage_stock')?['ItemName'], '')",
        "location": "@items('For_each_usage_stock')?['LocationCode']",
        "onHand": "@items('For_each_usage_stock')?['OnHandQty']",
        "issued30": "@outputs('Compose_sum30')",
        "issued90": "@outputs('Compose_sum90')",
        "tx90": "@length(body('Filter_rows90'))"
      }
      ```
    - **`Append_usage_row`**
      - Run after: after `Compose_usage_row` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vUsage",
        "value": "@union(variables('vUsage'), createArray(outputs('Compose_usage_row')))"
      }
      ```
- ### `Filter_used`
  - Run after: after `For_each_usage_stock` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Filter array**
  ```json
  {
    "from": "@variables('vUsage')",
    "where": "@greater(item()?['issued90'], 0)"
  }
  ```
- ### `Table_usage_html`
  - Run after: after `Filter_used` Succeeded
  **Data Operation > Create HTML/CSV table**
  ```json
  {
    "from": "@body('Filter_used')",
    "format": "HTML",
    "columns": [
      {
        "header": "Item",
        "value": "@item()?['item']"
      },
      {
        "header": "Name",
        "value": "@item()?['name']"
      },
      {
        "header": "Location",
        "value": "@item()?['location']"
      },
      {
        "header": "On hand",
        "value": "@item()?['onHand']"
      },
      {
        "header": "Issued 30 days",
        "value": "@item()?['issued30']"
      },
      {
        "header": "Issued 90 days",
        "value": "@item()?['issued90']"
      },
      {
        "header": "Issue transactions (90d)",
        "value": "@item()?['tx90']"
      }
    ]
  }
  ```
- ### `Table_usage_csv`
  - Run after: after `Table_usage_html` Succeeded
  **Data Operation > Create HTML/CSV table**
  ```json
  {
    "from": "@variables('vUsage')",
    "format": "CSV",
    "columns": [
      {
        "header": "StockKey",
        "value": "@item()?['stockKey']"
      },
      {
        "header": "Item",
        "value": "@item()?['item']"
      },
      {
        "header": "Name",
        "value": "@item()?['name']"
      },
      {
        "header": "Location",
        "value": "@item()?['location']"
      },
      {
        "header": "OnHand",
        "value": "@item()?['onHand']"
      },
      {
        "header": "Issued30d",
        "value": "@item()?['issued30']"
      },
      {
        "header": "Issued90d",
        "value": "@item()?['issued90']"
      },
      {
        "header": "IssueTx90d",
        "value": "@item()?['tx90']"
      }
    ]
  }
  ```
- ### `Compose_usage_summary`
  - Run after: after `Table_usage_csv` Succeeded
  **Data Operation > Compose**
  ```json
  "@concat(string(length(variables('vUsage'))), ' stock records; ', string(length(body('Filter_used'))), ' with issues in the last 90 days')"
  ```
- ### `Send_usage_email_if_recipients`
  - Run after: after `Compose_usage_summary` Succeeded
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@and(not(empty(coalesce(outputs('Compose_Settings')?['ReportRecipientsUsage'], ''))), not(contains(coalesce(outputs('Compose_Settings')?['ReportRecipientsUsage'], ''), 'CHANGE-ME')))", true]}
  ```
  - Inside `Send_usage_email_if_recipients`:
    - **`Send_usage_email`**
      - Run after: first action
      **Office 365 Outlook > Send an email (V2)**
      ```json
      {
        "emailMessage/To": "@replace(coalesce(outputs('Compose_Settings')?['ReportRecipientsUsage'], ''), ',', ';')",
        "emailMessage/Subject": "@concat('POU usage 30/90 days ', outputs('Compose_LocalDate'), ': ', outputs('Compose_usage_summary'))",
        "emailMessage/Body": "@concat('<html><body style=''font-family:Segoe UI,Arial,sans-serif;font-size:13px''><h3>POU usage by item/location</h3><p>Units ISSUED (removed) per stock record. Source: ledger rows with LedgerType=ISSUE and PostingState=Posted. UsageIncludeLegacy controls whether pre-cutover workbook history is included. The attached CSV has every stock record; sort it by Issued90d.</p>', '<h4>Items issued in the last 90 days (list is ordered by item, then location)</h4>', body('Table_usage_html'), '<p style=\"color:#555\">Usage is demand history, not a purchase recommendation: it does not consider lead times or open orders.</p></body></html>')",
        "emailMessage/Importance": "Normal",
        "emailMessage/Attachments": [
          {
            "Name": "POU_usage_30_90.csv",
            "ContentBytes": "@base64(body('Table_usage_csv'))"
          }
        ]
      }
      ```
    - **`Send_usage_email_if_sent`**
      - Run after: after `Send_usage_email` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@equals(actions('Send_usage_email')?['status'], 'Succeeded')", true]}
      ```
      - Inside `Send_usage_email_if_sent`:
        - **`Find_setting_LastWeeklyUsageDate`**
          - Run after: first action
          **Data Operation > Filter array**
          ```json
          {
            "from": "@body('Get_settings')?['d']?['results']",
            "where": "@equals(item()?['SettingKey'], 'LastWeeklyUsageDate')"
          }
          ```
        - **`Save_setting_LastWeeklyUsageDate`**
          - Run after: after `Find_setting_LastWeeklyUsageDate` Succeeded
          **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUSettings'')/items(', first(body('Find_setting_LastWeeklyUsageDate'))?['Id'], ')')`
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
