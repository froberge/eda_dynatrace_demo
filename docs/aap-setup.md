# Ansible Automation Platform setup

Configure AAP 2.6+ Event-Driven Ansible (EDA) to receive Dynatrace workflow events and launch remediation on **Automation Controller** via a **Workflow Job Template**.

**Controller workflow setup (job template, workflow template, credentials):** [aap-controller-workflow.md](aap-controller-workflow.md)

## Prerequisites

- Ansible Automation Platform 2.6 or newer with EDA enabled
- Git access to this repository
- Kubernetes API access from the decision environment execution context
- ServiceNow credentials for incident closure

## 1. Install collections in the decision environment

Use the platform default decision environment (`ansible-rulebook` image) or build a custom environment from [`execution-environment.yml`](../execution-environment.yml).

**Build and push commands:** [build-decision-environment.md](build-decision-environment.md)

Collections required (see [`collections/requirements.yml`](../collections/requirements.yml)):

- `ansible.eda`
- `kubernetes.core`
- `servicenow.itsm`

## 2. Create the project

1. In AAP, go to **Automation Decisions** (or EDA) **Projects**.
2. Create a project pointing at this Git repository.
3. Sync the project and confirm `rulebooks/k8s_pod_remediation.yml` and `playbooks/` are present.

## 3. Token Event Stream credential

1. Go to **Automation Decisions** > **Infrastructure** > **Credentials**.
2. **Create credential**:
   - **Credential type:** `Token Event Stream`
   - **Token:** generate a strong random token (save for Dynatrace)
   - **HTTP Header Key:** `Authorization`

## 4. Event stream

1. Go to **Automation Decisions** > **Event streams**.
2. **Create event stream**:
   - **Event stream type:** `Token Event Stream`
   - **Credential:** the credential from step 3
3. Copy the **POST URL** (format):

   `https://<aap-host>/eda-event-streams/api/eda/v1/external_event_stream/<uuid>/post`

4. Turn off **Test mode** when running the live demo (events in test mode do not reach activations).

## 5. Automation Controller workflow

Create the job template and workflow job template before enabling the rulebook activation. See **[aap-controller-workflow.md](aap-controller-workflow.md)** for:

- Job template `EDA - Remediate K8s Pod` → `playbooks/remediate_k8s_pod.yml`
- Workflow job template `EDA - Dynatrace K8s Remediation`
- **Prompt on launch** for extra variables (required)
- Kubernetes and ServiceNow credentials on the job template

## 6. Rulebook activation

1. Go to **Rulebook activations** > **Create**.
2. Select the synced project and rulebook `k8s_pod_remediation.yml`.
3. Choose a decision environment with the required collections (`ansible.eda` at minimum).
4. **Map the event stream** to the rulebook source:
   - Open source mapping (gear icon).
   - Select source **`dynatrace_events`** (defined in the rulebook).
   - Attach the Token Event Stream from step 4.
5. Set activation **Variables** (must match your Controller workflow; see [`vars/aap_controller.yml.example`](../vars/aap_controller.yml.example)):

   ```yaml
   remediation_workflow_job_template: "EDA - Dynatrace K8s Remediation"
   controller_organization: "Default"
   ```

   The rulebook uses these names in `run_workflow_template`. If your workflow template has a different name, change the variable here—do not edit the rulebook unless you prefer a hardcoded name.

6. Link the activation to your Automation Controller instance (per your AAP deployment).
7. Enable the activation.

The rulebook declares `ansible.eda.event_stream` on source `dynatrace_events`. At runtime, AAP still delivers events to the activation via **`eda.builtin.pg_listener`** (Postgres `LISTEN/NOTIFY`) after you map the Token Event Stream. Rules and actions are unchanged; matched events call `run_workflow_template` with `namespace`, `pod_name`, and `incident_number` from the event payload (see [aap-controller-workflow.md](aap-controller-workflow.md)).

## 7. Verify with a test event

```bash
export EVENT_STREAM_URL="https://<aap-host>/eda-event-streams/api/eda/v1/external_event_stream/<uuid>/post"
export EVENT_STREAM_TOKEN="<your-token>"
chmod +x samples/curl_post_event.sh
./samples/curl_post_event.sh
```

