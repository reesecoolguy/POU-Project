# Control reference (generated)

Build id `POU-APP-d414ca54`. Every control of every screen with its exact name, type and Power Fx. If pasting the YAML into Studio is not accepted by your Studio version, build the app by hand from this file: create each control with the listed name and type and paste each formula into the property named.

Conventions: `varX` global (Set) | `locX` screen context variable | `colX` collection. All geometry values are for a 1366x768 Windows PC screen (App > Settings > Display: Landscape, 1366x768, scale to fit OFF, lock aspect ratio ON).

## App

### App.OnStart

```powerfx
// 1. who/where: the Microsoft account running the app is NOT the employee
Set(varStation, Upper(Trim(Coalesce(Param("StationID"), LookUp(POUStations, Active = true, ExpectedAccountUPN = Lower(User().Email)).StationID, ""))));
Set(varBuild, "POU-APP-d414ca54");
Set(varRowLimit, 500);
// 2. central settings (editable in POUSettings); defaults mirror schema/settings_defaults.json
Set(varSettingsOk, false);
IfError(ClearCollect(colSettings, POUSettings); Set(varSettingsOk, CountRows(colSettings) > 0), Clear(colSettings));
Set(varIdleMin, If(IsNumeric(LookUp(colSettings, SettingKey = "IdleTimeoutMinutes").SettingValue), Value(LookUp(colSettings, SettingKey = "IdleTimeoutMinutes").SettingValue), 3));
Set(varMaxAdd, If(IsNumeric(LookUp(colSettings, SettingKey = "MaxAddQty").SettingValue), Value(LookUp(colSettings, SettingKey = "MaxAddQty").SettingValue), 500));
Set(varAuditVar, If(IsNumeric(LookUp(colSettings, SettingKey = "AuditConfirmVariance").SettingValue), Value(LookUp(colSettings, SettingKey = "AuditConfirmVariance").SettingValue), 5));
Set(varScanIdle, If(IsNumeric(LookUp(colSettings, SettingKey = "ScanCommitIdleMs").SettingValue), Value(LookUp(colSettings, SettingKey = "ScanCommitIdleMs").SettingValue), 350));
Set(varScanMin, If(IsNumeric(LookUp(colSettings, SettingKey = "ScanMinLength").SettingValue), Value(LookUp(colSettings, SettingKey = "ScanMinLength").SettingValue), 3));
Set(varPollSec, If(IsNumeric(LookUp(colSettings, SettingKey = "StatusPollSeconds").SettingValue), Value(LookUp(colSettings, SettingKey = "StatusPollSeconds").SettingValue), 2));
Set(varPollMax, If(IsNumeric(LookUp(colSettings, SettingKey = "StatusPollTimeoutSeconds").SettingValue), Value(LookUp(colSettings, SettingKey = "StatusPollTimeoutSeconds").SettingValue), 45));
Set(varLogoutAfter, Lower(Coalesce(LookUp(colSettings, SettingKey = "LogoutAfterSubmit").SettingValue, "false")) = "true");
Set(varSupAudit, Lower(Coalesce(LookUp(colSettings, SettingKey = "RequireSupervisorForAudit").SettingValue, "true")) = "true");
Set(varSupNewItem, Lower(Coalesce(LookUp(colSettings, SettingKey = "RequireSupervisorForNewItem").SettingValue, "true")) = "true");
Set(varLowRule, Coalesce(LookUp(colSettings, SettingKey = "LowStockRule").SettingValue, "LE"));
Set(varTzName, Coalesce(LookUp(colSettings, SettingKey = "DisplayTimeZoneIana").SettingValue, "America/Chicago"));
// 3. is this Microsoft account a supervisor/admin? Display only - the server decides authority from the request Author.
Set(varMeEmp, IfError(LookUp(POUEmployees, MicrosoftUPN = Lower(User().Email), Active = true), Blank()));
Set(varIsPriv, Not(IsBlank(varMeEmp)) And varMeEmp.Role.Value <> "Operator");
// 4. state
Set(varSession, ""); Set(varEmpName, ""); Set(varRole, ""); Set(varSupMode, false);
Set(varBusy, false); Set(varLastActivity, Now()); Set(varTick, Now());
Set(varLoginMsg, ""); Set(varOutKind, ""); Set(varOutText, ""); Set(varPolling, false); Set(varPollTries, 0);
Set(varLookupFailed, false); Set(varCreateFailed, false); Set(varSent, false);
Set(varLogin, {ok: "no", code: "", message: "", sessionId: "", employeeName: "", role: "", idleMinutes: ""});
Set(varResp, {status: "", code: "", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: ""});
Set(varFound, Blank()); Set(varRow, Blank()); Set(varTgtRow, Blank());
Set(varFinal, ""); Set(varText, ""); Set(varEffect, ""); Set(varShort, "");
// 5. the local outbox: a request that was filed but never confirmed survives a crash/restart and keeps its RequestID
ClearCollect(colOutbox, {RequestID: "", SessionID: "", Station: "", RequestType: "", StockKey: "", ItemID: "", LocationCode: "", Quantity: "", ExpectedVersion: "", Reason: "", PayloadJson: "", TargetRequestID: "", Decision: "", ReversesLedgerKey: "", Summary: ""});
Clear(colOutbox);
IfError(LoadData(colOutbox, "POUOutbox", true), true);
Set(varReq, Blank());
ClearCollect(colStock, {ID: 0, StockKey: "", ItemID: "", LocationCode: "", ItemName: "", Area: "", MinQty: 0, MaxQty: 0, OnHandQty: 0, StockVersion: 0, LowStockFlag: false, Active: true});
Clear(colStock)
```

### App.StartScreen

```powerfx
scrLogin
```

### App.OnError

```powerfx
Notify("Something went wrong: " & FirstError.Message & ". If you were submitting a request, do NOT enter it again - use 'Retry same request'.", NotificationType.Error)
```

## scrLogin - Badge / session entry

Identifies the EMPLOYEE by badge. The badge is identification only: the session is bound server-side to the Microsoft account running the app and to this station. A supervisor uses 'Continue as supervisor' with their OWN Microsoft sign-in; no badge or editable variable can grant authority.

**Screen properties**

- `Fill`
  ```powerfx
  =RGBA(31, 56, 100, 1)
  ```
- `OnVisible`
  ```powerfx
  =Set(varBusy, false);
  Set(varLoginMsg, "");
  Set(varSession, "");
  Set(varSupMode, false);
  UpdateContext({locBadgePending: false, locLastKey: Now()});
  Reset(txtBadge);
  SetFocus(txtBadge)
  ```

| Control | Type | Purpose |
|---|---|---|
| `recLoginBg` | Rectangle |  |
| `lblLoginTitle` | Label | Title |
| `lblLoginStation` | Label | Station identity |
| `lblLoginPrompt` | Label |  |
| `txtBadge` | Text input | Scanner target. The value is cleared immediately after it is read. |
| `btnLogin` | Button | Calls POU-Session (LOGIN). Also called by the scan timer. |
| `lblLoginMsg` | Label | Why sign-in failed |
| `btnSupSignIn` | Button | Only appears when the Microsoft account running the app is an active Supervisor/Admin in POUEmployees. Authority is re-checked by the server from the request Author. |
| `lblLoginFoot` | Label | Which Microsoft account the app is running as (this is NOT the employee) |
| `tmrBadge` | Timer | Debounce for the badge scan |
| `tmrLoginTick` | Timer | Keeps the clock/idle variables moving |

### `recLoginBg` (Rectangle)

**Fill**

```powerfx
=RGBA(31, 56, 100, 1)
```

### `lblLoginTitle` (Label)

**Text**

```powerfx
="Point-of-Use Inventory"
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblLoginStation` (Label)

**Text**

```powerfx
=If(IsBlank(varStation), "NO STATION SET UP ON THIS PC - see START_HERE / Admin: open the app with ?StationID=<id> or assign this Microsoft account to a station", "Station " & varStation)
```

**Color**

```powerfx
=RGBA(255, 230, 153, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblLoginPrompt` (Label)

**Text**

```powerfx
="Scan your badge"
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtBadge` (Text input)

**HintText**

```powerfx
="Scan badge"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=UpdateContext({locBadgePending: true, locLastKey: Now()})
```

**DisplayMode**

```powerfx
=If(varBusy Or IsBlank(varStation), DisplayMode.Disabled, DisplayMode.Edit)
```

**TabIndex**

```powerfx
=1
```

### `btnLogin` (Button)

**Text**

```powerfx
="Sign in"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locBadgePending: false});
If(
    varBusy Or IsBlank(varStation),
    false,
    With(
        {b: Substitute(Trim(txtBadge.Text), "*", "")},
        If(
            Len(b) < varScanMin,
            Set(varLoginMsg, "Scan your badge."),
            Set(varBusy, true);
            Reset(txtBadge);
            Set(varLogin, IfError(
                'POU-Session'.Run("LOGIN", b, varStation, "", Lower(User().Email)),
                {ok: "no", code: "NETWORK", message: "Could not reach the server, so you are NOT signed in. Try again.", sessionId: "", employeeName: "", role: "", idleMinutes: ""}));
            If(
                varLogin.ok = "yes",
                Set(varSession, varLogin.sessionId);
                Set(varEmpName, varLogin.employeeName);
                Set(varRole, varLogin.role);
                Set(varSupMode, false);
                Set(varLoginMsg, "");
                Set(varOutKind, ""); Set(varOutText, "");
                If(
                    IsBlank(varReq) And CountRows(Filter(colOutbox, Station = varStation)) > 0,
                    Set(varReq, First(Filter(colOutbox, Station = varStation)));
                    Set(varOutKind, "unconfirmed");
                    Set(varOutText, "An earlier request on this station was never confirmed (" & varReq.Summary & "). Do not re-enter it: press 'Retry same request'.")
                );
                Set(varLastActivity, Now());
                Navigate(scrScan, ScreenTransition.None),
                Set(varLoginMsg, varLogin.message)
            );
            Set(varBusy, false)
        )
    )
)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(varBusy Or IsBlank(varStation), DisplayMode.Disabled, DisplayMode.Edit)
```

**TabIndex**

```powerfx
=2
```

### `lblLoginMsg` (Label)

**Text**

```powerfx
=varLoginMsg
```

**Color**

```powerfx
=RGBA(255, 199, 206, 1)
```

**Fill**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=Not(IsBlank(varLoginMsg))
```

### `btnSupSignIn` (Button)

**Text**

```powerfx
="Continue as supervisor: " & Coalesce(varMeEmp.EmployeeName, "")
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Set(varSession, "");
Set(varEmpName, varMeEmp.EmployeeName);
Set(varRole, varMeEmp.Role.Value);
Set(varSupMode, true);
Set(varLastActivity, Now());
Navigate(scrSupervisor, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(84, 130, 53, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=DisplayMode.Edit
```

**Visible**

```powerfx
=varIsPriv
```

**TabIndex**

```powerfx
=3
```

### `lblLoginFoot` (Label)

**Text**

```powerfx
="Signed in to Microsoft as " & User().Email & "  |  app build " & varBuild & "  |  " & If(varSettingsOk, "settings loaded", "SETTINGS NOT LOADED - using defaults")
```

**Color**

```powerfx
=RGBA(200, 200, 200, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `tmrBadge` (Timer)

**Duration**

```powerfx
=150
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=If(
    locBadgePending And DateDiff(locLastKey, Now(), Milliseconds) >= varScanIdle,
    Select(btnLogin)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `tmrLoginTick` (Timer)

**Duration**

```powerfx
=1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=Set(varTick, Now())
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

## scrScan - Item / location scan: ADD and REMOVE

The everyday screen. ADD creates a RECEIPT request, REMOVE an ISSUE request. The app never changes a quantity itself: it files the request, asks the flow to process it, and shows the outcome read back from the request row.

**Screen properties**

- `Fill`
  ```powerfx
  =RGBA(242, 242, 242, 1)
  ```
- `OnVisible`
  ```powerfx
  =If(IsBlank(varSession) And Not(varSupMode), Navigate(scrLogin, ScreenTransition.None));
  Set(varLastActivity, Now());
  UpdateContext({locSel: Blank(), locMsg: "", locPending: false, locLocPending: false, locLastKey: Now()});
  If(IsBlank(varReq), Clear(colStock); Reset(txtItemScan); Reset(txtLocScan); Reset(txtQtyScan); SetFocus(txtItemScan))
  ```

| Control | Type | Purpose |
|---|---|---|
| `recHdrScan` | Rectangle | Header band |
| `lblHdrStationScan` | Label | Station identity (always visible) |
| `lblHdrUserScan` | Label | Employee identity (always visible) |
| `lblHdrIdleScan` | Label | Idle countdown |
| `btnHdrOutScan` | Button | Ends the server session |
| `tmrIdleScan` | Timer | Idle timeout checker (central setting IdleTimeoutMinutes) |
| `btnNavScanScan` | Button | Go to scrScan |
| `btnNavAuditScan` | Button | Go to scrAudit |
| `btnNavAddItemScan` | Button | Go to scrAddItem |
| `btnNavLowScan` | Button | Go to scrLowStock |
| `btnNavHistScan` | Button | Go to scrHistory |
| `btnNavSupScan` | Button | Go to scrSupervisor |
| `btnNavAdminScan` | Button | Go to scrAdmin |
| `btnRunScan` | Button | Tiny transparent button. Runs the shared posting procedure for the retained request varReq; never creates a new RequestID. |
| `lblStep1Scan` | Label |  |
| `txtItemScan` | Text input | Scanner target. Enter/Tab suffix from the scanner ends the scan; the timer commits it. |
| `btnFindScan` | Button | Resolves the scan; also called by the scan timer |
| `lblStep2Scan` | Label |  |
| `txtLocScan` | Text input | Second scan target |
| `btnLocScan` | Button | Resolves the location scan; also called by the scan timer |
| `tmrScanScan` | Timer | Debounce: commits a scan once keystrokes stop for ScanCommitIdleMs, so Enter/Tab/no-suffix scanners all work |
| `lblMsgScan` | Label | Lookup messages |
| `galLocScan` | Vertical gallery | Choose the location when an item is stocked in more than one place |
| `lblGalLocScan` | Label |  |
| `lblNameScan` | Label | Item name |
| `lblMetaScan` | Label | Identity of the exact stock record |
| `lblOnHandScan` | Label | On hand (blank = no verified quantity) |
| `lblStatusScan` | Label | Server-computed status; the app never recomputes low stock |
| `lblStep3Scan` | Label |  |
| `txtQtyScan` | Text input | Whole number 1-9999. Anything else (a scanned barcode, text, 0, 1.5) is refused and never truncated. |
| `lblQtyHintScan` | Label | Why the quantity is not accepted (never silently truncated) |
| `btnAddScan` | Button | Creates a RECEIPT request once (new GUID), then posts it. Disabled while busy, while a request is unresolved, or when the entry is invalid. |
| `btnRemoveScan` | Button | Creates an ISSUE request once, then posts it. |
| `btnRetryScan` | Button | Re-sends the SAME request number. Safe: the server de-duplicates by RequestID. |
| `tmrPollScan` | Timer | Reads the request status while it is unconfirmed; never re-sends |
| `lblBannerScan` | Label | Outcome of the last request: ok / waiting / unconfirmed / bad |

### `recHdrScan` (Rectangle)

**Fill**

```powerfx
=RGBA(31, 56, 100, 1)
```

### `lblHdrStationScan` (Label)

**Text**

```powerfx
="Station " & varStation
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrUserScan` (Label)

**Text**

```powerfx
=If(varSupMode, varEmpName & " (supervisor, signed in as " & User().Email & ")", varEmpName & " - badge session")
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrIdleScan` (Label)

**Text**

```powerfx
="Auto sign-out in " & Max(0, varIdleMin * 60 - DateDiff(varLastActivity, varTick, Seconds)) & " s"
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnHdrOutScan` (Button)

**Text**

```powerfx
="Sign out"
```

**OnSelect**

```powerfx
=If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `tmrIdleScan` (Timer)

**Duration**

```powerfx
=1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=Set(varTick, Now());
If(
    (Not(IsBlank(varSession)) Or varSupMode) And DateDiff(varLastActivity, varTick, Seconds) >= varIdleMin * 60,
    If(
        Not(IsBlank(varSession)),
        IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
    );
    Set(varSession, "");
    Set(varEmpName, "");
    Set(varRole, "");
    Set(varSupMode, false);
    Clear(colStock);
    Navigate(scrLogin, ScreenTransition.None)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `btnNavScanScan` (Button)

**Text**

```powerfx
="Add / Remove"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrScan, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=Not(varSupMode)
```

### `btnNavAuditScan` (Button)

**Text**

```powerfx
="Count"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAudit, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavAddItemScan` (Button)

**Text**

```powerfx
="New item"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAddItem, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavLowScan` (Button)

**Text**

```powerfx
="Low stock"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrLowStock, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavHistScan` (Button)

**Text**

```powerfx
="History"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrHistory, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavSupScan` (Button)

**Text**

```powerfx
="Supervisor"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrSupervisor, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnNavAdminScan` (Button)

**Text**

```powerfx
="Admin"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAdmin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnRunScan` (Button)

**Text**

```powerfx
=""
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**OnSelect**

```powerfx
=If(
    IsBlank(varReq) Or varBusy,
    false,
    Set(varBusy, true);
Set(varOutKind, "");
Set(varOutText, "");
Set(varLookupFailed, false);
Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Set(varLookupFailed, true); Blank()));
Set(varSent, Not(IsBlank(varFound)));
If(
    Not(varSent) And Not(varLookupFailed),
    Set(varCreateFailed, false);
    IfError(Patch(POURequests, Defaults(POURequests), {
        Title: varReq.Summary,
        RequestID: varReq.RequestID,
        RequestType: {Value: varReq.RequestType},
        RequestStatus: {Value: "Pending"},
        IsOpen: true,
        SessionID: varReq.SessionID,
        StationID: varReq.Station,
        StockKey: varReq.StockKey,
        ItemID: varReq.ItemID,
        LocationCode: varReq.LocationCode,
        Quantity: If(IsBlank(varReq.Quantity), Blank(), Value(varReq.Quantity)),
        ExpectedVersion: If(IsBlank(varReq.ExpectedVersion), Blank(), Value(varReq.ExpectedVersion)),
        PayloadJson: varReq.PayloadJson,
        Reason: varReq.Reason,
        ReversesLedgerKey: varReq.ReversesLedgerKey,
        TargetRequestID: varReq.TargetRequestID,
        Decision: If(IsBlank(varReq.Decision), Blank(), {Value: varReq.Decision}),
        ClientLocalTime: Text(Now(), "yyyy-mm-dd hh:mm:ss")
    }), Set(varCreateFailed, true));
    Set(varSent, Not(varCreateFailed));
    If(
        varCreateFailed,
        Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
        Set(varSent, Not(IsBlank(varFound)))
    )
);
If(
    varSent,
    Set(varResp, IfError('POU-ProcessRequest'.Run(varReq.RequestID),
        {status: "", code: "NO_RESPONSE", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID}));
    Set(varRow, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
Set(varFinal, If(IsBlank(varRow), Coalesce(varResp.status, ""), varRow.RequestStatus.Value));
Set(varText, If(IsBlank(varRow), Coalesce(varResp.message, ""), Coalesce(varRow.ResultMessage, varResp.message, "")));
Set(varEffect, If(IsBlank(varRow), Coalesce(varResp.effect, ""), Coalesce(varRow.InventoryEffect.Value, "")));
Set(varShort, Left(varReq.RequestID, 8));
If(
    varFinal = "Succeeded",
        Set(varPolling, false); Set(varOutKind, "ok"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtyScan);
If(
    varOutKind = "bad",
    UpdateContext({locSel: IfError(LookUp(POUStockLocations, StockKey = locSel.StockKey), locSel)}),
    Reset(txtItemScan); Reset(txtLocScan); Clear(colStock); UpdateContext({locSel: Blank()}); SetFocus(txtItemScan)
);
If(varOutKind = "ok" And varLogoutAfter, If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)),
    varFinal = "Rejected",
        Set(varPolling, false); Set(varOutKind, "bad"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtyScan);
If(
    varOutKind = "bad",
    UpdateContext({locSel: IfError(LookUp(POUStockLocations, StockKey = locSel.StockKey), locSel)}),
    Reset(txtItemScan); Reset(txtLocScan); Clear(colStock); UpdateContext({locSel: Blank()}); SetFocus(txtItemScan)
);
If(varOutKind = "ok" And varLogoutAfter, If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)),
    varFinal = "AwaitingSupervisor",
        Set(varPolling, false); Set(varOutKind, "wait");
        Set(varOutText, "Waiting for a supervisor to approve (request " & varShort & "). Nothing has been changed yet. It appears under History.");
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtyScan);
If(
    varOutKind = "bad",
    UpdateContext({locSel: IfError(LookUp(POUStockLocations, StockKey = locSel.StockKey), locSel)}),
    Reset(txtItemScan); Reset(txtLocScan); Clear(colStock); UpdateContext({locSel: Blank()}); SetFocus(txtItemScan)
);
If(varOutKind = "ok" And varLogoutAfter, If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)),
    varFinal = "Failed",
        Set(varPolling, false); Set(varOutKind, "bad");
        Set(varOutText, varText & If(varEffect = "NotApplied", "", " The quantity MAY have changed. Do not repeat this. Tell a supervisor (request " & varShort & ")."));
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtyScan);
If(
    varOutKind = "bad",
    UpdateContext({locSel: IfError(LookUp(POUStockLocations, StockKey = locSel.StockKey), locSel)}),
    Reset(txtItemScan); Reset(txtLocScan); Clear(colStock); UpdateContext({locSel: Blank()}); SetFocus(txtItemScan)
);
If(varOutKind = "ok" And varLogoutAfter, If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & varShort & "). Do not enter it again. Press 'Retry same request' or wait: it cannot post twice and it finishes automatically.");
    Set(varPolling, true)
),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The app could not confirm that the server received it. Do not enter it again: press 'Retry same request' - the same request number is reused, so it cannot post twice.");
    Set(varPolling, false)
);
Set(varBusy, false)
)
```

### `lblStep1Scan` (Label)

**Text**

```powerfx
="1  Scan the item"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtItemScan` (Text input)

**HintText**

```powerfx
="Scan or type item number"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=UpdateContext({locPending: true, locLastKey: Now()});
Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**TabIndex**

