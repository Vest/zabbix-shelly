#!/usr/bin/env python3
"""Bulk-import the Shelly Zabbix templates via the Zabbix API (7.4).

Imports every template YAML in dependency order (common bases before the device
templates that link them), so linked-template references resolve. Safe to re-run:
uses createMissing + updateExisting, never deleteMissing.

Config comes from a .env file (or real environment variables; env wins):
    ZABBIX_URL    e.g. http://zabbix.example.lan   (/api_jsonrpc.php appended if absent)
    ZABBIX_TOKEN  a Zabbix API token (Users -> API tokens)

Usage:
    python3 import_templates.py               # import all templates, in order
    python3 import_templates.py FILE [FILE..] # import only the given files, in order
    python3 import_templates.py --insecure    # skip TLS verification (self-signed https)
    python3 import_templates.py --dry-run      # list what would be imported, no network

Stdlib only — no pip install required.
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# Dependency-correct order: each common base BEFORE the device templates that link it.
DEFAULT_FILES = [
    "shelly_gen3_common_by_mqtt.yaml",   # MQTT base
    "shelly_pm_mini_gen3_by_mqtt.yaml",
    "shelly_mini_1_gen3_by_mqtt.yaml",
    "shelly_gen3_common_by_http.yaml",   # HTTP base
    "shelly_mini_1_gen3_by_http.yaml",
    "shelly_plus_2pm_by_http.yaml",
    "shelly_plus_2pm_cover_by_http.yaml",
    "shelly_plug_s_gen3_by_http.yaml",
    "shelly_pm_mini_gen3_by_http.yaml",
]

# Safe, re-runnable rules: create new + update changed, never delete.
RULES = {
    "template_groups": {"createMissing": True, "updateExisting": True},
    "templates": {"createMissing": True, "updateExisting": True},
    "items": {"createMissing": True, "updateExisting": True, "deleteMissing": False},
    "triggers": {"createMissing": True, "updateExisting": True, "deleteMissing": False},
    "valueMaps": {"createMissing": True, "updateExisting": True, "deleteMissing": False},
    "templateDashboards": {"createMissing": True, "updateExisting": True, "deleteMissing": False},
}


def load_dotenv(path):
    """Minimal .env parser: KEY=VALUE per line; ignores blanks and # comments.
    Does not override values already present in the real environment."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def api_endpoint(url):
    url = url.rstrip("/")
    if not url.endswith("/api_jsonrpc.php"):
        url += "/api_jsonrpc.php"
    return url


def import_file(endpoint, token, ctx, path, req_id):
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    payload = {
        "jsonrpc": "2.0",
        "method": "configuration.import",
        "params": {"format": "yaml", "source": source, "rules": RULES},
        "id": req_id,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if "error" in body:
        err = body["error"]
        detail = err.get("data") or err.get("message") or str(err)
        raise RuntimeError(detail)
    return body.get("result")


def main():
    ap = argparse.ArgumentParser(description="Bulk-import Shelly Zabbix templates.")
    ap.add_argument("files", nargs="*", help="Template YAML files (default: all, in order).")
    ap.add_argument("--insecure", action="store_true", help="Skip TLS verification (self-signed https).")
    ap.add_argument("--dry-run", action="store_true", help="List files to import; no network calls.")
    args = ap.parse_args()

    load_dotenv(os.path.join(HERE, ".env"))

    files = args.files or DEFAULT_FILES
    # Resolve to absolute paths (relative to the script dir if not absolute).
    resolved = [f if os.path.isabs(f) else os.path.join(HERE, f) for f in files]

    missing = [f for f in resolved if not os.path.exists(f)]
    if missing:
        print("ERROR: file(s) not found:", file=sys.stderr)
        for m in missing:
            print("  " + m, file=sys.stderr)
        return 2

    if args.dry_run:
        print("Would import %d file(s) in this order:" % len(resolved))
        for f in resolved:
            print("  " + os.path.basename(f))
        return 0

    url = os.environ.get("ZABBIX_URL")
    token = os.environ.get("ZABBIX_TOKEN")
    if not url or not token:
        print("ERROR: ZABBIX_URL and ZABBIX_TOKEN must be set (in .env or environment).", file=sys.stderr)
        print("       Copy .env.example to .env and fill it in.", file=sys.stderr)
        return 2

    endpoint = api_endpoint(url)
    ctx = ssl._create_unverified_context() if args.insecure else None

    print("Importing %d template(s) -> %s" % (len(resolved), endpoint))
    failures = 0
    for i, path in enumerate(resolved, start=1):
        name = os.path.basename(path)
        try:
            import_file(endpoint, token, ctx, path, i)
            print("OK    " + name)
        except urllib.error.HTTPError as e:
            failures += 1
            print("FAIL  %s: HTTP %s %s" % (name, e.code, e.reason), file=sys.stderr)
        except urllib.error.URLError as e:
            failures += 1
            print("FAIL  %s: cannot reach %s (%s)" % (name, endpoint, e.reason), file=sys.stderr)
        except Exception as e:  # import error, JSON error, etc.
            failures += 1
            print("FAIL  %s: %s" % (name, e), file=sys.stderr)

    if failures:
        print("\n%d of %d import(s) failed." % (failures, len(resolved)), file=sys.stderr)
        return 1
    print("\nAll %d template(s) imported successfully." % len(resolved))
    return 0


if __name__ == "__main__":
    sys.exit(main())
