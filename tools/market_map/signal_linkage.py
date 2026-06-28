"""Honest signal validation: does an option-derived feature actually predict forward
returns? Computes the information coefficient (rank correlation) per feature, a t-stat,
and applies Benjamini-Hochberg FDR across features so we don't fool ourselves with
multiple testing. Until real outcomes accrue in bs_record, weights stay 'uncalibrated'."""
import math

def _rank(x):
    order=sorted(range(len(x)),key=lambda i:x[i]); r=[0]*len(x)
    i=0
    while i<len(x):
        j=i
        while j+1<len(x) and x[order[j+1]]==x[order[i]]: j+=1
        avg=(i+j)/2.0
        for k in range(i,j+1): r[order[k]]=avg
        i=j+1
    return r

def pearson(a,b):
    n=len(a); ma=sum(a)/n; mb=sum(b)/n
    cov=sum((a[i]-ma)*(b[i]-mb) for i in range(n))
    va=sum((x-ma)**2 for x in a); vb=sum((y-mb)**2 for y in b)
    return cov/math.sqrt(va*vb) if va>0 and vb>0 else 0.0

from metrics import spearman   # canonical tie-averaged rank-corr (numerically identical: Pearson is
#                                invariant to the 0- vs 1-based rank offset). Single source of truth.

def _norm_sf(z): return 0.5*math.erfc(z/math.sqrt(2))

def ic_report(feature_cols, y, names=None, alpha=0.10):
    """feature_cols: list of equal-length feature arrays; y: forward returns.
    Returns per-feature {ic, t, p, hit, fdr_significant} with BH-FDR at alpha."""
    n=len(y); names=names or [f"f{i}" for i in range(len(feature_cols))]
    rows=[]
    for nm,col in zip(names,feature_cols):
        ic=spearman(col,y)
        t=ic*math.sqrt(max(n-2,1)/max(1-ic*ic,1e-9))
        p=2*_norm_sf(abs(t))
        med=sorted(col)[len(col)//2]
        hi=[y[i] for i in range(n) if col[i]>med]; lo=[y[i] for i in range(n) if col[i]<=med]
        hit=(sum(1 for v in hi if v>0)/len(hi)) if hi else None
        rows.append({"name":nm,"ic":round(ic,4),"t":round(t,3),"p":p,
                     "hiMeanRet":round(sum(hi)/len(hi),5) if hi else None,
                     "loMeanRet":round(sum(lo)/len(lo),5) if lo else None,"hitRate":round(hit,3) if hit else None})
    # Benjamini-Hochberg
    m=len(rows); order=sorted(range(m),key=lambda i:rows[i]["p"])
    thresh=0.0
    for rank,i in enumerate(order,1):
        if rows[i]["p"]<=alpha*rank/m: thresh=alpha*rank/m
    for r in rows: r["fdrSignificant"]=(r["p"]<=thresh); r["p"]=round(r["p"],5)
    rows.sort(key=lambda r:r["p"])
    return rows

def validate_from_history(rows, feature_keys, alpha=0.10):
    """Pair bs_record snapshots (with .summary[feature]) to later outcome.fwdRet."""
    snaps=[r for r in rows if r.get("kind")=="snapshot" and r.get("summary")]
    outs=[r for r in rows if r.get("kind")=="outcome"]
    X={k:[] for k in feature_keys}; Y=[]
    for o in outs:
        prior=[s for s in snaps if s["ticker"]==o["ticker"] and s["ts"]<=o.get("refTs",o["ts"])]
        if not prior: continue
        s=max(prior,key=lambda r:r["ts"]); fr=o["outcome"].get("fwdRet") if isinstance(o["outcome"],dict) else None
        if fr is None: continue
        vals={k:s["summary"].get(k) for k in feature_keys}
        if any(v is None for v in vals.values()): continue
        for k in feature_keys: X[k].append(float(vals[k]))
        Y.append(float(fr))
    if len(Y)<20: return {"pairs":len(Y),"note":"need >=20 outcomes to validate"}
    return {"pairs":len(Y),"report":ic_report([X[k] for k in feature_keys],Y,feature_keys,alpha)}