```powerfx
=1
```

### `btnFindScan` (Button)

**Text**

```powerfx
="Look up"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locPending: false, locSel: Blank(), locMsg: ""});
Reset(txtQtyScan); Reset(txtLocScan);
With(
    {scan: Upper(Trim(Substitute(txtItemScan.Text, "*", "")))},
    If(
        Len(scan) < varScanMin,
        UpdateContext({locMsg: "Scan or type the item number."}),
        Set(varLookupFailed, false);
        IfError(
            ClearCollect(colStock, SortByColumns(Filter(POUStockLocations, ItemID = scan, Active = true), "LocationCode", SortOrder.Ascending)),
            Set(varLookupFailed, true); Clear(colStock);
            UpdateContext({locMsg: "Could not look the item up (network?). Nothing was changed. Scan it again."})
        );
        If(
            Not(varLookupFailed),
            If(
                CountRows(colStock) = 0,
                UpdateContext({locMsg: If(
                    Not(IsBlank(LookUp(POUItems, ItemID = scan))),
                    "Item " & scan & " exists but is not stocked in any active location. A supervisor can add a stocking location (New item screen).",
                    "Item " & scan & " was not found. Check the barcode, or ask a supervisor to add the item.")}),
                CountRows(colStock) = 1,
                UpdateContext({locSel: First(colStock)}); SetFocus(txtQtyScan),
                UpdateContext({locMsg: "Item " & scan & " is stocked in " & CountRows(colStock) & " locations. Choose or scan the location."});
                SetFocus(txtLocScan)
            )
        )
    )
)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**TabIndex**

```powerfx
=2
```

### `lblStep2Scan` (Label)

**Text**

```powerfx
="2  Location (only when the item is in several places)"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtLocScan` (Text input)

**HintText**

```powerfx
="Scan or type location"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=UpdateContext({locLocPending: true, locLastKey: Now()});
Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**TabIndex**

```powerfx
=3
```

**Visible**

```powerfx
=CountRows(colStock) > 1
```

### `btnLocScan` (Button)

**Text**

