variable "iso_url" {
  type    = string
  default = "https://download.rockylinux.org/pub/rocky/9/isos/x86_64/Rocky-9-latest-x86_64-minimal.iso"
}

variable "iso_checksum" {
  type    = string
  default = "file:https://download.rockylinux.org/pub/rocky/9/isos/x86_64/CHECKSUM"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/ai_dfir_node_test_ed25519.pub"
}

variable "disk_size_mb" {
  type    = number
  default = 40960
}

variable "memory_mb" {
  type    = number
  default = 8192
}

variable "cpus" {
  type    = number
  default = 4
}
