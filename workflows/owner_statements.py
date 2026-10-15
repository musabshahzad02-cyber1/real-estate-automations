"""Workflow 3: Month-end reconciliation and owner statements.

1. Matches every general ledger entry to the bank feed (same amount, within 3 days).
2. Flags likely duplicates, miscoded entries, and unmatched items on either side.
3. Builds an owner statement per property with income, expenses, management fee,
   and net to owner. Statements with open exceptions are marked HOLD.
"""
from collections import defaultdict
from datetime import date

from common import money, out_dir, read_csv, today

MATCH_WINDOW_DAYS = 3
DUPLICATE_WINDOW_DAYS = 3

# Payee keywords -> the account that payee should be coded to.
EXPECTED_ACCOUNT = [
    (["home depot", "lowe's", "lowes", "menards", "rooter", "plumbing", "hvac", "electric", "handy"], "Repairs & Maintenance"),
    (["pest"], "Pest Control"),
    (["water", "gas co", "power", "utility"], "Utilities"),
]


def d(s: str) -> date:
    return date.fromisoformat(s)


def expected_account(payee: str):
    p = payee.lower()
    return next((acct for words, acct in EXPECTED_ACCOUNT if any(w in p for w in words)), None)


def main() -> None:
    print("\n[3] Month-end reconciliation and owner statements")
    gl = read_csv("general_ledger.csv")
    bank = read_csv("bank_feed.csv")
    props = {p["property"]: p for p in read_csv("properties.csv")}
    tenant_names = {t["name"] for t in read_csv("tenants.csv")}
    for e in gl:
        e["amount"] = float(e["amount"])
    for b in bank:
        b["amount"] = float(b["amount"])

    exceptions = []  # (property or None, kind, detail, gl entry or None)

    # Duplicates: same property, payee and amount within a few days.
    dup_refs = set()
    for i, a in enumerate(gl):
        for b in gl[i + 1:]:
            if (
                a["property"] == b["property"]
                and a["payee"] == b["payee"]
                and a["amount"] == b["amount"]
                and abs((d(a["date"]) - d(b["date"])).days) <= DUPLICATE_WINDOW_DAYS
            ):
                dup_refs.add(b["ref"])
                exceptions.append((b["property"], "Possible duplicate",
                                   f"{b['ref']} {b['payee']} {money(b['amount'])} on {b['date']} repeats {a['ref']} on {a['date']}", b))

    # Miscoding: expense in an income account, or payee coded to the wrong account.
    for e in gl:
        exp = expected_account(e["payee"])
        if e["account"] == "Rent Income" and (e["amount"] < 0 or e["payee"] not in tenant_names):
            exceptions.append((e["property"], "Miscoded",
                               f"{e['ref']} {e['payee']} {money(e['amount'])} is coded to Rent Income"
                               + (f"; should likely be {exp}" if exp else ""), e))
        elif exp and e["account"] != exp:
            exceptions.append((e["property"], "Miscoded",
                               f"{e['ref']} {e['payee']} coded to {e['account']}; expected {exp}", e))

    # Bank matching, one-to-one, closest date first.
    unmatched_bank = list(bank)
    for e in gl:
        candidates = [b for b in unmatched_bank
                      if b["amount"] == e["amount"] and abs((d(b["date"]) - d(e["date"])).days) <= MATCH_WINDOW_DAYS]
        if candidates:
            best = min(candidates, key=lambda b: abs((d(b["date"]) - d(e["date"])).days))
            unmatched_bank.remove(best)
            e["cleared"] = True
        else:
            e["cleared"] = False
            if e["ref"] not in dup_refs:
                exceptions.append((e["property"], "Not in bank",
                                   f"{e['ref']} {e['payee']} {money(e['amount'])} has no matching bank transaction", e))
    for b in unmatched_bank:
        exceptions.append((None, "Not in ledger",
                           f"Bank item {b['date']} '{b['description']}' {money(b['amount'])} has no ledger entry", None))

    out = out_dir("03_month_end")
    month = today().strftime("%B %Y")

    ex_lines = [f"# Reconciliation exceptions, {month}", "",
                f"{len(exceptions)} item(s) need review before statements go out.", "",
                "| Property | Issue | Detail |", "|---|---|---|"]
    ex_lines += [f"| {p or 'Unassigned'} | {k} | {det} |" for p, k, det, _ in exceptions]
    (out / "exceptions.md").write_text("\n".join(ex_lines) + "\n", encoding="utf-8")

    statements = out / "owner_statements"
    statements.mkdir(exist_ok=True)
    by_prop = defaultdict(list)
    for e in gl:
        if e["ref"] not in dup_refs:  # hold duplicates out until reviewed
            by_prop[e["property"]].append(e)

    summary = []
    for name, info in props.items():
        entries = by_prop.get(name, [])
        rent_collected = sum(e["amount"] for e in entries if e["account"] == "Rent Income" and e["amount"] > 0)
        expenses = [e for e in entries if e["amount"] < 0]
        expense_total = sum(e["amount"] for e in expenses)
        fee = round(rent_collected * float(info["mgmt_fee_pct"]) / 100, 2)
        net = rent_collected + expense_total - fee
        open_items = [x for x in exceptions if x[0] == name]
        status = "HOLD: resolve exceptions first" if open_items else "Ready to send"

        lines = [f"# Owner statement: {name}", "",
                 f"**Owner:** {info['owner']}  ", f"**Period:** {month}  ", f"**Status:** {status}", "",
                 "## Income", "", "| Date | Description | Amount |", "|---|---|---:|"]
        lines += [f"| {e['date']} | Rent, {e['payee']} | {money(e['amount'])} |"
                  for e in entries if e["account"] == "Rent Income" and e["amount"] > 0]
        lines += [f"| | **Total rent collected** | **{money(rent_collected)}** |", "",
                  "## Expenses", "", "| Date | Payee | Account | Amount |", "|---|---|---|---:|"]
        lines += [f"| {e['date']} | {e['payee']} | {e['account']} | {money(e['amount'])} |" for e in expenses]
        lines += [f"| | | **Total expenses** | **{money(expense_total)}** |", "",
                  "## Summary", "", "| | Amount |", "|---|---:|",
                  f"| Rent collected | {money(rent_collected)} |",
                  f"| Expenses | {money(expense_total)} |",
                  f"| Management fee ({info['mgmt_fee_pct']}% of collected rent) | {money(-fee)} |",
                  f"| **Net to owner** | **{money(net)}** |"]
        if open_items:
            lines += ["", "## Open items", ""] + [f"- {k}: {det}" for _, k, det, _ in open_items]
        (statements / f"{name.replace(' ', '_')}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        summary.append((name, net, status))

    for name, net, status in summary:
        print(f"  {name}: net to owner {money(net)} ({status})")
    print(f"  {len(exceptions)} exceptions written to exceptions.md")


if __name__ == "__main__":
    main()
