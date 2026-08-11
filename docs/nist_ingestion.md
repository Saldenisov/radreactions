# NIST ingestion boundary

`nist/` separates immutable retrieval evidence from mutable derived state:

`query → candidate Detail URL → reservation → immutable response attempt → canonical Detail state`

- Raw HTTP bodies are content-addressed by SHA-256 in archive storage. Existing blobs are verified, never overwritten.
- `accepted` requires HTTP 200 and two independent NIST Detail signatures.
- `confirmed_empty` requires HTTP 200 and explicit zero-record text.
- 5xx and known backend/Cloudflare failures are `retryable`; 403/429 are `blocked`.
- `details.accepted_attempt_id` and `source_sha256` must point to an accepted immutable attempt. `recount()` enforces this invariant.
- Stale reservations are visible through `reconcile --dry-run`; `--apply` appends a retryable attempt and removes only the unfinished reservation.
- Daily caps and minimum request spacing are enforced transactionally across separate CLI invocations.

No command performs network access except `fetch-details`.

```bash
python -m nist.cli reconcile \
  --registry /data/nist_registry.sqlite \
  --archive-root /data/nist_raw \
  --dry-run

python -m nist.cli fetch-details \
  --registry /data/nist_registry.sqlite \
  --archive-root /data/nist_raw \
  --limit 5 --min-delay 180 --daily-limit 100 \
  --stop-on-first-retryable
```

Derived parsing must select only `details.status = 'accepted'` and only files whose SHA-256 matches `details.source_sha256`.
