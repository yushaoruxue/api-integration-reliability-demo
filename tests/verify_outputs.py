#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = json.loads((ROOT / "outputs" / "evidence.json").read_text(encoding="utf-8"))

def s(name):
    return E[name]["summary"]

def main():
    v1, v1r = s("v1_first_run"), s("v1_rerun")
    f503, bad = s("permanent_503"), s("malformed_envelope")
    v2, v2r = s("v2_first_run"), s("v2_rerun")
    events = [x["event"] for x in E["v1_first_run"]["trace"]]

    checks = [
        ("V1 ends SUCCESS", v1["status"] == "SUCCESS"),
        ("V1 uses six contact API calls", v1["contact_api_calls"] == 6),
        ("expired token is refreshed exactly once", v1["token_refresh_count"] == 1),
        ("401/429/timeout consume three bounded retries", v1["bounded_retries"] == 3),
        ("V1 inserts 11 unique valid contacts", v1["inserted"] == 11),
        ("malformed item is rejected explicitly", v1["malformed_rejected"] == 1),
        ("cross-page duplicate is skipped", v1["duplicate_skipped"] == 1),
        ("V1 final store has 11 rows", v1["final_local_rows"] == 11),
        ("V1 rerun creates no new rows", v1r["inserted"] == 0 and v1r["updated"] == 0),
        ("V1 rerun reports 11 unchanged rows", v1r["unchanged"] == 11),
        ("V1 rerun hash is stable", v1r["final_dataset_hash"] == v1["final_dataset_hash"]),
        ("trace contains HTTP 401", "http_401" in events),
        ("trace contains token refresh", "token_refreshed" in events),
        ("trace contains HTTP 429", "http_429" in events),
        ("trace contains timeout", "timeout" in events),
        ("permanent 503 fails the run", f503["status"] == "FAILED"),
        ("permanent 503 keeps only committed page-1 rows", f503["final_local_rows"] == 5),
        ("permanent 503 exposes terminal error", f503["error"] == "http_503 page=2"),
        ("malformed envelope fails the run", bad["status"] == "FAILED"),
        ("malformed envelope keeps only committed page-1 rows", bad["final_local_rows"] == 5),
        ("V2 rule change produces 1 insert, 2 updates, 1 filtered inactive", v2["inserted"] == 1 and v2["updated"] == 2 and v2["never_seen_inactive_filtered"] == 1 and v2["final_local_rows"] == 12),
        ("V2 rerun remains idempotent", v2r["inserted"] == 0 and v2r["updated"] == 0 and v2r["unchanged"] == 12 and v2r["final_dataset_hash"] == v2["final_dataset_hash"]),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL") + " - " + name)
    print(f"{len(checks)-len(failed)}/{len(checks)} acceptance checks PASS")
    if failed:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
