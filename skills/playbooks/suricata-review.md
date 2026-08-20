# Playbook: Suricata alert review

1. Pull alerts for the window from Elasticsearch, grouped by signature and
   source/destination.
2. For each distinct signature, check whether it is a known-benign/chronic
   firer for this environment before treating it as signal.
3. For a genuine hit, correlate against Zeek conn/dns logs for the same
   5-tuple and time window to build context around the alert.
4. Pull the flagged session's PCAP via arkime-mcp and confirm the payload
   actually matches what the signature claims.
5. Map to ATT&CK and state confidence.
