"""Workflow 4: AI voice agent call routing.

A voice agent platform (for example Bland, Vapi, Retell, or BickleAI) answers the
call and sends the transcript to a webhook. This script is that webhook's logic:
it identifies the caller type and intent, routes emergencies to on-call staff,
pre-qualifies rental prospects, and writes a CRM note with a follow-up task.

The voice agent's own script lives in voice_agent_prompt.md.
"""
import json
import re

from common import ask_claude_json, mode_label, out_dir, read_csv, read_json

ON_CALL = "(815) 555-0100"
EMERGENCY_WORDS = ["burst", "flood", "water is everywhere", "gas", "fire", "smoke", "sparking", "sewage"]
INCOME_MULTIPLE = 3  # common screening rule: gross income at least 3x rent
LISTING_RENT = {"Riverside Lofts": 1650, "Maple Court": 1250, "Elm Street Duplex": 1400}


def rules(call: dict, known_phones: dict) -> dict:
    t = call["transcript"].lower()
    tenant = known_phones.get(call["from"])
    if "i own" in t or "owner statement" in t:
        caller, intent = "owner", "owner question"
    elif tenant:
        caller = "tenant"
        intent = "maintenance emergency" if any(w in t for w in EMERGENCY_WORDS) else "maintenance follow-up"
    elif any(w in t for w in ["listing", "move in", "see it", "available", "bedroom"]):
        caller, intent = "prospect", "rental inquiry"
    else:
        caller, intent = "unknown", "general"
    income = re.search(r"(?:make|earn)\D{0,10}([\d,]{3,})", t)
    prop = next((p for p in LISTING_RENT if p.lower() in t), None)
    return {
        "caller_type": caller,
        "intent": intent,
        "monthly_income": int(income.group(1).replace(",", "")) if income else None,
        "pets": "cat" if "cat" in t else ("dog" if "dog" in t else None),
        "property_mentioned": prop,
        "summary": call["transcript"][:160],
    }


def analyze(call: dict, known_phones: dict) -> dict:
    ai = ask_claude_json(
        "You process call transcripts for a property management office.\n"
        f"Transcript: {call['transcript']!r}\n"
        f"Caller is a known tenant: {call['from'] in known_phones}\n"
        'Return {"caller_type": tenant|prospect|owner|vendor|unknown, "intent": short phrase, '
        '"is_emergency": true/false, "monthly_income": number or null, "pets": string or null, '
        '"property_mentioned": string or null, "summary": one sentence}.'
    )
    base = rules(call, known_phones)
    if isinstance(ai, dict):
        base.update({k: v for k, v in ai.items() if v is not None})
        if ai.get("is_emergency"):
            base["intent"] = "maintenance emergency"
    return base


def main() -> None:
    print(f"\n[4] Voice agent call routing ({mode_label()})")
    tenants = read_csv("tenants.csv")
    known = {t["phone"]: t for t in tenants}
    out = out_dir("04_calls")
    notes = []
    for call in read_json("call_transcripts.json"):
        a = analyze(call, known)
        tenant = known.get(call["from"])
        task = {"owner": "Property manager", "due": "today"}
        if a["intent"] == "maintenance emergency":
            route = f"Warm transfer to on-call {ON_CALL} and text the on-call tech"
            task = {"owner": "On-call maintenance", "due": "immediately"}
        elif a["caller_type"] == "prospect":
            rent = LISTING_RENT.get(a.get("property_mentioned") or "", None)
            income = a.get("monthly_income")
            qualifies = bool(rent and income and income >= INCOME_MULTIPLE * rent)
            a["prequalified"] = qualifies
            route = ("Book a showing and send the application link" if qualifies
                     else "Send listing details and application; leasing agent to review income")
            task = {"owner": "Leasing agent", "due": "within 1 hour"}
        elif a["caller_type"] == "owner":
            route = "Create task for property manager to call the owner back today"
        else:
            route = "Log call and check status of the caller's open work order"
            task = {"owner": "Maintenance coordinator", "due": "today"}
        note = {
            "call_id": call["call_id"],
            "time": call["time"],
            "from": call["from"],
            "caller": tenant["name"] if tenant else None,
            "unit": f"{tenant['property']} #{tenant['unit']}" if tenant else None,
            **a,
            "route": route,
            "task": task,
        }
        notes.append(note)
        print(f"  {call['call_id']}: {a['caller_type']}, {a['intent']} -> {route}")

    (out / "crm_notes.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
