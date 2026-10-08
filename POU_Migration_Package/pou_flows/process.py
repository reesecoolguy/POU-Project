"""POU-ProcessRequest: instant flow called by the app (and by supervisors' console) with a RequestID."""
from __future__ import annotations

from .common import DEFAULT_SITE_URL, SCHEMA_RESPONSE, preamble
from .core import build_core, init_vars
from .dsl import ALL, Ex, Flow, X, o, powerapps_trigger, trig_input, v


def response_body(rid_expr) -> dict:
    g = lambda k: X(f"variables('vRes')?['{k}']")
    return {"status": g("status"), "code": g("code"), "message": g("message"), "ledgerKey": g("ledger"),
            "effect": g("effect"), "newOnHand": g("newOnHand"), "requestId": X(rid_expr)}


def build(site_url: str = DEFAULT_SITE_URL) -> Flow:
    fl = Flow("POU-ProcessRequest", "POU - Process Request",
              "Instant flow called by the app with a RequestID. Claims the request, validates session/identity/permissions on the server, "
              "creates the ledger intent (unique-key compare-and-swap), applies the stock change, marks it Posted, and answers with the real outcome.",
              powerapps_trigger([("RequestID", "The request GUID created by the app")]))
    root = preamble(fl, site_url)
    init_vars(root)
    root.compose("Compose_RequestIdIn", X("trim(string(coalesce(" + str(trig_input(0)) + ", '')))"))
    root.scope("Core", build_core)
    root.respond("Respond", response_body(o("Compose_RequestIdIn")), SCHEMA_RESPONSE, after={"Core": list(ALL)})
    return fl
