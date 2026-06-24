"""Per-maturity risk-free curve. Pulls US Treasury par yields from FRED (keyless CSV),
log-linear interpolates by maturity in years. Falls back to a static recent curve so
the pipeline never breaks offline. rate_for(T) returns a continuously-compounded rate."""
import math
_FRED={"DGS1MO":1/12,"DGS3MO":0.25,"DGS6MO":0.5,"DGS1":1,"DGS2":2,"DGS3":3,"DGS5":5,"DGS7":7,"DGS10":10,"DGS20":20,"DGS30":30}
_FALLBACK=[(1/12,0.0445),(0.25,0.0440),(0.5,0.0430),(1,0.0410),(2,0.0395),(3,0.0390),(5,0.0395),(7,0.0405),(10,0.0420)]

def fetch_curve(sess=None):
    pts=[]
    try:
        import requests
        s=sess or requests.Session()
        for sid,yrs in _FRED.items():
            try:
                u=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
                txt=s.get(u,timeout=12).text.strip().splitlines()
                last=[r for r in txt[1:] if r.split(",")[-1] not in ("",".")][-1]
                y=float(last.split(",")[-1])/100.0
                pts.append((yrs,y))
            except Exception: continue
    except Exception: pass
    pts=sorted(pts) if len(pts)>=4 else list(_FALLBACK)
    return pts

class Curve:
    def __init__(self, pts=None): self.pts=sorted(pts or _FALLBACK)
    def rate_for(self, T):
        p=self.pts
        if T<=p[0][0]: y=p[0][1]
        elif T>=p[-1][0]: y=p[-1][1]
        else:
            for (t0,y0),(t1,y1) in zip(p,p[1:]):
                if t0<=T<=t1:
                    w=(T-t0)/(t1-t0); y=y0+w*(y1-y0); break
        return math.log(1+y)   # par-yield -> continuously compounded (approx)

def default_curve(): return Curve(_FALLBACK)
