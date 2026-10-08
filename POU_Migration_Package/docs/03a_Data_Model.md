# Data model (generated from schema/lists.json)

Do not edit by hand: edit `schema/lists.json` and run `python -m pou_tools.docs_gen`. Provisioning (`pou_tools.provision`) reads the same file.

## Conventions

* **listNames**: No spaces or underscores in list names: the REST entity type of a list with an underscore is encoded as _x005f_ and breaks hand-written flow calls.
* **internalNames**: PascalCase, <= 32 chars, never start with an underscore, never reuse SharePoint reserved names (ID, Title, Created, Modified, Author, Editor, Version, Type, Status). Created via SchemaXml so internal name == Name below.
* **title**: Every list keeps the built-in Title column but it is made non-required and holds a human-readable label written by flows (for example 'K100593 @ 1-A'). No logic reads Title.
* **stockKey**: StockKey = UPPER(TRIM(ItemID)) + '|' + UPPER(TRIM(LocationCode)). '|' is forbidden inside ItemID and LocationCode.
* **ledgerKey**: LedgerKey = StockKey + '#' + SeqNo for live rows; 'LEGACY|<sheet>|r<row>' for legacy rows.
* **timestamps**: All DateTime columns store UTC. *Local text columns store America/Chicago text for display so every device shows the same time.
* **indexLimit**: SharePoint Online allows 20 indexed columns per list; the largest list here uses 10.

## POUSettings

Central configuration. One row per setting. Read by app and flows; edited only by POU Admins.

Expected size: tens of rows

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `SettingKey` | Text max 100 | yes | yes | **yes** | Stable key used by the app and flows. |
| `SettingValue` | Text max 255 |  |  |  | Value as text. Must not contain double quotes or backslashes (flows build a JSON object from these rows). |
| `ValueType` | Choice (Text, Number, Boolean, EmailList, Hour) |  |  |  | Documentation and validation hint. Default: Text. |
| `Description` | Note |  |  |  | What the setting does. |

## POUStations

Cabinet stations. StationID is passed to the app in the launch URL (?StationID=CAB-01). Editable by Admins without touching the app.

Expected size: tens of rows

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `StationID` | Text max 50 | yes | yes | **yes** |  |
| `StationName` | Text max 255 |  |  |  |  |
| `Active` | Boolean |  |  |  | Default: True. |
| `ExpectedAccountUPN` | Text max 255 |  |  |  | Optional. If set, requests from this station must be authored by this Microsoft account. |
| `Notes` | Note |  |  |  |  |

## POULocations

Known stocking locations (bin / shelf codes). New stock locations must reference an active row here.

Expected size: tens of rows

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `LocationCode` | Text max 50 | yes | yes | **yes** |  |
| `Description` | Text max 255 |  |  |  |  |
| `Active` | Boolean |  |  |  | Default: True. |

## POUEmployees

Badge holders. BadgeID is identification only. Role/MicrosoftUPN decide who may approve (via their own Microsoft sign-in), never the badge.

Expected size: tens to hundreds of rows

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `BadgeID` | Text max 50 | yes | yes | **yes** | TEXT. Leading zeros preserved. |
| `EmployeeName` | Text max 255 | yes |  |  |  |
| `Active` | Boolean |  |  |  | Default: True. |
| `Role` | Choice (Operator, Supervisor, Admin) |  |  |  | Default: Operator. |
| `MicrosoftUPN` | Text max 255 |  | yes |  | Entra sign-in name. Required for Supervisor/Admin approval authority. Matched case-insensitively against the authenticated author of a request. |
| `Notes` | Note |  |  |  |  |

## POUSessions

Badge sessions created by the POU-Session flow. Never readable by operators.

Expected size: hundreds per month (purged by weekly health flow)

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `SessionID` | Text max 64 | yes | yes | **yes** |  |
| `BadgeID` | Text max 50 |  | yes |  |  |
| `EmployeeName` | Text max 255 |  |  |  |  |
| `StationID` | Text max 50 |  |  |  |  |
| `AppAccountUPN` | Text max 255 |  |  |  | Microsoft account that was running the app. Requests in this session must be authored by it. |
| `StartedUtc` | DateTime |  |  |  |  |
| `LastActivityUtc` | DateTime |  |  |  |  |
| `SessionState` | Choice (Active, Ended, Expired) |  | yes |  | Default: Active. |
| `EndedReason` | Text max 100 |  |  |  |  |

