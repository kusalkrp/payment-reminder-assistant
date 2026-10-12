"""Unit tests for payment reminder rules engine: validation, overdue calculation, tiers, and sent suppression."""

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
        self.assertEqual(len(plan["actions"]), 1)
        self.assertEqual(plan["actions"][0]["invoice_id"], "INV-2")

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


class RulesLogicTest(unittest.TestCase):
    def test_paid_invoices_plan_nothing(self):
        inv1 = {"id": "I1", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": "2026-10-12"}
        inv2 = {"id": "I2", "customer": "B", "amount": 100.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": "2026-09-15"}
        plan = build_plan([inv1, inv2], [], "2026-10-12")
        self.assertEqual(plan["actions"], [])
        self.assertEqual(plan["skipped"], [])

    def test_overdue_thresholds(self):
        # 0, 1, 2 days overdue and future invoices -> plan nothing
        cases_none = [
            ("2026-10-12", 0),
            ("2026-10-11", 1),
            ("2026-10-10", 2),
            ("2026-10-15", -3),
        ]
        for due, days in cases_none:
            inv = {"id": "T1", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": due, "paid_date": None}
            plan = build_plan([inv], [], "2026-10-12")
            self.assertEqual(plan["actions"], [], f"Expected no action for {days} days overdue")

        # 3 to 9 days -> friendly, needs_approval = False
        for due in ["2026-10-09", "2026-10-03"]:
            inv = {"id": "T2", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": due, "paid_date": None}
            plan = build_plan([inv], [], "2026-10-12")
            self.assertEqual(plan["actions"][0]["step"], "friendly")
            self.assertFalse(plan["actions"][0]["needs_approval"])

        # 10 to 23 days -> firm, needs_approval = True
        for due in ["2026-10-02", "2026-09-19"]:
            inv = {"id": "T3", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": due, "paid_date": None}
            plan = build_plan([inv], [], "2026-10-12")
            self.assertEqual(plan["actions"][0]["step"], "firm")
            self.assertTrue(plan["actions"][0]["needs_approval"])

        # 24+ days -> final, needs_approval = True
        for due in ["2026-09-18", "2026-08-01"]:
            inv = {"id": "T4", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": due, "paid_date": None}
            plan = build_plan([inv], [], "2026-10-12")
            self.assertEqual(plan["actions"][0]["step"], "final")
            self.assertTrue(plan["actions"][0]["needs_approval"])

    def test_sent_suppression_and_single_highest_action(self):
        # 12 days overdue = firm. Nothing sent -> plan firm
        inv = {"id": "S1", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-09-30", "paid_date": None}
        plan = build_plan([inv], [], "2026-10-12")
        self.assertEqual(plan["actions"][0]["step"], "firm")

        # 12 days overdue = firm. Friendly sent -> plan firm
        plan = build_plan([inv], [{"invoice_id": "S1", "step": "friendly", "sent_on": "2026-10-05"}], "2026-10-12")
        self.assertEqual(plan["actions"][0]["step"], "firm")

        # 12 days overdue = firm. Firm sent -> plan nothing
        plan = build_plan([inv], [{"invoice_id": "S1", "step": "firm", "sent_on": "2026-10-05"}], "2026-10-12")
        self.assertEqual(plan["actions"], [])

        # 12 days overdue = firm. Final sent -> plan nothing
        plan = build_plan([inv], [{"invoice_id": "S1", "step": "final", "sent_on": "2026-10-05"}], "2026-10-12")
        self.assertEqual(plan["actions"], [])

        # 30 days overdue = final. Firm sent -> plan final
        inv_final = {"id": "S2", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-09-10", "paid_date": None}
        plan = build_plan([inv_final], [{"invoice_id": "S2", "step": "firm", "sent_on": "2026-09-20"}], "2026-10-12")
        self.assertEqual(plan["actions"][0]["step"], "final")

        # Ignore irrelevant sent entries (unknown IDs or unknown steps)
        plan = build_plan([inv], [
            {"invoice_id": "UNKNOWN", "step": "firm", "sent_on": "2026-10-01"},
            {"invoice_id": "S1", "step": "unknown_step", "sent_on": "2026-10-01"}
        ], "2026-10-12")
        self.assertEqual(plan["actions"][0]["step"], "firm")


class SortingTest(unittest.TestCase):
    def test_character_order_sorting(self):
        # Plain text character-by-character order: INV-100 comes before INV-99
        invoices = [
            {"id": "INV-99", "customer": "A", "amount": 100.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None},
            {"id": "INV-100", "customer": "B", "amount": 200.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None},
            {"id": "INV-10", "customer": "C", "amount": 300.0, "currency": "EUR", "due_date": "2026-09-01", "paid_date": None},
        ]
        plan = build_plan(invoices, [], "2026-10-12")
        ids = [a["invoice_id"] for a in plan["actions"]]
        self.assertEqual(ids, ["INV-10", "INV-100", "INV-99"])

        # Also for skipped
        skipped_invs = [
            {"id": "INV-99", "amount": -1},
            {"id": "INV-100", "amount": -1},
            {"id": "INV-10", "amount": -1},
        ]
        plan2 = build_plan(skipped_invs, [], "2026-10-12")
        skipped_ids = [s["invoice_id"] for s in plan2["skipped"]]
        self.assertEqual(skipped_ids, ["INV-10", "INV-100", "INV-99"])


if __name__ == "__main__":
    unittest.main()
