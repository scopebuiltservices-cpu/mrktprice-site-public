"""Planted test: synth marketmap + hist where each name's returns = known betas . factors + idio, synth
FF cache. enrich() must recover betas into n.fac.b and set expPct sign per the factor premia."""
import sys, os, json, math, random, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import residualize_board as RB
import factor_returns as FR
import residualize_engine as RE

def _build(tmp, betas, T=400, drift_factor=0.001):
    rng = random.Random(5)
    os.makedirs(os.path.join(tmp, "hist"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
    # factor rows with a POSITIVE mean on MktRF (so expPct>0 for positive market beta)
    rows = []
    base = 20240101
    dates = []
    y, m, d = 2024, 1, 1
    import datetime as dt
    cur = dt.date(2024, 1, 2)
    for i in range(T):
        rows.append({"date": int(cur.strftime("%Y%m%d")),
                     "MktRF": rng.gauss(drift_factor, 0.01), "SMB": rng.gauss(0, 0.006),
                     "HML": rng.gauss(0, 0.006), "RMW": rng.gauss(0, 0.005),
                     "CMA": rng.gauss(0, 0.005), "Mom": rng.gauss(0, 0.007), "RF": 0.0001})
        cur += dt.timedelta(days=1)
    FR._write_cache(rows, os.path.join(tmp, "data", "ff_factors.csv"))
    # hist closes consistent with returns = betas.factors + idio + RF
    price = 100.0
    hrows = []
    for r in rows:
        ex = sum(betas[f] * r[f] for f in RE.FACTORS) + rng.gauss(0, 0.003)
        ret = ex + r["RF"]
        price *= math.exp(ret)
        ds = "%04d-%02d-%02d" % (int(str(r["date"])[:4]), int(str(r["date"])[4:6]), int(str(r["date"])[6:8]))
        hrows.append([ds, round(price, 4), 1000000])
    json.dump({"ticker": "TST", "rows": hrows}, open(os.path.join(tmp, "hist", "TST.json"), "w"))
    mm = {"names": [{"t": "TST", "ret": {}}]}
    json.dump(mm, open(os.path.join(tmp, "marketmap.json"), "w"))
    return mm

def test_recovers_and_writes_fac():
    tmp = tempfile.mkdtemp()
    betas = {"MktRF": 1.20, "SMB": 0.50, "HML": -0.40, "RMW": 0.10, "CMA": 0.0, "Mom": 0.30}
    mm = _build(tmp, betas)
    factor_rows = FR.load_factor_csv(os.path.join(tmp, "data", "ff_factors.csv"))
    done = RB.enrich(mm, os.path.join(tmp, "hist"), factor_rows, horizon=21)
    assert done == 1, done
    fac = mm["names"][0]["fac"]
    for f in RE.FACTORS:
        assert abs(fac["b"][f] - betas[f]) < 0.06, (f, fac["b"][f], betas[f])
    assert fac["r2"] > 0.7, fac["r2"]
    # MktRF beta>0 and positive market premium -> factor-explained return expPct > 0
    assert fac["expPct"] > 0, fac["expPct"]
    print("  PASS  enrich recovers betas (max err<0.06, R2=%.3f), expPct=%.3f%% (>0)" % (fac["r2"], fac["expPct"]))

def test_missing_hist_skipped():
    tmp = tempfile.mkdtemp()
    _build(tmp, {f: 0.0 for f in RE.FACTORS})
    factor_rows = FR.load_factor_csv(os.path.join(tmp, "data", "ff_factors.csv"))
    mm = {"names": [{"t": "NOHIST"}, {"t": "TST"}]}
    done = RB.enrich(mm, os.path.join(tmp, "hist"), factor_rows, 21)
    assert done == 1 and "fac" not in mm["names"][0] and "fac" in mm["names"][1]
    print("  PASS  names without hist are skipped (no fac block)")

if __name__ == "__main__":
    test_recovers_and_writes_fac(); test_missing_hist_skipped()
    print("\nALL RESIDUALIZE_BOARD TESTS PASSED")
