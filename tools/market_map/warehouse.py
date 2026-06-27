#!/usr/bin/env python3
"""Normalized warehouse layer for the quarterly-timeline spec (pp.9-13, 21).

Builds the spec's basis-flagged price table (raw / split-adjusted / total-return kept SEPARATELY, never
overwriting each other), a deterministic file-naming convention, and a run manifest (source, versions,
hashes, basis flags, as-of). Persists to partitioned PARQUET when an engine (pyarrow/fastparquet) is
available; otherwise CSV (the spec lists CSV+parquet as acceptable for data extracts). Pure pandas +
stdlib; reuses the verified quarterly_timeline total-return math.

Spec discipline encoded:
 - never overwrite one price basis with another (raw / split-adj / total-return are distinct columns),
 - never forward-fill traded prices across non-trading days (caller passes only trading-day rows),
 - every artifact carries an explicit basis flag + a manifest hash so charts are auditable.
"""
import os, json, hashlib, datetime
import pandas as pd
try:
    import quarterly_timeline as _qt
except Exception:
    _qt = None

BASIS = {
    "raw_close":        {"splits": False, "dividends": False, "use": "exact tape price / trade reconstruction"},
    "split_adj_close":  {"splits": True,  "dividends": False, "use": "technical history without false split jumps"},
    "total_return":     {"splits": True,  "dividends": True,  "use": "investment-performance comparison (DEFAULT)"},
}

def _tr_index(close, divs=None, base=100.0):
    if _qt is not None:
        return _qt.total_return_index(close, divs, base)
    divs = divs or {}; tr = [base]
    for t in range(1, len(close)):
        d = divs.get(t, 0.0); r = (close[t] - close[t-1] + d) / close[t-1] if close[t-1] else 0.0
        tr.append(tr[-1] * (1 + r))
    return tr

def normalize_prices(ticker, dates, raw_close, split_adj_close=None, divs=None, exchange="NASDAQ"):
    """Return a DataFrame with the three distinct bases as separate columns (never overwritten), each
    flagged in BASIS. `divs` maps row-index -> cash dividend on ex-date. Caller supplies trading-day rows
    only (no forward-fill across holidays)."""
    n = len(raw_close)
    sac = split_adj_close if split_adj_close is not None else list(raw_close)
    tr = _tr_index(sac, divs)
    df = pd.DataFrame({
        "ticker": [ticker.upper()] * n, "exchange": [exchange] * n, "date": list(dates),
        "raw_close": list(raw_close), "split_adj_close": list(sac), "total_return": tr,
    })
    df.attrs["basis_flags"] = BASIS
    return df

def deterministic_name(ticker, exchange, start, end, asof, artifact, ext):
    return "%s_%s_%s_%s_%s_%s.%s" % (ticker.upper(), exchange, start, end, asof, artifact, ext)

def _hash_df(df):
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:16]

def write_table(df, outdir, ticker, exchange, start, end, asof, artifact, partition_cols=None):
    """Parquet (zstd) if an engine is available, else CSV. Returns {path, format, rows, sha16}."""
    os.makedirs(outdir, exist_ok=True)
    engine = None
    for eng in ("pyarrow", "fastparquet"):
        try:
            __import__(eng); engine = eng; break
        except Exception:
            continue
    sha = _hash_df(df)
    if engine:
        path = os.path.join(outdir, deterministic_name(ticker, exchange, start, end, asof, artifact, "parquet"))
        df.to_parquet(path, engine=engine, compression="zstd", index=False, partition_cols=partition_cols)
        fmt = "parquet:" + engine
    else:
        path = os.path.join(outdir, deterministic_name(ticker, exchange, start, end, asof, artifact, "csv"))
        df.to_csv(path, index=False)
        fmt = "csv"
    return {"path": path, "format": fmt, "rows": len(df), "sha16": sha}

def read_table(path):
    return pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)

def manifest(config, tables, asof=None, source="", code_version=""):
    """Audit manifest: run config, per-table format+hash, basis flags, as-of timestamp."""
    return {
        "asof": asof or datetime.date.today().isoformat(),
        "source": source, "code_version": code_version,
        "config": config, "basis_flags": BASIS, "default_basis": "total_return",
        "tables": tables,
        "generated_utc": datetime.datetime.utcnow().isoformat() + "Z",
    }

def write_manifest(man, outdir, ticker, exchange, start, end, asof):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, deterministic_name(ticker, exchange, start, end, asof, "manifest", "json"))
    open(path, "w").write(json.dumps(man, indent=1))
    return path
