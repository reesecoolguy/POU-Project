# POU-DailyLowStock - POU - Daily low stock report

Hourly tick; sends once per day at the configured local hour. Replenishment SUGGESTIONS only.

- **Flow name** (type it EXACTLY; the app refers to the two app-triggered flows by name): `POU-DailyLowStock`
- **Trigger**: Recurrence 1 h (tick) - Once per local day at LowStockReportHourLocal
- **Actions** (all levels): 54
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
  "@and(greaterOrEquals(outputs('Compose_LocalHour'), int(coalesce(outputs('Compose_Settings')?['LowStockReportHourLocal'], '7'))), not(equals(coalesce(outputs('Compose_Settings')?['LastLowStockReportDate'], ''), outputs('Compose_LocalDate'))))"
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
- ### `Init_vLow`
  - Run after: after `If_not_due` Succeeded/Failed/Skipped/TimedOut
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vLow",
        "type": "array",
        "value": []
      }
    ]
  }
  ```
- ### `Init_vLowNext`
  - Run after: after `Init_vLow` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vLowNext",
        "type": "string",
        "value": ""
      }
    ]
  }
  ```
- ### `Init_vNoBal`
  - Run after: after `Init_vLowNext` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vNoBal",
        "type": "array",
        "value": []
      }
    ]
  }
  ```
- ### `Init_vNoBalNext`
  - Run after: after `Init_vNoBal` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vNoBalNext",
        "type": "string",
        "value": ""
      }
    ]
  }
  ```
- ### `Init_vP1`
  - Run after: after `Init_vNoBalNext` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vP1",
        "type": "array",
        "value": []
      }
    ]
  }
  ```
- ### `Low_reset_rows`
  - Run after: after `Init_vP1` Succeeded
  **Variable > Set variable**
  ```json
  {
    "name": "vLow",
    "value": []
  }
  ```
- ### `Low_first_uri`
  - Run after: after `Low_reset_rows` Succeeded
  **Variable > Set variable**
  ```json
  {
    "name": "vLowNext",
    "value": "@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items?$top=500&$select=StockKey,ItemID,ItemName,LocationCode,OnHandQty,MinQty,MaxQty,BalanceStatus', '&$orderby=LocationCode,ItemID', '&$filter=', 'LowStockFlag eq 1 and Active eq 1')"
  }
  ```
- ### `Low_until`
  - Run after: after `Low_first_uri` Succeeded
  **Control > Do until**  limit count 100, timeout PT1H
  - Condition: `@empty(variables('vLowNext'))`
  - Inside `Low_until`:
    - **`Low_page`**
      - Run after: first action
      **SharePoint > Send an HTTP request to SharePoint**  `GET`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@variables('vLowNext')`
      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
    - **`Low_append`**
      - Run after: after `Low_page` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vLow",
        "value": "@union(variables('vLow'), coalesce(body('Low_page')?['d']?['results'], createArray()))"
      }
      ```
    - **`Low_next`**
      - Run after: after `Low_append` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vLowNext",
        "value": "@if(empty(coalesce(body('Low_page')?['d']?['__next'], '')), '', substring(body('Low_page')?['d']?['__next'], indexOf(body('Low_page')?['d']?['__next'], '/_api/')))"
      }
      ```
- ### `NoBal_reset_rows`
  - Run after: after `Low_until` Succeeded/Failed/Skipped/TimedOut
  **Variable > Set variable**
  ```json
  {
    "name": "vNoBal",
    "value": []
  }
  ```
- ### `NoBal_first_uri`
  - Run after: after `NoBal_reset_rows` Succeeded
  **Variable > Set variable**
  ```json
  {
    "name": "vNoBalNext",
    "value": "@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items?$top=500&$select=StockKey,ItemID,ItemName,LocationCode,OnHandQty,MinQty,MaxQty,BalanceStatus', '&$orderby=LocationCode,ItemID', '&$filter=', 'BalanceStatus eq ''NoBalance'' and Active eq 1')"
  }
  ```
