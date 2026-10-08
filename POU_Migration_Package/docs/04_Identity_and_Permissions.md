# 04 - Identity, authority and permissions

The exact list-by-list matrix is generated from `schema/permissions.json`: see `04a_Permissions_Matrix.md`. This page explains the reasoning, the write identity, and the supervisor path.

## Rules this design holds to

1. **A badge identifies; it never authenticates and never authorises.** Scanning a badge says "this is Jane". It cannot make anyone a supervisor. There is no admin flag in the app, no editable variable, no badge number that unlocks anything.
2. **Authority is the Microsoft sign-in of whoever *created the request*.** SharePoint stamps `Created By` (`Author`) on every row; neither the app nor the user can set it. The flow reads it and compares it with `POUEmployees` (active, role Supervisor/Admin, `MicrosoftUPN`).
3. **UI hiding is not access control.** Every button the app hides or disables is *also* refused by SharePoint or by the flow. The tests in `08_Testing_and_Acceptance.md` (T-PERM-*) prove it by trying the forbidden thing directly against SharePoint.
4. **Separation of duties.** An approver cannot be the author of the request, nor the same account as the employee whose session raised it.

## Who actually writes what

| Data | Written by | Through |
|---|---|---|
| `POURequests` rows (a *request*) | The signed-in app account (station/named operator, or supervisor) | Power Apps' own SharePoint connection runs **as the signed-in user** -> SharePoint records that user as Author. Permission level *POU Add Only*: can add, cannot edit or delete. |
| `POUStockLocations` (quantities) and `POULedger` | **Only** the flow service account | Flows use a SharePoint connection created by the service account, set to "use this connection" for run-only users (see `07_Deployment.md`). Group *POU Flow Service* is the only group with edit rights on those two lists. |
| `POUSessions` | Flow service account | `POU-Session` |
| `POUSettings`, `POUStations`, `POULocations`, `POUEmployees`, `POUItems` (admin data) | POU Admins directly in SharePoint, and the app's Admin screen (which can only do what the signed-in admin's SharePoint rights allow) | `POUItems` is also written by `POU-ProcessRequest` when an approved ITEM_CREATE is processed. |
| Everything via Site Owners | Break-glass only | Bypasses the protocol; the nightly `POU-Reconcile` detects the effect. |

So the "actual write identity" for a quantity is always the service account; the *accountability* for it is recorded separately (ledger: employee name and badge from the verified session, station, and for authority actions `AuthorizedByUPN`).

## What an operator account can and cannot do (even outside the app)

| Attempt | Result | Why |
|---|---|---|
| Edit `OnHandQty` in the SharePoint list view or Excel/"Edit in grid" | **403** | No edit right on `POUStockLocations`. |
| Delete or edit a ledger row | **403** | Read only. |
| Add a `POURequests` row claiming to be a supervisor's APPROVE | Row is created, then **rejected `NOT_AUTHORIZED`** by the flow | `Author` is the operator's account, which is not in the privileged set. |
| Add a request with another employee's session id | **Rejected `SESSION_ACCOUNT_MISMATCH`** | Session is bound to the account that logged in; `Author` differs. |
| Replay an old request id | Returns the **stored** outcome; nothing is posted twice | Unique `RequestID` and unique `LedgerKey`. |
| Read badge numbers / employees / sessions | **No access** | Lists `POUEmployees`, `POUSessions`, `POUOpsEvents` are invisible to operators. |
| Edit settings | **403** | Read only. |

(Operators can *read* `POURequests` and `POULedger` on purpose: they see their station's status and history. The price is that an operator can read other stations' request text. SharePoint's "read items created by the user" setting would hide that, but would also hide the approval queue from supervisors, so it is left off - an open decision for IT, `02_Architecture.md` D-list.)

## The supervisor path that actually works

A supervisor must authenticate with **their own Microsoft account**, because that is the only thing the flow can trust. Three practical routes, all the same app:

1. **Own device** (phone browser, laptop, office PC): open the app, sign in as yourself, press **Continue as supervisor** on the first screen. The button appears only if your account is an active Supervisor/Admin in `POUEmployees` (a convenience check; the flow re-checks).
2. **Cabinet PC, supervisor present**: open a private/InPrivate browser window on the cabinet PC, go to the app link, sign in as yourself, **Continue as supervisor**. Close the window when done. The station's own session is not affected.
3. **Later**: the operator's request waits in `AwaitingSupervisor` (nothing changed); the supervisor approves from the **Approvals** tab whenever convenient (default expiry 24 h, `ApprovalExpiryHours`).

In supervisor mode the same audit/new-item/adjustment screens file the request *as the supervisor*; the flow sees an authorised `Author` and needs no second approver. Reversals, adjustments, parameter changes and APPROVE always need a supervisor author; `OPENING` needs an Admin author.

## Groups and how they map

| SharePoint group (created by `provision`) | Put in it | Gets |
|---|---|---|
| POU Operators | Station accounts / named operators who run the app | Read most, add-only on requests |
| POU Supervisors | Named supervisors' accounts | As operators + read on `POUEmployees`, `POUOpsEvents` |
| POU Admins | Named admins | Edit configuration lists |
| POU Flow Service | The service account that owns the flows | Edit on stock, ledger, sessions, settings state keys |

Canvas apps are shared with **Microsoft Entra (Azure AD) groups or users**, not with SharePoint groups. Recommended: create one Entra security group per row above and add each Entra group into the matching SharePoint group (the provisioning script creates the SharePoint groups; adding Entra groups to them is a two-minute manual step in `07_Deployment.md`), then share the app with the same Entra groups.

## What IT must confirm (do not assume)

1. **Licence of every signed-in account.** Station/named-operator accounts need a licence that includes SharePoint Online and permission to run a canvas app that uses only standard connectors. A *shared* "station" user is a normal licensed user, not a shared mailbox (shared mailboxes cannot sign in).
2. **Licence and capacity of the flow service account** - see `05_Platform_Facts_and_Capacity.md`; at the smallest plan the flows run out of daily actions within a few dozen transactions.
3. **Conditional Access / MFA** for station accounts and the service account: the service account's connections must keep working unattended (token lifetime, sign-in frequency, location policies).
4. **Data Loss Prevention policy** for the environment: SharePoint and Office 365 Outlook (used only for report mail) must be in the same data group; the SharePoint action used is "Send an HTTP request to SharePoint" - confirm it is not blocked.
5. **Environment**: where the flows and app may be created (default vs a dedicated environment), who may import solutions, and whether the "service account owns the flows" arrangement is allowed by policy.
6. **Whether the platform supplies the caller's identity header** (`x-ms-user-email-encoded`) for app-triggered flows in your tenant. The design does not depend on it for security (the request `Author` is authoritative), but the Session flow prefers it; test T-ID-01 checks it.
7. **Entra group creation** and nested-group support for SharePoint groups.
8. **Retention / records policy** on the ledger list (append-only evidence): do not apply a policy that deletes after 90 days; the flows purge only `POURequests` and `POUSessions` (`RequestRetentionDays`, `SessionRetentionDays`), never the ledger.
