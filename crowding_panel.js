/* crowding_panel.js — per-name CROWDING / SQUEEZE chip on the Bull/Bear board. EXTERNAL module (same
   pattern as mastery_panel.js / event_panel.js): reads each row's window.MMAP record and surfaces the
   short-side crowding read from data already present client-side — short-interest level/trend (FINRA
   fails), institutional distribution (13F), and gamma regime (negative gamma = trend-amplifying squeeze
   fuel). Transparent, bounded score; only paints a chip when the read is materially crowded. This is the
   client view of the verified crowding_engine (#7); the full days-to-cover / HHI / borrow-fee version
   runs server-side where the raw short + 13F holder data live. Research only, not advice. */
(function () {
  'use strict';
  var CHIP = 'bbcrowd';
  function nmeFor(tk){try{var m=window.MMAP&&window.MMAP.names;if(!m||!tk)return null;tk=tk.toUpperCase();
    for(var i=0;i<m.length;i++)if((m[i].t||'').toUpperCase()===tk)return m[i];}catch(e){}return null;}
  function clamp01(x){return Math.max(0,Math.min(1,x));}

  function crowdFor(n){
    var sh=n.short, inst=n.inst, gex=n.gex;
    // PREFER the server-computed crowding block (crowding_board.py): real days-to-cover (FTD/ADV),
    // FTD short-interest %, and crowding_engine penalty. Falls back to the client proxy below.
    var cr=n.cr;
    if(cr){
      var dtcN=(cr.dtc!=null)?clamp01(cr.dtc/8.0):0;                 // ~8d to cover = max
      var penN=(cr.pen!=null)?clamp01(cr.pen/0.10):0;                // ~10% penalty = max
      var sScore=clamp01(0.55*dtcN + 0.45*penN + (cr.squeeze?0.25:0));
      var sWhy=[];
      if(cr.dtc!=null) sWhy.push('DTC '+cr.dtc.toFixed(1)+'d');
      if(cr.siPct!=null) sWhy.push('SI '+cr.siPct.toFixed(1)+'%');
      if(cr.borrowFee!=null && cr.borrowFee>1) sWhy.push('borrow ~'+cr.borrowFee.toFixed(1)+'%');
      if(gex&&/negative/.test(gex.regime||'')) sWhy.push('neg-gamma');
      return {score:sScore, why:sWhy, server:true};
    }
    if(!sh && !inst) return null;                                   // nothing to say
    // short-interest level (FINRA fails proxy): elevated dominates the read
    var lvl=sh?({elevated:1.0,moderate:0.5,low:0.15}[sh.level]!=null?{elevated:1.0,moderate:0.5,low:0.15}[sh.level]:0.3):0.3;
    var trend=sh?({rising:0.30,falling:-0.20,flat:0.0}[sh.trend]||0):0;
    var gamma=(gex&&/negative/.test(gex.regime||''))?0.25:0;        // negative gamma amplifies a squeeze
    var conc=inst?({distribution:0.15,accumulation:-0.10,stable:0}[inst.verdict]||0):0;
    var score=clamp01(0.5*lvl + trend + gamma + conc);
    var why=[];
    if(sh){why.push('short '+(sh.level||'?')+'/'+(sh.trend||'?'));}
    if(gamma){why.push('neg-gamma');}
    if(inst&&inst.verdict==='distribution'){why.push('13F distribution');}
    if(inst&&inst.verdict==='accumulation'){why.push('13F accumulation');}
    return {score:score, why:why};
  }

  function paint(board){
    var rows=Array.prototype.slice.call(board.querySelectorAll('.bbrow'));
    rows.forEach(function(r){
      var hd=r.querySelector('.bbhd'); if(!hd)return;
      var old=hd.querySelector('.'+CHIP); if(old)old.parentNode.removeChild(old);
      var tk=r.getAttribute('data-tk'); var n=nmeFor(tk); if(!n)return;
      var c=crowdFor(n); if(!c)return;
      if(c.score<0.35) return;                                      // only flag materially crowded names
      var hot=c.score>=0.6;
      var lab=hot?'🔥 squeeze':'crowded';
      var col=hot?'#ef7a3a':'#caa24a';
      var sp=document.createElement('span'); sp.className=CHIP;
      sp.style.cssText='font-size:8px;font-weight:700;letter-spacing:.02em;color:'+col+';border:1px solid '+col
        +'66;border-radius:3px;padding:0 4px;margin-left:6px;white-space:nowrap';
      sp.title='crowding/squeeze read '+(c.score*100).toFixed(0)+'/100 · '+(c.why.join(' · ')||'short-side pressure')
        +(c.server
           ? ' · SERVER crowding_engine (#7): days-to-cover = SEC fails-to-deliver / avg daily volume, FTD short-interest %, borrow-fee proxy. FTD is a conservative floor on true short interest.'
           : ' · client proxy: short level/trend + negative gamma + 13F distribution. Full days-to-cover/borrow runs server-side.')
        +' Research only, not advice.';
      sp.textContent=lab;
      hd.appendChild(sp);
    });
  }

  var t=null,applying=false;
  function schedule(){clearTimeout(t);t=setTimeout(run,150);}
  function run(){var b=document.getElementById('bullBearBoard');if(!b||!b.querySelector('.bbcol'))return;
    applying=true;try{paint(b);}catch(e){}setTimeout(function(){applying=false;},0);}
  if(typeof document!=='undefined'){
    if(document.readyState!=='loading')schedule();else document.addEventListener('DOMContentLoaded',schedule);
    new MutationObserver(function(muts){if(applying)return;for(var i=0;i<muts.length;i++){var tg=muts[i].target;
      if(tg&&(tg.id==='bullBearBoard'||(tg.closest&&tg.closest('#bullBearBoard')))){schedule();return;}}})
      .observe(document.body,{childList:true,subtree:true});
  }
})();