- ### `NoBal_until`
  - Run after: after `NoBal_first_uri` Succeeded
  **Control > Do until**  limit count 100, timeout PT1H
  - Condition: `@empty(variables('vNoBalNext'))`
  - Inside `NoBal_until`:
    - **`NoBal_page`**
      - Run after: first action
      **SharePoint > Send an HTTP request to SharePoint**  `GET`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@variables('vNoBalNext')`
      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
    - **`NoBal_append`**
      - Run after: after `NoBal_page` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vNoBal",
        "value": "@union(variables('vNoBal'), coalesce(body('NoBal_page')?['d']?['results'], createArray()))"
      }
      ```
    - **`NoBal_next`**
      - Run after: after `NoBal_append` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vNoBalNext",
        "value": "@if(empty(coalesce(body('NoBal_page')?['d']?['__next'], '')), '', substring(body('NoBal_page')?['d']?['__next'], indexOf(body('NoBal_page')?['d']?['__next'], '/_api/')))"
      }
      ```
- ### `Select_low_rows`
  - Run after: after `NoBal_until` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Select**
  ```json
  {
    "from": "@variables('vLow')",
    "select": {
      "Item": "@item()?['ItemID']",
      "Name": "@item()?['ItemName']",
      "Location": "@item()?['LocationCode']",
      "OnHand": "@item()?['OnHandQty']",
      "Min": "@item()?['MinQty']",
      "Max": "@item()?['MaxQty']",
      "SuggestedOrder": "@if(less(sub(coalesce(item()?['MaxQty'], 0), coalesce(item()?['OnHandQty'], 0)), 0), 0, sub(coalesce(item()?['MaxQty'], 0), coalesce(item()?['OnHandQty'], 0)))",
      "Status": "@if(equals(coalesce(item()?['OnHandQty'], 0), 0), 'CRITICAL', 'LOW')"
    }
  }
  ```
- ### `Filter_critical`
  - Run after: after `Select_low_rows` Succeeded
  **Data Operation > Filter array**
  ```json
  {
    "from": "@body('Select_low_rows')",
    "where": "@equals(item()?['Status'], 'CRITICAL')"
  }
  ```
- ### `Filter_low`
  - Run after: after `Filter_critical` Succeeded
  **Data Operation > Filter array**
  ```json
  {
    "from": "@body('Select_low_rows')",
    "where": "@equals(item()?['Status'], 'LOW')"
  }
  ```
- ### `Compose_ordered_rows`
  - Run after: after `Filter_low` Succeeded
  **Data Operation > Compose**
  ```json
  "@union(body('Filter_critical'), body('Filter_low'))"
  ```
- ### `Table_low`
  - Run after: after `Compose_ordered_rows` Succeeded
  **Data Operation > Create HTML/CSV table**
  ```json
  {
    "from": "@outputs('Compose_ordered_rows')",
    "format": "HTML",
    "columns": [
      {
        "header": "Status",
        "value": "@item()?['Status']"
      },
      {
        "header": "Item",
        "value": "@item()?['Item']"
      },
      {
        "header": "Name",
        "value": "@item()?['Name']"
      },
      {
        "header": "Location",
        "value": "@item()?['Location']"
      },
      {
        "header": "On hand",
        "value": "@item()?['OnHand']"
      },
      {
        "header": "Min",
        "value": "@item()?['Min']"
      },
      {
        "header": "Max",
        "value": "@item()?['Max']"
      },
      {
        "header": "Suggested order qty (Max - On hand)",
        "value": "@item()?['SuggestedOrder']"
      }
    ]
  }
  ```
- ### `Select_nobal_rows`
  - Run after: after `Table_low` Succeeded
  **Data Operation > Select**
  ```json
  {
    "from": "@variables('vNoBal')",
    "select": {
      "Item": "@item()?['ItemID']",
      "Name": "@item()?['ItemName']",
      "Location": "@item()?['LocationCode']"
    }
  }
  ```
- ### `Table_nobal`
  - Run after: after `Select_nobal_rows` Succeeded
  **Data Operation > Create HTML/CSV table**
  ```json
  {
    "from": "@body('Select_nobal_rows')",
    "format": "HTML",
    "columns": [
      {
        "header": "Item",
        "value": "@item()?['Item']"
      },
      {
        "header": "Name",
        "value": "@item()?['Name']"
      },
      {
        "header": "Location",
        "value": "@item()?['Location']"
      }
    ]
  }
  ```
- ### `Get_priority1_items`
  - Run after: after `Table_nobal` Succeeded
  **SharePoint > Send an HTTP request to SharePoint**  `GET`
  - Site Address: `@outputs('Cfg_SiteUrl')`
  - Uri: `@concat('/_api/web/lists/getbytitle(''POUItems'')/items', '?', '$filter=', 'Priority eq 1 and Active eq 1', '&', '$select=ItemID,ItemName', '&', '$top=200')`
  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
- ### `For_each_p1_item`
  - Run after: after `Get_priority1_items` Succeeded
  **Control > Apply to each**  concurrency 1
  - Select an output: `@body('Get_priority1_items')?['d']?['results']`
  - Inside `For_each_p1_item`:
    - **`Get_p1_stock`**
      - Run after: first action
      **SharePoint > Send an HTTP request to SharePoint**  `GET`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items', '?', '$filter=', 'ItemID eq ''', uriComponent(replace(string(items('For_each_p1_item')?['ItemID']), '''', '''''')), ''' and Active eq 1', '&', '$select=StockKey,ItemID,ItemName,LocationCode,OnHandQty,MinQty,MaxQty,BalanceStatus', '&', '$top=50')`
      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
    - **`Append_p1_rows`**
      - Run after: after `Get_p1_stock` Succeeded
      **Variable > Set variable**
      ```json
      {
        "name": "vP1",
        "value": "@union(variables('vP1'), coalesce(body('Get_p1_stock')?['d']?['results'], createArray()))"
      }
      ```
