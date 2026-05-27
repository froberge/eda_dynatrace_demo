# Build decision / execution environment

Build a container image from [`execution-environment.yml`](../execution-environment.yml) with **ansible-builder**, push it to a registry, and register the same image in AAP as:

- an **EDA decision environment** (rulebook activation), and
- a **Controller execution environment** (workflow job template).

The definition file is **version 3** and builds from **`registry.access.redhat.com/ubi9/python-312-minimal:latest`**, with Python 3.12 pinned via `python_interpreter`, then installs `ansible-rulebook`, `ansible.eda`, `kubernetes.core`, `servicenow.itsm`, and the `kubernetes` Python package.

**Do not** set `quay.io/ansible/ansible-rulebook:latest` as `images.base_image` in ansible-builder. That Quay image is already a finished decision environment; layering ansible-builder on it causes pip/Python mismatches (see [Troubleshooting](#troubleshooting)).

For **Event Streams only**, EDA can use the platform default `ansible-rulebook` image without a custom build. Build a custom image when you need pinned collections or one image for both EDA and Controller in this demo.

## Prerequisites

On the build host:

- **Podman**
- **Quay.io access**
- **ansible-builder 3.1+** (required for `version: 3` and `dependencies.exclude`)

```bash
python3 -m pip install --upgrade "ansible-builder>=3.1"
ansible-builder --version
```

Log in before pulling the UBI base and before pushing your image:

```bash
podman login registry.access.redhat.com   # required to pull ubi9/python-312-minimal
podman login quay.io                      # required to push your built image
```

## Build for AAP cluster architecture

Most AAP and OpenShift clusters run **`linux/amd64`** (x86_64). If you build on **Apple Silicon** (or any `arm64` host) without setting the platform, the image is `linux/arm64` and rulebook activation fails with:

```text
exec /usr/local/bin/ansible-rulebook: exec format error
```

**Always build for the architecture your cluster uses.** For typical AAP deployments, pass `--platform linux/amd64` (see commands below). If you build on `linux/amd64` Linux already, you may omit the platform flag.

Cross-build on arm64 Mac requires Podman/Docker with QEMU/binfmt (Podman Desktop includes this by default).

## 1. Build the image

From the repository root:

```bash
cd /path/to/eda_dynatrace_demo

ansible-builder build \
  -f execution-environment.yml \
  -t quay.io/<your-namespace>/eda-dynatrace-demo-ee:latest \
  --extra-build-cli-args='--platform linux/amd64'
```

| Flag | Meaning |
|------|---------|
| `-f execution-environment.yml` | Definition file (`execution-environment.yml` is the default if omitted) |
| `-t ...` | Full image name and tag to produce |
| `--extra-build-cli-args='--platform linux/amd64'` | Target x86_64 for AAP nodes (omit if build host is already amd64) |

**Generate build context only (no image):**

```bash
ansible-builder create -f execution-environment.yml -c ./context
```

The `context/` directory is gitignored. Review the generated `Containerfile` before building in restricted environments.

## 2. Push to a registry

AAP must pull the image from a registry reachable from the cluster or platform hosts.

```bash
podman push quay.io/<your-namespace>/eda-dynatrace-demo-ee:latest
```

## 3. Register in AAP

Use the **full image reference including tag**, for example `quay.io/<your-namespace>/eda-dynatrace-demo-ee:latest`.

### EDA — Decision environment

1. **Automation Decisions** → **Decision Environments** → **Create decision environment**
2. **Image:** `quay.io/<your-namespace>/eda-dynatrace-demo-ee:latest`
3. **Credential:** registry credential if the repository is private
4. **Organization:** your organization (for example `Default`)
5. On the rulebook activation for [`rulebooks/k8s_pod_remediation.yml`](../rulebooks/k8s_pod_remediation.yml), select this decision environment

See [Red Hat — Decision environments](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/using_automation_decisions/eda-decision-environments).

### Controller — Execution environment

1. **Automation Execution** → **Execution Environments** → **Create execution environment**
2. **Image:** same URL as above
3. **Credential:** registry credential if needed
4. Attach to job template **EDA - Remediate K8s Pod** — [aap-controller-workflow.md](aap-controller-workflow.md)

See [Red Hat — Creating execution environments](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/creating_and_using_execution_environments).


## Related docs

- [aap-setup.md](aap-setup.md) — Event Stream and rulebook activation
- [aap-controller-workflow.md](aap-controller-workflow.md) — Controller job and workflow templates
- [`collections/requirements.yml`](../collections/requirements.yml) — collection versions
