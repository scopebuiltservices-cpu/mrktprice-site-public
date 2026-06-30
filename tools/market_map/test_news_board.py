#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import news_board as NB
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else "  -> "+str(d)))
    if not c: F.append(n)
mm={"asof":"2026-06-28","names":[
  {"t":"AAA","sec":"Technology","mcap":1000},
  {"t":"BBB","sec":"Technology","mcap":10},
  {"t":"CCC","sec":"Energy","mcap":500}]}
news={"AAA":[{"title":"AAA beats and raises, surges to record","date":"2026-06-28"}],
      "BBB":[{"title":"BBB misses, cuts guidance, faces lawsuit","date":"2026-06-28"}],
      "CCC":[{"title":"CCC wins major contract, upgraded","date":"2026-06-28"}]}
done=NB.enrich(mm,news)
ok("scored all 3",done==3,done)
ok("AAA tailwind",mm["names"][0]["news"]["label"]=="tailwind",mm["names"][0]["news"])
ok("BBB headwind",mm["names"][1]["news"]["label"]=="headwind")
ok("market tone present",mm["newsTone"]["market"]["n"]==3)
ok("tech sector cap-weighted positive (AAA dominates)",mm["newsTone"]["sectors"]["Technology"]["net"]>0,mm["newsTone"]["sectors"]["Technology"])
ok("energy sector tailwind",mm["newsTone"]["sectors"]["Energy"]["label"]=="tailwind")
print("\n"+("ALL NEWS-BOARD TESTS PASSED" if not F else "%d FAILED: %s"%(len(F),F)))
raise SystemExit(1 if F else 0)
