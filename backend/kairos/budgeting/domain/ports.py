"""Ports for Budgeting."""

from __future__ import annotations

from abc import ABC, abstractmethod

from kairos.budgeting.domain.spend_ledger import SpendLedger


class SpendLedgerRepository(ABC):
    @abstractmethod
    def current(self) -> SpendLedger:
        """The ledger for today, rolled forward if the date has moved on."""

    @abstractmethod
    def save(self, ledger: SpendLedger) -> None: ...
