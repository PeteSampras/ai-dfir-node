# Runbook: NVIDIA L4 DirectPath I/O passthrough on ESXi (Dell R6615)

1. Confirm VT-d/IOMMU is enabled in the R6615's BIOS.
2. In the ESXi host client: **Manage → Hardware → PCI Devices** → locate the
   NVIDIA L4 → toggle it for passthrough → reboot the host (required for the
   toggle to take effect).
3. Edit the AI DFIR node VM → **Add other device → PCI device** → select the
   L4.
4. Add these advanced VM configuration parameters (spec §2):
   - `pciPassthru.use64bitMMIO = TRUE`
   - `pciPassthru.64bitMMIOSizeGB = 64`
5. Boot the VM, then inside the guest: re-run the `nvidia_gpu` Ansible role
   (`ansible-playbook -i inventory/production.ini -e @group_vars/ainode_production.yml
   site.yml --tags nvidia_gpu`) — this is the same role code Task 4 of the
   plan wrote and verified the *skip path* for; this is where its *driver
   install path* runs for the first time, against real hardware.
6. Verify: `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader`
   should print the L4 and ~24576 MiB.
7. Re-run the `llama_server` role tags — this fetches the real Unsloth GGUF
   and starts `llama-server.service` for the first time. Confirm with
   `curl http://127.0.0.1:8080/v1/models`.
