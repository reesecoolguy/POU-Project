# POU-ProcessRequest - POU - Process Request

Instant flow called by the app with a RequestID. Claims the request, validates session/identity/permissions on the server, creates the ledger intent (unique-key compare-and-swap), applies the stock change, marks it Posted, and answers with the real outcome.

- **Trigger**: Instant (Power Apps V2) - On demand from the app / supervisor console
- **Actions** (all levels): 218
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
            "title": "RequestID",
            "type": "string",
            "x-ms-dynamically-added": true,
            "description": "The request GUID created by the app",
            "x-ms-content-hint": "TEXT"
          }
        },
        "required": [
          "text"
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
- ### `Init_vRes`
  - Run after: after `Guard_site_url_configured` Succeeded/Failed/Skipped/TimedOut
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vRes",
        "type": "object",
        "value": {
          "outcome": "continue",
          "status": "Processing",
          "code": "UNCONFIRMED",
          "message": "Not confirmed yet. Do NOT repeat this action: it may already have been recorded. The system is still checking and will finish it automatically.",
          "finalize": "no",
          "effect": "",
          "ledger": "",
          "newOnHand": "",
          "authBy": ""
        }
      }
    ]
  }
  ```
- ### `Init_vAuth`
  - Run after: after `Init_vRes` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vAuth",
        "type": "object",
        "value": {
          "isSup": false,
          "isAdmin": false,
          "name": "",
          "decision": "",
          "approver": ""
        }
      }
    ]
  }
  ```
- ### `Init_vRev`
  - Run after: after `Init_vAuth` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vRev",
        "type": "object",
        "value": {
          "orig": null,
          "existing": false
        }
      }
    ]
  }
  ```
- ### `Init_vAttempt`
  - Run after: after `Init_vRev` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vAttempt",
        "type": "integer",
        "value": 0
      }
    ]
  }
  ```
- ### `Init_vIntent`
  - Run after: after `Init_vAttempt` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vIntent",
        "type": "string",
        "value": "none"
      }
    ]
  }
  ```
- ### `Init_vSeq`
  - Run after: after `Init_vIntent` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vSeq",
        "type": "integer",
        "value": 0
      }
    ]
  }
  ```
- ### `Init_vApplied`
  - Run after: after `Init_vSeq` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vApplied",
        "type": "string",
        "value": "no"
      }
    ]
  }
  ```
- ### `Init_vApplyTries`
  - Run after: after `Init_vApplied` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vApplyTries",
        "type": "integer",
        "value": 0
      }
    ]
  }
  ```
