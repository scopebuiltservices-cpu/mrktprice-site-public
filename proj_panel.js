/* proj_panel.js — per-name forward P(up) chip on the Bull/Bear board. EXTERNAL module (mastery_panel
   pattern): reads window.MMAP n.pj (server no-lookahead OU/EMA-blend projection, proj_board.py) and paints
   a compact "P↑NN%" chip showing the 21d probability the name finishes above its current price, colored by
   direction. Only shows when the edge is meaningful (probUp <=0.42 or >=0.58) to keep rows clean. This is
   the SAME forecast the projClose-vs-priceNow learning is scored against. Research only, not advice. */
(function () {
  'use strict';
  var CHIP = 'bbproj';
  function nmeFor(tk){try{var m=window.MMAP&&window.MMAP.names;if(!m||!tk)return null;tk=tk.toUpperCase();
    for(var i=0;i<m.length;i++)if((m[i].t||'').toUpperCase()===tk)return m[i];}catch(e){}return null;}

  function paint(board){
    var rows=Array.prototype.slice.call(board.querySelectorAll('.bbrow'));
    rows.forEach(function(r){
      var hd=r.querySelector('.bbhd'); if(!hd)return;
      var old=hd.querySelector('.'+CHIP); if(old)old.parentNode.removeChild(old);
      var n=nmeFor(r.getAttribute('data-tk')); if(!n||!n.pj)return;
      var pj=n.pj, pu=pj.probUp; if(pu==null)return;
      if(pu>0.42 && pu<0.58) return;                                // only flag a meaningful directional edge
      var up=pu>=0.58, col=up?'#2ecc8f':'#ef5f4e';
      var sp=document.createElement('span'); sp.className=CHIP;
      sp.style.cssText='font-size:8px;font-weight:800;letter-spacing:.02em;color:'+col+';border:1px solid '+col
        +'66;border-radius:3px;padding:0 4px;margin-left:6px;white-space:nowrap';
      sp.title='server '+(pj.h||21)+'d forward projection (no lookahead, OU/EMA-blend drift): projClose '
        +(pj.projClose!=null?pj.projClose:'?')+' = '+(pj.projPct>=0?'+':'')+(pj.projPct!=null?pj.projPct:'?')
        +'% vs now · P(close > now) = '+(pu*100).toFixed(0)+'% · forecast sigma '+(pj.sigmaHPct!=null?pj.sigmaHPct+'%':'?')
        +'. Same forecast the projClose-vs-priceNow learning is scored on (#4/#8). Research only.';
      sp.textContent=(up?'P↑':'P↓')+(pu*100).toFixed(0)+'%';
      hd.appendChild(sp);
    });
  }

  var t=null,applying=false;
  function schedule(){clearTimeout(t);t=setTimeout(run,190);}
  function run(){var b=document.getElementById('bullBearBoard');if(!b||!b.querySelector('.bbcol'))return;
    applying=true;try{paint(b);}catch(e){}setTimeout(function(){applying=false;},0);}
  if(typeof document!=='undefined'){
    if(document.readyState!=='loading')schedule();else document.addEventListener('DOMContentLoaded',schedule);
    new MutationObserver(function(muts){if(applying)return;for(var i=0;i<muts.length;i++){var tg=muts[i].target;
      if(tg&&(tg.id==='bullBearBoard'||(tg.closest&&tg.closest('#bullBearBoard')))){schedule();return;}}})
      .observe(document.body,{childList:true,subtree:true});
  }
})();
