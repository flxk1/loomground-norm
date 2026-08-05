# repo-topology.md — staged diff for loomground-norm

Not applied to `RVND/docs/loomground-proposals/repo-topology.md` — this
staging pass is read-only on rvnd. Land this diff when the real extraction
(see the landing plan in the design report) reaches step 2.

## Repo table — new row

```diff
 | `solver` | reasoning | 5D/nD reasoning, Loomground evaluation |
+| `loomground-deontic` | normative language | the general deontic language and algebra: the three modal operators (O/P/F), the eight Hohfeld incidents, the formula carrier and grammar — no reasoning, no rule extraction |
+| `loomground-norm` | normative reasoning | rule extraction, obligation tracking, multi-hop subsumption — the general norm-reasoning substrate between deontic/solver and any normative domain (AI governance, contracts, legal) |
 | `versum` | knowledge | the 5D+nD knowledge plane |
```

## Contracts between repos — new bullet

```diff
 - **Library planes → rvnd:** consumed as packages through `server/src/workspaces/adapters/`
   only. No deep imports past the adapter seam in either direction.
+- **norm → deontic:** `loomground-norm` consumes `loomground-deontic` as a
+  library dependency for the deontic language itself — the three modal
+  operators (O/P/F), the eight Hohfeld incidents, and the formula carrier.
+  Norm carries no parallel copy of that model; it adds only the reasoning
+  layer (extraction, obligation state, subsumption) and the one adapter
+  deontic declines to own (lifting a `RuleFacet` into deontic's formula, and
+  attaching deontic's incidents to a `RuleFacet` in place).
+- **norm → solver:** `loomground-norm` consumes `loomground_solver.dimensions`,
+  `loomground_solver.temporal`, and `loomground_solver.norm_contract` as a
+  library dependency — the same relationship `loomground-solver` has to
+  `loomground-governance`. It carries no governance, no jurisdiction, no
+  legal-entity map of its own; a host injects those through
+  `loomground_norm.ports` (`SourceInstrument`, `AuditSink`, `LegalSystemPack`).
+  The direction is one-way: norm never imports rvnd, governance, or any
+  legal-domain package. rvnd consumes `loomground-norm` the same way it
+  consumes solver/versum — through `server/src/workspaces/adapters/norm/`,
+  no deep imports past that seam.
```
