"""The committed flow deliverables are exactly what the generators produce, and the solution-candidate tree is internally consistent."""
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from pou_flows import build
from pou_flows.common import DEFAULT_SITE_URL

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("flows")
    build.build_all(DEFAULT_SITE_URL, out)
    return out


def test_committed_definitions_are_not_stale(built):
    for p in sorted((built / "definitions").glob("*.json")):
        committed = ROOT / "flows" / "definitions" / p.name
        assert committed.exists(), p.name
        assert json.loads(committed.read_text()) == json.loads(p.read_text()), f"{p.name} is stale: run scripts\\7_rebuild_package.cmd"
    for p in sorted((built / "docs").glob("*.md")):
        assert (ROOT / "flows" / "docs" / p.name).read_text() == p.read_text(), f"flows/docs/{p.name} is stale"


def test_solution_candidate_is_internally_consistent(built):
    sol = built / "solution_candidate"
    ns = {}
    manifest = ET.parse(sol / "solution.xml").getroot()
    ids = {rc.get("id").strip("{}").lower() for rc in manifest.iter("RootComponent")}
    custom = ET.parse(sol / "customizations.xml").getroot()
    wf = {w.get("WorkflowId").strip("{}").lower(): w for w in custom.iter("Workflow")}
    assert ids == set(wf) and len(ids) == 8
    for gid, w in wf.items():
        path = sol / w.find("JsonFileName").text.lstrip("/")
        assert path.exists() and gid.upper() in path.name
        d = json.loads(path.read_text())
        assert set(d) == {"properties", "schemaVersion"}
        props = d["properties"]
        assert props["definition"]["triggers"] and props["definition"]["actions"]
        for ref in props["connectionReferences"].values():
            assert ref["connection"]["connectionReferenceLogicalName"]
    assert (sol / "[Content_Types].xml").exists()
    with zipfile.ZipFile(built / "POU_Flows_solution_CANDIDATE.zip") as z:
        names = z.namelist()
        assert "solution.xml" in names and "customizations.xml" in names and "[Content_Types].xml" in names
        assert sum(n.startswith("Workflows/") for n in names) == 8
    assert "NOT VALIDATED" in (sol / "README_CANDIDATE.txt").read_text()


def test_placeholder_guard_present_in_every_flow(built):
    for p in (built / "definitions").glob("*.json"):
        text = p.read_text()
        assert "CHANGE-ME.sharepoint.com" in text and "Guard_site_url_configured" in text, p.name


def test_app_triggered_flow_names_match_the_app(built):
    from pou_app.lint import FLOW_ARGS
    from pou_flows import process, session
    for fl, key in ((session.build(), "POU_Session"), (process.build(), "POU_ProcessRequest")):
        assert fl.name.replace("-", "_") == key
        n_inputs = len(fl.trigger["manual"]["inputs"]["schema"]["properties"])
        assert n_inputs == FLOW_ARGS[key], (fl.name, n_inputs)
