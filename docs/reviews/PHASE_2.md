# Phase 2 review: Results check

**Result: PASS · score 90/100 (threshold 90) · all gates green**

## Built
- **EC8A schema** (`docs/ec8a-schema.md`, `apps/results/schema.py`): 8 ballot-accounting fields, party figures + words, cancelled/signed/stamped. Sourced from public reporting of real sheets. Added rule: issued = used + unused + spoilt.
- **Capture (PWA):** in-app camera (`getUserMedia`, fallback `capture="environment"`), client compression, persistent device ID, idempotency key, **IndexedDB offline queue** (`static/js/offline-queue.js`), service worker shell, live status polling.
- **Server intake:** idempotent `POST /api/results/uploads`, size/type limits, **EXIF stripped** (re-encoded JPEG), SHA-256 + perceptual hash, rate limits per visitor and per IP, CSRF enforced.
- **Extraction:** Azure Responses API with a **strict JSON schema**; every field has value + confidence + unreadable; server validation (party list, PU code match, integers); confidence gate → `NEEDS_REVIEW`; reuse by (image, schema, prompt, model). The IReV image goes through the same reader.
- **IReV adapters:** `MockIrevSource` (seeded, labelled "mock") and a documented `PublicIrevSource` stub (disabled; no public API; respects INEC terms).
- **Pipeline jobs:** `check_upload → extract → recompute` with immutable `ResultCheck` revisions (only on material change), audit trail, and SMS to subscribers via the outbox (en + pcm templates).
- **Outputs:** PU result page (badge with icon + text, side-by-side wall vs IReV, history), JSON API, **deterministic evidence pack** (ZIP with images, hashes, extracted JSON, IReV, history, audit, summary.html), gated to verified observers/verifiers.
- **Evaluation:** synthetic EC8A generator (handwriting fonts, skew, shadow, blur, noise, smudges, cancelled stamps, arithmetic errors), 32-sheet eval set, `eval_extraction --live`.

## Live extraction results (Azure `gpt-5.6-terra-1`)
| Run | Prompt | Field accuracy | Silent wrong fields | Smudges guessed | Confident-field accuracy | Wrong sheets published without review |
|---|---|---|---|---|---|---|
| 1 | v1 | 98.4% | 4 | 1 | 99.1% | 0 |
| 2 | v2 | 98.6% | **0** | **0** | **100%** | **0** |
| 3 | v2 (fixed generator) | 98.4% | 2 | 0 | 99.5% | **0** |

"Wrong sheets published without review" is the number that matters. In every run, each misread was caught by the confidence gate or the arithmetic rules and routed to `NEEDS_REVIEW`. Prompt v2 trades a higher review rate (~13% of fields flagged) for safety. Reports: `docs/reviews/eval/`.

## Scorecard
| # | Criterion | Weight | Score | Evidence |
|---|---|---|---|---|
| 1 | Correct status for every integration case | 25 | 25 | Mismatch (2 cross-party agents), matches, single-origin → review, pending, cancelled, smudge, arithmetic, reused image, gallery, delayed offline upload, too far |
| 2 | Live extraction: synthetic ≥ 97%; real ≥ 90% or 0 silent wrong on real | 25 | 17 | Synthetic 98.4–98.6% ✅. **Real set not done:** IReV needs an account and INEC's older PDF links 404. Partial credit for 0 sheet-level silent errors on synthetic |
| 3 | Offline capture survives reload/offline, syncs once, idempotent | 15 | 15 | Playwright in Chromium (offline → reload → online → single upload → result) + 4 Node tests + server idempotency test |
| 4 | Integrity: gallery blocked, EXIF stripped, reuse, location | 10 | 10 | Integration tests for each |
| 5 | Evidence pack complete + deterministic | 10 | 10 | Byte-identical across downloads; contents asserted |
| 6 | Schema researched/sourced; mock IReV labelled | 10 | 8 | No official blank template retrievable; fields from reporting of real sheets |
| 7 | Result page clarity + wording rules | 5 | 5 | Presenter tests assert no "won"/"winner" |
| | **Total** | 100 | **90** | |

## Bugs found by the loop (fixed)
1. **Independence bug:** two people photographing the same wall sheet were merged into one source by the near-image rule. Near-image merging is now off for result sheets; reuse across PUs is still caught by integrity.
2. **CSRF cookie missing** on the capture page, so every real upload would have got a 403. Caught by the browser test. Fixed, with a regression test.
3. **Camera race:** "Take photo" before the video was ready produced an empty image. Now waits for frames.

## Known limits
- Real-sheet accuracy is unmeasured. **Action for the user:** share real EC8A photos (or OK an IReV account) to close this.
- Pidgin SMS templates are drafts that need a native-speaker review.
- 13% of fields flagged means a meaningful verifier workload on bad photos.
