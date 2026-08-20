#!/usr/bin/env bash
# Fetches and pins the MITRE ATT&CK Enterprise STIX bundle for offline use.
# Run at BUILD time only — never at runtime (spec: air-gap safety).
set -euo pipefail
VERSION="${1:-17.1}"
OUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/mcp-servers/attack-mcp/data/enterprise-attack.json"
URL="https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-${VERSION}.json"

echo "Fetching ATT&CK Enterprise v${VERSION} -> ${OUT}"
curl -fsSL "$URL" -o "$OUT"
python3 -c "import json,sys; json.load(open('${OUT}'))" && echo "OK: valid JSON, $(du -h "$OUT" | cut -f1)"
