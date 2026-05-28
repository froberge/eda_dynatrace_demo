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
 

### Path: Webhook on OpenShift (no Event Stream)

Use to avoid `pg_listener` / Postgres on activation jobs. This **does not** use the standard Dynatrace Event Stream POST URL.

1. On the rulebook activation, set **Service name** (for example `k8s-cluster-remediation`). EDA creates a ClusterIP Service on port **5000** when the activation is Running.
2. Create a **Route** to that Service

   ```bash
   oc expose svc k8s-cluster-remediation --port=5000 -n aap
   ```

3. **TLS on the Route is required for `https://` curls.** If `spec.tls` is empty, OpenShift returns **503** (“Application is not available”) on HTTPS while `http://` may still return **200**. Match other AAP routes:

   ```bash
   oc patch route k8s-cluster-remediation -n aap --type=merge -p \
     '{"spec":{"tls":{"termination":"edge","insecureEdgeTerminationPolicy":"Redirect"}}}'
   ```

4. POST JSON to the Route (not `./samples/curl_post_event.sh`):

   ```bash
   curl -sS -X POST "https://k8s-cluster-remediation-aap.apps.<cluster-domain>/" \
     -H "Content-Type: application/json" \
     -d @samples/dynatrace_eda_event.json
   ```


Dynatrace’s built-in Red Hat EDA connector expects the **event stream** URL; Path C requires a custom HTTP action to the webhook Route.


## References

- [Red Hat simplified event routing](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/using_automation_decisions/simplified-event-routing)
- [Dynatrace Red Hat EDA integration](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/default-workflow-actions/actions/red-hat/redhat-even-driven-ansible)
