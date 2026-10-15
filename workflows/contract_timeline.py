"""Workflow 5: Contract to close timeline.

Reads an executed contract, extracts the parties and every deadline, rolls
deadlines that land on a weekend to the next business day, and produces:
  - timeline.md for the TC to review
  - deadlines.ics, a calendar file with a reminder the day before each deadline
  - intro emails to lender, title, and both agents

With ANTHROPIC_API_KEY set, Claude reads the contract text (works on real,
messy contract wording). Without it, a parser handles the sample format.
The TC reviews every extracted date before anything is sent.
"""
import re
from datetime import date, datetime, timedelta, timezone

from common import DATA, ask_claude_json, mode_label, out_dir

ROLL_WEEKENDS = True  # many contracts move a weekend deadline to the next business day


def parse_rules(text: str) -> dict:
    def field(label):
        m = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.M)
        return m.group(1).strip() if m else ""

    effective = datetime.strptime(field("Effective Date"), "%B %d, %Y").date()
    deadlines = []
    for m in re.finditer(r"^([^:\n]+):.*?within (\d+) days after the Effective Date|^([^:\n]+):.*?ends (\d+) days after the Effective Date",
                         text, re.M):
        label = (m.group(1) or m.group(3)).strip()
        days = int(m.group(2) or m.group(4))
        deadlines.append({"name": label, "days_after_effective": days})
    closing = field("Closing Date")
    if closing:
        deadlines.append({"name": "Closing", "date": datetime.strptime(closing, "%B %d, %Y").date().isoformat()})

    def contact(label):
        m = re.match(r"(.*?)\s*\(([^)]+@[^)]+)\)", field(label))
        return {"name": m.group(1).strip(" ,"), "email": m.group(2)} if m else {"name": field(label), "email": ""}

    return {
        "property": field("Property"),
        "price": field("Sales Price"),
        "effective_date": effective.isoformat(),
        "buyer": contact("Buyer"),
        "seller": contact("Seller"),
        "lender": contact("Lender"),
        "title": contact("Title Company"),
        "listing_agent": contact("Listing Agent"),
        "buyers_agent": contact("Buyer's Agent"),
        "deadlines": deadlines,
    }


def extract(text: str) -> dict:
    ai = ask_claude_json(
        "Extract the key terms from this real estate contract.\n\n" + text + "\n\n"
        'Return {"property", "price", "effective_date" (YYYY-MM-DD), '
        '"buyer", "seller", "lender", "title", "listing_agent", "buyers_agent" (each {"name","email"}), '
        '"deadlines": [{"name", "days_after_effective" (int) OR "date" (YYYY-MM-DD)}]}.',
        max_tokens=1500,
    )
    if isinstance(ai, dict) and ai.get("effective_date") and ai.get("deadlines"):
        return ai
    return parse_rules(text)


def business_day(d: date) -> date:
    while ROLL_WEEKENDS and d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def ics_event(uid: str, title: str, day: date, description: str) -> str:
    nxt = day + timedelta(days=1)
    return "\r\n".join([
        "BEGIN:VEVENT",
        f"UID:{uid}@real-estate-automations",
        f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
        f"DTEND;VALUE=DATE:{nxt:%Y%m%d}",
        f"SUMMARY:{title}",
        f"DESCRIPTION:{description}",
        "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY", f"DESCRIPTION:Tomorrow: {title}", "END:VALARM",
        "END:VEVENT",
    ])


def main() -> None:
    print(f"\n[5] Contract to close timeline ({mode_label()})")
    text = (DATA / "sample_contract.txt").read_text(encoding="utf-8")
    c = extract(text)
    effective = date.fromisoformat(c["effective_date"])

    timeline = []
    for dl in c["deadlines"]:
        raw = date.fromisoformat(dl["date"]) if dl.get("date") else effective + timedelta(days=int(dl["days_after_effective"]))
        due = business_day(raw)
        timeline.append({"name": dl["name"], "due": due, "rolled": due != raw})
    timeline.sort(key=lambda x: x["due"])

    out = out_dir("05_contract_timeline")
    addr = c["property"]
    lines = [f"# Transaction timeline: {addr}", "",
             f"**Buyer:** {c['buyer']['name']}  ", f"**Seller:** {c['seller']['name']}  ",
             f"**Price:** {c['price']}  ", f"**Effective date:** {effective:%A, %B %d, %Y}", "",
             "| Deadline | Due | Note |", "|---|---|---|"]
    lines += [f"| {t['name']} | {t['due']:%a %b %d, %Y} | {'Moved off weekend' if t['rolled'] else ''} |" for t in timeline]
    lines += ["", "_Review every date against the executed contract before sending intro emails._"]
    (out / "timeline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    events = [ics_event(f"{i}-{t['due']:%Y%m%d}", f"{t['name']}: {addr}", t["due"],
                        f"{t['name']} deadline for {addr}") for i, t in enumerate(timeline)]
    cal = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//real-estate-automations//TC//EN", *events, "END:VCALENDAR"]) + "\r\n"
    (out / "deadlines.ics").write_bytes(cal.encode("utf-8"))

    dates_block = "\n".join(f"  - {t['name']}: {t['due']:%A, %B %d}" for t in timeline)
    emails = out / "intro_emails"
    emails.mkdir(exist_ok=True)
    for role, key in [("lender", "lender"), ("title", "title"), ("listing agent", "listing_agent"), ("buyer's agent", "buyers_agent")]:
        person = c.get(key) or {}
        if not person.get("name"):
            continue
        body = (
            f"To: {person.get('email', '')}\nSubject: Under contract: {addr}\n\n"
            f"Hi {person['name'].split(',')[0].split()[0]},\n\n"
            f"I'm the transaction coordinator on {addr} ({c['buyer']['name']} buying from {c['seller']['name']}, "
            f"{c['price']}). Here are the key dates from the executed contract:\n\n{dates_block}\n\n"
            "Please reply-all with anything you need from us, and send documents to me so I can keep the file complete.\n\n"
            "Thank you,\nTransaction Coordinator\n"
        )
        (emails / f"{role.replace(' ', '_').replace(chr(39), '')}.txt").write_text(body, encoding="utf-8")

    for t in timeline:
        print(f"  {t['name']}: {t['due']:%a %b %d}{' (moved off weekend)' if t['rolled'] else ''}")


if __name__ == "__main__":
    main()