- ### `Table_p1`
  - Run after: after `For_each_p1_item` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Create HTML/CSV table**
  ```json
  {
    "from": "@variables('vP1')",
    "format": "HTML",
    "columns": [
      {
        "header": "Item",
        "value": "@item()?['ItemID']"
      },
      {
        "header": "Name",
        "value": "@item()?['ItemName']"
      },
      {
        "header": "Location",
        "value": "@item()?['LocationCode']"
      },
      {
        "header": "On hand",
        "value": "@item()?['OnHandQty']"
      },
      {
        "header": "Min",
        "value": "@item()?['MinQty']"
      },
      {
        "header": "Max",
        "value": "@item()?['MaxQty']"
      }
    ]
  }
  ```
- ### `Compose_counts`
  - Run after: after `Table_p1` Succeeded
  **Data Operation > Compose**
  ```json
  "@concat(string(length(variables('vLow'))), ' at or below minimum (', string(length(body('Filter_critical'))), ' CRITICAL = zero on hand); ', string(length(variables('vNoBal'))), ' need a first count')"
  ```
- ### `Compose_body`
  - Run after: after `Compose_counts` Succeeded
  **Data Operation > Compose**
  ```json
  "@concat('<html><body style=''font-family:Segoe UI,Arial,sans-serif;font-size:13px''><h3>POU low stock - daily</h3><p>Rule: LowStockRule setting (LE = on hand <= min, LT = on hand < min). <b>Suggested order quantity is a suggestion only (Max - On hand). It does NOT consider open purchase orders: this system holds no order data.</b></p>', '<h4>Low stock</h4>', body('Table_low'), '<h4>Needs a first count (no verified balance - not counted as low stock)</h4>', body('Table_nobal'), '<h4>Priority 1 items - on hand</h4>', body('Table_p1'), '<p style=\"color:#555\">Generated by POU-DailyLowStock. Counts: see subject. Change recipients/time in the POUSettings list.</p></body></html>')"
  ```
