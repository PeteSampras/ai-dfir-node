#!/usr/bin/env bash
# backup.sh — nightly bundle of chat DB + audit tree + configs.
set -euo pipefail
AUDIT_ROOT="${AUDIT_ROOT:-/srv/ainode/audit}"
BACKUP_ROOT="${BACKUP_ROOT:-/srv/ainode/backup}"
CONFIG_ROOT="${CONFIG_ROOT:-/etc/ainode}"
WEBUI_DATA="${WEBUI_DATA:-/var/lib/containers/storage/volumes/open-webui-data/_data}"
KEEP="${BACKUP_KEEP:-14}"
TS="${BACKUP_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"

mkdir -p "$BACKUP_ROOT"
OUT="${BACKUP_ROOT}/ainode-backup-${TS}.tar.gz"

TMP_MANIFEST="$(mktemp)"
trap 'rm -f "$TMP_MANIFEST"' EXIT

{
  [[ -d "$AUDIT_ROOT" ]] && echo "$AUDIT_ROOT" || true
  [[ -d "$CONFIG_ROOT" ]] && echo "$CONFIG_ROOT" || true
  [[ -d "$WEBUI_DATA" ]] && echo "$WEBUI_DATA" || true
} > "$TMP_MANIFEST"

if [[ ! -s "$TMP_MANIFEST" ]]; then
  echo "backup.sh: nothing to back up, all source paths missing" >&2
  exit 1
fi

tar -czf "$OUT" -T "$TMP_MANIFEST"
echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))"

# Prune to the newest $KEEP backups
mapfile -t old < <(ls -1t "${BACKUP_ROOT}"/ainode-backup-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))")
for f in "${old[@]:-}"; do
  [[ -n "$f" ]] || continue
  rm -f "$f"
  echo "Pruned $f"
done
