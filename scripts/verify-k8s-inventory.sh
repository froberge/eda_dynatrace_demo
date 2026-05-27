#!/usr/bin/env bash
# Verify openshift_k8s_inventory.py and log kubernetes.core k8s plugin status.
# Usage: ./scripts/verify-k8s-inventory.sh
# With cluster creds: K8S_AUTH_HOST=... K8S_AUTH_API_KEY=... ./scripts/verify-k8s-inventory.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="${ROOT}/inventory/openshift_k8s_inventory.py"
LOG_PATH="${AGENT_DEBUG_LOG_PATH:-${ROOT}/.cursor/debug-5606a3.log}"
RUN_ID="${AGENT_RUN_ID:-verify-inventory}"

export AGENT_DEBUG_LOG_PATH="${LOG_PATH}"
export AGENT_RUN_ID="${RUN_ID}"

# #region agent log
_log() {
  local hyp="$1" msg="$2" data="${3:-{}}"
  export HYP="$hyp" MSG="$msg" DATA="$data" LOG_PATH="${LOG_PATH}"
  python3 -c "
import json, os, time
entry = {
  'sessionId': '5606a3',
  'runId': os.environ.get('AGENT_RUN_ID', 'verify-inventory'),
  'hypothesisId': os.environ['HYP'],
  'location': 'scripts/verify-k8s-inventory.sh',
  'message': os.environ['MSG'],
  'data': json.loads(os.environ.get('DATA', '{}')),
  'timestamp': int(time.time() * 1000),
}
with open(os.environ['LOG_PATH'], 'a') as f:
  f.write(json.dumps(entry) + '\n')
" 2>/dev/null || true
}
# #endregion

echo "Checking ${SCRIPT} ..."

if [[ ! -x "${SCRIPT}" ]]; then
  chmod +x "${SCRIPT}"
fi

python3 -m py_compile "${SCRIPT}"
_log "H1" "inventory script syntax ok" "{}"

if command -v ansible-galaxy >/dev/null 2>&1; then
  KC_VER="$(ansible-galaxy collection list kubernetes.core 2>/dev/null | awk '/kubernetes\.core/ {print $2; exit}')"
  _log "H1" "kubernetes.core version on controller" "{\"version\":\"${KC_VER:-unknown}\"}"
  if python3 -c "
import importlib.util
spec = importlib.util.find_spec('ansible_collections.kubernetes.core.plugins.inventory.k8s')
exit(0 if spec else 1)
" 2>/dev/null; then
    _log "H1" "k8s inventory plugin present" "{\"present\":true}"
  else
    _log "H1" "k8s inventory plugin present" "{\"present\":false,\"note\":\"removed in kubernetes.core 6.0; use openshift_k8s_inventory.py\"}"
  fi
fi

if [[ -n "${K8S_AUTH_HOST:-}" && -n "${K8S_AUTH_API_KEY:-}" ]]; then
  echo "Running --list with provided K8S_AUTH_* (no token logged) ..."
  "${SCRIPT}" --list | python3 -c "import json,sys; d=json.load(sys.stdin); print('groups:', len(d.get('all',{}).get('children',[]))); print('hosts:', len(d.get('_meta',{}).get('hostvars',{})))"
  _log "H3" "live inventory list succeeded" "{}"
else
  echo "Skip live API test (set K8S_AUTH_HOST and K8S_AUTH_API_KEY to test against cluster)."
  _log "H3" "live inventory list skipped" "{\"reason\":\"no K8S_AUTH_* env\"}"
fi

echo "Done. Logs: ${LOG_PATH}"
