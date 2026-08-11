# NIST Solution Kinetics retrieval status — 2026-08-11

## Reliable boundary

This report supersedes the counts in the 2026-07-29 historical snapshot. It is based
on read-only inspection of the repaired primary registry and derived databases.

- Registry: `/Users/sad/dev/projects/radreactions/data/nist_solution/nist_archive.sqlite`
- Registry size: 182,095,872 bytes; modified 2026-08-03 16:28:46 +0200.
- Registry SHA-256: `30155ede7d7a06a1dac654ddd8801dd727345acee312505a6ffb06f1ec6c56db`.
- Derived DB: `/Users/sad/dev/projects/radreactions/data/nist_solution/nist_reactions.sqlite`
- Derived DB SHA-256: `392f6ce249b115c14faa805adc5ff2a6c75296f54315205504c87fa34168aeeb`.
- Both databases pass `PRAGMA quick_check`.

| Metric | Count |
|---|---:|
| Known Detail candidates | 23,651 |
| Legacy accepted boundary (`downloaded`, HTTP 200, archived path and SHA present) | 21,931 |
| Missing or retryable Detail candidates | 1,720 |
| Pending or retry discovery queries | 8,405 |

These counts are reliable only against the known Detail candidate set. Total NIST
coverage remains unbounded until the discovery frontier is exhausted. The legacy
accepted predicate does not replace strict response-signature and SHA validation in
the new ingestion layer.

## Current missing inventory

| Registry state | HTTP state | Count |
|---|---:|---:|
| `error` | 500 | 184 |
| `queued` | no response | 459 |
| `queued` | prior 500 | 1,072 |
| `queued` | prior 502 | 2 |
| `queued` | prior 503 | 3 |
| **Total** |  | **1,720** |

Full identifiers, NIST URLs, source paths, response SHA-256 values, timestamps, and
failures are in `current_missing_reactions_2026-08-11.csv` (1,720 data rows; file
SHA-256 `30889ca70333a2c1071bbad49292b1f58ef74e8adaab807150a684d9566cf65c`).

The discovery frontier comprises 1,515 planned product queries, 6,753 planned and 52
retry reactant queries, and 65 planned and 20 retry solvent queries.

## Reconciliation already completed

Repair run `cfb55e8e-451a-4bcd-a3d2-61d374cde290` was applied at
2026-08-03 14:27:20.913892 UTC. It requeued 1,053 global Detail rows and 811
per-search rows, and cancelled 522 unfinished quota events. No `__pending__` events
remain. Current repair dry-run proposes zero additional repairs.

Backup:
`data/nist_solution/nist_archive.sqlite.pre-refactor-20260803T160000Z.bak`, SHA-256
`1769ebfdcb424acf74d97cded350f52c7a5ce2b283ee676db8ba6bffa3f5b4a7`.

## Why prior retrieval failed

The historical evidence still supports interruption during repeated HTTP 500 retries.
The legacy implementation could record final 5xx responses as `downloaded`, infer
`empty` from non-Detail pages, and leave unfinished quota events or queue states after
interruption. The 2026-08-03 repair corrected registry state but did not complete the
remaining network retrieval.

The derived tables cannot be used as a completeness metric. They contain 22,247
reaction rows, including 316 blank reactions, and 22,254 measurements, including 612
without a rate value. The legacy parser retains rows after a Detail is requeued and
does not restrict input to an accepted registry row with the exact archived SHA.

## Current blocker and next retrieval plan

The new `nist/` layer now provides immutable attempts, content-addressed response
storage, strict classification, query-to-candidate provenance, transactional daily
caps, minimum spacing, and reconciliation. It has not yet imported the repaired legacy
registry and query provenance. Running the known legacy fetchers would reintroduce the
status and parser defects above; fetching from an unpopulated v3 registry would lose
provenance. No live request was therefore made during this refactor.

1. Add a read-only, checksummed migration from the repaired registry into a new v3
   registry; reject rows without query provenance.
2. Verify `recount()` invariants and run `reconcile --dry-run` before network access.
3. Select five stratified rows from the 1,720-row inventory. Fetch at most five, wait at
   least 180 seconds between requests, cap at 100/day, and stop immediately on a
   retryable or blocked response.
4. Review HTTP status, Detail signature, archived SHA, reaction, and measurements before
   expanding the batch.
5. Parse only `accepted` Details whose archived body matches `source_sha256`; build the
   derived database atomically into a new path.

## Verification

- NIST ingestion tests: 24 passed.
- Full repository tests at report time: 39 passed.
- No live NIST request was performed.
- No primary registry row or archived response was changed.
