"""Executes a workflow definition (dict) with the expression engine, connector backends and a virtual clock."""
from __future__ import annotations

import json
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .expr import Ctx, ExprError, evaluate, evaluate_expression, to_str


class FlowKilled(Exception):
    """Simulated platform/host crash: the run stops dead, nothing after this point executes."""


class FlowTerminated(Exception):
    def __init__(self, status, message=""):
        super().__init__(f"{status}: {message}")
        self.status, self.message = status, message


class Clock:
    def __init__(self, start: datetime | None = None):
        self._t = start or datetime(2026, 10, 8, 14, 0, 0, tzinfo=timezone.utc)
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._t

    def advance(self, seconds: float):
        with self._lock:
            self._t += timedelta(seconds=seconds)


@dataclass
class AR:
    name: str
    status: str = "Skipped"
    outputs: object = None
    body: object = None
    error: str = ""
    kind: str = ""


class ActionLimit(Exception):
    pass


class Runtime:
    def __init__(self, definition: dict, trigger_body=None, trigger_headers=None, connectors=None, clock: Clock | None = None,
                 params=None, rng=None, yield_sleep=True):
        self.d = definition
        self._trigger_body = trigger_body
        self._trigger_headers = trigger_headers or {}
        self.connectors = connectors or {}
        self.clock = clock or Clock()
        self.params = dict(params or {})
        self.vars: dict = {}
        self.results: dict[str, AR] = {}
        self.scope_children: dict[str, list[str]] = {}
        self.loop_stack: dict[str, object] = {}
        self.response = None
        self.status = "Running"
        self.run_name = str(uuid.uuid4()).replace("-", "")[:12]
        self.rng = rng or random.Random()
        self.ctx = Ctx(self)
        self.action_count = 0
        self.max_actions = 20000
        self.yield_sleep = yield_sleep
        self.trace: list[str] = []

    # ---------------------------------------------------------------- services for expressions
    def now(self): return self.clock.now()
    def new_guid(self): return uuid.UUID(int=self.rng.getrandbits(128), version=4)

    def variable(self, n):
        if n not in self.vars:
            raise ExprError(f"variable {n} not initialised")
        return self.vars[n]

    def parameter(self, n):
        if n in self.params:
            return self.params[n]
        p = self.d.get("parameters", {}).get(n)
        if p is not None and "defaultValue" in p:
            return p["defaultValue"]
        raise ExprError(f"parameter {n} undefined")

    def _res(self, n):
        r = self.results.get(n)
        if r is None:
            raise ExprError(f"action '{n}' has not run")
        if r.status == "Skipped":
            raise ExprError(f"action '{n}' was skipped")
        return r

    def action_body(self, n): return self._res(n).body
    def action_outputs(self, n): return self._res(n).outputs

    def action_info(self, n):
        r = self.results.get(n)
        if r is None:
            raise ExprError(f"action '{n}' has not run")
        return {"name": n, "status": r.status, "outputs": r.outputs if r.status != "Skipped" else None,
                "code": r.error or None}

    def scope_result(self, n):
        return [{"name": c, "status": self.results[c].status, "outputs": self.results[c].outputs}
                for c in self.scope_children.get(n, []) if c in self.results]

    def loop_item(self, n):
        if n not in self.loop_stack:
            raise ExprError(f"items('{n}') outside loop")
        return self.loop_stack[n]

    def trigger_body(self): return self._trigger_body
    def trigger_outputs(self): return {"headers": self._trigger_headers, "body": self._trigger_body}
    def workflow_info(self): return {"name": self.d.get("name", "flow"), "run": {"name": self.run_name}}

    # ---------------------------------------------------------------- execution
    def run(self):
        try:
            self._exec_actions(self.d["actions"], "")
            self.status = "Succeeded" if not self._any_failed_top() else "Succeeded"
        except FlowTerminated as t:
            self.status = t.status
        return self

    def _any_failed_top(self):
        return False

    def _order(self, actions: dict):
        names = list(actions)
        done, order = set(), []
        deps = {n: list((actions[n].get("runAfter") or {}).keys()) for n in names}
        for n, ds in deps.items():
            for dname in ds:
                if dname not in actions:
                    raise ExprError(f"runAfter of '{n}' references unknown action '{dname}'")
        while len(order) < len(names):
            progressed = False
            for n in names:
                if n in done:
                    continue
                if all(x in done for x in deps[n]):
                    order.append(n); done.add(n); progressed = True
            if not progressed:
                raise ExprError("cyclic runAfter in " + str(names))
        return order

    def _exec_actions(self, actions: dict, path: str, skip_all=False):
        order = self._order(actions)
        self.scope_children[path] = order
        any_failed = False
        for n in order:
            a = actions[n]
            ra = a.get("runAfter") or {}
            ok = not skip_all
            if ok:
                for pred, allowed in ra.items():
                    st = self.results[pred].status if pred in self.results else "Skipped"
                    if st not in allowed:
                        ok = False
                        break
            if not ok:
                self._mark_skipped(n, a)
                continue
            self.action_count += 1
            if self.action_count > self.max_actions:
                raise ActionLimit(f"more than {self.max_actions} actions executed")
            r = self._exec_one(n, a)
            if r.status in ("Failed", "TimedOut"):
                any_failed = True
        return any_failed

    def _mark_skipped(self, n, a):
        self.results[n] = AR(n, "Skipped", kind=a.get("type", ""))
        for key in ("actions",):
            if key in a:
                self._exec_actions_skipped(a[key], n)
        if "else" in a:
            self._exec_actions_skipped(a["else"].get("actions", {}), n)
        for c in (a.get("cases") or {}).values():
            self._exec_actions_skipped(c.get("actions", {}), n)
        if "default" in a:
            self._exec_actions_skipped(a["default"].get("actions", {}), n)

    def _exec_actions_skipped(self, actions, path):
        for n, a in actions.items():
            self._mark_skipped(n, a)

    def _exec_one(self, n, a) -> AR:
        t = a["type"]
        r = AR(n, "Succeeded", kind=t)
        self.results[n] = r
        ctx = self.ctx
        try:
            if t == "Compose":
                v = evaluate(a["inputs"], ctx)
                r.outputs = r.body = v
            elif t == "InitializeVariable":
                for var in a["inputs"]["variables"]:
                    v = evaluate(var.get("value"), ctx)
                    self.vars[var["name"]] = v
            elif t == "SetVariable":
                self.vars[a["inputs"]["name"]] = evaluate(a["inputs"]["value"], ctx)
            elif t == "IncrementVariable":
                self.vars[a["inputs"]["name"]] += evaluate(a["inputs"].get("value", 1), ctx)
            elif t == "AppendToArrayVariable":
                self.vars[a["inputs"]["name"]].append(evaluate(a["inputs"]["value"], ctx))
            elif t == "AppendToStringVariable":
                self.vars[a["inputs"]["name"]] += to_str(evaluate(a["inputs"]["value"], ctx))
            elif t == "If":
                cond = self._cond(a["expression"])
                branch = a.get("actions", {}) if cond else a.get("else", {}).get("actions", {})
                other = a.get("else", {}).get("actions", {}) if cond else a.get("actions", {})
                self._exec_actions_skipped(other, n)
                failed = self._exec_actions(branch, n)
                r.status = "Failed" if failed else "Succeeded"
                r.outputs = {"condition": cond}
            elif t == "Switch":
                val = evaluate(a["expression"], ctx)
                chosen = None
                for cname, c in (a.get("cases") or {}).items():
                    if chosen is None and to_str(evaluate(c["case"], ctx)) == to_str(val):
                        chosen = cname
                failed = False
                for cname, c in (a.get("cases") or {}).items():
                    if cname == chosen:
                        failed |= self._exec_actions(c.get("actions", {}), n)
                    else:
                        self._exec_actions_skipped(c.get("actions", {}), n)
                if chosen is None and "default" in a:
                    failed |= self._exec_actions(a["default"].get("actions", {}), n)
                elif "default" in a:
                    self._exec_actions_skipped(a["default"].get("actions", {}), n)
                r.status = "Failed" if failed else "Succeeded"
            elif t == "Scope":
                failed = self._exec_actions(a["actions"], n)
                r.status = "Failed" if failed else "Succeeded"
            elif t == "Foreach":
                items = evaluate(a["foreach"], ctx)
                if not isinstance(items, list):
                    raise ExprError("foreach input is not an array")
                failed = False
                for it in items:
                    self.loop_stack[n] = it
                    ctx.item_stack.append(it)
                    try:
                        failed |= self._exec_actions(a["actions"], n)
                    finally:
                        ctx.item_stack.pop()
                self.loop_stack.pop(n, None)
                r.status = "Failed" if failed else "Succeeded"
            elif t == "Until":
                limit = (a.get("limit") or {}).get("count", 60)
                failed, i = False, 0
                while True:
                    failed |= self._exec_actions(a["actions"], n)
                    i += 1
                    if evaluate(a["expression"], ctx) is True or i >= limit:
                        break
                r.status = "Failed" if failed else "Succeeded"
            elif t == "Terminate":
                inp = a["inputs"]
                raise FlowTerminated(inp["runStatus"], to_str(evaluate(inp.get("runError", {}).get("message", ""), ctx)) if inp.get("runError") else "")
            elif t == "Response":
                inp = a["inputs"]
                resp = {"statusCode": evaluate(inp.get("statusCode", 200), ctx), "body": evaluate(inp.get("body"), ctx)}
                if self.response is None:
                    self.response = resp
                r.outputs = resp
            elif t == "Delay":
                iv = a["inputs"]["interval"]
                mult = {"Second": 1, "Minute": 60, "Hour": 3600, "Day": 86400}[iv["unit"]]
                self.clock.advance(iv["count"] * mult)
                if self.yield_sleep:
                    time.sleep(0.0005 * iv["count"])   # scaled so other threads really interleave during back-off
            elif t == "ParseJson":
                c = evaluate(a["inputs"]["content"], ctx)
                r.outputs = r.body = json.loads(c) if isinstance(c, str) else c
            elif t == "Select":
                src = evaluate(a["inputs"]["from"], ctx)
                out = []
                for it in src:
                    ctx.item_stack.append(it)
                    try:
                        out.append(evaluate(a["inputs"]["select"], ctx))
                    finally:
                        ctx.item_stack.pop()
                r.outputs = r.body = out
            elif t == "Query":
                src = evaluate(a["inputs"]["from"], ctx)
                out = []
                for it in src:
                    ctx.item_stack.append(it)
                    try:
                        w = evaluate(a["inputs"]["where"], ctx)
                        if not isinstance(w, bool):
                            raise ExprError(f"Filter array 'where' must be boolean, got {w!r}")
                        if w:
                            out.append(it)
                    finally:
                        ctx.item_stack.pop()
                r.outputs = r.body = out
            elif t == "Join":
                src = evaluate(a["inputs"]["from"], ctx)
                r.outputs = r.body = evaluate(a["inputs"]["joinWith"], ctx).join(to_str(x) for x in src)
            elif t == "Table":
                src = evaluate(a["inputs"]["from"], ctx)
                cols = a["inputs"].get("columns")
                fmt = a["inputs"]["format"]
                if cols is None:
                    cols = [{"header": k, "value": "@item()?['%s']" % k} for k in (src[0].keys() if src else [])]
                rows = []
                for it in src:
                    ctx.item_stack.append(it)
                    try:
                        rows.append([to_str(evaluate(c["value"], ctx)) for c in cols])
                    finally:
                        ctx.item_stack.pop()
                hdr = [c["header"] for c in cols]
                if fmt == "CSV":
                    esc = lambda s: '"' + s.replace('"', '""') + '"' if any(ch in s for ch in ',"\n') else s
                    r.outputs = r.body = "\n".join([",".join(map(esc, hdr))] + [",".join(map(esc, row)) for row in rows])
                else:
                    r.outputs = r.body = "<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in hdr) + "</tr></thead><tbody>" + \
                        "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows) + "</tbody></table>"
            elif t == "ApiConnection":
                inp = a["inputs"]
                host = inp["host"]
                params = evaluate(inp.get("parameters", {}), ctx)
                be = self.connectors.get(host["connectionName"])
                if be is None:
                    raise ExprError(f"no connector backend for {host['connectionName']}")
                out = be(host["operationId"], params, self)
                r.outputs = out
                r.body = out.get("body") if isinstance(out, dict) else None
                sc = out.get("statusCode", 200) if isinstance(out, dict) else 200
                if not (200 <= int(sc) < 300):
                    r.status = "Failed"
                    r.error = f"HTTP {sc}"
            else:
                raise ExprError(f"unsupported action type {t} ({n})")
        except (FlowKilled, FlowTerminated, ActionLimit):
            raise
        except ExprError as e:
            r.status = "Failed"
            r.error = f"ExpressionEvaluationFailed: {e}"
            self.trace.append(f"{n}: {r.error}")
            self.expr_failures = getattr(self, "expr_failures", [])
            self.expr_failures.append((n, str(e)))
        return r

    def _cond(self, e):
        ctx = self.ctx
        if isinstance(e, str):
            v = evaluate(e, ctx)
            if not isinstance(v, bool):
                raise ExprError(f"condition not boolean: {v!r}")
            return v
        (op, args), = e.items()
        if op == "and":
            return all(self._cond(x) for x in args)
        if op == "or":
            return any(self._cond(x) for x in args)
        if op == "not":
            return not self._cond(args)
        vals = [evaluate(x, ctx) for x in args]
        from .expr import call
        return call(op, [("lit", v) for v in vals], lambda n: n[1], ctx)
