"""No test may open the committed production database for mutation."""
from pathlib import Path

import pytest

from lottery_assistant.db import DB

PRODUCTION_DB = Path(__file__).resolve().parents[1] / 'data/lottery.db'


@pytest.fixture(autouse=True)
def protect_production_db(monkeypatch):
    original = DB.__init__
    attempts = []
    def isolated_init(self, path):
        if Path(path).resolve() == PRODUCTION_DB:
            attempts.append(str(path))
            raise AssertionError('test attempted to open production DB; use a temporary copy')
        original(self, path)
    monkeypatch.setattr(DB, '__init__', isolated_init)
    yield
    assert not attempts, f'test tried production DB access (possibly caught by runtime): {attempts}'
