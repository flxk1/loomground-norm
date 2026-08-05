<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 flxk1 -->
# Releasing

Self-contained: how a release of this repository happens, without needing any
other file.

## Version axes

1. **Package/release** — `src/loomground_norm/_version.py` is the single source;
   `pyproject.toml` reads it dynamically, and `.release-please-manifest.json`
   mirrors it. Release Please bumps `_version.py` (via `extra-files` + the
   `x-release-please-version` marker) and the manifest together, so they cannot
   drift.
2. **Contract/behavior** — the extraction schema, the obligation state machine,
   and the subsumption-chain shape change only when the norm model itself
   changes, never as a side effect of a package release.

## Release flow (Release Please)

Conventional commits on `main` drive a reviewed release pull request:
`fix:` → patch, `feat:` → minor, `feat!:`/`BREAKING CHANGE:` → major;
`docs:`/`test:`/`ci:`/`chore:` do not by themselves release. Merging the release
PR updates `_version.py` + `CHANGELOG.md` and creates a `norm-vX.Y.Z` tag.
Config: `release-please-config.json`, `.release-please-manifest.json`; workflow:
`.github/workflows/release-please.yml`.

## Dependency order (this plane is downstream)

norm consumes `loomground-solver` and `loomground-deontic` (the deontic
language — O/P/F, the Hohfeld incidents, the formula carrier; this plane is the
reasoning atop it and carries no parallel copy). It can only publish once those
are published with resolvable versions; until then `requirements-dev.txt` pins
their git revisions and CI installs from those pins. norm never blocks its
upstreams; it picks up their releases through its own dependency updates.

## Distribution (git-tag pins, not PyPI)

This family is **not** published to a package index. Distribution is by **git
tag**: once a release PR merges and the `norm-vX.Y.Z` tag exists, consumers
depend on this repository with a pinned git revision, e.g.

```
loomground-norm @ git+https://github.com/flxk1/loomground-norm@norm-v0.1.0
```

placed in the consumer's `requirements-dev.txt` (or equivalent) and installed
*before* `pip install .`, so the abstract range in `pyproject.toml` is already
satisfied and pip never needs an index. This is exactly how this repository, in
turn, pins its own upstreams (see `requirements-dev.txt`).

A dormant PyPI publish job ships in `.github/workflows/release-please.yml`,
gated behind the `PYPI_PUBLISHING` repository variable. There is no PyPI account
for this project, so it stays disabled; enabling it later would require
configuring a trusted publisher first. The abstract `>=X,<Y` ranges in
`pyproject.toml` are compatibility metadata for that possible future, never a
current install path.

## Local verification before tagging

```
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
reuse lint
python3 -m build
```
