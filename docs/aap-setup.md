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
6. Add the AAP Credential and Create rulebook activation
7. Enable the activation.


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

## Ensuring the database secret reaches the rulebook (activation pod)

The rulebook file does **not** carry the Postgres password. With Event Stream mapping, `ansible.eda.event_stream` becomes **`eda.builtin.pg_listener`**, which reads the EDA database using environment variables injected by the **EDA operator** when it creates the `activation-job-*` pod.

| What you configure in AAP UI | What it is for |
|------------------------------|----------------|
| **Token Event Stream** credential | HTTP `Authorization` token for Dynatrace/curl POST to the event stream URL |
| **Automation Controller** credential on the activation (if shown) | Controller API for `run_workflow_template` — not Postgres |
| **Decision environment** | `ansible.eda`, rulebook runtime — not Postgres |

You **cannot** paste the Postgres secret into `rulebooks/k8s_pod_remediation.yml` or activation **Variables** YAML to fix `pg_listener`.

### What must be true on the cluster

1. **Secret** (often `eda-postgres-configuration` in namespace `aap`) with keys such as `host`, `port`, `database`, `username`, `password`, `sslmode` (see [EDA operator database configuration](https://github.com/ansible/eda-server-operator/blob/main/docs/user-guide/database-configuration.md)).

2. **EDA custom resource** references that secret:
   ```yaml
   spec:
     database:
       database_secret: eda-postgres-configuration
   ```

3. **`aap26-eda-activation-worker`** has `EDA_DB_*` env vars (you confirmed this).

4. **Each `activation-job-*` pod** must have the **same** `EDA_DB_*` vars in the **eda** container (not only the worker):
   ```bash
   POD=$(oc get pods -n aap -l job-name --sort-by=.metadata.creationTimestamp -o name | tail -1 | cut -d/ -f2)
   CONTAINER=$(oc get pod "$POD" -n aap -o jsonpath='{.spec.containers[0].name}')
   oc exec -n aap "$POD" -c "$CONTAINER" -- env | grep -E '^EDA_.*DB' | sort
   ```
   If this is **empty** while the worker has vars, the operator is not passing the secret to job pods — platform fix ([eda-server-operator#313](https://github.com/ansible/eda-server-operator/issues/313)). Open a case with Red Hat / upgrade **eda-server-operator** to a build that includes the fix for your AAP version.

5. **Password matches Postgres** — from the worker only (do not share passwords in chat):
   ```bash
   oc exec -n aap deploy/aap26-eda-activation-worker -- \
     bash -c 'PGPASSWORD="$EDA_DB_PASSWORD" psql -h "$EDA_DB_HOST" -U "$EDA_DB_USER" -d "$EDA_DB_NAME" -c "select 1"'
   ```
   If this fails, update the secret and the `eda` user password in Postgres together, then restart EDA and Postgres pods.

### After the platform team fixes injection

1. Restart `aap26-eda-activation-worker` (or let the operator roll it).
2. **Disable** then **enable** the rulebook activation in AAP.
3. Confirm activation logs no longer show `password authentication failed`.
4. Map Event Stream → source `dynatrace_events`; run `./samples/curl_post_event.sh`.

## Troubleshooting

### Activation fails: `pg_listener` / `password authentication failed for user "eda"`

With `ansible.eda.event_stream` (or Event Stream mapping on source `dynatrace_events`), the activation pod runs **`eda.builtin.pg_listener`**, which reads events from the **EDA PostgreSQL** database. Your log shows host **`10.130.2.9:5432`** and user **`eda`**.

This is **not** caused by the decision environment image, the rulebook Git content, or the Token Event Stream HTTP token. The activation job cannot log in to Postgres.

| Log line | Meaning |
|----------|---------|
| `eda.builtin.pg_listener` | Event Stream path is active (expected when stream is mapped) |
| `password authentication failed for user "eda"` | Wrong/missing DB password in the **activation-job** pod |

**Diagnose on OpenShift (replace `<eda-ns>` with your EDA namespace, e.g. where `aap26-eda-api` runs):**

```bash
# 1) Does the activation worker have DB env vars?
oc exec -n <eda-ns> deploy/aap26-eda-activation-worker -- env | grep -E '^EDA_.*DB' | sort

# 2) Activation job pod (use -c for the eda container if the pod has multiple containers):
POD=<activation-job-pod>
CONTAINER=$(oc get pod "$POD" -n <eda-ns> -o jsonpath='{.spec.containers[0].name}')
oc exec -n <eda-ns> "$POD" -c "$CONTAINER" -- env | grep -E '^EDA_.*DB' | sort

# Optional: verify password works from the worker (same creds EDA should use)
oc exec -n <eda-ns> deploy/aap26-eda-activation-worker -- \
  bash -c 'PGPASSWORD="$EDA_DB_PASSWORD" psql -h "$EDA_DB_HOST" -U "$EDA_DB_USER" -d "$EDA_DB_NAME" -c "select 1"'

# 3) Compare secret keys (do not paste passwords into tickets)
oc get secret eda-postgres-configuration -n <eda-ns> -o jsonpath='{.data}' | python3 -m json.tool
```

If step 1 shows `EDA_DB_HOST`, `EDA_DB_PASSWORD`, etc. but step 2 shows **nothing**, the activation job is not receiving database credentials. That matches [eda-server-operator issue #313](https://github.com/ansible/eda-server-operator/issues/313) (common with external/managed Postgres). Your platform team must fix the EDA operator/deployment so **activation-job** pods inherit the same DB secret as `eda-server-activation-worker`.

If step 2 shows DB vars but auth still fails, the **password in the secret does not match** the password configured on the Postgres server for user `eda` (rotate secret and Postgres together, then restart EDA pods).

**After the platform fix:** disable and re-enable the rulebook activation; confirm logs no longer show `password authentication failed`, then run `./samples/curl_post_event.sh`.

**Not fixable in this repo:** changing `quay.io/froberge/eda-dynatrace-demo-ee:latest` or editing `rulebooks/k8s_pod_remediation.yml` will not resolve Postgres authentication.

### Other issues

| Symptom | Check |
|---------|--------|
| HTTP 401 on event POST | Token Event Stream credential; `Authorization: Bearer` header |
| Activation up, no rule match | Payload `eventType: K8S_POD_REMEDIATION`, `namespace`, `pod_name`, etc. |
| Workflow not launched | Controller link on activation; workflow name `remediate_k8s_cluster` exists |
| Controller job `system:anonymous` | OpenShift/Kubernetes credential on **job template** (see controller workflow doc) |
| Test mode | Turn off test mode on the event stream |

## References

- [Red Hat simplified event routing](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/using_automation_decisions/simplified-event-routing)
- [Dynatrace Red Hat EDA integration](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/default-workflow-actions/actions/red-hat/redhat-even-driven-ansible)
