"""Expression language: @expr, @{interpolation}, functions, ?['x'] navigation."""
from __future__ import annotations

import base64
import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

WIN_TZ = {
    "Central Standard Time": "America/Chicago", "Eastern Standard Time": "America/New_York",
    "Pacific Standard Time": "America/Los_Angeles", "Mountain Standard Time": "America/Denver", "UTC": "UTC",
}


class ExprError(Exception):
    pass


# ------------------------------------------------------------------------------------------ tokenizer / parser
_TOK = re.compile(r"""\s*(?:
    (?P<str>'(?:[^']|'')*') |
    (?P<num>-?\d+(?:\.\d+)?) |
    (?P<id>[A-Za-z_][A-Za-z0-9_]*) |
    (?P<qb>\?\[) | (?P<lb>\[) | (?P<rb>\]) |
    (?P<lp>\() | (?P<rp>\)) | (?P<comma>,) | (?P<dot>\.)
)""", re.X)


def tokenize(s: str):
    pos, out = 0, []
    while pos < len(s):
        m = _TOK.match(s, pos)
        if not m or m.end() == pos:
            if s[pos:].strip() == "":
                break
            raise ExprError(f"cannot tokenize at {s[pos:pos+30]!r} in {s!r}")
        pos = m.end()
        k = m.lastgroup
        out.append((k, m.group(k)))
    return out


class P:
    def __init__(self, toks, src):
        self.t, self.i, self.src = toks, 0, src

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def eat(self, kind=None):
        k, v = self.peek()
        if kind and k != kind:
            raise ExprError(f"expected {kind} got {k} {v!r} in {self.src!r}")
        self.i += 1
        return k, v

    def parse(self):
        n = self.expr()
        if self.i != len(self.t):
            raise ExprError(f"unexpected trailing {self.t[self.i:]} in {self.src!r}")
        return n

    def expr(self):
        k, v = self.eat()
        if k == "str":
            node = ("lit", v[1:-1].replace("''", "'"))
        elif k == "num":
            node = ("lit", float(v) if "." in v else int(v))
        elif k == "id":
            if self.peek()[0] == "lp":
                self.eat("lp")
                args = []
                if self.peek()[0] != "rp":
                    args.append(self.expr())
                    while self.peek()[0] == "comma":
                        self.eat("comma")
                        args.append(self.expr())
                self.eat("rp")
                node = ("call", v, args)
            elif v == "true":
                node = ("lit", True)
            elif v == "false":
                node = ("lit", False)
            elif v == "null":
                node = ("lit", None)
            else:
                raise ExprError(f"bare identifier {v!r} in {self.src!r}")
        else:
            raise ExprError(f"unexpected token {k} {v!r} in {self.src!r}")
        while True:
            k, v = self.peek()
            if k == "qb":
                self.eat(); idx = self.expr(); self.eat("rb"); node = ("idx", node, idx, True)
            elif k == "lb":
                self.eat(); idx = self.expr(); self.eat("rb"); node = ("idx", node, idx, False)
            elif k == "dot":
                self.eat(); _, name = self.eat("id"); node = ("idx", node, ("lit", name), False)
            else:
                break
        return node


_cache: dict[str, tuple] = {}


def parse(src: str):
    if src not in _cache:
        _cache[src] = P(tokenize(src), src).parse()
    return _cache[src]


# ------------------------------------------------------------------------------------------ values
def _type_name(v):
    return type(v).__name__


def _hkey(v):
    """Hashable canonical key with the same equality as strict_eq (type-strict, deep)."""
    import json
    try:
        return json.dumps(v, sort_keys=True, default=str)
    except TypeError:
        return repr(v)


def strict_eq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if a is None or b is None:
        return a is None and b is None
    return a == b


