# Playbook: Beaconing and C2 channel hunting

Sources: `logs-zeek-so` (3.3M), `logs-endpoint.events.network` (378k), Sysmon
event ID 3 (network connect) and 22 (DNS query).

1. Pick the window and the internal host set. Beaconing is a property of a
   pair, so aggregate by `source.ip` + `destination.ip` + `destination.port`.
2. Score regularity, not volume: compute inter-arrival times per pair and look
   for low variance ("every 60s ± 2s"). High-byte transfers are exfil, not
   beaconing — treat them as separate questions.
3. Discount the obvious periodic legitimates before reporting: NTP, telemetry,
   update checkers, monitoring agents. Establish they are routine by showing
   the same pattern across many unrelated hosts.
4. Pivot DNS: Sysmon 22 and `dns.question.name` in endpoint network events.
   Look for high-entropy/DGA-like names, one host resolving a domain no other
   host resolves, and NXDOMAIN bursts.
5. Attribute the channel to a process: `process.name`/`process.executable` on
   the endpoint network event, or Sysmon 3. A beacon you cannot attribute to a
   process is a weaker finding — say so.
6. Cross-check the destination against `logs-suricata.alerts-so` for the same
   window, and against `threat.indicator.*` if the `logs-ti_*` feeds are
   populated here. Absence of an alert is not exoneration — signature coverage
   is always partial, and the TI feeds may be empty.
