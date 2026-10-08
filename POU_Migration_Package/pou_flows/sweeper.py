"""POU-Sweeper (every 5 minutes): the recovery path.

* Re-processes requests whose instant call never arrived (Pending) or whose worker died (Processing with a stale claim).
  It runs the SAME core as POU-ProcessRequest, so a half-finished request is resumed from its ledger intent, never repeated.
* Rejects supervisor-approval requests nobody answered within ApprovalExpiryHours (nothing was changed: NotApplied).
* Costs ~6 actions when idle (probe -> terminate) so it does not burn flow capacity.
"""
from __future__ import annotations

from .common import DEFAULT_SITE_URL, L_REQUESTS, load_settings, preamble
from .core import build_core, init_vars, reset_vars
from .dsl import Ex, Flow, X, f, o, recurrence


def build(site_url: str = DEFAULT_SITE_URL) -> Flow:
    trig = recurrence(minutes=5)
    trig["Recurrence"]["runtimeConfiguration"] = {"concurrency": {"runs": 1}}
    fl = Flow("POU-Sweeper", "POU - Sweeper (recovery)", "Scheduled every 5 minutes: processes Pending / stale-Processing requests with the same core, expires unanswered supervisor approvals.", trig)
    root = preamble(fl, site_url)
    root.sp_get("Probe_open_requests", L_REQUESTS,
                ["RequestStatus eq 'Pending' or RequestStatus eq 'Processing' or RequestStatus eq 'AwaitingSupervisor'"],
                select="Id,RequestID,RequestStatus,Created,ClaimedUtc", top=100)
    root.compose("Compose_Open", X("body('Probe_open_requests')?['d']?['results']"))
    root.cond("If_nothing_open", f("empty", o("Compose_Open")), lambda t: t.terminate("Stop_nothing_to_do", "Succeeded"))
    init_vars(root)
    load_settings(root, "Sw_")
    sw = lambda k, d: Ex(f"int(coalesce(outputs('Sw_Compose_Settings')?['{k}'], '{d}'))")
    it = lambda k: Ex(f"item()?['{k}']")
    age_created = f("sub", f("ticks", f("utcNow")), f("ticks", it("Created")))
    age_claim = f("sub", f("ticks", f("utcNow")), f("ticks", Ex(f"coalesce({it('ClaimedUtc')}, {it('Created')})")))
    # a Pending request gets a 30 s head start for its own instant call; a Processing one is taken over only after the claim timeout
    root.filter_array("Filter_eligible", X(o("Compose_Open")), X(Ex(
        f"or(and(equals({it('RequestStatus')}, 'Pending'), greater({age_created}, 300000000)), "
        f"and(equals({it('RequestStatus')}, 'Processing'), greater({age_claim}, mul({sw('StaleClaimSeconds', 120)}, 10000000))))")))
    root.filter_array("Filter_expired", X(o("Compose_Open")), X(Ex(
        f"and(equals({it('RequestStatus')}, 'AwaitingSupervisor'), greater({age_created}, mul({sw('ApprovalExpiryHours', 24)}, 36000000000)))")))

    def run_core(c):
        c.compose("Compose_RequestIdIn", X("items('For_each_eligible_request')?['RequestID']"))
        reset_vars(c)
        build_core(c)
    root.foreach("For_each_eligible_request", X("body('Filter_eligible')"), run_core, concurrency=1, always=True)

    def expire(e):
        e.sp_update("Expire_request", L_REQUESTS, X("items('For_each_expired_request')?['Id']"),
                    {"RequestStatus": "Rejected", "ResultCode": "EXPIRED",
                     "ResultMessage": "No supervisor approved this in time. Nothing was changed. Please repeat it.",
                     "InventoryEffect": "NotApplied", "IsOpen": False, "ProcessedUtc": X("utcNow('yyyy-MM-ddTHH:mm:ssZ')")},
                    etag=X(Ex("items('For_each_expired_request')?['__metadata']?['etag']")))
    root.foreach("For_each_expired_request", X("body('Filter_expired')"), expire, concurrency=1, always=True)
    return fl
