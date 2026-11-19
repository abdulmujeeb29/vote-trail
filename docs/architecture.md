# Technical architecture: VoteTrail

Four views, from simple to technical:
1. **Big picture:** where VoteTrail fits in the election chain (non-technical)
2. **How it works:** the 5 layers (anyone)
3. **Architecture:** components and services (technical)
4. **Key flows:** results check, rumour check, unit-move alert

---

## View 1 — The big picture (non-technical)

The election chain runs left to right. VoteTrail plugs in at every stage where citizens need information or trust.

```mermaid
flowchart LR
    subgraph CHAIN["Nigeria's election chain (run by INEC)"]
        A[Inform voters] --> B[Register / transfer] --> C[Collect PVC] --> D[Find polling unit]
        D --> E[Accreditation<br/>BVAS] --> F[Vote & count<br/>EC8A on wall] --> G[Upload to IReV] --> H[Collation] --> I[Declaration] --> J[Disputes]
    end

    subgraph VT["VoteTrail (citizen side)"]
        V1[Guide + reminders<br/>in your language]
        V2[Unit-move alerts]
        V3[Live unit status<br/>opened · late · queue]
        V4[Results check<br/>wall photo vs IReV]
        V5[Rumour check]
        V6[Evidence pack]
    end

    V1 -.-> A & B & C
    V2 -.-> D
    V3 -.-> E
    V4 -.-> F & G & H
    V5 -.-> A & F & I
    V6 -.-> J
```

**Plain words:** INEC runs the election. VoteTrail sits beside it, telling voters what changed and letting them check what happened. It never replaces INEC and never declares results.

---

## View 2 — How it works: 5 layers

```mermaid
flowchart TB
    L1["📱 CHANNELS<br/>Web app (works offline) · USSD · SMS · Voice assistant · Voice notes · Community relay"]
    L2["🧭 JOURNEY<br/>Register → PVC → Polling unit → Election day → Results → Rumours → Disputes"]
    L3["🤖 AI LAYER<br/>Talks in local languages · Turns announcements into alerts · Reads result sheets · Weighs evidence"]
    L4["🛡️ TRUST LAYER<br/>Evidence rules · Photo integrity checks · Independent sources · Verified roles · Audit trail"]
    L5["🗄️ DATA LAYER<br/>Mock data → Public INEC sources (IReV, announcements, PU list) → Official INEC feed"]
    L1 --> L2 --> L3 --> L4 --> L5
```

| Layer | In plain words |
|---|---|
| Channels | However you reach us: smartphone, basic phone, your voice, or through your community leader |
| Journey | We walk you through every step of voting |
| AI | Understands your language, reads photos and announcements |
| Trust | **AI suggests, rules decide.** Nothing is "confirmed" without independent evidence |
| Data | Starts on public data; plugs into INEC directly when allowed |

---

## View 3 — Architecture (technical)

```mermaid
flowchart TB
    subgraph Users
        U1[Voter · smartphone]
        U2[Voter · basic phone]
        U3[Party agent / observer]
        U4[Polling official]
        U5[CSO verifier]
        U6[Community leader]
    end

    subgraph Channels
        PWA[PWA<br/>offline queue + sync]
        AT[Africa's Talking<br/>USSD · SMS · Voice]
        DASH[Verifier dashboard]
    end

    subgraph Core["VoteTrail core (Django)"]
        API[Web + API]
        USSD[USSD / SMS / Voice handlers]
        JOUR[Journey & alerts service]
        RES[Results service]
        RUM[Claims service]
        TRUST[Trust engine<br/>rules · integrity · independence]
        Q[[Job queue + workers]]
    end

    subgraph AI["AI services"]
        VIS[Azure OpenAI gpt-5.6<br/>EC8A reading · notices · evidence<br/>strict JSON schemas]
        LLM[Azure gpt-realtime<br/>voice assistant · voice notes]
        SPE[ElevenLabs<br/>voice notes for alerts]
    end

    subgraph Data
        DB[(SQLite local / Postgres prod<br/>users · PUs · uploads · claims · statuses · audit)]
        STORE[(File storage<br/>photos · audio · evidence packs)]
        ADP[Source adapters<br/>Mock · IReV · INEC announcements · PU list]
        TAV[Tavily<br/>public-source search]
    end

    U1 --> PWA
    U2 --> AT
    U3 --> PWA
    U4 --> AT
    U5 --> DASH
    U6 --> AT

    PWA --> API
    DASH --> API
    AT --> USSD

    API --> JOUR & RES & RUM
    USSD --> JOUR & RUM & RES

    RES --> Q
    RUM --> Q
    JOUR --> Q
    Q --> VIS & LLM & SPE
    Q --> TRUST
    RUM --> TAV
    TRUST --> DB
    RES --> STORE
    ADP --> DB
    JOUR -->|alerts| AT
```

