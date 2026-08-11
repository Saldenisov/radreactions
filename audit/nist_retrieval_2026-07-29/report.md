# NIST Solution Kinetics retrieval audit — 2026-07-29

> Historical snapshot. The registry was repaired on 2026-08-03; current counts and
> blockers are documented in `current_status_2026-08-11.md`. This file is preserved
> unchanged otherwise to retain the original audit trail.

## Scope and provenance

- Audited ignored corpus: `/Users/sad/dev/projects/radreactions/data/nist_solution/`
- Corpus size: 1.6 GB; 33,916 files.
- Registry: `nist_archive.sqlite`, 179,822,592 bytes, modified 2026-07-02 12:14:59 +0200.
- Parsed database: `nist_reactions.sqlite`, 271,142,912 bytes, built 2026-06-29 07:24:01 UTC.
- Registry SHA-256: `bd67c32e62d56a200c34cd68a2a9aa99844530e1cc66318e21c0546182848e52`.
- Parsed DB SHA-256: `745773e5946d658337d255913a938714a8a4608cc997ae45f00cce574d8e7cc0`.
- Both SQLite databases passed `PRAGMA quick_check`.
- No primary corpus file or registry row was changed.

## Established counts

| Metric | Prior corpus | After validated audit batch |
|---|---:|---:|
| Known candidate Detail URLs | 23,651 | 23,651 |
| Valid HTTP 200 Detail pages | 21,911 | 21,912 |
| HTTP 200 pages with nonblank parsed reaction | 21,881 | 21,882 |
| Known candidates lacking usable reaction | 1,770 | 1,769 |
| Pending/retry discovery queries | 8,405 | 8,405 |

“All NIST reactions” remains unbounded because 8,405 discovery queries have not run: 1,515 product, 6,805 reactant, and 85 solvent queries. Exact completeness is established only against the 23,651 currently known Detail candidates.

The prior `nist_reactions.sqlite` headline count of 22,169 reactions is not reliable. Only 21,881 rows combine HTTP 200 provenance with nonblank reaction text. The database also contains 22,199 measurements, including 611 without a rate value.

## Missing inventory

Baseline 1,770 candidates:

| Issue | Count |
|---|---:|
| HTTP error mislabeled `empty` | 737 |
| Queued | 483 |
| HTTP error mislabeled `downloaded` | 323 |
| Registry error | 197 |
| HTTP 200 parse gap | 30 |

All 737 `empty` rows have HTTP 500, so none is verified empty. The 323 mislabeled downloads comprise 317 HTTP 500, 3 HTTP 502, and 3 HTTP 503 pages.

Full identifiers, NIST URLs, statuses, failures, timestamps, saved paths, and parse outcomes: `missing_reactions.csv`.

## Why prior retrieval stopped

Direct observations:

- Last successful request: 2026-07-02 09:14:45 UTC.
- Next recorded request returned HTTP 500 at 10:14:54 UTC.
- A request for `1970AMI/TRE3670-3674:4` was reserved at 10:14:59 UTC but never finalized.
- A second HTTP 500 page for that request was saved at 10:45:00 UTC but never registered.
- Lock marker records PID 38062 from 2026-07-02 09:14:20 UTC. The lock file is not deleted by normal shutdown, so file presence alone does not prove a live process.
- No retained terminal log or exit status establishes the final termination signal.

Code-level causes:

- Default retry delay is 1,800 s after HTTP 5xx.
- After retries are exhausted, `_fetch_with_retries` returns the final 5xx response.
- `_process_detail` then records that response and marks it `downloaded`.
- Hole mode labels any non-detail response `empty`, including HTTP 500 pages.
- Interrupted requests leave `__pending__` quota events.
- Search queue contains stale `running` rows. One H2O solvent query failed with `AttributeError("'Namespace' object has no attribute 'expand_search'")`.

Evidence therefore supports interruption during repeated NIST HTTP 500 retries. Exact external termination cause is undocumented.

## Validated retrieval

One baseline queued URL was fetched through the repository’s allowlisted NIST client:

- URL: `https://kinetics.nist.gov/solution/Detail?id=1990BIG/CRA619-622:2`
- HTTP: 200
- Fetched: 2026-07-29 09:18:38.868977 UTC
- Response-body SHA-256: `94a109aece83134739db0e212fb4e120aadd86469c03598e6ff0b3c8451da582`
- Parsed reaction: `C6H5CO-C6H4CH2SO3- + C6H5COHC6H4CH2SO3- -> dimer`
- Solvent: H2O
- Rate constant: `6.3E6`
- Reaction order: 2
- Raw NIST pH: `-997`; preserved without interpretation.

Primary registry was not updated. Result is isolated in `raw/` and summarized in `validated_batch.json`.

## Blockers

- Complete retrieval code, registry, and 1.6 GB corpus exist only as ignored/untracked changes in the dirty primary checkout.
- Delegated worktree contains neither archive nor advanced parser/queue scripts.
- Primary `main` is 66 commits ahead and 24 behind `origin/main`; retrieval work is not reproducible from Git.
- Registry status semantics admit HTTP errors as completed data.
- Discovery frontier is incomplete; total NIST reaction count cannot yet be claimed.

## Next retrieval plan

1. Snapshot databases, scripts, schema, checksums, and command configuration without changing the corpus.
2. Fix status handling in a clean worktree:
   - accept `downloaded` only for HTTP 200 plus Detail-page signature;
   - keep 5xx as retryable errors;
   - never infer `empty` from 5xx;
   - finalize or cancel pending events in `finally`;
   - recover stale queue states explicitly.
3. Reconcile registry in dry-run mode. Reclassify 1,257 mislabeled/error rows only after backup and review.
4. Retry five stratified candidates into a new directory. Use one request per 180 s, maximum 100/day, and stop on first 5xx with 12 h backoff.
5. Require HTTP 200, Detail signature, nonblank reaction, and parsed measurement review before registry import.
6. Process 72 retry discovery queries before 8,333 planned queries. Preserve query fields, source URL, timestamps, response SHA-256, and outcome.
7. Rebuild parsed DB atomically only after batch validation; never overwrite archived HTML.

## Verification

- Targeted tests: 15 passed.
- Files created only under `audit/nist_retrieval_2026-07-29/`.
- No commit or push.
