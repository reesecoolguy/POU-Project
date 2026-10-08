# POU-Reconcile - POU - Nightly balance-to-ledger reconciliation

Hourly tick; once per night: proves OnHandQty == the ledger row for StockVersion, repairs LowStockFlag, raises ops events, purges old requests/sessions.

- **Trigger**: Recurrence 1 h (tick) - Once per night at ReconcileHourLocal
- **Actions** (all levels): 57
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
  "@and(greaterOrEquals(outputs('Compose_LocalHour'), int(coalesce(outputs('Compose_Settings')?['ReconcileHourLocal'], '7'))), not(equals(coalesce(outputs('Compose_Settings')?['LastReconcileDate'], ''), outputs('Compose_LocalDate'))))"
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
- ### `Init_vFixed`
  - Run after: after `Init_vFindings` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vFixed",
        "type": "integer",
        "value": 0
      }
    ]
  }
  ```
- ### `Init_vChecked`
  - Run after: after `Init_vFixed` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vChecked",
        "type": "integer",
        "value": 0
      }
    ]
  }
  ```
- ### `Stock_reset_rows`
  - Run after: after `Init_vChecked` Succeeded
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
    "value": "@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items?$top=500&$select=Id,StockKey,ItemID,OnHandQty,StockVersion,MinQty,LowStockFlag,BalanceStatus,Active')"
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
- ### `Filter_rows_to_check`
  - Run after: after `Stock_until` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Filter array**
  ```json
  {
    "from": "@variables('vStock')",
    "where": "@and(equals(item()?['Active'], true), not(and(equals(coalesce(item()?['StockVersion'], 0), 0), equals(item()?['OnHandQty'], null), equals(coalesce(item()?['LowStockFlag'], false), false))))"
  }
  ```