```powerfx
="Use location"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locLocPending: false});
With(
    {loc: Upper(Trim(Substitute(txtLocScan.Text, "*", "")))},
    If(
        CountRows(colStock) = 0,
        UpdateContext({locMsg: "Scan the item first."}),
        IsBlank(LookUp(colStock, LocationCode = loc)),
        UpdateContext({locSel: Blank(), locMsg: "Item " & First(colStock).ItemID & " is not stocked at " & loc & ". Choose a listed location, or ask a supervisor to add that location."}),
        UpdateContext({locSel: LookUp(colStock, LocationCode = loc)}); UpdateContext({locMsg: ""}); SetFocus(txtQtyScan)
    )
)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**Visible**

```powerfx
=CountRows(colStock) > 1
```

**TabIndex**

```powerfx
=4
```

### `tmrScanScan` (Timer)

**Duration**

```powerfx
=150
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=If(
    locPending And DateDiff(locLastKey, Now(), Milliseconds) >= varScanIdle,
    Select(btnFindScan)
);
If(
    locLocPending And DateDiff(locLastKey, Now(), Milliseconds) >= varScanIdle,
    Select(btnLocScan)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `lblMsgScan` (Label)

**Text**

```powerfx
=locMsg
```

**Color**

```powerfx
=RGBA(156, 0, 6, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=Not(IsBlank(locMsg))
```

### `galLocScan` (Vertical gallery)

**Items**

```powerfx
=colStock
```

**Visible**

```powerfx
=CountRows(colStock) > 1
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locSel: ThisItem});
UpdateContext({locMsg: ""});
SetFocus(txtQtyScan)
```

### `lblGalLocScan` (Label)

**Text**

```powerfx
=ThisItem.LocationCode & "   on hand: " & If(IsBlank(ThisItem.OnHandQty), "-", Text(ThisItem.OnHandQty))
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblNameScan` (Label)

**Text**

```powerfx
=If(IsBlank(locSel), If(CountRows(colStock) > 1, First(colStock).ItemName & "  -  choose a location", ""), locSel.ItemName)
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblMetaScan` (Label)

**Text**

```powerfx
=If(IsBlank(locSel), "", "Item " & locSel.ItemID & "   |   Location " & locSel.LocationCode & "   |   Area " & Coalesce(locSel.Area, "-") & "   |   Min " & Coalesce(Text(locSel.MinQty), "-") & "   Max " & Coalesce(Text(locSel.MaxQty), "-"))
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblOnHandScan` (Label)

**Text**

```powerfx
=If(IsBlank(locSel), "", If(IsBlank(locSel.OnHandQty), "-", Text(locSel.OnHandQty)))
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblStatusScan` (Label)

**Text**

```powerfx
=If(IsBlank(locSel), "", IsBlank(locSel.OnHandQty), "NO VERIFIED QUANTITY - a supervisor must count this item/location first", locSel.BalanceStatus.Value = "Unverified", "Quantity not yet verified by a count", locSel.LowStockFlag, "LOW STOCK", "")
```

**Color**

```powerfx
=RGBA(156, 87, 0, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblStep3Scan` (Label)

**Text**

```powerfx
="3  Quantity"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtQtyScan` (Text input)

**HintText**

```powerfx
="Quantity"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=5
```

### `lblQtyHintScan` (Label)

**Text**

```powerfx
=If(
    IsBlank(txtQtyScan.Text), "",
    Not(IsMatch(txtQtyScan.Text, "^[1-9][0-9]{0,3}$")), "Quantity must be a whole number from 1 to 9999. Was a barcode scanned into this box?",
    And(Not(IsBlank(locSel)), Not(IsBlank(locSel.OnHandQty)), Value(txtQtyScan.Text) > locSel.OnHandQty), "Only " & locSel.OnHandQty & " on hand here - REMOVE would be refused; ADD limit is " & varMaxAdd & ".",
    Value(txtQtyScan.Text) > varMaxAdd, "ADD is limited to " & varMaxAdd & " at once. Was a part number scanned here?",
    ""
)
```

**Color**

```powerfx
=RGBA(156, 0, 6, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnAddScan` (Button)

**Text**

```powerfx
="ADD"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), Not(IsBlank(locSel)), Not(IsBlank(locSel.OnHandQty)), If(IsMatch(Trim(txtQtyScan.Text), "^[1-9][0-9]{0,3}$"), Value(Trim(txtQtyScan.Text)) <= varMaxAdd, false)),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: "RECEIPT", StockKey: locSel.StockKey, ItemID: locSel.ItemID, LocationCode: locSel.LocationCode, Quantity: Trim(txtQtyScan.Text), ExpectedVersion: "", Reason: "", PayloadJson: "", TargetRequestID: "", Decision: "", ReversesLedgerKey: "", Summary: "ADD " & Trim(txtQtyScan.Text) & " x " & locSel.ItemID & " @ " & locSel.LocationCode & " by " & varEmpName & " at " & varStation});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunScan)
)
```

**Fill**

```powerfx
=RGBA(84, 130, 53, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(Not(varBusy), IsBlank(varReq), Not(IsBlank(locSel)), Not(IsBlank(locSel.OnHandQty)), If(IsMatch(Trim(txtQtyScan.Text), "^[1-9][0-9]{0,3}$"), Value(Trim(txtQtyScan.Text)) <= varMaxAdd, false)), DisplayMode.Edit, DisplayMode.Disabled)
```

**Visible**

```powerfx
=IsBlank(varReq)
```

**TabIndex**

```powerfx
=6
```

### `btnRemoveScan` (Button)

**Text**

```powerfx
="REMOVE"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), Not(IsBlank(locSel)), Not(IsBlank(locSel.OnHandQty)), IsMatch(Trim(txtQtyScan.Text), "^[1-9][0-9]{0,3}$")),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: "ISSUE", StockKey: locSel.StockKey, ItemID: locSel.ItemID, LocationCode: locSel.LocationCode, Quantity: Trim(txtQtyScan.Text), ExpectedVersion: "", Reason: "", PayloadJson: "", TargetRequestID: "", Decision: "", ReversesLedgerKey: "", Summary: "REMOVE " & Trim(txtQtyScan.Text) & " x " & locSel.ItemID & " @ " & locSel.LocationCode & " by " & varEmpName & " at " & varStation});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunScan)
)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(Not(varBusy), IsBlank(varReq), Not(IsBlank(locSel)), Not(IsBlank(locSel.OnHandQty)), IsMatch(Trim(txtQtyScan.Text), "^[1-9][0-9]{0,3}$")), DisplayMode.Edit, DisplayMode.Disabled)
```

**Visible**

```powerfx
=IsBlank(varReq)
```

**TabIndex**

```powerfx
=7
```

### `btnRetryScan` (Button)

**Text**

```powerfx
="Retry same request (" & Left(varReq.RequestID, 8) & ")"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Select(btnRunScan)
```

**Fill**

```powerfx
=RGBA(191, 144, 0, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(varBusy, DisplayMode.Disabled, DisplayMode.Edit)
```

**Visible**

```powerfx
=Not(IsBlank(varReq))
```

**TabIndex**

```powerfx
=6
```

### `tmrPollScan` (Timer)

**Duration**

```powerfx
=varPollSec * 1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=varPolling And Not(IsBlank(varReq))
```

**OnTimerEnd**

```powerfx
=If(
    IsBlank(varReq) Or Not(varPolling),
    Set(varPolling, false),
    Set(varPollTries, varPollTries + 1);
    Set(varResp, {status: "", code: "POLL", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID});
    Set(varRow, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
Set(varFinal, If(IsBlank(varRow), Coalesce(varResp.status, ""), varRow.RequestStatus.Value));
Set(varText, If(IsBlank(varRow), Coalesce(varResp.message, ""), Coalesce(varRow.ResultMessage, varResp.message, "")));
Set(varEffect, If(IsBlank(varRow), Coalesce(varResp.effect, ""), Coalesce(varRow.InventoryEffect.Value, "")));
Set(varShort, Left(varReq.RequestID, 8));
If(
    varFinal = "Succeeded",
        Set(varPolling, false); Set(varOutKind, "ok"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtyScan);
If(
    varOutKind = "bad",
    UpdateContext({locSel: IfError(LookUp(POUStockLocations, StockKey = locSel.StockKey), locSel)}),
    Reset(txtItemScan); Reset(txtLocScan); Clear(colStock); UpdateContext({locSel: Blank()}); SetFocus(txtItemScan)
);
If(varOutKind = "ok" And varLogoutAfter, If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)),
    varFinal = "Rejected",
        Set(varPolling, false); Set(varOutKind, "bad"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtyScan);
If(
    varOutKind = "bad",
    UpdateContext({locSel: IfError(LookUp(POUStockLocations, StockKey = locSel.StockKey), locSel)}),
    Reset(txtItemScan); Reset(txtLocScan); Clear(colStock); UpdateContext({locSel: Blank()}); SetFocus(txtItemScan)
);
If(varOutKind = "ok" And varLogoutAfter, If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)),
    varFinal = "AwaitingSupervisor",
        Set(varPolling, false); Set(varOutKind, "wait");
        Set(varOutText, "Waiting for a supervisor to approve (request " & varShort & "). Nothing has been changed yet. It appears under History.");
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtyScan);
If(
    varOutKind = "bad",
    UpdateContext({locSel: IfError(LookUp(POUStockLocations, StockKey = locSel.StockKey), locSel)}),
    Reset(txtItemScan); Reset(txtLocScan); Clear(colStock); UpdateContext({locSel: Blank()}); SetFocus(txtItemScan)
);
If(varOutKind = "ok" And varLogoutAfter, If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)),
    varFinal = "Failed",
        Set(varPolling, false); Set(varOutKind, "bad");
        Set(varOutText, varText & If(varEffect = "NotApplied", "", " The quantity MAY have changed. Do not repeat this. Tell a supervisor (request " & varShort & ")."));
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtyScan);
If(
    varOutKind = "bad",
    UpdateContext({locSel: IfError(LookUp(POUStockLocations, StockKey = locSel.StockKey), locSel)}),
    Reset(txtItemScan); Reset(txtLocScan); Clear(colStock); UpdateContext({locSel: Blank()}); SetFocus(txtItemScan)
);
If(varOutKind = "ok" And varLogoutAfter, If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & varShort & "). Do not enter it again. Press 'Retry same request' or wait: it cannot post twice and it finishes automatically.");
    Set(varPolling, true)
);
    If(
        varPolling And varPollTries * varPollSec >= varPollMax,
        Set(varPolling, false);
        Set(varOutText, "STILL NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The background job completes pending requests every few minutes. Do not enter it again; check History, or press 'Retry same request'.")
    )
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `lblBannerScan` (Label)

**Text**

```powerfx
=varOutText
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=If(varOutKind = "ok", RGBA(198, 239, 206, 1), varOutKind = "bad", RGBA(255, 199, 206, 1), RGBA(255, 230, 153, 1))
```

**Visible**

```powerfx
=Not(IsBlank(varOutText))
```

## scrAudit - Physical count / audit

Blind count. The record's StockVersion is captured when the item is selected (the count BEGINS); the request carries it as ExpectedVersion and the server refuses the count (STALE_COUNT) if any posting happened since. Supervisor approval is required by default (RequireSupervisorForAudit).

**Screen properties**

- `Fill`
  ```powerfx
  =RGBA(242, 242, 242, 1)
  ```
- `OnVisible`
  ```powerfx
  =If(IsBlank(varSession) And Not(varSupMode), Navigate(scrLogin, ScreenTransition.None));
  Set(varLastActivity, Now());
  UpdateContext({locSel: Blank(), locMsg: "", locPending: false, locLocPending: false, locLastKey: Now(), locReview: false, locFresh: Blank(), locVer: 0});
  If(IsBlank(varReq), Clear(colStock); Reset(txtItemAudit); Reset(txtLocAudit); Reset(txtCountAudit); SetFocus(txtItemAudit))
  ```

| Control | Type | Purpose |
|---|---|---|
| `recHdrAudit` | Rectangle | Header band |
| `lblHdrStationAudit` | Label | Station identity (always visible) |
| `lblHdrUserAudit` | Label | Employee identity (always visible) |
| `lblHdrIdleAudit` | Label | Idle countdown |
| `btnHdrOutAudit` | Button | Ends the server session |
| `tmrIdleAudit` | Timer | Idle timeout checker (central setting IdleTimeoutMinutes) |
| `btnNavScanAudit` | Button | Go to scrScan |
| `btnNavAuditAudit` | Button | Go to scrAudit |
| `btnNavAddItemAudit` | Button | Go to scrAddItem |
| `btnNavLowAudit` | Button | Go to scrLowStock |
| `btnNavHistAudit` | Button | Go to scrHistory |
| `btnNavSupAudit` | Button | Go to scrSupervisor |
| `btnNavAdminAudit` | Button | Go to scrAdmin |
| `btnRunAudit` | Button | Tiny transparent button. Runs the shared posting procedure for the retained request varReq; never creates a new RequestID. |
| `lblStep1Audit` | Label |  |
| `txtItemAudit` | Text input | Scanner target. Enter/Tab suffix from the scanner ends the scan; the timer commits it. |
| `btnFindAudit` | Button | Resolves the scan; also called by the scan timer |
| `lblStep2Audit` | Label |  |
| `txtLocAudit` | Text input | Second scan target |
| `btnLocAudit` | Button | Resolves the location scan; also called by the scan timer |
| `tmrScanAudit` | Timer | Debounce: commits a scan once keystrokes stop for ScanCommitIdleMs, so Enter/Tab/no-suffix scanners all work |
| `lblMsgAudit` | Label | Lookup messages |
| `galLocAudit` | Vertical gallery | Choose the location when an item is stocked in more than one place |
| `lblGalLocAudit` | Label |  |
| `lblAudNameAudit` | Label | What is being counted. The system quantity is deliberately hidden until the count is entered (blind count). |
| `lblStep3Audit` | Label |  |
| `txtCountAudit` | Text input | Whole number 0-999999. |
| `lblCountHintAudit` | Label |  |
| `btnReviewAudit` | Button | Re-reads the record and shows the variance before anything is filed |
| `lblReviewAudit` | Label | Result of the review |
| `btnRecountAudit` | Button | Reloads the record and restarts the count from its current version |
| `btnPostCountAudit` | Button | Variance >= AuditConfirmVariance needs this explicit second confirmation. If a supervisor approval is required the request waits (nothing changes until approved). |
| `btnRetryAudit` | Button |  |
| `tmrPollAudit` | Timer |  |
| `lblBannerAudit` | Label | Outcome of the last request: ok / waiting / unconfirmed / bad |

### `recHdrAudit` (Rectangle)

**Fill**

```powerfx
=RGBA(31, 56, 100, 1)
```

### `lblHdrStationAudit` (Label)

**Text**

```powerfx
="Station " & varStation
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrUserAudit` (Label)

**Text**

```powerfx
=If(varSupMode, varEmpName & " (supervisor, signed in as " & User().Email & ")", varEmpName & " - badge session")
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrIdleAudit` (Label)

**Text**

```powerfx
="Auto sign-out in " & Max(0, varIdleMin * 60 - DateDiff(varLastActivity, varTick, Seconds)) & " s"
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnHdrOutAudit` (Button)

**Text**

```powerfx
="Sign out"
```

**OnSelect**

```powerfx
=If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `tmrIdleAudit` (Timer)

**Duration**

```powerfx
=1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=Set(varTick, Now());
If(
    (Not(IsBlank(varSession)) Or varSupMode) And DateDiff(varLastActivity, varTick, Seconds) >= varIdleMin * 60,
    If(
        Not(IsBlank(varSession)),
        IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
    );
    Set(varSession, "");
    Set(varEmpName, "");
    Set(varRole, "");
    Set(varSupMode, false);
    Clear(colStock);
    Navigate(scrLogin, ScreenTransition.None)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `btnNavScanAudit` (Button)

**Text**

```powerfx
="Add / Remove"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrScan, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=Not(varSupMode)
```

### `btnNavAuditAudit` (Button)

**Text**

```powerfx
="Count"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAudit, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavAddItemAudit` (Button)

**Text**

```powerfx
="New item"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAddItem, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavLowAudit` (Button)

**Text**

```powerfx
="Low stock"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrLowStock, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavHistAudit` (Button)

**Text**

```powerfx
="History"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrHistory, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavSupAudit` (Button)

**Text**

```powerfx
="Supervisor"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrSupervisor, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnNavAdminAudit` (Button)

**Text**

```powerfx
="Admin"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAdmin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnRunAudit` (Button)

**Text**

```powerfx
=""
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**OnSelect**

```powerfx
=If(
    IsBlank(varReq) Or varBusy,
    false,
    Set(varBusy, true);
Set(varOutKind, "");
Set(varOutText, "");
Set(varLookupFailed, false);
Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Set(varLookupFailed, true); Blank()));
Set(varSent, Not(IsBlank(varFound)));
If(
    Not(varSent) And Not(varLookupFailed),
    Set(varCreateFailed, false);
    IfError(Patch(POURequests, Defaults(POURequests), {
        Title: varReq.Summary,
        RequestID: varReq.RequestID,
        RequestType: {Value: varReq.RequestType},
        RequestStatus: {Value: "Pending"},
        IsOpen: true,
        SessionID: varReq.SessionID,
        StationID: varReq.Station,
        StockKey: varReq.StockKey,
        ItemID: varReq.ItemID,
        LocationCode: varReq.LocationCode,
        Quantity: If(IsBlank(varReq.Quantity), Blank(), Value(varReq.Quantity)),
        ExpectedVersion: If(IsBlank(varReq.ExpectedVersion), Blank(), Value(varReq.ExpectedVersion)),
        PayloadJson: varReq.PayloadJson,
        Reason: varReq.Reason,
        ReversesLedgerKey: varReq.ReversesLedgerKey,
        TargetRequestID: varReq.TargetRequestID,
        Decision: If(IsBlank(varReq.Decision), Blank(), {Value: varReq.Decision}),
        ClientLocalTime: Text(Now(), "yyyy-mm-dd hh:mm:ss")
    }), Set(varCreateFailed, true));
    Set(varSent, Not(varCreateFailed));
    If(
        varCreateFailed,
        Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
        Set(varSent, Not(IsBlank(varFound)))
    )
);
If(
    varSent,
    Set(varResp, IfError('POU-ProcessRequest'.Run(varReq.RequestID),
        {status: "", code: "NO_RESPONSE", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID}));
    Set(varRow, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
Set(varFinal, If(IsBlank(varRow), Coalesce(varResp.status, ""), varRow.RequestStatus.Value));
Set(varText, If(IsBlank(varRow), Coalesce(varResp.message, ""), Coalesce(varRow.ResultMessage, varResp.message, "")));
Set(varEffect, If(IsBlank(varRow), Coalesce(varResp.effect, ""), Coalesce(varRow.InventoryEffect.Value, "")));
Set(varShort, Left(varReq.RequestID, 8));
If(
    varFinal = "Succeeded",
        Set(varPolling, false); Set(varOutKind, "ok"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtCountAudit);
UpdateContext({locReview: false, locSel: Blank(), locFresh: Blank()});
Reset(txtItemAudit); Reset(txtLocAudit); Clear(colStock); SetFocus(txtItemAudit),
    varFinal = "Rejected",
        Set(varPolling, false); Set(varOutKind, "bad"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtCountAudit);
UpdateContext({locReview: false, locSel: Blank(), locFresh: Blank()});
Reset(txtItemAudit); Reset(txtLocAudit); Clear(colStock); SetFocus(txtItemAudit),
    varFinal = "AwaitingSupervisor",
        Set(varPolling, false); Set(varOutKind, "wait");
        Set(varOutText, "Waiting for a supervisor to approve (request " & varShort & "). Nothing has been changed yet. It appears under History.");
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtCountAudit);
UpdateContext({locReview: false, locSel: Blank(), locFresh: Blank()});
Reset(txtItemAudit); Reset(txtLocAudit); Clear(colStock); SetFocus(txtItemAudit),
    varFinal = "Failed",
        Set(varPolling, false); Set(varOutKind, "bad");
        Set(varOutText, varText & If(varEffect = "NotApplied", "", " The quantity MAY have changed. Do not repeat this. Tell a supervisor (request " & varShort & ")."));
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtCountAudit);
UpdateContext({locReview: false, locSel: Blank(), locFresh: Blank()});
Reset(txtItemAudit); Reset(txtLocAudit); Clear(colStock); SetFocus(txtItemAudit),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & varShort & "). Do not enter it again. Press 'Retry same request' or wait: it cannot post twice and it finishes automatically.");
    Set(varPolling, true)
),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The app could not confirm that the server received it. Do not enter it again: press 'Retry same request' - the same request number is reused, so it cannot post twice.");
    Set(varPolling, false)
);
Set(varBusy, false)
)
```

### `lblStep1Audit` (Label)

**Text**

```powerfx
="1  Scan the item"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtItemAudit` (Text input)

**HintText**

```powerfx
="Scan or type item number"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=UpdateContext({locPending: true, locLastKey: Now()});
Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**TabIndex**

```powerfx
=1
```

### `btnFindAudit` (Button)

**Text**

```powerfx
="Look up"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locPending: false, locSel: Blank(), locMsg: ""});
Reset(txtCountAudit); Reset(txtLocAudit);
With(
    {scan: Upper(Trim(Substitute(txtItemAudit.Text, "*", "")))},
    If(
        Len(scan) < varScanMin,
        UpdateContext({locMsg: "Scan or type the item number."}),
        Set(varLookupFailed, false);
        IfError(
            ClearCollect(colStock, SortByColumns(Filter(POUStockLocations, ItemID = scan, Active = true), "LocationCode", SortOrder.Ascending)),
            Set(varLookupFailed, true); Clear(colStock);
            UpdateContext({locMsg: "Could not look the item up (network?). Nothing was changed. Scan it again."})
        );
        If(
            Not(varLookupFailed),
            If(
                CountRows(colStock) = 0,
                UpdateContext({locMsg: If(
                    Not(IsBlank(LookUp(POUItems, ItemID = scan))),
                    "Item " & scan & " exists but is not stocked in any active location. A supervisor can add a stocking location (New item screen).",
                    "Item " & scan & " was not found. Check the barcode, or ask a supervisor to add the item.")}),
                CountRows(colStock) = 1,
                UpdateContext({locSel: First(colStock), locVer: First(colStock).StockVersion, locReview: false, locFresh: Blank()}); SetFocus(txtCountAudit),
                UpdateContext({locMsg: "Item " & scan & " is stocked in " & CountRows(colStock) & " locations. Choose or scan the location."});
                SetFocus(txtLocAudit)
            )
        )
    )
)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**TabIndex**

```powerfx
=2
```

### `lblStep2Audit` (Label)

**Text**

```powerfx
="2  Location (only when the item is in several places)"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtLocAudit` (Text input)

**HintText**

```powerfx
="Scan or type location"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=UpdateContext({locLocPending: true, locLastKey: Now()});
Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**TabIndex**

```powerfx
=3
```

**Visible**

```powerfx
=CountRows(colStock) > 1
```

### `btnLocAudit` (Button)

**Text**

```powerfx
="Use location"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locLocPending: false});
With(
    {loc: Upper(Trim(Substitute(txtLocAudit.Text, "*", "")))},
    If(
        CountRows(colStock) = 0,
        UpdateContext({locMsg: "Scan the item first."}),
        IsBlank(LookUp(colStock, LocationCode = loc)),
        UpdateContext({locSel: Blank(), locMsg: "Item " & First(colStock).ItemID & " is not stocked at " & loc & ". Choose a listed location, or ask a supervisor to add that location."}),
        UpdateContext({locSel: LookUp(colStock, LocationCode = loc), locVer: LookUp(colStock, LocationCode = loc).StockVersion, locReview: false, locFresh: Blank()}); UpdateContext({locMsg: ""}); SetFocus(txtCountAudit)
    )
)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**Visible**

```powerfx
=CountRows(colStock) > 1
```

**TabIndex**

```powerfx
=4
```

### `tmrScanAudit` (Timer)

**Duration**

