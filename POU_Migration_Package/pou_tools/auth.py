"""Authentication helpers. No secrets are stored in this package.

Default is interactive device-code sign-in with MSAL against a PUBLIC client app registration that the
tenant admin creates (no client secret exists). Tokens live only in memory unless --token-cache is given.
"""
from __future__ import annotations

import os
import sys
from typing import Callable


def device_code_provider(tenant: str, client_id: str, site_url: str, cache_path: str | None = None) -> Callable[[], str]:
    import msal
    from urllib.parse import urlparse
    host = urlparse(site_url).netloc
    scopes = [f"https://{host}/.default"]
    cache = msal.SerializableTokenCache()
    if cache_path and os.path.exists(cache_path):
        cache.deserialize(open(cache_path, encoding="utf-8").read())
    app = msal.PublicClientApplication(client_id, authority=f"https://login.microsoftonline.com/{tenant}", token_cache=cache)

    def provider() -> str:
        accts = app.get_accounts()
        res = app.acquire_token_silent(scopes, account=accts[0]) if accts else None
        if not res:
            flow = app.initiate_device_flow(scopes=scopes)
            if "user_code" not in flow:
                raise RuntimeError(f"Device flow failed: {flow}")
            print(flow["message"], file=sys.stderr)
            res = app.acquire_token_by_device_flow(flow)
        if "access_token" not in res:
            raise RuntimeError(f"Sign-in failed: {res.get('error')}: {res.get('error_description')}")
        if cache_path and cache.has_state_changed:
            open(cache_path, "w", encoding="utf-8").write(cache.serialize())
        return res["access_token"]
    return provider


def env_token_provider(var: str = "POU_SP_TOKEN") -> Callable[[], str]:
    def provider() -> str:
        t = os.environ.get(var)
        if not t:
            raise RuntimeError(f"Environment variable {var} is not set")
        return t
    return provider


def make_provider(args) -> Callable[[], str]:
    if getattr(args, "auth", "device") == "env":
        return env_token_provider()
    if getattr(args, "auth", "device") == "fake":
        return lambda: f"fake:{args.fake_user}"
    if not args.tenant or not args.client_id:
        raise SystemExit("--tenant and --client-id are required for interactive sign-in (see docs/07_Deployment.md, step 'App registration').")
    return device_code_provider(args.tenant, args.client_id, args.site_url, getattr(args, "token_cache", None))