## POUItems

Item master: one row per ItemID (part), regardless of how many locations stock it.

Expected size: hundreds to low thousands

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `ItemID` | Text max 100 | yes | yes | **yes** | TEXT. Upper-case, trimmed. Never numeric. |
| `ItemName` | Text max 255 | yes |  |  |  |
| `Description` | Note |  |  |  |  |
| `Manufacturer` | Text max 255 |  |  |  |  |
| `Priority` | Number |  |  |  |  |
| `LeadTimeDays` | Number |  |  |  |  |
| `UnitCost` | Currency |  |  |  |  |
| `Notes` | Note |  |  |  |  |
| `Active` | Boolean |  |  |  | Default: True. |
| `LegacySourceRows` | Text max 255 |  |  |  | Provenance: Inventory sheet rows this item was built from. |
| `CreatedViaRequestID` | Text max 64 |  |  |  |  |
| `ApprovedByUPN` | Text max 255 |  |  |  |  |

## POUStockLocations

Item/location stock record: one row per ItemID at one LocationCode. OnHandQty is written ONLY by POU-ProcessRequest / POU-Sweeper.

Expected size: hundreds to low thousands

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `StockKey` | Text max 200 | yes | yes | **yes** |  |
| `ItemID` | Text max 100 | yes | yes |  |  |
| `LocationCode` | Text max 50 | yes | yes |  |  |
| `ItemName` | Text max 255 |  |  |  | Denormalised copy of POUItems.ItemName for list display; repaired weekly. |
| `Area` | Text max 255 |  |  |  |  |
| `MinQty` | Number |  |  |  |  |
| `MaxQty` | Number |  |  |  |  |
| `OnHandQty` | Number |  |  |  | BLANK means no verified balance. Never 0 by default. |
| `StockVersion` | Number |  |  |  | Equals the SeqNo of the last applied ledger row for this StockKey. Default: 0. |
| `BalanceStatus` | Choice (NoBalance, Unverified, Verified) |  | yes |  | Default: NoBalance. |
| `LowStockFlag` | Boolean |  | yes |  | Stored (not calculated) so Power Apps can filter on it with delegation. Recomputed by posting and nightly. Default: False. |
| `Active` | Boolean |  | yes |  | Default: True. |
| `LastLedgerKey` | Text max 255 |  |  |  |  |
| `LastPostedUtc` | DateTime |  |  |  |  |
| `LastCountedUtc` | DateTime |  |  |  |  |
| `LegacySourceRow` | Text max 100 |  |  |  |  |
| `CreatedViaRequestID` | Text max 64 |  |  |  |  |

## POURequests

Request queue. Operators and supervisors can only ADD rows. A request is an instruction, not a completed movement.

Expected size: hundreds per week (purged after RequestRetentionDays)

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `RequestID` | Text max 64 | yes | yes | **yes** | Client-generated GUID kept across retries. Duplicate-request protection. |
| `RequestType` | Choice (ISSUE, RECEIPT, AUDIT, OPENING, ADJUSTMENT, REVERSAL, ITEM_CREATE, LOCATION_ADD, PARAM_UPDATE, APPROVE) | yes | yes |  |  |
| `RequestStatus` | Choice (Pending, Processing, AwaitingSupervisor, Succeeded, Rejected, Failed) |  | yes |  | Default: Pending. |
| `IsOpen` | Boolean |  | yes |  | Yes until a flow marks the request terminal. Lets the app list unresolved requests with one delegable filter. Default: True. |
| `SessionID` | Text max 64 |  |  |  |  |
| `StationID` | Text max 50 |  | yes |  |  |
| `StockKey` | Text max 200 |  | yes |  |  |
| `ItemID` | Text max 100 |  |  |  |  |
| `LocationCode` | Text max 50 |  |  |  |  |
| `Quantity` | Number |  |  |  | ISSUE/RECEIPT: units. AUDIT/OPENING: counted/opening quantity. ADJUSTMENT: new absolute quantity. |
| `ExpectedVersion` | Number |  |  |  | StockVersion the client saw when the count began (AUDIT stale detection). |
| `PayloadJson` | Note |  |  |  | ITEM_CREATE / LOCATION_ADD / PARAM_UPDATE fields as JSON. |
| `Reason` | Text max 255 |  |  |  |  |
| `ReversesLedgerKey` | Text max 255 |  |  |  |  |
| `TargetRequestID` | Text max 64 |  | yes |  | APPROVE: request being approved or rejected. |
| `Decision` | Choice (Approve, Reject) |  |  |  |  |
| `ClientLocalTime` | Text max 50 |  |  |  | Informational device time text. Never used for ordering. |
| `ResultCode` | Text max 50 |  |  |  |  |
| `ResultMessage` | Note |  |  |  |  |
| `LedgerKey` | Text max 255 |  |  |  |  |
| `InventoryEffect` | Choice (NotApplied, Applied, Unknown) |  |  |  | NotApplied is written only when no ledger intent exists (established, not assumed). |
| `AuthorizedByUPN` | Text max 255 |  |  |  |  |
| `ProcessingRunId` | Text max 100 |  |  |  |  |
| `ClaimedUtc` | DateTime |  |  |  |  |
| `AttemptCount` | Number |  |  |  | Default: 0. |
| `ProcessedUtc` | DateTime |  |  |  |  |

