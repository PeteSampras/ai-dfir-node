# Playbook: Sysmon process-tree analysis

1. Identify the seed event (process creation, network connection, or file
   event) that started the investigation.
2. Walk the process tree up (parent chain) and down (children) via
   Elasticsearch queries on ProcessGuid/ParentProcessGuid.
3. Flag living-off-the-land binaries (powershell.exe, wmic.exe, rundll32.exe,
   certutil.exe, mshta.exe) with unusual parents or command lines.
4. Check for command-line obfuscation (base64, string concatenation) and
   decode it before judging intent.
5. Correlate any outbound network connection in the tree against Zeek/Suricata
   for the same timeframe.
6. Map to ATT&CK and state confidence.
