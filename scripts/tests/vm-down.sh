#!/usr/bin/env bash
# scripts/tests/vm-down.sh <vm_name>
set -euo pipefail
VM_NAME="${1:?vm name required}"
PIDFILE="/tmp/${VM_NAME}.pid"
if [[ -f "$PIDFILE" ]]; then
  kill "$(cat "$PIDFILE")" 2>/dev/null || true
  rm -f "$PIDFILE"
fi
rm -f "/tmp/${VM_NAME}.qcow2"