```powerfx
=150
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=If(
    locPending And DateDiff(locLastKey, Now(), Milliseconds) >= varScanIdle,
    Select(btnFindAudit)
);
If(
    locLocPending And DateDiff(locLastKey, Now(), Milliseconds) >= varScanIdle,
    Select(btnLocAudit)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `lblMsgAudit` (Label)

**Text**

```powerfx
=locMsg
```

**Color**

```powerfx
=RGBA(156, 0, 6, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=Not(IsBlank(locMsg))
```

### `galLocAudit` (Vertical gallery)

**Items**

```powerfx
=colStock
```

**Visible**

```powerfx
=CountRows(colStock) > 1
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locSel: ThisItem, locVer: ThisItem.StockVersion, locReview: false, locFresh: Blank()});
UpdateContext({locMsg: ""});
SetFocus(txtCountAudit)
```

### `lblGalLocAudit` (Label)

**Text**

```powerfx
=ThisItem.LocationCode & "   on hand: " & If(IsBlank(ThisItem.OnHandQty), "-", Text(ThisItem.OnHandQty))
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblAudNameAudit` (Label)

**Text**

```powerfx
=If(IsBlank(locSel), "", locSel.ItemName & "   |   " & locSel.ItemID & " @ " & locSel.LocationCode & "   (count started at record version " & locVer & ")")
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblStep3Audit` (Label)

**Text**

```powerfx
="3  Counted quantity (physical count, 0 or more)"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtCountAudit` (Text input)

**HintText**

```powerfx
="Counted quantity"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locReview: false, locFresh: Blank()})
```

**DisplayMode**

```powerfx
=If(And(IsBlank(varReq), Not(IsBlank(locSel))), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=5
```

### `lblCountHintAudit` (Label)

**Text**

```powerfx
=If(IsBlank(txtCountAudit.Text), "", Not(IsMatch(Trim(txtCountAudit.Text), "^(0|[1-9][0-9]{0,5})$")), "Counted quantity must be a whole number, 0 or more. Was a barcode scanned into this box?", "")
```

**Color**

```powerfx
=RGBA(156, 0, 6, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnReviewAudit` (Button)

**Text**

```powerfx
="Review count"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
IfError(
    UpdateContext({locFresh: LookUp(POUStockLocations, StockKey = locSel.StockKey), locReview: true, locMsg: ""}),
    UpdateContext({locMsg: "Could not re-read the current quantity (network?). Nothing was changed. Press Review again."})
)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(IsBlank(varReq), Not(IsBlank(locSel)), IsMatch(Trim(txtCountAudit.Text), "^(0|[1-9][0-9]{0,5})$")), DisplayMode.Edit, DisplayMode.Disabled)
```

**Visible**

```powerfx
=IsBlank(varReq)
```

**TabIndex**

```powerfx
=6
```

### `lblReviewAudit` (Label)

**Text**

```powerfx
=If(
    Not(locReview) Or IsBlank(locFresh), "",
    And(locReview, Not(IsBlank(locFresh)), locFresh.StockVersion <> locVer), "STOCK MOVED while you were counting: the record changed from version " & locVer & " to " & locFresh.StockVersion & " (an ADD, REMOVE or other posting happened). RECOUNT.",
    IsBlank(locFresh.OnHandQty), "FIRST COUNT. Counted " & Trim(txtCountAudit.Text) & ". There is no previous balance; this count becomes the verified starting quantity.",
    "Counted " & Trim(txtCountAudit.Text) & "   |   System says " & locFresh.OnHandQty & "   |   Variance " & Text((Value(Trim(txtCountAudit.Text)) - locFresh.OnHandQty), "+0;-0;0")
)
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=If(And(locReview, Not(IsBlank(locFresh)), locFresh.StockVersion <> locVer), RGBA(255, 199, 206, 1), And(locReview, Not(IsBlank(locFresh.OnHandQty)), Abs((Value(Trim(txtCountAudit.Text)) - locFresh.OnHandQty)) >= varAuditVar), RGBA(255, 230, 153, 1), RGBA(221, 235, 247, 1))
```

**Visible**

```powerfx
=locReview
```

### `btnRecountAudit` (Button)

**Text**

```powerfx
="Recount"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Reset(txtCountAudit);
UpdateContext({locReview: false, locFresh: Blank(), locVer: LookUp(POUStockLocations, StockKey = locSel.StockKey).StockVersion, locSel: LookUp(POUStockLocations, StockKey = locSel.StockKey)});
SetFocus(txtCountAudit)
```

**Fill**

```powerfx
=RGBA(191, 144, 0, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=locReview And IsBlank(varReq)
```

**TabIndex**

```powerfx
=8
```

### `btnPostCountAudit` (Button)

**Text**

```powerfx
=If(And(locReview, Not(IsBlank(locFresh.OnHandQty)), Abs((Value(Trim(txtCountAudit.Text)) - locFresh.OnHandQty)) >= varAuditVar), "Variance is " & Text((Value(Trim(txtCountAudit.Text)) - locFresh.OnHandQty), "+0;-0;0") & " - I recounted. POST COUNT", "POST COUNT")
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), locReview, Not(IsBlank(locSel)), IsMatch(Trim(txtCountAudit.Text), "^(0|[1-9][0-9]{0,5})$"), Not(And(locReview, Not(IsBlank(locFresh)), locFresh.StockVersion <> locVer))),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: "AUDIT", StockKey: locSel.StockKey, ItemID: locSel.ItemID, LocationCode: locSel.LocationCode, Quantity: Trim(txtCountAudit.Text), ExpectedVersion: Text(locVer), Reason: "", PayloadJson: "", TargetRequestID: "", Decision: "", ReversesLedgerKey: "", Summary: "COUNT " & Trim(txtCountAudit.Text) & " x " & locSel.ItemID & " @ " & locSel.LocationCode & " by " & varEmpName & " at " & varStation});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunAudit)
)
```

**Fill**

```powerfx
=If(And(locReview, Not(IsBlank(locFresh.OnHandQty)), Abs((Value(Trim(txtCountAudit.Text)) - locFresh.OnHandQty)) >= varAuditVar), RGBA(192, 80, 77, 1), RGBA(84, 130, 53, 1))
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(locReview, Not(And(locReview, Not(IsBlank(locFresh)), locFresh.StockVersion <> locVer)), Not(varBusy)), DisplayMode.Edit, DisplayMode.Disabled)
```

**Visible**

```powerfx
=IsBlank(varReq)
```

**TabIndex**

```powerfx
=7
```

### `btnRetryAudit` (Button)

**Text**

```powerfx
="Retry same request (" & Left(varReq.RequestID, 8) & ")"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Select(btnRunAudit)
```

**Fill**

```powerfx
=RGBA(191, 144, 0, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(varBusy, DisplayMode.Disabled, DisplayMode.Edit)
```

**Visible**

```powerfx
=Not(IsBlank(varReq))
```

**TabIndex**

```powerfx
=7
```

### `tmrPollAudit` (Timer)

**Duration**

```powerfx
=varPollSec * 1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=varPolling And Not(IsBlank(varReq))
```

**OnTimerEnd**

```powerfx
=If(
    IsBlank(varReq) Or Not(varPolling),
    Set(varPolling, false),
    Set(varPollTries, varPollTries + 1);
    Set(varResp, {status: "", code: "POLL", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID});
    Set(varRow, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
Set(varFinal, If(IsBlank(varRow), Coalesce(varResp.status, ""), varRow.RequestStatus.Value));
Set(varText, If(IsBlank(varRow), Coalesce(varResp.message, ""), Coalesce(varRow.ResultMessage, varResp.message, "")));
Set(varEffect, If(IsBlank(varRow), Coalesce(varResp.effect, ""), Coalesce(varRow.InventoryEffect.Value, "")));
Set(varShort, Left(varReq.RequestID, 8));
If(
    varFinal = "Succeeded",
        Set(varPolling, false); Set(varOutKind, "ok"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtCountAudit);
UpdateContext({locReview: false, locSel: Blank(), locFresh: Blank()});
Reset(txtItemAudit); Reset(txtLocAudit); Clear(colStock); SetFocus(txtItemAudit),
    varFinal = "Rejected",
        Set(varPolling, false); Set(varOutKind, "bad"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtCountAudit);
UpdateContext({locReview: false, locSel: Blank(), locFresh: Blank()});
Reset(txtItemAudit); Reset(txtLocAudit); Clear(colStock); SetFocus(txtItemAudit),
    varFinal = "AwaitingSupervisor",
        Set(varPolling, false); Set(varOutKind, "wait");
        Set(varOutText, "Waiting for a supervisor to approve (request " & varShort & "). Nothing has been changed yet. It appears under History.");
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtCountAudit);
UpdateContext({locReview: false, locSel: Blank(), locFresh: Blank()});
Reset(txtItemAudit); Reset(txtLocAudit); Clear(colStock); SetFocus(txtItemAudit),
    varFinal = "Failed",
        Set(varPolling, false); Set(varOutKind, "bad");
        Set(varOutText, varText & If(varEffect = "NotApplied", "", " The quantity MAY have changed. Do not repeat this. Tell a supervisor (request " & varShort & ")."));
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtCountAudit);
UpdateContext({locReview: false, locSel: Blank(), locFresh: Blank()});
Reset(txtItemAudit); Reset(txtLocAudit); Clear(colStock); SetFocus(txtItemAudit),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & varShort & "). Do not enter it again. Press 'Retry same request' or wait: it cannot post twice and it finishes automatically.");
    Set(varPolling, true)
);
    If(
        varPolling And varPollTries * varPollSec >= varPollMax,
        Set(varPolling, false);
        Set(varOutText, "STILL NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The background job completes pending requests every few minutes. Do not enter it again; check History, or press 'Retry same request'.")
    )
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `lblBannerAudit` (Label)

**Text**

```powerfx
=varOutText
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=If(varOutKind = "ok", RGBA(198, 239, 206, 1), varOutKind = "bad", RGBA(255, 199, 206, 1), RGBA(255, 230, 153, 1))
```

**Visible**

```powerfx
=Not(IsBlank(varOutText))
```

## scrAddItem - Add item / add stocking location

Two request types: ITEM_CREATE (new item master + first location) and LOCATION_ADD (existing item, additional location). Supervisor approval is on by default (RequireSupervisorForNewItem).

**Screen properties**

- `Fill`
  ```powerfx
  =RGBA(242, 242, 242, 1)
  ```
- `OnVisible`
  ```powerfx
  =If(IsBlank(varSession) And Not(varSupMode), Navigate(scrLogin, ScreenTransition.None));
  Set(varLastActivity, Now());
  UpdateContext({locMode: "ITEM_CREATE"});
  SetFocus(txtItemIdAddItem)
  ```

| Control | Type | Purpose |
|---|---|---|
| `recHdrAddItem` | Rectangle | Header band |
| `lblHdrStationAddItem` | Label | Station identity (always visible) |
| `lblHdrUserAddItem` | Label | Employee identity (always visible) |
| `lblHdrIdleAddItem` | Label | Idle countdown |
| `btnHdrOutAddItem` | Button | Ends the server session |
| `tmrIdleAddItem` | Timer | Idle timeout checker (central setting IdleTimeoutMinutes) |
| `btnNavScanAddItem` | Button | Go to scrScan |
| `btnNavAuditAddItem` | Button | Go to scrAudit |
| `btnNavAddItemAddItem` | Button | Go to scrAddItem |
| `btnNavLowAddItem` | Button | Go to scrLowStock |
| `btnNavHistAddItem` | Button | Go to scrHistory |
| `btnNavSupAddItem` | Button | Go to scrSupervisor |
| `btnNavAdminAddItem` | Button | Go to scrAdmin |
| `btnRunAddItem` | Button | Tiny transparent button. Runs the shared posting procedure for the retained request varReq; never creates a new RequestID. |
| `lblAddHelpAddItem` | Label |  |
| `btnModeNewAddItem` | Button |  |
| `btnModeLocAddItem` | Button |  |
| `lblL1AddItem` | Label |  |
| `txtItemIdAddItem` | Text input |  |
| `lblL2AddItem` | Label |  |
| `txtNameAddItem` | Text input |  |
| `lblL3AddItem` | Label |  |
| `txtMfrAddItem` | Text input |  |
| `lblL4AddItem` | Label |  |
| `txtDescAddItem` | Text input |  |
| `lblL5AddItem` | Label |  |
| `txtLocCodeAddItem` | Text input |  |
| `lblLocOkAddItem` | Label |  |
| `lblL6AddItem` | Label |  |
| `txtAreaAddItem` | Text input |  |
| `lblL7AddItem` | Label |  |
| `txtMinAddItem` | Text input |  |
| `txtMaxAddItem` | Text input |  |
| `lblAddWhyAddItem` | Label |  |
| `lblAddNoteAddItem` | Label |  |
| `btnAddSubmitAddItem` | Button | Files ITEM_CREATE / LOCATION_ADD. The server re-validates everything, creates both rows idempotently, and sets NO quantity. |
| `btnRetryAddItem` | Button |  |
| `tmrPollAddItem` | Timer |  |
| `lblBannerAddItem` | Label | Outcome of the last request: ok / waiting / unconfirmed / bad |

### `recHdrAddItem` (Rectangle)

**Fill**

```powerfx
=RGBA(31, 56, 100, 1)
```

### `lblHdrStationAddItem` (Label)

**Text**

```powerfx
="Station " & varStation
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrUserAddItem` (Label)

**Text**

```powerfx
=If(varSupMode, varEmpName & " (supervisor, signed in as " & User().Email & ")", varEmpName & " - badge session")
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrIdleAddItem` (Label)

**Text**

```powerfx
="Auto sign-out in " & Max(0, varIdleMin * 60 - DateDiff(varLastActivity, varTick, Seconds)) & " s"
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnHdrOutAddItem` (Button)

**Text**

```powerfx
="Sign out"
```

**OnSelect**

```powerfx
=If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `tmrIdleAddItem` (Timer)

**Duration**

```powerfx
=1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=Set(varTick, Now());
If(
    (Not(IsBlank(varSession)) Or varSupMode) And DateDiff(varLastActivity, varTick, Seconds) >= varIdleMin * 60,
    If(
        Not(IsBlank(varSession)),
        IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
    );
    Set(varSession, "");
    Set(varEmpName, "");
    Set(varRole, "");
    Set(varSupMode, false);
    Clear(colStock);
    Navigate(scrLogin, ScreenTransition.None)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `btnNavScanAddItem` (Button)

**Text**

```powerfx
="Add / Remove"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrScan, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=Not(varSupMode)
```

### `btnNavAuditAddItem` (Button)

**Text**

```powerfx
="Count"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAudit, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavAddItemAddItem` (Button)

**Text**

```powerfx
="New item"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAddItem, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavLowAddItem` (Button)

**Text**

```powerfx
="Low stock"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrLowStock, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavHistAddItem` (Button)

**Text**

```powerfx
="History"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrHistory, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavSupAddItem` (Button)

**Text**

```powerfx
="Supervisor"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrSupervisor, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnNavAdminAddItem` (Button)

**Text**

```powerfx
="Admin"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAdmin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnRunAddItem` (Button)

**Text**

```powerfx
=""
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**OnSelect**

```powerfx
=If(
    IsBlank(varReq) Or varBusy,
    false,
    Set(varBusy, true);
Set(varOutKind, "");
Set(varOutText, "");
Set(varLookupFailed, false);
Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Set(varLookupFailed, true); Blank()));
Set(varSent, Not(IsBlank(varFound)));
If(
    Not(varSent) And Not(varLookupFailed),
    Set(varCreateFailed, false);
    IfError(Patch(POURequests, Defaults(POURequests), {
        Title: varReq.Summary,
        RequestID: varReq.RequestID,
        RequestType: {Value: varReq.RequestType},
        RequestStatus: {Value: "Pending"},
        IsOpen: true,
        SessionID: varReq.SessionID,
        StationID: varReq.Station,
        StockKey: varReq.StockKey,
        ItemID: varReq.ItemID,
        LocationCode: varReq.LocationCode,
        Quantity: If(IsBlank(varReq.Quantity), Blank(), Value(varReq.Quantity)),
        ExpectedVersion: If(IsBlank(varReq.ExpectedVersion), Blank(), Value(varReq.ExpectedVersion)),
        PayloadJson: varReq.PayloadJson,
        Reason: varReq.Reason,
        ReversesLedgerKey: varReq.ReversesLedgerKey,
        TargetRequestID: varReq.TargetRequestID,
        Decision: If(IsBlank(varReq.Decision), Blank(), {Value: varReq.Decision}),
        ClientLocalTime: Text(Now(), "yyyy-mm-dd hh:mm:ss")
    }), Set(varCreateFailed, true));
    Set(varSent, Not(varCreateFailed));
    If(
        varCreateFailed,
        Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
        Set(varSent, Not(IsBlank(varFound)))
    )
);
If(
    varSent,
    Set(varResp, IfError('POU-ProcessRequest'.Run(varReq.RequestID),
        {status: "", code: "NO_RESPONSE", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID}));
    Set(varRow, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
Set(varFinal, If(IsBlank(varRow), Coalesce(varResp.status, ""), varRow.RequestStatus.Value));
Set(varText, If(IsBlank(varRow), Coalesce(varResp.message, ""), Coalesce(varRow.ResultMessage, varResp.message, "")));
Set(varEffect, If(IsBlank(varRow), Coalesce(varResp.effect, ""), Coalesce(varRow.InventoryEffect.Value, "")));
Set(varShort, Left(varReq.RequestID, 8));
If(
    varFinal = "Succeeded",
        Set(varPolling, false); Set(varOutKind, "ok"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtItemIdAddItem); Reset(txtNameAddItem); Reset(txtMfrAddItem); Reset(txtDescAddItem); Reset(txtLocCodeAddItem); Reset(txtAreaAddItem); Reset(txtMinAddItem); Reset(txtMaxAddItem);
SetFocus(txtItemIdAddItem),
    varFinal = "Rejected",
        Set(varPolling, false); Set(varOutKind, "bad"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtItemIdAddItem); Reset(txtNameAddItem); Reset(txtMfrAddItem); Reset(txtDescAddItem); Reset(txtLocCodeAddItem); Reset(txtAreaAddItem); Reset(txtMinAddItem); Reset(txtMaxAddItem);
SetFocus(txtItemIdAddItem),
    varFinal = "AwaitingSupervisor",
        Set(varPolling, false); Set(varOutKind, "wait");
        Set(varOutText, "Waiting for a supervisor to approve (request " & varShort & "). Nothing has been changed yet. It appears under History.");
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtItemIdAddItem); Reset(txtNameAddItem); Reset(txtMfrAddItem); Reset(txtDescAddItem); Reset(txtLocCodeAddItem); Reset(txtAreaAddItem); Reset(txtMinAddItem); Reset(txtMaxAddItem);
SetFocus(txtItemIdAddItem),
    varFinal = "Failed",
        Set(varPolling, false); Set(varOutKind, "bad");
        Set(varOutText, varText & If(varEffect = "NotApplied", "", " The quantity MAY have changed. Do not repeat this. Tell a supervisor (request " & varShort & ")."));
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtItemIdAddItem); Reset(txtNameAddItem); Reset(txtMfrAddItem); Reset(txtDescAddItem); Reset(txtLocCodeAddItem); Reset(txtAreaAddItem); Reset(txtMinAddItem); Reset(txtMaxAddItem);
SetFocus(txtItemIdAddItem),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & varShort & "). Do not enter it again. Press 'Retry same request' or wait: it cannot post twice and it finishes automatically.");
    Set(varPolling, true)
),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The app could not confirm that the server received it. Do not enter it again: press 'Retry same request' - the same request number is reused, so it cannot post twice.");
    Set(varPolling, false)
);
Set(varBusy, false)
)
```

### `lblAddHelpAddItem` (Label)

**Text**

```powerfx
="A NEW ITEM adds the item master AND its first stocking location. To stock an EXISTING item (e.g. K102516) in another place, choose ADD LOCATION: the item is never duplicated, merged or renumbered."
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnModeNewAddItem` (Button)

**Text**

```powerfx
="NEW ITEM"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locMode: "ITEM_CREATE"})
```

**Fill**

```powerfx
=If(locMode = "ITEM_CREATE", RGBA(31, 56, 100, 1), RGBA(150, 150, 150, 1))
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**TabIndex**

```powerfx
=1
```

### `btnModeLocAddItem` (Button)

**Text**

```powerfx
="ADD LOCATION"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locMode: "LOCATION_ADD"})
```

**Fill**

