"""Static checks on the generated app. These are OUR heuristics - they are not the Power Apps checker and do not evaluate Power Fx.

What they catch: unbalanced syntax, references to controls / lists / columns / flows / settings that do not exist, variables read but never set,
choice columns read without .Value, wrong flow argument counts, non-delegable constructs and unindexed filter columns on the big lists.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .spec import Ctl, Screen, walk

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "lists.json").read_text())
SETTINGS = {s["SettingKey"] for s in json.loads((ROOT / "schema" / "settings_defaults.json").read_text())["settings"]}
LISTS = {l["name"]: l for l in SCHEMA["lists"]}
BIG_LISTS = {"POURequests", "POULedger", "POUStockLocations"}
FLOW_ARGS = {"POU_Session": 5, "POU_ProcessRequest": 1}   # 'POU-Session' after strip()
COLLECTION_LIST = {"colStock": "POUStockLocations", "colSettings": "POUSettings"}
VAR_LIST = {"locSel": "POUStockLocations", "locFresh": "POUStockLocations", "varRow": "POURequests", "varFound": "POURequests", "varTgtRow": "POURequests",
            "varMeEmp": "POUEmployees", "locPickLedger": "POULedger"}
RECORD_VARS = {
    "varReq": {"RequestID", "SessionID", "Station", "RequestType", "StockKey", "ItemID", "LocationCode", "Quantity", "ExpectedVersion", "Reason", "PayloadJson",
               "TargetRequestID", "Decision", "ReversesLedgerKey", "Summary"},
    "varResp": {"status", "code", "message", "ledgerKey", "effect", "newOnHand", "requestId"},
    "varLogin": {"ok", "code", "message", "sessionId", "employeeName", "role", "idleMinutes"},
}
SYSTEM_COLS = {"ID", "Id", "Title", "Created", "Modified", "Created By", "Modified By", "Created_By", "Modified_By"}
KEYWORDS = {"true", "false", "Blank", "If", "And", "Or", "Not", "ThisItem", "Parent", "Self", "FirstError", "Value", "Email", "Message", "Text", "Color", "Fill"}
ENUMS = {"SortOrder", "DisplayMode", "ScreenTransition", "TextFormat", "FontWeight", "Align", "NotificationType", "Seconds", "Milliseconds", "JSONFormat", "Compact",
         "Ascending", "Descending", "None", "Edit", "View", "Disabled", "Bold", "Normal", "Left", "Right", "Center", "Success", "Error", "Warning", "Number"}
NON_DELEGABLE_FUNCS = {"Search", "CountRows", "CountIf", "Sum", "Average", "Max", "Min", "Distinct", "GroupBy", "AddColumns", "ShowColumns", "DropColumns", "Concat", "Last", "LastN"}
COL_WRAPPERS = {"Lower", "Upper", "Trim", "Left", "Right", "Mid", "Len", "Text", "Value", "Substitute", "Replace", "Coalesce", "Year", "Month", "Day", "DateDiff", "DateAdd"}


class Problem:
    def __init__(self, level, where, msg):
        self.level, self.where, self.msg = level, where, msg

    def __str__(self):
        return f"{self.level}: {self.where}: {self.msg}"


# ---------------------------------------------------------------------------------------------------------------------
def strip(fx: str) -> str:
    """Remove strings (keeping empty quotes) and comments; keep 'single quoted identifiers' as bare tokens with underscores for spaces."""
    out, i, n = [], 0, len(fx)
    while i < n:
        c = fx[i]
        if c == '"':
            j = i + 1
            while j < n:
                if fx[j] == '"':
                    if j + 1 < n and fx[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            else:
                raise ValueError("unterminated string")
            out.append('""')
            i = j + 1
        elif c == "'":
            j = fx.index("'", i + 1)
            out.append(fx[i + 1:j].replace(" ", "_").replace("-", "_"))
            i = j + 1
        elif fx.startswith("//", i):
            while i < n and fx[i] != "\n":
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def balanced(fx: str) -> str | None:
    stack, pairs = [], {")": "(", "]": "[", "}": "{"}
    try:
        s = strip(fx)
    except ValueError as e:
        return str(e)
    for c in s:
        if c in "([{":
            stack.append(c)
        elif c in ")]}":
            if not stack or stack.pop() != pairs[c]:
                return f"unbalanced '{c}'"
    return None if not stack else f"unclosed '{stack[-1]}'"


def split_args(s: str) -> list[str]:
    args, depth, cur = [], 0, []
    for c in s:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            args.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    args.append("".join(cur))
    return [a.strip() for a in args]


def calls(s: str, fname: str):
    """Yield the argument lists of every call of fname( ... ) in stripped text s."""
    for m in re.finditer(r"(?<![\w.])" + re.escape(fname) + r"\(", s):
        i, depth = m.end(), 1
        while i < len(s) and depth:
            depth += {"(": 1, ")": -1}.get(s[i], 0)
            i += 1
        yield split_args(s[m.end():i - 1])


def idents(s: str):
    for m in re.finditer(r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)(?!\w)(?!\s*\()", s):
        yield m.group(1)


# ---------------------------------------------------------------------------------------------------------------------
def formulas(screens: list[Screen], app_props: dict):
    """Yield (screen_name or '', where, property, text)."""
    for k, v in app_props.items():
        yield "", f"App.{k}", k, v if isinstance(v, str) else str(v)
    for s in screens:
        for k, v in s.props.items():
            yield s.name, f"{s.name}.{k}", k, str(v)
        for c in walk(s.children):
            for k, v in c.props.items():
                yield s.name, f"{s.name}.{c.name}.{k}", k, str(v)


def lint(screens: list[Screen], app_props: dict) -> list[Problem]:
    P: list[Problem] = []
    err = lambda w, m: P.append(Problem("ERROR", w, m))
    warn = lambda w, m: P.append(Problem("WARN", w, m))

    # ---- names
    names: dict[str, str] = {}
    snames = {s.name for s in screens}
    for s in screens:
        for c in walk(s.children):
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", c.name):
                err(f"{s.name}.{c.name}", "control name must be alphanumeric")
            if c.name in names or c.name in snames:
                err(f"{s.name}.{c.name}", f"duplicate control name (also in {names.get(c.name, 'screens')})")
            names[c.name] = s.name
    ctrl_screen = names

    # ---- global facts gathered from all formulas
    all_fx = list(formulas(screens, app_props))
    stripped = {}
    for scr, where, prop, text in all_fx:
        b = balanced(text)
        if b:
            err(where, b)
            continue
        stripped[(scr, where, prop)] = strip(text)
    set_vars = set()
    colls = set()
    ctx_by_screen: dict[str, set] = {}
    with_names = set()
    for (scr, where, prop), s in stripped.items():
        set_vars |= set(re.findall(r"\bSet\(\s*(\w+)\s*,", s))
        colls |= set(re.findall(r"\b(?:ClearCollect|Collect|LoadData)\(\s*(\w+)\s*,", s))
        for m in re.finditer(r"UpdateContext\(\s*\{", s):
            depth, i = 1, m.end()
            while i < len(s) and depth:
                depth += {"{": 1, "}": -1}.get(s[i], 0)
                i += 1
            body = s[m.end():i - 1]
            ctx_by_screen.setdefault(scr, set()).update(re.findall(r"(?:^|,)\s*(\w+)\s*:", body))
        for args in calls(s, "With"):
            with_names |= set(re.findall(r"(?:^|[{,])\s*(\w+)\s*:", args[0]))
    ctx_all = set().union(*ctx_by_screen.values()) if ctx_by_screen else set()

    # ---- per-formula checks
    for (scr, where, prop), s in stripped.items():
        # control references
        for m in re.finditer(r"(?<![\w.])((?:txt|btn|lbl|gal|tmr|rec|lblHdr|nav)[A-Z]\w*)\b", s):
            n = m.group(1)
            if n not in ctrl_screen:
                err(where, f"unknown control '{n}'")
            elif scr and ctrl_screen[n] != scr:
                err(where, f"control '{n}' belongs to {ctrl_screen[n]} (cross-screen reference)")
        for fn in ("Select", "Reset", "SetFocus"):
            for args in calls(s, fn):
                if args[0] not in ctrl_screen:
                    err(where, f"{fn}({args[0]}) names no control")
        for args in calls(s, "Navigate"):
            if args[0] not in snames:
                err(where, f"Navigate to unknown screen '{args[0]}'")
        # lists
        for ln in set(re.findall(r"\bPOU[A-Za-z]+\b", s)):
            if ln not in LISTS:
                err(where, f"unknown list '{ln}'")
        # flows
        for fl, n in FLOW_ARGS.items():
            for m in re.finditer(re.escape(fl) + r"\.Run\(", s):
                i, depth = m.end(), 1
                while i < len(s) and depth:
                    depth += {"(": 1, ")": -1}.get(s[i], 0)
                    i += 1
                got = len(split_args(s[m.end():i - 1]))
                if got != n:
                    err(where, f"{fl}.Run has {got} arguments, the flow trigger has {n}")
        if re.search(r"POU_[\w]*\.Run", s):
            for fl in set(re.findall(r"(POU_[\w]*)\.Run", s)):
                if fl not in FLOW_ARGS:
                    err(where, f"unknown flow {fl}")
        # settings
        for m in re.finditer(r'SettingKey\s*=\s*""', s):
            pass
        for key in set(re.findall(r'SettingKey = "([A-Za-z]+)"', stripped_with_strings(all_fx, where))):
            if key not in SETTINGS:
                err(where, f"setting '{key}' is not in settings_defaults.json")
        # variables
        for v in set(re.findall(r"(?<![\w.])(var[A-Z]\w*)\b", s)):
            if v not in set_vars:
                err(where, f"global variable {v} is read but never Set")
        for v in set(re.findall(r"(?<![\w.])(loc[A-Z]\w*)\b", s)):
            if v not in ctx_by_screen.get(scr, set()) and v not in with_names:
                err(where, f"context variable {v} is read on {scr or 'App'} but never set there with UpdateContext")
        for c in set(re.findall(r"(?<![\w.])(col[A-Z]\w*)\b", s)):
            if c not in colls:
                err(where, f"collection {c} is never created")
        # record fields
        for var, allowed in RECORD_VARS.items():
            for f in re.findall(r"(?<![\w.])" + var + r"\.(\w+)", s):
                if f not in allowed:
                    err(where, f"{var}.{f} is not a field of {var}")
        for var, ln in VAR_LIST.items():
            fields = {f["name"]: f for f in LISTS[ln]["fields"]}
            for m in re.finditer(r"(?<![\w.])" + var + r"\.(\w+)(\.\w+)?", s):
                f, sub = m.group(1), m.group(2)
                if f not in fields and f not in SYSTEM_COLS:
                    err(where, f"{var}.{f} is not a column of {ln}")
                elif f in fields and fields[f]["type"] == "Choice" and sub != ".Value":
                    err(where, f"{var}.{f} is a Choice column: use .Value")
        # delegation / indexed columns
        for fn in ("Filter", "LookUp", "SortByColumns", "Sort"):
            for args in calls(s, fn):
                src = args[0]
                ln = src if src in LISTS else COLLECTION_LIST.get(src)
                if src in LISTS:
                    pred = ",".join(args[1:]) if fn in ("Filter", "LookUp") else ""
                    cols = {f["name"]: f for f in LISTS[src]["fields"]}
                    for bad in NON_DELEGABLE_FUNCS:
                        if re.search(r"(?<![\w.])" + bad + r"\(", pred):
                            err(where, f"{fn}({src}, ...) uses {bad}() in its condition: not delegable")
                    if re.search(r"\bin\b", pred):
                        err(where, f"{fn}({src}, ...) uses 'in': not delegable")
                    for wrap in COL_WRAPPERS:
                        for wargs in calls(pred, wrap):
                            if any(a in cols for a in idents(",".join(wargs))):
                                err(where, f"{fn}({src}, ...) applies {wrap}() to a column: not delegable")
                    for m in re.finditer(r"(?<![\w.])(\w+)(?:\.Value)?\s*(?:=|<>|<=|>=|<|>)\s*(?!=)", pred):
                        col = m.group(1)
                        if col in cols and src in BIG_LISTS and not cols[col].get("indexed") and col not in ("ID",):
                            err(where, f"{fn}({src}) filters on non-indexed column {col}: unsafe beyond 5,000 rows")
                    for col in set(idents(pred)):
                        if col not in cols and col not in SYSTEM_COLS and col not in set_vars | with_names | ctx_all | colls | KEYWORDS | ENUMS and not col.startswith(("var", "loc", "col", "txt", "btn", "lbl", "gal")):
                            err(where, f"{fn}({src}, ...): '{col}' is not a column of {src} nor a known variable")
                    if fn == "SortByColumns":
                        for a in args[1:]:
                            pass
                if fn == "SortByColumns" and src.startswith(("Filter", "Sort", "First")):
                    pass
        for fn in NON_DELEGABLE_FUNCS:
            for args in calls(s, fn):
                if args and args[0] in LISTS and LISTS[args[0]]["name"] in BIG_LISTS:
                    err(where, f"{fn}({args[0]}...) over a large list is not delegable")
        # row-limit safety: unbounded reads of big lists
        for ln in BIG_LISTS:
            for m in re.finditer(r"(?<![\w.(])" + ln + r"\b(?!\s*,\s*Defaults)", s):
                ctx = s[max(0, m.start() - 24):m.start()]
                if re.search(r"(Refresh|Defaults|Patch|LookUp|Filter|SortByColumns|SortByColumns|Collect|ClearCollect)\(\s*$", ctx) or ctx.rstrip().endswith("ThisItem"):
                    continue
                if prop == "Items":
                    warn(where, f"Items reads {ln} without Filter/FirstN: only the app row limit is returned")

    # ---- ThisItem columns inside galleries
    for s_ in screens:
        for c in walk(s_.children):
            if c.type != "gallery.galleryVertical":
                continue
            items = strip(str(c.props.get("Items", "")))
            ln = next((x for x in re.findall(r"\bPOU[A-Za-z]+\b", items)), None) or next((COLLECTION_LIST[k] for k in COLLECTION_LIST if k in items), None)
            if not ln:
                continue
            fields = {f["name"]: f for f in LISTS[ln]["fields"]}
            for ch in walk(c.children):
                for k, v in ch.props.items():
                    for m in re.finditer(r"ThisItem\.(\w+)(\.\w+)?", strip(str(v))):
                        f, sub = m.group(1), m.group(2)
                        if f not in fields and f not in SYSTEM_COLS:
                            err(f"{s_.name}.{ch.name}.{k}", f"ThisItem.{f} is not a column of {ln}")
                        elif f in fields and fields[f]["type"] == "Choice" and sub != ".Value":
                            err(f"{s_.name}.{ch.name}.{k}", f"ThisItem.{f} is a Choice column: use .Value")

    # ---- required properties
    need = {"button": ["OnSelect", "Text"], "timer": ["OnTimerEnd", "Duration"], "gallery.galleryVertical": ["Items"], "label": ["Text"], "text": []}
    for s_ in screens:
        for c in walk(s_.children):
            for k in need.get(c.type, []):
                if k not in c.props:
                    err(f"{s_.name}.{c.name}", f"missing property {k}")
        n = len(list(walk(s_.children)))
        if n > 400:
            warn(s_.name, f"{n} controls (keep screens under ~300 for load time)")
    longest = max(((len(t), w) for _, w, _, t in all_fx), default=(0, ""))
    if longest[0] > 12000:
        warn(longest[1], f"formula is {longest[0]} characters")
    return P


def stripped_with_strings(all_fx, where):
    for _, w, _, t in all_fx:
        if w == where:
            return t
    return ""


def report(problems: list[Problem]) -> str:
    return "\n".join(str(p) for p in problems) or "no findings"
