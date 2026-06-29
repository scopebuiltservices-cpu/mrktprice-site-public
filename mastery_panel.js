/* mastery_panel.js — per-name SIGNAL-MASTERY tier badge on the Bull/Bear board. EXTERNAL module (same
   pattern as factor_neutral.js / event_panel.js): reads each row's data-* + window.MMAP, maps them to the
   mastery rubric components, classifies via window.MrktMastery, and injects a NOV/PROF/MAST badge. The
   must-pass `dsr` critical = the multiplicity-DEFLATED conviction (z − √(2 ln N_eff)), so a signal can only
   reach MASTERY (deployable) if it survives the overfit/breadth correction — the DSR/PBO hard gate, per row.
   Client view; the full server-side gate (real PBO/coverage/PIT) is the deeper version. Research only. */
(function () {
  'use strict';
  var BADGE = 'bbmast';
  function num(s){var v=parseFloat(s);return v===v?v:null;}
  function clamp01(x){return Math.max(0,Math.min(1,x));}
  function nmeFor(tk){try{var m=window.MMAP&&window.MMAP.names;if(!m||!tk)return null;tk=tk.toUpperCase();
    for(var i=0;i<m.length;i++)if((m[i].t||'').toUpperCase()===tk)return m[i];}catch(e){}return null;}

  function tierFor(r, nRows){
    if(!window.MrktMastery)return null;
    var tk=r.getAttribute('data-tk'); var n=nmeFor(tk)||{};
    var z=Math.abs(num(r.getAttribute('data-z'))||0);
    var net=num(r.getAttribute('data-net')), adj=num(r.getAttribute('data-adj')), tot=num(r.getAttribute('data-tot'))||0;
    var facN=(n.fac&&n.fac.n!=null)?n.fac.n:null;
    var evInt=(n.ev&&n.ev.intensity!=null)?n.ev.intensity:0;
    // multiplicity-deflated conviction: z minus the breadth penalty √(2 ln N_eff). N_eff = √#rows
    // (effective INDEPENDENT bets — names are cross-sectionally correlated, so raw N over-penalizes).
    var Neff=Math.max(2,Math.sqrt(nRows||30));
    var defl=z-Math.sqrt(2*Math.log(Neff));
    var comps={
      procedure: clamp01(z/3),                                  // OOS-style conviction strength
      concepts:  facN!=null?clamp01(facN/250):0.55,             // data sufficiency (FF regression n)
      reasoning: 0.7,                                           // calibration proxy (full coverage is server-side)
      transfer:  clamp01((defl)/2.0+0.5),                       // survives the multiplicity/breadth correction
      selfmon:   clamp01(1-evInt/3)                             // recent event intensity -> less stable
    };
    var edge=(net!=null)?net:(adj!=null?adj:tot);
    var criticals={
      dsr:  clamp01(defl/1.5+0.5),                              // DSR/PBO gate: deflated conviction must clear floor
      edge: edge>0?0.85:0.4,                                    // must-have positive net edge
      noLeak: 0.85, coverage: 0.8                               // assumed server PIT/coverage-gated (not a free pass)
    };
    return window.MrktMastery.classify(comps,criticals,{
      n: facN, initialPass:true, delayedPass:(facN!=null&&facN>=120),  // accrued evidence = the delayed confirm
    });
  }

  function paint(board){
    var rows=Array.prototype.slice.call(board.querySelectorAll('.bbrow'));
    rows.forEach(function(r){
      var hd=r.querySelector('.bbhd'); if(!hd)return;
      var old=hd.querySelector('.'+BADGE); if(old)old.parentNode.removeChild(old);
      var res=tierFor(r, rows.length); if(!res)return;
      var T=res.tier, lab=T==='mastery'?'MAST':T==='proficient'?'PROF':'NOV';
      var col=T==='mastery'?'#2ecc8f':T==='proficient'?'#d8b24a':'#69727f';
      var sp=document.createElement('span'); sp.className=BADGE;
      sp.style.cssText='font-size:8px;font-weight:800;letter-spacing:.04em;color:#0b0e13;background:'+col
        +';border-radius:3px;padding:1px 4px;margin-left:6px;white-space:nowrap';
      sp.title='signal-mastery: '+T.toUpperCase()+' · composite '+res.overall+'/100 · min-critical '+res.minCritical
        +' · evidence '+res.band+(res.whyNotMastery&&res.whyNotMastery.length?(' · not mastery: '+res.whyNotMastery.join(', ')):'')
        +(res.blockedBy&&res.blockedBy.length?(' · BLOCKED: '+res.blockedBy.join(', ')):'')
        +' · MAST requires composite≥85, all criticals≥80 (incl. deflated-conviction DSR gate) + accrued confirmation. Research only.';
      sp.textContent=lab;
      hd.appendChild(sp);
    });
  }

  var t=null,applying=false;
  function schedule(){clearTimeout(t);t=setTimeout(run,130);}
  function run(){var b=document.getElementById('bullBearBoard');if(!b||!b.querySelector('.bbcol'))return;
    applying=true;try{paint(b);}catch(e){}setTimeout(function(){applying=false;},0);}
  if(typeof document!=='undefined'){
    if(document.readyState!=='loading')schedule();else document.addEventListener('DOMContentLoaded',schedule);
    new MutationObserver(function(muts){if(applying)return;for(var i=0;i<muts.length;i++){var tg=muts[i].target;
      if(tg&&(tg.id==='bullBearBoard'||(tg.closest&&tg.closest('#bullBearBoard')))){schedule();return;}}})
      .observe(document.body,{childList:true,subtree:true});
  }
})();
