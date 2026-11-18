import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from app.analytics import pressure, reliability as R
from app.analytics.config import PressureConfig


class Shrinkage(unittest.TestCase):
    def test_pure_noise_is_fully_shrunk(self):
        rng = np.random.default_rng(1)
        se2 = np.full(300, 1.0)
        x = rng.normal(0, 1, 300)                      # no true variation
        r = R.eb_shrink(x, se2)
        self.assertLess(r["tau2"], 0.15)
        self.assertLess(np.abs(r["post"] - r["mu"]).max(), 0.6)

    def test_recovers_true_signal_and_shrinks_small_samples_more(self):
        rng = np.random.default_rng(2)
        theta = rng.normal(0, 1, 2000)
        n = rng.choice([10, 400], 2000)
        se2 = 4.0 / n
        x = theta + rng.normal(0, np.sqrt(se2))
        r = R.eb_shrink(x, se2)
        self.assertAlmostEqual(r["tau2"], 1.0, delta=0.15)
        self.assertLess(r["B"][n == 10].mean(), r["B"][n == 400].mean())           # small n -> more shrinkage
        mse_raw, mse_post = ((x - theta) ** 2).mean(), ((r["post"] - theta) ** 2).mean()
        self.assertLess(mse_post, mse_raw)                                          # EB is better than raw

    def test_small_sample_cannot_outrank_large_sample_with_same_raw_mean(self):
        r = R.eb_shrink(np.array([1.0, 1.0, 0, 0, 0, 0.5, -0.5, 0.2, -0.2]), np.array([4.0, 0.01] + [0.5] * 7))
        self.assertLess(r["post"][0], r["post"][1])

    def test_zero_tau_component_gets_zero_weight(self):
        c = {"level": np.array([1.0, 2.0]), "delta": np.array([5.0, -5.0]), "cons": np.array([.5, .6]),
             "mu": {"level": 0, "delta": 0, "cons": .5}, "tau": {"level": 1.0, "delta": 0.0, "cons": 0.1}}
        sc, z = R.composite(c, np.array([True, True]), {"level": 1, "delta": 1, "consistency": 1})
        self.assertTrue(np.all(z["delta"] == 0))

    def test_rank_ignores_ineligible(self):
        rk = R.rank_desc(np.array([5.0, 9.0, 7.0]), np.array([True, False, True]))
        self.assertEqual(list(rk[[0, 2]]), [2, 1]); self.assertTrue(np.isnan(rk[1]))


class PressureCategories(unittest.TestCase):
    def test_quantile_categories_within_innings(self):
        rng = np.random.default_rng(3)
        s = pd.DataFrame({"LI": np.r_[rng.random(1000) * 0.5, rng.random(1000) * 5], "innings": [1] * 1000 + [2] * 1000})
        out, info = pressure.assign(s, PressureConfig())
        for inn in (1, 2):
            sh = (out[out.innings == inn].pressure_cat.value_counts(normalize=True)).round(2)
            self.assertAlmostEqual(sh["Critical"], 0.05, delta=0.01); self.assertAlmostEqual(sh["High"], 0.15, delta=0.01)
        self.assertTrue(out.is_pressure.equals(out.pressure_cat.isin(["High", "Critical"])))


if __name__ == "__main__":
    unittest.main()
