"""Measures how many Power Automate ACTIONS (and SharePoint calls) each path costs, from the generated flow definitions.

Why it matters: Power Platform request limits are counted per action, per licence of the flow owner. docs/05_Platform_Facts_and_Capacity.md
uses these numbers. The budgets below fail the build if a change makes a path noticeably more expensive.
Run with POU_WRITE_CAPACITY=1 to refresh docs/generated/capacity.json."""
import json
import os
from pathlib import Path

from conftest import SITE_OWNER
from test_flow_basic import env, opening   # noqa: F401


def calls(rt):
    return len(rt.sp.log) if hasattr(rt.sp, "log") else None


def test_measure_and_budget(env):
    out = {}
    calls_ = {}
    mark = [env.fake.request_count]

    def took(name):
        calls_[name] = env.fake.request_count - mark[0]
        mark[0] = env.fake.request_count
    rt = env.sweep()
    out["sweeper_idle"] = rt.action_count
    took("sweeper_idle")
    sess_rt = env.run(env.flows["session"], ["LOGIN", "1001", "CAB-01", "", "station1@test"])
    out["login"] = sess_rt.action_count
    took("login")
    sid = sess_rt.response["body"]["sessionId"]
    _, o_rt = opening(env)
    out["opening"] = o_rt.action_count
    took("opening_incl_request_create")
    r1 = env.new_request("station1@test", RequestType="ISSUE", SessionID=sid, StationID="CAB-01", StockKey="A|1-A", ItemID="A", LocationCode="1-A", Quantity=1)
    mark[0] = env.fake.request_count
    out["issue"] = env.process(r1).action_count
    took("issue")
    r2 = env.new_request("station1@test", RequestType="RECEIPT", SessionID=sid, StationID="CAB-01", StockKey="A|1-A", ItemID="A", LocationCode="1-A", Quantity=1)
    mark[0] = env.fake.request_count
    out["receipt"] = env.process(r2).action_count
    took("receipt")
    mark[0] = env.fake.request_count
    out["logout"] = env.run(env.flows["session"], ["LOGOUT", "", "CAB-01", sid, "station1@test"]).action_count
    took("logout")
    env.clock.advance(15 * 3600)         # 05:00 UTC the next day = none of the scheduled jobs is due
    for name in ("monitor", "lowstock", "reconcile", "health", "usage"):
        out[f"{name}_tick_not_due"] = env.job(name).action_count
    env.clock.advance(14 * 3600)         # 19:00 UTC: a sample of a busy/due tick
    out["lowstock_tick_when_due_or_busy"] = env.job("lowstock").action_count
    out["sharepoint_calls"] = calls_
    out["definition_action_totals"] = {k: len(json.dumps(f.definition())) for k, f in env.flows.items()}
    print(json.dumps(out, indent=1))
    assert out["issue"] <= 140 and out["receipt"] <= 140, out
    assert out["login"] <= 60, out
    assert out["sweeper_idle"] <= 12, out
    assert all(out[f"{n}_tick_not_due"] <= 15 for n in ("monitor", "lowstock", "reconcile", "health", "usage")), out
    if os.environ.get("POU_WRITE_CAPACITY"):
        p = Path(__file__).resolve().parent.parent / "docs" / "generated"
        p.mkdir(parents=True, exist_ok=True)
        (p / "capacity.json").write_text(json.dumps(out, indent=1))
