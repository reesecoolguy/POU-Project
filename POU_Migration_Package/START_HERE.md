# START HERE - POU inventory: Excel/VBA -> SharePoint Online + Power Apps + Power Automate

This package is a **working migration kit**, not a proposal: scripts that read your workbook and build import files, scripts that provision SharePoint, eight generated Power Automate flows, a generated canvas app, tests, and the documents to deploy and cut over. It replaces `POU_Inventory_CodePack.zip` (which hardened Excel and did not migrate anything).

**This ZIP is a working folder, not an importable Power Platform solution.** The only solution-shaped file is `flows/POU_Flows_solution_CANDIDATE.zip`, and it is labelled unvalidated. There is no `.msapp`: Power Apps Studio or the Power Platform CLI must produce one.

## Read this before anything else: how much to trust it

* **Proven here (locally):** the migration of your actual workbook (254 stock records, 251 items, 22 locations, 7 employees, 26 history rows; 252 opening balances = 973 units, reconciled two independent ways), the SharePoint provisioning logic, and the flow logic - including two operators taking the last unit, retries, lost responses, crashes between every pair of writes, and recovery - run against **a model of SharePoint and a home-made interpreter of Power Automate**.
* **Not proven:** anything in a real Microsoft 365 tenant. No flow has been imported, no app opened in Power Apps Studio, no scanner tried. `docs/11_Validation_Status.md` labels every component *generated / statically checked / locally tested / awaiting tenant validation*. Believe the labels.
* **One decision blocks go-live:** the licence of the account that owns the flows. The design is correct but costs about 112 flow actions per ADD/REMOVE; on the smallest Microsoft 365 allowance that is a few dozen movements a day. See `docs/05_Platform_Facts_and_Capacity.md`.

## Read in this order

| # | File | Why |
|---|---|---|
| 1 | `docs/01_Source_Analysis_and_Corrections.md` | What your workbook/VBA really does, and what was wrong in the earlier proposal |
| 2 | `docs/02_Architecture.md` | The design, the posting protocol, assumptions, and the decisions that are yours |
| 3 | `docs/05_Platform_Facts_and_Capacity.md` | Limits that shape the design; the licence/capacity numbers |
| 4 | `docs/06_Consistency_Limits.md` | Why "just use ETags" is not enough; every failure and its recovery; SharePoint's limits; the SQL/Dataverse alternative |
| 5 | `docs/04_Identity_and_Permissions.md` (+ `04a`) | Badge vs Microsoft account vs flow identity; the supervisor path; what IT must confirm |
| 6 | `docs/07_Deployment.md` | Step-by-step, written for someone new to Power Platform |
| 7 | `docs/08_Testing_and_Acceptance.md` | The tests, including the ones only you can run (tenant, scanner) |
| 8 | `docs/09_Cutover_and_Rollback.md` | One authoritative system, shadow/replay comparison, verified opening balances, rollback that keeps new transactions |
| 9 | `docs/10_Maintenance.md` | Daily routine, alerts, repairs, everyday admin |
| 10 | `docs/11_Validation_Status.md`, `docs/12_Continuation_Checklist.md` | What is proven, what is next |

## What is where

```
START_HERE.md
docs/                  the documents above; 03a/03b/04a are generated from schema/; alt/PostMovement.sql = SQL variant
schema/                lists.json, permissions.json, settings_defaults.json   (single source of truth)
scripts/               Windows .cmd wrappers, numbered in order of use; config.cmd is the only file you edit
pou_tools/             Python: provision, extract, transform, import, verify, tenant probe, permission audit, shadow replay
migration/             GENERATED from your workbook: import/*.csv, exceptions/exceptions.csv, reconciliation/*.csv, RUN_SUMMARY.md
flows/                 definitions/*.json, docs/*.md (action by action), POU_Flows_solution_CANDIDATE.zip (NOT validated)
app/                   src/*.fx.yaml (best-effort Studio source), docs/CONTROL_REFERENCE.md, docs/DELEGATION.md
pou_flows/ pou_app/    generators for flows and app;  flowlab/  the flow interpreter used by the tests
tests/                 ~220 automated tests
```

## First hour

1. Read `docs/01` and `docs/02`; send IT the lists in `docs/04` ("What IT must confirm") and `docs/05` ("Capacity").
2. Install Python (python.org, tick "Add to PATH" and "py launcher"), run `scripts\0_setup_python.cmd`.
3. Run `scripts\2_extract_validate.cmd` (offline). Open `migration\RUN_SUMMARY.md` and `migration\exceptions\exceptions.csv`. The numbers should match the table at the top of this page.
4. Then follow `docs/07_Deployment.md` from step 2.

## Script cheat-sheet (all dry-run unless you add APPLY)

| Script | Does |
|---|---|
| `0_setup_python.cmd` | private Python + 3 libraries |
| `1_provision.cmd [APPLY]` | lists, columns, indexes, unique keys, groups, permissions, default settings |
| `2_extract_validate.cmd` | workbook -> import files + exceptions + reconciliation (offline) |
| `3_import.cmd [APPLY] [stages]` | loads reference data; `openings` stage = OPENING requests posted by the flow |
| `4_verify_import.cmd` | SharePoint vs import files, by item/location |
| `5_tenant_probe.cmd APPLY [5100]` | measures unique keys, ETag, races, 5,000-item threshold in a throw-away list |
| `6_permission_audit.cmd <group>` | what a signed-in test account can really do vs the matrix |
| `7_rebuild_package.cmd` | regenerate flows/app/docs and run all tests |
| `8_shadow_replay.cmd plan\|replay\|compare` | comparison period without dual posting |

No credentials are stored anywhere in this package. Sign-in is an interactive device-code prompt; `config.cmd` holds a site address, a tenant name and an app (client) id - none are secrets.

## What you must do, what IT must supply, what is untested

See the end of the hand-over message and `docs/12_Continuation_Checklist.md`; in short: decide the licence (D1), have IT create the app registration/groups/service account and allow the connections, run the tenant probe and permission audit, import/paste the flows and app and fix what the portal objects to, then run the **R** tests (two-PC last-unit race and the scanner tests on the real cabinet PC) before any real stock moves.