```powerfx
=If(locMode = "ITEM_CREATE", RGBA(150, 150, 150, 1), RGBA(31, 56, 100, 1))
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**TabIndex**

```powerfx
=2
```

### `lblL1AddItem` (Label)

**Text**

```powerfx
="Item ID"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtItemIdAddItem` (Text input)

**HintText**

```powerfx
="Item ID (text; leading zeros kept)"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=3
```

### `lblL2AddItem` (Label)

**Text**

```powerfx
="Name"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=locMode = "ITEM_CREATE"
```

### `txtNameAddItem` (Text input)

**HintText**

```powerfx
="Item name"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=4
```

**Visible**

```powerfx
=locMode = "ITEM_CREATE"
```

### `lblL3AddItem` (Label)

**Text**

```powerfx
="Manufacturer"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=locMode = "ITEM_CREATE"
```

### `txtMfrAddItem` (Text input)

**HintText**

```powerfx
="Manufacturer (optional)"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=5
```

**Visible**

```powerfx
=locMode = "ITEM_CREATE"
```

### `lblL4AddItem` (Label)

**Text**

```powerfx
="Description"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=locMode = "ITEM_CREATE"
```

### `txtDescAddItem` (Text input)

**HintText**

```powerfx
="Description (optional)"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=6
```

**Visible**

```powerfx
=locMode = "ITEM_CREATE"
```

### `lblL5AddItem` (Label)

**Text**

```powerfx
="Location"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtLocCodeAddItem` (Text input)

**HintText**

```powerfx
="Location code (must exist in the location list)"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=7
```

### `lblLocOkAddItem` (Label)

**Text**

```powerfx
=If(IsBlank(txtLocCodeAddItem.Text), "", Not(IsBlank(LookUp(POULocations, LocationCode = Upper(Trim(Substitute(txtLocCodeAddItem.Text, "*", ""))), Active = true))), "Location found", "Unknown or inactive location - an admin adds locations")
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblL6AddItem` (Label)

**Text**

```powerfx
="Area"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtAreaAddItem` (Text input)

**HintText**

```powerfx
="Area (optional)"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=8
```

### `lblL7AddItem` (Label)

**Text**

```powerfx
="Min / Max"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtMinAddItem` (Text input)

**HintText**

```powerfx
="Min"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=9
```

### `txtMaxAddItem` (Text input)

**HintText**

```powerfx
="Max"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=10
```

### `lblAddWhyAddItem` (Label)

**Text**

```powerfx
=If(
    IsBlank(txtItemIdAddItem.Text), "",
    Not(And(Len(Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", "")))) >= 1, Not("|" in Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", "")))), Not(" " in Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", "")))))), "Item ID cannot contain spaces or the | character.",
    And(locMode = "ITEM_CREATE", Not(IsBlank(LookUp(POUItems, ItemID = Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))))))), "Item " & Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))) & " already exists. Use ADD LOCATION to stock it somewhere else.",
    And(Not(locMode = "ITEM_CREATE"), Not(Not(IsBlank(LookUp(POUItems, ItemID = Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", "")))))))), "Item " & Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))) & " does not exist. Use NEW ITEM.",
    ""
)
```

**Color**

```powerfx
=RGBA(156, 0, 6, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblAddNoteAddItem` (Label)

**Text**

```powerfx
=If(varSupNewItem, "A supervisor must approve this before anything is created. Nothing is created until then, and no quantity is set: the first quantity comes from a supervisor-approved count.", "No quantity is set: the first quantity comes from a count.")
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnAddSubmitAddItem` (Button)

**Text**

```powerfx
=If(locMode = "ITEM_CREATE", "REQUEST NEW ITEM", "REQUEST NEW LOCATION")
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), And(Len(Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", "")))) >= 1, Not("|" in Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", "")))), Not(" " in Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))))), If(locMode = "ITEM_CREATE", Len(Trim(txtNameAddItem.Text)) > 0 And Not(Not(IsBlank(LookUp(POUItems, ItemID = Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))))))), Not(IsBlank(LookUp(POUItems, ItemID = Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))))))), Not(IsBlank(LookUp(POULocations, LocationCode = Upper(Trim(Substitute(txtLocCodeAddItem.Text, "*", ""))), Active = true))), IsMatch(Trim(txtMinAddItem.Text), "^(0|[1-9][0-9]{0,5})$"), IsMatch(Trim(txtMaxAddItem.Text), "^(0|[1-9][0-9]{0,5})$"), If(And(IsMatch(Trim(txtMinAddItem.Text), "^(0|[1-9][0-9]{0,5})$"), IsMatch(Trim(txtMaxAddItem.Text), "^(0|[1-9][0-9]{0,5})$")), Value(Trim(txtMinAddItem.Text)) <= Value(Trim(txtMaxAddItem.Text)), false)),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: locMode, StockKey: "", ItemID: Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))), LocationCode: Upper(Trim(Substitute(txtLocCodeAddItem.Text, "*", ""))), Quantity: "", ExpectedVersion: "", Reason: "", PayloadJson: JSON({ItemID: Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))), ItemName: Trim(txtNameAddItem.Text), Description: Trim(txtDescAddItem.Text), Manufacturer: Trim(txtMfrAddItem.Text), LocationCode: Upper(Trim(Substitute(txtLocCodeAddItem.Text, "*", ""))), Area: Trim(txtAreaAddItem.Text), MinQty: Value(Trim(txtMinAddItem.Text)), MaxQty: Value(Trim(txtMaxAddItem.Text))}, JSONFormat.Compact), TargetRequestID: "", Decision: "", ReversesLedgerKey: "", Summary: If(locMode = "ITEM_CREATE", "NEW ITEM ", "NEW LOCATION ") & Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))) & " @ " & Upper(Trim(Substitute(txtLocCodeAddItem.Text, "*", ""))) & " by " & varEmpName & " at " & varStation});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunAddItem)
)
```

**Fill**

```powerfx
=RGBA(84, 130, 53, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(Not(varBusy), IsBlank(varReq), And(Len(Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", "")))) >= 1, Not("|" in Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", "")))), Not(" " in Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))))), If(locMode = "ITEM_CREATE", Len(Trim(txtNameAddItem.Text)) > 0 And Not(Not(IsBlank(LookUp(POUItems, ItemID = Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))))))), Not(IsBlank(LookUp(POUItems, ItemID = Upper(Trim(Substitute(txtItemIdAddItem.Text, "*", ""))))))), Not(IsBlank(LookUp(POULocations, LocationCode = Upper(Trim(Substitute(txtLocCodeAddItem.Text, "*", ""))), Active = true))), IsMatch(Trim(txtMinAddItem.Text), "^(0|[1-9][0-9]{0,5})$"), IsMatch(Trim(txtMaxAddItem.Text), "^(0|[1-9][0-9]{0,5})$"), If(And(IsMatch(Trim(txtMinAddItem.Text), "^(0|[1-9][0-9]{0,5})$"), IsMatch(Trim(txtMaxAddItem.Text), "^(0|[1-9][0-9]{0,5})$")), Value(Trim(txtMinAddItem.Text)) <= Value(Trim(txtMaxAddItem.Text)), false)), DisplayMode.Edit, DisplayMode.Disabled)
```

**Visible**

```powerfx
=IsBlank(varReq)
```

**TabIndex**

```powerfx
=11
```

### `btnRetryAddItem` (Button)

**Text**

```powerfx
="Retry same request (" & Left(varReq.RequestID, 8) & ")"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Select(btnRunAddItem)
```

**Fill**

```powerfx
=RGBA(191, 144, 0, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(varBusy, DisplayMode.Disabled, DisplayMode.Edit)
```

**Visible**

```powerfx
=Not(IsBlank(varReq))
```

**TabIndex**

```powerfx
=11
```

### `tmrPollAddItem` (Timer)

**Duration**

```powerfx
=varPollSec * 1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=varPolling And Not(IsBlank(varReq))
```

**OnTimerEnd**

```powerfx
=If(
    IsBlank(varReq) Or Not(varPolling),
    Set(varPolling, false),
    Set(varPollTries, varPollTries + 1);
    Set(varResp, {status: "", code: "POLL", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID});
    Set(varRow, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
Set(varFinal, If(IsBlank(varRow), Coalesce(varResp.status, ""), varRow.RequestStatus.Value));
Set(varText, If(IsBlank(varRow), Coalesce(varResp.message, ""), Coalesce(varRow.ResultMessage, varResp.message, "")));
Set(varEffect, If(IsBlank(varRow), Coalesce(varResp.effect, ""), Coalesce(varRow.InventoryEffect.Value, "")));
Set(varShort, Left(varReq.RequestID, 8));
If(
    varFinal = "Succeeded",
        Set(varPolling, false); Set(varOutKind, "ok"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtItemIdAddItem); Reset(txtNameAddItem); Reset(txtMfrAddItem); Reset(txtDescAddItem); Reset(txtLocCodeAddItem); Reset(txtAreaAddItem); Reset(txtMinAddItem); Reset(txtMaxAddItem);
SetFocus(txtItemIdAddItem),
    varFinal = "Rejected",
        Set(varPolling, false); Set(varOutKind, "bad"); Set(varOutText, varText);
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtItemIdAddItem); Reset(txtNameAddItem); Reset(txtMfrAddItem); Reset(txtDescAddItem); Reset(txtLocCodeAddItem); Reset(txtAreaAddItem); Reset(txtMinAddItem); Reset(txtMaxAddItem);
SetFocus(txtItemIdAddItem),
    varFinal = "AwaitingSupervisor",
        Set(varPolling, false); Set(varOutKind, "wait");
        Set(varOutText, "Waiting for a supervisor to approve (request " & varShort & "). Nothing has been changed yet. It appears under History.");
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtItemIdAddItem); Reset(txtNameAddItem); Reset(txtMfrAddItem); Reset(txtDescAddItem); Reset(txtLocCodeAddItem); Reset(txtAreaAddItem); Reset(txtMinAddItem); Reset(txtMaxAddItem);
SetFocus(txtItemIdAddItem),
    varFinal = "Failed",
        Set(varPolling, false); Set(varOutKind, "bad");
        Set(varOutText, varText & If(varEffect = "NotApplied", "", " The quantity MAY have changed. Do not repeat this. Tell a supervisor (request " & varShort & ")."));
        RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtItemIdAddItem); Reset(txtNameAddItem); Reset(txtMfrAddItem); Reset(txtDescAddItem); Reset(txtLocCodeAddItem); Reset(txtAreaAddItem); Reset(txtMinAddItem); Reset(txtMaxAddItem);
SetFocus(txtItemIdAddItem),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & varShort & "). Do not enter it again. Press 'Retry same request' or wait: it cannot post twice and it finishes automatically.");
    Set(varPolling, true)
);
    If(
        varPolling And varPollTries * varPollSec >= varPollMax,
        Set(varPolling, false);
        Set(varOutText, "STILL NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The background job completes pending requests every few minutes. Do not enter it again; check History, or press 'Retry same request'.")
    )
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `lblBannerAddItem` (Label)

**Text**

```powerfx
=varOutText
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=If(varOutKind = "ok", RGBA(198, 239, 206, 1), varOutKind = "bad", RGBA(255, 199, 206, 1), RGBA(255, 230, 153, 1))
```

**Visible**

```powerfx
=Not(IsBlank(varOutText))
```

## scrLowStock - Low stock

Reads the server-maintained LowStockFlag. Items with no verified quantity are not listed as low stock (they appear in the data-health report).

**Screen properties**

- `Fill`
  ```powerfx
  =RGBA(242, 242, 242, 1)
  ```
- `OnVisible`
  ```powerfx
  =If(IsBlank(varSession) And Not(varSupMode), Navigate(scrLogin, ScreenTransition.None));
  Set(varLastActivity, Now());
  Reset(txtFilterLow)
  ```

| Control | Type | Purpose |
|---|---|---|
| `recHdrLow` | Rectangle | Header band |
| `lblHdrStationLow` | Label | Station identity (always visible) |
| `lblHdrUserLow` | Label | Employee identity (always visible) |
| `lblHdrIdleLow` | Label | Idle countdown |
| `btnHdrOutLow` | Button | Ends the server session |
| `tmrIdleLow` | Timer | Idle timeout checker (central setting IdleTimeoutMinutes) |
| `btnNavScanLow` | Button | Go to scrScan |
| `btnNavAuditLow` | Button | Go to scrAudit |
| `btnNavAddItemLow` | Button | Go to scrAddItem |
| `btnNavLowLow` | Button | Go to scrLowStock |
| `btnNavHistLow` | Button | Go to scrHistory |
| `btnNavSupLow` | Button | Go to scrSupervisor |
| `btnNavAdminLow` | Button | Go to scrAdmin |
| `lblLowTitleLow` | Label |  |
| `txtFilterLow` | Text input |  |
| `lblLowCountLow` | Label |  |
| `lblLowHeadLow` | Label |  |
| `galLowLow` | Vertical gallery | Delegable: Filter on Boolean columns + StartsWith + SortByColumns |
| `lblLowRowLow` | Label |  |
| `lblLowNoteLow` | Label |  |

### `recHdrLow` (Rectangle)

**Fill**

```powerfx
=RGBA(31, 56, 100, 1)
```

### `lblHdrStationLow` (Label)

**Text**

```powerfx
="Station " & varStation
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrUserLow` (Label)

**Text**

```powerfx
=If(varSupMode, varEmpName & " (supervisor, signed in as " & User().Email & ")", varEmpName & " - badge session")
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrIdleLow` (Label)

**Text**

```powerfx
="Auto sign-out in " & Max(0, varIdleMin * 60 - DateDiff(varLastActivity, varTick, Seconds)) & " s"
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnHdrOutLow` (Button)

**Text**

```powerfx
="Sign out"
```

**OnSelect**

