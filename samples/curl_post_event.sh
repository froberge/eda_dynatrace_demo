#!/usr/bin/env bash
# Post a test event to an AAP Token Event Stream (Dynatrace workflow uses the same URL).
#
# Usage:
#   export EVENT_STREAM_URL="https://<aap-host>/eda-event-streams/api/eda/v1/external_event_stream/<uuid>/post"
#   export EVENT_STREAM_TOKEN="<token-from-aap-credential>"
#   ./samples/curl_post_event.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD_FILE="${EVENT_PAYLOAD_FILE:-${SCRIPT_DIR}/dynatrace_eda_event.json}"

if [[ -z "${EVENT_STREAM_URL:-}" ]]; then
  echo "ERROR: Set EVENT_STREAM_URL to your AAP Event Stream POST URL." >&2
  exit 1
fi

if [[ -z "${EVENT_STREAM_TOKEN:-}" ]]; then
  echo "ERROR: Set EVENT_STREAM_TOKEN to the Token Event Stream credential value." >&2
  exit 1
fi

if [[ ! -f "${PAYLOAD_FILE}" ]]; then
  echo "ERROR: Payload file not found: ${PAYLOAD_FILE}" >&2
  exit 1
fi

export PAYLOAD_FILE POD_NAME INCIDENT_NUMBER
PAYLOAD="$(python3 <<'PY'
import json
import os

path = os.environ["PAYLOAD_FILE"]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

pod = os.environ.get("POD_NAME")
if pod:
    data["pod_name"] = pod

inc = os.environ.get("INCIDENT_NUMBER")
if inc:
    data["incident_number"] = inc

print(json.dumps(data))
PY
)"

echo "POST ${EVENT_STREAM_URL}"
HTTP_CODE="$(curl -sS -o /tmp/eda_event_stream_response.txt -w "%{http_code}" \
  -X POST "${EVENT_STREAM_URL}" \
  -H "Authorization: Bearer ${EVENT_STREAM_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")"

echo "HTTP ${HTTP_CODE}"
cat /tmp/eda_event_stream_response.txt
echo

if [[ "${HTTP_CODE}" -lt 200 || "${HTTP_CODE}" -ge 300 ]]; then
  exit 1
fi
