# Problem brief: VoteTrail
*Every Vote, Every Voice · KTech Fest 3.0 · [PDF version](problem-brief.pdf)*

## Amaka's election
Amaka lives in Garki, Abuja. She registered, collected her voter's card, and on election morning walked to her polling unit.

**It wasn't there.** It had moved. INEC had published the change online, but Amaka doesn't browse INEC's website, and nobody told her.

**When she found the new one,** the queue was long and the officials hadn't arrived. Nobody outside knew why, or when voting would start.

**That evening,** the results were pasted on the wall and people took photos. Days later, when the final numbers came, people asked: *is that what we saw on the wall?* There was no way to check.

**Meanwhile,** a WhatsApp message said votes were being bought for ₦5,000. It was forwarded again and again before anyone asked if it was true.

Amaka is made up. What happens to her is not: our research below shows each part happened in 2023.

## The weak link we chose
**INEC publishes the information. Voters don't get it, and can't check it.**

INEC already puts the election online: registration, polling unit lookup, and a photo of every polling unit's result sheet on its results website, IReV. But that information:
- **waits for you to find it.** Nothing tells you when something changes;
- **is in English, for smartphones,** when many voters have neither;
- **is never compared with what people saw.** The result on the wall and the result online never meet.

When information can't reach people or be checked, rumours fill the gap. **A count can be correct and still not be trusted.**

## What our research found
| | Finding | Source |
|---|---|---|
| **56,872** | new polling units created by INEC before the 2023 elections, so many voters had to check where they now vote | Nairametrics [1] |
| **44%** | of sampled polling units had started voting by 9:30am; officials had arrived at only 27% by 7:30am | Yiaga Africa [2] |
| **1 in 5** | presidential polling unit results were on IReV by noon the next day | EU observers [3] |
| **5%+** | of polling unit results were still missing at the end of March, with no explanation | EU observers [4] |
| **103M+** | registered voters for the next general election, on 16 January 2027 | INEC via Premium Times [5] |

**Rumours:** fact-checkers (Dubawa and the Nigeria Fact-checkers' Coalition) ran live monitoring of election mis- and disinformation in 2023 [6]. Their checks live on social media and in English, so they rarely reach basic phones or local languages.

## Who it hurts
- **Voters**, especially basic-phone users, non-English speakers, older people and people with disabilities.
- **Polling officials**, blamed for delays they have no way to explain.
- **Party agents**, who photograph the wall result with no way to compare it or prove a difference.
- **Community leaders**, asked questions they can't answer.
- **INEC**, which loses public trust even when its process works.

## Our answer
**VoteTrail tells every voter what changed, in their language, on any phone, and lets them check what was counted.**

| What happened to Amaka | Who does what | What VoteTrail does |
|---|---|---|
| Her unit moved | **Nobody has to do anything.** VoteTrail watches INEC's official notices. | AI reads the notice, rules check it really came from INEC, and only voters registered at that unit get an SMS (plus a voice note) with the new address, weeks before election day. |
| Officials were late | The **presiding officer** dials `*384*2027#`, picks the officials-only check-in, and presses "Polling unit opened". Only verified officials can. | Voters see **"Open since 09:40"** in the web app, or by dialling the same code. Voters at the unit can also report "long queue" or "not open yet"; these show only when two different people agree. |
| She doubted the result | **Party agents** (and any voter) photograph the result sheet on the wall, in the web app. | AI reads the handwriting, rules check the sums and that the photo is genuine, then it's compared with INEC's upload on IReV. It's flagged **"Mismatch"** only when two independent people, ideally from rival parties, agree with each other and differ from IReV. Observers get an evidence pack. |
| The rumour spread | **Any voter** pastes the message in the web app, or sends it by SMS or USSD. | VoteTrail weighs reports, verifiers and public sources. Forty forwards still count as **one** source. She gets a clear answer with reasons, in her language. |

### What makes it different
> **Others collect results. VoteTrail decides when citizens' evidence is strong enough to raise an alarm, and refuses to when it isn't.**

### How to use it, on any phone
| Web app (smartphone) | USSD (any phone, no data) | SMS (any phone) | Voice |
|---|---|---|---|
| Open the link; no download or account. Set up in 3 taps (language, polling unit, phone). Then **My vote**, **Verify** (photograph a result sheet or paste a rumour) and **Ask**. | Dial `*384*2027#`: 1 My polling unit · 2 Check a rumour · 3 Result check · 4 Get alerts · 5 Language | Text `PU 370602004` (where to vote), `CHECK` + message (rumour), `RESULT 370602004` (result), `STOP` (end alerts) | Ask questions out loud in the web app; alerts can arrive as voice notes; community leaders play them aloud. |

Languages: **English, Pidgin, Hausa, Yoruba and Igbo** on every channel. Voice notes are in English and Pidgin today; no Hausa, Yoruba or Igbo text-to-speech voice exists yet, so those voters get SMS. In the prototype, USSD and SMS run through an on-screen basic-phone simulator; going live needs a telco short code.

## Why people can trust it
- **AI reads, rules decide.** AI only reads handwriting, messages and notices. Fixed, tested rules decide every status.
- **Two independent people, or no alarm.** One photo can't trigger a mismatch; forwards are never proof.
- **It never says who won.** Only INEC declares results.

## How it grows
- **Uses what's already there:** INEC's notices and IReV, the phones people own, and steps officials and agents already take.
- **Cheap to run:** one server handles hundreds of uploads at once; a viral rumour is checked once, not forty times.
- **Voters pay nothing:** observer groups cover SMS; telcos can make the short code free.

## What success looks like
- Voters hear about a moved unit **before** election day, not at the gate.
- Every polling unit result can be **checked by citizens** against INEC's upload.
- A rumour gets a clear answer **within minutes**, in the voter's language.
- **No new burden** on officials or agents.

---
**Sources.** [1] Nairametrics, "INEC creates 56,872 new polling units". [2] Yiaga Africa, statement on the 2023 presidential election (election-day observation). [3] EU Election Observation Mission Nigeria 2023, first preliminary statement, 27 Feb 2023. [4] EU EOM Nigeria 2023, final report. [5] Premium Times, "Voter register hits 103 million: INEC". [6] Dubawa, live fact-check of the 2023 presidential and legislative elections.
