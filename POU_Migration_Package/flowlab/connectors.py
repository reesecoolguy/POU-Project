"""Connector backends for the interpreter: SharePoint 'Send an HTTP request' (via fakesp) and Outlook 'Send an email'."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field

from .runtime import FlowKilled


@dataclass
class Rule:
    """Fault rule. when: 'before' (call not applied) | 'after' (applied, then host dies) | 'lose' (applied, response lost -> 504)
    | 'throttle' (not applied, 429). nth: fire on the nth matching call (1-based) of this rule, or None for every match."""
    method: str
    uri_re: str
    when: str
    nth: int | None = 1
    body_re: str | None = None
    _count: int = 0


class FaultPlan:
    def __init__(self, rules=None):
        self.rules = list(rules or [])
        self.lock = threading.Lock()
        self.fired: list[str] = []

    def match(self, method, uri, body):
        with self.lock:
            for r in self.rules:
                if r.method.upper() != method.upper() or not re.search(r.uri_re, uri):
                    continue
                if r.body_re and not re.search(r.body_re, body or ""):
                    continue
                r._count += 1
                if r.nth is None or r._count == r.nth:
                    self.fired.append(f"{r.when}:{method} {uri[:80]}")
                    return r.when
        return None


class SpBackend:
    """Calls FakeSharePoint.handle exactly as the real connector calls SharePoint REST (relative uri under the dataset)."""

    def __init__(self, fake, upn: str, plan: FaultPlan | None = None, site_path: str | None = None):
        self.fake, self.upn, self.plan = fake, upn, plan or FaultPlan()
        self.site_path = site_path or fake.site_path
        self.calls: list[tuple[str, str]] = []

    def __call__(self, op, params, rt):
        if op != "HttpRequest":
            raise NotImplementedError(op)
        method = params["parameters/method"]
        uri = params["parameters/uri"]
        headers = dict(params.get("parameters/headers") or {})
        body = params.get("parameters/body")
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        self.calls.append((method, uri))
        fault = self.plan.match(method, uri, body)
        if fault == "before":
            raise FlowKilled(f"killed before {method} {uri[:60]}")
        if fault == "throttle":
            return {"statusCode": 429, "headers": {"Retry-After": "1"}, "body": {"error": {"message": {"value": "Too many requests"}}}}
        headers["Authorization"] = f"Bearer fake:{self.upn}"
        status, rh, rb = self.fake.handle(method, self.site_path + uri, headers, body.encode() if isinstance(body, str) else body)
        if fault == "after":
            raise FlowKilled(f"killed after {method} {uri[:60]} (write applied)")
        if fault == "lose":
            return {"statusCode": 504, "headers": {}, "body": {"error": {"message": {"value": "The request timed out (response lost)"}}}}
        return {"statusCode": status, "headers": rh or {}, "body": rb}


class MailBackend:
    def __init__(self):
        self.sent: list[dict] = []
        self.lock = threading.Lock()

    def __call__(self, op, params, rt):
        if op not in ("SendEmailV2", "SendEmailFromSharedMailbox"):
            raise NotImplementedError(op)
        with self.lock:
            self.sent.append({"to": params.get("emailMessage/To"), "subject": params.get("emailMessage/Subject"),
                              "body": params.get("emailMessage/Body"), "attachments": params.get("emailMessage/Attachments")})
        return {"statusCode": 200, "body": {}}


class CallIndexPlan:
    """Inject exactly one fault at the n-th SharePoint call (1-based, counting every call of this run)."""

    def __init__(self, index: int, when: str):
        self.index, self.when, self.n, self.fired = index, when, 0, []
        self.lock = threading.Lock()

    def match(self, method, uri, body):
        with self.lock:
            self.n += 1
            if self.n == self.index:
                self.fired.append(f"{self.when}@{self.n}:{method} {uri[:70]}")
                return self.when
        return None
