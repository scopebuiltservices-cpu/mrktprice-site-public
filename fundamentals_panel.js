/* fundamentals_panel.js — per-name FUNDAMENTALS + ANALYST chip on the Bull/Bear board. EXTERNAL module
   (mastery_panel pattern): reads window.MMAP n.fund (FMP bulk ratios/metrics + analyst price target +
   rating, via fmp_bulk.py -> fundamentals_board.py) and paints a compact chip with the analyst target
   upside and letter rating. Only shows when there is a meaningful target. Research only, not advice. */
(function () {
  'use strict';
  var CHIP = 'bbfund';
  function nmeFor(tk){try{var m=window.MMAP&&window.MMAP.names;if(!m||!tk)return null;tk=tk.toUpperCase();
    for(var i=0;i<m.length;i++)if((m[i].t||'').toUpperCase()===tk)return m[i];}catch(e){}return null;}

  function paint(board){
    var rows=Array.prototype.slice.call(board.querySelectorAll('.bbrow'));
    rows.forEach(function(r){
      var hd=r.querySelector('.bbhd'); if(!hd)return;
      var old=hd.querySelector('.'+CHIP); if(old)old.parentNode.removeChild(old);
      var n=nmeFor(r.getAttribute('data-tk')); if(!n||!n.fund)return;
      var f=n.fund, up=f.targetUpsidePct;
      if(up==null && f.rating==null) return;                       // nothing material to show
      var lab='', col='#9ab4e0';
      if(up!=null){ col=up>=0?'#2ecc8f':'#ef5f4e'; lab='PT '+(up>=0?'+':'')+up.toFixed(0)+'%'; }
      if(f.rating){ lab=(lab?lab+' ':'')+f.rating; }
      var sp=document.createElement('span'); sp.className=CHIP;
      sp.style.cssText='font-size:8px;font-weight:700;letter-spacing:.02em;color:'+col+';border:1px solid '+col
        +'66;border-radius:3px;padding:0 4px;margin-left:6px;white-space:nowrap';
      sp.title='FMP analyst + fundamentals'
        +(f.targetAvg!=null?(' · consensus price target $'+f.targetAvg+(up!=null?(' ('+(up>=0?'+':'')+up.toFixed(1)+'% vs now)'):'')):'')
        +(f.rating?(' · rating '+f.rating+(f.ratingScore!=null?(' ('+f.ratingScore+'/5)'):'')):'')
        +(f.pe!=null?(' · P/E '+(+f.pe).toFixed(1)):'')
        +(f.roe!=null?(' · ROE '+(f.roe*100).toFixed(0)+'%'):'')
        +(f.fcfYield!=null?(' · FCF-yield '+(f.fcfYield*100).toFixed(1)+'%'):'')
        +'. Bulk FMP (4 calls/universe). Research only.';
      sp.textContent=lab;
      hd.appendChild(sp);
    });
  }

  var t=null,applying=false;
  function schedule(){clearTimeout(t);t=setTimeout(run,210);}
  function run(){var b=document.getElementById('bullBearBoard');if(!b||!b.querySelector('.bbcol'))return;
    applying=true;try{paint(b);}catch(e){}setTimeout(function(){applying=false;},0);}
  if(typeof document!=='undefined'){
    if(document.readyState!=='loading')schedule();else document.addEventListener('DOMContentLoaded',schedule);
    new MutationObserver(function(muts){if(applying)return;for(var i=0;i<muts.length;i++){var tg=muts[i].target;
      if(tg&&(tg.id==='bullBearBoard'||(tg.closest&&tg.closest('#bullBearBoard')))){schedule();return;}}})
      .observe(document.body,{childList:true,subtree:true});
  }
})();
