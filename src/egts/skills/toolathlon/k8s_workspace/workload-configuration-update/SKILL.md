# Workload Configuration Update

## Description

Update Kubernetes workloads from local manifests or task instructions and verify rollout/readiness through cluster state. Use this for Toolathlon k8s tasks involving Helm upgrades, ConfigMaps, preview deployments, or workload configuration changes.

## Use Cases

- Apply a specified Helm chart version while preserving local values files
- Create or update ConfigMaps and deployments for a preview environment
- Modify workload configuration and confirm pods roll out successfully
- Save a deployment verification report after configuration changes

## Workflow

### Step 1: Inspect local manifests and instructions
- **Tool**: `filesystem-list_directory`, then `filesystem-read_file` × 1-n times
- **Examples**:
  - `filesystem-list_directory({"path": "/workspace"})`
  - `filesystem-read_file({"path": "/workspace/config/redis-values.yaml"})`
- **Purpose**: Identify required namespaces, chart versions, branches, manifests, values files, and expected service URLs.

### Step 2: Inspect current workload state
- **Tool**: `k8s-get_deployments`, `k8s-get_pods` × 1-n times
- **Examples**:
  - `k8s-get_deployments({"namespace": "shared-services"})`
  - `k8s-get_pods({"namespace": "shared-services"})`
- **Purpose**: Establish the pre-change state and identify target resources.

### Step 3: Describe target resources before changing them
- **Tool**: `k8s-describe_resource` × 1-n times
- **Example**: `k8s-describe_resource({"namespace": "shared-services", "kind": "deployment", "name": "redis"})`
- **Purpose**: Capture current image, chart, labels, selectors, config references, and readiness details.

### Step 4: Apply the configuration update
- **Tool**: `terminal-run_command` × 1-n times
- **Example**: `terminal-run_command({"command": "helm upgrade redis bitnami/redis --namespace shared-services --version 22.0.0 -f config/redis-values.yaml"})`
- **Purpose**: Run the task-specific `kubectl`, `helm`, or deployment command only after local files and target resources are grounded.

### Step 5: Verify rollout and readiness
- **Tool**: `k8s-get_deployments`, `k8s-get_pods`, `k8s-describe_resource` × 1-n times
- **Examples**:
  - `k8s-get_pods({"namespace": "shared-services"})`
  - `k8s-describe_resource({"namespace": "shared-services", "kind": "pod", "name": "pod name from list"})`
- **Purpose**: Confirm updated resources are present, pods are ready, and old/stale resources are not silently left behind.

### Step 6: Save and verify a rollout report
- **Tool**: `filesystem-write_file`, then `filesystem-read_file`
- **Examples**:
  - `filesystem-write_file({"path": "/workspace/k8s_rollout_report.md", "content": "Resource | Change | Verification\n--- | --- | ---"})`
  - `filesystem-read_file({"path": "/workspace/k8s_rollout_report.md"})`
- **Purpose**: Persist the final cluster evidence for EGTS synthesis and downstream review.

## Tools Involved

`filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`, `k8s-get_deployments`, `k8s-describe_resource`, `k8s-get_pods`, `terminal-run_command`

## Tips

- Read local manifests before running cluster-changing commands
- Verify namespace and resource names before updates; k8s tasks often evaluate exact namespace targeting
- Use k8s list/describe tools for verification even when the mutation used terminal commands
- For preview deployments, include browser smoke evidence when the task exposes a URL
