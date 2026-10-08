# POU-Session - POU - Session (badge login/logout)

Instant flow. LOGIN validates the badge and station and creates a session bound to the calling Microsoft account. LOGOUT ends it.

- **Trigger**: Instant (Power Apps V2) - On demand from the app
- **Actions** (all levels): 67
- **Connections**: SharePoint (`shared_sharepointonline`) as the flow service account
- **How to read this**: actions are listed in run order. Indented items are inside the parent scope / condition branch / loop. `Compose_*`, `Set_*` and `Result_*` actions are the decision points; each SharePoint call shows its exact URI and body. Expressions are the literal text to type into the Expression tab (without the leading `@` when you type into the editor's expression box).
- **Error handling model**: no step relies on a container's Succeeded/Failed status. Risky calls are followed by a step that runs after Succeeded/Failed/Skipped/TimedOut and inspects `actions('<call>')?['status']`. Outcome fields live in variable `vRes`; the Response action runs after everything and its defaults say 'Processing / UNCONFIRMED - do not repeat'.

## Trigger
```json
{
  "manual": {
    "type": "Request",
    "kind": "Button",
    "inputs": {
      "schema": {
        "type": "object",
        "properties": {
          "text": {
            "title": "Mode",
            "type": "string",
            "x-ms-dynamically-added": true,
            "description": "LOGIN or LOGOUT",
            "x-ms-content-hint": "TEXT"
          },
          "text_1": {
            "title": "BadgeID",
            "type": "string",
            "x-ms-dynamically-added": true,
            "description": "Typed or scanned badge",
            "x-ms-content-hint": "TEXT"
          },
          "text_2": {
            "title": "StationID",
            "type": "string",
            "x-ms-dynamically-added": true,
            "description": "Station",
            "x-ms-content-hint": "TEXT"
          },
          "text_3": {
            "title": "SessionID",
            "type": "string",
            "x-ms-dynamically-added": true,
            "description": "For LOGOUT",
            "x-ms-content-hint": "TEXT"
          },
          "text_4": {
            "title": "ClientAccount",
            "type": "string",
            "x-ms-dynamically-added": true,
            "description": "Signed-in account as reported by the app (used only if the platform header is absent)",
            "x-ms-content-hint": "TEXT"
          }
        },
        "required": [
          "text",
          "text_1",
          "text_2",
          "text_3",
          "text_4"
        ]
      }
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
- ### `Init_vOk`
  - Run after: after `Guard_site_url_configured` Succeeded/Failed/Skipped/TimedOut
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vOk",
        "type": "string",
        "value": "no"
      }
    ]
  }
  ```
- ### `Init_vCode`
  - Run after: after `Init_vOk` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vCode",
        "type": "string",
        "value": "ERROR"
      }
    ]
  }
  ```
- ### `Init_vMessage`
  - Run after: after `Init_vCode` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vMessage",
        "type": "string",
        "value": "Could not complete the request. Try again."
      }
    ]
  }
  ```
- ### `Init_vSessionId`
  - Run after: after `Init_vMessage` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vSessionId",
        "type": "string",
        "value": ""
      }
    ]
  }
  ```
- ### `Init_vName`
  - Run after: after `Init_vSessionId` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vName",
        "type": "string",
        "value": ""
      }
    ]
  }
  ```
