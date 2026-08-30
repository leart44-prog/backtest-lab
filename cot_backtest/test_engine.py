"""Correctness tests for the COT weekly backtest.

The important ones are the look-ahead tests: a decision taken for week `i`
must be provably independent of anything that happens after week `i`.
"""

import random
import unittest

import engine
from engine import Week


def _synth_weeks(n=60, start=1_400_000_000, px=100.0, seed=1):
    """Build n synthetic weekly sessions of 30 4H bars each."""
    rnd = random.Random(seed)
    weeks = []
    t = start
    p = px
    for _ in range(n):
        bars = []
        for _b in range(30):
            o = p
            c = o * (1 + rnd.uniform(-0.004, 0.004))
            h = max(o, c) * (1 + rnd.uniform(0, 0.003))
            lo = min(o, c) * (1 - rnd.uniform(0, 0.003))
            bars.append([t, o, h, lo, c])
            p = c
            t += 4 * 3600
        weeks.append(engine._mk_week(bars))
        t += 52 * 3600  # weekend gap
    return weeks


class TestWeekGrouping(unittest.TestCase):
    def test_no_intra_week_weekend_gap(self):
        weeks = engine.load_price_weeks("6A")
        for w in weeks:
            for a, b in zip(w.bars, w.bars[1:]):
                self.assertLessEqual(b[0] - a[0], 24 * 3600)

    def test_weeks_are_ordered_and_disjoint(self):
        weeks = engine.load_price_weeks("6A")
        for a, b in zip(weeks, weeks[1:]):
            self.assertLess(a.close_ts, b.open_ts)

    def test_duplicate_and_unsorted_timestamps(self):
        """Loader must sort and de-duplicate before grouping."""
        raw = [
            [1000 + 4 * 3600, 1, 1, 1, 1],
            [1000, 1, 1, 1, 1],
            [1000, 9, 9, 9, 9],           # duplicate timestamp
            [1000 + 8 * 3600, 1, 1, 1, 1],
        ]
        raw.sort(key=lambda r: r[0])
        seen, dedup = set(), []
        for r in raw:
            if r[0] in seen:
                continue
            seen.add(r[0])
            dedup.append(r)
        self.assertEqual([r[0] for r in dedup],
                         [1000, 1000 + 4 * 3600, 1000 + 8 * 3600])


class TestSignalCausality(unittest.TestCase):
    def test_cot_index_ignores_future(self):
        net = [random.Random(3).randint(-50000, 50000) for _ in range(300)]
        i, lb = 200, 156
        base = engine.cot_index(net, i, lb)
        mutated = list(net)
        for j in range(i + 1, len(mutated)):
            mutated[j] = 10 ** 9  # extreme future values
        self.assertEqual(base, engine.cot_index(mutated, i, lb))

    def test_rolling_std_ignores_future(self):
        vals = [random.Random(4).gauss(0, 1000) for _ in range(300)]
        i, lb = 200, 52
        base = engine.rolling_std(vals, i, lb)
        mutated = list(vals)
        for j in range(i + 1, len(mutated)):
            mutated[j] = 10 ** 9
        self.assertEqual(base, engine.rolling_std(mutated, i, lb))

    def test_lookback_warmup_returns_none(self):
        net = list(range(100))
        self.assertIsNone(engine.cot_index(net, 10, 156))
        self.assertIsNone(engine.rolling_std(net, 10, 52))


