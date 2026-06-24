"""Volatility estimators from OHLC bars (more efficient + jump-robust than close-to-close)
and a Corsi HAR-RV realized-variance forecaster. Annualized with `ann` trading days."""
import math

def _logs(a): return [math.log(x) for x in a]

def close_to_close(closes, ann=252):
    c=[float(x) for x in closes if x and float(x)>0]
    if len(c)<3: return None
    r=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]; n=len(r); m=sum(r)/n
    return math.sqrt(sum((x-m)**2 for x in r)/(n-1)*ann)

def parkinson(highs,lows,ann=252):
    h,l=[float(x) for x in highs],[float(x) for x in lows]
    if len(h)<2 or len(h)!=len(l): return None
    s=sum((math.log(hi/lo))**2 for hi,lo in zip(h,l) if hi>0 and lo>0)
    return math.sqrt(s/(4*math.log(2)*len(h))*ann)

def garman_klass(o,h,l,c,ann=252):
    o,h,l,c=[list(map(float,x)) for x in (o,h,l,c)]
    n=len(o)
    if n<2: return None
    s=sum(0.5*(math.log(h[i]/l[i]))**2-(2*math.log(2)-1)*(math.log(c[i]/o[i]))**2 for i in range(n))
    return math.sqrt(s/n*ann)

def rogers_satchell(o,h,l,c,ann=252):
    o,h,l,c=[list(map(float,x)) for x in (o,h,l,c)]; n=len(o)
    if n<2: return None
    s=sum(math.log(h[i]/c[i])*math.log(h[i]/o[i])+math.log(l[i]/c[i])*math.log(l[i]/o[i]) for i in range(n))
    return math.sqrt(s/n*ann)

def yang_zhang(o,h,l,c,ann=252):
    """Drift-independent, minimum-variance OHLC estimator (Yang-Zhang 2000)."""
    o,h,l,c=[list(map(float,x)) for x in (o,h,l,c)]; n=len(o)
    if n<3: return None
    oc=[math.log(o[i]/c[i-1]) for i in range(1,n)]      # overnight
    co=[math.log(c[i]/o[i]) for i in range(1,n)]        # open->close
    mo=sum(oc)/len(oc); mc=sum(co)/len(co)
    Vo=sum((x-mo)**2 for x in oc)/(len(oc)-1)
    Vc=sum((x-mc)**2 for x in co)/(len(co)-1)
    rs=sum(math.log(h[i]/c[i])*math.log(h[i]/o[i])+math.log(l[i]/c[i])*math.log(l[i]/o[i]) for i in range(1,n))/(n-1)
    k=0.34/(1.34+(n+1)/(n-1))
    return math.sqrt((Vo+k*Vc+(1-k)*rs)*ann)

def bipower_var(closes, ann=252):
    """Jump-robust realized variance (bipower variation, Barndorff-Nielsen-Shephard)."""
    c=[float(x) for x in closes if x and float(x)>0]
    if len(c)<3: return None
    r=[abs(math.log(c[i]/c[i-1])) for i in range(1,len(c))]
    mu1=math.sqrt(2/math.pi)
    bv=(1/mu1**2)*sum(r[i]*r[i-1] for i in range(1,len(r)))
    return bv*ann

def har_rv(rv_series):
    """Corsi (2009) HAR-RV: forecast next RV from daily/weekly/monthly averages.
    rv_series: list of daily realized variances (oldest..newest). Returns
    {coef, forecast} fit by OLS (closed form normal equations, stdlib)."""
    rv=[float(x) for x in rv_series if x is not None and float(x)>0]
    if len(rv)<30: return None
    def avg(a): return sum(a)/len(a)
    X,Y=[],[]
    for t in range(22,len(rv)-1):
        d=rv[t]; w=avg(rv[t-4:t+1]); m=avg(rv[t-21:t+1])
        X.append([1.0,d,w,m]); Y.append(rv[t+1])
    # OLS via normal equations (4x4)
    import itertools
    n,k=len(X),4
    XtX=[[sum(X[i][a]*X[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    XtY=[sum(X[i][a]*Y[i] for i in range(n)) for a in range(k)]
    # gaussian elimination
    M=[row[:]+[XtY[a]] for a,row in enumerate(XtX)]
    for col in range(k):
        piv=max(range(col,k),key=lambda r:abs(M[r][col]))
        M[col],M[piv]=M[piv],M[col]
        if abs(M[col][col])<1e-12: return None
        pivv=M[col][col]; M[col]=[v/pivv for v in M[col]]
        for r in range(k):
            if r!=col and abs(M[r][col])>0:
                f=M[r][col]; M[r]=[M[r][j]-f*M[col][j] for j in range(k+1)]
    beta=[M[i][k] for i in range(k)]
    d=rv[-1]; w=avg(rv[-5:]); m=avg(rv[-22:])
    fc=beta[0]+beta[1]*d+beta[2]*w+beta[3]*m
    return {"coef":{"const":beta[0],"daily":beta[1],"weekly":beta[2],"monthly":beta[3]},
            "forecastVar":max(fc,0.0),"forecastVol":math.sqrt(max(fc,0.0))}
