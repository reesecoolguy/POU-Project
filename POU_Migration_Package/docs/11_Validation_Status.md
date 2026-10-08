# 11 - Validation status of every component

Status vocabulary (each component carries the **highest** status it has actually reached):

| Label | Meaning |
|---|---|
| **Generated** | Produced by a script from the single sources (`schema/*.json`, `pou_flows/`, `pou_app/`). Nothing else claimed. |
| **Statically checked** | Parsed/linted by our own checks (syntax, references, limits, conformity to the schema and permission matrix). |
| **Locally tested** | Executed in this package's test suite against an **in-memory model of SharePoint** and, for flows, our **own interpreter** of the Power Automate expression language. |
| **Tenant-tested** | Run against a real Microsoft 365 tenant. **Nothing in this package has reached this level.** |
| **Awaiting validation** | Needs a tenant/hardware run described in `08_Testing_and_Acceptance.md`. |

Date of this status: build of this package. Local suite: ~220 tests, all passing at hand-over (`python -m pytest -q`).

## Components

| Component | Where | Generated | Static | Local test | Tenant | Notes |
|---|:-:|:-:|:-:|:-:|:-:|---|
| List/field/index/unique schema | `schema/lists.json` | yes | yes (validator: names, lengths, indexes, uniques, choice values) | yes (provisioned into the model) | **awaiting** | `tenant_probe` U1/R1/R2 settle unique/ETag behaviour. |
| Permission matrix | `schema/permissions.json` | yes | yes (every flow write checked against the matrix) | yes (real enforcement inside the model) | **awaiting** | `permission_audit` T-PERM-02. |
| Provisioning script | `pou_tools/provision.py` | - | - | yes (dry run, apply, idempotent re-run, drift, no overwrite) | **awaiting** | REST calls are the documented SharePoint REST API; real-tenant quirks (e.g. field creation order) are possible. |
| Extract / validate / transform | `pou_tools/extract.py`, `transform.py` | yes (`migration/`) | - | yes (14 tests; golden numbers on the real workbook; independent cross-check of 973 units / 252 openings) | n/a | Pure offline processing of your file. |
| Import / post-import verification | `pou_tools/import_data.py`, `verify_import.py` | - | - | yes (dry run, resume, no-overwrite, refuses balances) | **awaiting** | |
| Tenant probe, permission audit | `pou_tools/tenant_probe.py`, `permission_audit.py` | - | - | yes (against the model) | **awaiting** | They exist precisely to turn the model's assumptions into measured facts. |
| Shadow/replay | `pou_tools/shadow_replay.py` | - | - | yes | **awaiting** | |
| **Flow definitions (8)** | `flows/definitions/*.json` | yes | yes: every expression parsed (including never-executed branches), nesting depth <= 8, <= 500 actions, references exist, SharePoint columns/choices exist, settings keys exist, write permissions conform | **yes**: executed by `flowlab` against the model - posting, auth, approvals, stale audits, reversals, master data, sweeper recovery, reports, **crash/lost-response at every SharePoint call, 25 random two-operator races, out-of-band edits, 5,300-row completeness** | **awaiting** | See "Interpreter fidelity" below - the largest single risk. |
| Flow solution package | `flows/POU_Flows_solution_CANDIDATE.zip` | yes | yes (XML well-formed, ids consistent, 8 workflows) | - | **awaiting - never imported, not built by `pac`** | Labelled CANDIDATE. Fallback: `flows/docs/*.md`. |
| Action-by-action flow docs | `flows/docs/*.md` | yes | yes (not stale - tested) | - | n/a | |
| Canvas app source (YAML) | `app/src/*.fx.yaml` | yes | yes (own linter: balanced syntax, every control/list/column/flow/setting/variable reference exists, choice `.Value`, flow argument counts, delegable queries, indexed filter columns on large lists) | **no** (Power Fx is not executed anywhere here) | **awaiting - Studio has never opened it** | The paste format was written from the published format. |
| Control reference + formulas | `app/docs/CONTROL_REFERENCE.md` | yes | as above | no | awaiting | Hand-build route if paste fails. |
| Delegation matrix | `app/docs/DELEGATION.md` | yes | yes | - | **awaiting (Studio's own warnings are the proof)** | |
| SQL variant | `docs/alt/PostMovement.sql` | yes | - | pattern only, on SQLite (`tests/test_sql_alternative.py`) | **not executed on SQL Server** | |
| Dataverse variant | `docs/06_...` | description only | - | - | not built | |
| Documents | `docs/*.md`, `START_HERE.md` | partly (`03a/03b/04a` generated) | - | - | - | |

## Interpreter fidelity (what "locally tested flows" does and does not mean)

`flowlab` re-implements the subset of the Logic Apps expression language and action semantics that the generated flows use (about 70 functions, conditions, loops, `Until`, scopes, run-after, `Terminate`, SharePoint and mail actions). It was written from Microsoft's published behaviour and **not** checked against the real engine. Known places where reality could differ and the design's answer:

| Area | Design answer |
|---|---|
| Container (scope/condition) run-after status when an inner action fails | The flows **never rely on a container's status**: risky actions are inspected with `actions('X')?['status']` and steps after containers run after *all* statuses and are guarded by variables. |
| `and()`/`or()` evaluating all arguments, null handling in comparisons | Every comparison is null-safe (`coalesce`); a regression test caught and fixed several of these. |
| `union()` on arrays of objects removes duplicates | Rows carry unique ids, so no row is lost; the interpreter models the de-duplication. |
| `json()`, `formatDateTime`, `ticks`, `addDays`, `convertTimeZone` details | Used in simple, documented ways; ISO-8601 UTC strings throughout. Tenant test T-REP-01/T-ID-04 exercise them. |
| SharePoint behaviours (ETag/412, unique-key error codes, the 5,000 threshold) | Modelled from documentation; `tenant_probe` U1, E1-E3, R1, R2, L1-L4 measure them. |
| Expression/limit constants (8,192 chars, depth 8, 500 actions, 120 s response) | From documentation; enforced statically. |
| Action cost and speed | Counted exactly in the model (`docs/generated/capacity.json`); real latency is a tenant measurement (T-CAP-01). |

## Known limitations and risks (not hidden)

1. **Nothing has run in a tenant.** Expect the first import/paste to need fixes. The tests give a good chance that the *logic* is right; they give no evidence about portal behaviour.
2. **Capacity/licence** (decision D1) may make the SharePoint+flows design uneconomical; the alternative is described and partly demonstrated.
3. **Fixed 1366x768 layout**; tablets/phones are not supported by the generated layout.
4. **Timers** (idle sign-out, scan debounce, status polling) are central to behaviour; they are untested in a real player (T-APP-04).
5. **`SaveData/LoadData`** local outbox may be unavailable in some players (T-APP-09); the in-memory retained request id still protects within a session.
6. **Time display**: the History screen's fallback time uses the PC's zone (must be Chicago); ledger rows carry Chicago text written by the flow.
7. **Ambiguous legacy history**: the workbook never recorded locations, so history for K102516/K102517/K13471 is not attributable to a location (kept, flagged `Unresolved`).
8. **A request keyed twice by a person** after a restart with no outbox cannot be detected (two legitimate requests).
9. **Audit-trail strength**: append-only by permission, not cryptographic.
10. **Reports** are suggestions only and ignore open purchase orders; `Priority` is empty in the source so the "priority 1 on-hand" note found in the workbook cannot be satisfied yet.
