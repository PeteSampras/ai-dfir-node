#!/usr/bin/env bash
# scripts/tests/vm-up.sh <vm_name> <ssh_key_path>
set -euo pipefail
VM_NAME="${1:?vm name required}"
SSH_KEY="${2:?ssh key path required}"
QCOW2="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/packer/output-rocky9/rocky9.qcow2"
RUN_QCOW2="/tmp/${VM_NAME}.qcow2"

cp "$QCOW2" "$RUN_QCOW2"

qemu-system-x86_64 \
  -name "$VM_NAME" \
  -machine accel=kvm \
  -m 8192 -smp 4 \
  -drive "file=${RUN_QCOW2},format=qcow2,if=virtio" \
  -netdev user,id=net0,hostfwd=tcp::2222-:22 \
  -device virtio-net-pci,netdev=net0 \
  -display none -daemonize \
  -pidfile "/tmp/${VM_NAME}.pid"

for _ in $(seq 1 60); do
  if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
     -p 2222 ainode@127.0.0.1 true 2>/dev/null; then
    echo "127.0.0.1"
    exit 0
  fi
  sleep 5
done
echo "vm-up: SSH never came up" >&2
exit 1
