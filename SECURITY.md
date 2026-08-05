<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 flxk1 -->
# Security policy

## Supported versions

loomground-norm is currently pre-1.0. Security fixes are made on the latest
release line only.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
vulnerability reporting for this repository. Include the affected version or
commit, reproduction steps, impact, and any suggested mitigation. Please allow
the maintainer time to investigate before public disclosure.

This repository ships a standard-library-only **general normative-reasoning
plane** — rule extraction, obligation tracking and scheduling, and multi-hop
subsumption over the formula carrier of `loomground-deontic`. It has no network
service of its own and grows no parallel language or engine: the modal
vocabulary lives on `loomground-deontic`, composition and grounded reasoning on
`loomground-solver`. A vulnerability report against this repository is most
likely to concern the rule-extraction surface (`rule_extractor` /
`rule_extractor_llm`), the obligation runtime/scheduler state machines, the
injected ports (`loomground_norm.ports`), or the build and release pipeline;
please say which of these is affected.
