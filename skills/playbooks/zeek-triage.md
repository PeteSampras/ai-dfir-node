# Playbook: Zeek conn/dns/http/ssl triage

1. Scope the time window and host(s) under review.
2. Query `conn.log`-derived data via the Elasticsearch MCP for long-duration,
   high-byte-count, or unusual-port sessions in that window.
3. Cross-reference `dns.log` for the same hosts: newly-seen domains, high
   query volume to one domain, or NXDOMAIN bursts.
4. Cross-reference `http.log`/`ssl.log`: unusual User-Agents, JA3/JA4
   fingerprints, or SNI mismatches.
5. For any session that looks worth a closer look, pull the underlying PCAP
   via arkime-mcp's `fetch_pcap_slice` and dissect locally with `tshark`.
6. Map confirmed findings to ATT&CK techniques via attack-mcp before writing
   up.
