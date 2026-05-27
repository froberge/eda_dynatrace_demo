# Automation Controller workflow

EDA receives Dynatrace events and launches a **Workflow Job Template** on Automation Controller. The workflow runs the remediation playbook with credentials, inventory, and execution environment managed by Controller—not by the EDA decision environment.

## Flow

```text
Dynatrace Workflow → AAP Event Stream → EDA rulebook
    → run_workflow_template → Workflow Job Template
        → Job Template → playbooks/remediate_k8s_pod.yml
```

## 1. Controller project

1. **Automation Controller** → **Projects** → **Create**.
2. Source: same Git repo as the EDA project.
3. **Playbook directory:** leave default (repo root).
4. Sync and confirm `playbooks/remediate_k8s_pod.yml` is present.

## 2. Execution environment (Controller)

Build or select an EE that includes:

- `kubernetes.core`
- `servicenow.itsm`

See [`collections/requirements.yml`](../collections/requirements.yml) and [build-decision-environment.md](build-decision-environment.md) (build from [`execution-environment.yml`](../execution-environment.yml)).

The EDA decision environment only needs `ansible.eda` for the rulebook; **job execution** uses this Controller EE.

## 3. Inventory and credential

### OpenShift API access (recommended)

Create a ServiceAccount on the cluster and an AAP Bearer token credential. Full steps: **[aap-openshift-inventory.md](aap-openshift-inventory.md)**.

```bash
oc apply -f k8s/rbac/openshift_aap_sa.yaml
oc create token aap-inventory -n aap --duration=8760h
```

Use that token in an **OpenShift or Kubernetes API Bearer Token** credential in Controller, then:

1. **(Optional)** Inventory `OpenShift Demo` → source **Sourced from a Project** → `inventory/openshift_k8s_inventory.py` — see [aap-openshift-inventory.md](aap-openshift-inventory.md). Do **not** use **OpenShift Virtualization** (VMs only).
2. Attach the **same credential** to job template `EDA - Remediate K8s Pod` (required).

The remediation playbook runs on **`localhost`** and calls the API via `kubernetes.core`. Dynamic inventory is for cluster assessment; EDA remediation does not require inventory sync.

### Controller objects

| Object | Settings |
|--------|----------|
| **Inventory (remediation / EDA)** | `EDA Localhost` — single host `localhost` |
| **Inventory (optional assessment)** | `OpenShift Demo` — **Sourced from a Project**, file `inventory/openshift_k8s_inventory.py` |
| **Credential (OpenShift/Kubernetes)** | Bearer token from `aap-inventory` ServiceAccount — inventory source (if used) + job template |
| **Credential (ServiceNow)** | ServiceNow or custom type — attach to job template, or use `SN_*` injected via credential |

## 4. Job template

**Name:** `EDA - Remediate K8s Pod` (must match the workflow node)

| Field | Value |
|-------|--------|
| Inventory | `EDA Localhost` |
| Project | This repository |
| Playbook | `playbooks/remediate_k8s_pod.yml` |
| Execution environment | Controller EE with `kubernetes.core` + `servicenow.itsm` |
| Credentials | **OpenShift or Kubernetes API Bearer Token** (required) |
| **Prompt on launch → Extra Variables** | **Enabled** (required for EDA `run_workflow_template`) |
| **Prompt on launch → Credentials** | **Enabled** if workflow jobs fail with `system:anonymous` |

Optional: add a **Survey** with fields `namespace`, `pod_name`, `incident_number`, `problem_id`, `pod_label_selector` for manual runs. EDA passes the same keys via `job_args.extra_vars`.

## 5. Workflow job template

**Name:** `EDA - Dynatrace K8s Remediation` (must match [`vars/aap_controller.yml.example`](../vars/aap_controller.yml.example))

1. **Automation Controller** → **Templates** → **Workflow Templates** → **Create**.
2. Add a single node: **Job Template** → `EDA - Remediate K8s Pod`.
3. **Prompt on launch → Extra Variables:** **Enabled** on the workflow template.
4. Save.

You can extend the workflow later (approval step, notification job, second job for audit-only) without changing the rulebook contract.

## 6. EDA rulebook activation variables

On the rulebook activation, set **Variables** (example from [`vars/aap_controller.yml.example`](../vars/aap_controller.yml.example)):

```yaml
remediation_workflow_job_template: "EDA - Dynatrace K8s Remediation"
controller_organization: "Default"
```

The rulebook references these names in `run_workflow_template`.

Ensure the activation is linked to your **Automation Controller** instance (EDA settings / organization default).

## 7. Extra variables passed from events

EDA sends these to the workflow launch API:

| Variable | Source |
|----------|--------|
| `namespace` | `event.payload.namespace` |
| `pod_name` | `event.payload.pod_name` |
| `incident_number` | `event.payload.incident_number` |
| `problem_id` | `event.payload.problem_id` |
| `severity` | `event.payload.severity` |
| `pod_label_selector` | `event.payload.pod_label_selector` |

The engine also injects `ansible_eda` (event metadata). **Prompt on launch** for extra variables on the workflow template is required so these values are accepted.

## 8. Verify

1. Run the workflow manually from Controller with survey/extra vars from [`samples/dynatrace_eda_event.json`](../samples/dynatrace_eda_event.json).
2. POST a test event: [`samples/curl_post_event.sh`](../samples/curl_post_event.sh).
3. Confirm **Workflow Jobs** shows a successful run and pod/incident outcomes match expectations.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Variables ansible_eda are not allowed on launch` | Enable **Prompt on launch** for Extra Variables on the **workflow** template |
| Workflow runs but extra vars empty | Enable prompt on launch on the **job** template; check activation variable names |
| `run_workflow_template` cannot find template | `remediation_workflow_job_template` matches workflow name and `controller_organization` |
| `system:anonymous` / cannot get `/apis` | Attach **OpenShift or Kubernetes API Bearer Token** to the **job template** (not only inventory); enable credential prompt on workflow if needed |
| K8s Forbidden / RBAC | Same credential; SA token and ClusterRole in [aap-openshift-inventory.md](aap-openshift-inventory.md) |
| Inventory sync Forbidden | ServiceAccount token and ClusterRole in `k8s/rbac/openshift_aap_sa.yaml` |
| Wrong hosts / VM-only inventory | Use **Sourced from a Project** + `inventory/openshift_k8s_inventory.py`, not OpenShift Virtualization |
| `k8s inventory plugin has been removed` | Inventory file must be `.py` script, not YAML `plugin: kubernetes.core.k8s` (EE has kubernetes.core 6.x) |
| Inventory sync OK but job fails | Remediation uses **EDA Localhost** + credential on job template, not pod SSH hosts |

## References

- [ansible-rulebook: run_workflow_template](https://docs.ansible.com/projects/rulebook/en/latest/actions.html)
- [EDA setup (Event Stream)](aap-setup.md)