```powerfx
=If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `tmrIdleLow` (Timer)

**Duration**

```powerfx
=1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=Set(varTick, Now());
If(
    (Not(IsBlank(varSession)) Or varSupMode) And DateDiff(varLastActivity, varTick, Seconds) >= varIdleMin * 60,
    If(
        Not(IsBlank(varSession)),
        IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
    );
    Set(varSession, "");
    Set(varEmpName, "");
    Set(varRole, "");
    Set(varSupMode, false);
    Clear(colStock);
    Navigate(scrLogin, ScreenTransition.None)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `btnNavScanLow` (Button)

**Text**

```powerfx
="Add / Remove"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrScan, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=Not(varSupMode)
```

### `btnNavAuditLow` (Button)

**Text**

```powerfx
="Count"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAudit, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavAddItemLow` (Button)

**Text**

```powerfx
="New item"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAddItem, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavLowLow` (Button)

**Text**

```powerfx
="Low stock"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrLowStock, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavHistLow` (Button)

**Text**

```powerfx
="History"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrHistory, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavSupLow` (Button)

**Text**

```powerfx
="Supervisor"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrSupervisor, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnNavAdminLow` (Button)

**Text**

```powerfx
="Admin"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAdmin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `lblLowTitleLow` (Label)

**Text**

```powerfx
="Low stock (On hand <= Min by default; the rule is the central LowStockRule setting)"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtFilterLow` (Text input)

**HintText**

```powerfx
="Filter: item number starts with..."
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**TabIndex**

```powerfx
=1
```

### `lblLowCountLow` (Label)

**Text**

```powerfx
=CountRows(galLowLow.AllItems) & " shown" & If(CountRows(galLowLow.AllItems) >= varRowLimit, "  -  LIST MAY BE TRUNCATED at the app row limit of " & varRowLimit & ". The emailed low-stock report is complete.", "")
```

**Color**

```powerfx
=RGBA(156, 87, 0, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblLowHeadLow` (Label)

**Text**

```powerfx
="Item                         Location        On hand   Min   Max   Suggested (Max - On hand)"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `galLowLow` (Vertical gallery)

**Items**

```powerfx
=FirstN(SortByColumns(Filter(POUStockLocations, Active = true, LowStockFlag = true, StartsWith(ItemID, Upper(Trim(Substitute(txtFilterLow.Text, "*", ""))))), "ItemID", SortOrder.Ascending), varRowLimit)
```

### `lblLowRowLow` (Label)

**Text**

```powerfx
=ThisItem.ItemID & "   " & ThisItem.ItemName & "   |   " & ThisItem.LocationCode & "   |   on hand " & Coalesce(Text(ThisItem.OnHandQty), "-") & "   min " & Coalesce(Text(ThisItem.MinQty), "-") & "   max " & Coalesce(Text(ThisItem.MaxQty), "-") & "   |   suggest " & If(IsBlank(ThisItem.OnHandQty) Or IsBlank(ThisItem.MaxQty), "-", Max(0, ThisItem.MaxQty - ThisItem.OnHandQty))
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblLowNoteLow` (Label)

**Text**

```powerfx
="Suggestions only - they do NOT consider open purchase orders. No order is created."
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

## scrHistory - Transaction history and processing status

Left: this station's requests with their real status (AwaitingSupervisor / Pending / Succeeded / Rejected / Failed). Right: the append-only ledger. Times shown are the ledger's stored local text (America/Chicago, written by the flow); the fallback uses this PC's time zone, which must be America/Chicago.

**Screen properties**

- `Fill`
  ```powerfx
  =RGBA(242, 242, 242, 1)
  ```
- `OnVisible`
  ```powerfx
  =If(IsBlank(varSession) And Not(varSupMode), Navigate(scrLogin, ScreenTransition.None));
  Set(varLastActivity, Now());
  Reset(txtHistItemHist);
  Refresh(POURequests)
  ```

| Control | Type | Purpose |
|---|---|---|
| `recHdrHist` | Rectangle | Header band |
| `lblHdrStationHist` | Label | Station identity (always visible) |
| `lblHdrUserHist` | Label | Employee identity (always visible) |
| `lblHdrIdleHist` | Label | Idle countdown |
| `btnHdrOutHist` | Button | Ends the server session |
| `tmrIdleHist` | Timer | Idle timeout checker (central setting IdleTimeoutMinutes) |
| `btnNavScanHist` | Button | Go to scrScan |
| `btnNavAuditHist` | Button | Go to scrAudit |
| `btnNavAddItemHist` | Button | Go to scrAddItem |
| `btnNavLowHist` | Button | Go to scrLowStock |
| `btnNavHistHist` | Button | Go to scrHistory |
| `btnNavSupHist` | Button | Go to scrSupervisor |
| `btnNavAdminHist` | Button | Go to scrAdmin |
| `lblReqTitleHist` | Label |  |
| `btnRefreshHist` | Button |  |
| `galReqHist` | Vertical gallery | Delegable: Filter on indexed StationID, SortByColumns on ID |
| `lblReqRowHist` | Label |  |
| `btnReCheckHist` | Button | Asks the flow to finish an unfinished request. Idempotent: it cannot post twice. |
| `lblLedTitleHist` | Label |  |
| `txtHistItemHist` | Text input |  |
| `galLedHist` | Vertical gallery | Delegable: Filter on indexed ItemID, SortByColumns on ID, FirstN |
| `lblLedRowHist` | Label |  |

### `recHdrHist` (Rectangle)

**Fill**

```powerfx
=RGBA(31, 56, 100, 1)
```

### `lblHdrStationHist` (Label)

**Text**

```powerfx
="Station " & varStation
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrUserHist` (Label)

**Text**

```powerfx
=If(varSupMode, varEmpName & " (supervisor, signed in as " & User().Email & ")", varEmpName & " - badge session")
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrIdleHist` (Label)

**Text**

```powerfx
="Auto sign-out in " & Max(0, varIdleMin * 60 - DateDiff(varLastActivity, varTick, Seconds)) & " s"
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnHdrOutHist` (Button)

**Text**

```powerfx
="Sign out"
```

**OnSelect**

```powerfx
=If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `tmrIdleHist` (Timer)

**Duration**

```powerfx
=1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=Set(varTick, Now());
If(
    (Not(IsBlank(varSession)) Or varSupMode) And DateDiff(varLastActivity, varTick, Seconds) >= varIdleMin * 60,
    If(
        Not(IsBlank(varSession)),
        IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
    );
    Set(varSession, "");
    Set(varEmpName, "");
    Set(varRole, "");
    Set(varSupMode, false);
    Clear(colStock);
    Navigate(scrLogin, ScreenTransition.None)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `btnNavScanHist` (Button)

**Text**

```powerfx
="Add / Remove"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrScan, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=Not(varSupMode)
```

### `btnNavAuditHist` (Button)

**Text**

```powerfx
="Count"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAudit, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavAddItemHist` (Button)

**Text**

```powerfx
="New item"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAddItem, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavLowHist` (Button)

**Text**

```powerfx
="Low stock"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrLowStock, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavHistHist` (Button)

**Text**

```powerfx
="History"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrHistory, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavSupHist` (Button)

**Text**

```powerfx
="Supervisor"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrSupervisor, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnNavAdminHist` (Button)

**Text**

```powerfx
="Admin"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAdmin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `lblReqTitleHist` (Label)

**Text**

```powerfx
="Requests from this station - with processing status"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnRefreshHist` (Button)

**Text**

```powerfx
="Refresh"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Refresh(POURequests); Refresh(POULedger)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `galReqHist` (Vertical gallery)

**Items**

```powerfx
=FirstN(SortByColumns(Filter(POURequests, StationID = varStation), "ID", SortOrder.Descending), 50)
```

### `lblReqRowHist` (Label)

**Text**

```powerfx
=ThisItem.RequestType.Value & "  " & Coalesce(ThisItem.Title, "") & "
" & ThisItem.RequestStatus.Value & If(ThisItem.IsOpen, "  (open)", "") & "  -  " & Coalesce(ThisItem.ResultMessage, "") & "
" & Text(ThisItem.Created, "mmm d, h:mm AM/PM") & "  |  request " & Left(ThisItem.RequestID, 8) & If(ThisItem.InventoryEffect.Value = "Unknown", "  |  EFFECT UNKNOWN - tell a supervisor", "")
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnReCheckHist` (Button)

**Text**

```powerfx
="Re-check"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
IfError('POU-ProcessRequest'.Run(ThisItem.RequestID), true);
Refresh(POURequests)
```

**Fill**

```powerfx
=RGBA(191, 144, 0, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=ThisItem.IsOpen And ThisItem.RequestStatus.Value <> "AwaitingSupervisor"
```

### `lblLedTitleHist` (Label)

**Text**

```powerfx
="Ledger (every posted movement). Legacy = imported from the old workbook, not part of the balance."
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtHistItemHist` (Text input)

**HintText**

```powerfx
="Item number (blank = latest 60)"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**TabIndex**

```powerfx
=1
```

### `galLedHist` (Vertical gallery)

**Items**

```powerfx
=If(IsBlank(Upper(Trim(Substitute(txtHistItemHist.Text, "*", "")))), FirstN(SortByColumns(POULedger, "ID", SortOrder.Descending), 60), FirstN(SortByColumns(Filter(POULedger, ItemID = Upper(Trim(Substitute(txtHistItemHist.Text, "*", "")))), "ID", SortOrder.Descending), 60))
```

### `lblLedRowHist` (Label)

**Text**

```powerfx
=ThisItem.LedgerType.Value & If(ThisItem.Origin.Value = "Legacy", " (LEGACY)", "") & " " & ThisItem.ItemID & " @ " & Coalesce(ThisItem.LocationCode, "?") & "  delta " & Coalesce(Text(ThisItem.QtyDelta), "-") & "  -> " & Coalesce(Text(ThisItem.QtyAfter), "-") & "
" & Coalesce(ThisItem.EmployeeName, ThisItem.LegacyUser, "?") & "  |  " & Coalesce(ThisItem.OccurredLocalText, ThisItem.LegacyTimestampText, Text(ThisItem.OccurredUtc, "mmm d, h:mm AM/PM")) & If(ThisItem.PostingState.Value <> "Posted", "  |  " & ThisItem.PostingState.Value, "")
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

## scrSupervisor - Supervisor console (own Microsoft sign-in)

Approve/reject waiting requests, post adjustments, reversals, parameter changes and (Admin) opening balances. Every action is a request authored by the supervisor's OWN Microsoft account; the flow decides authority from that Author identity. Hiding this screen is convenience only.

**Screen properties**

- `Fill`
  ```powerfx
  =RGBA(242, 242, 242, 1)
  ```
- `OnVisible`
  ```powerfx
  =If(Not(varSupMode), Navigate(scrLogin, ScreenTransition.None));
  Set(varLastActivity, Now());
  UpdateContext({locTab: "Q", locSel: Blank(), locMsg: "", locPending: false, locLocPending: false, locLastKey: Now(), locPickLedger: Blank(), locParamActive: true});
  Refresh(POURequests)
  ```

| Control | Type | Purpose |
|---|---|---|
| `recHdrSup` | Rectangle | Header band |
| `lblHdrStationSup` | Label | Station identity (always visible) |
| `lblHdrUserSup` | Label | Employee identity (always visible) |
| `lblHdrIdleSup` | Label | Idle countdown |
| `btnHdrOutSup` | Button | Ends the server session |
| `tmrIdleSup` | Timer | Idle timeout checker (central setting IdleTimeoutMinutes) |
| `btnNavScanSup` | Button | Go to scrScan |
| `btnNavAuditSup` | Button | Go to scrAudit |
| `btnNavAddItemSup` | Button | Go to scrAddItem |
| `btnNavLowSup` | Button | Go to scrLowStock |
| `btnNavHistSup` | Button | Go to scrHistory |
| `btnNavSupSup` | Button | Go to scrSupervisor |
| `btnNavAdminSup` | Button | Go to scrAdmin |
| `btnRunSup` | Button | Tiny transparent button. Runs the shared posting procedure for the retained request varReq; never creates a new RequestID. |
| `btnTabQSup` | Button |  |
| `btnTabASup` | Button |  |
| `btnTabRSup` | Button |  |
| `btnTabPSup` | Button |  |
| `lblSupWhoSup` | Label |  |
| `lblQHeadSup` | Label |  |
| `btnQRefreshSup` | Button |  |
| `galQueueSup` | Vertical gallery | Delegable: Filter on Boolean IsOpen + choice .Value (confirm the delegation indicator in Studio) + SortByColumns on ID |
| `lblQRowSup` | Label |  |
| `btnApproveSup` | Button | Files an APPROVE request authored by YOUR Microsoft account, then lets the flow process the target. The server refuses self-approval. |
| `btnRejectSup` | Button |  |
| `lblStep1Sup` | Label |  |
| `txtItemSup` | Text input | Scanner target. Enter/Tab suffix from the scanner ends the scan; the timer commits it. |
| `btnFindSup` | Button | Resolves the scan; also called by the scan timer |
| `lblStep2Sup` | Label |  |
| `txtLocSup` | Text input | Second scan target |
| `btnLocSup` | Button | Resolves the location scan; also called by the scan timer |
| `tmrScanSup` | Timer | Debounce: commits a scan once keystrokes stop for ScanCommitIdleMs, so Enter/Tab/no-suffix scanners all work |
| `lblMsgSup` | Label | Lookup messages |
| `galLocSup` | Vertical gallery | Choose the location when an item is stocked in more than one place |
| `lblGalLocSup` | Label |  |
| `lblSupSelSup` | Label | Supervisors see the system quantity |
| `lblAdjHeadSup` | Label |  |
| `lblQtyLSup` | Label |  |
| `txtQtySup` | Text input |  |
| `lblReasonLSup` | Label |  |
| `txtReasonSup` | Text input |  |
| `btnAdjustSup` | Button | Needs an authenticated supervisor; the server refuses it for anyone else. |
| `btnOpeningSup` | Button | OPENING is accepted by the server only from an Admin and only on a record that has never had a balance. |
| `lblRevHeadSup` | Label |  |
| `galRevSup` | Vertical gallery |  |
| `lblRevRowSup` | Label |  |
| `btnReverseSup` | Button |  |
| `lblParHeadSup` | Label |  |
| `txtMinSup` | Text input |  |
| `txtMaxSup` | Text input |  |
| `txtAreaSup` | Text input |  |
| `btnActiveSup` | Button |  |
| `btnParamSup` | Button |  |
| `btnRetrySup` | Button | Re-sends the SAME request number |
| `tmrPollSup` | Timer |  |
| `lblBannerSup` | Label | Outcome of the last request: ok / waiting / unconfirmed / bad |

### `recHdrSup` (Rectangle)

**Fill**

```powerfx
=RGBA(31, 56, 100, 1)
```

### `lblHdrStationSup` (Label)

**Text**

```powerfx
="Station " & varStation
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrUserSup` (Label)

**Text**

```powerfx
=If(varSupMode, varEmpName & " (supervisor, signed in as " & User().Email & ")", varEmpName & " - badge session")
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrIdleSup` (Label)

**Text**

```powerfx
="Auto sign-out in " & Max(0, varIdleMin * 60 - DateDiff(varLastActivity, varTick, Seconds)) & " s"
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnHdrOutSup` (Button)

**Text**

```powerfx
="Sign out"
```

**OnSelect**

```powerfx
=If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `tmrIdleSup` (Timer)

**Duration**

```powerfx
=1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=Set(varTick, Now());
If(
    (Not(IsBlank(varSession)) Or varSupMode) And DateDiff(varLastActivity, varTick, Seconds) >= varIdleMin * 60,
    If(
        Not(IsBlank(varSession)),
        IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
    );
    Set(varSession, "");
    Set(varEmpName, "");
    Set(varRole, "");
    Set(varSupMode, false);
    Clear(colStock);
    Navigate(scrLogin, ScreenTransition.None)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `btnNavScanSup` (Button)

**Text**

```powerfx
="Add / Remove"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrScan, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=Not(varSupMode)
```

### `btnNavAuditSup` (Button)

**Text**

```powerfx
="Count"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAudit, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavAddItemSup` (Button)

**Text**

```powerfx
="New item"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAddItem, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavLowSup` (Button)

**Text**

```powerfx
="Low stock"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrLowStock, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavHistSup` (Button)

**Text**

```powerfx
="History"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrHistory, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavSupSup` (Button)

**Text**

```powerfx
="Supervisor"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrSupervisor, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnNavAdminSup` (Button)

**Text**

```powerfx
="Admin"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAdmin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnRunSup` (Button)

**Text**

```powerfx
=""
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**OnSelect**

```powerfx
=If(
    IsBlank(varReq) Or varBusy,
    false,
    Set(varBusy, true);
Set(varOutKind, "");
Set(varOutText, "");
Set(varLookupFailed, false);
Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Set(varLookupFailed, true); Blank()));
Set(varSent, Not(IsBlank(varFound)));
If(
    Not(varSent) And Not(varLookupFailed),
    Set(varCreateFailed, false);
    IfError(Patch(POURequests, Defaults(POURequests), {
        Title: varReq.Summary,
        RequestID: varReq.RequestID,
        RequestType: {Value: varReq.RequestType},
        RequestStatus: {Value: "Pending"},
        IsOpen: true,
        SessionID: varReq.SessionID,
        StationID: varReq.Station,
        StockKey: varReq.StockKey,
        ItemID: varReq.ItemID,
        LocationCode: varReq.LocationCode,
        Quantity: If(IsBlank(varReq.Quantity), Blank(), Value(varReq.Quantity)),
        ExpectedVersion: If(IsBlank(varReq.ExpectedVersion), Blank(), Value(varReq.ExpectedVersion)),
        PayloadJson: varReq.PayloadJson,
        Reason: varReq.Reason,
        ReversesLedgerKey: varReq.ReversesLedgerKey,
        TargetRequestID: varReq.TargetRequestID,
        Decision: If(IsBlank(varReq.Decision), Blank(), {Value: varReq.Decision}),
        ClientLocalTime: Text(Now(), "yyyy-mm-dd hh:mm:ss")
    }), Set(varCreateFailed, true));
    Set(varSent, Not(varCreateFailed));
    If(
        varCreateFailed,
        Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
        Set(varSent, Not(IsBlank(varFound)))
    )
);
If(
    varSent,
    Set(varResp, IfError('POU-ProcessRequest'.Run(varReq.RequestID),
        {status: "", code: "NO_RESPONSE", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID}));
    Set(varRow, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
Set(varFinal, If(IsBlank(varRow), Coalesce(varResp.status, ""), varRow.RequestStatus.Value));
Set(varText, If(IsBlank(varRow), Coalesce(varResp.message, ""), Coalesce(varRow.ResultMessage, varResp.message, "")));
Set(varEffect, If(IsBlank(varRow), Coalesce(varResp.effect, ""), Coalesce(varRow.InventoryEffect.Value, "")));
Set(varShort, Left(varReq.RequestID, 8));
If(
    varFinal = "Succeeded",
        Set(varPolling, false); Set(varOutKind, "ok"); Set(varOutText, varText);
        If(varReq.RequestType = "APPROVE",
If(
    varOutKind = "ok",
    IfError('POU-ProcessRequest'.Run(varReq.TargetRequestID), true);
    Set(varTgtRow, IfError(LookUp(POURequests, RequestID = varReq.TargetRequestID), Blank()));
    Set(varOutKind, If(varTgtRow.RequestStatus.Value = "Succeeded", "ok", Or(varTgtRow.RequestStatus.Value = "Rejected", varTgtRow.RequestStatus.Value = "Failed"), "bad", "wait"));
    Set(varOutText, "Decision recorded. The request is now: " & Coalesce(varTgtRow.RequestStatus.Value, "unknown") & ". " & Coalesce(varTgtRow.ResultMessage, ""))
);
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Refresh(POURequests),
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtySup); Reset(txtReasonSup); Reset(txtMinSup); Reset(txtMaxSup); Reset(txtAreaSup); UpdateContext({locPickLedger: Blank()}); Refresh(POURequests)),
    varFinal = "Rejected",
        Set(varPolling, false); Set(varOutKind, "bad"); Set(varOutText, varText);
        If(varReq.RequestType = "APPROVE",
If(
    varOutKind = "ok",
    IfError('POU-ProcessRequest'.Run(varReq.TargetRequestID), true);
    Set(varTgtRow, IfError(LookUp(POURequests, RequestID = varReq.TargetRequestID), Blank()));
    Set(varOutKind, If(varTgtRow.RequestStatus.Value = "Succeeded", "ok", Or(varTgtRow.RequestStatus.Value = "Rejected", varTgtRow.RequestStatus.Value = "Failed"), "bad", "wait"));
    Set(varOutText, "Decision recorded. The request is now: " & Coalesce(varTgtRow.RequestStatus.Value, "unknown") & ". " & Coalesce(varTgtRow.ResultMessage, ""))
);
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Refresh(POURequests),
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtySup); Reset(txtReasonSup); Reset(txtMinSup); Reset(txtMaxSup); Reset(txtAreaSup); UpdateContext({locPickLedger: Blank()}); Refresh(POURequests)),
    varFinal = "AwaitingSupervisor",
        Set(varPolling, false); Set(varOutKind, "wait");
        Set(varOutText, "Waiting for a supervisor to approve (request " & varShort & "). Nothing has been changed yet. It appears under History.");
        If(varReq.RequestType = "APPROVE",
If(
    varOutKind = "ok",
    IfError('POU-ProcessRequest'.Run(varReq.TargetRequestID), true);
    Set(varTgtRow, IfError(LookUp(POURequests, RequestID = varReq.TargetRequestID), Blank()));
    Set(varOutKind, If(varTgtRow.RequestStatus.Value = "Succeeded", "ok", Or(varTgtRow.RequestStatus.Value = "Rejected", varTgtRow.RequestStatus.Value = "Failed"), "bad", "wait"));
    Set(varOutText, "Decision recorded. The request is now: " & Coalesce(varTgtRow.RequestStatus.Value, "unknown") & ". " & Coalesce(varTgtRow.ResultMessage, ""))
);
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Refresh(POURequests),
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtySup); Reset(txtReasonSup); Reset(txtMinSup); Reset(txtMaxSup); Reset(txtAreaSup); UpdateContext({locPickLedger: Blank()}); Refresh(POURequests)),
    varFinal = "Failed",
        Set(varPolling, false); Set(varOutKind, "bad");
        Set(varOutText, varText & If(varEffect = "NotApplied", "", " The quantity MAY have changed. Do not repeat this. Tell a supervisor (request " & varShort & ")."));
        If(varReq.RequestType = "APPROVE",
If(
    varOutKind = "ok",
    IfError('POU-ProcessRequest'.Run(varReq.TargetRequestID), true);
    Set(varTgtRow, IfError(LookUp(POURequests, RequestID = varReq.TargetRequestID), Blank()));
    Set(varOutKind, If(varTgtRow.RequestStatus.Value = "Succeeded", "ok", Or(varTgtRow.RequestStatus.Value = "Rejected", varTgtRow.RequestStatus.Value = "Failed"), "bad", "wait"));
    Set(varOutText, "Decision recorded. The request is now: " & Coalesce(varTgtRow.RequestStatus.Value, "unknown") & ". " & Coalesce(varTgtRow.ResultMessage, ""))
);
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Refresh(POURequests),
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtySup); Reset(txtReasonSup); Reset(txtMinSup); Reset(txtMaxSup); Reset(txtAreaSup); UpdateContext({locPickLedger: Blank()}); Refresh(POURequests)),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & varShort & "). Do not enter it again. Press 'Retry same request' or wait: it cannot post twice and it finishes automatically.");
    Set(varPolling, true)
),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The app could not confirm that the server received it. Do not enter it again: press 'Retry same request' - the same request number is reused, so it cannot post twice.");
    Set(varPolling, false)
);
Set(varBusy, false)
)
```

### `btnTabQSup` (Button)

**Text**

```powerfx
="Approvals"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locTab: "Q"})
```

**Fill**

```powerfx
=If(locTab = "Q", RGBA(31, 56, 100, 1), RGBA(150, 150, 150, 1))
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `btnTabASup` (Button)

