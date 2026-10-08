"""In-memory model of the SharePoint Online REST subset used by this package.

PURPOSE: local testing of provisioning, import, and the Power Automate flow definitions (executed by
flowlab) without a tenant. It models SharePoint's *documented* behaviour:

  * list/field creation from SchemaXml, indexes, EnforceUniqueValues (case-insensitive)
  * item CRUD, defaults, required/min/max/maxlength/choice validation
  * ETag + If-Match conditional updates (412 on mismatch)
  * $filter/$select/$expand(Author)/$orderby/$top paging with __next
  * the 5,000 item list-view threshold (query must be resolvable through an index)
  * list permissions: role definitions (base-permission masks), SharePoint groups, unique list permissions
  * Author/Editor/Created/Modified stamped by the SERVER from the authenticated caller
  * fault-injection hooks (throttle, timeout-after-commit "lost response", crash points)

IT DOES NOT PROVE the real service behaves identically. Every guarantee the protocol relies on is listed in
docs/06_Consistency_Limits.md and exercised against a real tenant by tests/tenant/tenant_probe.py.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse, quote

from . import masks

THRESHOLD = 5000
DEFAULT_PAGE = 100


class SPHttp(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------------------
# $filter parser
# ---------------------------------------------------------------------------------------------
_TOKEN = re.compile(r"""\s*(
    datetime'[^']*' |
    '(?:[^']|'')*' |
    \( | \) | , |
    [A-Za-z_][A-Za-z0-9_/]* |
    -?\d+(?:\.\d+)?
)""", re.X)


def _tokenize(s: str):
    pos, out = 0, []
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            if s[pos:].strip() == "":
                break
            raise SPHttp(400, "-1, Microsoft.SharePoint.Client.InvalidClientQueryException", f"bad $filter near {s[pos:pos+20]!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def eat(self, x=None):
        v = self.peek()
        if x is not None and (v is None or v.lower() != x):
            raise SPHttp(400, "-1", f"expected {x} got {v}")
        self.i += 1
        return v

    def parse(self):
        node = self.or_()
        if self.peek() is not None:
            raise SPHttp(400, "-1", f"trailing tokens {self.t[self.i:]}")
        return node

    def or_(self):
        n = self.and_()
        while self.peek() and self.peek().lower() == "or":
            self.eat()
            n = ("or", n, self.and_())
        return n

    def and_(self):
        n = self.not_()
        while self.peek() and self.peek().lower() == "and":
            self.eat()
            n = ("and", n, self.not_())
        return n

    def not_(self):
        if self.peek() and self.peek().lower() == "not":
            self.eat()
            return ("not", self.not_())
        return self.atom()

    def atom(self):
        p = self.peek()
        if p == "(":
            self.eat()
            n = self.or_()
            self.eat(")")
            return n
        if p and p.lower() in ("startswith", "substringof"):
            fn = self.eat().lower()
            self.eat("(")
            a = self.value()
            self.eat(",")
            b = self.value()
            self.eat(")")
            return ("fn", fn, a, b)
        left = self.value()
        op = self.eat()
        if op is None or op.lower() not in ("eq", "ne", "gt", "ge", "lt", "le"):
            raise SPHttp(400, "-1", f"bad operator {op}")
        right = self.value()
        return ("cmp", op.lower(), left, right)

    def value(self):
        t = self.eat()
        if t.startswith("datetime'"):
            return ("lit", _parse_dt(t[9:-1]))
        if t.startswith("'"):
            return ("lit", t[1:-1].replace("''", "'"))
        if re.fullmatch(r"-?\d+(?:\.\d+)?", t):
            return ("lit", float(t) if "." in t else int(t))
        if t.lower() in ("true", "false"):
            return ("lit", t.lower() == "true")
        if t.lower() == "null":
            return ("lit", None)
        return ("field", t)


def _parse_dt(s: str):
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def _coerce_pair(a, b):
    if isinstance(a, datetime) or isinstance(b, datetime):
        def cv(x):
            if isinstance(x, datetime):
                return x
            if isinstance(x, str):
                try:
                    return _parse_dt(x)
                except Exception:
                    return None
            return None
        return cv(a), cv(b)
    if isinstance(a, bool) or isinstance(b, bool):
        def bv(x):
            if isinstance(x, bool) or x is None:
                return x
            if x in (1, "1", "true", "True"):
                return True
            if x in (0, "0", "false", "False"):
                return False
            return x
        return bv(a), bv(b)
    if isinstance(a, str) and isinstance(b, str):
        return a.lower(), b.lower()
    return a, b


def _eval(node, item_fields, ftypes):
    k = node[0]
    if k == "or":
        return _eval(node[1], item_fields, ftypes) or _eval(node[2], item_fields, ftypes)
    if k == "and":
        return _eval(node[1], item_fields, ftypes) and _eval(node[2], item_fields, ftypes)
    if k == "not":
        return not _eval(node[1], item_fields, ftypes)

    def val(n):
        if n[0] == "lit":
            return n[1]
        name = n[1]
        v = item_fields.get(name)
        t = ftypes.get(name)
        if t == "Boolean" and v is not None:
            return bool(v)
        return v

    if k == "fn":
        _, fn, a, b = node
        av, bv = val(a), val(b)
        if av is None or bv is None:
            return False
        if fn == "startswith":
            return str(av).lower().startswith(str(bv).lower())
        return str(av).lower() in str(bv).lower()  # substringof('x', Field)
    _, op, l, r = node
    lv, rv = val(l), val(r)
    # datetime field vs datetime literal
    if isinstance(rv, datetime) or isinstance(lv, datetime):
        lv, rv = _coerce_pair(lv, rv)
    else:
        lv, rv = _coerce_pair(lv, rv)
    if op == "eq":
        return lv == rv
    if op == "ne":
        return lv != rv
    if lv is None or rv is None:
        return False
    try:
        return {"gt": lv > rv, "ge": lv >= rv, "lt": lv < rv, "le": lv <= rv}[op]
    except TypeError:
        return False


def _conjuncts(node):
    if node[0] == "and":
        return _conjuncts(node[1]) + _conjuncts(node[2])
    return [node]


# ---------------------------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------------------------
class FField:
    def __init__(self, name, type_, display=None, required=False, indexed=False, unique=False,
                 max_length=255, min_=None, max_=None, choices=None, default=None, builtin=False, decimals=None):
        self.name, self.type, self.display = name, type_, display or name
        self.required, self.indexed, self.unique = required, indexed, unique
        self.max_length, self.min, self.max = max_length, min_, max_
        self.choices, self.default, self.builtin = choices or [], default, builtin
        self.decimals = decimals

    def to_json(self):
        return {"InternalName": self.name, "StaticName": self.name, "Title": self.display,
                "TypeAsString": self.type, "Required": self.required, "Indexed": self.indexed,
                "EnforceUniqueValues": self.unique, "MaxLength": self.max_length,
                "Choices": {"results": list(self.choices)} if self.type == "Choice" else None}


class FList:
    def __init__(self, title, lid):
        self.title, self.id = title, lid
        self.description = ""
        self.fields: dict[str, FField] = {}
        self.items: dict[int, dict] = {}
        self.next_id = 1
        self.unique_perms = False
        self.assignments: list[tuple[str, int]] = []  # (principal key, roledef id)
        self.props = {"EnableVersioning": False, "MajorVersionLimit": 0, "ReadSecurity": 1, "WriteSecurity": 1}
        for n, t, req in (("Title", "Text", True), ("Created", "DateTime", False), ("Modified", "DateTime", False)):
            self.fields[n] = FField(n, t, required=req, builtin=True)
        self.fields["Title"].required = True

    @property
    def entity_type(self):
        return "SP.Data." + self.title.replace("_", "_x005f_") + "ListItem"


class FakeSharePoint:
    def __init__(self, site_path="/sites/POU", threshold=THRESHOLD):
        self.site_path = site_path.rstrip("/")
        self.threshold = threshold
        self.lock = threading.RLock()
        self.lists: dict[str, FList] = {}
        self.site_admins: set[str] = set()
        self.groups: dict[str, dict] = {}     # title -> {"Id", "Title", "members": set(upn)}
        self.users: dict[str, dict] = {}      # upn lower -> principal
        self.roledefs: dict[str, dict] = {}   # name -> {"Id","Name","mask","builtin"}
        self.web_assignments: list[tuple[str, int]] = []
        self._pid = 10
        self.request_log: list[dict] = []
        self.fault_before = None   # callable(ctx) -> (status, body) | None
        self.fault_after = None    # callable(ctx, resp) -> resp
        self.request_count = 0
        for name, m in masks.BUILTIN_MASKS.items():
            self._add_roledef(name, m, builtin=True)
        self._ensure_group("Site Owners")
        self.owners_group = "Site Owners"
        self.web_assignments.append((self._gkey("Site Owners"), self.roledefs["Full Control"]["Id"]))

    # ----- principals ------------------------------------------------------------------------
    def _next_pid(self):
        self._pid += 1
        return self._pid

    def _gkey(self, title):
        return "g:" + title.lower()

    def _ensure_group(self, title, description=""):
        if title not in self.groups:
            self.groups[title] = {"Id": self._next_pid(), "Title": title, "Description": description, "members": set()}
        return self.groups[title]

    def _add_roledef(self, name, mask, builtin=False, description=""):
        if name in self.roledefs:
            raise SPHttp(400, "-2130575306", f"role definition {name} exists")
        self.roledefs[name] = {"Id": self._next_pid(), "Name": name, "mask": mask, "builtin": builtin, "Description": description}
        return self.roledefs[name]

    def user(self, upn):
        k = upn.lower()
        if k not in self.users:
            self.users[k] = {"Id": self._next_pid(), "EMail": upn, "Title": upn.split("@")[0], "LoginName": f"i:0#.f|membership|{upn}"}
        return self.users[k]

    def add_member(self, group_title, upn):
        with self.lock:
            self.user(upn)
            self._ensure_group(group_title)["members"].add(upn.lower())

    def make_site_admin(self, upn):
        self.user(upn)
        self.site_admins.add(upn.lower())

    def _principal_by_id(self, pid):
        for g in self.groups.values():
            if g["Id"] == pid:
                return self._gkey(g["Title"])
        for u in self.users.values():
            if u["Id"] == pid:
                return "u:" + u["EMail"].lower()
        raise SPHttp(404, "-2146232832", f"principal {pid} not found")

    def _principal_json(self, key):
        if key.startswith("g:"):
            for g in self.groups.values():
                if self._gkey(g["Title"]) == key:
                    return {"Id": g["Id"], "Title": g["Title"], "PrincipalType": 8}
        for u in self.users.values():
            if "u:" + u["EMail"].lower() == key:
                return {"Id": u["Id"], "Title": u["Title"], "PrincipalType": 1}
        return {"Id": 0, "Title": key}

    def effective_mask(self, upn, flist: FList | None) -> int:
        k = upn.lower()
        if k in self.site_admins:
            return masks.FLAGS["FullMask"]
        assigns = flist.assignments if (flist is not None and flist.unique_perms) else self.web_assignments
        m = 0
        for pkey, rid in assigns:
            hit = False
            if pkey.startswith("g:"):
                for g in self.groups.values():
                    if self._gkey(g["Title"]) == pkey and k in g["members"]:
                        hit = True
            elif pkey == "u:" + k:
                hit = True
            if hit:
                for rd in self.roledefs.values():
                    if rd["Id"] == rid:
                        m |= rd["mask"]
        return m

    def _need(self, upn, flist, flag):
        if not (self.effective_mask(upn, flist) & masks.FLAGS[flag]):
            raise SPHttp(403, "-2147024891, System.UnauthorizedAccessException", "Access denied. You do not have permission to perform this action or access this resource.")

    # ----- request entry -------------------------------------------------------------------
    def handle(self, method, url, headers=None, body=None):
        """Returns (status, headers, json-able body or None)."""
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        parsed = urlparse(url)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs = {k: v[0] for k, v in qs.items()}
        ctx = {"method": method.upper(), "path": path, "qs": qs, "headers": headers, "body": body}
        override = headers.get("x-http-method")
        if override:
            ctx["method"] = override.upper()
        auth = headers.get("authorization", "")
        m = re.match(r"Bearer fake:(.+)", auth)
        caller = m.group(1) if m else None
        ctx["caller"] = caller
        with self.lock:
            self.request_count += 1
        if self.fault_before:
            r = self.fault_before(ctx)
            if r is not None:
                return r[0], {}, r[1]
        try:
            if caller is None:
                raise SPHttp(401, "-2147024891", "Unauthorized")
            with self.lock:
                self.user(caller)
                resp = self._route(ctx, caller)
        except SPHttp as e:
            resp = (e.status, {}, {"error": {"code": e.code, "message": {"lang": "en-US", "value": e.message}}})
        self.request_log.append({"method": ctx["method"], "path": path, "status": resp[0], "caller": caller})
        if self.fault_after:
            resp = self.fault_after(ctx, resp)
        return resp

    # ----- routing -------------------------------------------------------------------------
    def _route(self, ctx, caller):
        path, method = ctx["path"], ctx["method"]
        if not path.startswith(self.site_path + "/_api/"):
            raise SPHttp(404, "-1", "unknown path " + path)
        rel = path[len(self.site_path) + len("/_api/"):]
        body = ctx["body"]
        data = json.loads(body) if body else {}

        if rel == "web/currentuser":
            u = self.user(caller)
            return 200, {}, {"d": {"Id": u["Id"], "Email": u["EMail"], "Title": u["Title"], "LoginName": u["LoginName"]}}
        if rel == "web/associatedownergroup":
            g = self.groups[self.owners_group]
            return 200, {}, {"d": {"Id": g["Id"], "Title": g["Title"]}}

        # ---- site groups
        if rel == "web/sitegroups":
            if method == "GET":
                res = [{"Id": g["Id"], "Title": g["Title"], "Description": g["Description"]} for g in self.groups.values()]
                f = ctx["qs"].get("$filter")
                if f:
                    mm = re.fullmatch(r"Title eq '(.*)'", f)
                    if mm:
                        res = [g for g in res if g["Title"].lower() == mm.group(1).replace("''", "'").lower()]
                return 200, {}, {"d": {"results": res}}
            if method == "POST":
                self._need_web_manage(caller)
                t = data["Title"]
                if t in self.groups:
                    raise SPHttp(400, "-2130575306, Microsoft.SharePoint.SPException", "A group with this name already exists.")
                g = self._ensure_group(t, data.get("Description", ""))
                return 201, {}, {"d": {"Id": g["Id"], "Title": g["Title"]}}
        mm = re.fullmatch(r"web/sitegroups\((\d+)\)/users", rel)
        if mm:
            gid = int(mm.group(1))
            g = next((g for g in self.groups.values() if g["Id"] == gid), None)
            if not g:
                raise SPHttp(404, "-2146232832", "group not found")
            if method == "GET":
                return 200, {}, {"d": {"results": [{"Email": m_, "Title": m_} for m_ in sorted(g["members"])]}}
            if method == "POST":
                self._need_web_manage(caller)
                upn = data["LoginName"].split("|")[-1]
                self.user(upn)
                g["members"].add(upn.lower())
                return 201, {}, {"d": {"Email": upn}}

        # ---- role definitions
        if rel == "web/roledefinitions":
            if method == "GET":
                res = [{"Id": r["Id"], "Name": r["Name"], "Description": r["Description"],
                        "BasePermissions": masks.split(r["mask"])} for r in self.roledefs.values()]
                f = ctx["qs"].get("$filter")
                if f:
                    mm = re.fullmatch(r"Name eq '(.*)'", f)
                    if mm:
                        res = [r for r in res if r["Name"].lower() == mm.group(1).lower()]
                return 200, {}, {"d": {"results": res}}
            if method == "POST":
                self._need_web_manage(caller)
                bp = data["BasePermissions"]
                rd = self._add_roledef(data["Name"], masks.join(bp["Low"], bp["High"]), description=data.get("Description", ""))
                return 201, {}, {"d": {"Id": rd["Id"], "Name": rd["Name"]}}

        # ---- lists collection
        if rel == "web/lists":
            if method == "GET":
                res = [self._list_json(l) for l in self.lists.values()]
                f = ctx["qs"].get("$filter")
                if f:
                    mm = re.fullmatch(r"Title eq '(.*)'", f)
                    if mm:
                        res = [r for r in res if r["Title"].lower() == mm.group(1).lower()]
                return 200, {}, {"d": {"results": res}}
            if method == "POST":
                self._need_web_manage(caller)
                t = data["Title"]
                if t in self.lists:
                    raise SPHttp(400, "-2130575257, Microsoft.SharePoint.SPException", "A list, survey, discussion board, or document library with the specified title already exists in this Web site.  Please choose another title.")
                fl = FList(t, str(uuid.uuid4()))
                fl.description = data.get("Description", "")
                self.lists[t] = fl
                return 201, {}, {"d": self._list_json(fl)}

        mm = re.match(r"web/lists/getbytitle\('((?:[^']|'')*)'\)(.*)$", rel)
        if mm:
            title = mm.group(1).replace("''", "'")
            rest = mm.group(2)
            fl = self.lists.get(title)
            if fl is None:
                raise SPHttp(404, "-1, System.ArgumentException", f"List '{title}' does not exist at site with URL 'https://fake{self.site_path}'.")
            return self._route_list(ctx, caller, fl, rest, data)
        raise SPHttp(404, "-1", "unhandled route " + rel)

    def _need_web_manage(self, caller):
        if not (self.effective_mask(caller, None) & masks.FLAGS["ManageWeb"]):
            raise SPHttp(403, "-2147024891, System.UnauthorizedAccessException", "Access denied.")

    def _list_json(self, fl):
        return {"Id": fl.id, "Title": fl.title, "Description": fl.description, "BaseTemplate": 100,
                "ItemCount": len(fl.items), "ListItemEntityTypeFullName": fl.entity_type,
                "HasUniqueRoleAssignments": fl.unique_perms, **fl.props}

    # ---- list-scoped routes ------------------------------------------------------------------
    def _route_list(self, ctx, caller, fl: FList, rest, data):
        method = ctx["method"]
        if rest == "":
            if method == "GET":
                self._need(caller, fl, "ViewListItems")
                return 200, {}, {"d": self._list_json(fl)}
            if method == "MERGE":
                self._need(caller, fl, "ManageLists")
                for k, v in data.items():
                    if k == "__metadata":
                        continue
                    if k == "Description":
                        fl.description = v
                    elif k in fl.props:
                        fl.props[k] = v
                    else:
                        raise SPHttp(400, "-1", f"unknown list property {k}")
                return 204, {}, None
        # fields
        if rest.startswith("/fields"):
            return self._route_fields(ctx, caller, fl, rest[len("/fields"):], data)
        # permissions
        mm = re.fullmatch(r"/breakroleinheritance\(copyRoleAssignments=(true|false),\s*clearSubscopes=(true|false)\)", rest)
        if mm and method == "POST":
            self._need(caller, fl, "ManagePermissions")
            if not fl.unique_perms:
                fl.unique_perms = True
                fl.assignments = list(self.web_assignments) if mm.group(1) == "true" else []
            return 200, {}, None
        if rest == "/resetroleinheritance" and method == "POST":
            self._need(caller, fl, "ManagePermissions")
            fl.unique_perms = False
            fl.assignments = []
            return 200, {}, None
        if rest.startswith("/roleassignments"):
            return self._route_roleassign(ctx, caller, fl, rest[len("/roleassignments"):], data)
        if rest.startswith("/items"):
            return self._route_items(ctx, caller, fl, rest[len("/items"):], data)
        raise SPHttp(404, "-1", "unhandled list route " + rest)

    def _route_roleassign(self, ctx, caller, fl, rest, data):
        method = ctx["method"]
        if rest == "" and method == "GET":
            self._need(caller, fl, "ViewListItems")
            assigns = fl.assignments if fl.unique_perms else self.web_assignments
            res = []
            for pkey, rid in assigns:
                rd = next(r for r in self.roledefs.values() if r["Id"] == rid)
                res.append({"Member": self._principal_json(pkey),
                            "RoleDefinitionBindings": {"results": [{"Id": rd["Id"], "Name": rd["Name"]}]}})
            return 200, {}, {"d": {"results": res}}
        mm = re.fullmatch(r"/(add|remove)roleassignment\(principalid=(\d+),\s*roledefid=(\d+)\)", rest)
        if mm and method == "POST":
            self._need(caller, fl, "ManagePermissions")
            if not fl.unique_perms:
                raise SPHttp(400, "-2147467259", "list inherits permissions; break inheritance first")
            pkey = self._principal_by_id(int(mm.group(2)))
            rid = int(mm.group(3))
            if mm.group(1) == "add":
                if (pkey, rid) not in fl.assignments:
                    fl.assignments.append((pkey, rid))
            else:
                fl.assignments = [a for a in fl.assignments if a != (pkey, rid)]
            return 200, {}, None
        raise SPHttp(404, "-1", "unhandled roleassignments route " + rest)

    # ---- fields ------------------------------------------------------------------------------
    def _route_fields(self, ctx, caller, fl, rest, data):
        method = ctx["method"]
        if rest == "" and method == "GET":
            self._need(caller, fl, "ViewListItems")
            res = [f.to_json() for f in fl.fields.values()]
            f = ctx["qs"].get("$filter")
            if f:
                mm = re.fullmatch(r"InternalName eq '(.*)'", f)
                if mm:
                    res = [r for r in res if r["InternalName"] == mm.group(1)]
            return 200, {}, {"d": {"results": res}}
        if rest == "/createfieldasxml" and method == "POST":
            self._need(caller, fl, "ManageLists")
            xml = data["parameters"]["SchemaXml"]
            root = ET.fromstring(xml)
            a = root.attrib
            name = a["Name"]
            if name in fl.fields:
                raise SPHttp(400, "-2130575342, Microsoft.SharePoint.SPException", f"A duplicate field name \"{name}\" was found.")
            choices = [c.text for c in root.findall("./CHOICES/CHOICE")]
            dflt = root.findtext("Default")
            t = a["Type"]
            ff = FField(name, t, display=a.get("DisplayName", name), required=a.get("Required", "FALSE") == "TRUE",
                        indexed=a.get("Indexed", "FALSE") == "TRUE" or a.get("EnforceUniqueValues", "FALSE") == "TRUE",
                        unique=a.get("EnforceUniqueValues", "FALSE") == "TRUE",
                        max_length=int(a.get("MaxLength", 255)),
                        min_=float(a["Min"]) if "Min" in a else None, max_=float(a["Max"]) if "Max" in a else None,
                        choices=choices, decimals=int(a["Decimals"]) if "Decimals" in a else None)
            if ff.unique and not ff.indexed:
                raise SPHttp(400, "-1", "EnforceUniqueValues requires Indexed")
            if dflt is not None:
                ff.default = {"Boolean": lambda x: x == "1", "Number": float, "Currency": float}.get(t, lambda x: x)(dflt)
            if ff.unique and len(fl.items) and any(i["fields"].get(name) is not None for i in fl.items.values()):
                pass
            n_idx = sum(1 for f in fl.fields.values() if f.indexed)
            if ff.indexed and n_idx >= 20:
                raise SPHttp(400, "-1", "A list can have at most 20 indexed columns")
            fl.fields[name] = ff
            return 200, {}, {"d": ff.to_json()}
        mm = re.fullmatch(r"/getbyinternalnameortitle\('([^']*)'\)", rest)
        if mm:
            name = mm.group(1)
            ff = fl.fields.get(name) or next((f for f in fl.fields.values() if f.display == name), None)
            if ff is None:
                raise SPHttp(404, "-1", f"Column '{name}' does not exist.")
            if method == "GET":
                self._need(caller, fl, "ViewListItems")
                return 200, {}, {"d": ff.to_json()}
            if method == "MERGE":
                self._need(caller, fl, "ManageLists")
                for k, v in data.items():
                    if k == "__metadata":
                        continue
                    if k == "Required":
                        ff.required = bool(v)
                    elif k == "Indexed":
                        ff.indexed = bool(v)
                    elif k == "EnforceUniqueValues":
                        if v and not ff.indexed:
                            raise SPHttp(400, "-1", "Column must be indexed to enforce unique values")
                        ff.unique = bool(v)
                    elif k == "Title":
                        ff.display = v
                    elif k == "Description":
                        pass
                    else:
                        raise SPHttp(400, "-1", f"unsupported field property {k}")
                return 204, {}, None
        raise SPHttp(404, "-1", "unhandled fields route " + rest)

    # ---- items -------------------------------------------------------------------------------
    def _validate_value(self, ff: FField, v, listname):
        if v is None:
            return None
        t = ff.type
        if t == "Text":
            v = str(v) if not isinstance(v, str) else v
            if len(v) > ff.max_length:
                raise SPHttp(400, "-2130575163, Microsoft.SharePoint.SPException", f"The value of '{ff.display}' is too long ({len(v)} > {ff.max_length}).")
        elif t == "Note":
            v = str(v)
        elif t in ("Number", "Currency"):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise SPHttp(400, "-1", f"'{ff.display}' must be a number")
            if ff.min is not None and v < ff.min:
                raise SPHttp(400, "-2130575163, Microsoft.SharePoint.SPException", f"'{ff.display}' must be >= {ff.min}")
            if ff.max is not None and v > ff.max:
                raise SPHttp(400, "-2130575163, Microsoft.SharePoint.SPException", f"'{ff.display}' must be <= {ff.max}")
        elif t == "Boolean":
            if v in (1, True, "1", "true", "True"):
                v = True
            elif v in (0, False, "0", "false", "False"):
                v = False
            else:
                raise SPHttp(400, "-1", f"'{ff.display}' must be boolean")
        elif t == "Choice":
            if v not in ff.choices:
                raise SPHttp(400, "-2130575163, Microsoft.SharePoint.SPException", f"'{v}' is not a valid choice for '{ff.display}'")
        elif t == "DateTime":
            try:
                _parse_dt(str(v))
            except Exception:
                raise SPHttp(400, "-1", f"'{ff.display}' must be an ISO date-time")
        return v

    def _check_unique(self, fl, fields, exclude_id=None):
        for name, ff in fl.fields.items():
            if not ff.unique:
                continue
            v = fields.get(name)
            if v is None or v == "":
                continue
            for iid, it in fl.items.items():
                if iid == exclude_id:
                    continue
                ov = it["fields"].get(name)
                if ov is not None and str(ov).lower() == str(v).lower():
                    raise SPHttp(400, "-2130575169, Microsoft.SharePoint.SPException",
                                 f"The list item could not be added or updated because duplicate values were found in the following field(s) in the list: [{ff.display}].")

    def _item_json(self, fl, it, select=None, expand=None):
        out = {}
        for n, ff in fl.fields.items():
            out[n] = it["fields"].get(n)
        out["Id"] = it["id"]
        out["ID"] = it["id"]
        out["AuthorId"] = it["author"]["Id"]
        out["EditorId"] = it["editor"]["Id"]
        if expand and "Author" in expand:
            out["Author"] = {"EMail": it["author"]["EMail"], "Title": it["author"]["Title"], "Id": it["author"]["Id"]}
        if expand and "Editor" in expand:
            out["Editor"] = {"EMail": it["editor"]["EMail"], "Title": it["editor"]["Title"]}
        if select:
            keep = {}
            for s in select:
                s = s.strip()
                if "/" in s:
                    base = s.split("/")[0]
                    if base in out:
                        keep[base] = out[base]
                elif s in out:
                    keep[s] = out[s]
            out = keep
        out["__metadata"] = {"id": f"fake/{fl.title}/{it['id']}", "type": fl.entity_type,
                             "etag": f"\"{it['version']}\"", "uri": f"fake/{fl.title}/items({it['id']})"}
        return out

    def _route_items(self, ctx, caller, fl: FList, rest, data):
        method = ctx["method"]
        qs = ctx["qs"]
        if rest == "":
            if method == "GET":
                self._need(caller, fl, "ViewListItems")
                return self._query(ctx, fl)
            if method == "POST":
                self._need(caller, fl, "AddListItems")
                md = data.get("__metadata")
                # entity type is required only for odata=verbose bodies; nometadata content-type may omit it
                ct = ctx["headers"].get("content-type", "")
                if "nometadata" not in ct and (not md or md.get("type") != fl.entity_type):
                    raise SPHttp(400, "-1, System.InvalidOperationException", "A type named 'SP.Data...' could not be resolved; expected " + fl.entity_type)
                fields = {k: v for k, v in data.items() if k != "__metadata"}
                for k in fields:
                    if k not in fl.fields:
                        raise SPHttp(400, "-1, System.ArgumentException", f"Column '{k}' does not exist. It may have been deleted by another user.")
                    if fl.fields[k].builtin and k in ("Created", "Modified"):
                        pass
                vals = {}
                for n, ff in fl.fields.items():
                    if n in fields:
                        vals[n] = self._validate_value(ff, fields[n], fl.title)
                    elif ff.default is not None:
                        vals[n] = ff.default
                    else:
                        vals[n] = None
                for n, ff in fl.fields.items():
                    if ff.required and (vals.get(n) is None or vals.get(n) == "") and n != "Title":
                        raise SPHttp(400, "-2130575163, Microsoft.SharePoint.SPException", f"You must specify a value for this required field: {ff.display}.")
                    if n == "Title" and ff.required and not vals.get(n):
                        raise SPHttp(400, "-2130575163, Microsoft.SharePoint.SPException", "You must specify a value for this required field: Title.")
                self._check_unique(fl, vals)
                u = self.user(caller)
                now = now_iso()
                vals["Created"], vals["Modified"] = now, now
                it = {"id": fl.next_id, "fields": vals, "version": 1, "author": u, "editor": u}
                fl.items[it["id"]] = it
                fl.next_id += 1
                return 201, {}, {"d": self._item_json(fl, it, None, None)}
        mm = re.fullmatch(r"\((\d+)\)", rest)
        if mm:
            iid = int(mm.group(1))
            it = fl.items.get(iid)
            if it is None:
                raise SPHttp(404, "-2147024809, System.ArgumentException", "Item does not exist. It may have been deleted by another user.")
            if method == "GET":
                self._need(caller, fl, "ViewListItems")
                sel = qs["$select"].split(",") if "$select" in qs else None
                exp = qs["$expand"].split(",") if "$expand" in qs else None
                return 200, {}, {"d": self._item_json(fl, it, sel, exp)}
            if method in ("MERGE", "PATCH", "PUT"):
                self._need(caller, fl, "EditListItems")
                self._check_etag(ctx, it)
                fields = {k: v for k, v in data.items() if k != "__metadata"}
                new = dict(it["fields"])
                for k, v in fields.items():
                    if k not in fl.fields:
                        raise SPHttp(400, "-1, System.ArgumentException", f"Column '{k}' does not exist.")
                    new[k] = self._validate_value(fl.fields[k], v, fl.title)
                for n, ff in fl.fields.items():
                    if ff.required and n in fields and (new.get(n) is None or new.get(n) == "") and n != "Title":
                        raise SPHttp(400, "-2130575163, Microsoft.SharePoint.SPException", f"You must specify a value for this required field: {ff.display}.")
                self._check_unique(fl, new, exclude_id=iid)
                new["Modified"] = now_iso()
                it["fields"] = new
                it["version"] += 1
                it["editor"] = self.user(caller)
                return 204, {"ETag": f"\"{it['version']}\""}, None
            if method == "DELETE":
                self._need(caller, fl, "DeleteListItems")
                self._check_etag(ctx, it)
                del fl.items[iid]
                return 200, {}, None
        raise SPHttp(404, "-1", "unhandled items route " + rest)

    def _check_etag(self, ctx, it):
        im = ctx["headers"].get("if-match")
        if im is None:
            raise SPHttp(412, "-2130575306, Microsoft.SharePoint.SPException", "The request ETag value '' does not match the object's ETag value.")
        if im.strip() == "*":
            return
        if im.strip() != f"\"{it['version']}\"":
            raise SPHttp(412, "-2130575306, Microsoft.SharePoint.SPException",
                         f"The request ETag value '{im}' does not match the object's ETag value '\"{it['version']}\"'.")

    # ---- querying ----------------------------------------------------------------------------
    def _query(self, ctx, fl: FList):
        qs = ctx["qs"]
        types = {n: f.type for n, f in fl.fields.items()}
        flt = qs.get("$filter")
        ast = _Parser(_tokenize(flt)).parse() if flt else None
        items = list(fl.items.values())
        total = len(items)
        # threshold emulation
        if total > self.threshold:
            ok = False
            if ast is not None:
                for c in _conjuncts(ast):
                    flds = self._fields_in(c)
                    if flds and all((fl.fields.get(f) and fl.fields[f].indexed) or f in ("ID", "Id") for f in flds):
                        n = sum(1 for it in items if _eval(c, self._flat(it), types))
                        if n <= self.threshold:
                            ok = True
                            break
            if not ok:
                raise SPHttp(500, "-2147024860, System.Runtime.InteropServices.COMException",
                             "The attempted operation is prohibited because it exceeds the list view threshold enforced by the administrator.")
            ob = qs.get("$orderby")
            if ob:
                for part in ob.split(","):
                    f = part.strip().split(" ")[0]
                    if f not in ("ID", "Id") and not (fl.fields.get(f) and fl.fields[f].indexed):
                        raise SPHttp(500, "-2147024860, System.Runtime.InteropServices.COMException",
                                     "The attempted operation is prohibited because it exceeds the list view threshold enforced by the administrator.")
        if ast is not None:
            items = [it for it in items if _eval(ast, self._flat(it), types)]
        # order
        ob = qs.get("$orderby")
        if ob:
            for part in reversed([p.strip() for p in ob.split(",")]):
                bits = part.split(" ")
                f, desc = bits[0], len(bits) > 1 and bits[1].lower() == "desc"
                if f in ("ID", "Id"):
                    items.sort(key=lambda it: it["id"], reverse=desc)
                else:
                    def kf(it, f=f):
                        v = it["fields"].get(f)
                        return (v is None, v if not isinstance(v, str) else v.lower())
                    items.sort(key=kf, reverse=desc)
        else:
            items.sort(key=lambda it: it["id"])
        skip = 0
        if "$skiptoken" in qs:
            mm = re.search(r"o(\d+)", qs["$skiptoken"])
            skip = int(mm.group(1)) if mm else 0
        top = int(qs["$top"]) if "$top" in qs else DEFAULT_PAGE
        if top > 5000:
            top = 5000
        page = items[skip:skip + top]
        sel = qs["$select"].split(",") if "$select" in qs else None
        exp = qs["$expand"].split(",") if "$expand" in qs else None
        res = [self._item_json(fl, it, sel, exp) for it in page]
        d = {"results": res}
        if skip + top < len(items):
            q2 = dict(qs)
            q2["$skiptoken"] = f"Paged=TRUE&o{skip + top}"
            safe = "$=,'() "
            d["__next"] = f"https://fake{self.site_path}/_api/web/lists/getbytitle('{fl.title}')/items?" + "&".join(
                k + "=" + quote(str(v), safe=safe) for k, v in q2.items())
        return 200, {}, {"d": d}

    @staticmethod
    def _fields_in(node):
        if node[0] in ("and", "or"):
            return FakeSharePoint._fields_in(node[1]) | FakeSharePoint._fields_in(node[2])
        if node[0] == "not":
            return FakeSharePoint._fields_in(node[1])
        if node[0] == "cmp":
            return {n[1] for n in (node[2], node[3]) if n[0] == "field"}
        if node[0] == "fn":
            return {n[1] for n in (node[2], node[3]) if n[0] == "field"}
        return set()

    @staticmethod
    def _flat(it):
        d = dict(it["fields"])
        d["ID"] = d["Id"] = it["id"]
        return d

    # ---- convenience for tests ---------------------------------------------------------------
    def items_of(self, list_title):
        return [dict(it["fields"], Id=it["id"]) for it in self.lists[list_title].items.values()]

    def count(self, list_title):
        return len(self.lists[list_title].items)

    def bulk_load(self, list_title, rows, author="seed@test"):
        """Fast path for large-list tests: bypasses validation but still enforces unique keys."""
        fl = self.lists[list_title]
        u = self.user(author)
        now = now_iso()
        with self.lock:
            for r in rows:
                vals = {n: None for n in fl.fields}
                for n, ff in fl.fields.items():
                    if ff.default is not None:
                        vals[n] = ff.default
                vals.update(r)
                vals["Created"] = vals["Modified"] = now
                fl.items[fl.next_id] = {"id": fl.next_id, "fields": vals, "version": 1, "author": u, "editor": u}
                fl.next_id += 1


# ---------------------------------------------------------------------------------------------
# HTTP wrapper so the REAL client (requests) is exercised in tests
# ---------------------------------------------------------------------------------------------
def serve(fake: FakeSharePoint, host="127.0.0.1", port=0):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        disable_nagle_algorithm = True   # avoid the 40 ms Nagle/delayed-ACK stall on keep-alive connections
        wbufsize = -1                    # single write per response

        def log_message(self, *a):
            pass

        def _do(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else None
            status, hdrs, out = fake.handle(self.command, self.path, dict(self.headers), body)
            raw = json.dumps(out).encode() if out is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json;odata=verbose")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in (hdrs or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = do_DELETE = do_PUT = do_MERGE = do_PATCH = _do

    srv = ThreadingHTTPServer((host, port), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://{host}:{srv.server_address[1]}{fake.site_path}"
