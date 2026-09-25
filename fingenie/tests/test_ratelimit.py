import pytest

from fingenie.ratelimit import RateExhausted, RateGovernor


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_unmetered_source_never_blocks(tmp_path):
    gov = RateGovernor(tmp_path / "rl.db", budgets={})
    for _ in range(100):
        gov.acquire("frankfurter")  # no budget -> no-op
    assert gov.remaining("frankfurter") == {}


def test_per_minute_budget_exhausts(tmp_path):
    clock = FakeClock()
    gov = RateGovernor(tmp_path / "rl.db", budgets={"x": [(3, 60)]}, clock=clock)
    gov.acquire("x")
    gov.acquire("x")
    gov.acquire("x")
    with pytest.raises(RateExhausted):
        gov.acquire("x")


def test_window_slides(tmp_path):
    clock = FakeClock()
    gov = RateGovernor(tmp_path / "rl.db", budgets={"x": [(2, 60)]}, clock=clock)
    gov.acquire("x")
    gov.acquire("x")
    with pytest.raises(RateExhausted):
        gov.acquire("x")
    clock.t += 61  # old hits fall out of the window
    gov.acquire("x")
    assert gov.remaining("x") == {"60s": 1}


def test_daily_budget_persists_across_instances(tmp_path):
    clock = FakeClock()
    db = tmp_path / "rl.db"
    gov1 = RateGovernor(db, budgets={"x": [(1000, 60), (2, 86_400)]}, clock=clock)
    gov1.acquire("x")
    gov1.acquire("x")
    gov1.close()
    gov2 = RateGovernor(db, budgets={"x": [(1000, 60), (2, 86_400)]}, clock=clock)
    with pytest.raises(RateExhausted):
        gov2.acquire("x")  # daily cap already spent in a prior "process"