**Text**

```powerfx
="Adjust / opening"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locTab: "A"})
```

**Fill**

```powerfx
=If(locTab = "A", RGBA(31, 56, 100, 1), RGBA(150, 150, 150, 1))
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `btnTabRSup` (Button)

**Text**

```powerfx
="Reverse"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locTab: "R"})
```

**Fill**

```powerfx
=If(locTab = "R", RGBA(31, 56, 100, 1), RGBA(150, 150, 150, 1))
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `btnTabPSup` (Button)

**Text**

```powerfx
="Min / Max / Area"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locTab: "P"})
```

**Fill**

```powerfx
=If(locTab = "P", RGBA(31, 56, 100, 1), RGBA(150, 150, 150, 1))
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `lblSupWhoSup` (Label)

**Text**

```powerfx
=If(varSupMode, "You act as " & varEmpName & " (" & User().Email & "). The SERVER decides your authority from this Microsoft sign-in and POUEmployees.", "Supervisor functions need 'Continue as supervisor' on the sign-in screen, using your own Microsoft account.")
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblQHeadSup` (Label)

**Text**

```powerfx
="Waiting for a supervisor, oldest first. These requests have NOT changed any quantity yet."
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=locTab = "Q"
```

### `btnQRefreshSup` (Button)

**Text**

```powerfx
="Refresh"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Refresh(POURequests)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=locTab = "Q"
```

### `galQueueSup` (Vertical gallery)

**Visible**

```powerfx
=locTab = "Q"
```

**Items**

```powerfx
=FirstN(SortByColumns(Filter(POURequests, IsOpen = true, RequestStatus.Value = "AwaitingSupervisor"), "ID", SortOrder.Ascending), 100)
```

### `lblQRowSup` (Label)

**Text**

```powerfx
=ThisItem.RequestType.Value & "   " & Coalesce(ThisItem.Title, "") & "
" & "Item " & Coalesce(ThisItem.ItemID, "-") & " @ " & Coalesce(ThisItem.LocationCode, "-") & "   qty " & Coalesce(Text(ThisItem.Quantity), "-") & "   counted-from version " & Coalesce(Text(ThisItem.ExpectedVersion), "-") & "
" & Text(ThisItem.Created, "mmm d, h:mm AM/PM") & "  |  filed by account " & ThisItem.'Created By'.Email & "  |  request " & Left(ThisItem.RequestID, 8)
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnApproveSup` (Button)

**Text**

```powerfx
="APPROVE"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), varSupMode),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: "APPROVE", StockKey: "", ItemID: "", LocationCode: "", Quantity: "", ExpectedVersion: "", Reason: "", PayloadJson: "", TargetRequestID: ThisItem.RequestID, Decision: "Approve", ReversesLedgerKey: "", Summary: "APPROVE " & Left(ThisItem.RequestID, 8) & " " & ThisItem.RequestType.Value & " by " & varEmpName});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunSup)
)
```

**Fill**

```powerfx
=RGBA(84, 130, 53, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(Not(varBusy), IsBlank(varReq), varSupMode), DisplayMode.Edit, DisplayMode.Disabled)
```

### `btnRejectSup` (Button)

**Text**

```powerfx
="REJECT"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), varSupMode),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: "APPROVE", StockKey: "", ItemID: "", LocationCode: "", Quantity: "", ExpectedVersion: "", Reason: "", PayloadJson: "", TargetRequestID: ThisItem.RequestID, Decision: "Reject", ReversesLedgerKey: "", Summary: "REJECT " & Left(ThisItem.RequestID, 8) & " " & ThisItem.RequestType.Value & " by " & varEmpName});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunSup)
)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(Not(varBusy), IsBlank(varReq), varSupMode), DisplayMode.Edit, DisplayMode.Disabled)
```

### `lblStep1Sup` (Label)

**Text**

```powerfx
="1  Scan the item"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=Not(locTab = "Q")
```

### `txtItemSup` (Text input)

**HintText**

```powerfx
="Scan or type item number"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=UpdateContext({locPending: true, locLastKey: Now()});
Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**TabIndex**

```powerfx
=1
```

**Visible**

```powerfx
=Not(locTab = "Q")
```

### `btnFindSup` (Button)

**Text**

```powerfx
="Look up"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locPending: false, locSel: Blank(), locMsg: ""});
Reset(txtQtySup); Reset(txtLocSup);
With(
    {scan: Upper(Trim(Substitute(txtItemSup.Text, "*", "")))},
    If(
        Len(scan) < varScanMin,
        UpdateContext({locMsg: "Scan or type the item number."}),
        Set(varLookupFailed, false);
        IfError(
            ClearCollect(colStock, SortByColumns(Filter(POUStockLocations, ItemID = scan, Active = true), "LocationCode", SortOrder.Ascending)),
            Set(varLookupFailed, true); Clear(colStock);
            UpdateContext({locMsg: "Could not look the item up (network?). Nothing was changed. Scan it again."})
        );
        If(
            Not(varLookupFailed),
            If(
                CountRows(colStock) = 0,
                UpdateContext({locMsg: If(
                    Not(IsBlank(LookUp(POUItems, ItemID = scan))),
                    "Item " & scan & " exists but is not stocked in any active location. A supervisor can add a stocking location (New item screen).",
                    "Item " & scan & " was not found. Check the barcode, or ask a supervisor to add the item.")}),
                CountRows(colStock) = 1,
                UpdateContext({locSel: First(colStock), locPickLedger: Blank(), locParamActive: First(colStock).Active}); SetFocus(txtQtySup),
                UpdateContext({locMsg: "Item " & scan & " is stocked in " & CountRows(colStock) & " locations. Choose or scan the location."});
                SetFocus(txtLocSup)
            )
        )
    )
)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**TabIndex**

```powerfx
=2
```

**Visible**

```powerfx
=Not(locTab = "Q")
```

### `lblStep2Sup` (Label)

**Text**

```powerfx
="2  Location (only when the item is in several places)"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=Not(locTab = "Q")
```

### `txtLocSup` (Text input)

**HintText**

```powerfx
="Scan or type location"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=UpdateContext({locLocPending: true, locLastKey: Now()});
Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**TabIndex**

```powerfx
=3
```

**Visible**

```powerfx
=And(Not(locTab = "Q"), CountRows(colStock) > 1)
```

### `btnLocSup` (Button)

**Text**

```powerfx
="Use location"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locLocPending: false});
With(
    {loc: Upper(Trim(Substitute(txtLocSup.Text, "*", "")))},
    If(
        CountRows(colStock) = 0,
        UpdateContext({locMsg: "Scan the item first."}),
        IsBlank(LookUp(colStock, LocationCode = loc)),
        UpdateContext({locSel: Blank(), locMsg: "Item " & First(colStock).ItemID & " is not stocked at " & loc & ". Choose a listed location, or ask a supervisor to add that location."}),
        UpdateContext({locSel: LookUp(colStock, LocationCode = loc), locPickLedger: Blank(), locParamActive: LookUp(colStock, LocationCode = loc).Active}); UpdateContext({locMsg: ""}); SetFocus(txtQtySup)
    )
)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq), DisplayMode.Edit, DisplayMode.View)
```

**Visible**

```powerfx
=And(Not(locTab = "Q"), CountRows(colStock) > 1)
```

**TabIndex**

```powerfx
=4
```

### `tmrScanSup` (Timer)

**Duration**

```powerfx
=150
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=If(
    locPending And DateDiff(locLastKey, Now(), Milliseconds) >= varScanIdle,
    Select(btnFindSup)
);
If(
    locLocPending And DateDiff(locLastKey, Now(), Milliseconds) >= varScanIdle,
    Select(btnLocSup)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `lblMsgSup` (Label)

**Text**

```powerfx
=locMsg
```

**Color**

```powerfx
=RGBA(156, 0, 6, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=And(Not(locTab = "Q"), Not(IsBlank(locMsg)))
```

### `galLocSup` (Vertical gallery)

**Items**

```powerfx
=colStock
```

**Visible**

```powerfx
=And(Not(locTab = "Q"), CountRows(colStock) > 1)
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locSel: ThisItem, locPickLedger: Blank(), locParamActive: ThisItem.Active});
UpdateContext({locMsg: ""});
SetFocus(txtQtySup)
```

### `lblGalLocSup` (Label)

**Text**

```powerfx
=ThisItem.LocationCode & "   on hand: " & If(IsBlank(ThisItem.OnHandQty), "-", Text(ThisItem.OnHandQty))
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblSupSelSup` (Label)

**Text**

```powerfx
=If(IsBlank(locSel), "", locSel.ItemName & "
" & locSel.ItemID & " @ " & locSel.LocationCode & "   on hand " & Coalesce(Text(locSel.OnHandQty), "-") & "   record version " & locSel.StockVersion & "   " & locSel.BalanceStatus.Value)
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=Not(locTab = "Q")
```

### `lblAdjHeadSup` (Label)

**Text**

```powerfx
="ADJUSTMENT sets the quantity to the number you enter and records your reason. It is a new ledger entry, never an edit of history."
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=locTab = "A"
```

### `lblQtyLSup` (Label)

**Text**

```powerfx
="New quantity"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=locTab = "A"
```

### `txtQtySup` (Text input)

**HintText**

```powerfx
="New quantity"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=5
```

**Visible**

```powerfx
=locTab = "A"
```

### `lblReasonLSup` (Label)

**Text**

```powerfx
="Reason (required)"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=Or(locTab = "A", locTab = "R")
```

### `txtReasonSup` (Text input)

**HintText**

```powerfx
="Why?"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=6
```

**Visible**

```powerfx
=Or(locTab = "A", locTab = "R")
```

### `btnAdjustSup` (Button)

**Text**

```powerfx
="POST ADJUSTMENT"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), varSupMode, Not(IsBlank(locSel)), IsMatch(Trim(txtQtySup.Text), "^(0|[1-9][0-9]{0,5})$"), Len(Trim(txtReasonSup.Text)) > 0),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: "ADJUSTMENT", StockKey: locSel.StockKey, ItemID: locSel.ItemID, LocationCode: locSel.LocationCode, Quantity: Trim(txtQtySup.Text), ExpectedVersion: "", Reason: Trim(txtReasonSup.Text), PayloadJson: "", TargetRequestID: "", Decision: "", ReversesLedgerKey: "", Summary: "ADJUST " & locSel.ItemID & " @ " & locSel.LocationCode & " to " & Trim(txtQtySup.Text) & " by " & varEmpName});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunSup)
)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(Not(varBusy), IsBlank(varReq), varSupMode, Not(IsBlank(locSel)), IsMatch(Trim(txtQtySup.Text), "^(0|[1-9][0-9]{0,5})$"), Len(Trim(txtReasonSup.Text)) > 0), DisplayMode.Edit, DisplayMode.Disabled)
```

**Visible**

```powerfx
=locTab = "A" And IsBlank(varReq)
```

**TabIndex**

```powerfx
=7
```

### `btnOpeningSup` (Button)

**Text**

```powerfx
="SET OPENING BALANCE (admin, first time only)"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), varSupMode, Not(IsBlank(locSel)), IsMatch(Trim(txtQtySup.Text), "^(0|[1-9][0-9]{0,5})$"), Len(Trim(txtReasonSup.Text)) > 0, varRole = "Admin"),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: "OPENING", StockKey: locSel.StockKey, ItemID: locSel.ItemID, LocationCode: locSel.LocationCode, Quantity: Trim(txtQtySup.Text), ExpectedVersion: "", Reason: Trim(txtReasonSup.Text), PayloadJson: "", TargetRequestID: "", Decision: "", ReversesLedgerKey: "", Summary: "OPENING " & Trim(txtQtySup.Text) & " x " & locSel.ItemID & " @ " & locSel.LocationCode & " by " & varEmpName});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunSup)
)
```

**Fill**

```powerfx
=RGBA(112, 48, 160, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(Not(varBusy), IsBlank(varReq), varSupMode, Not(IsBlank(locSel)), IsMatch(Trim(txtQtySup.Text), "^(0|[1-9][0-9]{0,5})$"), Len(Trim(txtReasonSup.Text)) > 0, varRole = "Admin"), DisplayMode.Edit, DisplayMode.Disabled)
```

**Visible**

```powerfx
=locTab = "A" And IsBlank(varReq)
```

### `lblRevHeadSup` (Label)

**Text**

```powerfx
="REVERSAL cancels one posted ADD or REMOVE with a new ledger entry. Pick the movement (newest first):"
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=locTab = "R"
```

### `galRevSup` (Vertical gallery)

**Visible**

```powerfx
=locTab = "R"
```

**Items**

```powerfx
=If(IsBlank(locSel), Blank(), FirstN(SortByColumns(Filter(POULedger, StockKey = locSel.StockKey), "ID", SortOrder.Descending), 30))
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locPickLedger: ThisItem})
```

### `lblRevRowSup` (Label)

**Text**

```powerfx
=ThisItem.LedgerKey & "  " & ThisItem.LedgerType.Value & "  delta " & Coalesce(Text(ThisItem.QtyDelta), "-") & "  " & Coalesce(ThisItem.OccurredLocalText, "") & "  " & Coalesce(ThisItem.EmployeeName, "")
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnReverseSup` (Button)

**Text**

```powerfx
="POST REVERSAL"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), varSupMode, Not(IsBlank(locSel)), Not(IsBlank(locPickLedger)), Len(Trim(txtReasonSup.Text)) > 0),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: "REVERSAL", StockKey: locSel.StockKey, ItemID: locSel.ItemID, LocationCode: locSel.LocationCode, Quantity: "", ExpectedVersion: "", Reason: Trim(txtReasonSup.Text), PayloadJson: "", TargetRequestID: "", Decision: "", ReversesLedgerKey: locPickLedger.LedgerKey, Summary: "REVERSE " & locPickLedger.LedgerKey & " by " & varEmpName});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunSup)
)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(Not(varBusy), IsBlank(varReq), varSupMode, Not(IsBlank(locSel)), Not(IsBlank(locPickLedger)), Len(Trim(txtReasonSup.Text)) > 0), DisplayMode.Edit, DisplayMode.Disabled)
```

**Visible**

```powerfx
=locTab = "R" And IsBlank(varReq)
```

### `lblParHeadSup` (Label)

**Text**

```powerfx
="Change Min / Max / Area, or deactivate. Leave a box empty to keep its value. This never changes a quantity."
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Visible**

```powerfx
=locTab = "P"
```

### `txtMinSup` (Text input)

**HintText**

```powerfx
="New Min"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=5
```

**Visible**

```powerfx
=locTab = "P"
```

### `txtMaxSup` (Text input)

**HintText**

```powerfx
="New Max"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=6
```

**Visible**

```powerfx
=locTab = "P"
```

### `txtAreaSup` (Text input)

**HintText**

```powerfx
="New Area"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=7
```

**Visible**

```powerfx
=locTab = "P"
```

### `btnActiveSup` (Button)

**Text**

```powerfx
=If(locParamActive, "ACTIVE (press to deactivate)", "INACTIVE (press to reactivate)")
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
UpdateContext({locParamActive: Not(locParamActive)})
```

**Fill**

```powerfx
=RGBA(100, 100, 100, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=locTab = "P"
```

### `btnParamSup` (Button)

**Text**

