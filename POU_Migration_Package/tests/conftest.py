import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pou_tools.fakesp import FakeSharePoint, serve          # noqa: E402
from pou_tools.provision import provision                  # noqa: E402
from pou_tools.schema import load_permissions, load_schema  # noqa: E402
from pou_tools.spclient import SpClient                    # noqa: E402

SITE_OWNER = "owner@test"


def mk_fake():
    f = FakeSharePoint()
    f.make_site_admin(SITE_OWNER)
    f.add_member("Site Owners", SITE_OWNER)
    return f


def client_for(fake, upn, base_url, sleep=lambda s: None):
    return SpClient(base_url, lambda: f"fake:{upn}", sleep=sleep)


@pytest.fixture
def schema():
    return load_schema()


@pytest.fixture
def perms():
    return load_permissions()


@pytest.fixture
def fake_http():
    f = mk_fake()
    srv, url = serve(f)
    yield f, url
    srv.shutdown()


@pytest.fixture
def provisioned(fake_http, schema, perms):
    """A fully provisioned fake site with one user in each group (served over real HTTP)."""
    f, url = fake_http
    admin = client_for(f, SITE_OWNER, url)
    provision(admin, schema, perms, apply=True, log=lambda *a: None)
    f.add_member("POU Operators", "station1@test")
    f.add_member("POU Operators", "station2@test")
    f.add_member("POU Supervisors", "sup@test")
    f.add_member("POU Admins", "admin@test")
    f.add_member("POU Flow Service", "svc@test")
    return f, url
