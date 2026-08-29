# B2B Prospecting Agent — ADK + Gemini

An autonomous agent that runs Aptitude's B2B prospecting pipeline end to end:
finds ICP-matching leads, researches each company, drafts and audits a
personalized outreach email, sends it, and keeps the CRM sheet up to date —
all through a single chain of decisions the agent itself executes, with human
input reserved for a handful of well-defined exceptions. Built for the
**Taskmaster** track of the All Things Agentic Hackathon.

The agent runs autonomously in production today, scheduled via Cloud
Scheduler across five daily jobs (new prospecting, follow-ups, retry of
rejected leads, inbox monitoring for replies/bounces, and pending-approval
processing).

## Try it live

A dedicated demo instance is available at:
**[prospector-agent-demo](https://prospector-agent-demo-405290540774.us-central1.run.app)**

This instance always runs in a safe demo mode: say hi, share your email
(and optionally a target country in Latin America), and any email the
agent would normally send goes to you instead of a real prospect. It still
drafts genuine, personalized Aptitude outreach — this is exactly how the
agent behaves in production — so you'll see real research and real
writing, not placeholder content. You can also ask the agent directly
about this project — how it was built, the stack, the challenges we ran
into — at any point in the conversation.

You can watch leads get logged live in this **read-only spreadsheet**:
[Demo leads sheet](https://docs.google.com/spreadsheets/d/1Abr0X62ngMsx30N0UWmkdBl4G2kUYvyx2Q2ZwdP0B7s/edit)

Try: *"Prospect 3 companies in the banking sector"*

## What's in this repo

```
prospector-agent/
├── prospector_agent/
│   ├── __init__.py       # required by ADK, do not touch
│   ├── agent.py            # orchestrator: instructions + tool wiring
│   └── tools.py             # 20 tools: lead search, research, drafting,
│                             # verification, sending, CRM, follow-up,
│                             # retries, inbox monitoring, reporting,
│                             # on-demand daily prospecting, test-mode approvals
├── cloud_function/
│   ├── main.py              # 5 Cloud Functions that trigger the agent
│   │                         # on a schedule (Cloud Scheduler can't chain
│   │                         # HTTP calls, so this is the bridge layer)
│   └── requirements.txt
├── requirements.txt
├── .env.example
├── .gcloudignore
├── .gitignore
└── README.md
```

## How it works

A single orchestrator agent (`agente_prospeccion`) with 20 tools. You (or a
scheduled job) send it a natural-language instruction — *"Prospect 5
companies in the banking sector"*, *"Follow up on leads that haven't
responded"*, *"Review pending approvals"* — and Gemini decides the entire
execution sequence itself. There is no hand-coded workflow graph; the model
reasons about which tool to call next based on the instructions in
`agent.py`.

### The full chain, for a new lead

1. **Exclusion check** (email and company name, against two manually
   maintained Google Sheets tabs) — happens FIRST, before any research or
   drafting, so excluded contacts never cost an API call.
2. **Research** via Gemini's native Google Search tool.
3. **Draft** a personalized email (Gemini), citing the research and a
   relevant Aptitude client case study by industry.
4. **Verify** the draft (Gemini) — checks fidelity to the research, correct
   case study, word limit, and domain plausibility. Rejects up to 2 times
   with feedback fed back into a redraft.
5. **Prior-contact check** (has this company been emailed before?).
6. If approved: **send** via Microsoft Graph (Outlook) and **log** to the
   Google Sheets CRM substitute.
7. If rejected 2 times, excluded, or already contacted: **escalate** —
   notify the user by email and persist the case to a "Pending Approval"
   sheet, so it can be approved manually or retried automatically later.

### Autonomous scheduled behavior

| Time (Bogotá) | Job | What it does |
|---|---|---|
| 7:00 AM daily | Inbox review | Checks unread email for bounces and replies; classifies interest with Gemini; updates lead status |
| 8:30 AM daily | Retry rejected | Re-attempts leads rejected by the verifier 7+ days ago, from scratch, once |
| 12:00 PM, weekdays only | New prospecting | Finds 10 new leads in a rotating industry sector, one per company max per run (skips Colombian public holidays) |
| 2:00 PM daily | Follow-up | Sends a 2nd/3rd touch to leads that haven't responded, 5 days apart, max 3 attempts |
| 4:00 PM daily | Pending approvals | Sends any human-approved emails waiting in the "Pending Approval" sheet |

The user can also trigger any of these on demand through the chat interface.
For new prospecting specifically, just ask — 'run a daily prospecting round'
splits 10 leads across all four rotating sectors, or specify one directly
('run a daily prospecting round for banking') to target just that sector.
Either way it's the exact same chain as the scheduled 12 PM job. You can
also ask for a status report ('give me a report') that summarizes lead counts
by outcome, with an optional follow-up to email that report to any address.

## CRM: Google Sheets today, HubSpot integration planned

Aptitude's real CRM is HubSpot, already in production use for other
workflows. To avoid mixing hackathon test data with live business data, this
project currently logs leads to a Google Sheet that mirrors the relevant
CRM fields instead. The tool is still named `crear_negocio_hubspot` for
historical reasons in the codebase, but it does not touch HubSpot today.

A real HubSpot integration is on the roadmap once the agent moves past the
testing phase — it would give the sales team proper deal-stage tracking,
pipeline visibility, and reporting inside the tool they already use daily,
instead of a spreadsheet. The Sheets-based approach was the right call for
building and validating the agent safely during the hackathon; it isn't the
target end state.

## Setup

### 1. Google Cloud project

Create a project in [Google Cloud Console](https://console.cloud.google.com/),
enable billing, and enable the **Agent Platform API** (formerly branded
Vertex AI API).

### 2. Install the Google Cloud CLI and authenticate

```bash
gcloud auth application-default login
```

### 3. Python environment

```bash
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Environment variables

```bash
cp .env.example prospector_agent/.env
```

Fill in: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (must be a
multi-region like `us`, not a specific region — Gemini 3.5 Flash requires
it), `APOLLO_API_KEY`, `MICROSOFT_TENANT_ID`/`MICROSOFT_CLIENT_ID`/
`MICROSOFT_CLIENT_SECRET`/`MICROSOFT_MAILBOX` (Microsoft Entra app
registration with Mail.Send permissions), `GOOGLE_SHEETS_CREDENTIALS_JSON`
(a Google service account key, compressed to a single line) and
`GOOGLE_SHEETS_ID`.

### 5. Run locally

```bash
adk web
```

Try:

> "Prospect 2 companies in the banking sector"

You'll see the agent chain through the tools live, and the built-in trace
view shows every tool call and its arguments — useful for understanding the
reasoning, not just the output.

### 6. Deploy to Cloud Run

```bash
adk deploy cloud_run --project=<your-project> --region=us-central1 \
  --service_name=prospector-agent --app_name=prospector_agent --with_ui \
  prospector_agent -- --env-vars-file=env-vars.yaml \
  --allow-unauthenticated --clear-base-image --timeout=1800
```

`requirements.txt` must exist both at the repo root and inside
`prospector_agent/` — the deploy command only packages the agent subfolder.

### 7. Deploy the scheduling layer (optional, for full autonomy)

Each scheduled behavior needs a small Cloud Function (bridges Cloud
Scheduler, which can only make one HTTP call per job, to the two calls ADK's
API server needs — create session, then run) and a Cloud Scheduler job:

```bash
gcloud functions deploy trigger-prospector --gen2 --runtime=python312 \
  --region=us-central1 --source=cloud_function \
  --entry-point=trigger_prospector --trigger-http --allow-unauthenticated \
  --timeout=540 --set-env-vars=AGENT_SERVICE_URL=<your-cloud-run-url>

gcloud scheduler jobs create http prospeccion-diaria --location=us-central1 \
  --schedule="0 12 * * 1-5" --uri=<function-url> --http-method=POST \
  --time-zone="America/Bogota" --attempt-deadline=600s --max-retry-attempts=0
```

Repeat for each of the 5 functions in `cloud_function/main.py`
(`trigger_prospector`, `trigger_seguimiento`, `trigger_reintento_rechazados`,
`trigger_revision_respuestas`, `trigger_revision_aprobaciones`).

## Notes for judges

- **Autonomy**: the agent runs the full chain — search, research, draft,
  verify with retries, send, log — without step-by-step user confirmation.
  It is currently live and prospecting real leads on a daily schedule, not
  just a demo script.
- **Architectural discipline**: each capability is an isolated, single-
  responsibility tool with its own docstring that Gemini reads to decide
  when to use it. Column lookups in Google Sheets are always by header name
  (with English/Spanish fallback), never by fixed position, so the schema
  can evolve without breaking existing rows.
- **Human-in-the-loop, scoped narrowly**: the only points where the agent
  pauses for a person are contact exclusions, already-contacted companies,
  and emails rejected twice by the verifier — everything else
  proceeds autonomously. Rejected leads get one automatic retry after 7
  days before they're left for manual review permanently.
- **New Projects Only compliance**: this codebase and its prompts were
  written from scratch during the hackathon submission period, drawing only
  on the author's own prior operational knowledge of B2B outreach — no
  external code or prompt text was copied from any other system.
- **Out of scope, intentionally**: real-time inbox monitoring (this agent
  checks once daily instead of every minute, a conscious batch-vs-real-time
  architecture trade-off) and meeting-booking detection (would require a
  real scheduling system connection — likely HubSpot Meetings once the
  planned HubSpot integration lands, but out of scope for the current
  Sheets-based version).
