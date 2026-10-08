"""Minimal SharePoint Online REST client (verbose OData) with throttling-aware retries.

Used by provisioning, the importer, the post-import reconciliation and tests (against fakesp over real HTTP).
No credentials are ever read from or written to files by this module.
"""
from __future__ import annotations

import json
import random
import time
from typing import Callable, Iterator
from urllib.parse import quote

import requests

JSON = "application/json;odata=verbose"


class SpError(Exception):
    def __init__(self, status: int, code: str, message: str, method: str = "", url: str = ""):
        super().__init__(f"HTTP {status} {code}: {message} [{method} {url}]")
        self.status, self.code, self.message = status, code, message

    @property
    def is_duplicate(self) -> bool:
        return self.status in (400, 409) and "duplicate" in self.message.lower()

    @property
    def is_precondition(self) -> bool:
        return self.status == 412

    @property
    def is_threshold(self) -> bool:
        return "threshold" in self.message.lower()

    @property
    def is_forbidden(self) -> bool:
        return self.status in (401, 403)


def odata_str(s: str) -> str:
    """Escape a string for use inside a single-quoted OData literal."""
    return str(s).replace("'", "''")


class SpClient:
    def __init__(self, site_url: str, token_provider: Callable[[], str], session: requests.Session | None = None,
                 max_retries: int = 6, sleep: Callable[[float], None] = time.sleep, user_agent: str = "POU-Tools/1.0"):
        self.site_url = site_url.rstrip("/")
        self.token_provider = token_provider
        self.http = session or requests.Session()
        self.max_retries = max_retries
        self.sleep = sleep
        self.user_agent = user_agent
        self._types: dict[str, str] = {}
        self.stats = {"requests": 0, "retries": 0}

    # ------------------------------------------------------------------ low level
    def _headers(self, extra=None, method="GET"):
        h = {"Authorization": f"Bearer {self.token_provider()}", "Accept": JSON, "User-Agent": self.user_agent}
        if method != "GET":
            h["Content-Type"] = JSON
        if extra:
            h.update(extra)
        return h

    def request(self, method: str, rel: str, body=None, headers=None, ok=(200, 201, 204)) -> dict | None:
        url = rel if rel.startswith("http") else f"{self.site_url}/_api/{rel.lstrip('/')}"
        attempt = 0
        while True:
            self.stats["requests"] += 1
            data = json.dumps(body) if body is not None else None
            send_method = method
            hdrs = self._headers(headers, method)
            if method in ("MERGE", "PATCH", "DELETE"):
                hdrs["X-HTTP-Method"] = method
                send_method = "POST"
            try:
                r = self.http.request(send_method, url, data=data, headers=hdrs, timeout=60)
            except requests.RequestException as e:
                if attempt >= self.max_retries:
                    raise SpError(0, "NETWORK", str(e), method, url)
                attempt += 1
                self.stats["retries"] += 1
                self.sleep(min(30, 2 ** attempt) * (0.5 + random.random() / 2))
                continue
            if r.status_code in (429, 503, 504) and attempt < self.max_retries:
                attempt += 1
                self.stats["retries"] += 1
                ra = r.headers.get("Retry-After")
                self.sleep(float(ra) if ra and ra.replace(".", "").isdigit() else min(60, 2 ** attempt))
                continue
            if r.status_code in ok:
                if r.content:
                    try:
                        return r.json()
                    except ValueError:
                        return None
                return None
            code, msg = "", r.text[:500]
            try:
                e = r.json().get("error", {})
                code = str(e.get("code", ""))
                m = e.get("message", {})
                msg = m.get("value", msg) if isinstance(m, dict) else str(m)
            except ValueError:
                pass
            raise SpError(r.status_code, code, msg, method, url)

    # ------------------------------------------------------------------ lists
    @staticmethod
    def _lp(title: str) -> str:
        return f"web/lists/getbytitle('{odata_str(title)}')"

    def get_list(self, title: str) -> dict | None:
        try:
            return self.request("GET", self._lp(title))["d"]
        except SpError as e:
            if e.status == 404:
                return None
            raise

    def create_list(self, title: str, description: str = "") -> dict:
        return self.request("POST", "web/lists", {"__metadata": {"type": "SP.List"}, "BaseTemplate": 100,
                                                  "Title": title, "Description": description})["d"]

    def update_list(self, title: str, props: dict):
        self.request("MERGE", self._lp(title), {"__metadata": {"type": "SP.List"}, **props}, {"IF-MATCH": "*"})

    def list_fields(self, title: str) -> dict[str, dict]:
        res = self.request("GET", self._lp(title) + "/fields")["d"]["results"]
        return {f["InternalName"]: f for f in res}

    def create_field_xml(self, title: str, schema_xml: str):
        return self.request("POST", self._lp(title) + "/fields/createfieldasxml",
                            {"parameters": {"__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"},
                                            "SchemaXml": schema_xml, "Options": 8}})

    def update_field(self, title: str, internal_name: str, props: dict):
        self.request("MERGE", self._lp(title) + f"/fields/getbyinternalnameortitle('{odata_str(internal_name)}')",
                     {"__metadata": {"type": "SP.Field"}, **props}, {"IF-MATCH": "*"})

    # ------------------------------------------------------------------ items
    def entity_type(self, title: str) -> str:
        if title not in self._types:
            self._types[title] = self.request("GET", self._lp(title) + "?$select=ListItemEntityTypeFullName")["d"]["ListItemEntityTypeFullName"]
        return self._types[title]

    def query(self, title: str, filter: str | None = None, select: str | None = None, orderby: str | None = None,
              expand: str | None = None, top: int = 100, max_items: int | None = None) -> Iterator[dict]:
        """Yield every matching item, following __next links (never relies on one big page)."""
        parts = [f"$top={int(top)}"]
        if filter:
            parts.append("$filter=" + quote(filter, safe="'()=, "))
        if select:
            parts.append("$select=" + select)
        if orderby:
            parts.append("$orderby=" + quote(orderby, safe=", "))
        if expand:
            parts.append("$expand=" + expand)
        url = self._lp(title) + "/items?" + "&".join(parts)
        n = 0
        while url:
            d = self.request("GET", url)["d"]
            for it in d["results"]:
                yield it
                n += 1
                if max_items and n >= max_items:
                    return
            url = d.get("__next")

    def get_by_key(self, title: str, field: str, value: str, select: str | None = None) -> dict | None:
        rows = list(self.query(title, f"{field} eq '{odata_str(value)}'", select, top=2))
        if len(rows) > 1:
            raise SpError(0, "AMBIGUOUS", f"{title}.{field}={value!r} matched {len(rows)} rows")
        return rows[0] if rows else None

    def create_item(self, title: str, fields: dict) -> dict:
        body = {"__metadata": {"type": self.entity_type(title)}, **fields}
        return self.request("POST", self._lp(title) + "/items", body)["d"]

    def update_item(self, title: str, item_id: int, fields: dict, etag: str = "*"):
        self.request("MERGE", self._lp(title) + f"/items({int(item_id)})",
                     {"__metadata": {"type": self.entity_type(title)}, **fields}, {"IF-MATCH": etag})

    def delete_item(self, title: str, item_id: int, etag: str = "*"):
        self.request("DELETE", self._lp(title) + f"/items({int(item_id)})", None, {"IF-MATCH": etag})

    # ------------------------------------------------------------------ principals
    def current_user(self) -> dict:
        return self.request("GET", "web/currentuser")["d"]

    def find_group(self, title: str) -> dict | None:
        res = self.request("GET", "web/sitegroups?$filter=Title eq '" + odata_str(title) + "'")["d"]["results"]
        return res[0] if res else None

    def create_group(self, title: str, description: str = "") -> dict:
        return self.request("POST", "web/sitegroups", {"__metadata": {"type": "SP.Group"}, "Title": title, "Description": description})["d"]

    def find_roledef(self, name: str) -> dict | None:
        res = self.request("GET", "web/roledefinitions?$filter=Name eq '" + odata_str(name) + "'")["d"]["results"]
        return res[0] if res else None

    def create_roledef(self, name: str, low: int, high: int, description: str = "") -> dict:
        return self.request("POST", "web/roledefinitions", {
            "__metadata": {"type": "SP.RoleDefinition"}, "Name": name, "Description": description, "Order": 100,
            "BasePermissions": {"__metadata": {"type": "SP.BasePermissions"}, "Low": str(low), "High": str(high)}})["d"]

    def list_assignments(self, title: str) -> list[dict]:
        return self.request("GET", self._lp(title) + "/roleassignments?$expand=Member,RoleDefinitionBindings")["d"]["results"]

    def break_inheritance(self, title: str):
        self.request("POST", self._lp(title) + "/breakroleinheritance(copyRoleAssignments=false,clearSubscopes=true)")

    def add_assignment(self, title: str, principal_id: int, roledef_id: int):
        self.request("POST", self._lp(title) + f"/roleassignments/addroleassignment(principalid={principal_id},roledefid={roledef_id})")

    def add_user_to_group(self, group_id: int, login_name: str):
        self.request("POST", f"web/sitegroups({group_id})/users", {"__metadata": {"type": "SP.User"}, "LoginName": login_name})
