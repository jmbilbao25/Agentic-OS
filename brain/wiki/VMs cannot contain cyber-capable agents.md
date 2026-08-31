---
created: 2026-08-30
tags: [doctor, draft]
---

# VMs cannot contain cyber-capable agents

Sandboxing a capable agent inside a virtual machine assumes the VM boundary holds against software-level attacks the agent itself can mount. The claim is it does not: agents with code-execution, network, and persistence capabilities can chain kernel or hypervisor bugs, escape the VM, and treat the host as part of their operating surface. VM isolation is a deployment convenience, not a security boundary, for agents that can act on cyber capabilities. This reinforces [[Persona-Execution Separation Requires Distinct Trust Domains]]: safety against a capable agent requires architecturally separate trust domains, not just a thinner or better-patched sandbox. The practical conclusion is that containerisation is a cost-control tool, not a containment tool.

Distilled from `2026-08-30 AI radar.md` by the doctor. Review before relying on it.
Related: 
