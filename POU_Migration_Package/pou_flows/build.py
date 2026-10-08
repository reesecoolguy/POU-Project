"""Build the flow deliverables from the generators.

  python -m pou_flows.build --site-url https://TENANT.sharepoint.com/sites/POU --out flows

Writes:
  <out>/definitions/<Flow>.json         the Logic Apps workflow definition exactly as Power Automate stores it (properties.definition)
  <out>/docs/<Flow>.md                  action-by-action reference: every action, run-after, SharePoint call, expression
  <out>/docs/FLOW_INDEX.md              overview, connections, capacity numbers
  <out>/solution_candidate/             an UNPACKED Power Platform solution tree built to the documented structure   (NOT validated)
  <out>/POU_Flows_solution_CANDIDATE.zip  the same, zipped                                                         (NOT validated)

The solution is only a candidate: it has never been imported into a tenant by us. docs/04_Deployment.md gives the supported
manual route (build from the action-by-action docs) in case import is refused.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from . import process, reports, session, sweeper
from .common import DEFAULT_SITE_URL

NS = uuid.UUID("6f1c1f56-2d6e-4b0e-9a44-5f0c9f4d1e01")
SOLUTION_UNIQUE = "POUInventoryFlows"
PUBLISHER_PREFIX = "pou"

FLOWS = [
    ("POU-Session", session.build, "Instant (Power Apps V2)", "On demand from the app"),
    ("POU-ProcessRequest", process.build, "Instant (Power Apps V2)", "On demand from the app / supervisor console"),
    ("POU-Sweeper", sweeper.build, "Recurrence 5 min", "Every 5 minutes (probe costs ~8 actions when idle)"),
    ("POU-Monitor", reports.build_monitor, "Recurrence 1 h", "Hourly"),
    ("POU-DailyLowStock", reports.build_lowstock, "Recurrence 1 h (tick)", "Once per local day at LowStockReportHourLocal"),
    ("POU-Reconcile", reports.build_reconcile, "Recurrence 1 h (tick)", "Once per night at ReconcileHourLocal"),
    ("POU-WeeklyHealth", reports.build_health, "Recurrence 1 h (tick)", "Weekly on WeeklyDayOfWeek / WeeklyHourLocal"),
    ("POU-WeeklyUsage", reports.build_usage, "Recurrence 1 h (tick)", "Weekly on WeeklyDayOfWeek / WeeklyHourLocal"),
]


def flow_guid(name: str) -> str:
    return str(uuid.uuid5(NS, name)).upper()


def connection_refs(fl) -> dict:
    uses_mail = "shared_office365" in json.dumps(fl.definition())
    refs = {"shared_sharepointonline": {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": f"{PUBLISHER_PREFIX}_sharedsharepointonline_pou"},
                                        "api": {"name": "shared_sharepointonline"}}}
    if uses_mail:
        refs["shared_office365"] = {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": f"{PUBLISHER_PREFIX}_sharedoffice365_pou"},
                                    "api": {"name": "shared_office365"}}
    return refs


# ---------------------------------------------------------------------------------------------------------------------
# action-by-action documentation
# ---------------------------------------------------------------------------------------------------------------------
def _summ(a: dict) -> list[str]:
    t = a["type"]
    out = []
    if t == "ApiConnection":
        inp = a["inputs"]
        op = inp["host"]["operationId"]
        p = inp["parameters"]
        if op == "HttpRequest":
            h = p.get("parameters/headers", {})
            verb = h.get("X-HTTP-Method") or p["parameters/method"]
            out.append(f"**SharePoint > Send an HTTP request to SharePoint**  `{verb}`")
            out.append(f"- Site Address: `{p['dataset']}`")
            out.append(f"- Uri: `{p['parameters/uri']}`")
            hh = {k: v for k, v in h.items() if k not in ("Accept",)}
            out.append(f"- Headers: `{json.dumps(hh)}`  (+ Accept: application/json;odata=verbose)")
            if "parameters/body" in p:
                out.append("- Body:\n```json\n" + json.dumps(p["parameters/body"], indent=2) + "\n```")
        else:
            out.append(f"**Office 365 Outlook > Send an email (V2)**")
            out.append("```json\n" + json.dumps(p, indent=2) + "\n```")
    elif t in ("Compose", "InitializeVariable", "SetVariable", "IncrementVariable", "AppendToArrayVariable", "Select", "Query", "Join", "Table", "Response", "Delay", "Terminate"):
        label = {"Compose": "Data Operation > Compose", "InitializeVariable": "Variable > Initialize variable", "SetVariable": "Variable > Set variable",
                 "IncrementVariable": "Variable > Increment variable", "AppendToArrayVariable": "Variable > Append to array variable",
                 "Select": "Data Operation > Select", "Query": "Data Operation > Filter array", "Join": "Data Operation > Join",
                 "Table": "Data Operation > Create HTML/CSV table", "Response": "Power Apps > Respond to a PowerApp or flow", "Delay": "Schedule > Delay",
                 "Terminate": "Control > Terminate"}[t]
        out.append(f"**{label}**")
        out.append("```json\n" + json.dumps(a["inputs"], indent=2) + "\n```")
    elif t == "If":
        out.append("**Control > Condition**  (advanced mode)")
        out.append("```json\n" + json.dumps(a["expression"]) + "\n```")
    elif t == "Foreach":
        out.append(f"**Control > Apply to each**  concurrency {a.get('runtimeConfiguration', {}).get('concurrency', {}).get('repetitions', 'default')}")
        out.append(f"- Select an output: `{a['foreach']}`")
    elif t == "Until":
        out.append(f"**Control > Do until**  limit count {a['limit']['count']}, timeout {a['limit']['timeout']}")
        out.append(f"- Condition: `{a['expression']}`")
    elif t == "Scope":
        out.append("**Control > Scope**")
    else:
        out.append(f"**{t}**")
    return out


def _render(actions: dict, indent: int, lines: list[str]):
    pad = "  " * indent
    for name, a in actions.items():
        ra = a.get("runAfter") or {}
        ra_txt = "first action" if not ra else "; ".join(f"after `{k}` {'/'.join(v)}" for k, v in ra.items())
        lines.append(f"{pad}- ### `{name}`" if indent == 0 else f"{pad}- **`{name}`**")
        lines.append(f"{pad}  - Run after: {ra_txt}")
        for l in _summ(a):
            for sub in l.split("\n"):
                lines.append(f"{pad}  {sub}" if not sub.startswith("```") else f"{pad}  {sub}")
        for key, label in (("actions", "Inside"),):
            if key in a and a[key]:
                lines.append(f"{pad}  - {label} `{name}`:")
                _render(a[key], indent + 2, lines)
        if "else" in a and a["else"].get("actions"):
            lines.append(f"{pad}  - If NO (else) in `{name}`:")
            _render(a["else"]["actions"], indent + 2, lines)


def count_all(actions: dict) -> int:
    n = 0
    for a in actions.values():
        n += 1
        for k in ("actions",):
            if k in a:
                n += count_all(a[k])
        if "else" in a:
            n += count_all(a["else"].get("actions", {}))
    return n


def doc_for(fl, trigger_desc: str, schedule: str) -> str:
    d = fl.definition()
    lines = [f"# {fl.name} - {fl.display}", "", fl.description, "",
             f"- **Trigger**: {trigger_desc} - {schedule}", f"- **Actions** (all levels): {count_all(d['actions'])}",
             f"- **Connections**: SharePoint (`shared_sharepointonline`) as the flow service account" + (", Office 365 Outlook (`shared_office365`)" if "shared_office365" in json.dumps(d) else ""),
             "- **How to read this**: actions are listed in run order. Indented items are inside the parent scope / condition branch / loop. "
             "`Compose_*`, `Set_*` and `Result_*` actions are the decision points; each SharePoint call shows its exact URI and body. "
             "Expressions are the literal text to type into the Expression tab (without the leading `@` when you type into the editor's expression box).",
             "- **Error handling model**: no step relies on a container's Succeeded/Failed status. Risky calls are followed by a step that runs "
             "after Succeeded/Failed/Skipped/TimedOut and inspects `actions('<call>')?['status']`. Outcome fields live in variable `vRes`; the "
             "Response action runs after everything and its defaults say 'Processing / UNCONFIRMED - do not repeat'.", ""]
    lines += ["## Trigger", "```json", json.dumps(fl.trigger, indent=2), "```", "", "## Actions", ""]
    _render(d["actions"], 0, lines)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------------------------------
def solution_candidate(out: Path, built: dict):
    root = out / "solution_candidate"
    if root.exists():
        shutil.rmtree(root)
    (root / "Workflows").mkdir(parents=True)
    wfs, roots = [], []
    for name, fl in built.items():
        g = flow_guid(name)
        fn = f"{name}-{g}.json"
        body = {"properties": {"connectionReferences": connection_refs(fl), "definition": fl.definition(), "templateName": None}, "schemaVersion": "1.0.0.0"}
        (root / "Workflows" / fn).write_text(json.dumps(body, indent=2), encoding="utf-8")
        roots.append(f'      <RootComponent type="29" id="{{{g.lower()}}}" behavior="0" />')
        wfs.append(f"""    <Workflow WorkflowId="{{{g.lower()}}}" Name="{name}">
      <JsonFileName>/Workflows/{fn}</JsonFileName>
      <Type>1</Type><Subprocess>0</Subprocess><Category>5</Category><Mode>0</Mode><Scope>4</Scope><OnDemand>0</OnDemand>
      <TriggerOnCreate>0</TriggerOnCreate><TriggerOnDelete>0</TriggerOnDelete><AsyncAutodelete>0</AsyncAutodelete><SyncWorkflowLogOnFailure>0</SyncWorkflowLogOnFailure>
      <StateCode>0</StateCode><StatusCode>1</StatusCode><RunAs>1</RunAs><IsTransacted>1</IsTransacted><IntroducedVersion>1.0</IntroducedVersion>
      <IsCustomizable>1</IsCustomizable><BusinessProcessType>0</BusinessProcessType><IsCustomProcessingStepAllowedForOtherPublishers>1</IsCustomProcessingStepAllowedForOtherPublishers>
      <PrimaryEntity>none</PrimaryEntity>
      <LocalizedNames><LocalizedName languagecode="1033" description="{name}" /></LocalizedNames>
    </Workflow>""")
    (root / "solution.xml").write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml version="9.2.0.0" SolutionPackageVersion="9.2" languagecode="1033" generatedBy="POU-Migration-Package" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <SolutionManifest>
    <UniqueName>{SOLUTION_UNIQUE}</UniqueName>
    <LocalizedNames><LocalizedName description="POU Inventory Flows" languagecode="1033" /></LocalizedNames>
    <Descriptions />
    <Version>1.0.0.0</Version>
    <Managed>0</Managed>
    <Publisher>
      <UniqueName>pouinventory</UniqueName>
      <LocalizedNames><LocalizedName description="POU Inventory" languagecode="1033" /></LocalizedNames>
      <Descriptions />
      <EMailAddress xsi:nil="true" /><SupportingWebsiteUrl xsi:nil="true" />
      <CustomizationPrefix>{PUBLISHER_PREFIX}</CustomizationPrefix>
      <CustomizationOptionValuePrefix>74291</CustomizationOptionValuePrefix>
      <Addresses />
    </Publisher>
    <RootComponents>
{chr(10).join(roots)}
    </RootComponents>
    <MissingDependencies />
  </SolutionManifest>
</ImportExportXml>
""", encoding="utf-8")
    conn = "".join(f"""
    <connectionreference connectionreferencelogicalname="{PUBLISHER_PREFIX}_{api.replace('_', '')}_pou">
      <connectionreferencedisplayname>{disp}</connectionreferencedisplayname>
      <connectorid>/providers/Microsoft.PowerApps/apis/{api}</connectorid>
      <iscustomizable>1</iscustomizable><statecode>0</statecode><statuscode>1</statuscode>
    </connectionreference>""" for api, disp in (("shared_sharepointonline", "SharePoint"), ("shared_office365", "Office 365 Outlook")))
    (root / "customizations.xml").write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Entities />
  <Roles />
  <Workflows>
{chr(10).join(wfs)}
  </Workflows>
  <FieldSecurityProfiles />
  <Templates />
  <EntityMaps />
  <EntityRelationships />
  <OrganizationSettings />
  <optionsets />
  <CustomControls />
  <EntityDataProviders />
  <connectionreferences>{conn}
  </connectionreferences>
  <Languages><Language>1033</Language></Languages>
