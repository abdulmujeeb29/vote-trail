# System sketch: where VoteTrail fits
*Also on page 3 of the [problem brief PDF](problem-brief.pdf).*

## 1 · The bigger picture: Nigeria's election chain
INEC runs every step. VoteTrail runs none of them; it works beside them, strengthening one link: **information and trust between INEC and voters.**

```mermaid
flowchart LR
    A["1 · Inform and<br/>prepare voters"] --> B["2 · Identify voters<br/>(BVAS)"] --> C["3 · Move materials<br/>and staff"] --> D["4 · Count at the<br/>polling unit"] --> E["5 · Send results on<br/>(IReV, collation)"] --> F["6 · Settle<br/>disputes"]
    VT["🗳️ <b>VoteTrail</b><br/>tells voters what changed<br/>lets them check what was counted"]
    VT -. "Amaka's unit moved:<br/>SMS + voice note" .-> A
    VT -. "BVAS down?<br/>officials report by USSD" .-> B
    VT -. "Is it open?<br/>'Open since 09:40'" .-> C
    VT -. "agents photograph<br/>the wall result" .-> D
    VT -. "Amaka checks the wall<br/>sheet against IReV" .-> E
    VT -. "evidence pack" .-> F
    R["💬 <b>Rumour check, at every step</b><br/>40 forwards = 1 source"] -.-> VT
    style VT fill:#0f2a1a,stroke:#5bd38a,color:#ffffff
    style R fill:#e8f5ec,stroke:#1f8a50,color:#111111
```

## 2 · Who does what: information in, trust out
```mermaid
flowchart LR
    INEC["🏛️ <b>INEC</b><br/>notices · IReV result sheets"]
    OFF["👮 <b>Polling officials</b><br/>check in by USSD"]
    AG["📸 <b>Party agents and voters</b><br/>photograph the wall · report rumours"]
    VT["🗳️ <b>VoteTrail</b><br/>AI reads · rules decide<br/>never declares a winner"]
    V["👥 <b>Voters</b><br/>web · USSD · SMS · voice · 5 languages"]
    CL["📢 <b>Community leaders</b><br/>voice notes to play aloud"]
    OBS["🔎 <b>Observers and CSOs</b><br/>review queue · evidence packs"]
    INEC --> VT
    OFF --> VT
    AG --> VT
    VT --> V
    VT --> CL
    VT --> OBS
    V -- "reports · rumours · questions" --> VT
```

## 3 · The two core checks
**How a result is checked**
```mermaid
flowchart LR
    P["📸 Two people photograph<br/>the wall result sheet"] --> R["🤖 AI reads<br/>the handwriting"] --> K["📏 Rules check<br/>sums · genuine photo ·<br/>right place and time"] --> C["⚖️ Compare<br/>with IReV"]
    C --> M["✅ Matches"]
    C --> X["⚠️ Mismatch<br/>(two independent people agree)"]
    C --> N["👀 Needs review<br/>(a person checks)"]
    X --> E["📦 Evidence pack"]
```

**How a rumour is checked**
```mermaid
flowchart LR
    A["💬 Amaka pastes it,<br/>texts CHECK, or dials the code"] --> G["🧮 Group copies<br/>forwards = one source"] --> W["🤖 AI weighs<br/>reports · verifiers · public sources"] --> D["📏 Rules decide<br/>how many saw it, when,<br/>and who confirms it"]
    D --> U["Not confirmed"]
    D --> CO["Corroborated"]
    D --> CF["Confirmed or denied<br/>by an official source"]
```

**In one line:** INEC runs the election. VoteTrail **tells** every voter what changed and **lets them check** what was counted, on any phone and in their language. *AI reads, rules decide, and only INEC declares results.*

Technical detail: [`architecture.md`](architecture.md).
