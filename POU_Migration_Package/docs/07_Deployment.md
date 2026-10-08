# 07 - Deployment, step by step (written for someone who knows Excel/VBA, not Power Platform)

**Honest status before you start.** Everything in the SharePoint, migration and tooling steps (2-8) was built and tested against an in-memory model of SharePoint - not against your tenant. The flow definitions are generated and run in a local interpreter; they have never been imported into Power Automate. The app source has never been opened in Power Apps Studio. Steps 9-11 are therefore where you will meet surprises; `11_Validation_Status.md` lists exactly what is proven and what is not, and `08_Testing_and_Acceptance.md` is the gate you must pass before any real stock moves.

Time: about one working day for steps 1-8 (mostly waiting for IT), plus however long the flow import takes (step 9).

## 0. Before you begin (ask IT; answers drive everything)

Send IT the list in `04_Identity_and_Permissions.md` section "What IT must confirm" and `05_Platform_Facts_and_Capacity.md` section "Capacity". Do not start step 9 until decision **D1** (licence of the flow service account) is made. You need:

| You need | Why |
|---|---|
| A **site owner** account for the SharePoint site (yours, to run the setup scripts) | creates lists and permissions |
| A **flow service account**: an ordinary licensed Microsoft 365 user (e.g. `svc-pou@yourcompany.com`), mailbox optional | owns the flows and their connections; the only account that can write stock and ledger |
| Station accounts (one per cabinet PC, or named operators) | sign in to the app; licensed users with SharePoint access |
| A Windows PC with **Python 3.10+** (python.org installer; tick "Add python.exe to PATH" and "py launcher") | runs the scripts in `scripts\` |
| Ability to create an **app registration** in Microsoft Entra, or an IT person who can | lets the scripts sign in as you (no secret is created) |
| Permission to create flows / import a solution in an environment | step 9 |

## 1. Unpack and configure the scripts

1. Unzip the package, e.g. to `C:\POU\POU_Migration_Package`. Put your workbook one folder up (`C:\POU\POU_Inventory_Pilot Test _With_Badge.xlsm`) or change `WORKBOOK` in `scripts\config.cmd`.
2. Double-click `scripts\0_setup_python.cmd` (creates a private Python environment and installs three libraries).
3. Edit `scripts\config.cmd`: `SITE_URL`, `TENANT`, `CLIENT_ID` (you get the last one in step 3). **No passwords or keys go in this file** and none are asked for anywhere: sign-in is a browser device-code prompt.
4. Run `scripts\2_extract_validate.cmd` now (it needs no tenant): it reads the workbook and (re)generates `migration\import\*.csv`, `migration\exceptions\exceptions.csv`, `migration\RUN_SUMMARY.md`. Read the summary and the exceptions before going further.

## 2. Create the SharePoint site

SharePoint admin center (or "+ Create site" from SharePoint home) -> **Team site** -> name "POU" -> note the address, e.g. `https://contoso.sharepoint.com/sites/POU`. Put it in `SITE_URL`. You (the creator) are a site owner. Do **not** add operators to the site's Members group: the provisioning script creates its own groups and a user who is also in the site's default Members group could have more rights than the matrix allows. The script reports any extra assignment on a POU list as `EXTRA_ASSIGN ... DRIFT` and never removes one itself; the permission audit in step 6 catches the effect.

## 3. Register the sign-in app for the scripts (one time, IT may do it)

Microsoft Entra admin center -> Applications -> **App registrations** -> New registration:

1. Name `POU Setup Tools`; supported account types **this organizational directory only**; redirect URI: platform **Public client/native**, `https://login.microsoftonline.com/common/oauth2/nativeclient`.
2. Authentication -> Advanced settings -> **Allow public client flows = Yes**. Save.
3. API permissions -> Add -> **SharePoint** -> **Delegated** -> `AllSites.FullControl` -> Add -> **Grant admin consent**.
4. Copy **Application (client) ID** into `CLIENT_ID` and **Directory (tenant) ID** (or `yourtenant.onmicrosoft.com`) into `TENANT`.

If device-code sign-in is blocked by Conditional Access, IT must allow it for this app and the people running the scripts, or run the tools from a managed device.

## 4. Provision the lists (dry run, then apply)

