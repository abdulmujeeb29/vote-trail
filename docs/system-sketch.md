# System sketch: where VoteTrail fits

## 1 · The bigger picture: Nigeria's election chain
The challenge describes the election as a chain. VoteTrail strengthens one link, **information and trust between INEC and voters**, and that link runs alongside every other step.

```mermaid
flowchart LR
    A["Inform and<br/>prepare voters"] --> B["Identify voters<br/>(BVAS)"] --> C["Move materials<br/>and staff"] --> D["Count at the<br/>polling unit"] --> E["Send results on<br/>(IReV, collation)"] --> F["Settle<br/>disputes"]
    VT["🗳️ <b>VoteTrail</b><br/>tells voters what changed<br/>lets them check what was counted"]
    VT -. "unit moved?" .-> A
    VT -. "is it open?" .-> C
    VT -. "wall sheet vs IReV" .-> E
    VT -. "evidence pack" .-> F
    style VT fill:#0f2a1a,stroke:#5bd38a,color:#ffffff
```
*VoteTrail runs no part of the election. It works beside INEC's own steps.*

## 2 · Who does what
```mermaid
flowchart LR
    INEC["🏛️ <b>INEC</b><br/>notices · IReV result sheets"]
    OFF["👮 <b>Polling officials</b><br/>check in by USSD"]
    AG["📸 <b>Party agents</b><br/>photograph the wall result"]
    VT["🗳️ <b>VoteTrail</b><br/>AI reads · rules decide"]
    V["👥 <b>Voters</b><br/>web · USSD · SMS · voice"]
    CL["📢 <b>Community leaders</b><br/>voice notes to share"]
    OBS["🔎 <b>Observers and CSOs</b><br/>review queue · evidence packs"]
    INEC --> VT
    OFF --> VT
    AG --> VT
    VT --> V
    VT --> CL
    VT --> OBS
    V -- "reports · rumours · questions" --> VT
```

## 3 · The core feature: checking a result
```mermaid
flowchart LR
    P["📸 Two people photograph<br/>the wall result sheet"] --> R["🤖 AI reads<br/>the handwriting"] --> K["📏 Rules check<br/>sums · photo is genuine ·<br/>right place and time"] --> C["⚖️ Compare<br/>with IReV"]
    C --> M["✅ Matches"]
    C --> X["⚠️ Mismatch<br/>(needs 2 independent sources)"]
    C --> N["👀 Needs review<br/>(a person checks)"]
    X --> E["📦 Evidence pack<br/>photos · hashes · times"]
```

**In one line:** INEC runs the election. VoteTrail **tells** every voter what changed and **lets them check** what was counted, on any phone and in their language. *AI reads, rules decide, and only INEC declares results.*

Technical detail: [`architecture.md`](architecture.md).
