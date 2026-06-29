/* signal_screener.js — 100x USE/INPUT/ANALYSIS: one interactive, filterable, ranked ACTIONABLE-SETUPS
   panel that fuses every per-name enrichment into a single composite read. EXTERNAL module: reads
   window.MMAP (server enrichments) — adjusted beta, n.fund (target upside / rating / forward EPS /
   surprise), n.cr (crowding/squeeze), n.reg (calm/stress regime), n.pj (P-up), conviction z, secMismatch.
   INPUT: filter toggles + free-text search + sort. ANALYSIS: composite actionability score + one-line
   synthesized read per name. NOTIFICATION: "N high-conviction setups today" badge. Filters persist in
   localStorage. Pure read-only over the board data; research only, not advice. */
(function () {
  'use strict';
  var MOUNT = 'mrktScreener', LSK = 'mrktScreenerFilters';
  function clamp01(x){return Math.max(0,Math.min(1,x));}
  function num(x){return (x==null||x!==x)?null:+x;}

  // ---- pure, testable scoring/filtering (exposed on window.MrktScreener) ----
  function score(n){
    var f=n.fund||{}, cr=n.cr||{}, rg=n.reg||{}, pj=n.pj||{};
    var z=Math.abs(num(n.z)||0);                                  // conviction
    var up=num(f.targetUpsidePct);                                // analyst upside %
    var pu=num(pj.probUp);                                        // P(close>now)
    var pen=num(cr.pen)||0;                                       // crowding penalty (mu drag)
    var stress=rg.state==='stress';
    var ratingScore=num(f.ratingScore);                          // 1..5
    var surprise=num(f.surprisePct);
    var s = 0.30*clamp01(z/2.5)
          + 0.28*clamp01(((up==null?0:up))/20)                    // +20% target = max
          + 0.20*clamp01(pu==null?0.5:(pu-0.5)/0.25)              // P-up edge above 50%
          + 0.12*clamp01(ratingScore==null?0.5:(ratingScore-1)/4)
          + 0.10*clamp01(surprise==null?0.5:(surprise/10+0.5));   // recent beat
    s -= 0.20*clamp01(pen/0.05);                                  // crowding drag
    if(stress) s*=0.7;                                            // size down in stress
    var reasons=[];
    if(up!=null&&up>=8) reasons.push('PT +'+up.toFixed(0)+'%');
    if(z>=1.5) reasons.push('HIGH conviction');
    if(pu!=null&&pu>=0.58) reasons.push('P-up '+(pu*100).toFixed(0)+'%');
    if(f.rating) reasons.push(f.rating);
    if(surprise!=null&&surprise>=3) reasons.push('beat +'+surprise.toFixed(0)+'%');
    if(cr.squeeze) reasons.push('⚠ squeeze');
    if(stress) reasons.push('⚡ stress');
    if(n.secMismatch) reasons.push('sector reclassified');
    // a HIGH-CONVICTION actionable setup: strong, cheap-to-target, calm, not crowded
    var actionable = (z>=1.3) && (up!=null&&up>=8) && !stress && !cr.squeeze && (pu==null||pu>=0.55);
    return {score:Math.round(clamp01(s)*100), actionable:!!actionable, reasons:reasons,
            up:up, z:z, pu:pu, stress:stress, squeeze:!!cr.squeeze, rating:f.rating||null};
  }
  function passes(n, F){
    var sc=score(n), f=n.fund||{}, rg=n.reg||{}, cr=n.cr||{};
    if(F.mast && !(sc.z>=1.5 && (f.targetUpsidePct||0)>=8)) return false;   // proxy "high quality"
    if(F.calm && rg.state==='stress') return false;
    if(F.noCrowd && cr.squeeze) return false;
    if(F.upMin && !((f.targetUpsidePct||-999)>=F.upMin)) return false;
    if(F.squeeze && !cr.squeeze) return false;
    if(F.q){ var q=F.q.toUpperCase(); if(((n.t||'')+(n.sec||'')).toUpperCase().indexOf(q)<0) return false; }
    return true;
  }
  window.MrktScreener = {score:score, passes:passes};

  // ---- UI ----
  function isETF(n){return ['Commodity','FX','Rate','Style','Broad','Global','Sector'].indexOf(n.sec)>=0;}
  function loadF(){try{return JSON.parse(localStorage.getItem(LSK))||{};}catch(e){return {};}}
  function saveF(F){try{localStorage.setItem(LSK,JSON.stringify(F));}catch(e){}}
  function mount(){
    var board=document.getElementById('bullBearBoard'); if(!board)return null;
    var p=document.getElementById(MOUNT);
    if(!p){p=document.createElement('div');p.id=MOUNT;p.style.cssText='margin:12px 0';board.parentNode.insertBefore(p,board);}
    return p;
  }
  function chip(label,on){return '<b data-f="'+label+'" class="scf'+(on?' on':'')+'">'+label+'</b>';}

  function render(){
    var m=window.MMAP, p=mount(); if(!m||!m.names||!p)return;
    var F=loadF();
    var names=m.names.filter(function(n){return n.t&&!isETF(n);});
    var scored=names.map(function(n){return {n:n,s:window.MrktScreener.score(n)};});
    var nAction=scored.filter(function(x){return x.s.actionable;}).length;
    var view=scored.filter(function(x){return window.MrktScreener.passes(x.n,F);});
    view.sort(function(a,b){return b.s.score-a.s.score;});
    var top=view.slice(0,12);
    var css='<style>#'+MOUNT+'{background:#0b0e13;border:1px solid var(--line);border-radius:10px;padding:8px 10px}'
      +'#'+MOUNT+' .scbar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:10px;color:var(--muted)}'
      +'#'+MOUNT+' .scf{cursor:pointer;border:1px solid var(--line);border-radius:6px;padding:2px 7px;color:#9aa4b2;font-weight:600}'
      +'#'+MOUNT+' .scf.on{background:var(--brandglow,rgba(120,160,255,.18));color:var(--ink,#e7ecf3);border-color:#5b7;}'
      +'#'+MOUNT+' input.scq{background:var(--panel2,#0f141b);border:1px solid var(--line);border-radius:6px;color:#e7ecf3;padding:2px 7px;font-size:10px;width:120px}'
      +'#'+MOUNT+' .scrow{display:flex;gap:8px;align-items:baseline;padding:4px 6px;border-top:1px solid var(--line);cursor:pointer}'
      +'#'+MOUNT+' .scrow:hover{background:rgba(255,255,255,.03)}#'+MOUNT+' .sct{font-weight:800;font-size:12px;min-width:54px}'
      +'#'+MOUNT+' .scsc{font-weight:800;font-size:12px;min-width:30px}#'+MOUNT+' .scwhy{font-size:9px;color:#8a93a3}'
      +'#'+MOUNT+' .scbadge{font-weight:800;color:#0b0e13;background:#2ecc8f;border-radius:5px;padding:1px 7px;font-size:11px}</style>';
    var bar='<div class="scbar"><span class="scbadge">'+nAction+' actionable setups today</span>'
      + '<b style="color:var(--gold);font-size:11px">SIGNAL SCREENER</b> · filter: '
      + chip('MAST',F.mast)+chip('calm',F.calm)+chip('noCrowd',F.noCrowd)+chip('squeeze',F.squeeze)
      + '<label style="cursor:pointer">PT&gt;<input class="scq" id="scUp" type="number" value="'+(F.upMin||'')+'" style="width:46px" placeholder="%"></label>'
      + '<input class="scq" id="scQ" placeholder="search ticker/sector" value="'+(F.q||'')+'">'
      + '<span style="color:var(--faint)">showing '+top.length+'/'+view.length+' · ranked by composite. Research only.</span></div>';
    var rows=top.map(function(x){var n=x.n,s=x.s;var col=s.actionable?'#2ecc8f':(s.stress||s.squeeze?'#ef5f4e':'#9ab4e0');
      return '<div class="scrow" onclick="try{load(\''+n.t+'\',DATA[\''+n.t+'\'])}catch(e){}">'
        +'<span class="scsc" style="color:'+col+'">'+s.score+'</span>'
        +'<span class="sct">'+n.t+(s.actionable?' ★':'')+'</span>'
        +'<span style="font-size:9px;color:var(--muted);min-width:90px">'+(n.sec||'')+'</span>'
        +'<span class="scwhy">'+(s.reasons.join(' · ')||'no strong signal')+'</span></div>';}).join('');
    p.innerHTML=css+bar+'<div>'+rows+'</div>';
    // wire inputs
    p.querySelectorAll('.scf').forEach(function(b){b.onclick=function(){var k={MAST:'mast',calm:'calm',noCrowd:'noCrowd',squeeze:'squeeze'}[b.getAttribute('data-f')];F[k]=!F[k];saveF(F);render();};});
    var up=document.getElementById('scUp'); if(up)up.onchange=function(){F.upMin=up.value?+up.value:0;saveF(F);render();};
    var q=document.getElementById('scQ'); if(q)q.oninput=function(){F.q=q.value;saveF(F);clearTimeout(q._t);q._t=setTimeout(render,200);};
  }

  var t=null,applying=false;
  function schedule(){clearTimeout(t);t=setTimeout(run,200);}
  function run(){if(applying)return;var b=document.getElementById('bullBearBoard');if(!b||!b.querySelector('.bbcol'))return;
    applying=true;try{render();}catch(e){}setTimeout(function(){applying=false;},0);}
  if(typeof document!=='undefined'){
    if(document.readyState!=='loading')schedule();else document.addEventListener('DOMContentLoaded',schedule);
    new MutationObserver(function(muts){if(applying)return;for(var i=0;i<muts.length;i++){var tg=muts[i].target;
      if(tg&&tg.id==='bullBearBoard'){schedule();return;}}}).observe(document.body,{childList:true,subtree:true});
  }
})();