**Design principles**
- **Rules first, AI second.** AI extracts and explains; the trust engine decides status.
- **Async by default.** Uploads and AI calls go through a queue, so spikes don't crash the app.
- **Offline-first.** The PWA queues uploads; USSD/SMS need only basic GSM.
- **Swappable data sources.** Adapters let us move from mock to public to official INEC data with no code change.
- **Privacy by design.** No VIN stored; phone numbers kept as a keyed hash (lookup) plus encrypted (sending); append-only audit log; delete-my-data (NDPA 2023).
- **Every language, every channel.** English, Pidgin, Hausa, Yoruba and Igbo across the app (Django i18n), USSD, SMS and verdicts, written in plain letters so they fit basic-phone SMS.

---

## View 4 — Key flows

### 4a. Results check (core)

```mermaid
sequenceDiagram
    actor Agent as Agent / citizen
    participant App as PWA
    participant Core as VoteTrail core
    participant AI as Vision AI
    participant Trust as Trust engine
    participant IReV as IReV adapter
    actor Voter as Voter (SMS)

    Agent->>App: Photo of wall EC8A (in-app camera)
    App->>App: Stamp time + GPS, queue if offline
    App->>Core: Upload when signal returns
    Core->>Trust: Integrity check (hash, reuse, location)
    Core->>AI: Extract figures
    AI-->>Core: Party votes, totals, PU code
    Core->>Trust: Arithmetic rules
    Core->>IReV: Fetch INEC upload for PU
    Trust->>Trust: Compare + count independent uploads
    Trust-->>Core: Status: Matches / Mismatch / Pending / Needs review
    Core-->>Voter: SMS "PU 012: matches IReV ✅"
    Core-->>Agent: Evidence pack available
```

### 4b. Rumour check (Amara pattern)

```mermaid
flowchart LR
    A[Claim in<br/>app · SMS · voice note] --> B[Normalise + dedupe<br/>forwards ≠ sources]
    B --> C[Gather evidence<br/>local reports · verifiers · Tavily]
    C --> D[AI analysis<br/>quotes · times · contradictions]
    D --> E[Validate quotes<br/>& references]
    E --> F{Rules}
    F -->|single / repeated source| G[Unconfirmed]
    F -->|≥2 independent, same time window| H[Corroborated]
    F -->|trusted authority confirms| I[Confirmed by source]
    G & H & I --> J[Answer in voter's language<br/>with reasons]
```

### 4c. Unit-move alert

```mermaid
flowchart LR
    A[INEC announcement<br/>or PU list change] --> B[AI extracts<br/>affected PUs]
    B --> C[Rules confirm<br/>source is official]
    C --> D[Match subscribed voters]
    D --> E[SMS + voice note<br/>in their language]
    D --> F[Community relay<br/>voice message for leaders]
```

---

## Trust rules (summary)

| Status | Rule |
|---|---|
| **Pending** | Not enough evidence yet |
| **Unconfirmed** | Single source, repeated forwards, or conflicting evidence |
| **Corroborated** | ≥2 independent sources (different verified numbers and devices) in the same time window, no unresolved conflict; cross-party agreement weighs most |
| **Confirmed by [source]** | A configured authority (e.g. INEC, police) explicitly confirms it |
| **Matches IReV** | Citizen figures = IReV figures, arithmetic valid |
| **Mismatch** | Citizen figures ≠ IReV, from ≥2 independent uploads → flagged to verifiers |
