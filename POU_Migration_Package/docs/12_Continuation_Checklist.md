# 12 - Continuation checklist (what is done, what is next)

Use this to resume without repeating the analysis. Tick items in a copy.

## Done in this package (generated + locally tested unless stated)

- [x] Source analysis of the workbook and VBA; critique of the CodePack (`01`)
- [x] Data model (10 lists), permission matrix, defaults - single source of truth (`schema/`), generated docs (`03a`, `03b`, `04a`)
- [x] Provisioning with dry run / safe re-run / drift report
- [x] Migration pipeline: extract, validate, transform, import files, exception report (79 items: 33 WARN, 46 INFO), row-count and quantity reconciliation, importer, post-import verifier
- [x] Eight flows: Session, ProcessRequest, Sweeper, Monitor, DailyLowStock, Reconcile, WeeklyHealth, WeeklyUsage - definitions, action-by-action docs, solution CANDIDATE
- [x] Posting protocol proven in the model: last-unit race, retries, lost response, crash at every call, recovery, out-of-band edits
- [x] Canvas app: 8 screens, 248 controls, complete Power Fx, lint, delegation matrix, control reference
- [x] Tenant probe, permission audit, shadow/replay, SQL-variant pattern test
- [x] Deployment, testing, cutover/rollback, maintenance, status documents

## Next, in order (you / IT)

1. [ ] **Decide D1 (licence of the flow service account)** and the other open decisions in `02_Architecture.md` (D1-D9). Blocking.
2. [ ] Create the site, app registration, groups; run `1_provision` dry run then APPLY (`07`, steps 2-5).
3. [ ] Run `5_tenant_probe` and `6_permission_audit` for all four groups. **Any failure stops the project until understood** (`06` explains what each assumption protects).
4. [ ] `3_import` reference data (no quantities).
5. [ ] Flows: try the solution candidate (`pac solution pack` then import); if refused, send the exact error back so the packaging can be corrected, or build the first three flows by hand (`07` step 9).
6. [ ] App: paste the YAML or build from `CONTROL_REFERENCE.md`; clear Studio's red/blue underlines; report any delegation warning (the delegation table is then wrong).
7. [ ] Run the **R** tests in `08` on a TEST site with a test station, including scanner tests on the real cabinet PC and T-RACE-01 on two PCs.
8. [ ] Fill in `POUEmployees` roles and `MicrosoftUPN`; real report recipients.
9. [ ] Comparison period with `shadow_replay` (`09`), then cutover day.

## Things to feed back to whoever maintains the generators

| If you find... | Change this source | Then |
|---|---|---|
| The portal refuses the solution zip | `pou_flows/build.py` (solution layout) | `scripts\7_rebuild_package.cmd` |
| Studio refuses the YAML | `pou_app/spec.py` (emitter), possibly control type names in `pou_app/widgets.py` | rebuild |
| A control name/formula needs to change | `pou_app/screens.py` / `widgets.py` / `formulas.py` | rebuild (the linter and `tests/test_app_lint.py` re-check) |
| A flow expression behaves differently in Power Automate than in `flowlab` | the expression in `pou_flows/*.py`; add a regression test using the real behaviour | rebuild, run tests |
| A SharePoint behaviour differs from `pou_tools/fakesp.py` | fix the model first (so tests show the failure), then the flow/tool | |
| Latency or capacity is unacceptable | consider the SQL/Dataverse core (`06` section 4) | |

## Known work not done (candidates for the next session)

- A **supported-tool build** of the flow solution and the canvas app (`pac`); needs a machine with the Power Platform CLI. Replacing the CANDIDATE labels with tenant-tested results.
- Responsive/tablet layout; accessibility pass (tab order is set, screen-reader labels are not).
- A hash-chained ledger for tamper evidence (currently permission + nightly chain check).
- A fully worked Dataverse or SQL implementation of the posting core (only the pattern and a T-SQL sketch exist).
- Purchase-order awareness in the replenishment suggestions (deliberately out of scope: suggestions never imply open orders are considered).
- Permanent IDs for the 142 `TEMP####` items; `Priority` / `Lead Time` / `Cost` data (empty in the source) and the "priority 1 on-hand" report the workbook's stray note asks for.
- An Entra-group automation step (adding Entra groups into the SharePoint groups is manual).
