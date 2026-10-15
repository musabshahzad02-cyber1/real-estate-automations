"""Workflow 6: Instant lead response.

A website form posts to a webhook (directly, or through Make.com). The handler
normalizes the lead, de-duplicates it against existing contacts, tags it by
intent, drafts a personal SMS and email, and creates a task for the agent.

Run modes:
  python lead_response.py            process data/leads.json (demo)
  python lead_response.py --serve    start a Flask webhook at POST /webhook/lead

The CRM here is a local JSON file standing in for GoHighLevel or Follow Up Boss.
In production, push_to_crm() calls the client's CRM API with their key.
"""
import json
import re
import sys

from common import OUTPUT, out_dir, read_json

CRM_FILE = OUTPUT / "06_leads" / "crm_contacts.json"


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return f"+1{digits}" if len(digits) == 10 else digits


def tag_lead(message: str, source: str) -> list[str]:
    m = message.lower()
    tags = [f"source:{source}"]
    if "rental" in source or any(w in m for w in ["rent", "lease", "rentals"]):
        tags.append("renter")
    if any(w in m for w in ["sell", "worth", "listing my"]) or "home-value" in source:
        tags.append("seller")
    if any(w in m for w in ["buy", "pre-approved", "preapproved", "looking for a"]):
        tags.append("buyer")
    if "pre-approved" in m or "preapproved" in m:
        tags.append("pre-approved")
    return tags


def draft_messages(first: str, tags: list[str]) -> dict:
    if "seller" in tags:
        sms = f"Hi {first}, thanks for reaching out about your home's value! I can put together a free market analysis. What's the best time for a quick call this week?"
    elif "renter" in tags:
        sms = f"Hi {first}, thanks for your rental inquiry! I'll send over what's available for your move-in date. How many bedrooms and what budget are you working with?"
    else:
        sms = f"Hi {first}, thanks for reaching out about buying! I'd love to set up a search that matches what you want. Are you free for a 10-minute call today or tomorrow?"
    email = sms + "\n\nYou can also book a time that works for you here: [booking link]\n"
    return {"sms": sms, "email": email}


def load_crm() -> list[dict]:
    return json.loads(CRM_FILE.read_text()) if CRM_FILE.exists() else []


def push_to_crm(contacts: list[dict]) -> None:
    CRM_FILE.write_text(json.dumps(contacts, indent=2), encoding="utf-8")


def handle_lead(lead: dict, contacts: list[dict]) -> dict:
    email = lead.get("email", "").strip().lower()
    phone = normalize_phone(lead.get("phone", ""))
    name = " ".join(w.capitalize() for w in lead.get("name", "").split())
    tags = tag_lead(lead.get("message", ""), lead.get("source", "website"))

    existing = next((c for c in contacts if c["email"] == email or (phone and c["phone"] == phone)), None)
    if existing:
        existing["tags"] = sorted(set(existing["tags"]) | set(tags))
        existing["notes"].append(lead.get("message", ""))
        return {"status": "updated existing contact", "contact": existing, "messages": None, "task": None}

    contact = {"name": name, "email": email, "phone": phone, "tags": tags, "notes": [lead.get("message", "")]}
    contacts.append(contact)
    msgs = draft_messages(name.split()[0] if name else "there", tags)
    task = {"assignee": "Agent", "due": "within 5 minutes", "title": f"Call new lead {name} ({', '.join(t for t in tags if ':' not in t)})"}
    return {"status": "new contact", "contact": contact, "messages": msgs, "task": task}


def run_demo() -> None:
    print("\n[6] Instant lead response")
    out = out_dir("06_leads")
    contacts = []  # start fresh each demo run
    results = []
    for lead in read_json("leads.json"):
        r = handle_lead(lead, contacts)
        results.append(r)
        print(f"  {r['contact']['name']}: {r['status']} {r['contact']['tags']}")
    push_to_crm(contacts)
    (out / "responses.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


def serve() -> None:
    from flask import Flask, jsonify, request

    app = Flask(__name__)

    @app.post("/webhook/lead")
    def webhook():
        contacts = load_crm()
        result = handle_lead(request.get_json(force=True), contacts)
        push_to_crm(contacts)
        return jsonify(result)

    out_dir("06_leads")
    app.run(port=5000)


def main() -> None:
    run_demo()


if __name__ == "__main__":
    serve() if "--serve" in sys.argv else run_demo()