## POULedger

Append-only movement ledger. Written only by flows. PostingState: Intent (written before stock changes) -> Posted. Voided rows never changed stock.

Expected size: thousands per year; the largest list

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `LedgerKey` | Text max 255 | yes | yes | **yes** | StockKey#SeqNo. The unique constraint is the compare-and-swap that serialises writers per stock record. |
| `RequestID` | Text max 100 | yes | yes | **yes** | Unique: one ledger row per request, ever (duplicate-posting protection). |
| `LedgerType` | Choice (ISSUE, RECEIPT, AUDIT, OPENING, ADJUSTMENT, REVERSAL) | yes | yes |  |  |
| `Origin` | Choice (Live, Legacy) |  | yes |  | Default: Live. |
| `AffectsBalance` | Boolean |  |  |  | No for legacy rows: they are history only and never replayed against stock. Default: True. |
| `PostingState` | Choice (Intent, Posted, Voided) |  | yes |  | Default: Intent. |
| `StockKey` | Text max 200 |  | yes |  | Blank for legacy rows whose location cannot be established. |
| `ItemID` | Text max 100 |  | yes |  |  |
| `LocationCode` | Text max 50 |  |  |  |  |
| `SeqNo` | Number |  |  |  |  |
| `QtyDelta` | Number |  |  |  | Signed. Blank when unknown (opening, first count, legacy without data). |
| `QtyBefore` | Number |  |  |  |  |
| `QtyAfter` | Number |  |  |  |  |
| `BadgeID` | Text max 50 |  |  |  |  |
| `EmployeeName` | Text max 255 |  |  |  |  |
| `StationID` | Text max 50 |  |  |  |  |
| `AuthorizedByUPN` | Text max 255 |  |  |  |  |
| `OccurredUtc` | DateTime |  | yes |  |  |
| `OccurredLocalText` | Text max 40 |  |  |  |  |
| `Reason` | Text max 255 |  |  |  |  |
| `ReversesLedgerKey` | Text max 255 |  | yes |  |  |
| `LegacyUser` | Text max 255 |  |  |  | Name text exactly as recorded in the workbook. Never mapped to a badge. |
| `LegacyTimestampText` | Text max 50 |  |  |  | Original workbook timestamp, unmodified. |
| `LegacySource` | Text max 100 |  |  |  |  |
| `LocationResolution` | Choice (Recorded, UniqueAtCutover, Unresolved) |  |  |  | How StockKey was established for legacy rows. |

## POUOpsEvents

Operational findings raised by monitoring flows (stuck requests, drift, data-health). De-duplicates alert emails.

Expected size: tens per week

| Column | Type | Required | Index | Unique | Notes |
|---|---|---|---|---|---|
| `EventKey` | Text max 255 | yes | yes | **yes** |  |
| `EventType` | Text max 100 |  | yes |  |  |
| `Severity` | Choice (Info, Warning, Critical) |  |  |  | Default: Warning. |
| `Subject` | Text max 255 |  |  |  |  |
| `Details` | Note |  |  |  |  |
| `FirstSeenUtc` | DateTime |  |  |  |  |
| `LastSeenUtc` | DateTime |  |  |  |  |
| `OccurrenceCount` | Number |  |  |  | Default: 1. |
| `Resolved` | Boolean |  | yes |  | Default: False. |

