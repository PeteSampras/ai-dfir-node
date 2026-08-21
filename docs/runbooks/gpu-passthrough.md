# Runbook: NVIDIA L4 DirectPath I/O passthrough on ESXi (Dell R6615)

**Confirmed 2026-08-20: cannot be prepared or baked into the OVA.** PCI
passthrough is tied to the specific physical device address on the exact
host it's configured on -- there's no OVF/OVA mechanism to declare it
portably. This is genuinely a manual, host-and-VM-level ESXi configuration
step, done entirely *after* import.

**By the time you get here, the driver and container toolkit are already
installed** -- `kmod-nvidia-open-dkms` and `nvidia-container-toolkit` were
installed during provisioning (`gpu_available: true`), *before* the OVA was
exported. The only thing that still needs the real hardware is CDI-spec
generation and live verification, both handled automatically at boot by
`nvidia-cdi-generate.service` (gated on `/dev/nvidia0` existing) --
`llama-server.service` now depends on it (`After=`+`Requires=`) so it can't
start against a stale or missing CDI spec. **No manual Ansible re-run is
needed for this step** -- there is no `--tags nvidia_gpu` in this project
(no role uses Ansible tags at all); the correct path is boot-and-verify,
not re-provision.

1. Confirm VT-d/IOMMU is enabled in the R6615's BIOS.
2. In the ESXi host client: **Manage → Hardware → PCI Devices** → locate the
   NVIDIA L4 → toggle it for passthrough → reboot the host (required for the
   toggle to take effect).
3. Edit the AI DFIR node VM → **Add other device → PCI device** → select the
   L4.
4. Add these advanced VM configuration parameters (spec §2):
   - `pciPassthru.use64bitMMIO = TRUE`
   - `pciPassthru.64bitMMIOSizeGB = 64`
5. Boot the VM. `nvidia-cdi-generate.service` fires automatically once
   `/dev/nvidia0` exists (the driver binding to the real GPU) and
   `llama-server.service` starts right after it. Verify both:
   ```
   systemctl status nvidia-cdi-generate.service   # should be active (exited), not skipped
   nvidia-smi --query-gpu=name,memory.total --format=csv,noheader   # should print the L4, ~24576 MiB
   systemctl status llama-server.service          # should be active (running)
   curl http://127.0.0.1:8080/v1/models           # confirms the model actually loaded
   ```
   If `nvidia-cdi-generate.service` shows `inactive (dead)` rather than
   `active (exited)`, its `ConditionPathExists=/dev/nvidia0` wasn't met --
   passthrough isn't actually working yet (recheck steps 1-4), not an
   Ansible problem.
6. If the model was *not* baked in at build time (see
   `docs/CONFIGURATION.md`), fetch or copy it now and start
   `llama-server.service` manually -- but the intended path is to have
   already set `model_local_path` in `ainode_production.yml` before the OVA
   was built, so this step is normally unnecessary.
