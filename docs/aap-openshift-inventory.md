# OpenShift inventory and ServiceAccount for AAP

Connect an OpenShift cluster to **Automation Controller** using a dedicated **ServiceAccount** and an **OpenShift / Kubernetes API Bearer Token** credential. Use the same credential for:

- **Inventory source** — discover namespaces and pods (project-sourced [`inventory/openshift_k8s_inventory.py`](../inventory/openshift_k8s_inventory.py) script; works with `kubernetes.core` 6.x)
- **Job template** — `kubernetes.core` API calls in [`playbooks/remediate_k8s_pod.yml`](../playbooks/remediate_k8s_pod.yml) (runs on `localhost` inventory; API auth via credential)

## Architecture

```text
OpenShift cluster
  └── ServiceAccount aap-inventory (namespace aap)
        └── ClusterRole aap-inventory-demo (demo: read + pod delete cluster-wide)
              └── token → AAP Credential
                    ├── Inventory → Sourced from a Project (inventory/openshift_k8s_inventory.py) → Sync
                    └── Job template EDA - Remediate K8s Pod (EDA Localhost + same credential)
```

## AAP 2.6: no built-in “OpenShift cluster” source

Automation Controller does **not** ship a built-in inventory source that lists **container pods** on a general OpenShift/Kubernetes cluster. The OpenShift-related built-in source is **OpenShift Virtualization**, which syncs **KubeVirt VMs**—not Deployment pods such as `demo-app` in `eda-demo`.

| Source in UI | Use for this demo? |
|--------------|-------------------|
| **OpenShift Virtualization** | **No** — VMs only |
| **Sourced from a Project** | **Yes** — use [`inventory/openshift_k8s_inventory.py`](../inventory/openshift_k8s_inventory.py) (not the removed `kubernetes.core.k8s` YAML plugin) |
| *(no inventory sync)* | **Yes** for EDA-only — `EDA Localhost` + credential on the job template is enough for remediation |

## 1. Apply RBAC on OpenShift

Requires cluster-admin (or equivalent) once.

```bash
oc apply -f k8s/rbac/openshift_aap_sa.yaml
```

Verify permissions for the ServiceAccount:

```bash
oc auth can-i list pods --all-namespaces \
  --as=system:serviceaccount:aap:aap-inventory

oc auth can-i delete pods --all-namespaces \
  --as=system:serviceaccount:aap:aap-inventory
```

Both should return `yes` for this demo role.

## 2. Create an API token

OpenShift 4.x (short-lived token; adjust duration for your policy. Currently the token will be good for 1 year):

```bash
oc create token aap-inventory -n aap --duration=8760h
```

Copy the token immediately and store it in AAP only (never commit to Git).

## 3. Gather API endpoint and CA

**API server URL** (OpenShift API endpoint for the credential):

```bash
oc whoami --show-server
```

Example: `https://api.cluster.example.com:6443`

**CA certificate** (for TLS verify in AAP):

```bash
oc get configmap kube-root-ca.crt -n aap \
  -o jsonpath='{.data.ca\.crt}' > openshift-ca.crt
```

## 4. Create credential in Automation Controller

1. **Automation Execution** → **Credentials** → **Create credential**
2. **Credential type:** **OpenShift or Kubernetes API Bearer Token**
3. Fields (labels vary slightly by AAP version):

| Field | Value |
|-------|--------|
| OpenShift API Endpoint / Host | Output of `oc whoami --show-server` (no trailing slash) |
| API Bearer Token | Token from step 2 |
| SSL certificate / CA | Contents of `openshift-ca.crt`, or disable verify for lab only |

4. Save (for example name: `OpenShift Demo API`).

## 5. Create inventory and source (Sourced from a Project)

1. **Inventories** → **Create inventory** (for example `OpenShift Demo`).
2. Open the inventory → **Sources** → **Add**.
3. **Source:** **Sourced from a Project** (not OpenShift Virtualization).
4. **Project:** the same Git project as this repository (Controller must sync the project first).
5. **Inventory file:** `inventory/openshift_k8s_inventory.py`
6. **Credential:** `OpenShift Demo API` from step 4.
7. **Execution environment:** Controller EE that includes `kubernetes.core` (same EE as the remediation job template).
8. **Save** and run **Sync**.

