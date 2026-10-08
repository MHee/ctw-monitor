"""Vendored from the Claude Science skill `onc-oceans3-api` (October 2026). See vendor/README.md.

Only onc_token, onc_get and onc_ok are kept. Imports are inside functions, so heavy optional packages (none) are only needed
by the functions that use them."""
# ruff: noqa
import os

import re

import json

ONC_BASE = "https://data.oceannetworks.ca"

ONC_API = "https://data.oceannetworks.ca/api"

ONC_CORE_JS = "https://data.oceannetworks.ca/onc-static/static/build/dmasCoreJs.js"

def onc_token(token=None):
    """Resolve the API token from the ONC_API_TOKEN credential. Never print it."""
    if token is None:
        token = os.environ.get("ONC_API_TOKEN")
    if not token:
        raise RuntimeError(
            "No ONC token. Add it as the credential ONC_API_TOKEN "
            "(Customize -> Credentials), or pass token=..."
        )
    return token

def onc_get(path, token=None, timeout=120, **params):
    """GET an official /api endpoint: onc_get('deployments', deviceCategoryCode='BPR')."""
    import requests
    p = dict(params)
    p["token"] = onc_token(token)
    r = requests.get(ONC_API + "/" + path.lstrip("/"), params=p, timeout=timeout)
    if r.status_code != 200:
        try:
            detail = r.json().get("errors", r.text[:300])
        except Exception:
            detail = r.text[:300]
        raise RuntimeError("ONC %s -> HTTP %s: %s" % (path, r.status_code, detail))
    return r.json()

def onc_ok(response):
    """Did an enveloped call succeed? HTTP 200 is NOT enough -- the
    {payload, statusCode} envelope reports failure with a non-zero statusCode."""
    if response.status_code != 200:
        return False
    try:
        j = response.json()
    except Exception:
        return False
    return not (isinstance(j, dict) and j.get("statusCode", 0) != 0)
