"""Payment reminder rules engine (part 1 & part 3).

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

STEP_WEIGHTS = {
    "friendly": 1,
    "firm": 2,
    "final": 3,
}


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


def format_message(customer, invoice_id, amount, currency, due_date_str, days_overdue, step):
    """Generate email reminder message adhering strictly to requirements:

    - Customer name, invoice id, due date (YYYY-MM-DD)
    - Amount with currency and 2 decimals
    - Number of days overdue
    - Tone fitting step: friendly, firm, or final
    - No other figures, no made-up claims/fees/deadlines, no mention of earlier reminders
    """
    amount_str = f"{currency} {amount:.2f}"
    if step == "friendly":
        return (
            f"Dear {customer},\n\n"
            f"This is a friendly reminder that invoice {invoice_id} for {amount_str} "
            f"was due on {due_date_str} and is now {days_overdue} days overdue. "
            f"Please let us know once payment has been arranged.\n\n"
            f"Best regards"
        )
    elif step == "firm":
        return (
            f"Dear {customer},\n\n"
            f"Please be advised that payment for invoice {invoice_id} in the amount of {amount_str} "
            f"remains outstanding. It was due on {due_date_str} and is currently {days_overdue} days overdue. "
            f"Please arrange settlement as soon as possible.\n\n"
            f"Sincerely"
        )
    elif step == "final":
        return (
            f"Dear {customer},\n\n"
            f"This is a final notice regarding overdue invoice {invoice_id} for {amount_str}. "
            f"The invoice was due on {due_date_str} and is now {days_overdue} days overdue. "
            f"Immediate payment is required.\n\n"
            f"Sincerely"
        )
    return ""


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

    # Map sent reminders: highest valid step sent per invoice_id
    max_sent_step = {}
    if isinstance(sent, list):
        for entry in sent:
            if isinstance(entry, dict):
                inv_id = entry.get("invoice_id")
                step = entry.get("step")
                if inv_id and step in STEP_WEIGHTS:
                    current_max = max_sent_step.get(inv_id, 0)
                    max_sent_step[inv_id] = max(current_max, STEP_WEIGHTS[step])

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

        # 2. Paid check: if paid_date <= today, plan nothing
        if paid_date is not None and paid_date <= today_date:
            continue

        # 3. Not yet: fewer than 3 days overdue -> plan nothing
        days_overdue = (today_date - due_date).days
        if days_overdue < 3:
            continue

        # 4. Highest step reached
        if days_overdue >= 24:
            step = "final"
            needs_approval = True
            step_weight = STEP_WEIGHTS["final"]
        elif days_overdue >= 10:
            step = "firm"
            needs_approval = True
            step_weight = STEP_WEIGHTS["firm"]
        else:
            step = "friendly"
            needs_approval = False
            step_weight = STEP_WEIGHTS["friendly"]

        # If that step, or a higher one, is already in sent.json, plan nothing
        sent_weight = max_sent_step.get(inv_id, 0)
        if sent_weight >= step_weight:
            continue

        customer = inv.get("customer", "")
        currency = inv.get("currency", "")
        due_date_raw = inv.get("due_date", "")
        amount = inv.get("amount", 0.0)

        message = format_message(
            customer=customer,
            invoice_id=inv_id,
            amount=amount,
            currency=currency,
            due_date_str=due_date_raw,
            days_overdue=days_overdue,
            step=step,
        )

        actions.append({
            "invoice_id": inv_id,
            "step": step,
            "needs_approval": needs_approval,
            "days_overdue": days_overdue,
            "message": message,
        })

    # Plain text character-by-character sorting by invoice_id
    actions.sort(key=lambda a: str(a["invoice_id"]))
    skipped.sort(key=lambda s: str(s["invoice_id"]))

    return {"today": today, "actions": actions, "skipped": skipped}


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Plan today's payment reminders.")
    parser.add_argument("--invoices", required=True, help="path to invoices.json")
    parser.add_argument("--sent", required=True, help="path to sent.json")
    parser.add_argument("--today", required=True, help="date as YYYY-MM-DD")
    parser.add_argument("--out", required=True, help="path to write the plan JSON")
    args = parser.parse_args()

    # Validate --today argument
    if parse_date(args.today) is None:
        sys.stderr.write(f"Error: Invalid --today date '{args.today}'. Must be a valid date in YYYY-MM-DD format.\n")
        sys.exit(1)

    # Read invoices file
    try:
        invoices = read_json(args.invoices)
    except Exception as e:
        sys.stderr.write(f"Error: Could not read invoices file '{args.invoices}': {e}\n")
        sys.exit(1)

    # Read sent file
    try:
        sent = read_json(args.sent)
    except Exception as e:
        sys.stderr.write(f"Error: Could not read sent file '{args.sent}': {e}\n")
        sys.exit(1)

    # Build the plan
    try:
        plan = build_plan(invoices, sent, args.today)
    except Exception as e:
        sys.stderr.write(f"Error: Failed to build reminder plan: {e}\n")
        sys.exit(1)

    # Write output JSON
    try:
        out_dir = os.path.dirname(args.out)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
            f.write("\n")
    except Exception as e:
        sys.stderr.write(f"Error: Could not write output file '{args.out}': {e}\n")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
