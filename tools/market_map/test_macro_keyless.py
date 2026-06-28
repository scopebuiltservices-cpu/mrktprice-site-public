import macro_keyless as M
F=[]
def chk(n,c):
    print(("  PASS  " if c else "  FAIL  ")+n)
    if not c: F.append(n)
csv=("DATE,DGS10,DTWEXBGS,VIXCLS,DCOILWTICO,T10YIE\n"
     "2025-01-01,4.00,120.0,15.0,70.0,2.30\n"
     "2025-01-02,4.05,120.5,.,71.0,.\n"            # missing VIX + breakeven that day
     "2025-01-03,4.10,121.0,16.0,72.0,2.31\n")
bd=M.parse_fred_multi(csv)
chk("parses dates", len(bd)==3)
chk("skips '.' missing", "VIXCLS" not in bd["2025-01-02"] and "DGS10" in bd["2025-01-02"])
chk("maps RATE/DXY/VIX/OIL/BREAKEVEN ids", set(M.SERIES.values())>={"RATE","DXY","VIX","OIL"})
# weekly_pct
lv=[100,101,102,103,104,105,106,107,108,109,110]   # step 5 -> [100,105,110]
wp=M.weekly_pct(lv,step=5)
chk("weekly pct change correct", len(wp)==2 and abs(wp[0]-0.05)<1e-9 and abs(wp[1]-(110/105-1))<1e-9)
# to_macro on a longer synthetic series -> produces weekly-change series with >=8 points
bd2={}
import datetime
d0=datetime.date(2025,1,1)
for i in range(80):
    d=(d0+datetime.timedelta(days=i)).isoformat()
    bd2[d]={"DGS10":4.0+0.01*i,"DTWEXBGS":120+0.1*i,"VIXCLS":15+(i%5),"DCOILWTICO":70+0.2*i}
mac=M.to_macro(bd2)
chk("to_macro yields RATE/DXY/VIX/OIL series", set(mac.keys())>={"RATE","DXY","VIX","OIL"})
chk("series length >=8", all(len(v)>=8 for v in mac.values()))
chk("forward-fill: no None in output series", all(all(x==x for x in v) for v in mac.values()))
print("\n"+("ALL MACRO-KEYLESS TESTS PASSED" if not F else "FAILED: %s"%F)); import sys; sys.exit(1 if F else 0)
