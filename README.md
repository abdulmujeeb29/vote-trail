# VoteTrail

| ▶ Demo video | 🌐 Live app | 📄 Problem brief + system sketch |
|---|---|---|
| **[youtu.be/ntpQpu8W5qg](https://youtu.be/ntpQpu8W5qg)** | **[vote-trail.apps.thalesops.com](https://vote-trail.apps.thalesops.com)** | **[docs/problem-brief.pdf](docs/problem-brief.pdf)** |

**Every vote, every voice.** VoteTrail tells every Nigerian voter what changed at their polling unit, in their language, on any phone, and lets them check that what was counted is what they saw.

Built for KTech Fest 3.0, challenge *"Every Vote, Every Voice"* ([challenge.md](challenge.md)).

## The problem
INEC publishes the information: polling unit changes, and a photo of every result sheet on IReV. **Voters don't get it, and can't check it.** It waits to be found, it's in English for smartphones, and the result on the wall is never compared with the result online. In 2023, only 1 in 5 presidential results was on IReV by noon the next day, and rumours filled the gap. Full brief: [docs/problem-brief.md](docs/problem-brief.md).

## What VoteTrail does
| When | What happens |
|---|---|
| Your polling unit moves | You get an SMS and a voice note, before election day |
| Election morning | Officials check in by USSD, so you can see "Open since 09:40" |
| After counting | Agents photograph the wall result; AI reads it and compares it with IReV |
| A rumour spreads | Paste, text or dial it; get a clear answer with reasons, in your language |

Works on the **web app**, **USSD** (`*384*2027#`, no data), **SMS** and **voice**, in **English, Pidgin, Hausa, Yoruba and Igbo**.

## What makes it different
> **Others collect results. VoteTrail decides when citizens' evidence is strong enough to raise an alarm, and refuses to when it isn't.**

- **Two independent people, or no alarm.** One photo can't flag a mismatch; rival party agents agreeing counts most.
- **Forty forwards are still one source.** Repeats never count as confirmation.
- **AI reads, rules decide.** AI reads handwriting, notices and messages; fixed, tested rules decide every status. VoteTrail never says who won.

## How AI is used
| Task | Model |
|---|---|
| Read handwritten result sheets (EC8A), INEC notices, rumour evidence | Azure OpenAI `gpt-5.6-terra-1` (strict JSON output) |
| Voice assistant and voice-note understanding | Azure `gpt-realtime-2.1` |
| Voice notes for alerts | ElevenLabs |
| Public-source evidence for rumours | Tavily search |

How it fits together: [system sketch](docs/system-sketch.md) · [technical architecture](docs/architecture.md).

## Run it
Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 20+ for browser tests.
```bash
cp .env.example .env     # add your keys
uv sync
make dev                 # http://127.0.0.1:8010 (migrates, seeds, runs the worker)
```
Deploy: the `Dockerfile` runs migrations, Gunicorn and the job worker. Set `SECRET_KEY`, `PHONE_HMAC_KEY`, `FIELD_ENCRYPTION_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `SEED_ON_START=1` and the AI keys from `.env.example`.

Checks: `make check` (lint and 356 tests) · `npx playwright test` (browser and accessibility tests).

## Honest status
- **Real:** the 24 FCT polling units come from INEC's CVR locator. AI reading, rules, alerts and rumour checks run live.
- **Demo data, labelled in the app:** the election, the parties (PA–PD, fictional) and the IReV sheets. IReV has no public API.
- **Simulated:** USSD and SMS run through an on-screen basic-phone simulator until a telco short code is assigned.
- **Privacy (NDPA 2023):** no voter IDs stored; phone numbers are hashed and encrypted; delete-my-data is built in.

## What's next
1. **Pilot:** one LGA in the FCT with an observer group (such as Yiaga Africa), before the January 2027 election.
2. **Real channels:** a free short code and SMS line through a telco partner (Africa's Talking-ready today).
3. **Official data:** INEC access to notices and IReV sheets, replacing the demo data.
4. **Languages:** native-speaker review of all translations; Hausa, Yoruba and Igbo voice notes once those voices exist.
5. **Verifier network:** fact-checkers and observer groups reviewing flagged results and rumours.

## Credits
- **Libraries:** Django, WhiteNoise, Gunicorn, psycopg, cryptography, Pillow, ImageHash, httpx, OpenAI SDK, websockets, pytest, Hypothesis, Ruff, Playwright, axe-core, Lighthouse.
- **AI and services:** Azure OpenAI, ElevenLabs, Tavily, Africa's Talking (API spec).
- **Data:** INEC CVR polling unit locator (FCT sample); research sources in [docs/sources.md](docs/sources.md).
- **Fonts:** Instrument Serif, Manrope, JetBrains Mono, Caveat, Kalam (OFL).
- **Ideas:** the evidence-rules pattern is adapted from the team's earlier prototype, *Amara*.

**AI coding assistant:** the team did the problem research, product idea and system design. Claude Code (Anthropic) was used as an AI coding assistant to speed up implementation, tests and docs, under the team's direction and review.
