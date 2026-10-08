"""Test harness: runs the GENERATED flow definitions (flowlab) against the SharePoint model."""
from __future__ import annotations

import base64
import random
import threading
import uuid

from flowlab.connectors import FaultPlan, MailBackend, SpBackend
from flowlab.runtime import Clock, FlowKilled, Runtime
from pou_flows import process, session

SITE = "https://fake.sharepoint.com/sites/POU"
SVC = "svc@test"


class Env:
    """A provisioned fake site plus flow runner. Clients use the in-process fake (no HTTP) for speed."""

    def __init__(self, fake, url, clients):
        self.fake, self.url = fake, url
        self.clock = Clock()
        fake.clock = self.clock
        self.mail = MailBackend()
        self.flows = {"process": process.build(SITE), "session": session.build(SITE)}
        self.clients = clients      # callable upn -> SpClient
        self.rng = random.Random(12345)   # ONE shared generator so guid() is unique across runs, as in production

    def c(self, upn):
        return self.clients(upn)

    def run(self, flow, inputs, caller="station1@test", plan=None, clock=None, header=True, svc=SVC, rng=None, mail=None):
        d = flow.definition() if hasattr(flow, "definition") else flow
        trig = {("text" if i == 0 else f"text_{i}"): x for i, x in enumerate(inputs)}
        hdr = {"x-ms-user-email-encoded": base64.b64encode(caller.encode()).decode()} if header else {}
        sp = SpBackend(self.fake, svc, plan)
        rt = Runtime(d, trigger_body=trig, trigger_headers=hdr,
                     connectors={"shared_sharepointonline": sp, "shared_office365": mail or self.mail},
                     clock=clock or self.clock, rng=rng or self.rng)
        try:
            rt.run()
        except FlowKilled as k:
            rt.status = "Killed"
            rt.killed = str(k)
        rt.sp = sp
        return rt

    # -------- conveniences
    def login(self, badge="1001", station="CAB-01", caller="station1@test", **kw):
        rt = self.run(self.flows["session"], ["LOGIN", badge, station, "", caller], caller=caller, **kw)
        return rt.response["body"] if rt.response else None

    def new_request(self, caller, **fields):
        rid = fields.pop("RequestID", str(uuid.uuid4()))
        body = {"Title": rid, "RequestID": rid, **fields}
        self.c(caller).create_item("POURequests", body)
        return rid

    def process(self, rid, caller="station1@test", **kw):
        rt = self.run(self.flows["process"], [rid], caller=caller, **kw)
        return rt

    def req(self, rid):
        return self.c("owner@test").get_by_key("POURequests", "RequestID", rid)

    def stock(self, key):
        return self.c("owner@test").get_by_key("POUStockLocations", "StockKey", key)

    def ledger(self, key=None, **flt):
        q = f"StockKey eq '{key}'" if key else None
        return list(self.c("owner@test").query("POULedger", q, top=500))
