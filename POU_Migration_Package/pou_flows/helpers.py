"""Helpers shared by the scheduled reporting / monitoring flows."""
from __future__ import annotations

from .common import L_OPS, L_SETTINGS, cfg, cfgi
from .dsl import Block, Ex, X, and_, cat, coalesce, eq, f, if_, is_null, lit, not_, nz, o, ok, or_, qv, v

TZ_WIN = lambda pfx="": Ex(f"coalesce({cfg('DisplayTimeZoneWindows', pfx)}, 'Central Standard Time')")


def local_fmt(fmt: str, pfx="") -> Ex:
    return Ex(f"convertFromUtc(utcNow(), {TZ_WIN(pfx)}, '{fmt}')")


def tick_gate(blk: Block, hour_key: str, last_key: str, weekly: bool = False, pfx: str = ""):
    """Hourly 'tick' flows run every hour, do almost nothing (a handful of actions) unless the configured local hour has
    arrived and the job has not run today. Schedules therefore live in POUSettings, not in the flow."""
    blk.compose(f"{pfx}Compose_LocalDate", X(local_fmt("yyyy-MM-dd", pfx)))
    blk.compose(f"{pfx}Compose_LocalHour", X(f"int({local_fmt('HH', pfx)})"))
    blk.compose(f"{pfx}Compose_LocalDow", X(f"toLower({local_fmt('dddd', pfx)})"))
    due = and_(f("greaterOrEquals", o(f"{pfx}Compose_LocalHour"), cfgi(hour_key, 7, pfx)),
               not_(eq(coalesce(cfg(last_key, pfx), ""), o(f"{pfx}Compose_LocalDate"))))
    if weekly:
        due = and_(due, eq(o(f"{pfx}Compose_LocalDow"), Ex(f"toLower(coalesce({cfg('WeeklyDayOfWeek', pfx)}, 'monday'))")))
    blk.compose(f"{pfx}Compose_Due", X(due))
    blk.cond(f"{pfx}If_not_due", eq(o(f"{pfx}Compose_Due"), False), lambda t: t.terminate(f"{pfx}Stop_not_due", "Succeeded"))


def save_setting(blk: Block, key: str, value, pfx: str = ""):
    blk.filter_array(f"{pfx}Find_setting_{key}", X(f"body('{pfx}Get_settings')?['d']?['results']"), X(f"equals(item()?['SettingKey'], '{key}')"))
    blk.sp_update(f"{pfx}Save_setting_{key}", L_SETTINGS, X(f"first(body('{pfx}Find_setting_{key}'))?['Id']"), {"SettingValue": value})


def paged(blk: Block, name: str, list_name: str, filter_parts, select: str, var_rows: str, var_next: str, orderby: str | None = None, top: int = 500):
    """Collect EVERY matching row by following __next (no single call is trusted to return the whole set).
    var_rows (array) and var_next (string) must be initialised at the top level of the flow.

    LIST-VIEW THRESHOLD RULE: pass filter_parts=None to enumerate a whole list by ID order (works at any size) and filter in the flow.
    Only pass a server-side filter when it is selective (a few hundred rows, e.g. LowStockFlag eq 1): a filter that matches more than
    5,000 rows is refused by SharePoint even on an indexed column."""
    parts = [f"/_api/web/lists/getbytitle('{list_name}')/items?$top={top}&$select={select}"]
    if orderby:
        parts.append(f"&$orderby={orderby}")
    if filter_parts is not None:
        parts += ["&$filter="] + list(filter_parts)
    blk.set_var(var_rows, [], name=f"{name}_reset_rows")
    blk.set_var(var_next, cat(*parts), name=f"{name}_first_uri")

    def page(p: Block):
        p.sp(f"{name}_page", "GET", X(v(var_next)))
        p.set_var(var_rows, X(f"union(variables('{var_rows}'), coalesce(body('{name}_page')?['d']?['results'], createArray()))"), name=f"{name}_append")
        p.set_var(var_next, X(f"if(empty(coalesce(body('{name}_page')?['d']?['__next'], '')), '', substring(body('{name}_page')?['d']?['__next'], indexOf(body('{name}_page')?['d']?['__next'], '/_api/')))"), name=f"{name}_next")
    blk.until(f"{name}_until", Ex(f"empty(variables('{var_next}'))"), page, count=100, timeout="PT1H")


def ops_event_once(blk: Block, pfx: str, key, etype: str, severity: str, subject, details, new_var: str):
    """Create the event if its key is new (and remember it for the summary email). Existing events are left untouched."""
    def build(s: Block):
        s.sp_get(f"{pfx}_Get_event", L_OPS, ["EventKey eq '", qv(key), "'"], select="Id", top=2)
        s.cond(f"{pfx}_Event_is_new", Ex(f"empty(body('{pfx}_Get_event')?['d']?['results'])"),
               lambda t: (t.sp_create(f"{pfx}_Create_event", L_OPS,
                                      {"Title": subject, "EventKey": key, "EventType": etype, "Severity": severity, "Subject": subject, "Details": details,
                                       "FirstSeenUtc": X("utcNow('yyyy-MM-ddTHH:mm:ssZ')"), "LastSeenUtc": X("utcNow('yyyy-MM-ddTHH:mm:ssZ')"),
                                       "OccurrenceCount": 1, "Resolved": False}),
                          t.add("{}_Remember".format(pfx), {"type": "AppendToArrayVariable", "inputs": {
                              "name": new_var, "value": {"severity": severity, "type": etype, "subject": subject, "details": details}}})))
    return blk.scope(f"{pfx}_Once", build)


def recipients_ok(pfx_key: str, pfx: str = "") -> Ex:
    r = coalesce(cfg(pfx_key, pfx), "")
    return and_(nz(r), not_(f("contains", r, "CHANGE-ME")))


def send_report(blk: Block, name: str, recipients_key: str, subject, body, pfx: str = "", attachments=None, otherwise=None, after_send=None):
    """Send only when recipients are configured (not the CHANGE-ME placeholder); otherwise raise a visible ops event.
    after_send(block) runs only when the mail action succeeded, so a job is marked 'done today' only after it really reported."""
    to = X(f"replace(coalesce({cfg(recipients_key, pfx)}, ''), ',', ';')")

    def send(t: Block):
        t.mail(name, to, subject, body, attachments)
        if after_send:
            t.cond(f"{name}_if_sent", Ex(f"equals(actions('{name}')?['status'], 'Succeeded')"), after_send, always=True)
    blk.cond(f"{name}_if_recipients", recipients_ok(recipients_key, pfx), send, otherwise)