def to_str(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else repr(v)
    if isinstance(v, (list, dict)):
        return json.dumps(v, separators=(",", ":"), ensure_ascii=False)
    return str(v)


def to_num(v):
    if isinstance(v, bool) or v is None:
        raise ExprError(f"not a number: {v!r}")
    if isinstance(v, (int, float)):
        return v
    raise ExprError(f"not a number: {v!r}")


def parse_ts(s):
    if isinstance(s, datetime):
        return s
    if not isinstance(s, str):
        raise ExprError(f"not a timestamp: {s!r}")
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    t = re.sub(r"(\.\d{6})\d+", r"\1", t)
    d = datetime.fromisoformat(t)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


_FMT = re.compile(r"'[^']*'|y+|M+|d+|H+|h+|m+|s+|f+|t+|.", re.S)


def fmt_dt(d: datetime, fmt: str | None):
    if fmt is None or fmt == "o":
        return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond:06d}0Z"
    if fmt == "s":
        return d.strftime("%Y-%m-%dT%H:%M:%S")
    out = []
    for tok in _FMT.findall(fmt):
        c = tok[0]
        if c == "'":
            out.append(tok[1:-1])
        elif c == "y":
            out.append(f"{d.year:04d}" if len(tok) >= 4 else f"{d.year % 100:02d}")
        elif c == "M":
            out.append({1: str(d.month), 2: f"{d.month:02d}", 3: d.strftime("%b"), 4: d.strftime("%B")}.get(len(tok), f"{d.month:02d}"))
        elif c == "d":
            out.append({1: str(d.day), 2: f"{d.day:02d}", 3: d.strftime("%a"), 4: d.strftime("%A")}.get(len(tok), f"{d.day:02d}"))
        elif c == "H":
            out.append(f"{d.hour:02d}" if len(tok) > 1 else str(d.hour))
        elif c == "h":
            h = d.hour % 12 or 12
            out.append(f"{h:02d}" if len(tok) > 1 else str(h))
        elif c == "m":
            out.append(f"{d.minute:02d}" if len(tok) > 1 else str(d.minute))
        elif c == "s":
            out.append(f"{d.second:02d}" if len(tok) > 1 else str(d.second))
        elif c == "f":
            out.append(f"{d.microsecond:06d}"[:len(tok)])
        elif c == "t":
            out.append(("AM" if d.hour < 12 else "PM")[:len(tok)])
        else:
            out.append(tok)
    return "".join(out)


class Ctx:
    """Evaluation context supplied by the runtime."""

    def __init__(self, runtime=None):
        self.rt = runtime
        self.item_stack: list = []     # current item() values (innermost last)
        self.loop_items: dict = {}     # loop name -> current item


def _ticks(d: datetime):
    base = datetime(1, 1, 1, tzinfo=timezone.utc)
    delta = d - base
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def _unit(d: datetime, n, unit):
    unit = unit.lower()
    if unit.startswith("second"):
        return d + timedelta(seconds=n)
    if unit.startswith("minute"):
        return d + timedelta(minutes=n)
    if unit.startswith("hour"):
        return d + timedelta(hours=n)
    if unit.startswith("day"):
        return d + timedelta(days=n)
    if unit.startswith("week"):
        return d + timedelta(weeks=n)
    raise ExprError(f"bad time unit {unit}")


def _lazy_if(args, ev):
    c = ev(args[0])
    if not isinstance(c, bool):
        raise ExprError(f"if() condition must be boolean, got {c!r}")
    return ev(args[1] if c else args[2])


def _and(args, ev):
    # EAGER on purpose: flows must not rely on short-circuit evaluation (unverified in the real engine).
    vals = [ev(a) for a in args]
    for v in vals:
        if not isinstance(v, bool):
            raise ExprError(f"and() needs booleans, got {v!r}")
    return all(vals)


def _or(args, ev):
    vals = [ev(a) for a in args]
    for v in vals:
        if not isinstance(v, bool):
            raise ExprError(f"or() needs booleans, got {v!r}")
    return any(vals)


def _coalesce(args, ev):
    for a in args:
        v = ev(a)
        if v is not None:
            return v
    return None


LAZY = {"if": _lazy_if, "and": _and, "or": _or, "coalesce": _coalesce}


