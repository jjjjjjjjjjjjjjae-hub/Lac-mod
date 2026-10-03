from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict


class EconomyError(Exception):
    pass


@dataclass
class Transaction:
    tx_id: str
    timestamp: str
    kind: str
    currency: str
    amount: int
    balance_after: int
    note: str


class Project009Economy:
    """Local-first economy core for Almas Official / Project 009.

    The engine is intentionally independent from Unity so it can later be bridged
    to PlayerPrefs, a native Android layer, or a server API without rewriting the
    business rules.
    """

    def __init__(self, config_path: str | Path, state_path: str | Path):
        self.config_path = Path(config_path)
        self.state_path = Path(state_path)
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.eco = self.config["economy"]
        self.state = self._load_or_create_state()

    def _load_or_create_state(self) -> Dict[str, Any]:
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._validate_state(state)
            return state

        balances = {
            key: int(spec["start_balance"])
            for key, spec in self.eco["currencies"].items()
        }
        state = {
            "version": 1,
            "balances": balances,
            "ledger": [],
            "daily": {"last_claim": None, "streak": 0},
            "owned_items": [],
        }
        self._save(state)
        return state

    def _validate_state(self, state: Dict[str, Any]) -> None:
        if "balances" not in state or "ledger" not in state:
            raise EconomyError("Economy state is invalid or incomplete")
        for currency in self.eco["currencies"]:
            state["balances"].setdefault(
                currency, int(self.eco["currencies"][currency]["start_balance"])
            )

    def _save(self, state: Dict[str, Any] | None = None) -> None:
        if state is not None:
            self.state = state
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.state_path)

    def _currency_spec(self, currency: str) -> Dict[str, Any]:
        try:
            return self.eco["currencies"][currency]
        except KeyError as exc:
            raise EconomyError(f"Unknown currency: {currency}") from exc

    def balance(self, currency: str) -> int:
        self._currency_spec(currency)
        return int(self.state["balances"][currency])

    def balances(self) -> Dict[str, int]:
        return {k: int(v) for k, v in self.state["balances"].items()}

    def _new_tx_id(self, kind: str, currency: str, amount: int, note: str) -> str:
        raw = f"{datetime.now(timezone.utc).isoformat()}|{kind}|{currency}|{amount}|{note}|{len(self.state['ledger'])}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _apply(self, currency: str, delta: int, kind: str, note: str = "") -> Transaction:
        spec = self._currency_spec(currency)
        current = self.balance(currency)
        new_balance = current + int(delta)
        minimum = int(spec.get("min_balance", 0))
        maximum = int(spec.get("max_balance", 2**63 - 1))

        if new_balance < minimum:
            raise EconomyError(
                f"Insufficient {currency}: {current} available, {abs(delta)} requested"
            )
        if new_balance > maximum:
            raise EconomyError(f"{currency} balance limit exceeded")

        self.state["balances"][currency] = new_balance
        tx = Transaction(
            tx_id=self._new_tx_id(kind, currency, int(delta), note),
            timestamp=datetime.now(timezone.utc).isoformat(),
            kind=kind,
            currency=currency,
            amount=int(delta),
            balance_after=new_balance,
            note=note,
        )
        self.state["ledger"].append(tx.__dict__)
        self._save()
        return tx

    def credit(self, currency: str, amount: int, note: str = "") -> Transaction:
        if amount <= 0:
            raise EconomyError("Credit amount must be positive")
        return self._apply(currency, amount, "credit", note)

    def debit(self, currency: str, amount: int, note: str = "") -> Transaction:
        if amount <= 0:
            raise EconomyError("Debit amount must be positive")
        return self._apply(currency, -amount, "debit", note)

    def complete_job(self, job_id: str) -> Dict[str, Transaction]:
        jobs = self.eco.get("jobs", {})
        if job_id not in jobs:
            raise EconomyError(f"Unknown job: {job_id}")
        job = jobs[job_id]
        out: Dict[str, Transaction] = {}
        reward = int(job.get("reward_ao_coin", 0))
        reputation = int(job.get("reputation", 0))
        if reward:
            out["ao_coin"] = self.credit("ao_coin", reward, f"job:{job_id}")
        if reputation:
            out["reputation"] = self.credit(
                "reputation", reputation, f"job:{job_id}"
            )
        return out

    def buy_item(self, item_id: str) -> Transaction:
        shop = self.eco.get("shop", {})
        if item_id not in shop:
            raise EconomyError(f"Unknown shop item: {item_id}")
        if item_id in self.state["owned_items"]:
            raise EconomyError("Item already owned")

        item = shop[item_id]
        currency = item["currency"]
        price = int(item["price"])
        tx = self.debit(currency, price, f"shop:{item_id}")
        self.state["owned_items"].append(item_id)
        self._save()
        return tx

    def deposit_to_bank(self, ao_coin_amount: int) -> Dict[str, Transaction]:
        if ao_coin_amount <= 0:
            raise EconomyError("Deposit amount must be positive")
        fee_pct = float(self.eco.get("banking", {}).get("deposit_fee_percent", 0.0))
        fee = int(round(ao_coin_amount * fee_pct / 100.0))
        credited = ao_coin_amount - fee
        if credited <= 0:
            raise EconomyError("Deposit is too small after fee")

        debit_tx = self.debit("ao_coin", ao_coin_amount, "bank:deposit")
        credit_tx = self.credit("bank", credited, "bank:deposit")
        return {"debit": debit_tx, "credit": credit_tx}

    def withdraw_from_bank(self, bank_amount: int) -> Dict[str, Transaction]:
        if bank_amount <= 0:
            raise EconomyError("Withdrawal amount must be positive")
        fee_pct = float(self.eco.get("banking", {}).get("withdraw_fee_percent", 0.0))
        fee = int(round(bank_amount * fee_pct / 100.0))
        credited = bank_amount - fee
        if credited <= 0:
            raise EconomyError("Withdrawal is too small after fee")

        debit_tx = self.debit("bank", bank_amount, "bank:withdraw")
        credit_tx = self.credit("ao_coin", credited, "bank:withdraw")
        return {"debit": debit_tx, "credit": credit_tx}

    def claim_daily(self, today: date | None = None) -> Dict[str, Transaction]:
        today = today or date.today()
        daily = self.state["daily"]
        last_raw = daily.get("last_claim")
        last = date.fromisoformat(last_raw) if last_raw else None

        if last == today:
            raise EconomyError("Daily reward already claimed today")

        if last == today - timedelta(days=1):
            streak = int(daily.get("streak", 0)) + 1
        else:
            streak = 1

        rewards = self.eco.get("daily_rewards", [])
        if not rewards:
            raise EconomyError("Daily rewards are not configured")

        index = (streak - 1) % len(rewards)
        reward = rewards[index]
        out: Dict[str, Transaction] = {}

        for currency in ("ao_coin", "gold"):
            amount = int(reward.get(currency, 0))
            if amount > 0:
                out[currency] = self.credit(
                    currency, amount, f"daily:day{reward.get('day', index + 1)}"
                )

        daily["last_claim"] = today.isoformat()
        daily["streak"] = streak
        self._save()
        return out

    def snapshot(self) -> Dict[str, Any]:
        return {
            "balances": self.balances(),
            "owned_items": list(self.state["owned_items"]),
            "daily": dict(self.state["daily"]),
            "ledger_size": len(self.state["ledger"]),
        }


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    engine = Project009Economy(
        here / "config" / "project009.json",
        here / "runtime" / "economy_state.json",
    )
    print(json.dumps(engine.snapshot(), ensure_ascii=False, indent=2))