- ### `Send_low_stock_email_if_recipients`
  - Run after: after `Compose_body` Succeeded
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@and(not(empty(coalesce(outputs('Compose_Settings')?['ReportRecipientsLowStock'], ''))), not(contains(coalesce(outputs('Compose_Settings')?['ReportRecipientsLowStock'], ''), 'CHANGE-ME')))", true]}
  ```
  - Inside `Send_low_stock_email_if_recipients`:
    - **`Send_low_stock_email`**
      - Run after: first action
      **Office 365 Outlook > Send an email (V2)**
      ```json
      {
        "emailMessage/To": "@replace(coalesce(outputs('Compose_Settings')?['ReportRecipientsLowStock'], ''), ',', ';')",
        "emailMessage/Subject": "@concat('POU low stock ', outputs('Compose_LocalDate'), ': ', outputs('Compose_counts'))",
        "emailMessage/Body": "@outputs('Compose_body')",
        "emailMessage/Importance": "Normal"
      }
      ```
    - **`Send_low_stock_email_if_sent`**
      - Run after: after `Send_low_stock_email` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@equals(actions('Send_low_stock_email')?['status'], 'Succeeded')", true]}
      ```
      - Inside `Send_low_stock_email_if_sent`:
        - **`Find_setting_LastLowStockReportDate`**
          - Run after: first action
          **Data Operation > Filter array**
          ```json
          {
            "from": "@body('Get_settings')?['d']?['results']",
            "where": "@equals(item()?['SettingKey'], 'LastLowStockReportDate')"
          }
          ```
        - **`Save_setting_LastLowStockReportDate`**
          - Run after: after `Find_setting_LastLowStockReportDate` Succeeded
          **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUSettings'')/items(', first(body('Find_setting_LastLowStockReportDate'))?['Id'], ')')`
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
  - If NO (else) in `Send_low_stock_email_if_recipients`:
    - **`NoRcpt_Ops_event`**
      - Run after: first action
      **Control > Scope**
      - Inside `NoRcpt_Ops_event`:
        - **`NoRcpt_Get_event`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items', '?', '$filter=', 'EventKey eq ''', uriComponent(replace(string('REPORT_RECIPIENTS_LOWSTOCK'), '''', '''''')), '''', '&', '$select=Id,OccurrenceCount', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`NoRcpt_Event_row`**
          - Run after: after `NoRcpt_Get_event` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('NoRcpt_Get_event')?['d']?['results'])"
          ```
        - **`NoRcpt_Event_exists`**
          - Run after: after `NoRcpt_Event_row` Succeeded
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@not(equals(outputs('NoRcpt_Event_row'), null))", true]}
          ```
          - Inside `NoRcpt_Event_exists`:
            - **`NoRcpt_Update_event`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items(', outputs('NoRcpt_Event_row')?['Id'], ')')`
              - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
              - Body:
              ```json
              {
                "__metadata": {
                  "type": "SP.Data.POUOpsEventsListItem"
                },
                "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                "OccurrenceCount": "@add(int(coalesce(outputs('NoRcpt_Event_row')?['OccurrenceCount'], 1)), 1)",
                "Details": "Setting ReportRecipientsLowStock is empty or still CHANGE-ME@... so the daily report was not emailed.",
                "Resolved": false
              }
              ```
          - If NO (else) in `NoRcpt_Event_exists`:
            - **`NoRcpt_Create_event`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `POST`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `/_api/web/lists/getbytitle('POUOpsEvents')/items`
              - Headers: `{"Content-Type": "application/json;odata=verbose"}`  (+ Accept: application/json;odata=verbose)
              - Body:
              ```json
              {
                "__metadata": {
                  "type": "SP.Data.POUOpsEventsListItem"
                },
                "Title": "Low-stock report recipients not configured",
                "EventKey": "REPORT_RECIPIENTS_LOWSTOCK",
                "EventType": "CONFIG",
                "Severity": "Warning",
                "Subject": "Low-stock report recipients not configured",
                "Details": "Setting ReportRecipientsLowStock is empty or still CHANGE-ME@... so the daily report was not emailed.",
                "FirstSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                "OccurrenceCount": 1,
                "Resolved": false
              }
              ```
