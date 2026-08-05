# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Single version source. ``pyproject.toml`` resolves ``[project].version``
from this attribute, and the package exports it as
``loomground_norm.__version__`` — one artifact, one label, nothing to drift.

Internal by design: a version constant, not a surface.
"""

__version__ = "0.1.0"  # x-release-please-version
