#!/usr/bin/env bash
# Converts a provisioned qcow2 into an OVA (streamOptimized VMDK + OVF + manifest, tarred).
set -euo pipefail
SRC_QCOW2="${1:?path to provisioned qcow2 required}"
OUT_DIR="${2:-dist}"
VM_NAME="ai-dfir-node"

mkdir -p "$OUT_DIR"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

VMDK="${WORK}/${VM_NAME}-disk1.vmdk"
qemu-img convert -O vmdk -o subformat=streamOptimized "$SRC_QCOW2" "$VMDK"

DISK_BYTES=$(qemu-img info --output=json "$VMDK" | python3 -c "import json,sys; print(json.load(sys.stdin)['virtual-size'])")

sed \
  -e "s/__VM_NAME__/${VM_NAME}/g" \
  -e "s/__DISK_BYTES__/${DISK_BYTES}/g" \
  -e "s/__DISK_FILE__/${VM_NAME}-disk1.vmdk/g" \
  "$(dirname "${BASH_SOURCE[0]}")/ovf-template.xml.j2" > "${WORK}/${VM_NAME}.ovf"

python3 -c "import xml.dom.minidom as m; m.parse('${WORK}/${VM_NAME}.ovf')" && echo "OVF XML well-formed"

(
  cd "$WORK"
  sha256_ovf=$(sha256sum "${VM_NAME}.ovf" | awk '{print $1}')
  sha256_vmdk=$(sha256sum "${VM_NAME}-disk1.vmdk" | awk '{print $1}')
  cat > "${VM_NAME}.mf" <<EOF
SHA256(${VM_NAME}.ovf)= ${sha256_ovf}
SHA256(${VM_NAME}-disk1.vmdk)= ${sha256_vmdk}
EOF
)

# Member order matters: the OVF spec requires the .ovf descriptor FIRST, and the
# manifest is meant to be readable before the (large) disk payload in a streamed
# extract -- this previously wrote .ovf, disk, .mf (manifest last), which some
# importers read strictly enough to reject. .ovf, .mf, disk is the canonical order.
tar -cf "${OUT_DIR}/${VM_NAME}.ova" -C "$WORK" "${VM_NAME}.ovf" "${VM_NAME}.mf" "${VM_NAME}-disk1.vmdk"
echo "Wrote ${OUT_DIR}/${VM_NAME}.ova ($(du -h "${OUT_DIR}/${VM_NAME}.ova" | cut -f1))"
