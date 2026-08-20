#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUBS="$DIR/stubs"
STATUS_SH="$DIR/../node-status.sh"

pass=0
fail=0

assert_contains() {
  local haystack="$1" needle="$2" desc="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    echo "PASS: $desc"; pass=$((pass+1))
  else
    echo "FAIL: $desc"; echo "  expected to contain: $needle"; echo "  got: $haystack"; fail=$((fail+1))
  fi
}

# Case 1: nothing configured (matches the real test VM) -> everything SKIP/OK, exit 1 (llama_server/mcpo/webui/attack_mcp all down)
set +e
out=$(PATH="$STUBS:$PATH" GPU_AVAILABLE=false ELASTICSEARCH_CONFIGURED=false ARKIME_CONFIGURED=false \
  FAKE_ACTIVE_UNITS="" bash "$STATUS_SH")
rc=$?
set -e
assert_contains "$out" "gpu             SKIP" "gpu SKIP when not configured"
assert_contains "$out" "elasticsearch   SKIP" "elasticsearch SKIP when not configured"
[[ $rc -eq 1 ]] && { echo "PASS: exit 1 when services down"; pass=$((pass+1)); } || { echo "FAIL: expected exit 1, got $rc"; fail=$((fail+1)); }

# Case 2: everything configured and healthy -> all OK, exit 0
set +e
out=$(PATH="$STUBS:$PATH" GPU_AVAILABLE=true ELASTICSEARCH_CONFIGURED=true ARKIME_CONFIGURED=true \
  ELASTICSEARCH_URL=https://es.test ARKIME_BASE_URL=https://arkime.test \
  FAKE_ACTIVE_UNITS="open-webui.service mcpo.service attack-mcp.service llama-server.service" \
  bash "$STATUS_SH")
rc=$?
set -e
assert_contains "$out" "gpu             OK" "gpu OK when configured and nvidia-smi succeeds"
assert_contains "$out" "elasticsearch   OK" "elasticsearch OK when reachable"
[[ $rc -eq 0 ]] && { echo "PASS: exit 0 when all healthy"; pass=$((pass+1)); } || { echo "FAIL: expected exit 0, got $rc"; fail=$((fail+1)); }

# Case 3: JSON output is valid JSON
out=$(PATH="$STUBS:$PATH" GPU_AVAILABLE=false ELASTICSEARCH_CONFIGURED=false ARKIME_CONFIGURED=false \
  FAKE_ACTIVE_UNITS="" bash "$STATUS_SH" --json || true)
echo "$out" | python3 -c "import json,sys; json.load(sys.stdin)" \
  && { echo "PASS: --json output is valid JSON"; pass=$((pass+1)); } \
  || { echo "FAIL: --json output is not valid JSON"; fail=$((fail+1)); }

echo "---"
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
