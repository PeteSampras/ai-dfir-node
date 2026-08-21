# Playbook: PowerShell activity triage

Sources: `logs-windows.powershell_operational` and `logs-windows.powershell`.
Records carry `winlog.event_id`, `winlog.user.name`/`.domain`,
`winlog.computer_name`, and `winlog.record_id`.

1. Confirm what logging is actually on before interpreting absence: script
   block logging (4104), module logging (4103), and transcription each produce
   different events. If 4104 is absent, say so — "no malicious script seen" is
   not a supportable claim when the logging that would show it is off.
2. Retrieve script block text for the window and read it. Decode base64
   (`-enc`, `-EncodedCommand`) and reverse simple obfuscation (string
   concatenation, backtick insertion, char arrays) before judging intent.
3. Flag download-and-execute patterns: `Net.WebClient`, `Invoke-WebRequest`,
   `IEX`/`Invoke-Expression`, `DownloadString`, `Start-BitsTransfer`.
4. Tie each script block to its host process via `process.pid` +
   `winlog.computer_name`, then walk the parent chain in Sysmon (event ID 1) or
   `logs-endpoint.events.process`. PowerShell spawned by Office or a browser is
   a much stronger signal than PowerShell spawned by explorer.exe.
5. Correlate any outbound address in the script against `logs-zeek-so` and
   `logs-endpoint.events.network` for the same window to confirm the connection
   actually happened rather than just being attempted.
6. State confidence, and quote the decoded script text you based it on.
