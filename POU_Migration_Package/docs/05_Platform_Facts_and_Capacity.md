# 05 - Platform facts the design depends on, and what capacity really looks like

**How reliable is this page?** The build environment could not reach `learn.microsoft.com` or a tenant. Numbers below marked **[doc]** are Microsoft's published limits *as I know them*; marked **[measured]** come from running the generated flow definitions in the local interpreter (`tests/test_capacity.py`, `docs/generated/capacity.json`); marked **[tenant]** are things only a tenant run can settle - `pou_tools/tenant_probe.py` and the T-* tests do that. Check every **[doc]** number against current Microsoft documentation before you commit money to a licence.

## SharePoint Online

| Fact | Used by | Source |
|---|---|---|
| **List view threshold = 5,000 items.** A query that must *examine* more than 5,000 rows is refused (HTTP 500, "exceeds the list view threshold") even if it returns few rows, unless an **index** lets SharePoint narrow it first. A filter that *matches* more than 5,000 rows is refused even on an indexed column. | Every flow query filters on an indexed column that matches a handful of rows. "Read everything" jobs (reconcile, usage, health, low-stock) page **by ID order with no server filter** and filter inside the flow. | [doc], modelled in `fakesp`, probe L1-L4 **[tenant]** |
| Unique column values require the column to be **indexed**; uniqueness is case-insensitive; a duplicate create fails (HTTP 400, code `-2130575169` family). | `RequestID`, `LedgerKey`, `StockKey`, `ItemID`, `BadgeID`, `SettingKey`, ... | [doc]; probe U1, R1 **[tenant]** |
| Up to 20 indexed columns per list; the biggest list here uses 10. | schema | [doc] |
| Item `ETag` + `If-Match` on MERGE gives optimistic concurrency (HTTP 412 on mismatch). | claim, stock update | [doc]; probe E1-E3, R2 **[tenant]** |
| Throttling: HTTP 429/503 with `Retry-After`. Python tools back off; flows use the connector's retry policy. | tools, flows | [doc] |
| Versioning is on for data lists (500 major versions); not on Sessions/OpsEvents. | audit trail of edits | provisioned |
| A list's REST entity type contains the list name; underscores in names are encoded `_x005f_`. **No underscores in list names.** | list names `POU...` | [doc], design rule |
| Single-line text max 255 characters. | `SettingValue`, `Reason` are 255 | [doc], enforced by schema validator |
| **SharePoint has no multi-row transaction.** | The whole protocol in `06_Consistency_Limits.md` | [doc] |

## Power Apps (canvas)

| Fact | Consequence in the app |
|---|---|
| **Data row limit**: default 500, maximum 2,000 rows returned to the app from a *delegated* query. Beyond that the app silently sees only the first N. | Every gallery is `FirstN(..., N)`; the Low-stock screen prints a visible warning when it reaches the limit; totals/usage are never computed in the app. |
| **Delegation**: SharePoint delegates `=`, `<>`, `<`, `>`, `And/Or/Not`, `StartsWith`, `Sort/SortByColumns`, and `LookUp/Filter` on indexed/ordinary columns. It does **not** delegate `Search`, `in`, `CountRows`/`Sum`/`CountIf` over the list, `Len/Lower/Trim` applied to a *column*, `Distinct`, `GroupBy`. | `app/docs/DELEGATION.md` lists every query; the linter (`pou_app/lint.py`) rejects non-delegable constructs and unindexed filters on the large lists. **Studio's own delegation warnings must still be checked** (T-APP-05). |
| The row limit and the 5,000 threshold are different limits. A delegated `Filter` on an indexed column is fine on a 50,000-row list; the same `Filter` on an unindexed column fails once the list passes 5,000. | all large-list filters use indexed columns (`StationID`, `ItemID`, `StockKey`, `IsOpen`, `RequestStatus`) or ID order. |
| `Param("StationID")` reads a URL parameter. | station identity. |
| `SaveData/LoadData` (local outbox) availability depends on the player. **[tenant]** | If unavailable, the in-memory retained request still protects within the session (the code ignores the error); a browser crash then loses the *local* copy but the server still holds the request row and `History` shows it. T-APP-09. |
| Timer control with `Visible=false` may not run in all players. | The app uses tiny transparent *visible* timers. |
| A scanner suffix of Enter or Tab commits `TextInput.OnChange`. | App uses a debounce timer so both suffixes (and none) work. T-HW-*. |

## Power Automate

| Fact | Consequence |
|---|---|
| Max 500 actions per flow definition; nesting depth 8; expression length 8,192 characters. | Largest flow (`POU-Sweeper`) = 239 actions; static tests parse every expression and check depth (`tests/test_flow_static.py`). **[measured]** |
| Instant flow called from Power Apps: HTTP-style timeout ~120 s for the synchronous response. | `POU-ProcessRequest` answers well inside this. If it ever does not, the app shows UNCONFIRMED and keeps the same request id; the sweeper completes it. |
| "Send an HTTP request to SharePoint" is an action of the **SharePoint** connector (standard tier). | All SharePoint access uses it (needed for ETag, `If-Match`, unique-key errors). Confirm DLP allows it. |
| Flow "run-only" users can be given the owner's connection ("Use this connection"). | The write identity for stock and ledger is the service account. |
| Recurrence triggers use Windows time-zone names (`Central Standard Time`). | Daily/weekly jobs are hourly ticks that decide "due" from `DisplayTimeZoneWindows` and a `Last...Date` setting. |

