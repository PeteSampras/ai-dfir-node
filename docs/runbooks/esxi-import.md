# Runbook: Importing the AI DFIR Node OVA into ESXi

Prerequisites: vSphere/ESXi web client access to the Dell R6615 host, the
built `dist/ai-dfir-node.ova` (built from a PRODUCTION-sized provisioning
run — see note below), and the NVIDIA L4 physically installed in the host.

1. **Build the production OVA**, not the local test-VM one this plan produced.
   The test VM in this plan is 4 vCPU/8GB/40GB to prove the software stack
   cheaply; production is 12 vCPU/64GB/160GB thin (spec §3). Either:
   - Re-run `packer build` with `-var 'cpus=12' -var 'memory_mb=65536'
     -var 'disk_size_mb=163840'`, provision with `group_vars/ainode_production.yml`
     (`gpu_available: true`, real ES/Arkime creds), then run
     `scripts/ova-postprocess.sh` against that disk, OR
   - Treat this plan's test OVA as a software-validation artifact only and
     rebuild fresh for the real deploy — recommended, since production
     provisioning needs a host with an actual L4 to complete the
     `nvidia_gpu`/`llama_server` role bodies (see gpu-passthrough.md).

2. In the vSphere/ESXi client: **Create/Register VM → Deploy a virtual
   machine from an OVF or OVA file** → upload `ai-dfir-node.ova`.

3. Before first boot, attach the NVIDIA L4 via DirectPath I/O — see
   `gpu-passthrough.md` — this must be done as a host-level PCI passthrough
   configuration; it cannot be baked into the OVA itself.

4. Set the VM's guest network to whatever VLAN can reach your SOC
   Elasticsearch and Arkime.

5. Boot, then SSH in and confirm: `sudo /usr/local/bin/node-status.sh`.
   With real ES/Arkime credentials configured, `elasticsearch` and `arkime`
   should now report `OK` instead of `SKIP`; with the GPU attached and
   the model fetched, `gpu` and `llama_server` should report `OK` instead
   of `SKIP`/`FAIL`.

6. Continue with `manual-validation.md` for the full success-criteria
   checklist.
