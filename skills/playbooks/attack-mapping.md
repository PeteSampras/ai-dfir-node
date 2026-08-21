# Playbook: ATT&CK mapping with stated confidence

> **Requires the full build.** This playbook depends on attack-mcp, which the
> minimal Docker stack does not run. Kept here so the skill library stays whole.

1. For each confirmed behavior, call attack-mcp `search_techniques` with the
   behavior's plain-language description first.
2. Confirm the specific technique/sub-technique ID with `lookup_technique`
   before citing it — never cite an ID from memory.
3. State mapping confidence per technique: "confirmed" (direct evidence
   matches the technique's defined behavior), "likely" (strong circumstantial
   fit), or "possible" (worth noting, not enough evidence to commit to).
4. Group findings by tactic (kill-chain phase) in the final writeup, not just
   as a flat technique list.
