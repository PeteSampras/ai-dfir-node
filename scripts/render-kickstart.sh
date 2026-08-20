#!/usr/bin/env bash
# Generates the test SSH keypair (if missing) and renders packer/http/ks.cfg
# from ks.cfg.tmpl with the real public key baked in. Idempotent -- safe to
# run before every build. ks.cfg itself is gitignored on purpose: it always
# carries a real key, so it must never be the thing that's committed.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY_PATH="${AINODE_TEST_SSH_KEY:-$HOME/.ssh/ai_dfir_node_test_ed25519}"

if [[ ! -f "$KEY_PATH" ]]; then
  echo "Generating test SSH keypair at ${KEY_PATH}"
  ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "ai-dfir-node-test-$(hostname)" >/dev/null
fi

PUB_KEY="$(cat "${KEY_PATH}.pub")"

python3 - "$REPO_ROOT" "$PUB_KEY" <<'EOF'
import sys
import pathlib

repo_root, pub_key = sys.argv[1], sys.argv[2]
tmpl = pathlib.Path(repo_root) / "packer" / "http" / "ks.cfg.tmpl"
out = pathlib.Path(repo_root) / "packer" / "http" / "ks.cfg"
out.write_text(tmpl.read_text().replace("__SSH_PUBLIC_KEY__", pub_key))
comment = pub_key.split()[-1] if pub_key.split() else "(unknown)"
print(f"Rendered {out} with key comment '{comment}'")
EOF

echo "Public key path for Packer: ${KEY_PATH}.pub"
