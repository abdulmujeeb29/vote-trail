# Phase 1 review: Foundation + trust rules

**Result: PASS · score 99/100 · all gates green**

## Built
- Django 5.2 project (`votetrail/settings/{base,dev,test,prod,e2e}`), SQLite locally (WAL), Postgres via `DATABASE_URL`.
- `core`: signed-cookie visitor identity, request IDs, JSON logs with phone/key redaction, `Participant` (phone stored as HMAC + Fernet-encrypted), append-only `AuditLog` (save/update/delete blocked at model and queryset), `delete_my_data`, `/healthz` (DB + worker heartbeat).
- `geo`: State/LGA/Ward/PollingUnit, PU-code parser (`SS/LL/WW/PPP` or dashes), relocation chain, distance helper.
- **Real seed data:** 24 real FCT polling units (Municipal: City Centre, Garki; Bwari: Bwari Central, Kuduru), fetched from INEC's official CVR polling unit locator (`cvr.inecnigeria.org/pu`) and saved in `fixtures/geo/fct_sample.json` with the source. Coordinates are approximate and labelled. Amaka's relocation (`37/06/02/002 → 37/06/02/004`) is a labelled demo scenario.
- `elections`: demo election (16 Jan 2027) with **neutral demo parties PA–PD**, so the demo never accuses a real party.
- `jobs`: DB-backed queue with a portable atomic claim (one conditional `UPDATE`; works on SQLite and Postgres), lease + claim token, lost-claim protection (a late worker's result is rolled back), digest reuse, exponential backoff, dead-letter, worker with heartbeat and SIGTERM handling.
- `trust` (pure Python, no Django): independence (person/device/exact image/near-image/near-text/forwards), arithmetic, photo integrity, result status, claim status, material change.
- Ops: `Makefile` (`check`, `smoke`, `seed`…), `.env.example`, `scripts/secret_scan.py`, Dockerfile + compose + supervisor start script (built once; then deferred to deploy at the user's request).

## Scorecard
| # | Criterion | Weight | Score | Evidence |
|---|---|---|---|---|
| 1 | Trust rules complete, 100% branch coverage | 30 | 30 | `apps/trust/*` 100% branch; table + property tests (`hypothesis`): reordering never changes status; adding a forward never adds an origin |
| 2 | Job queue: concurrency, lease recovery, digest reuse, dead-letter | 20 | 20 | 4 threads × 30 jobs on a file SQLite DB: 30 unique claims, 30 runs; expired lease recovered; late result discarded |
| 3 | Data model + real sourced seed + relocated PU | 15 | 15 | 24 real PUs from INEC's locator; seed idempotent (tested) |
| 4 | Privacy and security | 15 | 15 | HMAC + encryption round-trip, redaction filter, append-only audit, delete-my-data |
| 5 | Run/health/Makefile/env/fail-fast | 10 | 9 | Docker image built and its "exit if a process dies" behaviour observed; that run exposed 2 bugs (heartbeat path type, file permission), both fixed. Verified with the local smoke test (Gunicorn + worker, prod settings). Docker re-run deferred to deploy |
| 6 | Code quality, sources | 10 | 10 | ruff clean, typed, `docs/sources.md` |
| | **Total** | 100 | **99** | |

## Gates
G1 ruff ✅ · G2 migrations ✅ · G3 tests ✅ · G4 secret scan ✅ · G5 local smoke ✅ · G6 mock data labelled ✅

## Decisions
- Demo parties are fictional (PA–PD) to stay non-partisan.
- Similar-image merging is **off** for result sheets (see Phase 2): two people photographing the same wall sheet must stay independent.