1. `scripts\1_provision.cmd` - **dry run**: signs you in (follow the on-screen code), reads the site, prints every list/column/index/unique constraint/group/permission it *would* create. Nothing is changed.
2. Read it. Then `scripts\1_provision.cmd APPLY`. Re-running is safe: existing correct objects are reported OK; differences are reported as DRIFT, never destructively "fixed".
3. Result: 10 lists, 4 SharePoint groups (POU Operators / Supervisors / Admins / Flow Service), 2 permission levels (*POU Add Only*, *POU Flow Writer*), default rows in `POUSettings`, and (with `--seed-station`) station `CAB-01`. `migration\provision_report.json` records what was done.

## 5. People and groups

1. In Entra create four **security groups** (e.g. `POU-Operators`, `POU-Supervisors`, `POU-Admins`, `POU-FlowService`). Add the accounts.
2. In SharePoint (Site settings -> Site permissions -> Advanced permissions settings) add each Entra group to the SharePoint group of the same name. **The flow service account must be in POU Flow Service and nowhere else with edit rights.**
3. Fill in the data lists (SharePoint -> the list -> Edit in grid view):
   * `POUStations`: one row per cabinet (`StationID` e.g. CAB-01, `Active` yes, optionally `ExpectedAccountUPN` = the station's Microsoft account so a stolen session cannot be used elsewhere).
   * `POUEmployees`: after the import (step 8) set `Role` and `MicrosoftUPN` for every supervisor/admin. **Until you do, nobody can approve audits or new items.**
   * `POUSettings`: replace the four `CHANGE-ME@yourcompany.example` recipient settings, review hours (`LowStockReportHourLocal` etc. are local Chicago hours).

## 6. Gate: prove SharePoint behaves the way the design assumes

* `scripts\5_tenant_probe.cmd APPLY` (a few minutes) - creates a throw-away list `POUProbe`, checks unique keys, text IDs, ETag/412, simultaneous creates and updates, deletes the list. **Every line must say PASS.** Add the 5,100-row run once (`scripts\5_tenant_probe.cmd APPLY 5100`, 30-40 minutes) to see the 5,000-item threshold behaviour on your tenant.
* `scripts\6_permission_audit.cmd operators` (sign in as a **test operator account**, not yourself), then again with `supervisors`, `admins`, `flowservice`. Every list must say OK. A BAD line means somebody has more or less access than the matrix says (often: the account is also in the Site Owners or Members group).

If anything fails here, stop: the protocol's guarantees depend on these.

## 7. Import the reference data (no quantities yet)

`scripts\3_import.cmd` (dry run) then `scripts\3_import.cmd APPLY locations,employees,items,stock,ledger`. This loads locations, employees (everyone Operator/Active - see step 5), the 251 items, the 254 stock records (all `NoBalance`), and the 26 legacy history rows (`Origin=Legacy`, `AffectsBalance=No`). **No quantity is written.** The importer refuses any file that has an `OnHandQty` column.

## 8. Quantities come in last, through the flow

Quantities enter as 252 `OPENING` requests (blank-On-Hand records get none). They must be **processed by the flow** so the ledger explains every balance - so this happens after step 9 and, per `09_Cutover_and_Rollback.md`, only on cutover day: `scripts\3_import.cmd APPLY openings`, wait for the sweeper (5-minute cadence) to post them, then `scripts\4_verify_import.cmd`, which writes `migration\reconciliation\post_import_quantity_reconciliation.csv` and must show 252 matched rows and a total of 973.

## 9. Flows

Eight flows, in `flows\definitions\*.json` (what the generator emits), `flows\docs\*.md` (action-by-action: every expression, URI, body, run-after and error branch), `flows\docs\FLOW_INDEX.md` (what each one is for). The two the app calls **must be named exactly** `POU-Session` and `POU-ProcessRequest` (the app code refers to them by those names).

### 9.0 Prepare (both routes)
1. Sign in to Power Automate as the **flow service account** (private browser window). Choose the environment IT specified.
2. Create the two **connections** in that account: Data -> Connections -> New: **SharePoint** and **Office 365 Outlook** (the latter only for report e-mails).

### 9.A Route A - import as a solution (preferred, UNVALIDATED here)
`flows\POU_Flows_solution_CANDIDATE.zip` follows the documented layout of an unmanaged solution with eight cloud flows. It was generated by this package, **not** produced by Microsoft's tooling and **never imported**. Two ways to try it:
1. Power Apps / Power Automate -> **Solutions** -> Import solution -> choose the zip. If the portal accepts it: map the two connection references to the service account's connections.
2. If you have the Power Platform CLI (`pac`): `pac solution pack --zipfile POU_Flows.zip --folder flows\solution_candidate --packagetype Unmanaged`, then import `POU_Flows.zip`. `pac` will tell you precisely what is wrong with the layout if anything is, and is the supported way to build the real package.

After import: open **each** flow -> edit the action `Cfg_SiteUrl` (replace `https://CHANGE-ME.sharepoint.com/sites/POU`; the flow deliberately **stops with an error** while the placeholder is present) -> Save -> **Turn on**.

### 9.B Route B - build by hand from the documents (works, but is long)
Power Automate's designer cannot import a raw definition. Each `flows\docs\<Flow>.md` lists, in run order, every action with the exact input to type. Sizes: Session 67 actions, Process 218, Sweeper 239, Monitor 37, DailyLowStock 54, Reconcile 57, WeeklyHealth 85, WeeklyUsage 44. Build in this order and test each before the next: **Session, ProcessRequest** (the app cannot work without these), **Sweeper** (recovery - required before real use), then **Monitor**, **Reconcile**, then the three reports. Expect days, not hours; Route A, or a Power Platform developer with `pac`, is far better. You can keep the cabinet on the workbook until Sweeper and Reconcile are live.

### 9.C Share and set the write identity
1. Flow `POU-Session` and `POU-ProcessRequest` -> **Run only users** -> Edit -> add the Entra group *POU-Operators* and *POU-Supervisors*; for each connection (SharePoint) choose **"Use this connection"** (the service account's), **not** "Provided by run-only user". This is what makes the service account the write identity.
2. Turn on the other six flows. Open each flow once and check its connections show no warning triangle.
3. **Test run** `POU-Sweeper` from the designer: with nothing open it ends in ~6 actions with status Succeeded.

## 10. The canvas app

1. make.powerapps.com -> Create -> **Blank canvas app** -> *Tablet* format, named `POU`. Settings -> Display: orientation Landscape, size **1366 x 768**, **Scale to fit off**, **Lock aspect ratio on**.
2. Settings -> General: **Data row limit = 500** (the app is written for this; raising to 2,000 is harmless). Settings -> Updates: leave **Formula-level error management on** (the app uses `IfError`).
3. Data -> Add data -> SharePoint -> your site -> tick **POUSettings, POUStations, POULocations, POUEmployees, POUItems, POUStockLocations, POURequests, POULedger**. (`POUSessions` and `POUOpsEvents` are deliberately not used by the app.) The data source names must be exactly these.
4. Power Automate pane -> Add flow -> `POU-Session` and `POU-ProcessRequest`.
5. Build the screens. Two ways:
   * **Paste code (fast, best effort).** For each file in `app\src` (`App.fx.yaml`, then `scrLogin`, `scrScan`, `scrAudit`, `scrAddItem`, `scrLowStock`, `scrHistory`, `scrSupervisor`, `scrAdmin`): the file is the Power Apps YAML source format. In Studio create the screen with that name, select it in the tree view, and paste (Ctrl+V) the file's text; for `App.fx.yaml` paste the properties onto **App**. **This paste format was written from the published format and has never been accepted by a real Studio** - if Studio rejects a file, use the other way for that screen.
   * **By hand from `app\docs\CONTROL_REFERENCE.md`.** It lists, per screen, every control (exact name and type) and the full Power Fx for every property. Create controls in the order listed; names must match exactly or other formulas break. Screen first, then the controls, then paste each formula.
6. Fix whatever the Studio checker underlines (red = error, blue = delegation warning). Compare every blue underline with `app\docs\DELEGATION.md`: there should be **none**. Report any difference back (it means the delegation table is wrong).
7. Save -> Publish. Share with the Entra groups *POU-Operators* and *POU-Supervisors* (user role). Each user is asked once to allow the SharePoint connection.

## 11. A cabinet PC

1. Windows time zone **(UTC-06:00) Central Time** (assumption A4).
2. Sign in to Windows or the browser as the **station account**. Open the app link with the station appended: `https://apps.powerapps.com/play/e/<env>/a/<appid>?tenantId=<tenant>&StationID=CAB-01`. Make a desktop shortcut: Edge -> `msedge.exe --app="<that URL>" --kiosk` (or the same without `--kiosk`). The first screen must show **Station CAB-01**.
3. Scanner: USB keyboard-wedge, configured to send **Enter** (or Tab) after each scan, no prefix. Code-39 start/stop `*` is fine (stripped). Then run the scanner tests in `08_Testing_and_Acceptance.md` (T-HW-*) on this PC.

## 12. Go-live gate

Do not move real stock until every test marked **required before go-live** in `08_Testing_and_Acceptance.md` has been run and recorded, then follow `09_Cutover_and_Rollback.md`.