The inventory file is an **executable Python script** that lists pods in all namespaces the ServiceAccount can `list`. It replaces the removed [`kubernetes.core.k8s`](https://docs.ansible.com/ansible/latest/collections/kubernetes/core/k8s_inventory.html) inventory plugin (removed in collection 6.0.0). AAP must be able to execute the script (default for project-sourced inventory).

**Do not** use `inventory/openshift_k8s_inventory.yml` with `plugin: kubernetes.core.k8s` on Execution Environments that ship `kubernetes.core` 6.x—you will see `k8s inventory plugin has been removed`.

After sync, expect groups such as `namespace_*` with pod hosts listed underneath (exact group names depend on collection version).

**After you push a new or renamed inventory file:** **Projects** → your repo → **Sync**, then update the inventory source **Inventory file** path if it changed, and run **Sync** on the inventory source again.

### EDA-only shortcut

If you only need Dynatrace → EDA → pod restart, you can **skip** inventory sync entirely. Create the credential, attach it to job template **EDA - Remediate K8s Pod**, and use inventory **`EDA Localhost`**.

## 6. Attach credential to the remediation job template

The demo playbook uses `hosts: localhost` and `kubernetes.core` modules. Pod delete/restart uses the **API**, not SSH to inventory hosts.

On job template **EDA - Remediate K8s Pod** ([aap-controller-workflow.md](aap-controller-workflow.md)):

| Field | Recommendation |
|-------|----------------|
| Inventory | **`EDA Localhost`** (required for EDA and API-based remediation) |
| Credentials | OpenShift Demo API + ServiceNow |

Do **not** point the remediation job at `OpenShift Demo` inventory hosts expecting a normal `ping` or `command` module to reach pods—pods are not SSH targets unless you add a container connection plugin.

## 7. Verify end-to-end

1. **Inventory sync:** job log shows `openshift_k8s_inventory.py` completing; hosts appear under `namespace_*` groups.
2. Deploy the demo app: [k8s/README.md](../k8s/README.md)
3. Run job template manually with extra vars from [`samples/dynatrace_eda_event.json`](../samples/dynatrace_eda_event.json)
4. Or POST a test event: [`samples/curl_post_event.sh`](../samples/curl_post_event.sh)
5. Confirm pod is recreated and ServiceNow incident closes (if configured)

## Production hardening

The demo [`ClusterRole`](../k8s/rbac/openshift_aap_sa.yaml) grants **cluster-wide pod delete**. For production:

- Use one **read-only** ServiceAccount for inventory sync only
- Use a separate ServiceAccount with `Role` / `RoleBinding` per allowed namespace for remediation
- Avoid storing long-lived tokens in AAP when your platform supports short-lived credentials and rotation

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Inventory file missing in AAP UI | File must exist on the Git branch the **Project** syncs (commit and push), then **Project → Sync** before setting the inventory source path |
| Inventory sync fails with Forbidden | `oc auth can-i` tests; credential on inventory source; SA RBAC |
| `k8s inventory plugin has been removed` | Use **`inventory/openshift_k8s_inventory.py`** (script), not `.yml` with `plugin: kubernetes.core.k8s` |
| Sync uses wrong plugin / no hosts | Source is **Sourced from a Project**, file `inventory/openshift_k8s_inventory.py`; not OpenShift Virtualization |
| Job cannot delete pod | Same credential on **job template** (not only on inventory source) |
| TLS errors | CA file matches cluster; API URL has no trailing slash; or lab-only disable SSL verify |
| Empty inventory after sync | SA can `list pods` cluster-wide; credential attached to inventory source; re-sync after project update |

## Related docs

- [aap-controller-workflow.md](aap-controller-workflow.md) — job and workflow templates
- [aap-setup.md](aap-setup.md) — EDA Event Stream and rulebook activation
- [k8s/README.md](../k8s/README.md) — demo workload in `eda-demo`
