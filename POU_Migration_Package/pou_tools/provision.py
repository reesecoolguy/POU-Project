"""Provision (or verify) the SharePoint lists, columns, indexes, unique constraints and permissions.

* DRY-RUN BY DEFAULT: without --apply only GET requests are sent and the plan is printed.
* SAFE TO RE-RUN: every step first reads current state; existing correct objects are reported as OK.
  Existing objects that differ in a non-destructive way (required / indexed / unique) are updated;
  anything that would need destructive change (type change, removing columns, removing permissions)
  is only reported as DRIFT. Data is never deleted or overwritten. Settings values are never overwritten.
* NO CREDENTIALS are read or stored. Run as a SharePoint site owner / admin.

Usage (see docs/07_Deployment.md for the full walkthrough):
  python -m pou_tools.provision --site-url https://TENANT.sharepoint.com/sites/POU --tenant TENANT.onmicrosoft.com --client-id <APP-ID>
  python -m pou_tools.provision ... --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

from . import masks
from .schema import Schema, load_permissions, load_schema, load_settings_defaults
from .spclient import SpClient, SpError, odata_str


@dataclass
class Action:
    kind: str
    target: str
    status: str = "PLANNED"     # PLANNED | DONE | OK | DRIFT | WARN | ERROR | SKIPPED
    detail: str = ""

    def line(self):
        return f"[{self.status:7}] {self.kind:18} {self.target}" + (f"  -- {self.detail}" if self.detail else "")


@dataclass
class Report:
    actions: list[Action] = field(default_factory=list)
    applied: bool = False

    def add(self, kind, target, status="PLANNED", detail=""):
        a = Action(kind, target, status, detail)
        self.actions.append(a)
        return a

    def count(self, status):
        return sum(1 for a in self.actions if a.status == status)

    @property
    def changes_needed(self):
        return sum(1 for a in self.actions if a.status in ("PLANNED", "DONE"))

    def to_json(self):
        return {"applied": self.applied, "actions": [a.__dict__ for a in self.actions]}


def role_mask(perms: dict, key: str) -> tuple[int, str]:
    rd = next(r for r in perms["roleDefinitions"] if r["key"] == key)
    if rd["builtin"]:
        return masks.BUILTIN_MASKS[rd["name"]], rd["name"]
    base = masks.BUILTIN_MASKS[rd["base"]]
    return base | masks.mask_of(rd["add"]), rd["name"]


def provision(client: SpClient, schema: Schema, perms: dict, apply: bool = False, owners_group: str | None = None,
              prune: bool = False, seed_station: str | None = None, skip_permissions: bool = False,
              skip_seed: bool = False, log=print) -> Report:
    rep = Report(applied=apply)

    def do(kind, target, fn, detail=""):
        a = rep.add(kind, target, "PLANNED", detail)
        if apply:
            try:
                fn()
                a.status = "DONE"
            except SpError as e:
                a.status = "ERROR"
                a.detail = f"{detail} {e}".strip()
        return a

    me = client.current_user()
    log(f"Connected as {me.get('Email') or me.get('Title')} ({'APPLY' if apply else 'DRY-RUN'})")

    existing_lists: dict[str, dict | None] = {}

    # ------------------------------------------------------------------ lists & fields
    for ln, ld in schema.lists.items():
        cur = client.get_list(ln)
        existing_lists[ln] = cur
        if cur is None:
            do("CREATE_LIST", ln, lambda ln=ln, ld=ld: client.create_list(ln, ld.description))
            have: dict[str, dict] = {}
            list_exists_now = apply and all(a.status != "ERROR" for a in rep.actions if a.target == ln)
        else:
            rep.add("LIST", ln, "OK", "exists")
            have = client.list_fields(ln)
            list_exists_now = True
        if cur is None and not (apply and list_exists_now):
            have = {}
        # Title: non-required label
        t = have.get("Title")
        if cur is not None and t is not None and t.get("Required"):
            do("UPDATE_FIELD", f"{ln}.Title", lambda ln=ln: client.update_field(ln, "Title", {"Required": False}), "Title -> not required")
        elif cur is None:
            do("UPDATE_FIELD", f"{ln}.Title", lambda ln=ln: client.update_field(ln, "Title", {"Required": False}), "Title -> not required")
        for f in ld.fields:
            h = have.get(f.name)
            if h is None:
                do("CREATE_FIELD", f"{ln}.{f.name}", lambda ln=ln, f=f: client.create_field_xml(ln, f.schema_xml()),
                   f"{f.type}{' unique' if f.unique else ''}{' indexed' if f.is_indexed else ''}")
                continue
            tas = h.get("TypeAsString", "")
            if tas != f.type and not (f.type == "Currency" and tas == "Currency"):
                rep.add("FIELD", f"{ln}.{f.name}", "DRIFT", f"type is {tas}, schema says {f.type} (not changed automatically)")
                continue
            if f.type == "Choice":
                have_choices = set((h.get("Choices") or {}).get("results", []))
                missing = [c for c in f.choices if c not in have_choices]
                if missing:
                    rep.add("FIELD", f"{ln}.{f.name}", "DRIFT", f"choices missing: {missing} (add in list settings)")
                    continue
            changes = {}
            if bool(h.get("Required")) != f.required:
                changes["Required"] = f.required
            if f.is_indexed and not h.get("Indexed"):
                changes["Indexed"] = True
            if f.unique and not h.get("EnforceUniqueValues"):
                changes["EnforceUniqueValues"] = True
            if changes:
                # set Indexed first, then unique (SharePoint requires an index for uniqueness)
                def upd(ln=ln, f=f, changes=changes):
                    if "Indexed" in changes:
                        client.update_field(ln, f.name, {"Indexed": True})
                    rest = {k: v for k, v in changes.items() if k != "Indexed"}
                    if rest:
                        client.update_field(ln, f.name, rest)
                do("UPDATE_FIELD", f"{ln}.{f.name}", upd, ", ".join(f"{k}={v}" for k, v in changes.items()))
            else:
                rep.add("FIELD", f"{ln}.{f.name}", "OK")
        for bi in ld.builtin_indexes:
            h = have.get(bi)
            if h is not None and h.get("Indexed"):
                rep.add("FIELD", f"{ln}.{bi}", "OK", "built-in column indexed")
            else:
                do("UPDATE_FIELD", f"{ln}.{bi}", lambda ln=ln, bi=bi: client.update_field(ln, bi, {"Indexed": True}), f"index built-in column {bi}")
        # list settings (versioning)
        ls = {**perms["listSettings"].get("_default", {}), **perms["listSettings"].get(ln, {})}
        props = {}
        if ls.get("enableVersioning") is not None and (cur is None or bool(cur.get("EnableVersioning")) != ls["enableVersioning"]):
            props["EnableVersioning"] = ls["enableVersioning"]
            if ls["enableVersioning"] and ls.get("majorVersionLimit"):
                props["MajorVersionLimit"] = ls["majorVersionLimit"]
        if props:
            do("LIST_SETTINGS", ln, lambda ln=ln, props=props: client.update_list(ln, props), json.dumps(props))

    # ------------------------------------------------------------------ permissions
    if not skip_permissions:
        _permissions(client, schema, perms, apply, owners_group, prune, rep, do, existing_lists, log)

    # ------------------------------------------------------------------ seed
    if not skip_seed:
        _seed(client, apply, seed_station, rep, do, existing_lists)

    return rep


def _permissions(client, schema, perms, apply, owners_group, prune, rep, do, existing_lists, log):
    group_ids: dict[str, int] = {}
    for g in perms["groups"]:
        cur = client.find_group(g["title"])
        if cur:
            group_ids[g["key"]] = cur["Id"]
            rep.add("GROUP", g["title"], "OK", "exists")
        else:
            a = do("CREATE_GROUP", g["title"], lambda g=g: group_ids.__setitem__(g["key"], client.create_group(g["title"], g["description"])["Id"]))
    role_ids: dict[str, int] = {}
    for rd in perms["roleDefinitions"]:
        m, name = role_mask(perms, rd["key"])
        cur = client.find_roledef(name)
        if cur:
            role_ids[rd["key"]] = cur["Id"]
            bp = cur.get("BasePermissions") or {}
            if not rd["builtin"] and masks.join(int(bp.get("Low", 0)), int(bp.get("High", 0))) != m:
                rep.add("ROLE", name, "DRIFT", "existing role definition has different permissions (not changed)")
            else:
                rep.add("ROLE", name, "OK", "exists")
        elif rd["builtin"]:
            rep.add("ROLE", name, "WARN", "built-in role not found on this site")
        else:
            sp = masks.split(m)
            do("CREATE_ROLE", name, lambda rd=rd, name=name, sp=sp: role_ids.__setitem__(rd["key"], client.create_roledef(name, sp["Low"], sp["High"], rd.get("description", ""))["Id"]))
    # owners group (break-glass)
    owners = None
    try:
        owners = owners_group and client.find_group(owners_group) or client.request("GET", "web/associatedownergroup")["d"]
    except SpError as e:
        rep.add("OWNERS", owners_group or "associated owners", "WARN", f"could not resolve owners group: {e}")

    for ln, row in perms["matrix"].items():
        cur = existing_lists.get(ln)
        if cur is None and not apply:
            rep.add("PERMISSIONS", ln, "PLANNED", "break inheritance; assign: " + ", ".join(f"{k}={v}" for k, v in row.items() if v))
            continue
        if cur is not None and not cur.get("HasUniqueRoleAssignments"):
            do("BREAK_INHERITANCE", ln, lambda ln=ln: client.break_inheritance(ln))
        elif cur is None:
            do("BREAK_INHERITANCE", ln, lambda ln=ln: client.break_inheritance(ln))
        try:
            have = client.list_assignments(ln) if (cur is not None and cur.get("HasUniqueRoleAssignments")) or apply else []
        except SpError:
            have = []
        have_pairs = set()
        for a in have:
            for b in a["RoleDefinitionBindings"]["results"]:
                have_pairs.add((a["Member"]["Id"], b["Id"]))
        want_pairs = set()
        if owners:
            fc = client.find_roledef("Full Control")
            if fc:
                want_pairs.add((owners["Id"], fc["Id"]))
        for gkey, rkey in row.items():
            if not rkey:
                continue
            gid, rid = group_ids.get(gkey), role_ids.get(rkey)
            if gid is None or rid is None:
                if apply:
                    rep.add("ASSIGN", f"{ln}: {gkey}->{rkey}", "ERROR", "group or role id unresolved")
                else:
                    pass
                continue
            want_pairs.add((gid, rid))
        for gid, rid in sorted(want_pairs):
            if (gid, rid) in have_pairs:
                rep.add("ASSIGN", f"{ln}: principal {gid} role {rid}", "OK")
            else:
                do("ASSIGN", f"{ln}: principal {gid} role {rid}", lambda ln=ln, gid=gid, rid=rid: client.add_assignment(ln, gid, rid))
        extra = have_pairs - want_pairs
        for (pid, rid) in sorted(extra):
            rep.add("EXTRA_ASSIGN", f"{ln}: principal {pid} role {rid}", "DRIFT" if not prune else "WARN",
                    "present but not in permissions matrix" + (" (pruning is not implemented for safety: remove in SharePoint UI)" if prune else ""))


def _seed(client, apply, seed_station, rep, do, existing_lists):
    if existing_lists.get("POUSettings") is None and not apply:
        rep.add("SEED_SETTINGS", "POUSettings", "PLANNED", "all default settings (list not created yet)")
        return
    have = {}
    try:
        have = {r["SettingKey"]: r for r in client.query("POUSettings", select="SettingKey,SettingValue", top=500)}
    except SpError as e:
        rep.add("SEED_SETTINGS", "POUSettings", "ERROR", str(e))
        return
    for s in load_settings_defaults():
        if s["SettingKey"] in have:
            rep.add("SETTING", s["SettingKey"], "OK", "exists (value kept)")
        else:
            do("SEED_SETTING", s["SettingKey"], lambda s=s: client.create_item("POUSettings", s), f"= {s['SettingValue']!r}")
    if seed_station:
        have_st = client.get_by_key("POUStations", "StationID", seed_station) if existing_lists.get("POUStations") or apply else None
        if have_st:
            rep.add("STATION", seed_station, "OK", "exists")
        else:
            do("SEED_STATION", seed_station, lambda: client.create_item("POUStations", {"Title": seed_station, "StationID": seed_station, "StationName": seed_station, "Active": True}))


def main(argv=None):
    from .auth import make_provider
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-url", required=True, help="https://TENANT.sharepoint.com/sites/POU")
    ap.add_argument("--tenant"); ap.add_argument("--client-id")
    ap.add_argument("--auth", choices=["device", "env", "fake"], default="device")
    ap.add_argument("--fake-user", default="admin@test")
    ap.add_argument("--token-cache", help="optional path for MSAL token cache (contains tokens; keep private)")
    ap.add_argument("--apply", action="store_true", help="actually make changes (default is dry-run)")
    ap.add_argument("--owners-group", help="SharePoint group that keeps Full Control (default: the site's Owners group)")
    ap.add_argument("--prune-permissions", action="store_true")
    ap.add_argument("--seed-station", help="create this StationID if missing (e.g. CAB-01)")
    ap.add_argument("--skip-permissions", action="store_true")
    ap.add_argument("--skip-seed", action="store_true")
    ap.add_argument("--report", help="write JSON report here")
    a = ap.parse_args(argv)
    client = SpClient(a.site_url, make_provider(a))
    rep = provision(client, load_schema(), load_permissions(), a.apply, a.owners_group, a.prune_permissions,
                    a.seed_station, a.skip_permissions, a.skip_seed)
    for x in rep.actions:
        if x.status != "OK" or "-v" in sys.argv:
            print(x.line())
    print(f"\n{rep.count('OK')} ok | {rep.count('PLANNED')} planned | {rep.count('DONE')} done | {rep.count('DRIFT')} drift | {rep.count('WARN')} warn | {rep.count('ERROR')} error")
    if not a.apply:
        print("DRY-RUN: nothing was changed. Re-run with --apply to make these changes.")
    if a.report:
        open(a.report, "w", encoding="utf-8").write(json.dumps(rep.to_json(), indent=2))
    return 1 if rep.count("ERROR") else 0


if __name__ == "__main__":
    sys.exit(main())
