# Playbook: PCAP walkthrough (Arkime pull -> local dissection)

1. Use arkime-mcp `search_sessions` to locate the session(s) of interest by
   expression and time range.
2. Use `get_spi_data`/`unique_values` to characterize the traffic before
   pulling any raw bytes.
3. Use `fetch_pcap_slice` to pull the session into `/srv/ainode/scratch/`.
4. Dissect locally: `tshark -r <file> -q -z conv,tcp` for conversations,
   `tshark -r <file> -Y <filter>` for targeted extraction, `capinfos` for
   file-level metadata.
5. For encrypted traffic, note JA3/JA3S/JA4 rather than attempting decryption
   you don't have keys for.
6. Delete the pulled PCAP slice from scratch when the investigation step is
   done — scratch is not a case archive.