- ### `Init_vRole`
  - Run after: after `Init_vName` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vRole",
        "type": "string",
        "value": ""
      }
    ]
  }
  ```
- ### `Compose_Mode`
  - Run after: after `Init_vRole` Succeeded
  **Data Operation > Compose**
  ```json
  "@toUpper(trim(string(coalesce(triggerBody()?['text'], ''))))"
  ```
- ### `Compose_Badge`
  - Run after: after `Compose_Mode` Succeeded
  **Data Operation > Compose**
  ```json
  "@trim(replace(string(coalesce(triggerBody()?['text_1'], '')), '*', ''))"
  ```
- ### `Compose_StationIn`
  - Run after: after `Compose_Badge` Succeeded
  **Data Operation > Compose**
  ```json
  "@trim(string(coalesce(triggerBody()?['text_2'], '')))"
  ```
- ### `Compose_SessionIn`
  - Run after: after `Compose_StationIn` Succeeded
  **Data Operation > Compose**
  ```json
  "@trim(string(coalesce(triggerBody()?['text_3'], '')))"
  ```
- ### `Compose_Header`
  - Run after: after `Compose_SessionIn` Succeeded
  **Data Operation > Compose**
  ```json
  "@coalesce(triggerOutputs()?['headers']?['x-ms-user-email-encoded'], '')"
  ```
- ### `Compose_AppAccount`
  - Run after: after `Compose_Header` Succeeded
  **Data Operation > Compose**
  ```json
  "@toLower(if(empty(outputs('Compose_Header')), trim(string(coalesce(triggerBody()?['text_4'], ''))), decodeBase64(outputs('Compose_Header'))))"
  ```
- ### `Work`
  - Run after: after `Compose_AppAccount` Succeeded
  **Control > Scope**
  - Inside `Work`:
    - **`Get_settings`**
      - Run after: first action
      **SharePoint > Send an HTTP request to SharePoint**  `GET`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@concat('/_api/web/lists/getbytitle(''POUSettings'')/items', '?', '$select=Id,SettingKey,SettingValue', '&', '$top=500')`
      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
    - **`Select_settings`**
      - Run after: after `Get_settings` Succeeded
      **Data Operation > Select**
      ```json
      {
        "from": "@body('Get_settings')?['d']?['results']",
        "select": "@concat('\"', item()?['SettingKey'], '\":\"', replace(replace(coalesce(item()?['SettingValue'], ''), '\"', ''), '\\', '/'), '\"')"
      }
      ```
    - **`Compose_Settings`**
      - Run after: after `Select_settings` Succeeded
      **Data Operation > Compose**
      ```json
      "@json(concat('{', join(body('Select_settings'), ','), '}'))"
      ```
    - **`Compose_Messages`**
      - Run after: after `Compose_Settings` Succeeded
      **Data Operation > Compose**
      ```json
      {
        "UNKNOWN_TYPE": "Unknown request type.",
        "NO_SESSION": "You are not signed in. Scan your badge again.",
        "SESSION_ENDED": "Your session has ended. Scan your badge again.",
        "SESSION_EXPIRED": "Your session timed out. Scan your badge again.",
        "SESSION_ACCOUNT_MISMATCH": "This badge session belongs to a different Microsoft sign-in. Scan your badge again.",
        "EMPLOYEE_INACTIVE": "This badge is not active. See a supervisor.",
        "STATION_INVALID": "This station is not set up or is inactive. See a supervisor.",
        "STATION_MISMATCH": "This request came from a different station than the session. Scan your badge again.",
        "STATION_ACCOUNT_MISMATCH": "This station only accepts its assigned Microsoft account.",
        "NOT_AUTHORIZED": "This action needs a supervisor who is signed in to Microsoft with their own account.",
        "SUPERVISOR_REJECTED": "A supervisor rejected this request. Nothing was changed.",
        "STOCK_NOT_FOUND": "That item/location does not exist. Nothing was changed.",
        "STOCK_INACTIVE": "That item/location is inactive. Nothing was changed.",
        "INVALID_QUANTITY": "Quantity must be a whole number of 1 or more. Nothing was changed.",
        "INVALID_COUNT": "Counted quantity must be a whole number of 0 or more. Nothing was changed.",
        "NO_BALANCE": "This item/location has no verified quantity yet. A supervisor must count it first (Audit). Nothing was changed.",
        "BALANCE_UNVERIFIED": "This quantity has not been verified by a count yet. Nothing was changed.",
        "MISSING_EXPECTED_VERSION": "The count did not record the stock version it started from. Recount. Nothing was changed.",
        "OPENING_NOT_ALLOWED": "An opening balance can only be set once, on a record with no balance. Nothing was changed.",
        "REASON_REQUIRED": "A reason is required. Nothing was changed.",
        "REVERSAL_TARGET_MISSING": "The movement to reverse was not found. Nothing was changed.",
        "REVERSAL_NOT_POSTED": "Only posted ISSUE or RECEIPT movements can be reversed. Nothing was changed.",
        "REVERSAL_WRONG_STOCK": "That movement belongs to a different item/location. Nothing was changed.",
        "REVERSAL_ALREADY": "That movement has already been reversed. Nothing was changed.",
        "REVERSAL_NEGATIVE": "Reversing would make the quantity negative. Use an ADJUSTMENT instead. Nothing was changed.",
        "DRIFT_DETECTED": "The stored quantity does not match its history. A supervisor has been alerted. Nothing was changed.",
        "STOCK_CHANGED_OUTSIDE_PROTOCOL": "The stored quantity was changed outside the normal process while this was being posted. A supervisor has been alerted. Nothing was changed by this request.",
        "PAYLOAD_INVALID": "The details supplied are incomplete or invalid. Nothing was changed.",
        "ITEM_EXISTS": "That Item ID already exists. Use 'Add stocking location' to stock it somewhere else. Nothing was changed.",
        "ITEM_NOT_FOUND": "That Item ID does not exist. Nothing was changed.",
        "STOCK_EXISTS": "That item is already stocked at that location. Nothing was changed.",
        "LOCATION_UNKNOWN": "That location is not in the location list (an admin adds locations). Nothing was changed.",
        "TARGET_NOT_FOUND": "The request being approved was not found.",
        "TARGET_NOT_WAITING": "That request is not waiting for approval.",
        "NONZERO_STOCK": "An item/location with stock cannot be deactivated. Count it to zero first. Nothing was changed.",
        "GAVE_UP": "This could not be processed after several automatic attempts. Nothing was changed. Please repeat it.",
        "EXPIRED": "No supervisor approved this in time. Nothing was changed. Please repeat it.",
        "INVALID_BADGE": "Badge not recognised. Try again or see a supervisor.",
        "BADGE_INACTIVE": "This badge is not active. See a supervisor.",
        "BAD_MODE": "Unknown session request."
      }
      ```
    - **`If_login`**
      - Run after: after `Compose_Messages` Succeeded
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@equals(outputs('Compose_Mode'), 'LOGIN')", true]}
      ```
      - Inside `If_login`:
        - **`Get_employee`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUEmployees'')/items', '?', '$filter=', 'BadgeID eq ''', uriComponent(replace(string(coalesce(outputs('Compose_Badge'), 'NONE')), '''', '''''')), '''', '&', '$select=Id,BadgeID,EmployeeName,Active,Role', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_Emp`**
          - Run after: after `Get_employee` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_employee')?['d']?['results'])"
          ```
        - **`Get_station`**
          - Run after: after `Compose_Emp` Succeeded
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUStations'')/items', '?', '$filter=', 'StationID eq ''', uriComponent(replace(string(coalesce(outputs('Compose_StationIn'), 'NONE')), '''', '''''')), '''', '&', '$select=Id,StationID,Active,ExpectedAccountUPN', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_Stn`**
          - Run after: after `Get_station` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_station')?['d']?['results'])"
          ```
        - **`Login_Rules1_badge_known_to_station_account`**
          - Run after: after `Compose_Stn` Succeeded
          **Data Operation > Compose**
          ```json
          "@if(empty(if(equals(outputs('Compose_Emp'), null), 'INVALID_BADGE', '')), if(empty(if(and(not(equals(outputs('Compose_Emp'), null)), not(equals(outputs('Compose_Emp')?['Active'], true))), 'BADGE_INACTIVE', '')), if(empty(if(or(equals(outputs('Compose_Stn'), null), not(equals(outputs('Compose_Stn')?['Active'], true))), 'STATION_INVALID', '')), if(and(not(empty(coalesce(outputs('Compose_Stn')?['ExpectedAccountUPN'], ''))), not(equals(toLower(coalesce(outputs('Compose_Stn')?['ExpectedAccountUPN'], '')), outputs('Compose_AppAccount')))), 'STATION_ACCOUNT_MISMATCH', ''), if(or(equals(outputs('Compose_Stn'), null), not(equals(outputs('Compose_Stn')?['Active'], true))), 'STATION_INVALID', '')), if(and(not(equals(outputs('Compose_Emp'), null)), not(equals(outputs('Compose_Emp')?['Active'], true))), 'BADGE_INACTIVE', '')), if(equals(outputs('Compose_Emp'), null), 'INVALID_BADGE', ''))"
          ```
        - **`Login_Result`**
          - Run after: after `Login_Rules1_badge_known_to_station_account` Succeeded
          **Data Operation > Compose**
          ```json
          "@outputs('Login_Rules1_badge_known_to_station_account')"
          ```
        - **`If_login_fail`**
          - Run after: after `Login_Result` Succeeded
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@not(empty(outputs('Login_Result')))", true]}
          ```
          - Inside `If_login_fail`:
            - **`Set_login_fail`**
              - Run after: first action
              **Control > Scope**
              - Inside `Set_login_fail`:
                - **`Set_login_fail_vCode`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vCode",
                    "value": "@outputs('Login_Result')"
                  }
                  ```
                - **`Set_login_fail_vMessage`**
                  - Run after: after `Set_login_fail_vCode` Succeeded
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vMessage",
                    "value": "@coalesce(outputs('Compose_Messages')?[outputs('Login_Result')], outputs('Login_Result'))"
                  }
                  ```
            - **`If_log_bad_badge`**
              - Run after: after `Set_login_fail` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@equals(outputs('Login_Result'), 'INVALID_BADGE')", true]}
              ```
              - Inside `If_log_bad_badge`:
                - **`Badge_Ops_event`**
                  - Run after: first action
                  **Control > Scope**
                  - Inside `Badge_Ops_event`:
                    - **`Badge_Get_event`**
                      - Run after: first action
                      **SharePoint > Send an HTTP request to SharePoint**  `GET`
                      - Site Address: `@outputs('Cfg_SiteUrl')`
                      - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items', '?', '$filter=', 'EventKey eq ''', uriComponent(replace(string(concat('BADGEFAIL|', outputs('Compose_StationIn'), '|', formatDateTime(utcNow(), 'yyyy-MM-dd'))), '''', '''''')), '''', '&', '$select=Id,OccurrenceCount', '&', '$top=2')`
                      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
                    - **`Badge_Event_row`**
                      - Run after: after `Badge_Get_event` Succeeded
                      **Data Operation > Compose**
                      ```json
                      "@first(body('Badge_Get_event')?['d']?['results'])"
                      ```
                    - **`Badge_Event_exists`**
                      - Run after: after `Badge_Event_row` Succeeded
                      **Control > Condition**  (advanced mode)
                      ```json
                      {"equals": ["@not(equals(outputs('Badge_Event_row'), null))", true]}
                      ```
                      - Inside `Badge_Event_exists`:
                        - **`Badge_Update_event`**
                          - Run after: first action
                          **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
                          - Site Address: `@outputs('Cfg_SiteUrl')`
                          - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items(', outputs('Badge_Event_row')?['Id'], ')')`
                          - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
                          - Body:
                          ```json
                          {
                            "__metadata": {
                              "type": "SP.Data.POUOpsEventsListItem"
                            },
                            "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                            "OccurrenceCount": "@add(int(coalesce(outputs('Badge_Event_row')?['OccurrenceCount'], 1)), 1)",
                            "Details": "@concat('Unrecognised badge attempts today at station ', outputs('Compose_StationIn'), '. Repeated failures may mean guessing. Last typed value length: ', string(length(outputs('Compose_Badge'))))",
                            "Resolved": false
                          }
                          ```
                      - If NO (else) in `Badge_Event_exists`:
                        - **`Badge_Create_event`**
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
                            "Title": "@concat('Unknown badge scanned at ', outputs('Compose_StationIn'))",
                            "EventKey": "@concat('BADGEFAIL|', outputs('Compose_StationIn'), '|', formatDateTime(utcNow(), 'yyyy-MM-dd'))",
                            "EventType": "BADGE_FAILURES",
                            "Severity": "Warning",
                            "Subject": "@concat('Unknown badge scanned at ', outputs('Compose_StationIn'))",
                            "Details": "@concat('Unrecognised badge attempts today at station ', outputs('Compose_StationIn'), '. Repeated failures may mean guessing. Last typed value length: ', string(length(outputs('Compose_Badge'))))",
                            "FirstSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                            "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                            "OccurrenceCount": 1,
                            "Resolved": false
                          }
                          ```
        - **`If_login_ok`**
          - Run after: after `If_login_fail` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@equals(outputs('Login_Result'), '')", true]}
          ```
          - Inside `If_login_ok`:
            - **`Compose_NewSessionId`**
              - Run after: first action
              **Data Operation > Compose**
              ```json
              "@replace(guid(), '-', '')"
              ```
            - **`Create_session`**
              - Run after: after `Compose_NewSessionId` Succeeded
              **SharePoint > Send an HTTP request to SharePoint**  `POST`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `/_api/web/lists/getbytitle('POUSessions')/items`
              - Headers: `{"Content-Type": "application/json;odata=verbose"}`  (+ Accept: application/json;odata=verbose)
              - Body:
              ```json
              {
                "__metadata": {
                  "type": "SP.Data.POUSessionsListItem"
                },
                "Title": "@concat('Session ', outputs('Compose_Emp')?['EmployeeName'], ' @ ', outputs('Compose_StationIn'))",
                "SessionID": "@outputs('Compose_NewSessionId')",
                "BadgeID": "@outputs('Compose_Emp')?['BadgeID']",
                "EmployeeName": "@outputs('Compose_Emp')?['EmployeeName']",
                "StationID": "@outputs('Compose_StationIn')",
                "AppAccountUPN": "@outputs('Compose_AppAccount')",
                "StartedUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                "LastActivityUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                "SessionState": "Active"
              }
              ```
            - **`If_session_created`**
              - Run after: after `Create_session` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@equals(actions('Create_session')?['status'], 'Succeeded')", true]}
              ```
              - Inside `If_session_created`:
                - **`Set_login_ok`**
                  - Run after: first action
                  **Control > Scope**
                  - Inside `Set_login_ok`:
                    - **`Set_login_ok_vOk`**
                      - Run after: first action
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vOk",
                        "value": "yes"
                      }
                      ```
                    - **`Set_login_ok_vCode`**
                      - Run after: after `Set_login_ok_vOk` Succeeded
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vCode",
                        "value": "OK"
                      }
                      ```
                    - **`Set_login_ok_vMessage`**
                      - Run after: after `Set_login_ok_vCode` Succeeded
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vMessage",
                        "value": "@concat('Welcome, ', outputs('Compose_Emp')?['EmployeeName'])"
                      }
                      ```
                    - **`Set_login_ok_vSessionId`**
                      - Run after: after `Set_login_ok_vMessage` Succeeded
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vSessionId",
                        "value": "@outputs('Compose_NewSessionId')"
                      }
                      ```
                    - **`Set_login_ok_vName`**
                      - Run after: after `Set_login_ok_vSessionId` Succeeded
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vName",
                        "value": "@outputs('Compose_Emp')?['EmployeeName']"
                      }
                      ```
                    - **`Set_login_ok_vRole`**
                      - Run after: after `Set_login_ok_vName` Succeeded
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vRole",
                        "value": "@coalesce(outputs('Compose_Emp')?['Role'], 'Operator')"
                      }
                      ```
              - If NO (else) in `If_session_created`:
                - **`Set_login_error`**
                  - Run after: first action
                  **Control > Scope**
                  - Inside `Set_login_error`:
                    - **`Set_login_error_vCode`**
                      - Run after: first action
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vCode",
                        "value": "SESSION_NOT_CREATED"
                      }
                      ```
                    - **`Set_login_error_vMessage`**
                      - Run after: after `Set_login_error_vCode` Succeeded
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vMessage",
                        "value": "Could not start a session. Try again."
                      }
                      ```
    - **`If_logout`**
      - Run after: after `If_login` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@equals(outputs('Compose_Mode'), 'LOGOUT')", true]}
      ```
      - Inside `If_logout`:
        - **`Get_session_out`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUSessions'')/items', '?', '$filter=', 'SessionID eq ''', uriComponent(replace(string(coalesce(outputs('Compose_SessionIn'), 'NONE')), '''', '''''')), '''', '&', '$select=Id,AppAccountUPN,SessionState', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_SessOut`**
          - Run after: after `Get_session_out` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_session_out')?['d']?['results'])"
          ```
        - **`If_can_end`**
          - Run after: after `Compose_SessOut` Succeeded
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(not(equals(outputs('Compose_SessOut'), null)), equals(toLower(coalesce(outputs('Compose_SessOut')?['AppAccountUPN'], '')), outputs('Compose_AppAccount')))", true]}
          ```
          - Inside `If_can_end`:
            - **`End_session`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUSessions'')/items(', outputs('Compose_SessOut')?['Id'], ')')`
              - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
              - Body:
              ```json
              {
                "__metadata": {
                  "type": "SP.Data.POUSessionsListItem"
                },
                "SessionState": "Ended",
                "EndedReason": "logout"
              }
              ```
            - **`If_ended`**
              - Run after: after `End_session` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@equals(actions('End_session')?['status'], 'Succeeded')", true]}
              ```
              - Inside `If_ended`:
                - **`Set_logout_ok`**
                  - Run after: first action
                  **Control > Scope**
                  - Inside `Set_logout_ok`:
                    - **`Set_logout_ok_vOk`**
                      - Run after: first action
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vOk",
                        "value": "yes"
                      }
                      ```
                    - **`Set_logout_ok_vCode`**
                      - Run after: after `Set_logout_ok_vOk` Succeeded
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vCode",
                        "value": "OK"
                      }
                      ```
                    - **`Set_logout_ok_vMessage`**
                      - Run after: after `Set_logout_ok_vCode` Succeeded
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vMessage",
                        "value": "Signed out."
                      }
                      ```
    - **`If_bad_mode`**
      - Run after: after `If_logout` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@not(contains(createArray('LOGIN', 'LOGOUT'), outputs('Compose_Mode')))", true]}
      ```
      - Inside `If_bad_mode`:
        - **`Set_bad_mode`**
          - Run after: first action
          **Control > Scope**
          - Inside `Set_bad_mode`:
            - **`Set_bad_mode_vCode`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vCode",
                "value": "BAD_MODE"
              }
              ```
            - **`Set_bad_mode_vMessage`**
              - Run after: after `Set_bad_mode_vCode` Succeeded
              **Variable > Set variable**
              ```json
              {
                "name": "vMessage",
                "value": "@coalesce(outputs('Compose_Messages')?['BAD_MODE'], 'BAD_MODE')"
              }
              ```
- ### `Respond`
  - Run after: after `Work` Succeeded/Failed/Skipped/TimedOut
  **Power Apps > Respond to a PowerApp or flow**
  ```json
  {
    "statusCode": 200,
    "body": {
      "ok": "@variables('vOk')",
      "code": "@variables('vCode')",
      "message": "@variables('vMessage')",
      "sessionId": "@variables('vSessionId')",
      "employeeName": "@variables('vName')",
      "role": "@variables('vRole')",
      "idleMinutes": "@string(int(coalesce(outputs('Compose_Settings')?['IdleTimeoutMinutes'], '3')))"
    },
    "schema": {
      "type": "object",
      "properties": {
        "ok": {
          "type": "string"
        },
        "code": {
          "type": "string"
        },
        "message": {
          "type": "string"
        },
        "sessionId": {
          "type": "string"
        },
        "employeeName": {
          "type": "string"
        },
        "role": {
          "type": "string"
        },
        "idleMinutes": {
          "type": "string"
        }
      }
    }
  }
  ```
