"""Workflow 2: Delinquency tracking and five-day notices.

After the grace period, computes each tenant's balance from the rent ledger,
separates unpaid rent from late fees, sends a reminder to anyone with a balance,
and prepares a five-day notice for tenants who owe rent. Notices demand rent
only, since many jurisdictions (Illinois among them) treat fees separately.
The batch goes to a manager for approval before anything is served.

This is a template, not legal advice. Have the client's attorney approve the
notice wording for their state.
"""
from collections import defaultdict

from common import money, out_dir, read_csv, today, write_csv

GRACE_DAYS = 5  # rent due on the 1st, late after the 5th

NOTICE = """LANDLORD'S FIVE DAY NOTICE (TEMPLATE, attorney review required)

To: {name}
Premises: {property}, Unit {unit}

You are hereby notified that in consequence of your default in payment of rent
for the premises above, I have elected to terminate your lease unless payment is
made. Rent now due and unpaid: {rent_due}

Unless payment of the rent due is made on or before the expiration of five (5)
days after service of this notice, your lease of the premises will be terminated.
Only FULL payment of the rent demanded in this notice will waive the landlord's
right to terminate the lease, unless the landlord agrees in writing to accept
partial payment.

Date prepared: {date}

______________________________
Landlord / Authorized Agent

AFFIDAVIT OF SERVICE
I served this notice on ____________ (date) by:
[ ] delivering a copy to the tenant  [ ] leaving a copy with a person 13 or older residing at the premises
[ ] certified mail, return receipt requested  [ ] posting, no one in actual possession
"""


def main() -> None:
    print("\n[2] Delinquency and five-day notices")
    now = today()
    if now.day <= GRACE_DAYS:
        print(f"  Still in grace period (day {now.day}), nothing to send.")
        return

    tenants = {t["tenant_id"]: t for t in read_csv("tenants.csv")}
    rent = defaultdict(float)
    fees = defaultdict(float)
    paid = defaultdict(float)
    for row in read_csv("rent_ledger.csv"):
        amt = float(row["amount"])
        if row["type"] in ("rent", "balance_forward"):
            rent[row["tenant_id"]] += amt
        elif row["type"] == "late_fee":
            fees[row["tenant_id"]] += amt
        elif row["type"] == "payment":
            paid[row["tenant_id"]] += amt

    out = out_dir("02_delinquency")
    notices = out / "five_day_notices"
    reminders = out / "reminders"
    notices.mkdir(exist_ok=True)
    reminders.mkdir(exist_ok=True)

    log = []
    for tid, t in tenants.items():
        total = rent[tid] + fees[tid] - paid[tid]
        if total <= 0:
            continue
        rent_due = max(0.0, rent[tid] - paid[tid])
        fee_due = round(total - rent_due, 2)
        action = "five-day notice + reminder" if rent_due > 0 else "reminder only (fees)"

        reminder = (
            f"To: {t['email']} | SMS: {t['phone']}\n\n"
            f"Hi {t['name'].split()[0]}, this is a reminder that your account for {t['property']} unit {t['unit']} "
            f"shows a balance of {money(total)}"
            + (f" ({money(rent_due)} rent, {money(fee_due)} late fees)" if rent_due and fee_due else "")
            + ". You can pay through your tenant portal. If you've already paid, please disregard this message. "
            "Reply here if you need to discuss a payment plan.\n"
        )
        (reminders / f"{tid}.txt").write_text(reminder, encoding="utf-8")

        if rent_due > 0:
            (notices / f"{tid}_{t['name'].replace(' ', '_')}.txt").write_text(
                NOTICE.format(
                    name=t["name"],
                    property=t["property"],
                    unit=t["unit"],
                    rent_due=money(rent_due),
                    date=now.strftime("%B %d, %Y"),
                ),
                encoding="utf-8",
            )
        log.append(
            {
                "tenant_id": tid,
                "tenant": t["name"],
                "property": t["property"],
                "unit": t["unit"],
                "rent_due": f"{rent_due:.2f}",
                "late_fees_due": f"{fee_due:.2f}",
                "total_balance": f"{total:.2f}",
                "action": action,
                "manager_approved": "",
                "served_date": "",
                "service_method": "",
            }
        )

    write_csv(out / "notice_batch_log.csv", log)
    n = sum(1 for r in log if r["action"].startswith("five"))
    total_rent = sum(float(r["rent_due"]) for r in log)
    print(f"  {len(log)} tenants with balances, {n} five-day notices prepared, {money(total_rent)} rent outstanding")


if __name__ == "__main__":
    main()
