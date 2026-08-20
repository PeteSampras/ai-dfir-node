packer {
  required_plugins {
    qemu = {
      version = ">= 1.1.0"
      source  = "github.com/hashicorp/qemu"
    }
  }
}

source "qemu" "rocky9" {
  iso_url          = var.iso_url
  iso_checksum     = var.iso_checksum
  output_directory = "output-rocky9"
  vm_name          = "rocky9.qcow2"
  disk_size        = var.disk_size_mb
  memory           = var.memory_mb
  cpus             = var.cpus
  format           = "qcow2"
  accelerator      = var.accelerator
  headless         = true

  http_directory = "http"

  boot_wait = var.boot_wait
  boot_command = [
    "<up><tab> inst.text inst.ks=http://{{ .HTTPIP }}:{{ .HTTPPort }}/ks.cfg<enter>"
  ]

  ssh_username = "ainode"
  ssh_private_key_file = replace(var.ssh_public_key_path, ".pub", "")
  ssh_timeout  = "45m"

  shutdown_command = "sudo shutdown -P now"
}

build {
  sources = ["source.qemu.rocky9"]

  provisioner "shell-local" {
    inline = [
      "echo qcow2 built at output-rocky9/rocky9.qcow2"
    ]
  }
}