def _cmp(a, b, op):
    if isinstance(a, bool) or isinstance(b, bool):
        raise ExprError("cannot order booleans")
    if a is None or b is None:
        raise ExprError(f"cannot compare {a!r} {b!r}")
    if type(a) != type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        raise ExprError(f"cannot compare {a!r} with {b!r}")
    return {"gt": a > b, "ge": a >= b, "lt": a < b, "le": a <= b}[op]


def _xml(v):
    """Minimal xml(json(...)) support: returns ('xml', obj)."""
    return ("xml", v)


def _xpath(x, path):
    if not (isinstance(x, tuple) and x[0] == "xml"):
        raise ExprError("xpath needs xml()")
    obj = x[1]
    m = re.fullmatch(r"(sum|count)\(//([A-Za-z_][A-Za-z0-9_]*)\)", path)
    if not m:
        raise ExprError(f"unsupported xpath in flowlab: {path}")
    fn, name = m.groups()
    vals = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == name:
                    if isinstance(v, list):
                        vals.extend(v)
                    else:
                        vals.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    if fn == "count":
        return len(vals)
    s = 0
    for v in vals:
        if v is None or v == "":
            continue
        s += float(v)
    return int(s) if s == int(s) else s


def call(name: str, args: list, ev, ctx: Ctx):
    n = name
    if n in LAZY:
        return LAZY[n](args, ev)
    a = [ev(x) for x in args]
    rt = ctx.rt
    # ---- logic / comparison
    if n == "equals": return strict_eq(a[0], a[1])
    if n == "not":
        if not isinstance(a[0], bool): raise ExprError(f"not() needs boolean, got {a[0]!r}")
        return not a[0]
    if n == "greater": return _cmp(a[0], a[1], "gt")
    if n == "greaterOrEquals": return _cmp(a[0], a[1], "ge")
    if n == "less": return _cmp(a[0], a[1], "lt")
    if n == "lessOrEquals": return _cmp(a[0], a[1], "le")
    # ---- math
    if n == "add": return to_num(a[0]) + to_num(a[1])
    if n == "sub": return to_num(a[0]) - to_num(a[1])
    if n == "mul": return to_num(a[0]) * to_num(a[1])
    if n == "div":
        x, y = to_num(a[0]), to_num(a[1])
        if y == 0: raise ExprError("division by zero")
        return x // y if isinstance(x, int) and isinstance(y, int) else x / y
    if n == "mod": return math.fmod(to_num(a[0]), to_num(a[1])) if isinstance(a[0], float) or isinstance(a[1], float) else to_num(a[0]) % to_num(a[1])
    if n == "min": return min(a[0] if isinstance(a[0], list) else a)
    if n == "max": return max(a[0] if isinstance(a[0], list) else a)
    if n == "range": return list(range(a[0], a[0] + a[1]))
    # ---- conversion
    if n == "string": return to_str(a[0])
    if n == "int":
        v = a[0]
        if isinstance(v, bool) or v is None: raise ExprError(f"int({v!r})")
        if isinstance(v, str):
            try: return int(float(v)) if re.fullmatch(r"\s*-?\d+(\.\d+)?\s*", v) else (_ for _ in ()).throw(ValueError())
            except ValueError: raise ExprError(f"int({v!r})")
        return int(v)
    if n == "float":
        try: return float(a[0])
        except (TypeError, ValueError): raise ExprError(f"float({a[0]!r})")
    if n == "bool":
        v = a[0]
        if isinstance(v, str): return v.lower() == "true"
        return bool(v)
    if n == "json":
        v = a[0]
        if isinstance(v, str):
            try: return json.loads(v)
            except ValueError as e: raise ExprError(f"json(): {e}")
        return v
    if n == "xml": return _xml(a[0])
    if n == "xpath": return _xpath(a[0], a[1])
    if n == "array": return [a[0]]
    if n == "createArray": return list(a)
    if n == "base64": return base64.b64encode(to_str(a[0]).encode()).decode()
    if n == "decodeBase64":
        if a[0] is None: raise ExprError("decodeBase64(null)")
        return base64.b64decode(a[0]).decode()
    if n == "uriComponent": return quote(to_str(a[0]), safe="")
    if n == "guid": return str(rt.new_guid() if rt else uuid.uuid4())
    # ---- strings
    if n == "concat": return "".join(to_str(x) for x in a)
    if n == "toLower": return to_str(a[0]).lower()
    if n == "toUpper": return to_str(a[0]).upper()
    if n == "trim": return to_str(a[0]).strip()
    if n == "replace":
        if not isinstance(a[0], str): raise ExprError(f"replace() needs string, got {a[0]!r}")
        return a[0].replace(a[1], a[2])
    if n == "substring":
        s = a[0]
        if a[1] + (a[2] if len(a) > 2 else 0) > len(s): raise ExprError("substring out of range")
        return s[a[1]:a[1] + a[2]] if len(a) > 2 else s[a[1]:]
    if n == "split": return a[0].split(a[1]) if a[1] else list(a[0])
    if n == "join": return a[1].join(to_str(x) for x in a[0])
    if n == "startsWith": return to_str(a[0]).lower().startswith(to_str(a[1]).lower())
    if n == "endsWith": return to_str(a[0]).lower().endswith(to_str(a[1]).lower())
    if n == "indexOf": return to_str(a[0]).lower().find(to_str(a[1]).lower())
    if n == "contains":
        c, v = a
        if isinstance(c, str): return to_str(v).lower() in c.lower()
        if isinstance(c, list): return any(strict_eq(x, v) for x in c)
        if isinstance(c, dict): return v in c
        raise ExprError("contains() on null")
    if n == "length":
        if a[0] is None: raise ExprError("length(null)")
        return len(a[0])
    if n == "empty":
        v = a[0]
        return v is None or (hasattr(v, "__len__") and len(v) == 0)
    # ---- collections
    if n == "first":
        v = a[0]
        return (v[0] if len(v) else None) if v is not None else None
    if n == "last":
        v = a[0]
        return (v[-1] if len(v) else None) if v is not None else None
    if n == "take": return a[0][:a[1]]
    if n == "skip": return a[0][a[1]:]
    if n == "union":
        if all(isinstance(x, dict) for x in a):
            r = {}
            for x in a: r.update(x)
            return r
        r, seen = [], set()
        for x in a:
            for y in x:
                k = _hkey(y)
                if k not in seen:
                    seen.add(k); r.append(y)
        return r
    if n == "intersection":
        other = {_hkey(y) for y in a[1]}
        return [x for x in a[0] if _hkey(x) in other]
    if n == "setProperty":
        d = dict(a[0]); d[a[1]] = a[2]; return d
    if n == "addProperty":
        if a[1] in a[0]: raise ExprError("property exists")
        d = dict(a[0]); d[a[1]] = a[2]; return d
    if n == "removeProperty":
        d = dict(a[0]); d.pop(a[1], None); return d
    # ---- time
    if n == "utcNow":
        return fmt_dt(rt.now() if rt else datetime.now(timezone.utc), a[0] if a else None)
    if n == "formatDateTime": return fmt_dt(parse_ts(a[0]), a[1] if len(a) > 1 else None)
    if n in ("addSeconds", "addMinutes", "addHours", "addDays"):
        unit = n[3:].lower()
        return fmt_dt(_unit(parse_ts(a[0]), a[1], unit), a[2] if len(a) > 2 else None)
    if n == "subtractFromTime": return fmt_dt(_unit(parse_ts(a[0]), -a[1], a[2]), a[3] if len(a) > 3 else None)
    if n == "getPastTime": return fmt_dt(_unit(rt.now(), -a[0], a[1]), a[2] if len(a) > 2 else None)
    if n == "getFutureTime": return fmt_dt(_unit(rt.now(), a[0], a[1]), a[2] if len(a) > 2 else None)
    if n == "ticks": return _ticks(parse_ts(a[0]))
    if n == "dayOfWeek": return (parse_ts(a[0]).weekday() + 1) % 7
    if n == "convertFromUtc":
        tz = ZoneInfo(WIN_TZ.get(a[1], a[1]))
        return fmt_dt(parse_ts(a[0]).astimezone(tz), a[2] if len(a) > 2 else None)
    if n == "convertToUtc":
        tz = ZoneInfo(WIN_TZ.get(a[1], a[1]))
        s = a[0]
        d = datetime.fromisoformat(s.rstrip("Z")).replace(tzinfo=tz)
        return fmt_dt(d.astimezone(timezone.utc), a[2] if len(a) > 2 else None)
    # ---- workflow context (need runtime)
    if rt is None:
        raise ExprError(f"function {n} needs a runtime")
    if n == "variables": return rt.variable(a[0])
    if n == "parameters": return rt.parameter(a[0])
    if n == "body": return rt.action_body(a[0])
    if n == "outputs": return rt.action_outputs(a[0])
    if n == "actions": return rt.action_info(a[0])
    if n == "result": return rt.scope_result(a[0])
    if n == "items": return rt.loop_item(a[0])
    if n == "item":
        if not ctx.item_stack: raise ExprError("item() outside of loop/select")
        return ctx.item_stack[-1]
    if n == "triggerBody": return rt.trigger_body()
    if n == "triggerOutputs": return rt.trigger_outputs()
    if n == "workflow": return rt.workflow_info()
    raise ExprError(f"unsupported function {n}()")


