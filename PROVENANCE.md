# Provenance and Evidence Boundary

## Classification

**Synthetic / internal proof. Not a client case.**

This public package is a sanitized, self-contained evidence surface. It does not expose personal execution infrastructure, browser/session internals, credentials, private orchestration, client code or unrelated private repositories.

## Earlier internal evidence reused

An internal synthetic capability spike on **2026-09-12** demonstrated the bounded connector loop:

```text
authentication
→ paginated fetch
→ normalization
→ idempotent sync
→ error handling
→ retry
→ verification
→ client-style rule change
→ rerun
```

That spike recorded:

- 401 access-token expiry followed by refresh;
- 429 with `Retry-After`;
- an actual timeout event inside the synthetic harness followed by bounded retry;
- 11 unique valid rows from a 3-page fixture;
- one malformed record isolated;
- one cross-page duplicate skipped;
- identical rerun with 0 inserts / 0 updates and a stable dataset hash;
- permanent 503 and malformed-envelope runs marked `FAILED`, not silently successful;
- a V2 business-rule change that stayed idempotent on rerun.

That earlier evidence was synthetic and did **not** establish any named vendor's production experience.

## What is new in this public proof

The buyer-facing package narrows those already-demonstrated mechanics into a small inspectable scenario and independently re-executes the same responsibility class with sanitized fixtures.

The included public harness, outputs and 22 acceptance assertions were run again for this package.

## Evidence boundary

Supported claim:

> bounded, read-oriented API/SaaS integration mechanics can be implemented with explicit validation, token refresh, pagination, rate-limit handling, bounded retry, idempotency, failure states and verification.

Not supported:

- production expertise with HubSpot, Salesforce, Amazon, Twitch, Clio or any other named vendor;
- production credential/secret lifecycle ownership;
- destructive writes or financial operations;
- high-scale webhook/event delivery;
- 24/7 operational responsibility;
- real client history.

Vendor-specific behavior must be checked from official documentation and the buyer's authorized environment before commitment.
