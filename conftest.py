# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Dev-only import shim for the sibling-repository layout.

The Loomground family is a set of sibling repositories developed side by side.
When they are pip-installed (CI, a release, an end user) this file does nothing:
every dependency imports normally and the shim never triggers. It exists purely
so that a fresh local checkout with the siblings present — but not installed —
can run ``pytest`` with no install dance, sidestepping editable-install
fragility. For each dependency that fails to import, and only then, its
``<family root>/loomground-<name>/src`` directory is prepended to ``sys.path``.
The siblings are checked out beside this one, so the family root is this
checkout's parent — the same resolution ``loomground-legal``'s shim uses.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent  # loomground-norm/.. -> family root (siblings live here)

# This package's own src, so a fresh checkout runs without an install step.
if importlib.util.find_spec("loomground_norm") is None:
    _self_src = _HERE / "src"
    if _self_src.is_dir() and str(_self_src) not in sys.path:
        sys.path.insert(0, str(_self_src))

# (import name, checkout directory relative to the family root)
# loomground-governance is not a direct dependency: loomground_solver imports
# loomground_governance at module import time, so a solver-from-checkout run
# needs it on the path too — a solver-level fact, resolved transitively by a
# pinned install.
_SIBLINGS = [
    ("loomground_solver", "loomground-solver"),
    ("loomground_deontic", "loomground-deontic"),
    ("deontic", "loomground-deontic"),
    ("loomground_governance", "loomground-governance"),
]

for _mod, _rel in _SIBLINGS:
    if importlib.util.find_spec(_mod) is not None:
        continue
    _src = _ROOT / _rel / "src"
    if _src.is_dir():
        _p = str(_src)
        if _p not in sys.path:
            sys.path.insert(0, _p)