```powerfx
="POST CHANGE"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    And(Not(varBusy), IsBlank(varReq), varSupMode, Not(IsBlank(locSel)), Or(Not(IsBlank(txtMinSup.Text)), Not(IsBlank(txtMaxSup.Text)), Not(IsBlank(txtAreaSup.Text)), Not(locParamActive = locSel.Active))),
    Set(varReq, {RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: "PARAM_UPDATE", StockKey: locSel.StockKey, ItemID: locSel.ItemID, LocationCode: locSel.LocationCode, Quantity: "", ExpectedVersion: "", Reason: "", PayloadJson: JSON({MinQty: If(IsBlank(txtMinSup.Text), Blank(), Value(txtMinSup.Text)), MaxQty: If(IsBlank(txtMaxSup.Text), Blank(), Value(txtMaxSup.Text)), Area: If(IsBlank(txtAreaSup.Text), Blank(), Trim(txtAreaSup.Text)), Active: locParamActive}, JSONFormat.Compact), TargetRequestID: "", Decision: "", ReversesLedgerKey: "", Summary: "SETTINGS " & locSel.ItemID & " @ " & locSel.LocationCode & " by " & varEmpName});
Collect(colOutbox, varReq);
IfError(SaveData(colOutbox, "POUOutbox"), true);
    Select(btnRunSup)
)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(And(Not(varBusy), IsBlank(varReq), varSupMode, Not(IsBlank(locSel)), Or(Not(IsBlank(txtMinSup.Text)), Not(IsBlank(txtMaxSup.Text)), Not(IsBlank(txtAreaSup.Text)), Not(locParamActive = locSel.Active))), DisplayMode.Edit, DisplayMode.Disabled)
```

**Visible**

```powerfx
=locTab = "P" And IsBlank(varReq)
```

### `btnRetrySup` (Button)

**Text**

```powerfx
="Retry same request (" & Left(varReq.RequestID, 8) & ")"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Select(btnRunSup)
```

**Fill**

```powerfx
=RGBA(191, 144, 0, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(varBusy, DisplayMode.Disabled, DisplayMode.Edit)
```

**Visible**

```powerfx
=Not(IsBlank(varReq))
```

### `tmrPollSup` (Timer)

**Duration**

```powerfx
=varPollSec * 1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=varPolling And Not(IsBlank(varReq))
```

**OnTimerEnd**

```powerfx
=If(
    IsBlank(varReq) Or Not(varPolling),
    Set(varPolling, false),
    Set(varPollTries, varPollTries + 1);
    Set(varResp, {status: "", code: "POLL", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID});
    Set(varRow, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
Set(varFinal, If(IsBlank(varRow), Coalesce(varResp.status, ""), varRow.RequestStatus.Value));
Set(varText, If(IsBlank(varRow), Coalesce(varResp.message, ""), Coalesce(varRow.ResultMessage, varResp.message, "")));
Set(varEffect, If(IsBlank(varRow), Coalesce(varResp.effect, ""), Coalesce(varRow.InventoryEffect.Value, "")));
Set(varShort, Left(varReq.RequestID, 8));
If(
    varFinal = "Succeeded",
        Set(varPolling, false); Set(varOutKind, "ok"); Set(varOutText, varText);
        If(varReq.RequestType = "APPROVE",
If(
    varOutKind = "ok",
    IfError('POU-ProcessRequest'.Run(varReq.TargetRequestID), true);
    Set(varTgtRow, IfError(LookUp(POURequests, RequestID = varReq.TargetRequestID), Blank()));
    Set(varOutKind, If(varTgtRow.RequestStatus.Value = "Succeeded", "ok", Or(varTgtRow.RequestStatus.Value = "Rejected", varTgtRow.RequestStatus.Value = "Failed"), "bad", "wait"));
    Set(varOutText, "Decision recorded. The request is now: " & Coalesce(varTgtRow.RequestStatus.Value, "unknown") & ". " & Coalesce(varTgtRow.ResultMessage, ""))
);
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Refresh(POURequests),
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtySup); Reset(txtReasonSup); Reset(txtMinSup); Reset(txtMaxSup); Reset(txtAreaSup); UpdateContext({locPickLedger: Blank()}); Refresh(POURequests)),
    varFinal = "Rejected",
        Set(varPolling, false); Set(varOutKind, "bad"); Set(varOutText, varText);
        If(varReq.RequestType = "APPROVE",
If(
    varOutKind = "ok",
    IfError('POU-ProcessRequest'.Run(varReq.TargetRequestID), true);
    Set(varTgtRow, IfError(LookUp(POURequests, RequestID = varReq.TargetRequestID), Blank()));
    Set(varOutKind, If(varTgtRow.RequestStatus.Value = "Succeeded", "ok", Or(varTgtRow.RequestStatus.Value = "Rejected", varTgtRow.RequestStatus.Value = "Failed"), "bad", "wait"));
    Set(varOutText, "Decision recorded. The request is now: " & Coalesce(varTgtRow.RequestStatus.Value, "unknown") & ". " & Coalesce(varTgtRow.ResultMessage, ""))
);
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Refresh(POURequests),
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtySup); Reset(txtReasonSup); Reset(txtMinSup); Reset(txtMaxSup); Reset(txtAreaSup); UpdateContext({locPickLedger: Blank()}); Refresh(POURequests)),
    varFinal = "AwaitingSupervisor",
        Set(varPolling, false); Set(varOutKind, "wait");
        Set(varOutText, "Waiting for a supervisor to approve (request " & varShort & "). Nothing has been changed yet. It appears under History.");
        If(varReq.RequestType = "APPROVE",
If(
    varOutKind = "ok",
    IfError('POU-ProcessRequest'.Run(varReq.TargetRequestID), true);
    Set(varTgtRow, IfError(LookUp(POURequests, RequestID = varReq.TargetRequestID), Blank()));
    Set(varOutKind, If(varTgtRow.RequestStatus.Value = "Succeeded", "ok", Or(varTgtRow.RequestStatus.Value = "Rejected", varTgtRow.RequestStatus.Value = "Failed"), "bad", "wait"));
    Set(varOutText, "Decision recorded. The request is now: " & Coalesce(varTgtRow.RequestStatus.Value, "unknown") & ". " & Coalesce(varTgtRow.ResultMessage, ""))
);
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Refresh(POURequests),
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtySup); Reset(txtReasonSup); Reset(txtMinSup); Reset(txtMaxSup); Reset(txtAreaSup); UpdateContext({locPickLedger: Blank()}); Refresh(POURequests)),
    varFinal = "Failed",
        Set(varPolling, false); Set(varOutKind, "bad");
        Set(varOutText, varText & If(varEffect = "NotApplied", "", " The quantity MAY have changed. Do not repeat this. Tell a supervisor (request " & varShort & ")."));
        If(varReq.RequestType = "APPROVE",
If(
    varOutKind = "ok",
    IfError('POU-ProcessRequest'.Run(varReq.TargetRequestID), true);
    Set(varTgtRow, IfError(LookUp(POURequests, RequestID = varReq.TargetRequestID), Blank()));
    Set(varOutKind, If(varTgtRow.RequestStatus.Value = "Succeeded", "ok", Or(varTgtRow.RequestStatus.Value = "Rejected", varTgtRow.RequestStatus.Value = "Failed"), "bad", "wait"));
    Set(varOutText, "Decision recorded. The request is now: " & Coalesce(varTgtRow.RequestStatus.Value, "unknown") & ". " & Coalesce(varTgtRow.ResultMessage, ""))
);
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Refresh(POURequests),
RemoveIf(colOutbox, RequestID = varReq.RequestID);
IfError(SaveData(colOutbox, "POUOutbox"), true);
Set(varReq, Blank());
Reset(txtQtySup); Reset(txtReasonSup); Reset(txtMinSup); Reset(txtMaxSup); Reset(txtAreaSup); UpdateContext({locPickLedger: Blank()}); Refresh(POURequests)),
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & varShort & "). Do not enter it again. Press 'Retry same request' or wait: it cannot post twice and it finishes automatically.");
    Set(varPolling, true)
);
    If(
        varPolling And varPollTries * varPollSec >= varPollMax,
        Set(varPolling, false);
        Set(varOutText, "STILL NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The background job completes pending requests every few minutes. Do not enter it again; check History, or press 'Retry same request'.")
    )
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `lblBannerSup` (Label)

**Text**

```powerfx
=varOutText
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=If(varOutKind = "ok", RGBA(198, 239, 206, 1), varOutKind = "bad", RGBA(255, 199, 206, 1), RGBA(255, 230, 153, 1))
```

**Visible**

```powerfx
=Not(IsBlank(varOutText))
```

## scrAdmin - Admin / settings

Edits central settings and the location list. The app only offers the controls; SharePoint permissions (POU Admins) are what allow or refuse the write.

**Screen properties**

- `Fill`
  ```powerfx
  =RGBA(242, 242, 242, 1)
  ```
- `OnVisible`
  ```powerfx
  =If(Not(varSupMode), Navigate(scrLogin, ScreenTransition.None));
  Set(varLastActivity, Now());
  Refresh(POUSettings)
  ```

| Control | Type | Purpose |
|---|---|---|
| `recHdrAdmin` | Rectangle | Header band |
| `lblHdrStationAdmin` | Label | Station identity (always visible) |
| `lblHdrUserAdmin` | Label | Employee identity (always visible) |
| `lblHdrIdleAdmin` | Label | Idle countdown |
| `btnHdrOutAdmin` | Button | Ends the server session |
| `tmrIdleAdmin` | Timer | Idle timeout checker (central setting IdleTimeoutMinutes) |
| `btnNavScanAdmin` | Button | Go to scrScan |
| `btnNavAuditAdmin` | Button | Go to scrAudit |
| `btnNavAddItemAdmin` | Button | Go to scrAddItem |
| `btnNavLowAdmin` | Button | Go to scrLowStock |
| `btnNavHistAdmin` | Button | Go to scrHistory |
| `btnNavSupAdmin` | Button | Go to scrSupervisor |
| `btnNavAdminAdmin` | Button | Go to scrAdmin |
| `lblAdmTitleAdmin` | Label |  |
| `lblAdmWhoAdmin` | Label |  |
| `txtSetFilterAdmin` | Text input |  |
| `galSetAdmin` | Vertical gallery | Direct Patch on POUSettings. Allowed only for POU Admins (SharePoint permission), not by this app's logic. |
| `lblSetKeyAdmin` | Label |  |
| `txtSetValAdmin` | Text input |  |
| `btnSetSaveAdmin` | Button |  |
| `lblLocTitleAdmin` | Label |  |
| `txtNewLocAdmin` | Text input |  |
| `btnNewLocAdmin` | Button |  |
| `galLocListAdmin` | Vertical gallery |  |
| `lblLocRowAdmin` | Label |  |
| `lblStnTitleAdmin` | Label |  |
| `galStnAdmin` | Vertical gallery |  |
| `lblStnRowAdmin` | Label |  |
| `lblAdmNoteAdmin` | Label |  |

### `recHdrAdmin` (Rectangle)

**Fill**

```powerfx
=RGBA(31, 56, 100, 1)
```

### `lblHdrStationAdmin` (Label)

**Text**

```powerfx
="Station " & varStation
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrUserAdmin` (Label)

**Text**

```powerfx
=If(varSupMode, varEmpName & " (supervisor, signed in as " & User().Email & ")", varEmpName & " - badge session")
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblHdrIdleAdmin` (Label)

**Text**

```powerfx
="Auto sign-out in " & Max(0, varIdleMin * 60 - DateDiff(varLastActivity, varTick, Seconds)) & " s"
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `btnHdrOutAdmin` (Button)

**Text**

```powerfx
="Sign out"
```

**OnSelect**

```powerfx
=If(
    Not(IsBlank(varSession)),
    IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(192, 80, 77, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

### `tmrIdleAdmin` (Timer)

**Duration**

```powerfx
=1000
```

**Repeat**

```powerfx
=true
```

**AutoStart**

```powerfx
=false
```

**Start**

```powerfx
=true
```

**OnTimerEnd**

```powerfx
=Set(varTick, Now());
If(
    (Not(IsBlank(varSession)) Or varSupMode) And DateDiff(varLastActivity, varTick, Seconds) >= varIdleMin * 60,
    If(
        Not(IsBlank(varSession)),
        IfError('POU-Session'.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
    );
    Set(varSession, "");
    Set(varEmpName, "");
    Set(varRole, "");
    Set(varSupMode, false);
    Clear(colStock);
    Navigate(scrLogin, ScreenTransition.None)
)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

**Color**

```powerfx
=RGBA(0, 0, 0, 0)
```

**BorderColor**

```powerfx
=RGBA(0, 0, 0, 0)
```

**DisplayMode**

```powerfx
=DisplayMode.View
```

### `btnNavScanAdmin` (Button)

**Text**

```powerfx
="Add / Remove"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrScan, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=Not(varSupMode)
```

### `btnNavAuditAdmin` (Button)

**Text**

```powerfx
="Count"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAudit, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavAddItemAdmin` (Button)

**Text**

```powerfx
="New item"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAddItem, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavLowAdmin` (Button)

**Text**

```powerfx
="Low stock"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrLowStock, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavHistAdmin` (Button)

**Text**

```powerfx
="History"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrHistory, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=true
```

### `btnNavSupAdmin` (Button)

**Text**

```powerfx
="Supervisor"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrSupervisor, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `btnNavAdminAdmin` (Button)

**Text**

```powerfx
="Admin"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
Navigate(scrAdmin, ScreenTransition.None)
```

**Fill**

```powerfx
=RGBA(68, 114, 196, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**Visible**

```powerfx
=varSupMode
```

### `lblAdmTitleAdmin` (Label)

**Text**

```powerfx
="Settings (central configuration). Changes are versioned in SharePoint; flows read them on every run."
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblAdmWhoAdmin` (Label)

**Text**

```powerfx
=If(varRole = "Admin", "", "Read only - you are not an Admin. SharePoint would refuse your edits anyway.")
```

**Color**

```powerfx
=RGBA(255, 199, 206, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtSetFilterAdmin` (Text input)

**HintText**

```powerfx
="Filter by name..."
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**TabIndex**

```powerfx
=1
```

### `galSetAdmin` (Vertical gallery)

**Items**

```powerfx
=SortByColumns(Filter(POUSettings, StartsWith(SettingKey, Trim(txtSetFilterAdmin.Text))), "SettingKey", SortOrder.Ascending)
```

### `lblSetKeyAdmin` (Label)

**Text**

```powerfx
=ThisItem.SettingKey
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtSetValAdmin` (Text input)

**HintText**

```powerfx
="value"
```

**Default**

```powerfx
=ThisItem.SettingValue
```

**OnChange**

```powerfx
=false
```

**DisplayMode**

```powerfx
=If(varRole = "Admin", DisplayMode.Edit, DisplayMode.View)
```

### `btnSetSaveAdmin` (Button)

**Text**

```powerfx
="Save"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
IfError(
    Patch(POUSettings, ThisItem, {SettingValue: Trim(txtSetValAdmin.Text)});
    Notify("Saved " & ThisItem.SettingKey, NotificationType.Success),
    Notify("NOT saved: " & FirstError.Message, NotificationType.Error)
)
```

**Fill**

```powerfx
=RGBA(84, 130, 53, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(varRole = "Admin", DisplayMode.Edit, DisplayMode.Disabled)
```

### `lblLocTitleAdmin` (Label)

**Text**

```powerfx
="Locations"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `txtNewLocAdmin` (Text input)

**HintText**

```powerfx
="New location code"
```

**Default**

```powerfx
=""
```

**OnChange**

```powerfx
=Set(varLastActivity, Now())
```

**DisplayMode**

```powerfx
=If(varRole = "Admin", DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=2
```

### `btnNewLocAdmin` (Button)

**Text**

```powerfx
="Add"
```

**OnSelect**

```powerfx
=Set(varLastActivity, Now());
If(
    Len(Upper(Trim(Substitute(txtNewLocAdmin.Text, "*", "")))) > 0 And IsBlank(LookUp(POULocations, LocationCode = Upper(Trim(Substitute(txtNewLocAdmin.Text, "*", ""))))),
    IfError(
        Patch(POULocations, Defaults(POULocations), {Title: Upper(Trim(Substitute(txtNewLocAdmin.Text, "*", ""))), LocationCode: Upper(Trim(Substitute(txtNewLocAdmin.Text, "*", ""))), Description: "", Active: true});
        Reset(txtNewLocAdmin);
        Notify("Location added", NotificationType.Success),
        Notify("NOT added: " & FirstError.Message, NotificationType.Error)
    ),
    Notify("Enter a new location code that is not already in the list.", NotificationType.Warning)
)
```

**Fill**

```powerfx
=RGBA(84, 130, 53, 1)
```

**Color**

```powerfx
=RGBA(255, 255, 255, 1)
```

**DisplayMode**

```powerfx
=If(varRole = "Admin", DisplayMode.Edit, DisplayMode.Disabled)
```

**TabIndex**

```powerfx
=3
```

### `galLocListAdmin` (Vertical gallery)

**Items**

```powerfx
=SortByColumns(POULocations, "LocationCode", SortOrder.Ascending)
```

### `lblLocRowAdmin` (Label)

**Text**

```powerfx
=ThisItem.LocationCode & If(ThisItem.Active, "", "  (inactive)")
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblStnTitleAdmin` (Label)

**Text**

```powerfx
="Stations (editable; no code change needed to add a cabinet PC)"
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `galStnAdmin` (Vertical gallery)

**Items**

```powerfx
=SortByColumns(POUStations, "StationID", SortOrder.Ascending)
```

### `lblStnRowAdmin` (Label)

**Text**

```powerfx
=ThisItem.StationID & "  " & Coalesce(ThisItem.StationName, "") & If(ThisItem.Active, "", " (inactive)") & "  " & Coalesce(ThisItem.ExpectedAccountUPN, "")
```

**Color**

```powerfx
=RGBA(32, 32, 32, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```

### `lblAdmNoteAdmin` (Label)

**Text**

```powerfx
="Stations, employees and badge IDs are maintained in the SharePoint lists directly (admin only). Opening balances and adjustments are on the Supervisor screen."
```

**Color**

```powerfx
=RGBA(110, 110, 110, 1)
```

**Fill**

```powerfx
=RGBA(0, 0, 0, 0)
```
