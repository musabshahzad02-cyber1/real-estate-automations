# Real Estate Automation Workflows

Working Python demos of six automations for property managers and transaction
coordinators, built by **Muhammad Musab Shahzad** (property management, TC, and
AI automation for US real estate teams).

Every workflow runs on included sample data with one command, no accounts or API
keys required. Add an Anthropic API key and the AI steps use Claude instead of
the built-in rules.

**Showcase site:** see the `docs/` folder (published with GitHub Pages).

## Quick start

```bash
git clone REPO_URL.git
cd real-estate-automations
python run_all.py
```

Requires Python 3.10+. Results are written to `output/`. A copy of the sample
output is committed so you can browse it without running anything.

Optional extras:

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key   # AI triage, call analysis, and contract reading
python workflows/lead_response.py --serve   # live webhook at POST /webhook/lead
```

## The workflows

| # | Workflow | What it does | Output |
|---|---|---|---|
| 1 | [Work order triage](workflows/work_order_triage.py) | Tags requests by trade and priority, assigns the preferred vendor, drafts follow-ups for vendors past their response window, and writes a manager digest | `output/01_work_orders/` |
| 2 | [Delinquency and five-day notices](workflows/delinquency_notices.py) | Computes balances from the rent ledger, separates rent from late fees, drafts reminders, and prepares five-day notices for a manager to approve | `output/02_delinquency/` |
| 3 | [Month-end owner statements](workflows/owner_statements.py) | Matches the ledger to the bank feed, flags duplicates, miscoding, and unmatched items, then builds owner statements and holds any property with open issues | `output/03_month_end/` |
| 4 | [Voice agent call routing](workflows/call_router.py) | Webhook logic for an AI voice agent: identifies caller type, routes emergencies to on-call, pre-qualifies prospects, and writes CRM notes ([agent script](workflows/voice_agent_prompt.md)) | `output/04_calls/` |
| 5 | [Contract to close timeline](workflows/contract_timeline.py) | Extracts parties and deadlines from a contract, moves weekend deadlines to the next business day, and creates a calendar file and intro emails | `output/05_contract_timeline/` |
| 6 | [Instant lead response](workflows/lead_response.py) | Normalizes and de-duplicates web leads, tags buyer, seller, or renter, drafts SMS and email replies, and creates an agent task | `output/06_leads/` |

## What the sample run finds

- Two emergencies (a flooding sink and a gas smell) pushed to the top, with six vendor follow-ups drafted
- Three five-day notices for $3,600 in unpaid rent; one tenant who owes only a late fee gets a reminder, not a notice
- A duplicate $260 HVAC check, a Home Depot purchase coded to Rent Income, and a $95 bank fee missing from the ledger, so that owner's statement is held
- A burst-pipe call transferred to on-call, and a prospect earning 3x rent offered a showing
- Six contract deadlines turned into calendar events with reminders
- A repeat web lead merged into the existing contact instead of creating a duplicate

## Connecting to real systems

The demos read CSV and JSON files that mirror exports from AppFolio, Buildium,
Yardi, QuickBooks Online, Dotloop, GoHighLevel, and Follow Up Boss. In a client
deployment, the input step pulls from the client's software (API, scheduled
export, or Make.com), and the output step writes back or sends through their
email, SMS, and CRM. A person still approves anything legal or financial before
it goes out.

## Important

All names, addresses, and figures are fictional. The five-day notice is a
template, not legal advice; notice requirements differ by state and must be
approved by the client's attorney.

## Contact

Muhammad Musab Shahzad
musabshahzad02@gmail.com
[LinkedIn](https://www.linkedin.com/in/muhammad-musab-shahzad-7b3166236)
