#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "samples" / "scenario.json"
OUT = ROOT / "outputs"
WORK = ROOT / ".demo_tmp"

class ApiError(Exception):
    def __init__(self, status: int, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after

class EnvelopeError(Exception):
    pass

@dataclass
class Counters:
    contact_api_calls: int = 0
    token_refresh_count: int = 0
    bounded_retries: int = 0

class MockSaaS:
    """Synthetic OAuth + paginated CRM surface with deterministic faults."""
    def __init__(self, pages: dict[str, list[dict]], scenario: str):
        self.pages = pages
        self.scenario = scenario
        self.token = "access-v1"
        self.attempts: dict[int, int] = {}
        self.counters = Counters()

    def refresh_access_token(self) -> str:
        self.counters.token_refresh_count += 1
        self.token = "access-v2"
        return self.token

    def get_contacts(self, page: int, access_token: str):
        self.counters.contact_api_calls += 1
        self.attempts[page] = self.attempts.get(page, 0) + 1
        attempt = self.attempts[page]

        if self.scenario in {"v1", "v2"}:
            if page == 2 and attempt == 1 and access_token == "access-v1":
                raise ApiError(401, "expired_access_token")
            if page == 2 and attempt == 2:
                raise ApiError(429, "rate_limited", retry_after=0.02)
            if page == 3 and attempt == 1:
                raise TimeoutError("synthetic_client_timeout")

        if self.scenario == "permanent_503" and page == 2:
            raise ApiError(503, "upstream_unavailable")

        if self.scenario == "malformed_envelope" and page == 2:
            return "{not-valid-json-envelope"

        return {
            "items": self.pages[str(page)],
            "next_page": page + 1 if str(page + 1) in self.pages else None,
        }

class Store:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS contacts(
               contact_id TEXT PRIMARY KEY,
               name TEXT NOT NULL,
               email TEXT NOT NULL,
               status TEXT NOT NULL,
               updated_at TEXT NOT NULL)"""
        )
        self.conn.commit()

    def exists(self, contact_id: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM contacts WHERE contact_id=?", (contact_id,)
        ).fetchone() is not None

    def upsert(self, item: dict) -> str:
        current = self.conn.execute(
            "SELECT name,email,status,updated_at FROM contacts WHERE contact_id=?",
            (item["contact_id"],),
        ).fetchone()
        values = (item["name"], item["email"], item["status"], item["updated_at"])
        if current is None:
            self.conn.execute(
                "INSERT INTO contacts(contact_id,name,email,status,updated_at) VALUES(?,?,?,?,?)",
                (item["contact_id"], *values),
            )
            return "inserted"
        if tuple(current) == values:
            return "unchanged"
        self.conn.execute(
            "UPDATE contacts SET name=?,email=?,status=?,updated_at=? WHERE contact_id=?",
            (*values, item["contact_id"]),
        )
        return "updated"

    def commit(self):
        self.conn.commit()

    def rows(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT contact_id,name,email,status,updated_at FROM contacts ORDER BY contact_id"
        )
        keys = ["contact_id", "name", "email", "status", "updated_at"]
        return [dict(zip(keys, row)) for row in cur.fetchall()]

def digest(rows: list[dict]) -> str:
    body = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()

def sync_once(pages: dict[str, list[dict]], scenario: str, db: Path, active_only_new: bool):
    api, store = MockSaaS(pages, scenario), Store(db)
    metrics = {
        "inserted": 0, "updated": 0, "unchanged": 0,
        "malformed_rejected": 0, "duplicate_skipped": 0,
        "never_seen_inactive_filtered": 0,
    }
    seen, ledger, trace = set(), [], []
    access_token, page = api.token, 1
    status, error, max_attempts = "SUCCESS", None, 3

    try:
        while page is not None:
            attempt = 0
            while True:
                attempt += 1
                try:
                    payload = api.get_contacts(page, access_token)
                    if not isinstance(payload, dict) or "items" not in payload:
                        raise EnvelopeError(f"malformed_envelope page={page}")
                    trace.append({"page": page, "attempt": attempt, "event": "response_ok"})
                    break
                except ApiError as exc:
                    trace.append({"page": page, "attempt": attempt, "event": f"http_{exc.status}"})
                    if exc.status == 401 and api.counters.token_refresh_count == 0:
                        access_token = api.refresh_access_token()
                        api.counters.bounded_retries += 1
                        trace.append({"page": page, "attempt": attempt, "event": "token_refreshed"})
                        continue
                    if exc.status == 429 and attempt < max_attempts:
                        api.counters.bounded_retries += 1
                        time.sleep(exc.retry_after or 0)
                        continue
                    if 500 <= exc.status < 600 and attempt < max_attempts:
                        api.counters.bounded_retries += 1
                        time.sleep(0.01)
                        continue
                    raise ApiError(exc.status, f"http_{exc.status} page={page}")
                except TimeoutError:
                    trace.append({"page": page, "attempt": attempt, "event": "timeout"})
                    if attempt < max_attempts:
                        api.counters.bounded_retries += 1
                        time.sleep(0.01)
                        continue
                    raise

            for index, item in enumerate(payload["items"], start=1):
                required = ("contact_id", "name", "email", "status", "updated_at")
                if any(not item.get(k) for k in required):
                    metrics["malformed_rejected"] += 1
                    ledger.append({"page": page, "index": index, "reason": "missing_required_field"})
                    continue
                cid = item["contact_id"]
                if cid in seen:
                    metrics["duplicate_skipped"] += 1
                    continue
                seen.add(cid)
                if active_only_new and item["status"] == "INACTIVE" and not store.exists(cid):
                    metrics["never_seen_inactive_filtered"] += 1
                    continue
                metrics[store.upsert(item)] += 1

            store.commit()
            page = payload.get("next_page")
    except (ApiError, TimeoutError, EnvelopeError) as exc:
        status, error = "FAILED", str(exc)

    rows = store.rows()
    summary = {
        "scenario": scenario,
        "status": status,
        "error": error,
        "contact_api_calls": api.counters.contact_api_calls,
        "token_refresh_count": api.counters.token_refresh_count,
        "bounded_retries": api.counters.bounded_retries,
        **metrics,
        "final_local_rows": len(rows),
        "final_dataset_hash": digest(rows),
    }
    return {"summary": summary, "trace": trace, "error_ledger": ledger, "rows": rows}

def write_csv(path: Path, rows: list[dict]):
    keys = ["contact_id", "name", "email", "status", "updated_at"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

def main():
    data = json.loads(SCENARIO.read_text(encoding="utf-8"))
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir()
    OUT.mkdir(exist_ok=True)

    primary = WORK / "primary.sqlite"
    evidence = {}
    evidence["v1_first_run"] = sync_once(data["v1_pages"], "v1", primary, False)
    evidence["v1_rerun"] = sync_once(data["v1_pages"], "v1", primary, False)
    evidence["v2_first_run"] = sync_once(data["v2_pages"], "v2", primary, True)
    evidence["v2_rerun"] = sync_once(data["v2_pages"], "v2", primary, True)
    evidence["permanent_503"] = sync_once(data["v1_pages"], "permanent_503", WORK/"fail503.sqlite", False)
    evidence["malformed_envelope"] = sync_once(data["v1_pages"], "malformed_envelope", WORK/"malformed.sqlite", False)

    final_rows = evidence["v2_rerun"]["rows"]
    for item in evidence.values():
        item.pop("rows", None)

    (OUT/"evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_csv(OUT/"final_contacts.csv", final_rows)
    shutil.rmtree(WORK)

    compact = {k: v["summary"] for k, v in evidence.items()}
    print(json.dumps(compact, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
