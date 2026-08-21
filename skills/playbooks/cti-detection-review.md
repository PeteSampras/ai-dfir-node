# Playbook: Detection and threat-intel review (offline node)

Elastic's threat-intel integrations land in `logs-ti_*` (abuse.ch, Anomali,
ESET, EclecticIQ, Rapid7, MISP, OTX, plus `ti_custom`), with indicators under
`threat.indicator.*`. Whether those are actually populated varies by
deployment, so establish it before relying on them:

    GET logs-ti_*/_count

If the count is zero, the feeds are templates only. In that case threat context
comes from signatures and behaviour, and you must not claim an indicator "is
not known malicious" on the strength of an empty index — that is an absence of
data, not evidence of benignity. If the count is non-zero, match observed IPs,
domains, and hashes against `threat.indicator.*` and cite the feed each hit
came from.

1. Start from what already fired: query `so-detection` (Security Onion's rule
   corpus) and `logs-suricata.alerts-so` for the host and window in question.
   Suricata alerts carry the signature name, `rule.*`, and full ECS
   `source.*`/`destination.*` plus `destination.geo.*`/`destination.as.*`.
2. Read the signature, not just its name. Pull the matching rule from
   `so-detection` and state exactly what condition fired, so the reader can
   judge false-positive likelihood themselves.
3. Establish whether the alert is novel or routine: count the same signature
   over the preceding weeks. A signature firing thousands of times across many
   hosts is environmental noise; the same signature firing once on one host is
   the interesting case. Say which it is.
4. Pivot the alert's IPs/domains into `logs-zeek-so` and
   `logs-endpoint.events.network` for the same window to see the full session,
   not just the alerting packet.
5. For host-side corroboration, pivot to the process that owned the connection
   via `process.entity_id` (endpoint events) or Sysmon event ID 3.
6. On an air-gapped node, `logs-ti_custom_latest.indicator-3` is the designed
   home for offline/custom indicators — populating it is a configuration task,
   not something to work around with guesses.
