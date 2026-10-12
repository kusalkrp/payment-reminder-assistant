"""Payment reminder rules engine (part 1).

Run from inside python/:

    python plan.py --invoices ../data/invoices.json --sent ../data/sent.json --today 2026-10-12 --out ../actions.json
"""

import argparse
from collections import Counter
from datetime import date, datetime
import json
import math
import os
import re
import sys

DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(date_str):
    """Parse a date string in YYYY-MM-DD format if valid, else return None."""
    if not isinstance(date_str, str):
        return None
    if not DATE_REGEX.match(date_str):
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def validate_invoice(inv, today_date, duplicate_ids):
    """Check an invoice for bad data in the strict order required by specification:

    1. duplicate_id: Handled at collection level
    2. invalid_amount: missing, not a JSON number (bool or non-number), or <= 0
    3. missing_due_date: missing, null, or empty string ""
    4. invalid_due_date: not a real calendar date in YYYY-MM-DD format
    5. invalid_paid_date: not null and not a real YYYY-MM-DD date, or date > today

    Returns (reason, parsed_due_date, parsed_paid_date) where reason is None if valid.
    """
    if not isinstance(inv, dict):
        return ("invalid_amount", None, None)

    inv_id = str(inv.get("id")) if inv.get("id") is not None else ""

    if inv_id in duplicate_ids:
        return ("duplicate_id", None, None)

    # 2. invalid_amount
    amount = inv.get("amount")
    if (
        amount is None
        or isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or math.isnan(amount)
        or math.isinf(amount)
        or amount <= 0
    ):
        return ("invalid_amount", None, None)

    # 3. missing_due_date
    due_date_raw = inv.get("due_date")
    if due_date_raw is None or due_date_raw == "":
        return ("missing_due_date", None, None)

    # 4. invalid_due_date
    due_date = parse_date(due_date_raw)
    if due_date is None:
        return ("invalid_due_date", None, None)

    # 5. invalid_paid_date
    paid_date_raw = inv.get("paid_date")
    paid_date = None
    if paid_date_raw is not None:
        paid_date = parse_date(paid_date_raw)
        if paid_date is None or paid_date > today_date:
            return ("invalid_paid_date", None, None)

    return (None, due_date, paid_date)


def build_plan(invoices, sent, today):
    """Return the plan for `today` as a dict with the keys today, actions and skipped.

    invoices: the list from invoices.json
    sent: the list from sent.json
    today: a date string, YYYY-MM-DD
    """
    today_date = parse_date(today)
    if today_date is None:
        raise ValueError(f"Invalid today date: {today}")

    actions = []
    skipped = []

    if not isinstance(invoices, list):
        return {"today": today, "actions": [], "skipped": []}

    # Count IDs to identify duplicates across the file
    id_counts = Counter()
    for inv in invoices:
        if isinstance(inv, dict) and "id" in inv and inv["id"] is not None:
            id_counts[str(inv["id"])] += 1

    duplicate_ids = {inv_id for inv_id, count in id_counts.items() if count > 1}

    # Every duplicate id is skipped once
    for dup_id in duplicate_ids:
        skipped.append({"invoice_id": dup_id, "reason": "duplicate_id"})

    for inv in invoices:
        if not isinstance(inv, dict):
            continue

        inv_id = str(inv.get("id")) if inv.get("id") is not None else ""

        # Skip invoices already marked as duplicate
        if inv_id in duplicate_ids:
            continue

        reason, due_date, paid_date = validate_invoice(inv, today_date, duplicate_ids)
        if reason:
            skipped.append({"invoice_id": inv_id, "reason": reason})
            continue

    skipped.sort(key=lambda s: str(s["invoice_id"]))

    return {"today": today, "actions": actions, "skipped": skipped}


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Plan today's payment reminders.")
    parser.add_argument("--invoices", required=True, help="path to invoices.json")
    parser.add_argument("--sent", required=True, help="path to sent.json")
    parser.add_argument("--today", required=True, help="date as YYYY-MM-DD")
    parser.add_argument("--out", required=True, help="path to write the plan JSON")
    args = parser.parse_args()

    invoices = read_json(args.invoices)
    sent = read_json(args.sent)
    plan = build_plan(invoices, sent, args.today)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
