#!/usr/bin/env python3
"""
Ansible inventory script for OpenShift/Kubernetes pods.

Use with Automation Controller: inventory source Sourced from a Project,
inventory file inventory/openshift_k8s_inventory.py, and an OpenShift or
Kubernetes API Bearer Token credential (sets K8S_AUTH_* env vars).

Uses only Python stdlib (no kubernetes pip package) so inventory sync works on
platform EEs that ship kubernetes.core but do not install the kubernetes client
for arbitrary scripts.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


def _api_base_url() -> str:
    host = os.environ.get("K8S_AUTH_HOST")
    if not host:
        raise SystemExit(
            "K8S_AUTH_HOST is not set. Attach an OpenShift/Kubernetes API Bearer "
            "Token credential to the inventory source."
        )
    host = host.rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host


def _auth_header() -> str:
    token = os.environ.get("K8S_AUTH_API_KEY", "").strip()
    if not token:
        raise SystemExit(
            "K8S_AUTH_API_KEY is not set. Attach an OpenShift/Kubernetes API Bearer "
            "Token credential to the inventory source."
        )
    if not token.startswith("Bearer "):
        token = f"Bearer {token}"
    return token


def _ssl_context() -> ssl.SSLContext:
    verify = os.environ.get("K8S_AUTH_VERIFY_SSL", "yes").lower()
    if verify in ("no", "false", "0"):
        return ssl._create_unverified_context()
    ctx = ssl.create_default_context()
    ca = os.environ.get("K8S_AUTH_SSL_CA_CERT")
    if ca and os.path.isfile(ca):
        ctx.load_verify_locations(cafile=ca)
    return ctx


def _api_get_json(path: str) -> dict:
    base = _api_base_url()
    url = f"{base}{path}" if path.startswith("/") else f"{base}/{path}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": _auth_header(), "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, context=_ssl_context(), timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def list_all_pods() -> list[dict]:
    pods: list[dict] = []
    path = "/api/v1/pods?limit=500"
    while path:
        data = _api_get_json(path)
        pods.extend(data.get("items", []))
        continue_token = data.get("metadata", {}).get("continue")
        if not continue_token:
            break
        path = f"/api/v1/pods?limit=500&continue={urllib.parse.quote(continue_token, safe='')}"
    return pods


def _safe_group_name(namespace: str) -> str:
    return "namespace_" + namespace.replace("-", "_").replace(".", "_")


def build_inventory() -> dict:
    inventory: dict = {"_meta": {"hostvars": {}}, "all": {"children": []}}
    groups: dict[str, dict] = {}

    for pod in list_all_pods():
        meta = pod.get("metadata") or {}
        status = pod.get("status") or {}
        name = meta.get("name", "")
        namespace = meta.get("namespace", "")
        if not name or not namespace:
            continue
        group = _safe_group_name(namespace)
        if group not in groups:
            groups[group] = {"hosts": []}
        groups[group]["hosts"].append(name)
        inventory["_meta"]["hostvars"][name] = {
            "ansible_host": name,
            "k8s_namespace": namespace,
            "k8s_pod_name": name,
            "k8s_pod_phase": status.get("phase", ""),
        }

    inventory.update(groups)
    inventory["all"]["children"] = sorted(groups.keys()) if groups else ["ungrouped"]
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="List all hosts")
    parser.add_argument("--host", help="Get variables for a single host")
    args = parser.parse_args()

    try:
        if args.list or not args.host:
            print(json.dumps(build_inventory(), indent=None))
        else:
            inv = build_inventory()
            hostvars = inv.get("_meta", {}).get("hostvars", {})
            print(json.dumps(hostvars.get(args.host, {}), indent=None))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as exc:
        print(f"openshift_k8s_inventory.py: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
