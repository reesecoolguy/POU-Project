# POU-Monitor - POU - Failed / stuck request monitor

Hourly: raises ONE ops event (and one email) per failed or stuck request / ledger intent.

- **Trigger**: Recurrence 1 h - Hourly
- **Actions** (all levels): 37
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
- ### `Probe_problem_requests`
  - Run after: after `Guard_site_url_configured` Succeeded/Failed/Skipped/TimedOut
  **SharePoint > Send an HTTP request to SharePoint**  `GET`
  - Site Address: `@outputs('Cfg_SiteUrl')`
  - Uri: `@concat('/_api/web/lists/getbytitle(''POURequests'')/items', '?', '$filter=', 'RequestStatus eq ''Failed'' or RequestStatus eq ''Pending'' or RequestStatus eq ''Processing'' or RequestStatus eq ''AwaitingSupervisor''', '&', '$select=Id,RequestID,RequestType,RequestStatus,Created,ClaimedUtc,ResultCode,InventoryEffect,StockKey', '&', '$top=200')`
  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
- ### `Probe_open_intents`
  - Run after: after `Probe_problem_requests` Succeeded
  **SharePoint > Send an HTTP request to SharePoint**  `GET`
  - Site Address: `@outputs('Cfg_SiteUrl')`
  - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items', '?', '$filter=', 'PostingState eq ''Intent''', '&', '$select=LedgerKey,RequestID,StockKey,Created', '&', '$top=100')`
  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
- ### `Compose_nothing`
  - Run after: after `Probe_open_intents` Succeeded
  **Data Operation > Compose**
  ```json
  "@and(empty(body('Probe_problem_requests')?['d']?['results']), empty(body('Probe_open_intents')?['d']?['results']))"
  ```
- ### `If_nothing_to_report`
  - Run after: after `Compose_nothing` Succeeded
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@equals(outputs('Compose_nothing'), true)", true]}
  ```
  - Inside `If_nothing_to_report`:
    - **`Stop_all_clear`**
      - Run after: first action
      **Control > Terminate**
      ```json
      {
        "runStatus": "Succeeded"
      }
      ```
- ### `Get_settings`
  - Run after: after `If_nothing_to_report` Succeeded/Failed/Skipped/TimedOut
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
- ### `Init_vNew`
  - Run after: after `Compose_Settings` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vNew",
        "type": "array",
        "value": []
      }
    ]
  }
  ```
- ### `For_each_problem_request`
  - Run after: after `Init_vNew` Succeeded
  **Control > Apply to each**  concurrency 1
  - Select an output: `@body('Probe_problem_requests')?['d']?['results']`
  - Inside `For_each_problem_request`:
    - **`Compose_class`**
      - Run after: first action
      **Data Operation > Compose**
      ```json
      "@if(equals(items('For_each_problem_request')?['RequestStatus'], 'Failed'), 'FAILED', if(and(equals(items('For_each_problem_request')?['RequestStatus'], 'AwaitingSupervisor'), greater(sub(ticks(utcNow()), ticks(items('For_each_problem_request')?['Created'])), 288000000000)), 'WAITING_APPROVAL', if(and(or(equals(items('For_each_problem_request')?['RequestStatus'], 'Pending'), equals(items('For_each_problem_request')?['RequestStatus'], 'Processing')), greater(sub(ticks(utcNow()), ticks(items('For_each_problem_request')?['Created'])), 9000000000)), 'STUCK', '')))"
      ```
    - **`If_reportable`**
      - Run after: after `Compose_class` Succeeded
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@not(empty(outputs('Compose_class')))", true]}
      ```
      - Inside `If_reportable`:
        - **`Req_Once`**
          - Run after: first action
          **Control > Scope**
          - Inside `Req_Once`:
            - **`Req_Get_event`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items', '?', '$filter=', 'EventKey eq ''', uriComponent(replace(string(concat(outputs('Compose_class'), '|', items('For_each_problem_request')?['RequestID'])), '''', '''''')), '''', '&', '$select=Id', '&', '$top=2')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`Req_Event_is_new`**
              - Run after: after `Req_Get_event` Succeeded
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@empty(body('Req_Get_event')?['d']?['results'])", true]}
              ```
              - Inside `Req_Event_is_new`:
                - **`Req_Create_event`**
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
                    "Title": "@concat(outputs('Compose_class'), ' request ', items('For_each_problem_request')?['RequestType'], ' ', string(coalesce(items('For_each_problem_request')?['StockKey'], '')))",
                    "EventKey": "@concat(outputs('Compose_class'), '|', items('For_each_problem_request')?['RequestID'])",
                    "EventType": "@concat('REQUEST_', outputs('Compose_class'))",
                    "Severity": "@if(equals(items('For_each_problem_request')?['InventoryEffect'], 'Unknown'), 'Critical', if(equals(outputs('Compose_class'), 'FAILED'), 'Warning', 'Warning'))",
                    "Subject": "@concat(outputs('Compose_class'), ' request ', items('For_each_problem_request')?['RequestType'], ' ', string(coalesce(items('For_each_problem_request')?['StockKey'], '')))",
                    "Details": "@concat('RequestID ', items('For_each_problem_request')?['RequestID'], ' status ', items('For_each_problem_request')?['RequestStatus'], ' result ', string(coalesce(items('For_each_problem_request')?['ResultCode'], '')), ' effect ', string(coalesce(items('For_each_problem_request')?['InventoryEffect'], '(none yet)')), '. Created ', items('For_each_problem_request')?['Created'], '.')",
                    "FirstSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "OccurrenceCount": 1,
                    "Resolved": false
                  }
                  ```
                - **`Req_Remember`**
                  - Run after: after `Req_Create_event` Succeeded
                  **Variable > Append to array variable**
                  ```json
                  {
                    "name": "vNew",
                    "value": {
                      "severity": "@if(equals(items('For_each_problem_request')?['InventoryEffect'], 'Unknown'), 'Critical', if(equals(outputs('Compose_class'), 'FAILED'), 'Warning', 'Warning'))",
                      "type": "@concat('REQUEST_', outputs('Compose_class'))",
                      "subject": "@concat(outputs('Compose_class'), ' request ', items('For_each_problem_request')?['RequestType'], ' ', string(coalesce(items('For_each_problem_request')?['StockKey'], '')))",
                      "details": "@concat('RequestID ', items('For_each_problem_request')?['RequestID'], ' status ', items('For_each_problem_request')?['RequestStatus'], ' result ', string(coalesce(items('For_each_problem_request')?['ResultCode'], '')), ' effect ', string(coalesce(items('For_each_problem_request')?['InventoryEffect'], '(none yet)')), '. Created ', items('For_each_problem_request')?['Created'], '.')"
                    }
                  }
                  ```
- ### `For_each_open_intent`
  - Run after: after `For_each_problem_request` Succeeded/Failed/Skipped/TimedOut
  **Control > Apply to each**  concurrency 1
  - Select an output: `@body('Probe_open_intents')?['d']?['results']`
  - Inside `For_each_open_intent`:
    - **`If_intent_old`**
      - Run after: first action
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@greater(sub(ticks(utcNow()), ticks(items('For_each_open_intent')?['Created'])), 9000000000)", true]}
      ```
      - Inside `If_intent_old`:
        - **`Int_Once`**
          - Run after: first action
          **Control > Scope**
          - Inside `Int_Once`:
            - **`Int_Get_event`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items', '?', '$filter=', 'EventKey eq ''', uriComponent(replace(string(concat('INTENT|', items('For_each_open_intent')?['LedgerKey'])), '''', '''''')), '''', '&', '$select=Id', '&', '$top=2')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`Int_Event_is_new`**
              - Run after: after `Int_Get_event` Succeeded
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@empty(body('Int_Get_event')?['d']?['results'])", true]}
              ```
              - Inside `Int_Event_is_new`:
                - **`Int_Create_event`**
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
                    "Title": "@concat('Ledger intent not completed: ', items('For_each_open_intent')?['LedgerKey'])",
                    "EventKey": "@concat('INTENT|', items('For_each_open_intent')?['LedgerKey'])",
                    "EventType": "LEDGER_INTENT_STUCK",
                    "Severity": "Critical",
                    "Subject": "@concat('Ledger intent not completed: ', items('For_each_open_intent')?['LedgerKey'])",
                    "Details": "@concat('Intent ', items('For_each_open_intent')?['LedgerKey'], ' for request ', items('For_each_open_intent')?['RequestID'], ' has been open since ', items('For_each_open_intent')?['Created'], '. The sweeper should have finished it.')",
                    "FirstSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "OccurrenceCount": 1,
                    "Resolved": false
                  }
                  ```
                - **`Int_Remember`**
                  - Run after: after `Int_Create_event` Succeeded
                  **Variable > Append to array variable**
                  ```json
                  {
                    "name": "vNew",
                    "value": {
                      "severity": "Critical",
                      "type": "LEDGER_INTENT_STUCK",
                      "subject": "@concat('Ledger intent not completed: ', items('For_each_open_intent')?['LedgerKey'])",
                      "details": "@concat('Intent ', items('For_each_open_intent')?['LedgerKey'], ' for request ', items('For_each_open_intent')?['RequestID'], ' has been open since ', items('For_each_open_intent')?['Created'], '. The sweeper should have finished it.')"
                    }
                  }
                  ```
- ### `Table_new`
  - Run after: after `For_each_open_intent` Succeeded/Failed/Skipped/TimedOut
  **Data Operation > Create HTML/CSV table**
  ```json
  {
    "from": "@variables('vNew')",
    "format": "HTML",
    "columns": [
      {
        "header": "Severity",
        "value": "@item()?['severity']"
      },
      {
        "header": "Type",
        "value": "@item()?['type']"
      },
      {
        "header": "What",
        "value": "@item()?['subject']"
      },
      {
        "header": "Details",
        "value": "@item()?['details']"
      }
    ]
  }
  ```
- ### `If_any_new`
  - Run after: after `Table_new` Succeeded/Failed/Skipped/TimedOut
  **Control > Condition**  (advanced mode)
  ```json
  {"equals": ["@greater(length(variables('vNew')), 0)", true]}
  ```
  - Inside `If_any_new`:
    - **`Send_ops_email_if_recipients`**
      - Run after: first action
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(not(empty(coalesce(outputs('Compose_Settings')?['ReportRecipientsOps'], ''))), not(contains(coalesce(outputs('Compose_Settings')?['ReportRecipientsOps'], ''), 'CHANGE-ME')))", true]}
      ```
      - Inside `Send_ops_email_if_recipients`:
        - **`Send_ops_email`**
          - Run after: first action
          **Office 365 Outlook > Send an email (V2)**
          ```json
          {
            "emailMessage/To": "@replace(coalesce(outputs('Compose_Settings')?['ReportRecipientsOps'], ''), ',', ';')",
            "emailMessage/Subject": "@concat('POU ALERT: ', string(length(variables('vNew'))), ' new failed/stuck item(s)')",
            "emailMessage/Body": "@concat('<html><body style=''font-family:Segoe UI,Arial,sans-serif;font-size:13px''><h3>POU failed / stuck requests</h3><p>Each item below was newly detected. Inventory Effect = Applied means the quantity DID change.</p>', '<h4>New findings</h4>', body('Table_new'), '<p style=\"color:#555\">Resolve in the POUOpsEvents list (tick Resolved). See docs/10_Maintenance.md for each EventType.</p></body></html>')",
            "emailMessage/Importance": "Normal"
          }
          ```
      - If NO (else) in `Send_ops_email_if_recipients`:
        - **`NoRcptOps_Ops_event`**
          - Run after: first action
          **Control > Scope**
          - Inside `NoRcptOps_Ops_event`:
            - **`NoRcptOps_Get_event`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items', '?', '$filter=', 'EventKey eq ''', uriComponent(replace(string('REPORT_RECIPIENTS_OPS'), '''', '''''')), '''', '&', '$select=Id,OccurrenceCount', '&', '$top=2')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`NoRcptOps_Event_row`**
              - Run after: after `NoRcptOps_Get_event` Succeeded
              **Data Operation > Compose**
              ```json
              "@first(body('NoRcptOps_Get_event')?['d']?['results'])"
              ```
            - **`NoRcptOps_Event_exists`**
              - Run after: after `NoRcptOps_Event_row` Succeeded
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@not(equals(outputs('NoRcptOps_Event_row'), null))", true]}
              ```
              - Inside `NoRcptOps_Event_exists`:
                - **`NoRcptOps_Update_event`**
                  - Run after: first action
                  **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items(', outputs('NoRcptOps_Event_row')?['Id'], ')')`
                  - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
                  - Body:
                  ```json
                  {
                    "__metadata": {
                      "type": "SP.Data.POUOpsEventsListItem"
                    },
                    "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "OccurrenceCount": "@add(int(coalesce(outputs('NoRcptOps_Event_row')?['OccurrenceCount'], 1)), 1)",
                    "Details": "Setting ReportRecipientsOps is empty or still CHANGE-ME@... so failed/stuck alerts are only visible in POUOpsEvents.",
                    "Resolved": false
                  }
                  ```
              - If NO (else) in `NoRcptOps_Event_exists`:
                - **`NoRcptOps_Create_event`**
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
                    "Title": "Ops alert recipients not configured",
                    "EventKey": "REPORT_RECIPIENTS_OPS",
                    "EventType": "CONFIG",
                    "Severity": "Warning",
                    "Subject": "Ops alert recipients not configured",
                    "Details": "Setting ReportRecipientsOps is empty or still CHANGE-ME@... so failed/stuck alerts are only visible in POUOpsEvents.",
                    "FirstSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                    "OccurrenceCount": 1,
                    "Resolved": false
                  }
                  ```
