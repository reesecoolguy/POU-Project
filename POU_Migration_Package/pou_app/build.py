"""Generate app/src/*.fx.yaml, app/docs/CONTROL_REFERENCE.md and app/docs/DELEGATION.md from the app model, after linting it."""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from . import lint, screens
from .spec import app_yaml, screen_markdown, screen_yaml, walk

ROOT = Path(__file__).resolve().parent.parent


def build_id(ss, ap) -> str:
    h = hashlib.sha256()
    for s in ss:
        h.update(screen_yaml(s).encode())
    h.update(str(sorted(k for k in ap if k != "OnStart")).encode())
    return "POU-APP-" + h.hexdigest()[:8]


def keep_strings(fx: str):
    """Like lint.strip but string literals are swapped for numbered tokens so the original text can be shown."""
    strs = []

    def sub(m):
        strs.append(m.group(0))
        return f'\u00a7{len(strs) - 1}\u00a7'
    t = re.sub(r'"(?:[^"]|"")*"', sub, fx)
    return lint.strip(t), strs


def restore(text: str, strs):
    return re.sub(r'\u00a7(\d+)\u00a7', lambda m: strs[int(m.group(1))], text)


def delegation_table(ss, ap) -> str:
    rows, seen = [], set()
    for scr, where, prop, text in lint.formulas(ss, ap):
        s, strs = keep_strings(text)
        for fn in ("Filter", "LookUp", "SortByColumns", "FirstN", "ClearCollect", "Patch", "Refresh"):
            for args in lint.calls(s, fn):
                src = args[0]
                if src in lint.LISTS and fn in ("Filter", "LookUp", "SortByColumns"):
                    pred = restore(" , ".join(args[1:]), strs)
                    key = (src, fn, pred)
                    if key in seen:
                        continue
                    seen.add(key)
                    big = src in lint.BIG_LISTS
                    idx = [c for c in re.findall(r"(?<![\w.])(\w+)(?:\.Value)?\s*(?:=|<>|<=|>=|<|>)", pred) if c in {f['name'] for f in lint.LISTS[src]['fields']}]
                    unindexed = [c for c in idx if not next(f for f in lint.LISTS[src]["fields"] if f["name"] == c).get("indexed")]
                    verdict = "Delegable (Microsoft documents =, <>, <, >, And/Or/Not, StartsWith, Sort/SortByColumns on SharePoint text/number/boolean/choice-.Value columns)"
                    if fn == "SortByColumns":
                        verdict = "Delegable when the column is a plain column or ID (verify the blue-underline indicator in Studio)"
                    if unindexed:
                        verdict += f". WARNING unindexed: {unindexed}"
                    rows.append((f"{where}", f"{fn}({src}, {pred[:110]})", "yes" if big else "small list", verdict))
    md = ["# Delegation matrix (generated)", "",
          "Every query against a SharePoint list that the app makes, with its delegation expectation. **This table is generated from the app source and our reading of the Microsoft delegation rules; "
          "it was NOT produced by the Power Apps checker.** Open each screen in Studio and confirm there is no blue delegation warning on the formulas below (test T-APP-05).", "",
          "Two different limits are involved and must not be confused:", "",
          "* **App data row limit** (default 500, maximum 2,000): how many rows a *delegated* query hands back to the app. Every gallery here is `FirstN(..., N)`-bounded and the Low-stock screen prints a warning if the result reaches the limit.",
          "* **SharePoint list view threshold** (5,000): a query that needs to *examine* more than 5,000 rows fails unless it can use an index. Every column filtered on the three large lists (Requests, Ledger, Stock) is indexed (checked by the linter); "
          "`ID`-ordered reads need no index.", "",
          "Things the app deliberately does **not** do against SharePoint: `CountRows`/`Sum`/`Search`/`in`/`Len(column)`/`Lower(column)`/`Distinct`/`GroupBy`. Totals, usage (30/90 days) and reconciliation are computed by the flows (which page by ID) and delivered by email/report.", "",
          "| Where | Query | Size | Expectation |", "|---|---|---|---|"]
    md += [f"| `{w}` | `{q}` | {z} | {v} |" for w, q, z, v in rows]
    md += ["", "Client-side (collection) operations such as `CountRows(colStock)` run on at most the rows already downloaded and are not a delegation concern."]
    return "\n".join(md) + "\n"


def main(argv=None):
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--out", default=str(ROOT / "app"))
    a = ap_.parse_args(argv)
    ss, props = screens.all_screens(), screens.app_props()
    problems = lint.lint(ss, props)
    errors = [p for p in problems if p.level == "ERROR"]
    if errors:
        print(lint.report(problems), file=sys.stderr)
        return 1
    bid = build_id(ss, props)
    props["OnStart"] = props["OnStart"].replace("{BUILD}", bid)
    out = Path(a.out)
    (out / "src").mkdir(parents=True, exist_ok=True)
    (out / "docs").mkdir(parents=True, exist_ok=True)
    (out / "src" / "App.fx.yaml").write_text(app_yaml(props))
    for s in ss:
        (out / "src" / f"{s.name}.fx.yaml").write_text(screen_yaml(s))
    ref = ["# Control reference (generated)", "",
           f"Build id `{bid}`. Every control of every screen with its exact name, type and Power Fx. If pasting the YAML into Studio is not accepted by your Studio version, build the app by hand from this file: "
           "create each control with the listed name and type and paste each formula into the property named.", "",
           "Conventions: `varX` global (Set) | `locX` screen context variable | `colX` collection. All geometry values are for a 1366x768 Windows PC screen (App > Settings > Display: Landscape, 1366x768, "
           "scale to fit OFF, lock aspect ratio ON).", "", "## App", "", "### App.OnStart", "", "```powerfx", props["OnStart"], "```", "", "### App.StartScreen", "", "```powerfx", props["StartScreen"].lstrip("="), "```", "",
           "### App.OnError", "", "```powerfx", props["OnError"], "```", ""]
    ref += [screen_markdown(s) for s in ss]
    (out / "docs" / "CONTROL_REFERENCE.md").write_text("\n".join(ref))
    (out / "docs" / "DELEGATION.md").write_text(delegation_table(ss, props))
    n_ctl = sum(len(list(walk(s.children))) for s in ss)
    print(f"built {len(ss)} screens, {n_ctl} controls, build id {bid}; lint warnings: {sum(p.level == 'WARN' for p in problems)}")
    for p in problems:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