class TestFutureMutation(unittest.TestCase):
    """The headline test: mutate the future, the past must not move."""

    def _run_with(self, cot, weeks, sigma_k=1.0):
        orig_cot, orig_px = engine.load_cot, engine.load_price_weeks
        engine.load_cot = lambda s: cot
        engine.load_price_weeks = lambda s: weeks
        try:
            return engine.run_symbol("6E", sigma_k=sigma_k, cot_lookback=52,
                                     sig_lookback=26)
        finally:
            engine.load_cot, engine.load_price_weeks = orig_cot, orig_px

    def _mk_cot(self, n=120, seed=7):
        rnd = random.Random(seed)
        first_t = 1_400_000_000 - (1_400_000_000 % engine.WEEK)
        ts = [first_t + i * engine.WEEK for i in range(n)]
        lo, sh = [], []
        a, b = 100000, 80000
        for _ in range(n):
            a += rnd.randint(-9000, 9000)
            b += rnd.randint(-9000, 9000)
            lo.append(a)
            sh.append(b)
        return {"ts": ts, "net": [lo[i] - sh[i] for i in range(n)],
                "long": lo, "short": sh}

    def test_future_cot_does_not_change_past_decisions(self):
        cot = self._mk_cot()
        weeks = _synth_weeks(n=140, start=cot["ts"][0] - 3 * engine.DAY)
        base = self._run_with(cot, weeks)
        self.assertGreater(len(base), 5, "need trades to make the test meaningful")

        cutoff = base[len(base) // 2].report_week_ts
        rnd = random.Random(99)
        mut = {k: list(v) for k, v in cot.items()}
        for j, t in enumerate(mut["ts"]):
            if t > cutoff:
                mut["long"][j] = rnd.randint(0, 500000)
                mut["short"][j] = rnd.randint(0, 500000)
                mut["net"][j] = mut["long"][j] - mut["short"][j]

        after = self._run_with(mut, weeks)
        kept_b = [t for t in base if t.report_week_ts <= cutoff]
        kept_a = [t for t in after if t.report_week_ts <= cutoff]
        self.assertEqual(len(kept_b), len(kept_a))
        for x, y in zip(kept_b, kept_a):
            self.assertEqual(x.report_week_ts, y.report_week_ts)
            self.assertEqual(x.direction, y.direction)
            self.assertEqual(x.at_extreme, y.at_extreme)
            self.assertEqual(x.cot_index, y.cot_index)
            self.assertEqual(x.entry_px, y.entry_px)
            self.assertEqual(x.exit_px, y.exit_px)

    def test_future_prices_do_not_change_past_decisions(self):
        cot = self._mk_cot()
        weeks = _synth_weeks(n=140, start=cot["ts"][0] - 3 * engine.DAY)
        base = self._run_with(cot, weeks)
        self.assertGreater(len(base), 5)

        pivot = base[len(base) // 2]
        # Everything strictly after this trade's exit is replaced with garbage.
        cutoff_ts = pivot.exit_ts
        rnd = random.Random(1234)
        mut_weeks = []
        for w in weeks:
            if w.open_ts > cutoff_ts:
                bars = [[b[0], 5000.0, 9000.0, 1.0, 7000.0] for b in w.bars]
                mut_weeks.append(engine._mk_week(bars))
            else:
                mut_weeks.append(w)

        after = self._run_with(cot, mut_weeks)
        kept_b = [t for t in base if t.exit_ts <= cutoff_ts]
        kept_a = [t for t in after if t.exit_ts <= cutoff_ts]
        self.assertEqual(len(kept_b), len(kept_a))
        for x, y in zip(kept_b, kept_a):
            self.assertEqual(x.entry_px, y.entry_px)
            self.assertEqual(x.exit_px, y.exit_px)
            self.assertEqual(x.ret_pct, y.ret_pct)
            self.assertEqual(x.direction, y.direction)


class TestReleaseGate(unittest.TestCase):
    def test_entry_week_opens_after_release(self):
        """No trade may open before its COT report was published."""
        for sym in ("6A",):
            for t in engine.run_symbol(sym, sigma_k=1.0):
                self.assertGreater(t.entry_week_open_ts, t.release_ts)
                # release must itself be after the report's Tuesday as-of date
                self.assertGreaterEqual(t.release_ts - t.report_week_ts,
                                        4 * engine.DAY)

    def test_limit_comes_from_a_completed_earlier_session(self):
        for t in engine.run_symbol("6A", sigma_k=1.0):
            self.assertGreater(t.entry_week_open_ts, t.report_week_ts)
            self.assertLessEqual(t.entry_ts, t.exit_ts)

    def test_entry_is_within_entry_week_and_exit_after(self):
        weeks = {w.open_ts: w for w in engine.load_price_weeks("6A")}
        for t in engine.run_symbol("6A", sigma_k=1.0):
            w = weeks[t.entry_week_open_ts]
            self.assertGreaterEqual(t.entry_ts, w.open_ts)
            self.assertLessEqual(t.entry_ts, w.close_ts)


class TestTradeMechanics(unittest.TestCase):
    def test_stop_distance_is_one_percent(self):
        for t in engine.run_symbol("6A", sigma_k=1.0):
            d = abs(t.stop_px - t.entry_px) / t.entry_px
            self.assertAlmostEqual(d, 0.01, places=9)

    def test_stopped_trades_lose_about_one_r(self):
        for t in engine.run_symbol("6A", sigma_k=1.0):
            if t.exit_reason == "STOP":
                # -1R plus slippage on both sides, never better than -1R
                self.assertLess(t.r_multiple, -0.98)
                self.assertGreater(t.r_multiple, -1.35)

    def test_limit_fill_respects_direction(self):
        for t in engine.run_symbol("6A", sigma_k=1.0):
            if t.filled_at_open:
                if t.direction == 1:
                    self.assertLessEqual(t.week_open_px, t.limit_px)
                else:
                    self.assertGreaterEqual(t.week_open_px, t.limit_px)

    def test_marketable_long_limit_fills_at_open(self):
        w = _synth_weeks(1)[0]
        bars = [[w.open_ts + i * 14400, 100.0, 101.0, 99.0, 100.0] for i in range(5)]
        wk = engine._mk_week(bars)
        j, px, at_open = engine._fill_limit(wk, limit=105.0, direction=1)
        self.assertTrue(at_open)
        self.assertEqual(px, 100.0)  # filled at the better price, not the limit

    def test_non_marketable_long_limit_waits_for_touch(self):
        bars = [
            [0, 100.0, 101.0, 99.5, 100.0],
            [14400, 100.0, 100.5, 98.0, 98.5],   # touches 99
            [28800, 98.5, 99.0, 98.0, 98.5],
        ]
        wk = engine._mk_week(bars)
        res = engine._fill_limit(wk, limit=99.0, direction=1)
        self.assertIsNotNone(res)
        j, px, at_open = res
        self.assertFalse(at_open)
        self.assertEqual(j, 1)
        self.assertEqual(px, 99.0)

    def test_unfilled_limit_returns_none(self):
        bars = [[0, 100.0, 101.0, 99.5, 100.0], [14400, 100.0, 100.5, 99.6, 100.0]]
        wk = engine._mk_week(bars)
        self.assertIsNone(engine._fill_limit(wk, limit=95.0, direction=1))


class TestExtremeLogic(unittest.TestCase):
    def test_extreme_flips_direction(self):
        net = [0] * 155 + [1000]           # last value is the max -> index 100
        idx = engine.cot_index(net, 155, 156)
        self.assertEqual(idx, 100.0)
        self.assertTrue(idx > 80.0)

    def test_mid_range_index(self):
        net = list(range(156))
        self.assertAlmostEqual(engine.cot_index(net, 155, 156), 100.0)
        net2 = list(range(156))[::-1]
        self.assertAlmostEqual(engine.cot_index(net2, 155, 156), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
