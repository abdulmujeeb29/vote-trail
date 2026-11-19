# Progress

| Phase | Status | Score | Review |
|---|---|---|---|
| 1 Foundation + trust rules | ✅ Passed | 99 | `reviews/PHASE_1.md` |
| 2 Results check | ✅ Passed | 90 | `reviews/PHASE_2.md` |
| 3 Rumours, alerts, voice | ✅ Passed | 96 | `reviews/PHASE_3.md` |
| 4 Journey, dashboard, demo, ship | ✅ Passed | 97 | `reviews/PHASE_4.md` |

## How to verify locally
```bash
make check   # lint + migrations + tests + coverage + secret scan
make smoke   # prod settings, Gunicorn + worker, real HTTP
npm run test:js
npx playwright test          # LIVE=1 adds the real gpt-realtime test
uv run python scripts/live_phase3.py
```
