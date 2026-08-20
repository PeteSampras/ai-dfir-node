#!/usr/bin/env bash
# Downloads the pinned Unsloth GGUF for muse glimmer. BUILD TIME ONLY.
set -euo pipefail
REPO="${1:?model repo required, e.g. unsloth/muse-glimmer-GGUF}"
FILE="${2:?model file required, e.g. muse-glimmer.Q5_K_M.gguf}"
DEST_DIR="${3:-/opt/ainode/models}"

mkdir -p "$DEST_DIR"
echo "Fetching ${REPO}/${FILE} -> ${DEST_DIR}/"
if command -v huggingface-cli >/dev/null 2>&1; then
  huggingface-cli download "$REPO" "$FILE" --local-dir "$DEST_DIR" --local-dir-use-symlinks False
else
  curl -fL "https://huggingface.co/${REPO}/resolve/main/${FILE}" -o "${DEST_DIR}/${FILE}"
fi
echo "OK: $(du -h "${DEST_DIR}/${FILE}" | cut -f1)"