## Capacity: the number that decides the licence

Power Platform meters **API requests ("actions") per 24 hours per licence**; each action, each loop iteration's actions and each retry count. Throttling (slowing) applies when the allocation is exceeded. **[doc - verify]** typical allocations: Microsoft 365 / "Power Automate for Microsoft 365" seeded rights **6,000** per 24 h; Power Automate Premium (per user) **40,000**; Power Automate Process (per flow) **250,000**. Which account the requests are counted against (flow owner vs caller) for an app-triggered flow is something to **confirm with Microsoft/IT**.

Cost of each path, **measured** on the generated definitions (`docs/generated/capacity.json`):

| Path | Actions | SharePoint calls |
|---|---:|---:|
| `POU-ProcessRequest`, ADD or REMOVE, uncontended | 112 | 16 |
| `POU-ProcessRequest`, OPENING | 120 | 17 |
| `POU-Session` LOGIN | 41 | 4 |
| `POU-Session` LOGOUT (also called at idle time-out) | 32 | 3 |
| `POU-Sweeper` when nothing to do (every 5 minutes) | 6 | 1 |
| Hourly "tick" flows when not due (Monitor 7; LowStock, Reconcile, Health, Usage 11 each) | 7 to 11 | 1 to 2 |
| Report flows when due | 33 to 85 + pages | |

Baseline with **zero** transactions: 288 x 6 + 24 x 7 + 24 x 4 x 11 = **about 2,950 actions/day**, plus about 100 for the due reports.
One cabinet "transaction" = login 41 + ADD/REMOVE 112 + logout 32 = **about 185 actions** if the person signs in for each one (a 3-minute idle time-out makes that common); about 112 for each further movement in the same session.

| If the flow account has... | Daily allowance | Left after baseline | Roughly how many sign-in-per-transaction movements/day |
|---|---:|---:|---:|
| Microsoft 365 seeded rights only **[doc]** | 6,000 | about 2,950 | **about 16** |
| Power Automate Premium, per user **[doc]** | 40,000 | about 37,000 | about 200 |
| Power Automate Process (per flow) licence on the 3 hot flows **[doc]** | 250,000 each | far more than needed | not a constraint |

**Reading it plainly:** the SharePoint + flows design is correct but *expensive per movement* because every safety step is an action. For a cabinet with a few dozen movements a day it needs at least a per-user premium licence for the service account (or per-flow licences) - this is decision **D1** and it blocks go-live. If that is unacceptable, use the Dataverse/SQL variant in `06_Consistency_Limits.md`, where one call does what 16 do here.

Ways to cut cost without weakening safety (all optional, all editable in the flow designer): lengthen the sweeper recurrence (5 -> 15 minutes saves about 1,150/day); make the four tick flows 2-hourly (saves about 530/day; report hours then must fall on even hours); raise `IdleTimeoutMinutes` so people sign in less often.

## Latency to expect (estimate, **[tenant]**)

16 sequential SharePoint calls at roughly 0.2 - 0.5 s each plus flow overhead: **about 5 - 15 seconds** from pressing ADD/REMOVE to the green banner. The app shows "Posting..." and disables the buttons meanwhile. If operators will not accept that, again see the SQL/Dataverse variant.

## Tooling versions, authentication and connections (what was used, what you need)

| Item | Version / setting |
|---|---|
| Python (scripts, tests) | 3.10 or newer required; built and tested on 3.13 |
| Python libraries | `requests` 2.x, `msal` 1.x (device-code sign-in, public client, **no secret**), `openpyxl` 3.1 (reads the workbook; macros are never executed), tests: `pytest` 8.x; `tzdata` on Windows |
| SharePoint | SharePoint Online REST (`/_api`, verbose OData `application/json;odata=verbose`); ETag via `__metadata.etag` and `IF-MATCH` |
| Power Automate | cloud flows, Logic Apps workflow-definition schema `2016-06-01`; trigger "Power Apps (V2)" for the two app-called flows; Recurrence for the others |
| Power Apps | canvas app, classic controls only (label, text input, button, timer, gallery, rectangle); YAML in the "As" source syntax; no component library, no preview features required |
| Sign-in for the setup scripts | Microsoft Entra **public client** app registration, delegated SharePoint permission `AllSites.FullControl` (admin consent), device-code flow; token kept in memory only |
| Connections used by the flows | `shared_sharepointonline` (SharePoint) and `shared_office365` (Office 365 Outlook, report mail only), both created by the **flow service account** |
| Connection used by the app | SharePoint, implicit, **as the signed-in user** (this is what stamps `Created By`); plus the two flows added to the app |
| Permission levels | Read, Contribute (built in); *POU Add Only* (Read + AddListItems), *POU Flow Writer* (Read + AddListItems + EditListItems) created by `provision` |
| Secrets | none anywhere in the package; the only placeholders are `CHANGE-ME` values (site URL, report recipients, client/tenant ids) |
