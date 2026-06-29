/* regime_panel.js — per-name VOLATILITY-REGIME chip on the Bull/Bear board. EXTERNAL module (mastery_panel
   pattern): reads window.MMAP n.reg (server-side 2-state HMM, regime_board.py) and paints a "STRESS" chip
   only on names currently in a genuinely separated high-variance regime (calm names get no chip, to keep
   rows clean). A stressed name should be sized down and its bands widened. Research only, not advice. */
(function () {
  'use strict';
  var CHIP = 'bbreg';
  function nmeFor(tk){try{var m=window.MMAP&&window.MMAP.names;if(!m||!tk)return null;tk=tk.toUpperCase();
    for(var i=0;i<m.length;i++)if((m[i].t||'').toUpperCase()===tk)return m[i];}catch(e){}return null;}

  function paint(board){
    var rows=Array.prototype.slice.call(board.querySelectorAll('.bbrow'));
    rows.forEach(function(r){
      var hd=r.querySelector('.bbhd'); if(!hd)return;
      var old=hd.querySelector('.'+CHIP); if(old)old.parentNode.removeChild(old);
      var n=nmeFor(r.getAttribute('data-tk')); if(!n||!n.reg)return;
      var rg=n.reg; if(rg.state!=='stress')return;                  // only flag real stress regimes
      var sp=document.createElement('span'); sp.className=CHIP;
      var col='#d2603f';
      sp.style.cssText='font-size:8px;font-weight:800;letter-spacing:.03em;color:'+col+';border:1px solid '+col
        +'66;border-radius:3px;padding:0 4px;margin-left:6px;white-space:nowrap';
      sp.title='HMM volatility regime: STRESS now · variance separation '+(rg.sep!=null?rg.sep.toFixed(1)+'x':'?')
        +' calm-vs-stress · P(stress)='+(rg.pStress!=null?rg.pStress.toFixed(2):'?')
        +' · stress-state annualized drift '+(rg.muStressAnn!=null?rg.muStressAnn.toFixed(0)+'%':'?')
        +'. Size down / widen bands in stress. 2-state Gaussian HMM (#5), '+(rg.n||'?')+' obs. Research only.';
      sp.textContent='⚡STRESS';
      hd.appendChild(sp);
    });
  }

  var t=null,applying=false;
  function schedule(){clearTimeout(t);t=setTimeout(run,170);}
  function run(){var b=document.getElementById('bullBearBoard');if(!b||!b.querySelector('.bbcol'))return;
    applying=true;try{paint(b);}catch(e){}setTimeout(function(){applying=false;},0);}
  if(typeof document!=='undefined'){
    if(document.readyState!=='loading')schedule();else document.addEventListener('DOMContentLoaded',schedule);
    new MutationObserver(function(muts){if(applying)return;for(var i=0;i<muts.length;i++){var tg=muts[i].target;
      if(tg&&(tg.id==='bullBearBoard'||(tg.closest&&tg.closest('#bullBearBoard')))){schedule();return;}}})
      .observe(document.body,{childList:true,subtree:true});
  }
})();
