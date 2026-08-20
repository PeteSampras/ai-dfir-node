#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SH="$DIR/../backup.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/audit" "$WORK/config" "$WORK/backup"
echo "audit-canary" > "$WORK/audit/sample.jsonl"
echo "config-canary" > "$WORK/config/sample.env"

pass=0; fail=0

# Case 1: a backup is created and contains the canary files
AUDIT_ROOT="$WORK/audit" CONFIG_ROOT="$WORK/config" WEBUI_DATA="$WORK/nonexistent" \
  BACKUP_ROOT="$WORK/backup" BACKUP_TIMESTAMP="20260101T000000Z" \
  bash "$BACKUP_SH" > /dev/null

if [[ -f "$WORK/backup/ainode-backup-20260101T000000Z.tar.gz" ]]; then
  echo "PASS: backup archive created"; pass=$((pass+1))
else
  echo "FAIL: backup archive not created"; fail=$((fail+1))
fi

if tar -tzf "$WORK/backup/ainode-backup-20260101T000000Z.tar.gz" | grep -q sample.jsonl; then
  echo "PASS: archive contains audit canary file"; pass=$((pass+1))
else
  echo "FAIL: archive missing audit canary file"; fail=$((fail+1))
fi

# Case 2: pruning keeps only BACKUP_KEEP newest archives
for i in $(seq -w 1 5); do
  AUDIT_ROOT="$WORK/audit" CONFIG_ROOT="$WORK/config" WEBUI_DATA="$WORK/nonexistent" \
    BACKUP_ROOT="$WORK/backup" BACKUP_TIMESTAMP="2026010${i}T000000Z" BACKUP_KEEP=3 \
    bash "$BACKUP_SH" > /dev/null
done
count=$(ls -1 "$WORK/backup"/ainode-backup-*.tar.gz | wc -l)
if [[ "$count" -eq 3 ]]; then
  echo "PASS: pruning keeps exactly BACKUP_KEEP=3 archives"; pass=$((pass+1))
else
  echo "FAIL: expected 3 archives after pruning, found $count"; fail=$((fail+1))
fi

echo "---"
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