- ### `Init_vAttempts`
  - Run after: after `Init_vApplyTries` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vAttempts",
        "type": "integer",
        "value": 0
      }
    ]
  }
  ```
- ### `Init_vSessionItem`
  - Run after: after `Init_vAttempts` Succeeded
  **Variable > Initialize variable**
  ```json
  {
    "variables": [
      {
        "name": "vSessionItem",
        "type": "string",
        "value": ""
      }
    ]
  }
  ```
- ### `Compose_RequestIdIn`
  - Run after: after `Init_vSessionItem` Succeeded
  **Data Operation > Compose**
  ```json
  "@trim(string(coalesce(triggerBody()?['text'], '')))"
  ```
- ### `Core`
  - Run after: after `Compose_RequestIdIn` Succeeded
  **Control > Scope**
  - Inside `Core`:
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
        "STATION_ACCOUNT_MISMATCH": "This station only accepts requests from its assigned Microsoft account.",
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
        "EXPIRED": "No supervisor approved this in time. Nothing was changed. Please repeat it."
      }
      ```
    - **`Get_request`**
      - Run after: after `Compose_Messages` Succeeded
      **SharePoint > Send an HTTP request to SharePoint**  `GET`
      - Site Address: `@outputs('Cfg_SiteUrl')`
      - Uri: `@concat('/_api/web/lists/getbytitle(''POURequests'')/items', '?', '$filter=', 'RequestID eq ''', uriComponent(replace(string(outputs('Compose_RequestIdIn')), '''', '''''')), '''', '&', '$select=Id,Created,RequestID,RequestType,RequestStatus,IsOpen,SessionID,StationID,StockKey,ItemID,LocationCode,Quantity,ExpectedVersion,PayloadJson,Reason,ReversesLedgerKey,TargetRequestID,Decision,ResultCode,ResultMessage,LedgerKey,InventoryEffect,ClaimedUtc,AttemptCount,ProcessingRunId,Author/EMail', '&', '$top=2', '&', '$expand=Author')`
      - Headers: `{}`  (+ Accept: application/json;odata=verbose)
    - **`Compose_Req`**
      - Run after: after `Get_request` Succeeded
      **Data Operation > Compose**
      ```json
      "@first(body('Get_request')?['d']?['results'])"
      ```
    - **`If_request_missing`**
      - Run after: after `Compose_Req` Succeeded
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@equals(outputs('Compose_Req'), null)", true]}
      ```
      - Inside `If_request_missing`:
        - **`Result_not_found`**
          - Run after: first action
          **Variable > Set variable**
          ```json
          {
            "name": "vRes",
            "value": {
              "outcome": "done",
              "status": "NotFound",
              "code": "REQUEST_NOT_FOUND",
              "message": "That request was not found. If you just created it, wait a moment; otherwise it was never recorded.",
              "finalize": "no",
              "effect": "",
              "ledger": "",
              "newOnHand": "",
              "authBy": ""
            }
          }
          ```
    - **`Compose_Status`**
      - Run after: after `If_request_missing` Succeeded/Failed/Skipped/TimedOut
      **Data Operation > Compose**
      ```json
      "@coalesce(outputs('Compose_Req')?['RequestStatus'], '')"
      ```
    - **`If_already_terminal`**
      - Run after: after `Compose_Status` Succeeded
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), contains(createArray('Succeeded', 'Rejected', 'Failed'), outputs('Compose_Status')))", true]}
      ```
      - Inside `If_already_terminal`:
        - **`Result_stored`**
          - Run after: first action
          **Variable > Set variable**
          ```json
          {
            "name": "vRes",
            "value": {
              "outcome": "done",
              "status": "@outputs('Compose_Status')",
              "code": "@coalesce(outputs('Compose_Req')?['ResultCode'], '')",
              "message": "@coalesce(outputs('Compose_Req')?['ResultMessage'], '')",
              "finalize": "no",
              "effect": "@coalesce(outputs('Compose_Req')?['InventoryEffect'], '')",
              "ledger": "@coalesce(outputs('Compose_Req')?['LedgerKey'], '')",
              "newOnHand": "",
              "authBy": ""
            }
          }
          ```
    - **`Compose_ClaimDecision`**
      - Run after: after `If_already_terminal` Succeeded/Failed/Skipped/TimedOut
      **Data Operation > Compose**
      ```json
      "@if(and(equals(outputs('Compose_Status'), 'Processing'), less(sub(ticks(utcNow()), ticks(coalesce(outputs('Compose_Req')?['ClaimedUtc'], '2000-01-01T00:00:00Z'))), mul(int(coalesce(outputs('Compose_Settings')?['StaleClaimSeconds'], '120')), 10000000))), 'busy', 'claim')"
      ```
    - **`If_busy_elsewhere`**
      - Run after: after `Compose_ClaimDecision` Succeeded
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(outputs('Compose_ClaimDecision'), 'busy'))", true]}
      ```
      - Inside `If_busy_elsewhere`:
        - **`Result_busy`**
          - Run after: first action
          **Variable > Set variable**
          ```json
          {
            "name": "vRes",
            "value": {
              "outcome": "done",
              "status": "Processing",
              "code": "IN_PROGRESS",
              "message": "Being processed right now. Do not repeat; the status will update.",
              "finalize": "no",
              "effect": "",
              "ledger": "",
              "newOnHand": "",
              "authBy": ""
            }
          }
          ```
    - **`Stage_claim`**
      - Run after: after `If_busy_elsewhere` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@equals(variables('vRes')?['outcome'], 'continue')", true]}
      ```
      - Inside `Stage_claim`:
        - **`Claim_request`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POURequests'')/items(', outputs('Compose_Req')?['Id'], ')')`
          - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "@outputs('Compose_Req')?['__metadata']?['etag']"}`  (+ Accept: application/json;odata=verbose)
          - Body:
          ```json
          {
            "__metadata": {
              "type": "SP.Data.POURequestsListItem"
            },
            "RequestStatus": "Processing",
            "ProcessingRunId": "@workflow()['run']['name']",
            "ClaimedUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
            "AttemptCount": "@if(equals(outputs('Compose_Status'), 'AwaitingSupervisor'), 1, add(int(coalesce(outputs('Compose_Req')?['AttemptCount'], 0)), 1))",
            "IsOpen": true
          }
          ```
        - **`If_claim_lost`**
          - Run after: after `Claim_request` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@not(equals(actions('Claim_request')?['status'], 'Succeeded'))", true]}
          ```
          - Inside `If_claim_lost`:
            - **`Result_claim_lost`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Processing",
                  "code": "CLAIM_LOST",
                  "message": "Another worker is processing this request. Do not repeat; the status will update.",
                  "finalize": "no",
                  "effect": "",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": ""
                }
              }
              ```
          - If NO (else) in `If_claim_lost`:
            - **`Set_vAttempts`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vAttempts",
                "value": "@if(equals(outputs('Compose_Status'), 'AwaitingSupervisor'), 1, add(int(coalesce(outputs('Compose_Req')?['AttemptCount'], 0)), 1))"
              }
              ```
    - **`Stage_existing_ledger`**
      - Run after: after `Stage_claim` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), contains(createArray('ISSUE', 'RECEIPT', 'AUDIT', 'OPENING', 'ADJUSTMENT', 'REVERSAL'), outputs('Compose_Req')?['RequestType']))", true]}
      ```
      - Inside `Stage_existing_ledger`:
        - **`Get_existing_ledger`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items', '?', '$filter=', 'RequestID eq ''', uriComponent(replace(string(outputs('Compose_RequestIdIn')), '''', '''''')), '''', '&', '$select=Id,LedgerKey,RequestID,LedgerType,PostingState,StockKey,ItemID,LocationCode,SeqNo,QtyDelta,QtyBefore,QtyAfter,AffectsBalance,ReversesLedgerKey,OccurredUtc,BadgeID,EmployeeName,Origin', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_ExistingLedger`**
          - Run after: after `Get_existing_ledger` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_existing_ledger')?['d']?['results'])"
          ```
        - **`If_existing_posted`**
          - Run after: after `Compose_ExistingLedger` Succeeded
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(not(equals(outputs('Compose_ExistingLedger'), null)), equals(outputs('Compose_ExistingLedger')?['PostingState'], 'Posted'))", true]}
          ```
          - Inside `If_existing_posted`:
            - **`Compose_PostedMessage`**
              - Run after: first action
              **Data Operation > Compose**
              ```json
              "@if(equals(outputs('Compose_ExistingLedger')?['LedgerType'], 'ISSUE'), concat('Removed ', string(sub(0, int(coalesce(outputs('Compose_ExistingLedger')?['QtyDelta'], 0)))), ' x ', concat(outputs('Compose_ExistingLedger')?['ItemID'], ' @ ', outputs('Compose_ExistingLedger')?['LocationCode']), '. On hand now ', string(outputs('Compose_ExistingLedger')?['QtyAfter']), '.'), if(equals(outputs('Compose_ExistingLedger')?['LedgerType'], 'RECEIPT'), concat('Added ', string(coalesce(outputs('Compose_ExistingLedger')?['QtyDelta'], 0)), ' x ', concat(outputs('Compose_ExistingLedger')?['ItemID'], ' @ ', outputs('Compose_ExistingLedger')?['LocationCode']), '. On hand now ', string(outputs('Compose_ExistingLedger')?['QtyAfter']), '.'), if(equals(outputs('Compose_ExistingLedger')?['LedgerType'], 'AUDIT'), concat('Count recorded for ', concat(outputs('Compose_ExistingLedger')?['ItemID'], ' @ ', outputs('Compose_ExistingLedger')?['LocationCode']), ': ', string(outputs('Compose_ExistingLedger')?['QtyAfter']), if(equals(outputs('Compose_ExistingLedger')?['QtyBefore'], null), ' (first count - no previous balance).', concat(' (system had ', string(outputs('Compose_ExistingLedger')?['QtyBefore']), ').'))), if(equals(outputs('Compose_ExistingLedger')?['LedgerType'], 'OPENING'), concat('Opening balance recorded for ', concat(outputs('Compose_ExistingLedger')?['ItemID'], ' @ ', outputs('Compose_ExistingLedger')?['LocationCode']), ': ', string(outputs('Compose_ExistingLedger')?['QtyAfter']), '.'), concat(outputs('Compose_ExistingLedger')?['LedgerType'], ' recorded for ', concat(outputs('Compose_ExistingLedger')?['ItemID'], ' @ ', outputs('Compose_ExistingLedger')?['LocationCode']), '. On hand now ', string(outputs('Compose_ExistingLedger')?['QtyAfter']), '.')))))"
              ```
            - **`Result_already_posted`**
              - Run after: after `Compose_PostedMessage` Succeeded
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Succeeded",
                  "code": "OK",
                  "message": "@outputs('Compose_PostedMessage')",
                  "finalize": "yes",
                  "effect": "Applied",
                  "ledger": "@outputs('Compose_ExistingLedger')?['LedgerKey']",
                  "newOnHand": "@string(outputs('Compose_ExistingLedger')?['QtyAfter'])",
                  "authBy": "@coalesce(outputs('Compose_ExistingLedger')?['AuthorizedByUPN'], '')"
                }
              }
              ```
        - **`If_existing_intent`**
          - Run after: after `If_existing_posted` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(not(equals(outputs('Compose_ExistingLedger'), null)), equals(outputs('Compose_ExistingLedger')?['PostingState'], 'Intent'))", true]}
          ```
          - Inside `If_existing_intent`:
            - **`Set_vIntent_resume`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vIntent",
                "value": "ours"
              }
              ```
    - **`Stage_giveup`**
      - Run after: after `Stage_existing_ledger` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none')), greater(variables('vAttempts'), int(coalesce(outputs('Compose_Settings')?['MaxProcessAttempts'], '5'))))", true]}
      ```
      - Inside `Stage_giveup`:
        - **`Result_gave_up`**
          - Run after: first action
          **Variable > Set variable**
          ```json
          {
            "name": "vRes",
            "value": {
              "outcome": "done",
              "status": "Rejected",
              "code": "GAVE_UP",
              "message": "@coalesce(outputs('Compose_Messages')?['GAVE_UP'], 'GAVE_UP')",
              "finalize": "yes",
              "effect": "NotApplied",
              "ledger": "",
              "newOnHand": "",
              "authBy": ""
            }
          }
          ```
    - **`Stage_context_auth`**
      - Run after: after `Stage_giveup` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none'))", true]}
      ```
      - Inside `Stage_context_auth`:
        - **`Get_session`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUSessions'')/items', '?', '$filter=', 'SessionID eq ''', uriComponent(replace(string(coalesce(outputs('Compose_Req')?['SessionID'], 'NONE')), '''', '''''')), '''', '&', '$select=Id,SessionID,BadgeID,EmployeeName,StationID,AppAccountUPN,LastActivityUtc,SessionState', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_Session`**
          - Run after: after `Get_session` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_session')?['d']?['results'])"
          ```
        - **`Get_session_employee`**
          - Run after: after `Compose_Session` Succeeded
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUEmployees'')/items', '?', '$filter=', 'BadgeID eq ''', uriComponent(replace(string(coalesce(outputs('Compose_Session')?['BadgeID'], 'NONE')), '''', '''''')), '''', '&', '$select=Id,BadgeID,EmployeeName,Active,Role,MicrosoftUPN', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_SessEmp`**
          - Run after: after `Get_session_employee` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_session_employee')?['d']?['results'])"
          ```
        - **`Get_station`**
          - Run after: after `Compose_SessEmp` Succeeded
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUStations'')/items', '?', '$filter=', 'StationID eq ''', uriComponent(replace(string(coalesce(outputs('Compose_Req')?['StationID'], 'NONE')), '''', '''''')), '''', '&', '$select=Id,StationID,Active,ExpectedAccountUPN', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_Station`**
          - Run after: after `Get_station` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_station')?['d']?['results'])"
          ```
        - **`Compose_AuthorEmail`**
          - Run after: after `Compose_Station` Succeeded
          **Data Operation > Compose**
          ```json
          "@toLower(coalesce(outputs('Compose_Req')?['Author']?['EMail'], ''))"
          ```
        - **`Compose_NeedsAuthority`**
          - Run after: after `Compose_AuthorEmail` Succeeded
          **Data Operation > Compose**
          ```json
          "@or(and(equals(outputs('Compose_Req')?['RequestType'], 'AUDIT'), equals(toLower(coalesce(outputs('Compose_Settings')?['RequireSupervisorForAudit'], 'true')), 'true')), and(contains(createArray('ITEM_CREATE', 'LOCATION_ADD'), outputs('Compose_Req')?['RequestType']), equals(toLower(coalesce(outputs('Compose_Settings')?['RequireSupervisorForNewItem'], 'true')), 'true')), equals(outputs('Compose_Req')?['RequestType'], 'PARAM_UPDATE'))"
          ```
        - **`If_privileged_lookup`**
          - Run after: after `Compose_NeedsAuthority` Succeeded
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@not(contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType']))", true]}
          ```
          - Inside `If_privileged_lookup`:
            - **`Get_privileged`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUEmployees'')/items', '?', '$filter=', 'Active eq 1 and Role ne ''Operator''', '&', '$select=Id,BadgeID,EmployeeName,Role,MicrosoftUPN', '&', '$top=200')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`Get_approvals`**
              - Run after: after `Get_privileged` Succeeded
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POURequests'')/items', '?', '$filter=', 'TargetRequestID eq ''', uriComponent(replace(string(outputs('Compose_RequestIdIn')), '''', '''''')), ''' and RequestType eq ''APPROVE''', '&', '$select=Id,Decision,Author/EMail', '&', '$top=10', '&', '$orderby=ID desc', '&', '$expand=Author')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`Filter_priv_with_upn`**
              - Run after: after `Get_approvals` Succeeded
              **Data Operation > Filter array**
              ```json
              {
                "from": "@body('Get_privileged')?['d']?['results']",
                "where": "@not(empty(coalesce(item()?['MicrosoftUPN'], '')))"
              }
              ```
            - **`Select_priv_upns`**
              - Run after: after `Filter_priv_with_upn` Succeeded
              **Data Operation > Select**
              ```json
              {
                "from": "@body('Filter_priv_with_upn')",
                "select": "@toLower(item()?['MicrosoftUPN'])"
              }
              ```
            - **`Filter_author_emp`**
              - Run after: after `Select_priv_upns` Succeeded
              **Data Operation > Filter array**
              ```json
              {
                "from": "@body('Filter_priv_with_upn')",
                "where": "@equals(toLower(item()?['MicrosoftUPN']), outputs('Compose_AuthorEmail'))"
              }
              ```
            - **`Compose_AuthorEmp`**
              - Run after: after `Filter_author_emp` Succeeded
              **Data Operation > Compose**
              ```json
              "@first(body('Filter_author_emp'))"
              ```
            - **`Filter_valid_approvals`**
              - Run after: after `Compose_AuthorEmp` Succeeded
              **Data Operation > Filter array**
              ```json
              {
                "from": "@body('Get_approvals')?['d']?['results']",
                "where": "@and(contains(body('Select_priv_upns'), toLower(coalesce(item()?['Author']?['EMail'], ''))), not(equals(toLower(coalesce(item()?['Author']?['EMail'], '')), outputs('Compose_AuthorEmail'))), not(equals(toLower(coalesce(item()?['Author']?['EMail'], '')), toLower(coalesce(outputs('Compose_SessEmp')?['MicrosoftUPN'], '')))))"
              }
              ```
            - **`Compose_Approval`**
              - Run after: after `Filter_valid_approvals` Succeeded
              **Data Operation > Compose**
              ```json
              "@first(body('Filter_valid_approvals'))"
              ```
            - **`Set_vAuth`**
              - Run after: after `Compose_Approval` Succeeded
              **Variable > Set variable**
              ```json
              {
                "name": "vAuth",
                "value": {
                  "isSup": "@and(not(empty(outputs('Compose_AuthorEmail'))), contains(body('Select_priv_upns'), outputs('Compose_AuthorEmail')))",
                  "isAdmin": "@and(not(empty(outputs('Compose_AuthorEmail'))), equals(coalesce(outputs('Compose_AuthorEmp')?['Role'], ''), 'Admin'))",
                  "name": "@coalesce(outputs('Compose_AuthorEmp')?['EmployeeName'], outputs('Compose_AuthorEmail'))",
                  "decision": "@coalesce(outputs('Compose_Approval')?['Decision'], '')",
                  "approver": "@toLower(coalesce(outputs('Compose_Approval')?['Author']?['EMail'], ''))"
                }
              }
              ```
        - **`Auth_Rules1_type_known_to_station_match`**
          - Run after: after `If_privileged_lookup` Succeeded/Failed/Skipped/TimedOut
          **Data Operation > Compose**
          ```json
          "@if(empty(if(not(contains(createArray('ISSUE', 'RECEIPT', 'AUDIT', 'OPENING', 'ADJUSTMENT', 'REVERSAL', 'ITEM_CREATE', 'LOCATION_ADD', 'PARAM_UPDATE', 'APPROVE'), outputs('Compose_Req')?['RequestType'])), 'UNKNOWN_TYPE', '')), if(empty(if(or(and(contains(createArray('ADJUSTMENT', 'REVERSAL', 'APPROVE'), outputs('Compose_Req')?['RequestType']), not(variables('vAuth')?['isSup'])), and(equals(outputs('Compose_Req')?['RequestType'], 'OPENING'), not(variables('vAuth')?['isAdmin']))), 'NOT_AUTHORIZED', '')), if(empty(if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), equals(outputs('Compose_Session'), null)), 'NO_SESSION', '')), if(empty(if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), not(equals(coalesce(outputs('Compose_Session')?['SessionState'], ''), 'Active'))), 'SESSION_ENDED', '')), if(empty(if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), not(equals(toLower(coalesce(outputs('Compose_Session')?['AppAccountUPN'], '')), outputs('Compose_AuthorEmail')))), 'SESSION_ACCOUNT_MISMATCH', '')), if(empty(if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), greater(sub(ticks(coalesce(outputs('Compose_Req')?['Created'], '2000-01-01T00:00:00Z')), ticks(coalesce(outputs('Compose_Session')?['LastActivityUtc'], outputs('Compose_Req')?['Created'], '2000-01-01T00:00:00Z'))), mul(int(coalesce(outputs('Compose_Settings')?['ServerSessionMaxIdleMinutes'], '10')), 600000000))), 'SESSION_EXPIRED', '')), if(empty(if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), or(equals(outputs('Compose_SessEmp'), null), not(equals(outputs('Compose_SessEmp')?['Active'], true)))), 'EMPLOYEE_INACTIVE', '')), if(empty(if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), or(equals(outputs('Compose_Station'), null), not(equals(outputs('Compose_Station')?['Active'], true)))), 'STATION_INVALID', '')), if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), not(equals(coalesce(outputs('Compose_Session')?['StationID'], ''), coalesce(outputs('Compose_Req')?['StationID'], '')))), 'STATION_MISMATCH', ''), if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), or(equals(outputs('Compose_Station'), null), not(equals(outputs('Compose_Station')?['Active'], true)))), 'STATION_INVALID', '')), if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), or(equals(outputs('Compose_SessEmp'), null), not(equals(outputs('Compose_SessEmp')?['Active'], true)))), 'EMPLOYEE_INACTIVE', '')), if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), greater(sub(ticks(coalesce(outputs('Compose_Req')?['Created'], '2000-01-01T00:00:00Z')), ticks(coalesce(outputs('Compose_Session')?['LastActivityUtc'], outputs('Compose_Req')?['Created'], '2000-01-01T00:00:00Z'))), mul(int(coalesce(outputs('Compose_Settings')?['ServerSessionMaxIdleMinutes'], '10')), 600000000))), 'SESSION_EXPIRED', '')), if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), not(equals(toLower(coalesce(outputs('Compose_Session')?['AppAccountUPN'], '')), outputs('Compose_AuthorEmail')))), 'SESSION_ACCOUNT_MISMATCH', '')), if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), not(equals(coalesce(outputs('Compose_Session')?['SessionState'], ''), 'Active'))), 'SESSION_ENDED', '')), if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), equals(outputs('Compose_Session'), null)), 'NO_SESSION', '')), if(or(and(contains(createArray('ADJUSTMENT', 'REVERSAL', 'APPROVE'), outputs('Compose_Req')?['RequestType']), not(variables('vAuth')?['isSup'])), and(equals(outputs('Compose_Req')?['RequestType'], 'OPENING'), not(variables('vAuth')?['isAdmin']))), 'NOT_AUTHORIZED', '')), if(not(contains(createArray('ISSUE', 'RECEIPT', 'AUDIT', 'OPENING', 'ADJUSTMENT', 'REVERSAL', 'ITEM_CREATE', 'LOCATION_ADD', 'PARAM_UPDATE', 'APPROVE'), outputs('Compose_Req')?['RequestType'])), 'UNKNOWN_TYPE', ''))"
          ```
        - **`Auth_Rules2_station_account_to_supervisor_rejected`**
          - Run after: after `Auth_Rules1_type_known_to_station_match` Succeeded
          **Data Operation > Compose**
          ```json
          "@if(empty(if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), not(empty(coalesce(outputs('Compose_Station')?['ExpectedAccountUPN'], ''))), not(equals(toLower(coalesce(outputs('Compose_Station')?['ExpectedAccountUPN'], '')), outputs('Compose_AuthorEmail')))), 'STATION_ACCOUNT_MISMATCH', '')), if(and(outputs('Compose_NeedsAuthority'), not(variables('vAuth')?['isSup']), equals(variables('vAuth')?['decision'], 'Reject')), 'SUPERVISOR_REJECTED', ''), if(and(or(not(variables('vAuth')?['isSup']), contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType'])), not(empty(coalesce(outputs('Compose_Station')?['ExpectedAccountUPN'], ''))), not(equals(toLower(coalesce(outputs('Compose_Station')?['ExpectedAccountUPN'], '')), outputs('Compose_AuthorEmail')))), 'STATION_ACCOUNT_MISMATCH', ''))"
          ```
        - **`Auth_Result`**
          - Run after: after `Auth_Rules2_station_account_to_supervisor_rejected` Succeeded
          **Data Operation > Compose**
          ```json
          "@if(empty(outputs('Auth_Rules1_type_known_to_station_match')), outputs('Auth_Rules2_station_account_to_supervisor_rejected'), outputs('Auth_Rules1_type_known_to_station_match'))"
          ```
        - **`Compose_AuthBy`**
          - Run after: after `Auth_Result` Succeeded
          **Data Operation > Compose**
          ```json
          "@if(variables('vAuth')?['isSup'], outputs('Compose_AuthorEmail'), if(equals(variables('vAuth')?['decision'], 'Approve'), variables('vAuth')?['approver'], ''))"
          ```
        - **`Compose_Actor`**
          - Run after: after `Compose_AuthBy` Succeeded
          **Data Operation > Compose**
          ```json
          {
            "badge": "@if(variables('vAuth')?['isSup'], '', coalesce(outputs('Compose_Session')?['BadgeID'], ''))",
            "name": "@if(variables('vAuth')?['isSup'], variables('vAuth')?['name'], coalesce(outputs('Compose_Session')?['EmployeeName'], ''))"
          }
          ```
        - **`Set_vSessionItem`**
          - Run after: after `Compose_Actor` Succeeded
          **Variable > Set variable**
          ```json
          {
            "name": "vSessionItem",
            "value": "@string(coalesce(outputs('Compose_Session')?['Id'], ''))"
          }
          ```
        - **`If_reject_auth`**
          - Run after: after `Set_vSessionItem` Succeeded
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@not(empty(outputs('Auth_Result')))", true]}
          ```
          - Inside `If_reject_auth`:
            - **`Result_auth_reject`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Rejected",
                  "code": "@outputs('Auth_Result')",
                  "message": "@coalesce(outputs('Compose_Messages')?[outputs('Auth_Result')], outputs('Auth_Result'))",
                  "finalize": "yes",
                  "effect": "NotApplied",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": ""
                }
              }
              ```
        - **`If_await_supervisor`**
          - Run after: after `If_reject_auth` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), outputs('Compose_NeedsAuthority'), not(variables('vAuth')?['isSup']), not(equals(variables('vAuth')?['decision'], 'Approve')))", true]}
          ```
          - Inside `If_await_supervisor`:
            - **`Result_await`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "AwaitingSupervisor",
                  "code": "NEEDS_SUPERVISOR",
                  "message": "Waiting for a supervisor to approve. They approve from their own device; nothing has been changed yet.",
                  "finalize": "yes",
                  "effect": "NotApplied",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": ""
                }
              }
              ```
    - **`Dispatch_quantity`**
      - Run after: after `Stage_context_auth` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none')), contains(createArray('ISSUE', 'RECEIPT', 'AUDIT', 'OPENING', 'ADJUSTMENT', 'REVERSAL'), outputs('Compose_Req')?['RequestType']))", true]}
      ```
      - Inside `Dispatch_quantity`:
        - **`Post_init`**
          - Run after: first action
          **Control > Scope**
          - Inside `Post_init`:
            - **`Post_init_vAttempt`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vAttempt",
                "value": 0
              }
              ```
        - **`Until_intent`**
          - Run after: after `Post_init` Succeeded/Failed/Skipped/TimedOut
          **Control > Do until**  limit count 6, timeout PT1H
          - Condition: `@or(equals(variables('vRes')?['outcome'], 'done'), equals(variables('vIntent'), 'ours'), greaterOrEquals(variables('vAttempt'), 4))`
          - Inside `Until_intent`:
            - **`Loop_inc_attempt`**
              - Run after: first action
              **Variable > Increment variable**
              ```json
              {
                "name": "vAttempt",
                "value": 1
              }
              ```
            - **`Get_stock`**
              - Run after: after `Loop_inc_attempt` Succeeded
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items', '?', '$filter=', 'StockKey eq ''', uriComponent(replace(string(coalesce(outputs('Compose_Req')?['StockKey'], 'NONE')), '''', '''''')), '''', '&', '$select=Id,StockKey,ItemID,LocationCode,ItemName,Area,MinQty,MaxQty,OnHandQty,StockVersion,BalanceStatus,LowStockFlag,Active,LastLedgerKey,LastCountedUtc,CreatedViaRequestID', '&', '$top=2')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`Compose_Stock`**
              - Run after: after `Get_stock` Succeeded
              **Data Operation > Compose**
              ```json
              "@first(body('Get_stock')?['d']?['results'])"
              ```
            - **`If_stock_missing`**
              - Run after: after `Compose_Stock` Succeeded
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@and(and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none')), equals(outputs('Compose_Stock'), null))", true]}
              ```
              - Inside `If_stock_missing`:
                - **`Result_stock_missing`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vRes",
                    "value": {
                      "outcome": "done",
                      "status": "Rejected",
                      "code": "STOCK_NOT_FOUND",
                      "message": "@coalesce(outputs('Compose_Messages')?['STOCK_NOT_FOUND'], 'STOCK_NOT_FOUND')",
                      "finalize": "yes",
                      "effect": "NotApplied",
                      "ledger": "",
                      "newOnHand": "",
                      "authBy": ""
                    }
                  }
                  ```
            - **`If_reversal_lookup`**
              - Run after: after `If_stock_missing` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@and(and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none')), equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'))", true]}
              ```
              - Inside `If_reversal_lookup`:
                - **`Get_original_ledger`**
                  - Run after: first action
                  **SharePoint > Send an HTTP request to SharePoint**  `GET`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items', '?', '$filter=', 'LedgerKey eq ''', uriComponent(replace(string(coalesce(outputs('Compose_Req')?['ReversesLedgerKey'], 'NONE')), '''', '''''')), '''', '&', '$select=Id,LedgerKey,RequestID,LedgerType,PostingState,StockKey,ItemID,LocationCode,SeqNo,QtyDelta,QtyBefore,QtyAfter,AffectsBalance,ReversesLedgerKey,OccurredUtc,BadgeID,EmployeeName,Origin', '&', '$top=2')`
                  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
                - **`Get_reversal_existing`**
                  - Run after: after `Get_original_ledger` Succeeded
                  **SharePoint > Send an HTTP request to SharePoint**  `GET`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items', '?', '$filter=', 'ReversesLedgerKey eq ''', uriComponent(replace(string(coalesce(outputs('Compose_Req')?['ReversesLedgerKey'], 'NONE')), '''', '''''')), ''' and PostingState ne ''Voided''', '&', '$select=Id,LedgerKey,PostingState', '&', '$top=2')`
                  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
                - **`Set_vRev`**
                  - Run after: after `Get_reversal_existing` Succeeded
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vRev",
                    "value": {
                      "orig": "@first(body('Get_original_ledger')?['d']?['results'])",
                      "existing": "@not(empty(body('Get_reversal_existing')?['d']?['results']))"
                    }
                  }
                  ```
            - **`Post_Rules1_stock_active_to_rev_target`**
              - Run after: after `If_reversal_lookup` Succeeded/Failed/Skipped/TimedOut
              **Data Operation > Compose**
              ```json
              "@if(empty(if(not(equals(outputs('Compose_Stock')?['Active'], true)), 'STOCK_INACTIVE', '')), if(empty(if(and(contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType']), or(not(and(not(equals(outputs('Compose_Req')?['Quantity'], null)), equals(mod(coalesce(outputs('Compose_Req')?['Quantity'], 0), 1), 0))), less(coalesce(outputs('Compose_Req')?['Quantity'], 0), 1))), 'INVALID_QUANTITY', '')), if(empty(if(and(contains(createArray('AUDIT', 'OPENING', 'ADJUSTMENT'), outputs('Compose_Req')?['RequestType']), or(not(and(not(equals(outputs('Compose_Req')?['Quantity'], null)), equals(mod(coalesce(outputs('Compose_Req')?['Quantity'], 0), 1), 0))), less(coalesce(outputs('Compose_Req')?['Quantity'], 0), 0))), 'INVALID_COUNT', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'RECEIPT'), greater(coalesce(outputs('Compose_Req')?['Quantity'], 0), int(coalesce(outputs('Compose_Settings')?['MaxAddQty'], '500')))), 'QUANTITY_OVER_LIMIT', '')), if(empty(if(and(contains(createArray('ISSUE', 'RECEIPT', 'ADJUSTMENT', 'REVERSAL'), outputs('Compose_Req')?['RequestType']), equals(outputs('Compose_Stock')?['OnHandQty'], null)), 'NO_BALANCE', '')), if(empty(if(and(contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType']), not(equals(toLower(coalesce(outputs('Compose_Settings')?['AllowIssueAgainstUnverified'], 'true')), 'true')), not(equals(outputs('Compose_Stock')?['BalanceStatus'], 'Verified'))), 'BALANCE_UNVERIFIED', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'ISSUE'), greater(coalesce(outputs('Compose_Req')?['Quantity'], 0), coalesce(outputs('Compose_Stock')?['OnHandQty'], 0))), 'INSUFFICIENT_STOCK', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'AUDIT'), equals(outputs('Compose_Req')?['ExpectedVersion'], null)), 'MISSING_EXPECTED_VERSION', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'AUDIT'), not(equals(outputs('Compose_Req')?['ExpectedVersion'], null)), not(equals(coalesce(outputs('Compose_Req')?['ExpectedVersion'], 0), coalesce(outputs('Compose_Stock')?['StockVersion'], 0)))), 'STALE_COUNT', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'OPENING'), not(and(equals(outputs('Compose_Stock')?['OnHandQty'], null), equals(coalesce(outputs('Compose_Stock')?['StockVersion'], 0), 0)))), 'OPENING_NOT_ALLOWED', '')), if(empty(if(and(contains(createArray('ADJUSTMENT', 'REVERSAL'), outputs('Compose_Req')?['RequestType']), empty(trim(coalesce(outputs('Compose_Req')?['Reason'], '')))), 'REASON_REQUIRED', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), equals(variables('vRev')?['orig'], null)), 'REVERSAL_TARGET_MISSING', ''), if(and(contains(createArray('ADJUSTMENT', 'REVERSAL'), outputs('Compose_Req')?['RequestType']), empty(trim(coalesce(outputs('Compose_Req')?['Reason'], '')))), 'REASON_REQUIRED', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'OPENING'), not(and(equals(outputs('Compose_Stock')?['OnHandQty'], null), equals(coalesce(outputs('Compose_Stock')?['StockVersion'], 0), 0)))), 'OPENING_NOT_ALLOWED', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'AUDIT'), not(equals(outputs('Compose_Req')?['ExpectedVersion'], null)), not(equals(coalesce(outputs('Compose_Req')?['ExpectedVersion'], 0), coalesce(outputs('Compose_Stock')?['StockVersion'], 0)))), 'STALE_COUNT', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'AUDIT'), equals(outputs('Compose_Req')?['ExpectedVersion'], null)), 'MISSING_EXPECTED_VERSION', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'ISSUE'), greater(coalesce(outputs('Compose_Req')?['Quantity'], 0), coalesce(outputs('Compose_Stock')?['OnHandQty'], 0))), 'INSUFFICIENT_STOCK', '')), if(and(contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType']), not(equals(toLower(coalesce(outputs('Compose_Settings')?['AllowIssueAgainstUnverified'], 'true')), 'true')), not(equals(outputs('Compose_Stock')?['BalanceStatus'], 'Verified'))), 'BALANCE_UNVERIFIED', '')), if(and(contains(createArray('ISSUE', 'RECEIPT', 'ADJUSTMENT', 'REVERSAL'), outputs('Compose_Req')?['RequestType']), equals(outputs('Compose_Stock')?['OnHandQty'], null)), 'NO_BALANCE', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'RECEIPT'), greater(coalesce(outputs('Compose_Req')?['Quantity'], 0), int(coalesce(outputs('Compose_Settings')?['MaxAddQty'], '500')))), 'QUANTITY_OVER_LIMIT', '')), if(and(contains(createArray('AUDIT', 'OPENING', 'ADJUSTMENT'), outputs('Compose_Req')?['RequestType']), or(not(and(not(equals(outputs('Compose_Req')?['Quantity'], null)), equals(mod(coalesce(outputs('Compose_Req')?['Quantity'], 0), 1), 0))), less(coalesce(outputs('Compose_Req')?['Quantity'], 0), 0))), 'INVALID_COUNT', '')), if(and(contains(createArray('ISSUE', 'RECEIPT'), outputs('Compose_Req')?['RequestType']), or(not(and(not(equals(outputs('Compose_Req')?['Quantity'], null)), equals(mod(coalesce(outputs('Compose_Req')?['Quantity'], 0), 1), 0))), less(coalesce(outputs('Compose_Req')?['Quantity'], 0), 1))), 'INVALID_QUANTITY', '')), if(not(equals(outputs('Compose_Stock')?['Active'], true)), 'STOCK_INACTIVE', ''))"
              ```
            - **`Post_Rules2_rev_posted_to_rev_non_negative`**
              - Run after: after `Post_Rules1_stock_active_to_rev_target` Succeeded
              **Data Operation > Compose**
              ```json
              "@if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), not(equals(variables('vRev')?['orig'], null)), or(not(equals(variables('vRev')?['orig']?['PostingState'], 'Posted')), not(equals(variables('vRev')?['orig']?['AffectsBalance'], true)), not(contains(createArray('ISSUE', 'RECEIPT'), variables('vRev')?['orig']?['LedgerType'])))), 'REVERSAL_NOT_POSTED', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), not(equals(variables('vRev')?['orig'], null)), not(equals(coalesce(variables('vRev')?['orig']?['StockKey'], ''), coalesce(outputs('Compose_Req')?['StockKey'], '')))), 'REVERSAL_WRONG_STOCK', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), equals(variables('vRev')?['existing'], true)), 'REVERSAL_ALREADY', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), not(equals(variables('vRev')?['orig'], null)), not(equals(outputs('Compose_Stock')?['OnHandQty'], null)), less(sub(coalesce(outputs('Compose_Stock')?['OnHandQty'], 0), coalesce(variables('vRev')?['orig']?['QtyDelta'], 0)), 0)), 'REVERSAL_NEGATIVE', ''), if(and(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), equals(variables('vRev')?['existing'], true)), 'REVERSAL_ALREADY', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), not(equals(variables('vRev')?['orig'], null)), not(equals(coalesce(variables('vRev')?['orig']?['StockKey'], ''), coalesce(outputs('Compose_Req')?['StockKey'], '')))), 'REVERSAL_WRONG_STOCK', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), not(equals(variables('vRev')?['orig'], null)), or(not(equals(variables('vRev')?['orig']?['PostingState'], 'Posted')), not(equals(variables('vRev')?['orig']?['AffectsBalance'], true)), not(contains(createArray('ISSUE', 'RECEIPT'), variables('vRev')?['orig']?['LedgerType'])))), 'REVERSAL_NOT_POSTED', ''))"
              ```
            - **`Post_Result`**
              - Run after: after `Post_Rules2_rev_posted_to_rev_non_negative` Succeeded
              **Data Operation > Compose**
              ```json
              "@if(empty(outputs('Post_Rules1_stock_active_to_rev_target')), outputs('Post_Rules2_rev_posted_to_rev_non_negative'), outputs('Post_Rules1_stock_active_to_rev_target'))"
              ```
            - **`If_post_reject`**
              - Run after: after `Post_Result` Succeeded
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@and(and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none')), not(empty(outputs('Post_Result'))))", true]}
              ```
              - Inside `If_post_reject`:
                - **`Result_post_reject`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vRes",
                    "value": {
                      "outcome": "done",
                      "status": "Rejected",
                      "code": "@outputs('Post_Result')",
                      "message": "@if(equals(outputs('Post_Result'), 'INSUFFICIENT_STOCK'), concat('Only ', string(coalesce(outputs('Compose_Stock')?['OnHandQty'], 0)), ' on hand - cannot remove ', string(coalesce(outputs('Compose_Req')?['Quantity'], 0)), '. Nothing was changed.'), if(equals(outputs('Post_Result'), 'QUANTITY_OVER_LIMIT'), concat('Quantity ', string(coalesce(outputs('Compose_Req')?['Quantity'], 0)), ' is over the limit of ', string(int(coalesce(outputs('Compose_Settings')?['MaxAddQty'], '500'))), ' for one ADD - was a part number scanned into Quantity? Nothing was changed.'), if(equals(outputs('Post_Result'), 'STALE_COUNT'), concat('Stock changed since you started counting (it is now version ', string(coalesce(outputs('Compose_Stock')?['StockVersion'], 0)), ', on hand ', string(coalesce(outputs('Compose_Stock')?['OnHandQty'], 0)), '). Recount. Nothing was changed.'), coalesce(outputs('Compose_Messages')?[outputs('Post_Result')], outputs('Post_Result')))))",
                      "finalize": "yes",
                      "effect": "NotApplied",
                      "ledger": "",
                      "newOnHand": "",
                      "authBy": ""
                    }
                  }
                  ```
            - **`If_plan_ok`**
              - Run after: after `If_post_reject` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@and(and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none')), equals(outputs('Post_Result'), ''))", true]}
              ```
              - Inside `If_plan_ok`:
                - **`Compose_Plan`**
                  - Run after: first action
                  **Data Operation > Compose**
                  ```json
                  {
                    "seq": "@add(coalesce(outputs('Compose_Stock')?['StockVersion'], 0), 1)",
                    "before": "@outputs('Compose_Stock')?['OnHandQty']",
                    "after": "@int(if(equals(outputs('Compose_Req')?['RequestType'], 'ISSUE'), sub(outputs('Compose_Stock')?['OnHandQty'], outputs('Compose_Req')?['Quantity']), if(equals(outputs('Compose_Req')?['RequestType'], 'RECEIPT'), add(outputs('Compose_Stock')?['OnHandQty'], outputs('Compose_Req')?['Quantity']), if(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), sub(coalesce(outputs('Compose_Stock')?['OnHandQty'], 0), coalesce(variables('vRev')?['orig']?['QtyDelta'], 0)), outputs('Compose_Req')?['Quantity']))))",
                    "delta": "@if(equals(if(equals(outputs('Compose_Req')?['RequestType'], 'ISSUE'), sub(0, outputs('Compose_Req')?['Quantity']), if(equals(outputs('Compose_Req')?['RequestType'], 'RECEIPT'), outputs('Compose_Req')?['Quantity'], if(equals(outputs('Compose_Req')?['RequestType'], 'OPENING'), null, if(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), sub(0, coalesce(variables('vRev')?['orig']?['QtyDelta'], 0)), if(equals(outputs('Compose_Stock')?['OnHandQty'], null), null, sub(outputs('Compose_Req')?['Quantity'], outputs('Compose_Stock')?['OnHandQty'])))))), null), null, int(if(equals(outputs('Compose_Req')?['RequestType'], 'ISSUE'), sub(0, outputs('Compose_Req')?['Quantity']), if(equals(outputs('Compose_Req')?['RequestType'], 'RECEIPT'), outputs('Compose_Req')?['Quantity'], if(equals(outputs('Compose_Req')?['RequestType'], 'OPENING'), null, if(equals(outputs('Compose_Req')?['RequestType'], 'REVERSAL'), sub(0, coalesce(variables('vRev')?['orig']?['QtyDelta'], 0)), if(equals(outputs('Compose_Stock')?['OnHandQty'], null), null, sub(outputs('Compose_Req')?['Quantity'], outputs('Compose_Stock')?['OnHandQty']))))))))"
                  }
                  ```
                - **`Get_prev_ledger`**
                  - Run after: after `Compose_Plan` Succeeded
                  **SharePoint > Send an HTTP request to SharePoint**  `GET`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items', '?', '$filter=', 'LedgerKey eq ''', uriComponent(replace(string(if(greater(coalesce(outputs('Compose_Stock')?['StockVersion'], 0), 0), concat(outputs('Compose_Stock')?['StockKey'], '#', string(coalesce(outputs('Compose_Stock')?['StockVersion'], 0))), 'NONE')), '''', '''''')), '''', '&', '$select=Id,LedgerKey,RequestID,LedgerType,PostingState,StockKey,ItemID,LocationCode,SeqNo,QtyDelta,QtyBefore,QtyAfter,AffectsBalance,ReversesLedgerKey,OccurredUtc,BadgeID,EmployeeName,Origin', '&', '$top=2')`
                  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
                - **`Compose_Prev`**
                  - Run after: after `Get_prev_ledger` Succeeded
                  **Data Operation > Compose**
                  ```json
                  "@first(body('Get_prev_ledger')?['d']?['results'])"
                  ```
                - **`Compose_ChainBad`**
                  - Run after: after `Compose_Prev` Succeeded
                  **Data Operation > Compose**
                  ```json
                  "@if(equals(coalesce(outputs('Compose_Stock')?['StockVersion'], 0), 0), not(equals(outputs('Compose_Stock')?['OnHandQty'], null)), or(equals(outputs('Compose_Prev'), null), not(contains(createArray('Posted', 'Intent'), outputs('Compose_Prev')?['PostingState'])), not(equals(outputs('Compose_Prev')?['QtyAfter'], outputs('Compose_Stock')?['OnHandQty']))))"
                  ```
                - **`If_chain_bad`**
                  - Run after: after `Compose_ChainBad` Succeeded
                  **Control > Condition**  (advanced mode)
                  ```json
                  {"equals": ["@equals(outputs('Compose_ChainBad'), true)", true]}
                  ```
                  - Inside `If_chain_bad`:
                    - **`Drift_Ops_event`**
                      - Run after: first action
                      **Control > Scope**
                      - Inside `Drift_Ops_event`:
                        - **`Drift_Get_event`**
                          - Run after: first action
                          **SharePoint > Send an HTTP request to SharePoint**  `GET`
                          - Site Address: `@outputs('Cfg_SiteUrl')`
                          - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items', '?', '$filter=', 'EventKey eq ''', uriComponent(replace(string(concat('DRIFT|', outputs('Compose_Stock')?['StockKey'])), '''', '''''')), '''', '&', '$select=Id,OccurrenceCount', '&', '$top=2')`
                          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
                        - **`Drift_Event_row`**
                          - Run after: after `Drift_Get_event` Succeeded
                          **Data Operation > Compose**
                          ```json
                          "@first(body('Drift_Get_event')?['d']?['results'])"
                          ```
                        - **`Drift_Event_exists`**
                          - Run after: after `Drift_Event_row` Succeeded
                          **Control > Condition**  (advanced mode)
                          ```json
                          {"equals": ["@not(equals(outputs('Drift_Event_row'), null))", true]}
                          ```
                          - Inside `Drift_Event_exists`:
                            - **`Drift_Update_event`**
                              - Run after: first action
                              **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
                              - Site Address: `@outputs('Cfg_SiteUrl')`
                              - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items(', outputs('Drift_Event_row')?['Id'], ')')`
                              - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
                              - Body:
                              ```json
                              {
                                "__metadata": {
                                  "type": "SP.Data.POUOpsEventsListItem"
                                },
                                "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                                "OccurrenceCount": "@add(int(coalesce(outputs('Drift_Event_row')?['OccurrenceCount'], 1)), 1)",
                                "Details": "@concat('StockKey ', outputs('Compose_Stock')?['StockKey'], ' has OnHandQty=', string(outputs('Compose_Stock')?['OnHandQty']), ' version ', string(coalesce(outputs('Compose_Stock')?['StockVersion'], 0)), ' but the ledger row for that version is missing or disagrees. Posting is blocked for this record until reconciled. Request ', outputs('Compose_RequestIdIn'), '.')",
                                "Resolved": false
                              }
                              ```
                          - If NO (else) in `Drift_Event_exists`:
                            - **`Drift_Create_event`**
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
                                "Title": "@concat('Balance does not match ledger: ', outputs('Compose_Stock')?['StockKey'])",
                                "EventKey": "@concat('DRIFT|', outputs('Compose_Stock')?['StockKey'])",
                                "EventType": "DRIFT",
                                "Severity": "Critical",
                                "Subject": "@concat('Balance does not match ledger: ', outputs('Compose_Stock')?['StockKey'])",
                                "Details": "@concat('StockKey ', outputs('Compose_Stock')?['StockKey'], ' has OnHandQty=', string(outputs('Compose_Stock')?['OnHandQty']), ' version ', string(coalesce(outputs('Compose_Stock')?['StockVersion'], 0)), ' but the ledger row for that version is missing or disagrees. Posting is blocked for this record until reconciled. Request ', outputs('Compose_RequestIdIn'), '.')",
                                "FirstSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                                "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                                "OccurrenceCount": 1,
                                "Resolved": false
                              }
                              ```
                    - **`Result_drift`**
                      - Run after: after `Drift_Ops_event` Succeeded/Failed/Skipped/TimedOut
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vRes",
                        "value": {
                          "outcome": "done",
                          "status": "Failed",
                          "code": "DRIFT_DETECTED",
                          "message": "@coalesce(outputs('Compose_Messages')?['DRIFT_DETECTED'], 'DRIFT_DETECTED')",
                          "finalize": "yes",
                          "effect": "NotApplied",
                          "ledger": "",
                          "newOnHand": "",
                          "authBy": ""
                        }
                      }
                      ```
                - **`If_create_intent`**
                  - Run after: after `If_chain_bad` Succeeded/Failed/Skipped/TimedOut
                  **Control > Condition**  (advanced mode)
                  ```json
                  {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none'))", true]}
                  ```
                  - Inside `If_create_intent`:
                    - **`Create_intent`**
                      - Run after: first action
                      **SharePoint > Send an HTTP request to SharePoint**  `POST`
                      - Site Address: `@outputs('Cfg_SiteUrl')`
                      - Uri: `/_api/web/lists/getbytitle('POULedger')/items`
                      - Headers: `{"Content-Type": "application/json;odata=verbose"}`  (+ Accept: application/json;odata=verbose)
                      - Body:
                      ```json
                      {
                        "__metadata": {
                          "type": "SP.Data.POULedgerListItem"
                        },
                        "Title": "@concat(outputs('Compose_Stock')?['StockKey'], ' #', string(outputs('Compose_Plan')?['seq']))",
                        "LedgerKey": "@concat(outputs('Compose_Stock')?['StockKey'], '#', string(outputs('Compose_Plan')?['seq']))",
                        "RequestID": "@outputs('Compose_RequestIdIn')",
                        "LedgerType": "@outputs('Compose_Req')?['RequestType']",
                        "Origin": "Live",
                        "AffectsBalance": true,
                        "PostingState": "Intent",
                        "StockKey": "@outputs('Compose_Stock')?['StockKey']",
                        "ItemID": "@outputs('Compose_Stock')?['ItemID']",
                        "LocationCode": "@outputs('Compose_Stock')?['LocationCode']",
                        "SeqNo": "@outputs('Compose_Plan')?['seq']",
                        "QtyDelta": "@outputs('Compose_Plan')?['delta']",
                        "QtyBefore": "@outputs('Compose_Plan')?['before']",
                        "QtyAfter": "@outputs('Compose_Plan')?['after']",
                        "BadgeID": "@outputs('Compose_Actor')?['badge']",
                        "EmployeeName": "@outputs('Compose_Actor')?['name']",
                        "StationID": "@coalesce(outputs('Compose_Req')?['StationID'], '')",
                        "AuthorizedByUPN": "@outputs('Compose_AuthBy')",
                        "OccurredUtc": "@coalesce(outputs('Compose_Req')?['Created'], utcNow('yyyy-MM-ddTHH:mm:ssZ'))",
                        "OccurredLocalText": "@convertFromUtc(coalesce(outputs('Compose_Req')?['Created'], utcNow('yyyy-MM-ddTHH:mm:ssZ')), coalesce(outputs('Compose_Settings')?['DisplayTimeZoneWindows'], 'Central Standard Time'), 'yyyy-MM-dd HH:mm:ss')",
                        "Reason": "@coalesce(outputs('Compose_Req')?['Reason'], '')",
                        "ReversesLedgerKey": "@coalesce(outputs('Compose_Req')?['ReversesLedgerKey'], '')"
                      }
                      ```
                    - **`If_intent_created`**
                      - Run after: after `Create_intent` Succeeded/Failed/Skipped/TimedOut
                      **Control > Condition**  (advanced mode)
                      ```json
                      {"equals": ["@equals(actions('Create_intent')?['status'], 'Succeeded')", true]}
                      ```
                      - Inside `If_intent_created`:
                        - **`Set_intent_ours`**
                          - Run after: first action
                          **Control > Scope**
                          - Inside `Set_intent_ours`:
                            - **`Set_intent_ours_vIntent`**
                              - Run after: first action
                              **Variable > Set variable**
                              ```json
                              {
                                "name": "vIntent",
                                "value": "ours"
                              }
                              ```
                            - **`Set_intent_ours_vSeq`**
                              - Run after: after `Set_intent_ours_vIntent` Succeeded
                              **Variable > Set variable**
                              ```json
                              {
                                "name": "vSeq",
                                "value": "@outputs('Compose_Plan')?['seq']"
                              }
                              ```
                      - If NO (else) in `If_intent_created`:
                        - **`Get_ledger_after_create`**
                          - Run after: first action
                          **SharePoint > Send an HTTP request to SharePoint**  `GET`
                          - Site Address: `@outputs('Cfg_SiteUrl')`
                          - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items', '?', '$filter=', 'RequestID eq ''', uriComponent(replace(string(outputs('Compose_RequestIdIn')), '''', '''''')), '''', '&', '$select=Id,LedgerKey,RequestID,LedgerType,PostingState,StockKey,ItemID,LocationCode,SeqNo,QtyDelta,QtyBefore,QtyAfter,AffectsBalance,ReversesLedgerKey,OccurredUtc,BadgeID,EmployeeName,Origin', '&', '$top=2')`
                          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
                        - **`Compose_AfterCreate`**
                          - Run after: after `Get_ledger_after_create` Succeeded
                          **Data Operation > Compose**
                          ```json
                          "@first(body('Get_ledger_after_create')?['d']?['results'])"
                          ```
                        - **`If_ours_after_failed_create`**
                          - Run after: after `Compose_AfterCreate` Succeeded
                          **Control > Condition**  (advanced mode)
                          ```json
                          {"equals": ["@not(equals(outputs('Compose_AfterCreate'), null))", true]}
                          ```
                          - Inside `If_ours_after_failed_create`:
                            - **`Set_vIntent_after_create`**
                              - Run after: first action
                              **Variable > Set variable**
                              ```json
                              {
                                "name": "vIntent",
                                "value": "ours"
                              }
                              ```
                          - If NO (else) in `If_ours_after_failed_create`:
                            - **`Wait_for_contention`**
                              - Run after: first action
                              **Schedule > Delay**
                              ```json
                              {
                                "interval": {
                                  "count": 2,
                                  "unit": "Second"
                                }
                              }
                              ```
        - **`If_contention_exhausted`**
          - Run after: after `Until_intent` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none'))", true]}
          ```
          - Inside `If_contention_exhausted`:
            - **`Result_contention`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Pending",
                  "code": "CONTENTION",
                  "message": "Busy - another transaction on this item is finishing. It will be retried automatically; do not repeat it.",
                  "finalize": "yes",
                  "effect": "",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": ""
                }
              }
              ```
    - **`Dispatch_master`**
      - Run after: after `Dispatch_quantity` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none')), contains(createArray('ITEM_CREATE', 'LOCATION_ADD'), outputs('Compose_Req')?['RequestType']))", true]}
      ```
      - Inside `Dispatch_master`:
        - **`Compose_Payload`**
          - Run after: first action
          **Data Operation > Compose**
          ```json
          "@json(coalesce(outputs('Compose_Req')?['PayloadJson'], '{}'))"
          ```
        - **`Compose_MItem`**
          - Run after: after `Compose_Payload` Succeeded
          **Data Operation > Compose**
          ```json
          "@toUpper(trim(replace(string(coalesce(outputs('Compose_Payload')?['ItemID'], '')), '*', '')))"
          ```
        - **`Compose_MLocIn`**
          - Run after: after `Compose_MItem` Succeeded
          **Data Operation > Compose**
          ```json
          "@trim(string(coalesce(outputs('Compose_Payload')?['LocationCode'], '')))"
          ```
        - **`Get_m_location`**
          - Run after: after `Compose_MLocIn` Succeeded
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POULocations'')/items', '?', '$filter=', 'LocationCode eq ''', uriComponent(replace(string(coalesce(outputs('Compose_MLocIn'), 'NONE')), '''', '''''')), '''', '&', '$select=Id,LocationCode,Active', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_MLoc`**
          - Run after: after `Get_m_location` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_m_location')?['d']?['results'])"
          ```
        - **`Compose_MStockKey`**
          - Run after: after `Compose_MLoc` Succeeded
          **Data Operation > Compose**
          ```json
          "@concat(outputs('Compose_MItem'), '|', toUpper(coalesce(outputs('Compose_MLoc')?['LocationCode'], '')))"
          ```
        - **`Get_m_item`**
          - Run after: after `Compose_MStockKey` Succeeded
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUItems'')/items', '?', '$filter=', 'ItemID eq ''', uriComponent(replace(string(coalesce(outputs('Compose_MItem'), 'NONE')), '''', '''''')), '''', '&', '$select=Id,ItemID,ItemName,CreatedViaRequestID', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_MItemRow`**
          - Run after: after `Get_m_item` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_m_item')?['d']?['results'])"
          ```
        - **`Get_m_stock`**
          - Run after: after `Compose_MItemRow` Succeeded
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items', '?', '$filter=', 'StockKey eq ''', uriComponent(replace(string(outputs('Compose_MStockKey')), '''', '''''')), '''', '&', '$select=Id,StockKey,ItemID,LocationCode,ItemName,Area,MinQty,MaxQty,OnHandQty,StockVersion,BalanceStatus,LowStockFlag,Active,LastLedgerKey,LastCountedUtc,CreatedViaRequestID', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_MStockRow`**
          - Run after: after `Get_m_stock` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_m_stock')?['d']?['results'])"
          ```
        - **`Master_Rules1_item_id_valid_to_stock_new`**
          - Run after: after `Compose_MStockRow` Succeeded
          **Data Operation > Compose**
          ```json
          "@if(empty(if(or(empty(outputs('Compose_MItem')), contains(outputs('Compose_MItem'), '|'), contains(outputs('Compose_MItem'), ' ')), 'PAYLOAD_INVALID', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'ITEM_CREATE'), empty(trim(string(coalesce(outputs('Compose_Payload')?['ItemName'], ''))))), 'PAYLOAD_INVALID', '')), if(empty(if(or(not(and(not(equals(outputs('Compose_Payload')?['MinQty'], null)), equals(mod(coalesce(outputs('Compose_Payload')?['MinQty'], 0), 1), 0))), not(and(not(equals(outputs('Compose_Payload')?['MaxQty'], null)), equals(mod(coalesce(outputs('Compose_Payload')?['MaxQty'], 0), 1), 0))), less(coalesce(outputs('Compose_Payload')?['MinQty'], 0), 0), greater(coalesce(outputs('Compose_Payload')?['MinQty'], 0), coalesce(outputs('Compose_Payload')?['MaxQty'], 0))), 'PAYLOAD_INVALID', '')), if(empty(if(or(equals(outputs('Compose_MLoc'), null), not(equals(outputs('Compose_MLoc')?['Active'], true))), 'LOCATION_UNKNOWN', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'ITEM_CREATE'), not(equals(outputs('Compose_MItemRow'), null)), not(equals(outputs('Compose_MItemRow')?['CreatedViaRequestID'], outputs('Compose_RequestIdIn')))), 'ITEM_EXISTS', '')), if(empty(if(and(equals(outputs('Compose_Req')?['RequestType'], 'LOCATION_ADD'), equals(outputs('Compose_MItemRow'), null)), 'ITEM_NOT_FOUND', '')), if(and(not(equals(outputs('Compose_MStockRow'), null)), not(equals(outputs('Compose_MStockRow')?['CreatedViaRequestID'], outputs('Compose_RequestIdIn')))), 'STOCK_EXISTS', ''), if(and(equals(outputs('Compose_Req')?['RequestType'], 'LOCATION_ADD'), equals(outputs('Compose_MItemRow'), null)), 'ITEM_NOT_FOUND', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'ITEM_CREATE'), not(equals(outputs('Compose_MItemRow'), null)), not(equals(outputs('Compose_MItemRow')?['CreatedViaRequestID'], outputs('Compose_RequestIdIn')))), 'ITEM_EXISTS', '')), if(or(equals(outputs('Compose_MLoc'), null), not(equals(outputs('Compose_MLoc')?['Active'], true))), 'LOCATION_UNKNOWN', '')), if(or(not(and(not(equals(outputs('Compose_Payload')?['MinQty'], null)), equals(mod(coalesce(outputs('Compose_Payload')?['MinQty'], 0), 1), 0))), not(and(not(equals(outputs('Compose_Payload')?['MaxQty'], null)), equals(mod(coalesce(outputs('Compose_Payload')?['MaxQty'], 0), 1), 0))), less(coalesce(outputs('Compose_Payload')?['MinQty'], 0), 0), greater(coalesce(outputs('Compose_Payload')?['MinQty'], 0), coalesce(outputs('Compose_Payload')?['MaxQty'], 0))), 'PAYLOAD_INVALID', '')), if(and(equals(outputs('Compose_Req')?['RequestType'], 'ITEM_CREATE'), empty(trim(string(coalesce(outputs('Compose_Payload')?['ItemName'], ''))))), 'PAYLOAD_INVALID', '')), if(or(empty(outputs('Compose_MItem')), contains(outputs('Compose_MItem'), '|'), contains(outputs('Compose_MItem'), ' ')), 'PAYLOAD_INVALID', ''))"
          ```
        - **`Master_Result`**
          - Run after: after `Master_Rules1_item_id_valid_to_stock_new` Succeeded
          **Data Operation > Compose**
          ```json
          "@outputs('Master_Rules1_item_id_valid_to_stock_new')"
          ```
        - **`If_m_reject`**
          - Run after: after `Master_Result` Succeeded
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@not(empty(outputs('Master_Result')))", true]}
          ```
          - Inside `If_m_reject`:
            - **`Result_m_reject`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Rejected",
                  "code": "@outputs('Master_Result')",
                  "message": "@coalesce(outputs('Compose_Messages')?[outputs('Master_Result')], outputs('Master_Result'))",
                  "finalize": "yes",
                  "effect": "NotApplied",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": ""
                }
              }
              ```
        - **`If_m_create`**
          - Run after: after `If_m_reject` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(outputs('Master_Result'), ''))", true]}
          ```
          - Inside `If_m_create`:
            - **`If_create_item`**
              - Run after: first action
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@and(equals(outputs('Compose_Req')?['RequestType'], 'ITEM_CREATE'), equals(outputs('Compose_MItemRow'), null))", true]}
              ```
              - Inside `If_create_item`:
                - **`Create_item`**
                  - Run after: first action
                  **SharePoint > Send an HTTP request to SharePoint**  `POST`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `/_api/web/lists/getbytitle('POUItems')/items`
                  - Headers: `{"Content-Type": "application/json;odata=verbose"}`  (+ Accept: application/json;odata=verbose)
                  - Body:
                  ```json
                  {
                    "__metadata": {
                      "type": "SP.Data.POUItemsListItem"
                    },
                    "Title": "@outputs('Compose_MItem')",
                    "ItemID": "@outputs('Compose_MItem')",
                    "ItemName": "@trim(string(outputs('Compose_Payload')?['ItemName']))",
                    "Description": "@string(coalesce(outputs('Compose_Payload')?['Description'], ''))",
                    "Manufacturer": "@string(coalesce(outputs('Compose_Payload')?['Manufacturer'], ''))",
                    "Active": true,
                    "CreatedViaRequestID": "@outputs('Compose_RequestIdIn')",
                    "ApprovedByUPN": "@outputs('Compose_AuthBy')"
                  }
                  ```
            - **`If_create_stock`**
              - Run after: after `If_create_item` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@equals(outputs('Compose_MStockRow'), null)", true]}
              ```
              - Inside `If_create_stock`:
                - **`Create_stock`**
                  - Run after: first action
                  **SharePoint > Send an HTTP request to SharePoint**  `POST`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `/_api/web/lists/getbytitle('POUStockLocations')/items`
                  - Headers: `{"Content-Type": "application/json;odata=verbose"}`  (+ Accept: application/json;odata=verbose)
                  - Body:
                  ```json
                  {
                    "__metadata": {
                      "type": "SP.Data.POUStockLocationsListItem"
                    },
                    "Title": "@concat(outputs('Compose_MItem'), ' @ ', outputs('Compose_MLoc')?['LocationCode'])",
                    "StockKey": "@outputs('Compose_MStockKey')",
                    "ItemID": "@outputs('Compose_MItem')",
                    "LocationCode": "@outputs('Compose_MLoc')?['LocationCode']",
                    "ItemName": "@if(equals(outputs('Compose_Req')?['RequestType'], 'ITEM_CREATE'), trim(string(outputs('Compose_Payload')?['ItemName'])), coalesce(outputs('Compose_MItemRow')?['ItemName'], ''))",
                    "Area": "@string(coalesce(outputs('Compose_Payload')?['Area'], ''))",
                    "MinQty": "@outputs('Compose_Payload')?['MinQty']",
                    "MaxQty": "@outputs('Compose_Payload')?['MaxQty']",
                    "StockVersion": 0,
                    "BalanceStatus": "NoBalance",
                    "LowStockFlag": false,
                    "Active": true,
                    "CreatedViaRequestID": "@outputs('Compose_RequestIdIn')"
                  }
                  ```
            - **`Verify_m_item`**
              - Run after: after `If_create_stock` Succeeded/Failed/Skipped/TimedOut
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUItems'')/items', '?', '$filter=', 'ItemID eq ''', uriComponent(replace(string(outputs('Compose_MItem')), '''', '''''')), '''', '&', '$select=Id,CreatedViaRequestID', '&', '$top=2')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`Verify_m_stock`**
              - Run after: after `Verify_m_item` Succeeded/Failed/Skipped/TimedOut
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items', '?', '$filter=', 'StockKey eq ''', uriComponent(replace(string(outputs('Compose_MStockKey')), '''', '''''')), '''', '&', '$select=Id,CreatedViaRequestID', '&', '$top=2')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`Compose_MVerified`**
              - Run after: after `Verify_m_stock` Succeeded/Failed/Skipped/TimedOut
              **Data Operation > Compose**
              ```json
              "@and(not(empty(body('Verify_m_stock')?['d']?['results'])), equals(first(body('Verify_m_stock')?['d']?['results'])?['CreatedViaRequestID'], outputs('Compose_RequestIdIn')), or(equals(outputs('Compose_Req')?['RequestType'], 'LOCATION_ADD'), and(not(empty(body('Verify_m_item')?['d']?['results'])), equals(first(body('Verify_m_item')?['d']?['results'])?['CreatedViaRequestID'], outputs('Compose_RequestIdIn')))))"
              ```
            - **`If_m_verified`**
              - Run after: after `Compose_MVerified` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@equals(outputs('Compose_MVerified'), true)", true]}
              ```
              - Inside `If_m_verified`:
                - **`Result_m_ok`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vRes",
                    "value": {
                      "outcome": "done",
                      "status": "Succeeded",
                      "code": "OK",
                      "message": "@concat('Created ', outputs('Compose_MStockKey'), '. It has NO quantity yet: a supervisor must count it (Audit) before it can be issued.')",
                      "finalize": "yes",
                      "effect": "NotApplied",
                      "ledger": "",
                      "newOnHand": "",
                      "authBy": "@outputs('Compose_AuthBy')"
                    }
                  }
                  ```
              - If NO (else) in `If_m_verified`:
                - **`Result_m_pending`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vRes",
                    "value": {
                      "outcome": "done",
                      "status": "Processing",
                      "code": "CREATE_PENDING",
                      "message": "Not confirmed yet. Do not repeat; it will be completed or retried automatically.",
                      "finalize": "no",
                      "effect": "",
                      "ledger": "",
                      "newOnHand": "",
                      "authBy": ""
                    }
                  }
                  ```
    - **`Dispatch_param`**
      - Run after: after `Dispatch_master` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none')), equals(outputs('Compose_Req')?['RequestType'], 'PARAM_UPDATE'))", true]}
      ```
      - Inside `Dispatch_param`:
        - **`Compose_PPayload`**
          - Run after: first action
          **Data Operation > Compose**
          ```json
          "@json(coalesce(outputs('Compose_Req')?['PayloadJson'], '{}'))"
          ```
        - **`Param_init`**
          - Run after: after `Compose_PPayload` Succeeded
          **Control > Scope**
          - Inside `Param_init`:
            - **`Param_init_vApplyTries`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vApplyTries",
                "value": 0
              }
              ```
            - **`Param_init_vApplied`**
              - Run after: after `Param_init_vApplyTries` Succeeded
              **Variable > Set variable**
              ```json
              {
                "name": "vApplied",
                "value": "no"
              }
              ```
        - **`Until_param`**
          - Run after: after `Param_init` Succeeded/Failed/Skipped/TimedOut
          **Control > Do until**  limit count 5, timeout PT1H
          - Condition: `@or(equals(variables('vApplied'), 'yes'), equals(variables('vRes')?['outcome'], 'done'), greaterOrEquals(variables('vApplyTries'), 3))`
          - Inside `Until_param`:
            - **`Param_inc_tries`**
              - Run after: first action
              **Variable > Increment variable**
              ```json
              {
                "name": "vApplyTries",
                "value": 1
              }
              ```
            - **`Get_p_stock`**
              - Run after: after `Param_inc_tries` Succeeded
              **SharePoint > Send an HTTP request to SharePoint**  `GET`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items', '?', '$filter=', 'StockKey eq ''', uriComponent(replace(string(coalesce(outputs('Compose_Req')?['StockKey'], 'NONE')), '''', '''''')), '''', '&', '$select=Id,StockKey,ItemID,LocationCode,ItemName,Area,MinQty,MaxQty,OnHandQty,StockVersion,BalanceStatus,LowStockFlag,Active,LastLedgerKey,LastCountedUtc,CreatedViaRequestID', '&', '$top=2')`
              - Headers: `{}`  (+ Accept: application/json;odata=verbose)
            - **`Compose_PStock`**
              - Run after: after `Get_p_stock` Succeeded
              **Data Operation > Compose**
              ```json
              "@first(body('Get_p_stock')?['d']?['results'])"
              ```
            - **`Param_Rules1_stock_found_to_no_deactivate_with_stock`**
              - Run after: after `Compose_PStock` Succeeded
              **Data Operation > Compose**
              ```json
              "@if(empty(if(equals(outputs('Compose_PStock'), null), 'STOCK_NOT_FOUND', '')), if(empty(if(or(not(and(not(equals(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), null)), equals(mod(coalesce(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), 0), 1), 0))), not(and(not(equals(coalesce(outputs('Compose_PPayload')?['MaxQty'], outputs('Compose_PStock')?['MaxQty']), null)), equals(mod(coalesce(coalesce(outputs('Compose_PPayload')?['MaxQty'], outputs('Compose_PStock')?['MaxQty']), 0), 1), 0))), less(coalesce(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), 0), 0), greater(coalesce(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), 0), coalesce(coalesce(outputs('Compose_PPayload')?['MaxQty'], outputs('Compose_PStock')?['MaxQty']), 0))), 'PAYLOAD_INVALID', '')), if(and(equals(coalesce(outputs('Compose_PPayload')?['Active'], outputs('Compose_PStock')?['Active']), false), not(equals(outputs('Compose_PStock')?['OnHandQty'], null)), greater(coalesce(outputs('Compose_PStock')?['OnHandQty'], 0), 0)), 'NONZERO_STOCK', ''), if(or(not(and(not(equals(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), null)), equals(mod(coalesce(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), 0), 1), 0))), not(and(not(equals(coalesce(outputs('Compose_PPayload')?['MaxQty'], outputs('Compose_PStock')?['MaxQty']), null)), equals(mod(coalesce(coalesce(outputs('Compose_PPayload')?['MaxQty'], outputs('Compose_PStock')?['MaxQty']), 0), 1), 0))), less(coalesce(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), 0), 0), greater(coalesce(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), 0), coalesce(coalesce(outputs('Compose_PPayload')?['MaxQty'], outputs('Compose_PStock')?['MaxQty']), 0))), 'PAYLOAD_INVALID', '')), if(equals(outputs('Compose_PStock'), null), 'STOCK_NOT_FOUND', ''))"
              ```
            - **`Param_Result`**
              - Run after: after `Param_Rules1_stock_found_to_no_deactivate_with_stock` Succeeded
              **Data Operation > Compose**
              ```json
              "@outputs('Param_Rules1_stock_found_to_no_deactivate_with_stock')"
              ```
            - **`If_p_reject`**
              - Run after: after `Param_Result` Succeeded
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), not(empty(outputs('Param_Result'))))", true]}
              ```
              - Inside `If_p_reject`:
                - **`Result_p_reject`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vRes",
                    "value": {
                      "outcome": "done",
                      "status": "Rejected",
                      "code": "@outputs('Param_Result')",
                      "message": "@coalesce(outputs('Compose_Messages')?[outputs('Param_Result')], outputs('Param_Result'))",
                      "finalize": "yes",
                      "effect": "NotApplied",
                      "ledger": "",
                      "newOnHand": "",
                      "authBy": ""
                    }
                  }
                  ```
            - **`If_p_apply`**
              - Run after: after `If_p_reject` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(outputs('Param_Result'), ''))", true]}
              ```
              - Inside `If_p_apply`:
                - **`Apply_param`**
                  - Run after: first action
                  **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items(', outputs('Compose_PStock')?['Id'], ')')`
                  - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "@outputs('Compose_PStock')?['__metadata']?['etag']"}`  (+ Accept: application/json;odata=verbose)
                  - Body:
                  ```json
                  {
                    "__metadata": {
                      "type": "SP.Data.POUStockLocationsListItem"
                    },
                    "MinQty": "@coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty'])",
                    "MaxQty": "@coalesce(outputs('Compose_PPayload')?['MaxQty'], outputs('Compose_PStock')?['MaxQty'])",
                    "Active": "@coalesce(outputs('Compose_PPayload')?['Active'], outputs('Compose_PStock')?['Active'])",
                    "LowStockFlag": "@and(not(equals(outputs('Compose_PStock')?['OnHandQty'], null)), if(equals(outputs('Compose_Settings')?['LowStockRule'], 'LT'), less(coalesce(outputs('Compose_PStock')?['OnHandQty'], 0), coalesce(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), 0)), lessOrEquals(coalesce(outputs('Compose_PStock')?['OnHandQty'], 0), coalesce(coalesce(outputs('Compose_PPayload')?['MinQty'], outputs('Compose_PStock')?['MinQty']), 0))))",
                    "Area": "@coalesce(outputs('Compose_PPayload')?['Area'], outputs('Compose_PStock')?['Area'])"
                  }
                  ```
                - **`If_param_ok`**
                  - Run after: after `Apply_param` Succeeded/Failed/Skipped/TimedOut
                  **Control > Condition**  (advanced mode)
                  ```json
                  {"equals": ["@equals(actions('Apply_param')?['status'], 'Succeeded')", true]}
                  ```
                  - Inside `If_param_ok`:
                    - **`Set_vApplied_param`**
                      - Run after: first action
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vApplied",
                        "value": "yes"
                      }
                      ```
        - **`If_param_done`**
          - Run after: after `Until_param` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vApplied'), 'yes'))", true]}
          ```
          - Inside `If_param_done`:
            - **`Result_param_ok`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Succeeded",
                  "code": "OK",
                  "message": "Settings for this item/location were updated.",
                  "finalize": "yes",
                  "effect": "NotApplied",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": "@outputs('Compose_AuthBy')"
                }
              }
              ```
        - **`If_param_pending`**
          - Run after: after `If_param_done` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vApplied'), 'no'))", true]}
          ```
          - Inside `If_param_pending`:
            - **`Result_param_pending`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Pending",
                  "code": "CONTENTION",
                  "message": "Busy - retrying automatically.",
                  "finalize": "yes",
                  "effect": "",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": ""
                }
              }
              ```
    - **`Dispatch_approve`**
      - Run after: after `Dispatch_param` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'none')), equals(outputs('Compose_Req')?['RequestType'], 'APPROVE'))", true]}
      ```
      - Inside `Dispatch_approve`:
        - **`Get_target`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POURequests'')/items', '?', '$filter=', 'RequestID eq ''', uriComponent(replace(string(coalesce(outputs('Compose_Req')?['TargetRequestID'], 'NONE')), '''', '''''')), '''', '&', '$select=Id,Created,RequestID,RequestType,RequestStatus,IsOpen,SessionID,StationID,StockKey,ItemID,LocationCode,Quantity,ExpectedVersion,PayloadJson,Reason,ReversesLedgerKey,TargetRequestID,Decision,ResultCode,ResultMessage,LedgerKey,InventoryEffect,ClaimedUtc,AttemptCount,ProcessingRunId,Author/EMail', '&', '$top=2', '&', '$expand=Author')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_Target`**
          - Run after: after `Get_target` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_target')?['d']?['results'])"
          ```
        - **`If_target_missing`**
          - Run after: after `Compose_Target` Succeeded
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@equals(outputs('Compose_Target'), null)", true]}
          ```
          - Inside `If_target_missing`:
            - **`Result_target_missing`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Rejected",
                  "code": "TARGET_NOT_FOUND",
                  "message": "@coalesce(outputs('Compose_Messages')?['TARGET_NOT_FOUND'], 'TARGET_NOT_FOUND')",
                  "finalize": "yes",
                  "effect": "NotApplied",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": ""
                }
              }
              ```
        - **`If_target_not_waiting`**
          - Run after: after `If_target_missing` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), not(equals(outputs('Compose_Target')?['RequestStatus'], 'AwaitingSupervisor')))", true]}
          ```
          - Inside `If_target_not_waiting`:
            - **`Result_target_not_waiting`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Succeeded",
                  "code": "OK_NOTHING_TO_DO",
                  "message": "That request is not waiting for approval (already finished or being processed). Nothing was changed.",
                  "finalize": "yes",
                  "effect": "NotApplied",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": ""
                }
              }
              ```
        - **`If_requeue_target`**
          - Run after: after `If_target_not_waiting` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@equals(variables('vRes')?['outcome'], 'continue')", true]}
          ```
          - Inside `If_requeue_target`:
            - **`Requeue_target`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POURequests'')/items(', outputs('Compose_Target')?['Id'], ')')`
              - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "@outputs('Compose_Target')?['__metadata']?['etag']"}`  (+ Accept: application/json;odata=verbose)
              - Body:
              ```json
              {
                "__metadata": {
                  "type": "SP.Data.POURequestsListItem"
                },
                "RequestStatus": "Pending",
                "IsOpen": true
              }
              ```
            - **`If_requeued`**
              - Run after: after `Requeue_target` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@equals(actions('Requeue_target')?['status'], 'Succeeded')", true]}
              ```
              - Inside `If_requeued`:
                - **`Result_approve_ok`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vRes",
                    "value": {
                      "outcome": "done",
                      "status": "Succeeded",
                      "code": "OK",
                      "message": "Your decision was recorded and the request was released for processing.",
                      "finalize": "yes",
                      "effect": "NotApplied",
                      "ledger": "",
                      "newOnHand": "",
                      "authBy": "@outputs('Compose_AuthBy')"
                    }
                  }
                  ```
              - If NO (else) in `If_requeued`:
                - **`Result_approve_pending`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vRes",
                    "value": {
                      "outcome": "done",
                      "status": "Processing",
                      "code": "REQUEUE_PENDING",
                      "message": "Decision recorded; releasing the request. It will complete automatically.",
                      "finalize": "no",
                      "effect": "",
                      "ledger": "",
                      "newOnHand": "",
                      "authBy": ""
                    }
                  }
                  ```
    - **`Stage_apply`**
      - Run after: after `Dispatch_approve` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vIntent'), 'ours'))", true]}
      ```
      - Inside `Stage_apply`:
        - **`Get_intent_row`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `GET`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items', '?', '$filter=', 'RequestID eq ''', uriComponent(replace(string(outputs('Compose_RequestIdIn')), '''', '''''')), '''', '&', '$select=Id,LedgerKey,RequestID,LedgerType,PostingState,StockKey,ItemID,LocationCode,SeqNo,QtyDelta,QtyBefore,QtyAfter,AffectsBalance,ReversesLedgerKey,OccurredUtc,BadgeID,EmployeeName,Origin,AuthorizedByUPN', '&', '$top=2')`
          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
        - **`Compose_Intent`**
          - Run after: after `Get_intent_row` Succeeded
          **Data Operation > Compose**
          ```json
          "@first(body('Get_intent_row')?['d']?['results'])"
          ```
        - **`If_intent_row_missing`**
          - Run after: after `Compose_Intent` Succeeded
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@equals(outputs('Compose_Intent'), null)", true]}
          ```
          - Inside `If_intent_row_missing`:
            - **`Result_intent_missing`**
              - Run after: first action
              **Variable > Set variable**
              ```json
              {
                "name": "vRes",
                "value": {
                  "outcome": "done",
                  "status": "Processing",
                  "code": "INTENT_NOT_FOUND",
                  "message": "Could not read the record just written. Do not repeat; it will be re-checked automatically.",
                  "finalize": "no",
                  "effect": "",
                  "ledger": "",
                  "newOnHand": "",
                  "authBy": ""
                }
              }
              ```
        - **`If_intent_row_present`**
          - Run after: after `If_intent_row_missing` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), not(equals(outputs('Compose_Intent'), null)))", true]}
          ```
          - Inside `If_intent_row_present`:
            - **`Apply_init`**
              - Run after: first action
              **Control > Scope**
              - Inside `Apply_init`:
                - **`Apply_init_vApplyTries`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vApplyTries",
                    "value": 0
                  }
                  ```
                - **`Apply_init_vApplied`**
                  - Run after: after `Apply_init_vApplyTries` Succeeded
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vApplied",
                    "value": "no"
                  }
                  ```
            - **`Until_apply`**
              - Run after: after `Apply_init` Succeeded/Failed/Skipped/TimedOut
              **Control > Do until**  limit count 5, timeout PT1H
              - Condition: `@or(equals(variables('vApplied'), 'yes'), equals(variables('vRes')?['outcome'], 'done'), greaterOrEquals(variables('vApplyTries'), 3))`
              - Inside `Until_apply`:
                - **`Apply_inc_tries`**
                  - Run after: first action
                  **Variable > Increment variable**
                  ```json
                  {
                    "name": "vApplyTries",
                    "value": 1
                  }
                  ```
                - **`Get_stock_apply`**
                  - Run after: after `Apply_inc_tries` Succeeded
                  **SharePoint > Send an HTTP request to SharePoint**  `GET`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items', '?', '$filter=', 'StockKey eq ''', uriComponent(replace(string(outputs('Compose_Intent')?['StockKey']), '''', '''''')), '''', '&', '$select=Id,StockKey,ItemID,LocationCode,ItemName,Area,MinQty,MaxQty,OnHandQty,StockVersion,BalanceStatus,LowStockFlag,Active,LastLedgerKey,LastCountedUtc,CreatedViaRequestID', '&', '$top=2')`
                  - Headers: `{}`  (+ Accept: application/json;odata=verbose)
                - **`Compose_StockApply`**
                  - Run after: after `Get_stock_apply` Succeeded
                  **Data Operation > Compose**
                  ```json
                  "@first(body('Get_stock_apply')?['d']?['results'])"
                  ```
                - **`Compose_ApplyState`**
                  - Run after: after `Compose_StockApply` Succeeded
                  **Data Operation > Compose**
                  ```json
                  "@if(equals(outputs('Compose_StockApply'), null), 'anomaly', if(greater(coalesce(outputs('Compose_StockApply')?['StockVersion'], 0), outputs('Compose_Intent')?['SeqNo']), 'applied', if(and(equals(outputs('Compose_StockApply')?['StockVersion'], outputs('Compose_Intent')?['SeqNo']), equals(outputs('Compose_StockApply')?['OnHandQty'], outputs('Compose_Intent')?['QtyAfter'])), 'applied', if(and(equals(outputs('Compose_StockApply')?['StockVersion'], sub(outputs('Compose_Intent')?['SeqNo'], 1)), if(equals(outputs('Compose_Intent')?['QtyBefore'], null), equals(outputs('Compose_StockApply')?['OnHandQty'], null), equals(outputs('Compose_StockApply')?['OnHandQty'], outputs('Compose_Intent')?['QtyBefore']))), 'unapplied', 'anomaly'))))"
                  ```
                - **`If_state_applied`**
                  - Run after: after `Compose_ApplyState` Succeeded
                  **Control > Condition**  (advanced mode)
                  ```json
                  {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(outputs('Compose_ApplyState'), 'applied'))", true]}
                  ```
                  - Inside `If_state_applied`:
                    - **`Set_vApplied_already`**
                      - Run after: first action
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vApplied",
                        "value": "yes"
                      }
                      ```
                - **`If_state_unapplied`**
                  - Run after: after `If_state_applied` Succeeded/Failed/Skipped/TimedOut
                  **Control > Condition**  (advanced mode)
                  ```json
                  {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(outputs('Compose_ApplyState'), 'unapplied'))", true]}
                  ```
                  - Inside `If_state_unapplied`:
                    - **`Apply_stock`**
                      - Run after: first action
                      **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
                      - Site Address: `@outputs('Cfg_SiteUrl')`
                      - Uri: `@concat('/_api/web/lists/getbytitle(''POUStockLocations'')/items(', outputs('Compose_StockApply')?['Id'], ')')`
                      - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "@outputs('Compose_StockApply')?['__metadata']?['etag']"}`  (+ Accept: application/json;odata=verbose)
                      - Body:
                      ```json
                      {
                        "__metadata": {
                          "type": "SP.Data.POUStockLocationsListItem"
                        },
                        "OnHandQty": "@outputs('Compose_Intent')?['QtyAfter']",
                        "StockVersion": "@outputs('Compose_Intent')?['SeqNo']",
                        "BalanceStatus": "@if(equals(outputs('Compose_Intent')?['LedgerType'], 'OPENING'), 'Unverified', if(equals(outputs('Compose_Intent')?['LedgerType'], 'AUDIT'), 'Verified', coalesce(outputs('Compose_StockApply')?['BalanceStatus'], 'NoBalance')))",
                        "LowStockFlag": "@and(not(equals(outputs('Compose_StockApply')?['MinQty'], null)), if(equals(outputs('Compose_Settings')?['LowStockRule'], 'LT'), less(outputs('Compose_Intent')?['QtyAfter'], coalesce(outputs('Compose_StockApply')?['MinQty'], 0)), lessOrEquals(outputs('Compose_Intent')?['QtyAfter'], coalesce(outputs('Compose_StockApply')?['MinQty'], 0))))",
                        "LastLedgerKey": "@outputs('Compose_Intent')?['LedgerKey']",
                        "LastPostedUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                        "LastCountedUtc": "@if(contains(createArray('AUDIT', 'OPENING'), outputs('Compose_Intent')?['LedgerType']), utcNow('yyyy-MM-ddTHH:mm:ssZ'), outputs('Compose_StockApply')?['LastCountedUtc'])"
                      }
                      ```
                    - **`If_apply_ok`**
                      - Run after: after `Apply_stock` Succeeded/Failed/Skipped/TimedOut
                      **Control > Condition**  (advanced mode)
                      ```json
                      {"equals": ["@equals(actions('Apply_stock')?['status'], 'Succeeded')", true]}
                      ```
                      - Inside `If_apply_ok`:
                        - **`Set_vApplied_ok`**
                          - Run after: first action
                          **Variable > Set variable**
                          ```json
                          {
                            "name": "vApplied",
                            "value": "yes"
                          }
                          ```
                - **`If_state_anomaly`**
                  - Run after: after `If_state_unapplied` Succeeded/Failed/Skipped/TimedOut
                  **Control > Condition**  (advanced mode)
                  ```json
                  {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(outputs('Compose_ApplyState'), 'anomaly'))", true]}
                  ```
                  - Inside `If_state_anomaly`:
                    - **`Anom_Ops_event`**
                      - Run after: first action
                      **Control > Scope**
                      - Inside `Anom_Ops_event`:
                        - **`Anom_Get_event`**
                          - Run after: first action
                          **SharePoint > Send an HTTP request to SharePoint**  `GET`
                          - Site Address: `@outputs('Cfg_SiteUrl')`
                          - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items', '?', '$filter=', 'EventKey eq ''', uriComponent(replace(string(concat('ANOMALY|', outputs('Compose_Intent')?['LedgerKey'])), '''', '''''')), '''', '&', '$select=Id,OccurrenceCount', '&', '$top=2')`
                          - Headers: `{}`  (+ Accept: application/json;odata=verbose)
                        - **`Anom_Event_row`**
                          - Run after: after `Anom_Get_event` Succeeded
                          **Data Operation > Compose**
                          ```json
                          "@first(body('Anom_Get_event')?['d']?['results'])"
                          ```
                        - **`Anom_Event_exists`**
                          - Run after: after `Anom_Event_row` Succeeded
                          **Control > Condition**  (advanced mode)
                          ```json
                          {"equals": ["@not(equals(outputs('Anom_Event_row'), null))", true]}
                          ```
                          - Inside `Anom_Event_exists`:
                            - **`Anom_Update_event`**
                              - Run after: first action
                              **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
                              - Site Address: `@outputs('Cfg_SiteUrl')`
                              - Uri: `@concat('/_api/web/lists/getbytitle(''POUOpsEvents'')/items(', outputs('Anom_Event_row')?['Id'], ')')`
                              - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
                              - Body:
                              ```json
                              {
                                "__metadata": {
                                  "type": "SP.Data.POUOpsEventsListItem"
                                },
                                "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                                "OccurrenceCount": "@add(int(coalesce(outputs('Anom_Event_row')?['OccurrenceCount'], 1)), 1)",
                                "Details": "@concat('Intent ', outputs('Compose_Intent')?['LedgerKey'], ' expected stock version ', string(sub(outputs('Compose_Intent')?['SeqNo'], 1)), ' (before) or ', string(outputs('Compose_Intent')?['SeqNo']), ' (after), found version ', string(outputs('Compose_StockApply')?['StockVersion']), ' on hand ', string(outputs('Compose_StockApply')?['OnHandQty']), '. The intent was voided; this request changed nothing.')",
                                "Resolved": false
                              }
                              ```
                          - If NO (else) in `Anom_Event_exists`:
                            - **`Anom_Create_event`**
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
                                "Title": "@concat('Stock changed outside the posting process: ', outputs('Compose_Intent')?['StockKey'])",
                                "EventKey": "@concat('ANOMALY|', outputs('Compose_Intent')?['LedgerKey'])",
                                "EventType": "STOCK_ANOMALY",
                                "Severity": "Critical",
                                "Subject": "@concat('Stock changed outside the posting process: ', outputs('Compose_Intent')?['StockKey'])",
                                "Details": "@concat('Intent ', outputs('Compose_Intent')?['LedgerKey'], ' expected stock version ', string(sub(outputs('Compose_Intent')?['SeqNo'], 1)), ' (before) or ', string(outputs('Compose_Intent')?['SeqNo']), ' (after), found version ', string(outputs('Compose_StockApply')?['StockVersion']), ' on hand ', string(outputs('Compose_StockApply')?['OnHandQty']), '. The intent was voided; this request changed nothing.')",
                                "FirstSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                                "LastSeenUtc": "@utcNow('yyyy-MM-ddTHH:mm:ssZ')",
                                "OccurrenceCount": 1,
                                "Resolved": false
                              }
                              ```
                    - **`Void_intent`**
                      - Run after: after `Anom_Ops_event` Succeeded/Failed/Skipped/TimedOut
                      **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
                      - Site Address: `@outputs('Cfg_SiteUrl')`
                      - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items(', outputs('Compose_Intent')?['Id'], ')')`
                      - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
                      - Body:
                      ```json
                      {
                        "__metadata": {
                          "type": "SP.Data.POULedgerListItem"
                        },
                        "LedgerKey": "@concat('VOID|', guid())",
                        "RequestID": "@concat('VOID|', guid())",
                        "PostingState": "Voided",
                        "Reason": "@concat('Voided: stock changed outside protocol. Original request ', outputs('Compose_Intent')?['RequestID'])"
                      }
                      ```
                    - **`Result_anomaly`**
                      - Run after: after `Void_intent` Succeeded/Failed/Skipped/TimedOut
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vRes",
                        "value": {
                          "outcome": "done",
                          "status": "Failed",
                          "code": "STOCK_CHANGED_OUTSIDE_PROTOCOL",
                          "message": "@coalesce(outputs('Compose_Messages')?['STOCK_CHANGED_OUTSIDE_PROTOCOL'], 'STOCK_CHANGED_OUTSIDE_PROTOCOL')",
                          "finalize": "yes",
                          "effect": "NotApplied",
                          "ledger": "",
                          "newOnHand": "",
                          "authBy": ""
                        }
                      }
                      ```
            - **`If_applied_finalize`**
              - Run after: after `Until_apply` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vApplied'), 'yes'))", true]}
              ```
              - Inside `If_applied_finalize`:
                - **`Finalize_ledger`**
                  - Run after: first action
                  **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
                  - Site Address: `@outputs('Cfg_SiteUrl')`
                  - Uri: `@concat('/_api/web/lists/getbytitle(''POULedger'')/items(', outputs('Compose_Intent')?['Id'], ')')`
                  - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
                  - Body:
                  ```json
                  {
                    "__metadata": {
                      "type": "SP.Data.POULedgerListItem"
                    },
                    "PostingState": "Posted"
                  }
                  ```
                - **`Compose_SuccessMessage`**
                  - Run after: after `Finalize_ledger` Succeeded/Failed/Skipped/TimedOut
                  **Data Operation > Compose**
                  ```json
                  "@if(equals(outputs('Compose_Intent')?['LedgerType'], 'ISSUE'), concat('Removed ', string(sub(0, int(coalesce(outputs('Compose_Intent')?['QtyDelta'], 0)))), ' x ', concat(outputs('Compose_Intent')?['ItemID'], ' @ ', outputs('Compose_Intent')?['LocationCode']), '. On hand now ', string(outputs('Compose_Intent')?['QtyAfter']), '.'), if(equals(outputs('Compose_Intent')?['LedgerType'], 'RECEIPT'), concat('Added ', string(coalesce(outputs('Compose_Intent')?['QtyDelta'], 0)), ' x ', concat(outputs('Compose_Intent')?['ItemID'], ' @ ', outputs('Compose_Intent')?['LocationCode']), '. On hand now ', string(outputs('Compose_Intent')?['QtyAfter']), '.'), if(equals(outputs('Compose_Intent')?['LedgerType'], 'AUDIT'), concat('Count recorded for ', concat(outputs('Compose_Intent')?['ItemID'], ' @ ', outputs('Compose_Intent')?['LocationCode']), ': ', string(outputs('Compose_Intent')?['QtyAfter']), if(equals(outputs('Compose_Intent')?['QtyBefore'], null), ' (first count - no previous balance).', concat(' (system had ', string(outputs('Compose_Intent')?['QtyBefore']), ').'))), if(equals(outputs('Compose_Intent')?['LedgerType'], 'OPENING'), concat('Opening balance recorded for ', concat(outputs('Compose_Intent')?['ItemID'], ' @ ', outputs('Compose_Intent')?['LocationCode']), ': ', string(outputs('Compose_Intent')?['QtyAfter']), '.'), concat(outputs('Compose_Intent')?['LedgerType'], ' recorded for ', concat(outputs('Compose_Intent')?['ItemID'], ' @ ', outputs('Compose_Intent')?['LocationCode']), '. On hand now ', string(outputs('Compose_Intent')?['QtyAfter']), '.')))))"
                  ```
                - **`If_ledger_posted`**
                  - Run after: after `Compose_SuccessMessage` Succeeded/Failed/Skipped/TimedOut
                  **Control > Condition**  (advanced mode)
                  ```json
                  {"equals": ["@equals(actions('Finalize_ledger')?['status'], 'Succeeded')", true]}
                  ```
                  - Inside `If_ledger_posted`:
                    - **`Result_success`**
                      - Run after: first action
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vRes",
                        "value": {
                          "outcome": "done",
                          "status": "Succeeded",
                          "code": "OK",
                          "message": "@outputs('Compose_SuccessMessage')",
                          "finalize": "yes",
                          "effect": "Applied",
                          "ledger": "@outputs('Compose_Intent')?['LedgerKey']",
                          "newOnHand": "@string(outputs('Compose_Intent')?['QtyAfter'])",
                          "authBy": "@coalesce(outputs('Compose_Intent')?['AuthorizedByUPN'], '')"
                        }
                      }
                      ```
                  - If NO (else) in `If_ledger_posted`:
                    - **`Result_finalizing`**
                      - Run after: first action
                      **Variable > Set variable**
                      ```json
                      {
                        "name": "vRes",
                        "value": {
                          "outcome": "done",
                          "status": "Processing",
                          "code": "FINALIZING",
                          "message": "The quantity WAS updated. Confirming the record. Do not repeat this; it will complete automatically.",
                          "finalize": "no",
                          "effect": "Applied",
                          "ledger": "@outputs('Compose_Intent')?['LedgerKey']",
                          "newOnHand": "@string(outputs('Compose_Intent')?['QtyAfter'])",
                          "authBy": ""
                        }
                      }
                      ```
            - **`If_apply_pending`**
              - Run after: after `If_applied_finalize` Succeeded/Failed/Skipped/TimedOut
              **Control > Condition**  (advanced mode)
              ```json
              {"equals": ["@and(equals(variables('vRes')?['outcome'], 'continue'), equals(variables('vApplied'), 'no'))", true]}
              ```
              - Inside `If_apply_pending`:
                - **`Result_apply_pending`**
                  - Run after: first action
                  **Variable > Set variable**
                  ```json
                  {
                    "name": "vRes",
                    "value": {
                      "outcome": "done",
                      "status": "Processing",
                      "code": "APPLY_PENDING",
                      "message": "Not confirmed yet. Do not repeat; it will be completed automatically.",
                      "finalize": "no",
                      "effect": "",
                      "ledger": "",
                      "newOnHand": "",
                      "authBy": ""
                    }
                  }
                  ```
    - **`Stage_finalize`**
      - Run after: after `Stage_apply` Succeeded/Failed/Skipped/TimedOut
      **Control > Condition**  (advanced mode)
      ```json
      {"equals": ["@and(equals(variables('vRes')?['finalize'], 'yes'), not(equals(outputs('Compose_Req'), null)))", true]}
      ```
      - Inside `Stage_finalize`:
        - **`Finalize_request`**
          - Run after: first action
          **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
          - Site Address: `@outputs('Cfg_SiteUrl')`
          - Uri: `@concat('/_api/web/lists/getbytitle(''POURequests'')/items(', outputs('Compose_Req')?['Id'], ')')`
          - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
          - Body:
          ```json
          {
            "__metadata": {
              "type": "SP.Data.POURequestsListItem"
            },
            "RequestStatus": "@variables('vRes')?['status']",
            "ResultCode": "@variables('vRes')?['code']",
            "ResultMessage": "@variables('vRes')?['message']",
            "LedgerKey": "@variables('vRes')?['ledger']",
            "InventoryEffect": "@if(empty(variables('vRes')?['effect']), null, variables('vRes')?['effect'])",
            "AuthorizedByUPN": "@variables('vRes')?['authBy']",
            "ProcessedUtc": "@if(contains(createArray('Succeeded', 'Rejected', 'Failed'), variables('vRes')?['status']), utcNow('yyyy-MM-ddTHH:mm:ssZ'), null)",
            "ClaimedUtc": null,
            "IsOpen": "@not(contains(createArray('Succeeded', 'Rejected', 'Failed'), variables('vRes')?['status']))"
          }
          ```
        - **`If_touch_session`**
          - Run after: after `Finalize_request` Succeeded/Failed/Skipped/TimedOut
          **Control > Condition**  (advanced mode)
          ```json
          {"equals": ["@and(not(empty(variables('vSessionItem'))), contains(createArray('Succeeded', 'Rejected'), variables('vRes')?['status']))", true]}
          ```
          - Inside `If_touch_session`:
            - **`Touch_session`**
              - Run after: first action
              **SharePoint > Send an HTTP request to SharePoint**  `MERGE`
              - Site Address: `@outputs('Cfg_SiteUrl')`
              - Uri: `@concat('/_api/web/lists/getbytitle(''POUSessions'')/items(', variables('vSessionItem'), ')')`
              - Headers: `{"Content-Type": "application/json;odata=verbose", "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}`  (+ Accept: application/json;odata=verbose)
              - Body:
              ```json
              {
                "__metadata": {
                  "type": "SP.Data.POUSessionsListItem"
                },
                "LastActivityUtc": "@coalesce(outputs('Compose_Req')?['Created'], utcNow('yyyy-MM-ddTHH:mm:ssZ'))"
              }
              ```
- ### `Respond`
  - Run after: after `Core` Succeeded/Failed/Skipped/TimedOut
  **Power Apps > Respond to a PowerApp or flow**
  ```json
  {
    "statusCode": 200,
    "body": {
      "status": "@variables('vRes')?['status']",
      "code": "@variables('vRes')?['code']",
      "message": "@variables('vRes')?['message']",
      "ledgerKey": "@variables('vRes')?['ledger']",
      "effect": "@variables('vRes')?['effect']",
      "newOnHand": "@variables('vRes')?['newOnHand']",
      "requestId": "@outputs('Compose_RequestIdIn')"
    },
    "schema": {
      "type": "object",
      "properties": {
        "status": {
          "type": "string"
        },
        "code": {
          "type": "string"
        },
        "message": {
          "type": "string"
        },
        "ledgerKey": {
          "type": "string"
        },
        "effect": {
          "type": "string"
        },
        "newOnHand": {
          "type": "string"
        },
        "requestId": {
          "type": "string"
        }
      }
    }
  }
  ```