Check **Rule audit** / activation logs for a matched rule and a **Workflow Job** in Automation Controller.

## 8. Dynatrace connection

Use the Event Stream POST URL and token in the Dynatrace **Red Hat Event-Driven Ansible** connection with **Event stream** enabled. See [dynatrace-workflow.md](dynatrace-workflow.md).

## Troubleshooting

### Activation fails: `pg_listener` / `password authentication failed for user "eda"`

When you **map a Token Event Stream** to source `dynatrace_events` (step 6), the activation runs **`eda.builtin.pg_listener`** to read events from **EDA PostgreSQL** (`LISTEN/NOTIFY`). HTTP POSTs to the public Event Stream URL are handled by EDA services first; the activation pod connects to Postgres (for example `10.130.2.9:5432`), not to the Event Stream URL directly.

| Symptom in logs | Meaning |
|-----------------|--------|
| `Shutting down source: eda.builtin.pg_listener` | Event Stream mapping is active (expected) |
| `password authentication failed for user "eda"` | Activation job pod cannot authenticate to EDA Postgres |
| `system:anonymous` on Controller jobs | Separate issue: missing OpenShift credential on **job template** |

This is an **AAP / EDA platform** credential issue, not a bug in `rulebooks/k8s_pod_remediation.yml`.

**Checks (cluster admin / platform team):**

1. Compare DB env vars on the **activation worker** vs the failing **activation-job** pod:
   ```bash
   oc exec -n <eda-namespace> deploy/eda-server-activation-worker -- env | grep -E '^EDA_.*DB'
   oc exec -n <eda-namespace> <activation-job-pod> -- env | grep -E '^EDA_.*DB'
   ```
   If the worker has `EDA_DB_*` / `EDA_ACTIVATION_DB_*` but the job pod does not, see [eda-server-operator issue #313](https://github.com/ansible/eda-server-operator/issues/313) (external PostgreSQL + Event Streams).

2. Compare **`EDA_PG_NOTIFY_DSN`** on EDA server pods with the database secret (they can differ from `EDA_DB_*`):

   ```bash
   kubectl exec -n <eda-namespace> deploy/eda-server-activation-worker -- \
     printenv EDA_PG_NOTIFY_DSN EDA_PG_NOTIFY_DSN_SERVER 2>/dev/null
   ```

   Test that DSN from a throwaway pod with `psql "$EDA_PG_NOTIFY_DSN" -c 'SELECT 1'`. If the secret tests OK but this DSN fails, fix NOTIFY credentials in the operator/EDA CR, not the rulebook.

3. Verify the EDA database secret matches the running Postgres instance (`eda-postgres-configuration` or your `database.database_secret` on the EDA CR): host, port, database name, username, password.

4. After fixing credentials, restart EDA components (API, activation worker, daphne), **delete and recreate** the rulebook activation, and confirm the Event Stream is mapped to **`dynatrace_events`** with **test mode off**.

### Other issues

| Symptom | Check |
|---------|--------|
| HTTP 401 on event POST | Token matches credential; `Authorization: Bearer` header |
| Activation runs, no rule match | Payload includes `eventType: K8S_POD_REMEDIATION` and required fields |
| Workflow not launched | Controller URL/token on EDA; `remediation_workflow_job_template` matches workflow name exactly |
| Workflow runs, job missing vars | Rulebook passes flat `namespace` / `pod_name`; enable prompt on launch on workflow template |
| `ansible_eda not allowed on launch` | Enable prompt on launch for extra vars on **workflow** template |
| Job fails on K8s | Credentials on **job template**; RBAC allows pod delete in namespace |
| Job skips SN close | Pod was healthy; incident only closes after successful restart |
| Test mode | Disable test mode on the event stream |

## References

- [Red Hat simplified event routing](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/using_automation_decisions/simplified-event-routing)
- [Dynatrace Red Hat EDA integration](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/default-workflow-actions/actions/red-hat/redhat-even-driven-ansible)
