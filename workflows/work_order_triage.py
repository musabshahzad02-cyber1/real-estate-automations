"""Workflow 1: Work order triage and vendor follow-up.

Reads open maintenance requests, tags each by trade and priority, assigns the
preferred vendor, and drafts follow-up emails for vendors who have gone quiet
past the response window for that priority. Ends with a manager digest.
"""
from datetime import date

from common import ask_claude_json, mode_label, out_dir, read_csv, today, write_csv

# Order matters: the first matching trade wins (gas is checked before appliance).
TRADE_RULES = [
    ("plumbing", ["gas", "sink", "toilet", "leak", "water", "pipe", "drain", "flood", "sewage"]),
    ("electrical", ["outlet", "breaker", "power", "light", "sparking", "wiring"]),
    ("hvac", ["heat", "furnace", "thermostat", "air condition", " ac ", "cooling"]),
    ("appliance", ["dishwasher", "fridge", "refrigerator", "oven", "stove", "washer", "dryer"]),
    ("pest", ["mice", "mouse", "rat", "roach", "ants", "bugs", "bed bug"]),
]
EMERGENCY = ["gas", "flood", "pouring", "burst", "sparking", "smoke", "fire", "sewage", "no water"]
URGENT = ["heat", "hot water", "leak", "outlet", "refrigerator", "fridge", "mice", "rat"]

# Days a vendor can go without an update before we chase them.
FOLLOW_UP_AFTER_DAYS = {"emergency": 0, "urgent": 1, "routine": 3}


def classify_rules(description: str) -> dict:
    text = f" {description.lower()} "
    trade = next((t for t, words in TRADE_RULES if any(w in text for w in words)), "general")
    if any(w in text for w in EMERGENCY):
        priority = "emergency"
    elif any(w in text for w in URGENT):
        priority = "urgent"
    else:
        priority = "routine"
    return {"trade": trade, "priority": priority}


def classify(description: str) -> dict:
    result = ask_claude_json(
        "You triage residential maintenance requests for a property manager.\n"
        f"Request: {description!r}\n"
        'Return {"trade": one of plumbing|electrical|hvac|appliance|pest|general, '
        '"priority": one of emergency|urgent|routine}. Emergency means risk to life or '
        "major property damage (gas, flooding, fire, sewage)."
    )
    if isinstance(result, dict) and result.get("trade") and result.get("priority"):
        return result
    return classify_rules(description)


def main() -> None:
    print(f"\n[1] Work order triage ({mode_label()})")
    vendors = {v["trade"]: v for v in read_csv("vendors.csv")}
    orders = read_csv("work_orders.csv")
    out = out_dir("01_work_orders")
    now = today()

    triaged, chase = [], []
    for wo in orders:
        tag = classify(wo["description"])
        vendor = wo["assigned_vendor"] or vendors.get(tag["trade"], vendors["general"])["vendor"]
        last = wo["last_vendor_update"] or wo["submitted"]
        days_quiet = (now - date.fromisoformat(last)).days
        overdue = days_quiet > FOLLOW_UP_AFTER_DAYS[tag["priority"]] or (
            tag["priority"] == "emergency" and not wo["last_vendor_update"]
        )
        row = {
            "id": wo["id"],
            "property": wo["property"],
            "unit": wo["unit"],
            "tenant": wo["tenant"],
            "trade": tag["trade"],
            "priority": tag["priority"],
            "vendor": vendor,
            "newly_assigned": "yes" if not wo["assigned_vendor"] else "no",
            "days_since_update": days_quiet,
            "needs_follow_up": "yes" if overdue else "no",
        }
        triaged.append(row)
        if overdue:
            chase.append((row, wo))

    order = {"emergency": 0, "urgent": 1, "routine": 2}
    triaged.sort(key=lambda r: (order[r["priority"]], r["id"]))
    write_csv(out / "triaged_work_orders.csv", triaged)

    emails = out / "vendor_emails"
    emails.mkdir(exist_ok=True)
    vendor_info = {v["vendor"]: v for v in read_csv("vendors.csv")}
    for row, wo in chase:
        v = vendor_info.get(row["vendor"], {})
        new = row["newly_assigned"] == "yes"
        subject = (
            f"{'EMERGENCY ' if row['priority'] == 'emergency' else ''}"
            f"{'New work order' if new else 'Status check'}: {row['id']} at {row['property']} #{row['unit']}"
        )
        body = (
            f"To: {v.get('email', '')}\nSubject: {subject}\n\n"
            f"Hi {row['vendor']} team,\n\n"
            + (
                f"We have a new {row['priority']} {row['trade']} request for you:\n"
                if new
                else f"Following up on this {row['priority']} request, last update was "
                f"{row['days_since_update']} day(s) ago:\n"
            )
            + f"\n  {wo['description']}\n  Location: {row['property']}, unit {row['unit']}\n"
            f"  Tenant: {row['tenant']}\n\n"
            "Please reply with your scheduled date and time, or let us know if anything is holding it up.\n\n"
            "Thank you,\nProperty Management Team\n"
        )
        (emails / f"{row['id']}.txt").write_text(body, encoding="utf-8")

    lines = [f"# Maintenance digest for {now:%B %d, %Y}", ""]
    emergencies = [r for r in triaged if r["priority"] == "emergency"]
    if emergencies:
        lines += ["## Call now", ""]
        for r in emergencies:
            lines.append(f"- **{r['id']}** {r['property']} #{r['unit']} ({r['tenant']}): {r['trade']}, vendor {r['vendor']}")
            if "gas" in next(w["description"].lower() for w in orders if w["id"] == r["id"]):
                lines.append("  - Gas smell: tell the tenant to leave the unit and call the gas utility's emergency line first.")
        lines.append("")
    lines += ["## Follow-ups sent", ""]
    lines += [f"- {r['id']} to {r['vendor']} ({r['priority']}, {r['days_since_update']} day(s) without update)" for r, _ in chase]
    lines += ["", "## All open orders", "", "| ID | Priority | Trade | Vendor | Days quiet |", "|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['priority']} | {r['trade']} | {r['vendor']} | {r['days_since_update']} |" for r in triaged]
    (out / "manager_digest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"  {len(triaged)} orders triaged, {len(emergencies)} emergencies, {len(chase)} vendor emails drafted")


if __name__ == "__main__":
    main()