- ### `For_each_stock`
  - Run after: after `Filter_rows_to_check` Succeeded
  **Control > Apply to each**  concurrency 1
  - Select an output: `@body('Filter_rows_to_check')`
  - Inside `For_each_stock`:
    - **`Count_checked`**
      - Run after: first action
      **Variable > Increment variable**
      ```json
      {
        "name": "vChecked",
        "value": 1
      }
      ```
    - **`Get_ledger_pair`**
      - Run after: after `Count_checked` Succeeded
      **SharePoint > Send an HTTP request to SharePoint**  `GET`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items', '?', '$filter=', 'LedgerKey eq ''', uriComponent(replace(string(concat(items('For_each_stock')?['StockKey'], '#', string(int(coalesce(items('For_each_stock')?['StockVersion'], 0))))), '''', '''''')), ''' or LedgerKey eq ''', uriComponent(replace(string(concat(items('For_each_stock')?['StockKey'], '#', string(add(int(coalesce(items('For_each_stock')?['StockVersion'], 0)), 1)))), '''', '''''')), '''', '&', '$select=LedgerKey,SeqNo,PostingState,QtyAfter,Created', '&', '$top=5')`
      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
    - **`Pick_current`**
      - Run after: after `Get_ledger_pair` Succeeded
      **Data Operation > Filter array**
      ```json
      {
        "from": "@body('Get_ledger_pair')?['d']?['results']",
        "where": "@equals(item()?['SeqNo'], int(coalesce(items('For_each_stock')?['StockVersion'], 0)))"
      }
      ```
    - **`Pick_next`**
      - Run after: after `Pick_current` Succeeded
      **Data Operation > Filter array**
      ```json
      {
        "from": "@body('Get_ledger_pair')?['d']?['results']",
        "where": "@equals(item()?['SeqNo'], add(int(coalesce(items('For_each_stock')?['StockVersion'], 0)), 1))"
      }
      ```
    - **`Compose_problem`**
      - Run after: after `Pick_next` Succeeded
      **Data Operation > Compose**
      ```json
      "@if(and(equals(int(coalesce(items('For_each_stock')?['StockVersion'], 0)), 0), not(equals(items('For_each_stock')?['OnHandQty'], null))), 'BALANCE_WITHOUT_LEDGER', if(and(greater(int(coalesce(items('For_each_stock')?['StockVersion'], 0)), 0), equals(first(body('Pick_current')), null)), 'LEDGER_ROW_MISSING', if(and(greater(int(coalesce(items('For_each_stock')?['StockVersion'], 0)), 0), not(equals(first(body('Pick_current')), null)), not(equals(first(body('Pick_current'))?['QtyAfter'], items('For_each_stock')?['OnHandQty']))), 'BALANCE_MISMATCH', if(and(not(equals(first(body('Pick_next')), null)), equals(first(body('Pick_next'))?['PostingState'], 'Posted')), 'STOCK_BEHIND_LEDGER', if(and(not(equals(first(body('Pick_next')), null)), greater(sub(ticks(utcNow()), ticks(coalesce(first(body('Pick_next'))?['Created'], utcNow()))), mul(int(coalesce(outputs('Compose_Settings')?['StaleIntentMinutes'], '5')), 12000000000))), 'STALE_INTENT', '')))))"
      ```
    - **`If_problem`**
      - Run after: after `Compose_problem` Succeeded
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@not(empty(outputs('Compose_problem')))", true]}
      ```
      - Inside `If_problem`:
        - **`Rec_Ops_event`**
          - Run after: first action
          **Control > Scope**
          - Inside `Rec_Ops_event`:
            - **`Rec_Get_event`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items', '?', '$filter=', 'EventKey eq ''', uriComponent(replace(string(concat('RECON|', outputs('Compose_problem'), '|', items('For_each_stock')?['StockKey'])), '''', '''''')), '''', '&', '$select=Id,OccurrenceCount', '&', '$top=2')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`Rec_Event_row`**
              - Run after: after `Rec_Get_event` Succeeded
              **Data Operation > Compose**
              ```json
              "@first(body('Rec_Get_event')?['d']?['results'])"
              ```
            - **`Rec_Event_exists`**
              - Run after: after `Rec_Event_row` Succeeded
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@not(equals(outputs('Rec_Event_row'), null))", true]}
              ```
              - Inside `Rec_Event_exists`:
                - **`Rec_Update_event`**
                  - Run after: first action
                  **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items(', outputs('Rec_Event_row')?['Id'], ')')`
                  - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
                  - Body:
                  ```json
                  {
                    "__metadata": {
                      "type": "SP.Data.POUOpsEventsListItem"
                    },
                    "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "OccurrenceCount": "@add(int(coalesce(outputs('Rec_Event_row')?['OccurrenceCount'], 1)), 1)",
                    "Details": "@concat('On hand ', string(items('For_each_stock')?['OnHandQty']), ', stock version ', string(int(coalesce(items('For_each_stock')?['StockVersion'], 0))), '. Ledger row at that version: ', string(coalesce(first(body('Pick_current'))?['QtyAfter'], 'none')), '. Posting for this record is blocked until resolved (see docs/10_Maintenance.md).')",
                    "Resolved": false
                  }
                  ```
              - If NO (else) in `Rec_Event_exists`:
                - **`Rec_Create_event`**
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
                    "Title": "@concat(outputs('Compose_problem'), ': ', items('For_each_stock')?['StockKey'])",
                    "EventKey": "@concat('RECON|', outputs('Compose_problem'), '|', items('For_each_stock')?['StockKey'])",
                    "EventType": "RECONCILE",
                    "Severity": "Critical",
                    "Subject": "@concat(outputs('Compose_problem'), ': ', items('For_each_stock')?['StockKey'])",
                    "Details": "@concat('On hand ', string(items('For_each_stock')?['OnHandQty']), ', stock version ', string(int(coalesce(items('For_each_stock')?['StockVersion'], 0))), '. Ledger row at that version: ', string(coalesce(first(body('Pick_current'))?['QtyAfter'], 'none')), '. Posting for this record is blocked until resolved (see docs/10_Maintenance.md).')",
                    "FirstSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "OccurrenceCount": 1,
                    "Resolved": false
                  }
                  ```
        - **`Add_finding`**
          - Run after: after `Rec_Ops_event` Succeeded/Failed/Skipped/TimedOut
          **Variable > Append to array variable**
          ```json
          {
            "name": "vFindings",
            "value": {
              "severity": "Critical",
              "area": "Balance vs ledger",
              "item": "@items('For_each_stock')?['StockKey']",
              "detail": "@outputs('Compose_problem')"
            }
          }
          ```
    - **`Compose_expected_flag`**
      - Run after: after `If_problem` Succeeded/Failed/Skipped/TimedOut
      **Data Operation > Compose**
      ```json
      "@and(not(equals(items('For_each_stock')?['OnHandQty'], null)), not(equals(items('For_each_stock')?['MinQty'], null)), if(equals(outputs('Compose_Settings')?['LowStockRule'], 'LT'), less(coalesce(items('For_each_stock')?['OnHandQty'], 0), coalesce(items('For_each_stock')?['MinQty'], 0)), lessOrEquals(coalesce(items('For_each_stock')?['OnHandQty'], 0), coalesce(items('For_each_stock')?['MinQty'], 0))))"
      ```
    - **`If_flag_wrong`**
      - Run after: after `Compose_expected_flag` Succeeded
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@not(equals(coalesce(items('For_each_stock')?['LowStockFlag'], false), outputs('Compose_expected_flag')))", true]}
      ```
      - Inside `If_flag_wrong`:
        - **`Fix_flag`**
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
            "LowStockFlag": "@outputs('Compose_expected_flag')"
          }
          ```
        - **`If_flag_fixed`**
          - Run after: after `Fix_flag` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@equals(actions('Fix_flag')?['status'], 'Succeeded')", true]}
          ```
          - Inside `If_flag_fixed`:
            - **`Count_fixed`**
              - Run after: first action
              **Variable > Increment variable**
              ```json
              {
                "name": "vFixed",
                "value": 1
              }
              ```
- ### `Compose_req_cutoff`
  - Run after: after `For_each_stock` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Compose**
  ```json
  "@addDays(utcNow(), mul(-1, int(coalesce(outputs('Compose_Settings')?['RequestRetentionDays'], '90'))), 'yyyy-MM-ddTHH:mm:ssZ')"
  ```
