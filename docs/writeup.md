# VoteTrail: submission write-up

**Team challenge:** Every Vote, Every Voice (KTech Fest 3.0)

## Problem
Nigeria's election process is largely online: CVR registration and transfers, polling unit lookup, and IReV result sheets. But it is pull-only, English-only, smartphone-only and scattered, and citizens have no way to check what they saw on the wall against what was uploaded. In 2023:
- Voters weren't told about reallocated polling units.
- Some units opened hours late.
- Only about 20% of results were on IReV by the next day.
- Rumours spread faster than checks.

With 103M+ voters heading to the polls on 16 January 2027, that information-and-trust gap is the weak link we chose.

## Solution
VoteTrail is a voice-first voter companion that works on any phone (app, USSD, SMS, voice, community relay), in English, Pidgin, Hausa, Yoruba and Igbo. It follows the voter's journey and goes deep on two trust features:
1. **Results check:** agents and citizens photograph the wall Form EC8A. AI reads it, rules check the arithmetic and photo integrity, and the figures are compared with IReV. A mismatch needs two independent sources, ideally agents from rival parties, and comes with an evidence pack for observers and courts.
2. **Rumour check:** reports, verifiers and public sources are weighed by fixed rules. Forwards are never confirmation, and the verdict comes back in the voter's language with reasons.

Around them: relocation alerts (SMS and Pidgin voice notes), election-day check-ins by officials over USSD, a verifier dashboard (password plus SMS code, audit trail), and a sourced voice assistant.

## How AI is used
- **Azure OpenAI `gpt-5.6-terra-1`:** reads handwritten result sheets, weighs rumour evidence and reads official notices, all with strict JSON schemas, per-field confidence and server-side quote validation.
- **Azure `gpt-realtime`:** live voice conversations over WebRTC with short-lived tokens, using tools grounded in a sourced knowledge base; it also understands voice notes, including Pidgin.
- **ElevenLabs:** voice notes for alerts and community leaders.
- **Tavily:** public-source evidence.
- **Principle:** AI reads and explains; deterministic, tested rules decide every status, and only INEC declares results.

Measured: 98.4–98.6% field accuracy on 32 synthetic sheets, with **zero wrong sheets published without review**. Forty forwards of a rumour stay "Unconfirmed".

## Tools
Django, SQLite/Postgres, a DB-backed job queue, vanilla JS (PWA with offline queue), Playwright, axe, Lighthouse, pytest and Hypothesis. AI coding assistant: **Claude Code** (declared).

## Status
- **Working prototype:** full voter journey, results check, rumour engine, alerts, USSD/SMS (simulator), voice, dashboard, demo replay.
- **Mock data, labelled in the UI:** IReV sheets, parties and the election.
- **Real data:** polling units are real (INEC CVR locator, FCT sample).
