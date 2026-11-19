# Phase 3 review: Rumours, alerts, basic phones, voice

**Result: PASS · score 96/100 · all gates green**

## Built
- **Rumour/incident engine** (`apps/claims`): intake from app, SMS, USSD, voice note and verifiers; forward detection (explicit + markers); grouping by incident type + ward (or near-identical text); evidence from citizen reports, verifiers and **Tavily** public sources (≤ 4, cached per query per day); **Azure analysis with strict schema and server-side quote validation** (invented quotes and unknown IDs are dropped); status **only from `trust.claim_status`**; immutable `ClaimAssessment` revisions; templated verdicts in English and Pidgin (status + reasons + "what we don't know").
- **Alerts** (`apps/alerts`): announcement intake (source URL required) → AI extraction (strict schema, quotes verified, PU codes must exist) → **auto-applied only from the official allowlist** (`inecnigeria.org`, `x.com/inecnigeria`), otherwise queued for verifier approval → PU relocation applied with audit → **exact targeting** of subscribers → SMS + voice notes (community leaders get voice) with **dedupe keys, so re-runs never duplicate**.
- **Basic phones** (`apps/channels`): Africa's Talking-spec **USSD handler** (`CON`/`END`, ≤ 182 chars, stateless, 9-digit PU codes for keypads), **inbound SMS commands** (`PU`, `CHECK`, `RESULT`, `STOP`, agent `R … REJ …` results → a citizen origin), outbox gateway (Africa's Talking backend ready behind `NOTIFY_BACKEND`), **OTP** (hashed, 5-min expiry, 5 attempts, rate-limited), optional webhook token, **phone simulator** driving the real handler.
- **Voice** (`apps/voice`): sourced knowledge base (`knowledge/*.md`, 8 topics, every file lists its sources); **gpt-realtime over WebRTC** from the browser using **short-lived client secrets** (the key never leaves the server); tools `lookup_pu`, `get_result_status`, `check_claim`, `kb_search`; guardrails (no winners, no voting advice) in both instructions and tool layer; read-back confirmation; **voice notes understood by the same gpt-realtime deployment** (transcript + English + language + intent) routed to the rumour engine or the KB; **ElevenLabs TTS** with a permanent cache.

## Live results (`docs/reviews/eval/phase3_live.json`, Playwright LIVE run)
| Check | Result |
|---|---|
| 12 forwards of one vote-buying rumour + 4 Tavily sources | **Unconfirmed**, 1 origin, 12 forwards, 16/16 evidence items validated; Pidgin verdict "We never confirm am. Na only one person report am. People don forward am 12 times, but forward no be confirmation." (8.1 s after the fix below) |
| INEC-style relocation notice | Applied, kind `pu_relocation`, exact quote, 0 errors (1.5 s) |
| Realtime client secret | `ek_…` token, no API key in the response (1.4 s) |
| ElevenLabs TTS | 38 KB MP3, second call served from cache (1.2 s) |
| Pidgin voice note → gpt-realtime | "Dem dey share money for Garki Ward 5 polling unit, make una check am." → language `pcm`, intent `rumour`, correct English translation (3.4 s) |
| **Browser ↔ gpt-realtime (WebRTC) tool loop** | The assistant read the code back ("You said 37/06/02/002, is that right?"), called `lookup_pu`, then answered: moved to 37/06/02/004, landmark, ramp, assisted-voting desk |

## Scorecard
| # | Criterion | Weight | Score | Evidence |
|---|---|---|---|---|
| 1 | Claims engine per rules, quotes validated, clear en + pcm verdicts | 25 | 24 | 14 tests + live run. −1: Pidgin text not yet reviewed by a native speaker |
| 2 | Alerts: allowlist, exact targeting, idempotent, reviewed templates | 20 | 20 | Exactly 4 messages to the 3 affected people (other PUs untouched); re-delivery adds 0; fake domains rejected; live extraction correct |
| 3 | USSD/SMS spec-correct + simulator on the real endpoint | 20 | 19 | Every menu path ≤ 182 chars; Playwright simulator test. −1: not run against a live Africa's Talking account (none provided) |
| 4 | Voice: grounded tools, key safety, guardrails, read-back | 20 | 20 | Live WebRTC tool loop; key never returned (tested); refusal patterns tested |
| 5 | TTS cache + community relay voice note | 5 | 4 | Works live. −1: no Nigerian-accent voice in the ElevenLabs library (adding one needs your account) |
| 6 | Knowledge base sourced; research recorded | 10 | 9 | 8 sourced files. −1: accessibility rule cites the Electoral Act tracker generally, not a section of the 2026 Act |
| | **Total** | 100 | **96** | |

## Improvements found by the loop
1. **Cost and latency:** each new report re-analysed every item (70 s for 12 reports). Now each item is analysed once and queued checks for a claim coalesce (8 s; 1 AI call for 10 reports, tested).
2. Paraphrased eyewitness reports didn't group (text hashing only catches near-copies). They now group by incident type + ward.
3. Refusal patterns missed "who should I vote for" and Pidgin forms. Fixed and tested.

## Known limits
- The simulator shows any number's outbox: fine for the demo, so turn it off (`SIMULATOR_ENABLED=false`) with real users.
- Yoruba, Hausa and Igbo are labelled beta; SMS and USSD fall back to English for them.
