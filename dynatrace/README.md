# Dynatrace portion of the EDA demo

What you must add in **Dynatrace SaaS** (Latest UI, `*.apps.dynatrace.com`) and **OpenShift** so Davis can see `load-test-app` in `ia-lab`, a custom alert can open problem **`ia-lab-500`** on HTTP 5xx, and a workflow can open a ServiceNow incident, then POST to AAP Event-Driven Ansible.

AAP Event Stream, rulebook activation, and Controller workflow are **not** documented here. Use [docs/aap-setup.md](../docs/aap-setup.md) and [docs/aap-controller-workflow.md](../docs/aap-controller-workflow.md).

```text
OpenShift  →  Dynatrace Operator + DynaKube
                ├── ActiveGate (kubernetes-monitoring, routing)
                └── webhook injects OneAgent into ia-lab pods
                      └── load-test-app appears in Dynatrace
                            └── HTTP 5xx → custom alert ia-lab-500 → Davis problem
                                  └── Dynatrace workflow
                                        ├── ServiceNow Create Incident
                                        └── Send event to EDA (INC + problem_id) → AAP Event Stream
```



## Demo checklist

Do this in order. Files in this folder are the OpenShift/DynaKube side; the rest is in the Dynatrace UI or AAP.


| #   | You add                                                                                                              | Where                                                                                                                          |
| --- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 1   | DPS SaaS tenant (Operator itself is not licensed; see [License](#license-dps--saas))                                 | Dynatrace account                                                                                                              |
| 2   | Operator + DynaKube, or reuse an existing DynaKube                                                                   | OpenShift — steps [1–6](#1-create-dynatrace-tokens)                                                                            |
| 3   | Operator + data-ingest platform tokens in secret `dynakube`                                                          | **My platform tokens** → [Tokens](#1-create-dynatrace-tokens) → `oc` secret                                                    |
| 4   | `load-test-app` visible (init container + Kubernetes app / Explorer)                                                 | Dynatrace UI + `oc` — [Verify](#7-verify-in-dynatrace)                                                                         |
| 5   | Custom alert **`ia-lab-500`** on HTTP 5xx (`dt.service.request.failure_count`)                                       | Settings → Analyze and alert — [Custom alert](#8-custom-alert-ia-lab-500)                                                      |
| 6   | Hub apps (ServiceNow, Red Hat Ansible, Business Events) + ServiceNow/EDA connections                                 | Hub / Settings — [Workflow → ServiceNow](#9-dynatrace-workflow--servicenow)                                                    |
| 7   | **External requests** — add **both** hosts (hostname only, no `https://`): `ven05434.service-now.com` and `aap-aap.apps.cluster-rjpxx.dyn.redhatworkshops.io` | **Settings → General → External requests** — [Outbound hosts](#external-requests-two-hosts)                                    |
| 8   | Workflow actor: `storage:events:read` (and usually `storage:buckets:read`)                                           | IAM / Workflows authorization — [Workflow actor](#workflow-actor-and-dql)                                                      |
| 9   | Import [ia-lab-aap-events.workflow-template.yaml](ia-lab-aap-events.workflow-template.yaml) (**IA-Lab - AAP Events**) | Workflows → **Upload** — [Import the template](#import-the-workflow-template)                                                  |
| 10  | Map connections; Event Stream URL + token; Event data already in the template (live INC from Create Incident)        | AAP + import wizard — [Workflow → EDA](#10-dynatrace-workflow--eda)                                                            |
| 11  | Classic **Personal access token** with `problems.write` on the AAP close-problem credential (not a platform token) | User menu → Personal access tokens — [docs/create-credentials.md](../docs/create-credentials.md) |
| 12  | Event Stream mapped to source `dynatrace_events`, activation, workflow `remediate_k8s_cluster`                       | Already in AAP docs above                                                                                                      |


If Operator is **already** installed (Installed Operators, or a DynaKube such as `openshift-july-agents`), skip to [Existing Operator](#existing-operator). Do not create a second DynaKube whose `namespaceSelector` overlaps the first.

## What this folder contains


| File                                                       | Purpose                                                                       |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `[namespace.yaml](namespace.yaml)`                         | `dynatrace` project (empty node selector)                                     |
| `[tokens-secret.yaml.example](tokens-secret.yaml.example)` | Operator + data-ingest token secret template                                  |
| `[dynakube.yaml](dynakube.yaml)`                           | DynaKube: application monitoring + ActiveGate, scoped to `dt-monitoring=true` |
| `[ia-lab-monitoring.yaml](ia-lab-monitoring.yaml)`                           | Label `ia-lab` so the webhook injects OneAgent                                              |
| `[ia-lab-aap-events.workflow-template.yaml](ia-lab-aap-events.workflow-template.yaml)` | Dynatrace workflow template (**IA-Lab - AAP Events**): Davis → ServiceNow INC → EDA |
| `[eda-event-data.json](eda-event-data.json)`                                 | Sample Event data JSON (curl tests; live runs use the imported workflow)            |


Injection is **namespace-scoped** so OneAgent is not injected into `aap`, `openshift-`*, or `kube-`*. Kubernetes Platform Monitoring still sees the **whole cluster** (see [License](#license-dps--saas)).

## License (DPS / SaaS)

The Operator, CSI driver, webhook, and in-cluster ActiveGate are free to install (Apache 2.0). Dynatrace bills **what is monitored** on a [Dynatrace Platform Subscription](https://docs.dynatrace.com/docs/license) rate card.


| Capability                         | Enabled by                           | Unit             | What is billed                                                         | Limited to `ia-lab`?                                                                                                               |
| ---------------------------------- | ------------------------------------ | ---------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Kubernetes Platform Monitoring** | `activeGate` `kubernetes-monitoring` | Pod-hours        | Every pod the API reports (all namespaces, including Operator/CSI/AAP) | **No** — [whole cluster](https://docs.dynatrace.com/docs/license/capabilities/container-monitoring/kubernetes-platform-monitoring) |
| **Application observability**      | `oneAgent.applicationMonitoring`     | Memory GiB-hours | Containers that get a code module                                      | **Yes** — `dt-monitoring=true`                                                                                                     |


List-price ballpark ([pricing](https://www.dynatrace.com/pricing/); your rate card may differ): about **$0.002 per pod-hour** for platform monitoring, about **$0.01 per memory-GiB-hour** for Full-Stack / app-only.

Kubernetes Platform Monitoring requires **DPS on SaaS**. Classic Host-Unit tenants should confirm with their Dynatrace admin.

Application-only GiB-hours use a 256 MiB minimum and round up to 0.25 GiB. If the container has **no memory limit**, billing can use **node size**. `load-test-app` sets `resources.limits.memory: 256Mi` for that reason.

Track usage in Account Management → Subscription, or metric `builtin:billing.kubernetes_monitoring.usage`.

## Prerequisites

- `oc` logged in as a user who can create projects and cluster-scoped Operator resources
- Dynatrace environment URL (API host, not the `.apps.` UI host)
- Two tokens (see [Tokens](#1-create-dynatrace-tokens))
- Demo app in `ia-lab`: `oc apply -f k8s/ia-lab-namespace.yaml -f k8s/load-test-app-pod.yaml -f k8s/load-test-app-svc.yaml`

Official install guides: [Application observability on OpenShift](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/application-observability), [tokens](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/tokens-permissions), [namespace injection](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/deployment-and-configuration/monitoring-and-instrumentation/annotate).

## 1. Create Dynatrace tokens

You need **two** Latest Dynatrace **platform tokens**. Keep them out of git. They go in the `dynakube` secret as `apiToken` (Operator) and `dataIngestToken` (Data Ingest).

A platform token only works within the **assigned identity's** permissions. Regular users create tokens **for themselves** (the default). Creating a **service user** is account-admin only — skip that if you cannot add service users.

If Operator and a DynaKube are already installed, skip this section and use [Existing Operator](#existing-operator).

Kubernetes onboarding can create these tokens automatically if an account admin has granted **Kubernetes Onboarding**.

### Create tokens for your user

1. Open **My platform tokens** ([platform tokens](https://docs.dynatrace.com/docs/manage/identity-access-management/access-tokens-and-oauth-clients/platform-tokens)).
2. Create **two** tokens. Generate each **for you**, restrict them to this environment, and copy the value (shown once).
3. Enable scopes from [Tokens and permissions](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/tokens-permissions) (Latest):

  | Secret key        | Purpose                                             | Scopes                                                                                                                                                                                                                                                                                        |
  | ----------------- | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | `apiToken`        | Operator lifecycle (DynaKube, ActiveGate, OneAgent) | `fleet-management:activegate.connection-info:read`, `fleet-management:activegate.tokens:create`, `fleet-management:container-images:read`, `fleet-management:oneagent.connection-info:read`, `fleet-management:oneagents:download`, `settings:objects:read`, `settings:objects:write` |
  | `dataIngestToken` | Metrics, logs, traces from the cluster              | `openpipeline:logs:ingest`, `openpipeline:metrics:ingest`, `openpipeline:traces:ingest`, `storage:metrics:write`                                                                                                                                                                              |


Use **`settings:objects:read`** and **`settings:objects:write`** on the Operator token. Do **not** use **`app-settings:objects:*`** — those scopes do not satisfy Kubernetes entity settings (Explorer stays empty; `MonitoredEntity` stays `False`).

Your user (or a group you belong to) must already have **Kubernetes Operator** and **Kubernetes Ingest**. If Generate fails or the Operator returns 401/403, ask an account admin to add those policies to your group, or to create the tokens for you.

### If you are an account admin

A dedicated **service user** is the better shared/demo identity:

1. **Account Management** → **Identity & access management** → **Service users** → **Add service user**.
2. Assign **Kubernetes Operator** and **Kubernetes Ingest**.
3. In **My platform tokens**, create one token per role and assign each token to that service user.



## 2. Create the `dynatrace` project

```bash
oc apply -f dynatrace/namespace.yaml
```

Equivalent: `oc adm new-project --node-selector="" dynatrace`

## 3. Install Dynatrace Operator (with CSI)

CSI is required for efficient code-module injection. OperatorHub **cannot** install the CSI driver; use the OpenShift manifest (or Helm).

Pinned release: **v1.10.2**.

```bash
oc apply -f https://github.com/Dynatrace/dynatrace-operator/releases/download/v1.10.2/openshift-csi.yaml

oc -n dynatrace wait pod --for=condition=ready \
  --selector=app.kubernetes.io/name=dynatrace-operator,app.kubernetes.io/component=webhook \
  --timeout=300s
```

Without CSI (not recommended for this demo): `openshift.yaml` from the same release.

## 4. Create the token secret

```bash
cp dynatrace/tokens-secret.yaml.example dynatrace/tokens-secret.yaml
# edit apiToken and dataIngestToken
oc apply -f dynatrace/tokens-secret.yaml
```

Or without a local secret file:

```bash
oc -n dynatrace create secret generic dynakube \
  --from-literal="apiToken=<OPERATOR_TOKEN>" \
  --from-literal="dataIngestToken=<DATA_INGEST_TOKEN>"
```

The secret name must match the DynaKube (`dynakube`) or `spec.tokens` in `[dynakube.yaml](dynakube.yaml)`.

## 5. Apply the DynaKube

1. Set `spec.apiUrl` in `[dynakube.yaml](dynakube.yaml)`:

  | Environment   | `apiUrl`                                                              |
  | ------------- | --------------------------------------------------------------------- |
  | SaaS          | `https://<environment-id>.live.dynatrace.com/api`                     |
  | Sprint / labs | `https://<environment-id>.sprint.dynatracelabs.com/api` (no `.apps.`) |

2. Apply:
  ```bash
   oc apply -f dynatrace/dynakube.yaml
   oc -n dynatrace get dynakube
   oc -n dynatrace get pods
  ```

Status should become **Running**. Expect Operator, webhook, ActiveGate, and a CSI driver pod per node.

## 6. Enable monitoring for `ia-lab` and restart the app

```bash
oc apply -f dynatrace/ia-lab-monitoring.yaml
oc delete pod load-test-app -n ia-lab --wait=false
oc apply -f k8s/load-test-app-pod.yaml
oc -n ia-lab wait pod/load-test-app --for=condition=Ready --timeout=180s
```

The webhook injects an init container named `dynatrace-operator` (or similar) on create. Existing pods are not mutated until they are recreated.

Confirm injection:

```bash
oc get pod load-test-app -n ia-lab -o jsonpath='{range .spec.initContainers[*]}{.name}{"\n"}{end}'
oc get ns ia-lab --show-labels
```

You should see a Dynatrace init container and label `dt-monitoring=true`. The Operator also adds `dynakube.internal.dynatrace.com/instance=<dynakube-name>`.

## 7. Verify in Dynatrace

Work in the **Latest** UI (`https://<environment-id>.apps.dynatrace.com`). The DynaKube `spec.apiUrl` stays on the **API** host: `https://<environment-id>.live.dynatrace.com/api` (or `.sprint.dynatracelabs.com/api` for labs). Never put `.apps.` in `apiUrl`.

### Operator and Kubernetes entities

The Operator token (`apiToken`) needs **`settings:objects:read`** and **`settings:objects:write`**. Do not substitute **`app-settings:objects:*`** — those scopes do not satisfy the Kubernetes entity settings the Operator writes.

Check the DynaKube condition:

```bash
oc -n dynatrace get dynakube dynakube -o yaml
```

If **`MonitoredEntity`** is `False` (token missing `settings:objects:read`), Kubernetes Explorer stays empty even when ActiveGate is Running. After you rotate the secret with the correct scopes, wait until that condition is `True`.

### Kubernetes Explorer vs Explorer Classic

The **new** Kubernetes Explorer needs the **New Kubernetes experience**. Until that is on, the cluster still appears as **`dynakube`** (the DynaKube name) in **Explorer Classic** / **Kubernetes Classic**, and ActiveGate logs may show `kubernetesAppEnabled=false` (and often `kubernetesSmartscapeEnabled=false`).

Enable it either:

- Kubernetes app → **Activation pending** (complete activation), or
- **Settings → Collect and capture → Cloud and virtualization → Kubernetes app**

Then confirm `ia-lab` / `load-test-app` in Explorer (or Classic until activation finishes).

### Workload and HTTP traffic

1. **Services** / process group for the Apache workload in `load-test-app`.
2. Get the OpenShift Route and generate **HTTP 5xx** so `dt.service.request.failure_count` has data **before** you create the custom alert:

```bash
oc get route load-test-app -n ia-lab
# Open https://<host>/ in a browser. Use the app control or path that returns HTTP 5xx
# (this image is gokev/load-test-app). Confirm with:
curl -sk -o /dev/null -w '%{http_code}\n' "https://$(oc get route load-test-app -n ia-lab -o jsonpath='{.spec.host}')/"
```

A **single** 500 is **not** a Davis problem by default. Keep a 5xx loop running while you create the alert and while you want the Davis problem **ACTIVE**:

```bash
HOST="$(oc get route load-test-app -n ia-lab -o jsonpath='{.spec.host}')"
# Replace PATH with the app's 5xx endpoint once you have confirmed it in the browser
while true; do curl -sk -o /dev/null -w '%{http_code}\n' "https://${HOST}/PATH"; sleep 1; done
```

Continue with [Custom alert `ia-lab-500`](#8-custom-alert-ia-lab-500).

## 8. Custom alert `ia-lab-500`

Latest UI has **no** **Settings → Anomaly detection**. Create a **custom alert** that opens a Davis event/problem when the service records HTTP failures.

Path: **Settings → Analyze and alert → Alerts → All alerts → Custom alerts** (or search **Custom alerts**). Open the **Advanced** tab.

### Query

Use this DQL. Do **not** add `from:` / `to:` — the alert owns the time window.

```dql
timeseries failed = sum(dt.service.request.failure_count, default: 0),
  interval: 1m
```

- **Actor** = a user who can already query that metric in Notebooks (your user, if that is who created the alert).
- **Static threshold**, **above 0**.
- **Violating samples:** **1 of 3**.
- **De-alerting:** as high as the UI allows so problems **close as soon as 500s stop**.

### Event template

**Create event template:**

| Field      | Value            |
| ---------- | ---------------- |
| Event name | **`ia-lab-500`** |
| Type       | **`CUSTOM_ALERT`** |

**Preview** must show a **breach**. If Preview never breaches, the alert will not open Davis events even when Notebooks show a metric spike.

### Confirm in Notebooks

1. Metric spike: the same `timeseries` query while 500s are in flight.
2. Then events: `fetch events` and/or `fetch dt.davis.events`. Do **not** rely only on `event.name == "ia-lab-500"` until a notebook row proves that name.

### Keep the problem ACTIVE

A **single** 500 can open a problem and **close it within a minute** once failures stop. Keep a 500 loop running if you need an **ACTIVE** problem for the workflow. Davis will not stay open forever with no traffic.

## 9. Dynatrace workflow → ServiceNow

Do **not** build the workflow by hand. Import [ia-lab-aap-events.workflow-template.yaml](ia-lab-aap-events.workflow-template.yaml). The template is titled **IA-Lab - AAP Events**. It creates a ServiceNow **incident** (`INC…`), not a ServiceNow Problem (`PRB`) record. AAP later documents that incident via `incident_number` ([playbooks/document_servicenow_incident.yml](../playbooks/document_servicenow_incident.yml)).

Install Hub apps, grant the actor Grail access, add the [two External requests hosts](#external-requests-two-hosts), and create connections **before** (or during) the import wizard.

### Install Hub apps and grant Workflows access

The template lists these apps. Install or update them from Hub if the import wizard says they are missing or outdated:

| App id | Role in this workflow |
| ------ | --------------------- |
| `dynatrace.servicenow` | Create Incident (`create_initial_incident`) |
| `dynatrace.redhat.ansible` | Send event to Event-Driven Ansible |
| `dynatrace.automations` | Execute DQL (`fetch_trigger_event`) |
| `dynatrace.biz.explore` | Ingest a business event after EDA (`store_information`) |

1. Dynatrace Hub → **ServiceNow**, **Red Hat Ansible**, **Business Events** (and Workflows/Automations if not already present) → **Install** ([ServiceNow Connector](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/default-workflow-actions/actions/service-now), [Red Hat Ansible for Workflows](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/default-workflow-actions/actions/red-hat/redhat-even-driven-ansible)).
2. **Workflows** → **Settings** → **Authorization settings**. Grant `app-settings:objects:read` (ServiceNow connector) **and** the [workflow actor](#workflow-actor-and-dql) Grail scopes.

### Workflow actor and DQL

The template’s first task is **`fetch_trigger_event`** (DQL on `dt.davis.events` / `dt.davis.problems`). The **workflow actor** must be able to query Grail. Notebook success as your user does **not** imply the actor can.

Grant the actor at least:

- `storage:events:read`
- usually `storage:buckets:read`

Without those, the run fails with **`NOT_AUTHORIZED_FOR_TABLE`** (table `events`). Set this under **Workflows → Settings → Authorization settings** (or the IAM policy attached to the actor).

### External requests (two hosts)

This demo needs **two** outbound hosts. Add both under **Settings → General → External requests**. Use the **hostname only** (no `https://`, no path).

| # | Purpose | Hostname to add |
| - | ------- | --------------- |
| 1 | ServiceNow Create Incident | `ven05434.service-now.com` |
| 2 | AAP Event Stream (Send event to Event-Driven Ansible) | `aap-aap.apps.cluster-rjpxx.dyn.redhatworkshops.io` |

If either host is missing, the matching workflow task fails with **`host not in allowlist`** / `Blocked request` / `NotCapable`. If you use a different ServiceNow instance or AAP route, add that hostname instead (from `https://<host>/...`).

### Create the ServiceNow connection

1. **Settings** → **Connections** → **Connectors** → **ServiceNow** → **Connection**.
2. Fill in:

  | Field                   | Value                                                                                                                |
  | ----------------------- | -------------------------------------------------------------------------------------------------------------------- |
  | Connection name         | Meaningful name (for example `servicenow-demo`)                                                                      |
  | ServiceNow instance URL | `https://<instance>.service-now.com`                                                                                 |
  | Type                    | **Basic** for this demo (username + password). **OAuth client credentials** (client id + secret) is the alternative. |

3. Use a **local** ServiceNow integration user with `itil` plus REST / table access on `incident`. **401 Unauthorized** on `POST .../api/now/v2/table/incident` is almost always credentials (wrong user/password, or SSO user with no local password).

You can also **Create a new connection** in the import wizard instead of creating it first.

### Import the workflow template

Latest UI ([Upload a workflow template](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/manage-workflows/workflows-upload)):

1. **Workflows** → **Upload**.
2. Choose [ia-lab-aap-events.workflow-template.yaml](ia-lab-aap-events.workflow-template.yaml) from this repo (YAML template, not a JSON workflow download).
3. **Required apps:** install or **Update from Hub** if a listed app is missing or too old, then **Refresh**.
4. **Required connections:** map the ServiceNow connection to `create_initial_incident`, and the Event-Driven Ansible connection to `send_event_to_event-driven-ansible_2`. Create the EDA connection here if you do not have one yet:
   - URL = Event Stream POST URL from [docs/aap-setup.md](../docs/aap-setup.md) (include `/post`).
   - Token = the Token Event Stream credential. The connector sends `Authorization: Bearer <token>` (same as [samples/curl_post_event.sh](../samples/curl_post_event.sh)).
5. **Import**. Workflows opens **IA-Lab - AAP Events** in the editor. **Save**.

Task order after import:

```text
fetch_trigger_event
  → create_initial_incident
      → send_event_to_event-driven-ansible_2
          → store_information
```

Do not rename `create_initial_incident`. Downstream tasks use `result("create_initial_incident")["number"]`.

### After import: fix ServiceNow fields

The exported template still has placeholder values that **fail** on a real instance. Open **create_initial_incident** and set:

| Field | Template default | Change to |
| ----- | ---------------- | --------- |
| Assignment group | `-1` / Unassigned | A **real** `sys_user_group` on the instance |
| Caller | `dynatrace` | An existing ServiceNow user, or **leave empty** |
| Category / subcategory / impact / urgency | `software` / `internal application` / 1 / 2 | Keep if those choices exist; otherwise pick values from the dropdowns |

Correlation ID is already `DT_{{ event()["event.id"] }}`. Short description uses `event.category`, `event.name`, and `display_id`.

Run once against a Davis payload and confirm the task result includes an incident **number** (`INC…`).

### Trigger on `ia-lab-500`

The template ships this event trigger (already **active**):

```text
event.name == "ia-lab-500" and event.kind == "DAVIS_PROBLEM"
```

That AND only fires if a notebook proves Davis **problems** use `event.name` **`ia-lab-500`**. If executions never start:

- Prefer **Problem** state **active** (or **active or closed** if problems close too fast). No minimum duration.
- Davis **event** is `event.kind == "DAVIS_EVENT"` (name is typically `ia-lab-500`). Davis **problem** is `DAVIS_PROBLEM` and the name **may differ** — do not keep the AND unless the notebook match is real.

Problems that are already **CLOSED** can still create an INC; keep a 500 loop running if you want an **ACTIVE** Davis problem at the same time.

## 10. Dynatrace workflow → EDA

The imported template already includes **Send event to Event-Driven Ansible** as `send_event_to_event-driven-ansible_2`, after `create_initial_incident`. Map the Event Stream connection in the import wizard (or open that task and select the connection).

Event data in the template. Custom-alert Davis problems **do not** have `k8s.namespace.name` / `k8s.pod.name`. Using those keys fails the task (`Undefined variables: k8s.namespace.name`). This demo hardcodes the OpenShift project and pod:

```json
{
  "eventType": "K8S_POD_REMEDIATION",
  "namespace": "ia-lab",
  "pod_name": "load-test-app",
  "incident_number": "{{ result(\"create_initial_incident\")[\"number\"] }}",
  "problem_id": "{{ event()[\"event.id\"] }}"
}
```

If you already imported an older template, paste that JSON into **send_event_to_event-driven-ansible_2** (and the same `namespace` / `pod_name` / `eventType` literals into **store_information**). Save, then re-run.

`incident_number` still comes from Create Incident. `problem_id` must be the **API** id (`event.id`), not display id `P-…`. Empty skips [playbooks/close_dynatrace_problem.yml](../playbooks/close_dynatrace_problem.yml).

The rulebook [rulebooks/k8s_cluster_remediation-event.yml](../rulebooks/k8s_cluster_remediation-event.yml) matches:

`event.payload.eventData.eventType == "K8S_POD_REMEDIATION"`

and launches workflow job template `remediate_k8s_cluster`.


| Field             | Required    | Notes                                                                           |
| ----------------- | ----------- | ------------------------------------------------------------------------------- |
| `eventType`       | yes         | Must be exactly `K8S_POD_REMEDIATION`                                           |
| `namespace`       | yes         | OpenShift project; string or `['ia-lab']` (normalized in `save_workflow_stats`) |
| `pod_name`        | yes         | Pod to delete/recreate; same list-or-scalar form                                |
| `incident_number` | yes         | ServiceNow `INC…` from `create_initial_incident`                                |
| `problem_id`      | recommended | API problemId for the close step                                                |


Test without a live problem (uses the **static** INC in [eda-event-data.json](eda-event-data.json); live workflow runs get the INC from Create Incident):

```bash
export EVENT_STREAM_URL="https://<aap-host>/eda-event-streams/api/eda/v1/external_event_stream/<uuid>/post"
export EVENT_STREAM_TOKEN="<token>"
./samples/curl_post_event.sh
```

`save_workflow_stats` reads `eda_payload.payload.eventData` and publishes `namespace`, `pod_name`, `sn_incident_number`, `dynatrace_problem_id`. See [docs/aap-controller-workflow.md](../docs/aap-controller-workflow.md) sections 6–8.

## Existing Operator

If Operator and a DynaKube are already installed:

1. Confirm: `oc get dynakube -A` and `oc get csv -A | grep -i dynatrace`.
2. **Do not** apply `[dynakube.yaml](dynakube.yaml)` if another DynaKube already selects `ia-lab` (overlapping `namespaceSelector` is rejected).
3. If that DynaKube has no `namespaceSelector`, it injects all namespaces except `kube-*`, `openshift-*`, and `dynatrace`. Labeling is optional; still **restart** `load-test-app`.
4. If it uses `namespaceSelector`, either add `dt-monitoring: "true"` to that selector or apply `[ia-lab-monitoring.yaml](ia-lab-monitoring.yaml)` when the selector already matches that label.
5. Recreate the app pod (step 6) so injection runs.

You are already consuming against that tenant. A second overlapping DynaKube does not add a license; apply fails.

## Troubleshooting


| Symptom | Fix |
| ------- | --- |
| DynaKube not created / webhook timeout | Wait for Operator webhook pods Ready; re-apply `dynakube.yaml` |
| DynaKube apply fails: namespaceSelector overlap | Only one DynaKube may inject a given namespace |
| ActiveGate / CSI pods Pending | `dynatrace` project must have empty node selector (`namespace.yaml`) |
| CSI pods Forbidden / privileged | OpenShift CSI install (`openshift-csi.yaml`) grants `privileged` SCC to the CSI SA |
| App pod unschedulable after injection | `feature.dynatrace.com/init-container-seccomp-profile: "false"` is already set on this DynaKube; check SCC vs `runAsUser: 0` on `load-test-app` |
| No init container on `load-test-app` | Namespace missing `dt-monitoring=true`; pod created before DynaKube was Ready — delete and re-apply the pod |
| App never appears in Dynatrace | Wrong `apiUrl` (do not use `.apps.`); token scopes; check `oc -n dynatrace logs` on operator and ActiveGate |
| Kubernetes Explorer empty; Classic still empty | Operator token used `app-settings:objects:*` instead of **`settings:objects:read` / `write`**. Check `oc -n dynatrace get dynakube dynakube` — **`MonitoredEntity`** must be `True` |
| Cluster in Explorer Classic only (`dynakube`); new Explorer empty | **New Kubernetes experience** is off (`kubernetesAppEnabled=false` in ActiveGate logs). Activate the Kubernetes app, or **Settings → Collect and capture → Cloud and virtualization → Kubernetes app** |
| 401/403 from Operator | Recreate `dynakube` secret with Operator + data-ingest platform tokens; your user (or service user) needs **Kubernetes Operator** and **Kubernetes Ingest** |
| Custom alert Status **Error** / Preview never breaches | Query must have **no** `from:` / `to:`; actor must be able to query the metric in Notebooks; generate HTTP 500s so `dt.service.request.failure_count` is non-zero |
| Metric spike in Notebooks but no Davis rows | Filter `fetch events` / `fetch dt.davis.events` without assuming `event.name == "ia-lab-500"` until a row confirms the name; wait for Preview to show a breach |
| Problem opens then is already **CLOSED** | A single 500 de-alerts quickly. Keep a 500 loop running; use trigger state **active or closed** if needed |
| `fetch_trigger_event` / `NOT_AUTHORIZED_FOR_TABLE` | Notebook user can query Grail; **workflow actor** cannot. Grant actor `storage:events:read` and usually `storage:buckets:read` |
| Error evaluating `eventData`: `Undefined variables: k8s.namespace.name` | Custom-alert problems have no `k8s.*` properties. In **send_event_to_event-driven-ansible_2**, hardcode `"namespace": "ia-lab"` and `"pod_name": "load-test-app"` (do not use `event()["k8s.namespace.name"]`). Same literals in **store_information**. |
| Create Incident or EDA POST: `host not in allowlist` / `NotCapable` | Add **both** [External requests](#external-requests-two-hosts): `ven05434.service-now.com` and `aap-aap.apps.cluster-rjpxx.dyn.redhatworkshops.io` (hostname only, no `https://`) |
| Dynatrace close skipped | `problem_id` empty in Event data |
| Rulebook does not match | `eventType` must be `K8S_POD_REMEDIATION` under `eventData` |
| Create Incident action missing from Workflows | Install **ServiceNow** from Hub; grant Workflows `app-settings:objects:read`; import [ia-lab-aap-events.workflow-template.yaml](ia-lab-aap-events.workflow-template.yaml) |
| Import wizard: required apps missing | Hub-install **ServiceNow**, **Red Hat Ansible**, **Business Events**, and Workflows/Automations; **Refresh** in the wizard |
| 401 Unauthorized from ServiceNow | Recreate the connection with a **local** integration user (`itil` + REST / `incident`); SSO users often have no local password |
| Create Incident fails on category / assignment group | After import, replace template defaults: assignment group must not be `-1`; caller must be a real user or empty |
| `incident_number` empty or EDA cannot document the ticket | Confirm task id is `create_initial_incident`; inspect the task result and use `.number` or `.result.number` as shown in a test run |
| Workflow never starts | Template trigger ANDs `event.name == "ia-lab-500"` with `DAVIS_PROBLEM`. Confirm that match in a notebook, or drop the name filter / use `DAVIS_EVENT` |



## References

- [Dynatrace Operator — OpenShift CSI install](https://github.com/Dynatrace/dynatrace-operator/releases)
- [DynaKube parameters](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/reference/dynakube-parameters)
- [OpenShift SCC notes](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/networking-security-compliance/security-configurations/openshift-configuration)
- [OperatorHub (no CSI)](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/other/ocp-operator-hub)
- [Kubernetes Platform Monitoring consumption](https://docs.dynatrace.com/docs/license/capabilities/container-monitoring/kubernetes-platform-monitoring)
- [Full-Stack / application-only GiB-hours](https://docs.dynatrace.com/docs/license/capabilities/app-infra-observability/full-stack-monitoring)
- [Custom alerts (advanced anomaly detection)](https://docs.dynatrace.com/docs/dynatrace-intelligence/anomaly-detection/anomaly-detection-app/configure-an-advanced-ad)
- [Allow external requests](https://developer.dynatrace.com/develop/guides/app-functions/allow-outbound-connections/)
- [Upload a workflow or a workflow template](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/manage-workflows/workflows-upload)
- [Event triggers for Workflows](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/build/trigger/event-trigger)
- [ServiceNow Connector for Workflows](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/default-workflow-actions/actions/service-now)
- [Red Hat Event-Driven Ansible for Workflows](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/default-workflow-actions/actions/red-hat/redhat-even-driven-ansible)
- [Workflows expressions (`event()`, `result()`)](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/reference)
