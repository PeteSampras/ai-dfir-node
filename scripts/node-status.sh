#!/usr/bin/env bash
# node-status.sh — health check for the AI DFIR node.
# Components not configured on this deployment report SKIP, not FAIL.
set -uo pipefail

JSON=false
[[ "${1:-}" == "--json" ]] && JSON=true

declare -A RESULT

check_gpu() {
  if [[ "${GPU_AVAILABLE:-false}" != "true" ]]; then
    RESULT[gpu]="SKIP"; return
  fi
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
    RESULT[gpu]="OK"
  else
    RESULT[gpu]="FAIL"
  fi
}

check_service() {
  local key="$1" unit="$2"
  if systemctl is-active --quiet "$unit" 2>/dev/null; then
    RESULT["$key"]="OK"
  else
    RESULT["$key"]="FAIL"
  fi
}

check_http() {
  local key="$1" url="$2"
  local code
  code="$(curl -sk -o /dev/null -m 5 -w '%{http_code}' "$url" 2>/dev/null || echo 000)"
  if [[ "$code" == "200" || "$code" == "401" ]]; then
    RESULT["$key"]="OK"
  else
    RESULT["$key"]="FAIL ($code)"
  fi
}

check_es() {
  if [[ "${ELASTICSEARCH_CONFIGURED:-false}" != "true" ]]; then
    RESULT[elasticsearch]="SKIP"; return
  fi
  check_http elasticsearch "${ELASTICSEARCH_URL:-}"
}

check_arkime() {
  if [[ "${ARKIME_CONFIGURED:-false}" != "true" ]]; then
    RESULT[arkime]="SKIP"; return
  fi
  check_http arkime "${ARKIME_BASE_URL:-}"
}

check_disk() {
  local pct
  pct="$(df --output=pcent /srv/ainode 2>/dev/null | tail -1 | tr -dc '0-9')"
  if [[ -z "$pct" ]]; then
    RESULT[disk]="FAIL (path missing)"
  elif [[ "$pct" -ge 90 ]]; then
    RESULT[disk]="FAIL (${pct}% used)"
  else
    RESULT[disk]="OK (${pct}% used)"
  fi
}

check_gpu
check_service webui open-webui.service
check_service mcpo mcpo.service
check_service attack_mcp attack-mcp.service
check_service llama_server llama-server.service
check_es
check_arkime
check_disk

overall=0
for k in "${!RESULT[@]}"; do
  [[ "${RESULT[$k]}" == FAIL* ]] && overall=1
done

if $JSON; then
  printf '{'
  first=true
  for k in "${!RESULT[@]}"; do
    $first || printf ','
    printf '"%s":"%s"' "$k" "${RESULT[$k]}"
    first=false
  done
  printf '}\n'
else
  for k in "${!RESULT[@]}"; do
    printf '%-15s %s\n' "$k" "${RESULT[$k]}"
  done
fi

exit $overall
