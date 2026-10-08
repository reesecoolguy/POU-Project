# app/ - the canvas app

| Path | What |
|---|---|
| `src/App.fx.yaml`, `src/scr*.fx.yaml` | The app in Power Apps source ("As") syntax: App properties + 8 screens. **Never opened in Studio** - treat as best effort. Regenerate with `python -m pou_app.build`. |
| `docs/CONTROL_REFERENCE.md` | Every control: exact name, type, and every formula. Build from this if pasting is refused. |
| `docs/DELEGATION.md` | Every SharePoint query in the app and its delegation expectation. |

An `.msapp` is **not** provided: it can only be produced by Power Apps Studio or the Power Platform CLI, neither of which was available. Do not rename the YAML to `.msapp`.
Assembly: `docs/07_Deployment.md` step 10. Data sources and flow names must match exactly.
