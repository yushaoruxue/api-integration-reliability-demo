# Acceptance Evidence

> Synthetic demo acceptance. This is not client acceptance.

## Frozen acceptance criteria

The demo passes only when all **22** checks below pass:

1. V1 ends `SUCCESS`.
2. V1 uses exactly 6 contact API calls.
3. Expired access token is refreshed exactly once.
4. 401 + 429 + timeout consume exactly 3 bounded retries.
5. V1 inserts 11 unique valid contacts.
6. One malformed contact is explicitly rejected.
7. One cross-page duplicate is skipped.
8. V1 final store contains 11 rows.
9. Re-running identical V1 creates no inserts or updates.
10. V1 rerun reports 11 unchanged rows.
11. V1 rerun dataset hash is unchanged.
12. Trace contains the 401 event.
13. Trace contains the token-refresh event.
14. Trace contains the 429 event.
15. Trace contains the timeout event.
16. Permanent 503 ends the run as `FAILED`.
17. Permanent 503 leaves only the 5 rows committed from page 1.
18. Permanent 503 exposes `http_503 page=2`.
19. Malformed response envelope ends the run as `FAILED`.
20. Malformed envelope leaves only the 5 page-1 rows.
21. V2 rule change produces 1 insert, 2 updates, 1 filtered never-seen inactive contact and 12 final rows.
22. Re-running identical V2 produces 0 inserts, 0 updates, 12 unchanged rows and the same dataset hash.

## Current result

**22/22 PASS**

Key V1 output:

```json
{
  "status": "SUCCESS",
  "contact_api_calls": 6,
  "token_refresh_count": 1,
  "bounded_retries": 3,
  "inserted": 11,
  "malformed_rejected": 1,
  "duplicate_skipped": 1,
  "final_local_rows": 11
}
```

Key permanent-failure output:

```json
{
  "status": "FAILED",
  "error": "http_503 page=2",
  "final_local_rows": 5
}
```

The committed outputs under `outputs/` were regenerated from the included public harness before publication.