</ImportExportXml>
""", encoding="utf-8")
    (root / "[Content_Types].xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/octet-stream" /><Default Extension="json" ContentType="application/octet-stream" /></Types>
""", encoding="utf-8")
    (root / "README_CANDIDATE.txt").write_text(
        "STATUS: CANDIDATE - NOT VALIDATED.\n"
        "This tree follows the documented unpacked layout of a Power Platform solution containing cloud flows (solution.xml, customizations.xml,\n"
        "Workflows/<name>-<guid>.json). It was generated and statically checked, but it has NEVER been imported into a tenant and was NOT produced by\n"
        "the Power Platform CLI (pac). If the portal refuses it, use the manual route in docs/04_Deployment.md (build each flow from flows/docs/<Flow>.md).\n"
        "After import: open each flow, set the two connections (SharePoint, Office 365 Outlook) to the FLOW SERVICE ACCOUNT, edit the Cfg_SiteUrl action, then turn the flow on.\n",
        encoding="utf-8")
    zpath = out / "POU_Flows_solution_CANDIDATE.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.name != "README_CANDIDATE.txt":
                z.write(p, p.relative_to(root).as_posix())
    return zpath


def build_all(site_url: str, out: Path):
    out = Path(out)
    (out / "definitions").mkdir(parents=True, exist_ok=True)
    (out / "docs").mkdir(parents=True, exist_ok=True)
    built = {}
    index = ["# Flow index", "",
             "| Flow | Trigger | When it runs | Actions | Purpose |", "|---|---|---|---:|---|"]
    for name, mk, trig, when in FLOWS:
        fl = mk(site_url)
        built[name] = fl
        d = fl.definition()
        doc = {"name": name, "displayName": fl.display, "description": fl.description, "connectionReferences": connection_refs(fl), "definition": d}
        (out / "definitions" / f"{name}.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
        (out / "docs" / f"{name}.md").write_text(doc_for(fl, trig, when), encoding="utf-8")
        index.append(f"| [{name}]({name}.md) | {trig} | {when} | {count_all(d['actions'])} | {fl.description[:110]} |")
    (out / "docs" / "FLOW_INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    z = solution_candidate(out, built)
    return built, z


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-url", default=DEFAULT_SITE_URL)
    ap.add_argument("--out", default="flows")
    a = ap.parse_args(argv)
    built, z = build_all(a.site_url, Path(a.out))
    print(f"Built {len(built)} flows -> {a.out}/definitions, docs, solution_candidate; wrote {z}")


if __name__ == "__main__":
    main()