def _index(base, key, safe):
    if base is None:
        if safe:
            return None
        raise ExprError("indexing null")
    if isinstance(base, dict):
        if key in base:
            return base[key]
        if safe:
            return None
        raise ExprError(f"property {key!r} does not exist (use ?['..'] if optional)")
    if isinstance(base, list):
        if isinstance(key, int) and -len(base) <= key < len(base):
            return base[key]
        if safe:
            return None
        raise ExprError(f"index {key!r} out of range")
    if isinstance(base, tuple):
        raise ExprError("cannot index xml")
    if safe:
        return None
    raise ExprError(f"cannot index {type(base).__name__}")


def ev_node(node, ctx: Ctx):
    k = node[0]
    if k == "lit":
        return node[1]
    if k == "call":
        return call(node[1], node[2], lambda n: ev_node(n, ctx), ctx)
    if k == "idx":
        base = ev_node(node[1], ctx)
        key = ev_node(node[2], ctx)
        return _index(base, key, node[3])
    raise ExprError(f"bad node {node}")


def evaluate_expression(src: str, ctx: Ctx):
    return ev_node(parse(src), ctx)


def _interpolate(s: str, ctx: Ctx):
    out, i = [], 0
    while i < len(s):
        if s.startswith("@@", i):
            out.append("@"); i += 2
        elif s.startswith("@{", i):
            j, depth, inq = i + 2, 1, False
            while j < len(s):
                c = s[j]
                if c == "'":
                    inq = not inq
                elif not inq and c == "{":
                    depth += 1
                elif not inq and c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if depth:
                raise ExprError(f"unterminated @{{ in {s!r}")
            out.append(to_str(evaluate_expression(s[i + 2:j], ctx)))
            i = j + 1
        else:
            out.append(s[i]); i += 1
    return "".join(out)


def evaluate(value, ctx: Ctx):
    """Evaluate a workflow-definition value (string/dict/list/scalar)."""
    if isinstance(value, str):
        if value.startswith("@@"):
            return _interpolate(value, ctx)
        if value.startswith("@") and not value.startswith("@{"):
            return evaluate_expression(value[1:], ctx)
        if "@{" in value or "@@" in value:
            return _interpolate(value, ctx)
        return value
    if isinstance(value, list):
        return [evaluate(x, ctx) for x in value]
    if isinstance(value, dict):
        return {k: evaluate(v, ctx) for k, v in value.items()}
    return value