- ### `Compose_sess_cutoff`
  - Run after: after `Compose_req_cutoff` Succeeded
  **Data Operation > Compose**
  ```json
  "@addDays(utcNow(), mul(-1, int(coalesce(outputs('Compose_Settings')?['SessionRetentionDays'], '30'))), 'yyyy-MM-ddTHH:mm:ssZ')"
  ```
- ### `Get_old_requests`
  - Run after: after `Compose_sess_cutoff` Succeeded
  **SharePoint > Send an HTTP request to SharePoint**  `GET`
  - Site Address: `@outputs('Cfg_SiteUrl')`
  - Uri: `@concat('/_api/web/lists/getbytitle(''POURequests'')/items', '?', '$filter=', 'Created lt datetime''', outputs('Compose_req_cutoff'), ''' and IsOpen eq 0', '&', '$select=Id', '&', '$top=300')`
  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
- ### `For_each_old_request`
  - Run after: after `Get_old_requests` Succeeded
  **Control > Apply to each**  concurrency 1
  - Select an output: `@body('Get_old_requests')?['d']?['results']`
  - Inside `For_each_old_request`:
    - **`Purge_request`**
      - Run after: first action
      **SharePoint > Send an HTTP request to SharePoint**  `DELETE`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@concat('/_api/web/lists/getbytitle(''POURequests'')/items(', items('For_each_old_request')?['Id'], ')')`
      - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "DELETE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
- ### `Get_old_sessions`
  - Run after: after `For_each_old_request` Succeeded/Failed/Skipped/TimedOut
  **SharePoint > Send an HTTP request to SharePoint**  `GET`
  - Site Address: `@outputs('Cfg_SiteUrl')`
  - Uri: `@concat('/_api/web/lists/getbytitle(''POUSessions'')/items', '?', '$filter=', 'Created lt datetime''', outputs('Compose_sess_cutoff'), ''' and SessionState ne ''Active''', '&', '$select=Id', '&', '$top=300')`
  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
- ### `For_each_old_session`
  - Run after: after `Get_old_sessions` Succeeded
  **Control > Apply to each**  concurrency 1
  - Select an output: `@body('Get_old_sessions')?['d']?['results']`
  - Inside `For_each_old_session`:
    - **`Purge_session`**
      - Run after: first action
      **SharePoint > Send an HTTP request to SharePoint**  `DELETE`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@concat('/_api/web/lists/getbytitle(''POUSessions'')/items(', items('For_each_old_session')?['Id'], ')')`
      - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "DELETE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
- ### `Table_findings`
  - Run after: after `For_each_old_session` Succeeded/Failed/Skipped/TimedOut
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
        "header": "Item",
        "value": "@item()?['item']"
      },
      {
        "header": "Detail",
        "value": "@item()?['detail']"
      }
    ]
  }
  ```
- ### `If_any_findings`
  - Run after: after `Table_findings` Succeeded
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(variables('vFindings')), 0)", true]}
  ```
  - Inside `If_any_findings`:
    - **`Send_reconcile_email_if_recipients`**
      - Run after: first action
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(not(empty(coalesce(outputs('Compose_Settings')?['ReportRecipientsDataHealth'], ''))), not(contains(coalesce(outputs('Compose_Settings')?['ReportRecipientsDataHealth'], ''), 'CHANGE-ME')))", true]}
      ```
      - Inside `Send_reconcile_email_if_recipients`:
        - **`Send_reconcile_email`**
          - Run after: first action
          **Office 365 Outlook > Send an email (V2)**
          ```json
          {
            "emailMessage/To": "@replace(coalesce(outputs('Compose_Settings')?['ReportRecipientsDataHealth'], ''), ',', ';')",
            "emailMessage/Subject": "@concat('POU reconciliation ', outputs('Compose_LocalDate'), ': ', string(length(variables('vFindings'))), ' problem(s)')",
            "emailMessage/Body": "@concat('<html><body style=''font-family:Segoe UI,Arial,sans-serif;font-size:13px''><h3>POU nightly reconciliation</h3><p>These stock records do not match their ledger. Posting is blocked for them until fixed.</p>', '<h4>Findings</h4>', body('Table_findings'), '<p style=\"color:#555\">Checked rows: see POUOpsEvents for history. Never edit OnHandQty directly: post an ADJUSTMENT or AUDIT.</p></body></html>')",
            "emailMessage/Importance": "Normal"
          }
          ```
- ### `Find_setting_LastReconcileDate`
  - Run after: after `If_any_findings` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Filter array**
  ```json
  {
    "from": "@body('Get_settings')?['d']?['results']",
    "where": "@equals(item()?['SettingKey'], 'LastReconcileDate')"
  }
  ```
- ### `Save_setting_LastReconcileDate`
  - Run after: after `Find_setting_LastReconcileDate` Succeeded
  **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
  - Site Address: `@outputs('Cfg_SiteUrl')`
  - Uri: `@concat('/_api/web/lists/getbytitle(''POUSettings'')/items(', first(body('Find_setting_LastReconcileDate'))?['Id'], ')')`
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
