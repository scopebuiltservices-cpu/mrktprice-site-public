"""Run the full option-analysis stack for one ticker and emit a compact summary plus a
PROVISIONAL composite signal (weights uncalibrated until signal_linkage validates them)."""
import math
import black_scholes as bs, bs_ext as be, american as am, realized as rl
import chain_quality as cq, parity as par, risk_neutral as rn, vol_surface as vs

def analyze(ticker, spot, closes, chain, days, r=0.04, q=0.0, record=True):
    if not chain or not spot or spot<=0: return None
    T=max(days,1)/365.0
    clean=cq.liquidity_filter(chain)
    if len(clean)<4: clean=chain
    arb=cq.no_arb_violations(clean,spot,T,r,q)
    # parity: implied forward + dividend (overrides q when available)
    pf=par.implied_forward(clean,spot,T,r)
    if pf and pf.get("impliedDivYield") is not None and -0.05<pf["impliedDivYield"]<0.20:
        q=pf["impliedDivYield"]
    # realized + HAR-RV forecast from closes
    rv_cc=rl.close_to_close(closes) if closes else None
    rets=[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))] if (closes and len(closes)>2) else []
    rvs=[x*x for x in rets]
    har=rl.har_rv(rvs) if len(rvs)>=30 else None
    fvar=har["forecastVar"]*252 if har else ((rv_cc**2) if rv_cc else None)   # annualized fwd variance
    refv=rv_cc
    # BS richness/greeks vs realized
    val=bs.value_chain(clean,spot,days,r=r,q=q,ref_vol=refv)
    # model-free implied var + VRP
    mf=rn.model_free_iv(clean,spot,T,r,forward=(pf["forward"] if pf else None))
    vrp=rn.variance_risk_premium(clean,spot,T,r,fvar) if (mf and fvar) else None
    bkm=rn.bkm_moments(clean,spot,T,r)
    # SVI slice from per-strike mid IV
    svi_feat=None
    try:
        ivk={}
        for c in (val["contracts"] if val else []):
            if c.get("iv"):
                k=math.log(c["strike"]/(pf["forward"] if pf else spot)); ivk.setdefault(round(k,4),[]).append(c["iv"])
        ks=sorted(ivk); ws=[ (sum(ivk[k])/len(ivk[k]))**2*T for k in ks]
        if len(ks)>=5:
            cal=vs.calibrate_svi(ks,ws)
            if cal: svi_feat=vs.slice_features(cal[0],T)
    except Exception: pass
    # American value + early-exercise premium at ATM
    Katm=min((float(o["strike"]) for o in clean), key=lambda K:abs(K-spot))
    am_val={"strike":Katm,
            "amCall":round(am.crr_price(spot,Katm,T,r,refv or 0.3,q,"C",300),4),
            "amPut":round(am.crr_price(spot,Katm,T,r,refv or 0.3,q,"P",300),4),
            "eepPutPct":None}
    eep=am.early_exercise_premium(spot,Katm,T,r,refv or 0.3,q,"P",300); bsp=bs.bs_price(spot,Katm,T,r,refv or 0.3,q,"P")
    am_val["eepPutPct"]=round(100*eep/bsp,2) if bsp>1e-6 else None
    # ---- PROVISIONAL composite (uncalibrated) ----
    feats={"vrpVolPts":(vrp["vrpVolPts"] if vrp else None),
           "rnSkew":(bkm["rnSkew"] if bkm else None),
           "atmSkew":(svi_feat["atmSkew"] if svi_feat else None),
           "avgRichnessPct":(val["summary"]["avgRichnessPct"] if val else None),
           "gexRegime":(1 if False else None)}
    def _z(v,s): return max(-1,min(1,v/s)) if v is not None else 0
    tilt=( -0.30*_z(feats["rnSkew"],1.0)          # steep negative RN skew -> crash risk -> caution
           +0.25*_z(feats["vrpVolPts"],8.0)        # high vol premium -> fear (often contrarian +)
           -0.20*_z(feats["avgRichnessPct"],10.0)) # paying up for options -> slight caution
    summary={"ticker":ticker,"spot":round(spot,4),"days":days,"r":round(r,4),"q":round(q,4),
             "forward":(pf["forward"] if pf else None),"impliedDivYield":(pf.get("impliedDivYield") if pf else None),
             "hardToBorrow":(pf.get("hardToBorrow") if pf else None),
             "noArbViolations":len(arb),"nContracts":(val["summary"]["n"] if val else 0),
             "refVolPct":round((refv or 0)*100,1) if refv else None,
             "atmIVpct":(val["summary"]["atmIVpct"] if val else None),
             "expMovePct":(val["summary"]["expMovePct"] if val else None),
             "avgRichnessPct":(val["summary"]["avgRichnessPct"] if val else None),
             "mfImpliedVolPct":round(mf["mfImpliedVol"]*100,2) if (mf and mf["mfImpliedVol"]) else None,
             "vrpVolPts":(vrp["vrpVolPts"] if vrp else None),
             "rnSkew":(bkm["rnSkew"] if bkm else None),"rnKurt":(bkm["rnKurt"] if bkm else None),
             "sviAtmVol":(svi_feat["atmVol"] if svi_feat else None),
             "sviAtmSkew":(svi_feat["atmSkew"] if svi_feat else None),
             "sviButterflyArbFree":(svi_feat["butterflyArbFree"] if svi_feat else None),
             "american":am_val,
             "optTilt":round(tilt,3),"optTiltStatus":"provisional/uncalibrated"}
    if record:
        try:
            import bs_record as rec; rec.record(ticker, summary, (val["contracts"] if val else None))
        except Exception: pass
    return summary
