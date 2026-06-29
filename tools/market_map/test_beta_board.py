"""Planted test for beta_board.py (leave-one-out EW market + Vasicek-adjusted beta)."""
import random
import beta_board as BB

def test_vasicek_shrinks_noisy_toward_mean():
    random.seed(5)
    T = 120
    mkt = [random.gauss(0, 0.02) for _ in range(T)]
    names = []
    for i, beta in enumerate([0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4]):          # clean, dispersed
        names.append({"t": "N%d" % i, "beta": beta, "wr": [beta * mkt[k] + random.gauss(0, 0.002) for k in range(T)]})
    names.append({"t": "WILD", "beta": 2.4, "wr": [2.4 * mkt[k] + random.gauss(0, 0.08) for k in range(T)]})  # noisy extreme
    mm = {"names": names}
    done = BB.enrich(mm)
    assert done == 9
    by = {n["t"]: n for n in names}
    # betaRaw = recomputed OLS; adjusted shrinks the noisy extreme toward the mean (adj < its own raw)
    assert by["WILD"]["beta"] < by["WILD"]["betaRaw"]
    # the noisy extreme shrinks MORE than a precise clean high-beta name
    assert (by["WILD"]["betaRaw"] - by["WILD"]["beta"]) > (by["N7"]["betaRaw"] - by["N7"]["beta"])
    # clean ordering preserved
    cb = [by["N%d" % i]["beta"] for i in range(8)]
    assert cb == sorted(cb)

def test_too_few_names_noop():
    assert BB.enrich({"names": [{"t": "A", "beta": 1.0, "wr": [0.01] * 40}]}) == 0

if __name__ == "__main__":
    test_vasicek_shrinks_noisy_toward_mean(); test_too_few_names_noop()
    print("test_beta_board: 2/2 PASS")
