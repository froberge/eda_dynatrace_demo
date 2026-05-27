#!/usr/bin/env python3
"""
Ansible inventory script for OpenShift/Kubernetes pods.

Use with Automation Controller: inventory source Sourced from a Project,
inventory file inventory/openshift_k8s_inventory.py, and an OpenShift or
Kubernetes API Bearer Token credential (sets K8S_AUTH_* env vars).

Compatible with kubernetes.core 6.x (replaces removed kubernetes.core.k8s plugin).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time


def _agent_log(hypothesis_id: str, message: str, data: dict) -> None:
    # #region agent log
    log_path = os.environ.get("AGENT_DEBUG_LOG_PATH")
    if not log_path:
        return
    try:
        entry = {
            "sessionId": "5606a3",
            "runId": os.environ.get("AGENT_RUN_ID", "inventory"),
            "hypothesisId": hypothesis_id,
            "location": "inventory/openshift_k8s_inventory.py",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    # #endregion


def _configure_k8s_client():
    from kubernetes import client

    configuration = client.Configuration()
    host = os.environ.get("K8S_AUTH_HOST")
    if not host:
        raise SystemExit(
            "K8S_AUTH_HOST is not set. Attach an OpenShift/Kubernetes API Bearer "
            "Token credential to the inventory source."
        )
    configuration.host = host.rstrip("/")

    token = os.environ.get("K8S_AUTH_API_KEY", "")
    if token:
        if not token.startswith("Bearer "):
            token = f"Bearer {token}"
        configuration.api_key = {"authorization": token}

    verify = os.environ.get("K8S_AUTH_VERIFY_SSL", "yes").lower()
    configuration.verify_ssl = verify not in ("no", "false", "0")

    ca = os.environ.get("K8S_AUTH_SSL_CA_CERT")
    if ca and os.path.isfile(ca):
        configuration.ssl_ca_cert = ca

    client.Configuration.set_default(configuration)
    return client.CoreV1Api()


def _safe_group_name(namespace: str) -> str:
    return "namespace_" + namespace.replace("-", "_").replace(".", "_")


def build_inventory() -> dict:
    api = _configure_k8s_client()
    _agent_log("H1", "configured k8s client", {"host_set": bool(os.environ.get("K8S_AUTH_HOST"))})

    inventory: dict = {"_meta": {"hostvars": {}}, "all": {"children": []}}
    groups: dict[str, dict] = {}
    pod_count = 0

    for pod in api.list_pod_for_all_namespaces().items:
        pod_count += 1
        name = pod.metadata.name
        namespace = pod.metadata.namespace
        group = _safe_group_name(namespace)
        if group not in groups:
            groups[group] = {"hosts": []}
        groups[group]["hosts"].append(name)
        inventory["_meta"]["hostvars"][name] = {
            "ansible_host": name,
            "k8s_namespace": namespace,
            "k8s_pod_name": name,
            "k8s_pod_phase": (pod.status.phase or ""),
        }

    inventory.update(groups)
    inventory["all"]["children"] = sorted(groups.keys()) if groups else ["ungrouped"]
    _agent_log("H3", "inventory built", {"pod_count": pod_count, "group_count": len(groups)})
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
    except Exception as exc:  # noqa: BLE001 - inventory scripts must exit non-zero on failure
        _agent_log("H2", "inventory script failed", {"error_type": type(exc).__name__, "error": str(exc)[:300]})
        print(json.dumps({"_meta": {"hostvars": {}}, "all": {"children": ["ungrouped"]}}))
        print(f"openshift_k8s_inventory.py: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
