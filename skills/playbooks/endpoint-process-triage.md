# Playbook: Elastic Defend endpoint process triage

Source: `logs-endpoint.events.process` (568k docs here), with sibling datasets
`.file`, `.network`, `.registry`, `.library`, `.security`. These carry richer
fields than Sysmon — use them when the host runs Elastic Defend.

1. Seed from the process of interest and use `process.Ext.ancestry` (an ordered
   array of ancestor entity IDs) to reconstruct the full tree in one query,
   rather than walking parents one hop at a time.
2. Check code signing on both process and parent:
   `process.code_signature.trusted`, `.subject_name`, `.status`, and the
   `process.Ext.code_signature.*` array. Unsigned or untrusted-signature
   binaries in system paths are the high-value finding.
3. Compare `process.executable` against its expected path. A correctly-named
   binary in the wrong directory is a masquerading indicator (and cite the path
   you observed).
4. Read `process.command_line` and `process.args` for LOLBin usage —
   rundll32, regsvr32, mshta, certutil, wmic, msbuild — and judge on the
   arguments, not the binary name alone.
5. Join to `logs-endpoint.events.network` on `process.entity_id` for that
   process's own connections, and to `.file`/`.registry` for what it wrote or
   persisted.
6. Where the host has both Defend and Sysmon, confirm the finding in each; if
   they disagree, report the disagreement rather than picking the convenient one.
