"""PERMISSION AUDIT: run it signed in AS a test account of each kind and compare what SharePoint says that account can do with the matrix.

  python -m pou_tools.permission_audit --site-url https://TENANT.sharepoint.com/sites/POU --tenant ... --client-id ... --as operators
  (repeat signed in as a supervisor with --as supervisors, an admin with --as admins, the flow service account with --as flowservice)

It asks SharePoint for EffectiveBasePermissions on every POU list: read-only, changes nothing. This is the test that UI hiding is not access control:
what is printed is what the account can really do, whatever the app shows.
Exit code 0 only if every list matches the matrix for the chosen group.
"""
from __future__ import annotations

import argparse
import sys

from . import masks
from .auth import make_provider
from .schema import load_permissions, load_schema
from .spclient import SpClient, SpError

ROLE_BITS = {  # role key -> (read, add, edit, delete)
    None: (False, False, False, False), "read": (True, False, False, False), "addonly": (True, True, False, False),
    "flowwriter": (True, True, True, False), "contribute": (True, True, True, True),
}


def expected_for(perms: dict, group: str, list_name: str):
    return ROLE_BITS[perms["matrix"][list_name][group]]


def audit(client: SpClient, perms: dict, group: str) -> list[dict]:
    out = []
    for ln in perms["matrix"]:
        try:
            m = client.effective_permissions(ln)
        except SpError as e:
            if not (e.is_forbidden or e.status == 404):
                raise
            m = 0
        got = tuple(bool(m & masks.FLAGS[f]) for f in ("ViewListItems", "AddListItems", "EditListItems", "DeleteListItems"))
        want = expected_for(perms, group, ln)
        out.append({"list": ln, "expected": want, "actual": got, "ok": got == want})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-url", required=True)
    ap.add_argument("--tenant"); ap.add_argument("--client-id")
    ap.add_argument("--auth", choices=["device", "env", "fake"], default="device")
    ap.add_argument("--fake-user", default="owner@test")
    ap.add_argument("--token-cache")
    ap.add_argument("--as", dest="group", required=True, choices=["operators", "supervisors", "admins", "flowservice"])
    a = ap.parse_args(argv)
    c = SpClient(a.site_url, make_provider(a))
    me = c.current_user()
    print(f"signed in as {me.get('Email') or me.get('LoginName')}; expecting the permissions of '{a.group}'\n")
    res = audit(c, load_permissions(), a.group)
    fmt = lambda t: "".join(ch if b else "-" for ch, b in zip("RAED", t))
    for r in res:
        print(f"[{'OK ' if r['ok'] else 'BAD'}] {r['list']:20} expected {fmt(r['expected'])}  actual {fmt(r['actual'])}")
    bad = [r for r in res if not r["ok"]]
    print(f"\n{len(res) - len(bad)} match, {len(bad)} differ.")
    if any(a.group != "admins" and r["actual"][3] for r in res):
        print("NOTE: delete rights are present somewhere they should not be; the account may also be in the Site Owners group (Full Control).")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
