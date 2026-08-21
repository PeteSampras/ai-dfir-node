# Playbook: Windows logon and privilege triage

Source: `logs-system.security`, with `winlog.*` fields (`winlog.event_id`,
`winlog.logon.id`, `winlog.computer_name`, `winlog.event_data.*`).

Which event IDs are collected depends on the host's audit policy, and differs
between environments. Confirm coverage before reasoning from absence:

    GET *system.security*/_search
    {"size":0,"aggs":{"e":{"terms":{"field":"winlog.event_id","size":20}}}}

This matters most for 4625 (failed logon): if it is not being collected, a
brute-force analysis built on failure counts is unsound, and the honest finding
is "cannot assess — 4625 not collected", not "no brute force observed".

1. Scope to host and window using `winlog.computer_name` and `@timestamp`.
2. For each 4624, record `winlog.event_data.LogonType` and the account. Type 3
   (network) and type 10 (RemoteInteractive/RDP) are the lateral-movement
   relevant ones; type 5/4 are service/batch and usually routine.
3. Correlate 4624 with 4672 ("special privileges assigned") on the same
   `winlog.logon.id`. A network logon that immediately receives sensitive
   privileges is worth explaining.
4. Use `winlog.logon.id` as the join key to tie a logon session to the
   processes it spawned (4688), rather than joining loosely on time.
5. Treat 4798/4799 (local user and group membership enumeration) as recon
   signals — they are noisy on their own, so only raise them when they cluster
   with a fresh logon or an unusual parent process.
6. 5379 (Credential Manager read) and 4673 (privileged service call) support a
   credential-access narrative; cite the specific event and account rather than
   asserting credential theft generally.
