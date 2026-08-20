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

variable "accelerator" {
  type    = string
  default = "kvm"
  # Override with -var accelerator=tcg on a host where the current shell
  # session predates a /dev/kvm group-membership grant (needs a fresh login
  # to pick up) -- tcg is qemu's software emulator, much slower but needs
  # no special device permissions at all.
}

variable "boot_wait" {
  type    = string
  default = "30s"
  # How long to wait after power-on before typing the boot_command over VNC.
  # Under tcg (software emulation) BIOS/GRUB rendering is much slower than
  # under kvm; too short a wait sends the boot_command keystrokes before the
  # boot menu is actually up, silently missing the kickstart entirely (the
  # installer sits at an interactive screen burning CPU with zero disk
  # writes -- easy to mistake for "still installing"). Bump higher (e.g.
  # 60s) if that happens again.
}

variable "cpu_model" {
  type    = string
  default = "max"
  # Rocky/RHEL 9 requires x86-64-v2 CPU features (SSE4.2, POPCNT, etc.) --
  # QEMU's own default CPU model doesn't provide them, which panics the
  # installer kernel ~4s into boot ("Attempted to kill init!") with NO
  # indication it's a CPU-features problem. "max" is accelerator-aware: under
  # kvm it behaves like "host" (full passthrough); under tcg it's the most
  # complete CPU QEMU's software emulation can provide. Works for both, no
  # conditional needed. Do not use "host" directly -- that flag requires kvm
  # and errors outright under tcg.
}
