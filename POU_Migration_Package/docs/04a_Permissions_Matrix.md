# Permissions matrix (generated from schema/permissions.json)

* SharePoint permissions are the only real access control in this design. Hidden screens, disabled buttons and Visible properties in the app are convenience only.
* Every list below breaks permission inheritance and is given exactly these assignments. 'NONE' means the group has no assignment on the list (the list is invisible and unreadable to them).
* POU Flow Service is the SharePoint group that holds the dedicated service account used by the flow connections. It is the ONLY principal with write access to POUStockLocations and POULedger.
* The site Owners group keeps Full Control as break-glass. Its use bypasses the posting protocol and is detected by the nightly reconciliation.

## Groups

* **POU Operators**: Microsoft accounts that run the cabinet app (station accounts or named operators). Read inventory; can only ADD rows to POURequests.
* **POU Supervisors**: Named supervisors. Authenticated by their own Microsoft sign-in. Can ADD requests (incl. APPROVE) from their own device.
* **POU Admins**: Edit configuration and item master data. Cannot write stock or ledger.
* **POU Flow Service**: Dedicated service account(s) that own the Power Automate connections.

## Custom permission levels

* **Read** (built in): 
* **Contribute** (built in): 
* **POU Add Only** (created by provisioning): Read + Add Items. No edit, no delete.
* **POU Flow Writer** (created by provisioning): Read + Add + Edit Items. No delete.

## Matrix

| List | POU Operators | POU Supervisors | POU Admins | POU Flow Service |
|---|---|---|---|---|
| `POUSettings` | Read | Read | Contribute (read/add/edit/delete) | Read + Add + Edit (no delete) |
| `POUStations` | Read | Read | Contribute (read/add/edit/delete) | Read |
| `POULocations` | Read | Read | Contribute (read/add/edit/delete) | Read |
| `POUEmployees` | none (list invisible) | Read | Contribute (read/add/edit/delete) | Read |
| `POUSessions` | none (list invisible) | none (list invisible) | Read | Contribute (read/add/edit/delete) |
| `POUItems` | Read | Read | Contribute (read/add/edit/delete) | Read + Add + Edit (no delete) |
| `POUStockLocations` | Read | Read | Read | Read + Add + Edit (no delete) |
| `POURequests` | Read + **Add** only | Read + **Add** only | Read | Contribute (read/add/edit/delete) |
| `POULedger` | Read | Read | Read | Read + Add + Edit (no delete) |
| `POUOpsEvents` | none (list invisible) | Read | Contribute (read/add/edit/delete) | Contribute (read/add/edit/delete) |

The site **Owners** group keeps Full Control as break-glass. Any use of it bypasses the posting protocol; the nightly reconciliation (POU-Reconcile) detects the consequences.
