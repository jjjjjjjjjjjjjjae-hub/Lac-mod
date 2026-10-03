import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from economy import EconomyError, Project009Economy


class EconomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parent
        self.engine = Project009Economy(
            root / "config" / "project009.json",
            Path(self.tmp.name) / "state.json",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_start_balances(self):
        self.assertEqual(self.engine.balance("ao_coin"), 2500)
        self.assertEqual(self.engine.balance("gold"), 50)
        self.assertEqual(self.engine.balance("bank"), 10000)

    def test_job_reward(self):
        before = self.engine.balance("ao_coin")
        self.engine.complete_job("taxi")
        self.assertEqual(self.engine.balance("ao_coin"), before + 500)
        self.assertEqual(self.engine.balance("reputation"), 3)

    def test_shop_purchase(self):
        self.engine.credit("ao_coin", 10000, "test")
        self.engine.buy_item("starter_vehicle_skin")
        self.assertIn("starter_vehicle_skin", self.engine.state["owned_items"])
        with self.assertRaises(EconomyError):
            self.engine.buy_item("starter_vehicle_skin")

    def test_cannot_go_negative(self):
        with self.assertRaises(EconomyError):
            self.engine.debit("gold", 999999, "test")

    def test_daily_reward_once(self):
        today = date(2026, 10, 4)
        self.engine.claim_daily(today)
        with self.assertRaises(EconomyError):
            self.engine.claim_daily(today)

    def test_bank_roundtrip(self):
        start_coin = self.engine.balance("ao_coin")
        start_bank = self.engine.balance("bank")
        self.engine.deposit_to_bank(1000)
        self.assertEqual(self.engine.balance("ao_coin"), start_coin - 1000)
        self.assertEqual(self.engine.balance("bank"), start_bank + 1000)
        self.engine.withdraw_from_bank(1000)
        self.assertEqual(self.engine.balance("bank"), start_bank)
        self.assertEqual(self.engine.balance("ao_coin"), start_coin - 10)


if __name__ == "__main__":
    unittest.main()
