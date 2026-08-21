# Playbook: Baselining "normal" before calling something anomalous

The value of this cluster is its history. Most false positives here come from
calling something malicious that is simply normal-for-this-environment. Build
the baseline first, then judge.

1. Define the comparison population explicitly: same host over time, or this
   host against its peers. State which you used — they answer different
   questions.
2. Use a long lookback for the baseline (weeks), not the incident window. The
   data spans multiple monthly indices per dataset, so query the pattern
   (e.g. `*zeek-so*`) rather than one dated index.
3. For any candidate indicator — a process name, parent/child pair, port,
   destination, user/host pairing — count how often it occurs across the
   baseline population before characterising it. "First seen ever on this host"
   and "seen daily on 40 hosts" are entirely different findings.
4. Where no IOC feed is populated, rarity is the strongest signal available:
   "rare in this environment" is a legitimate finding, but frame it as such and
   do not imply external corroboration you do not have.
5. Watch for baseline poisoning: if the compromise predates your lookback, the
   malicious behaviour is *in* the baseline. Check when the pattern first
   appeared rather than assuming its presence over time means benign.
6. Report the actual counts and the window you used, so the analyst can judge
   the baseline's quality themselves.
