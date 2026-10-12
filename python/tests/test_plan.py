"""Unit tests for payment reminder input validation and error handling."""

import unittest
from plan import build_plan, parse_date


class ShapeAndDateTest(unittest.TestCase):
    def test_empty_input_gives_empty_plan(self):
        plan = build_plan([], [], "2026-10-12")
        self.assertEqual(plan, {"today": "2026-10-12", "actions": [], "skipped": []})

    def test_invalid_today_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_plan([], [], "2026-02-30")
        with self.assertRaises(ValueError):
            build_plan([], [], "not-a-date")
        with self.assertRaises(ValueError):
            build_plan([], [], "12/10/2026")


class ValidationEdgeCasesTest(unittest.TestCase):
    def test_duplicate_id_skipped_once(self):
        invoices = [
            {"id": "INV-1", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None},
            {"id": "INV-1", "customer": "B", "amount": 200.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None},
            {"id": "INV-2", "customer": "C", "amount": 300.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None},
        ]
        plan = build_plan(invoices, [], "2026-10-12")
        self.assertEqual(plan["skipped"], [{"invoice_id": "INV-1", "reason": "duplicate_id"}])

    def test_invalid_amount(self):
        cases = [
            {"id": "A1", "customer": "A", "currency": "EUR", "due_date": "2026-09-01", "paid_date": None}, # missing
            {"id": "A2", "customer": "A", "amount": True, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None}, # bool True
            {"id": "A3", "customer": "A", "amount": False, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None}, # bool False
            {"id": "A4", "customer": "A", "amount": "100.0", "currency": "EUR", "due_date": "2026-09-01", "paid_date": None}, # string
            {"id": "A5", "customer": "A", "amount": 0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None}, # 0
            {"id": "A6", "customer": "A", "amount": -50.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None}, # negative
            {"id": "A7", "customer": "A", "amount": float("nan"), "currency": "EUR", "due_date": "2026-09-01", "paid_date": None}, # NaN
            {"id": "A8", "customer": "A", "amount": float("inf"), "currency": "EUR", "due_date": "2026-09-01", "paid_date": None}, # Inf
        ]
        for c in cases:
            plan = build_plan([c], [], "2026-10-12")
            self.assertEqual(plan["skipped"], [{"invoice_id": c["id"], "reason": "invalid_amount"}], f"Failed for {c}")

    def test_missing_due_date(self):
        cases = [
            {"id": "D1", "customer": "A", "amount": 100.0, "currency": "EUR", "paid_date": None}, # missing
            {"id": "D2", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": None, "paid_date": None}, # null
            {"id": "D3", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "", "paid_date": None}, # empty string
        ]
        for c in cases:
            plan = build_plan([c], [], "2026-10-12")
            self.assertEqual(plan["skipped"], [{"invoice_id": c["id"], "reason": "missing_due_date"}], f"Failed for {c}")

    def test_invalid_due_date(self):
        cases = [
            {"id": "ID1", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-02-30", "paid_date": None},
            {"id": "ID2", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "30/09/2026", "paid_date": None},
            {"id": "ID3", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-13-01", "paid_date": None},
            {"id": "ID4", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "invalid", "paid_date": None},
        ]
        for c in cases:
            plan = build_plan([c], [], "2026-10-12")
            self.assertEqual(plan["skipped"], [{"invoice_id": c["id"], "reason": "invalid_due_date"}], f"Failed for {c}")

    def test_invalid_paid_date(self):
        cases = [
            {"id": "P1", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": ""}, # empty string
            {"id": "P2", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": "2026-02-30"}, # bad calendar date
            {"id": "P3", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": "2026-10-13"}, # future (> today)
        ]
        for c in cases:
            plan = build_plan([c], [], "2026-10-12")
            self.assertEqual(plan["skipped"], [{"invoice_id": c["id"], "reason": "invalid_paid_date"}], f"Failed for {c}")

    def test_validation_priority_order(self):
        # 1. duplicate_id takes priority even if amount or dates are bad
        invs = [
            {"id": "DUP", "amount": -5, "due_date": "bad", "paid_date": "bad"},
            {"id": "DUP", "amount": -5, "due_date": "bad", "paid_date": "bad"},
        ]
        plan = build_plan(invs, [], "2026-10-12")
        self.assertEqual(plan["skipped"], [{"invoice_id": "DUP", "reason": "duplicate_id"}])

        # 2. invalid_amount takes priority over missing_due_date
        inv = {"id": "O1", "amount": "bad", "due_date": None, "paid_date": None}
        self.assertEqual(build_plan([inv], [], "2026-10-12")["skipped"][0]["reason"], "invalid_amount")

        # 3. missing_due_date takes priority over invalid_paid_date
        inv = {"id": "O2", "amount": 100.0, "due_date": "", "paid_date": "future-or-bad"}
        self.assertEqual(build_plan([inv], [], "2026-10-12")["skipped"][0]["reason"], "missing_due_date")

        # 4. invalid_due_date takes priority over invalid_paid_date
        inv = {"id": "O3", "amount": 100.0, "due_date": "2026-02-30", "paid_date": "future-or-bad"}
        self.assertEqual(build_plan([inv], [], "2026-10-12")["skipped"][0]["reason"], "invalid_due_date")


if __name__ == "__main__":
    unittest.main()
