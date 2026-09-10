# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""The per-language modal registry holds phrases, never stray characters.

A bare string passed where ``_modal_table`` expects a tuple iterates
character by character, registering each as a modal phrase.
"""

from __future__ import annotations

from loomground_norm.rule_extractor import _PROFILES


def test_modal_registry_has_no_single_character_keys():
    stray = {code: [k for k in prof.modal_classes if len(k) == 1]
             for code, prof in _PROFILES.items()}
    stray = {c: ks for c, ks in stray.items() if ks}
    assert stray == {}
