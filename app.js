"use strict";
/* Centrum rynku – cała logika strony. Dane pochodzą z data.json (tworzy go fetch_data.py). */

// ---------- pamięć przeglądarki ----------
const store={get(k,d){try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v)}catch(e){return d}},
 set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
const DEF_FAV=["TPE.WA","CDR.WA","BTC-USD","SI=F","GC=F","AAPL"];
let D=null,fav=store.get("fav",DEF_FAV),listTab="fav",range=store.get("range2","3M"),ntab="week";
let calScope="fav",calType="all",jMode="paper";
let settings=Object.assign({capital:10000,risk:1,mode:"cfd",comm:0,swap:7,days:1},store.get("settings",{}));
let journal=store.get("journal",[]);
const saveSettings=()=>store.set("settings",settings),saveJournal=()=>store.set("journal",journal);

// ---------- formatowanie ----------
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const dec=n=>Math.abs(n)>=1000?0:Math.abs(n)>=2?2:4;
const fmt=(n,d)=>n==null||!isFinite(n)?"–":n.toLocaleString("pl-PL",{minimumFractionDigits:d??dec(n),maximumFractionDigits:d??dec(n)});
const pln=n=>fmt(n,Math.abs(n)>=100?0:2)+" zł";
const pct=(x,d=1)=>x==null||!isFinite(x)?"–":(x>0?"+":x<0?"−":"")+Math.abs(x).toLocaleString("pl-PL",{minimumFractionDigits:d,maximumFractionDigits:d})+"%";
const sgn=x=>x==null||Math.abs(x)<1e-9?"flat":x>0?"up":"down";
const p50=p=>p==null?"flat":p>50?"up":p<50?"down":"flat";
const safe=u=>/^https?:\/\//.test(u||"")?u:"#";
const MON=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"];
const MONF=["stycznia","lutego","marca","kwietnia","maja","czerwca","lipca","sierpnia","września","października","listopada","grudnia"];
const WDF=["niedziela","poniedziałek","wtorek","środa","czwartek","piątek","sobota"];
const dayDate=o=>new Date((o-719163)*864e5); // numer dnia z Pythona (date.toordinal) -> data
const dlabel=(d,y)=>d.getUTCDate()+" "+MON[d.getUTCMonth()]+(y?" "+d.getUTCFullYear():"");
const hm=d=>d.toLocaleTimeString("pl-PL",{hour:"2-digit",minute:"2-digit"});
function ago(iso){const h=(Date.now()-new Date(iso))/36e5;if(h<1)return "przed chwilą";if(h<24)return Math.floor(h)+" godz. temu";const d=Math.floor(h/24);return d===1?"wczoraj":d+" dni temu"}
const DEC={go:"c-go",wait:"c-wait",no:"c-no"};
const item=s=>D.items.find(i=>i.symbol===s);

// ---------- godziny handlu (bez świąt) ----------
const SESS={gpw:{tz:"Europe/Warsaw",o:540,c:1025,name:"GPW"},us:{tz:"America/New_York",o:570,c:960,name:"Giełda USA"},
 fut:{tz:"America/New_York",name:"Surowce"},crypto:{name:"Krypto"}};
const KIND={"Akcje GPW":"gpw","Akcje USA":"us","Indeksy":"us","Surowce":"fut","Krypto":"crypto"};
const fmtCache={};
function local(tz,date){const f=fmtCache[tz]||(fmtCache[tz]=new Intl.DateTimeFormat("en-US",{timeZone:tz,weekday:"short",hour:"numeric",minute:"numeric",hourCycle:"h23"}));
 const p={};f.formatToParts(date).forEach(x=>p[x.type]=x.value);
 return {wd:["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].indexOf(p.weekday)+1,m:(+p.hour%24)*60+(+p.minute)}}
function isOpen(k,date){const s=SESS[k];if(k==="crypto")return true;const {wd,m}=local(s.tz,date);
 if(k==="fut")return (wd===7&&m>=1080)||(wd>=1&&wd<=4&&!(m>=1020&&m<1080))||(wd===5&&m<1020);
 return wd<=5&&m>=s.o&&m<s.c}
const statusCache={};
function status(k){if(k==="crypto")return {open:true,text:"Otwarty 24/7"};
 const key=k+Math.floor(Date.now()/6e4);if(statusCache[key])return statusCache[key];
 const now=new Date(),open=isOpen(k,now);let mins=0;
 for(let t=5;t<=6*24*60;t+=5){if(isOpen(k,new Date(now.getTime()+t*6e4))!==open){mins=t;break}}
 const h=Math.floor(mins/60),m=mins%60,dur=(h?h+" godz. ":"")+(h<10&&m?m+" min":"");
 return statusCache[key]={open,text:open?`Otwarty · zamknięcie za ${dur}`:`Zamknięty · otwarcie za ${dur}`}}

// ---------- wspólne kawałki ----------
const bar=(p,col)=>`<div class="bar8"><i style="width:${p??0}%;background:${col}"></i><b></b></div>`;
const heart=it=>{const f=fav.includes(it.symbol);return `<button class="heart" data-heart="${esc(it.symbol)}" aria-pressed="${f}" aria-label="${f?"Usuń z ulubionych":"Dodaj do ulubionych"}">${f?"♥":"♡"}</button>`};
const riskChip=r=>`<span class="chip dot r${r.level}">Ryzyko: ${esc(r.label.toLowerCase())}</span>`;
function eventsFor(sym){return (D.calendar||[]).filter(e=>e.symbols.includes(sym)&&e.days>=0)}
function whenTxt(d){return d===0?"dziś":d===1?"jutro":d<5?`za ${d} dni`:`za ${d} dni`}
function nextEventChip(sym){const e=eventsFor(sym).find(e=>e.impact==="high"&&e.days<=7);
 if(!e)return "";const t=e.kind==="wyniki"?"Wyniki":e.kind==="makro"?"Ważne dane":"Wydarzenie";
 return `<span class="chip" style="color:var(--info)">${t} ${whenTxt(e.days)}</span>`}

// ---------- RYNKI ----------
function spark(it){const c=it.hist.c.slice(-30),mn=Math.min(...c),mx=Math.max(...c),k=mx-mn||1;
 const pts=c.map((v,i)=>`${(i/(c.length-1)*100).toFixed(2)},${(38-(v-mn)/k*34).toFixed(2)}`).join(" ");
 return `<svg class="spark" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${c[c.length-1]>=c[0]?"var(--up)":"var(--down)"}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`}
function card(it){const st=status(KIND[it.group]);
 return `<article class="card" data-open="${esc(it.symbol)}" tabindex="0" role="button" aria-label="Pokaż analizę: ${esc(it.name)}">
 <header><div><h2>${esc(it.name)}</h2><span class="sub">${esc(it.symbol)} · ${st.open?"otwarty":"zamknięty"}</span></div>
 <div class="px">${fmt(it.price)} ${esc(it.currency)}<span class="chg ${sgn(it.change)}">${pct(it.change,2)}</span></div>${heart(it)}</header>
 ${spark(it)}
 <div class="cfoot"><span class="dec ${DEC[it.decision.key]} bg-${it.decision.key}">${esc(it.decision.title)}</span>${riskChip(it.risk)}${nextEventChip(it.symbol)}</div></article>`}
function viewRynki(){
 const k=["gpw","us","fut","crypto"].map(k=>{const s=status(k);return `<span class="chip dot ${s.open?"up":"flat"}" title="${esc(s.text)}">${SESS[k].name}: ${s.open?"otwarte":"zamknięte"}</span>`}).join("");
 $("app").innerHTML=`<div class="upd">${updTxt()}</div>
 <div class="status">${k}</div>
 <div class="pulse" aria-label="Puls rynku">${(D.pulse||[]).map(p=>`<div class="pc"><b>${esc(p.name)}</b><strong>${fmt(p.price)}</strong><span class="${sgn(p.change)}">${pct(p.change,2)}</span><small>${esc(p.note)}</small></div>`).join("")}</div>
 <div class="ctl"><div class="seg" role="group" aria-label="Lista"><button data-list="fav" aria-pressed="${listTab==="fav"}">Ulubione</button><button data-list="all" aria-pressed="${listTab==="all"}">Wszystkie</button></div>
 <input id="q" type="search" placeholder="Szukaj instrumentu" aria-label="Szukaj instrumentu"></div>
 <div id="out" class="grid"></div>`;
 $("q").oninput=renderList;renderList()}
function renderList(){const q=($("q")?.value||"").toLowerCase();
 const list=D.items.filter(i=>(listTab==="all"||fav.includes(i.symbol))&&(i.name+i.symbol+i.group).toLowerCase().includes(q));
 $("out").innerHTML=list.length?list.map(card).join(""):`<div class="msg">${listTab==="fav"&&!q?"Nie masz jeszcze ulubionych. Przejdź do „Wszystkie” i kliknij serduszko przy instrumencie.":"Nic nie pasuje do wyszukiwania."}</div>`}
const updTxt=()=>D?"Dane z "+new Date(D.updated).toLocaleString("pl-PL",{dateStyle:"medium",timeStyle:"short"}):"";

// ---------- SZCZEGÓŁY ----------
const DTABS=[["decyzja","Decyzja"],["wykres","Wykres"],["kalkulator","Kalkulator ryzyka"],["prognoza","Prognoza"],["newsy","Newsy i wydarzenia"]];
function viewDetail(sym,tab){const it=item(sym);if(!it){location.hash="#rynki";return}
 tab=DTABS.some(t=>t[0]===tab)?tab:"decyzja";const st=status(KIND[it.group]);
 $("app").innerHTML=`<button class="back" data-back>← Wróć do listy</button>
 <div class="dhead"><div><h2>${esc(it.name)}</h2><span class="sub">${esc(it.symbol)} · ${esc(it.group)} · <span class="${st.open?"up":"mut"}">${esc(st.text)}</span></span></div>
 <div class="row"><div class="dprice">${fmt(it.price)} ${esc(it.currency)}<span class="${sgn(it.change)}">${pct(it.change,2)}</span></div>${heart(it)}</div></div>
 <div class="tabs" role="tablist">${DTABS.map(([k,l])=>`<button role="tab" data-tab="${k}" aria-selected="${k===tab}">${l}</button>`).join("")}</div>
 <div id="tab"></div>`;
 ({decyzja:tDecyzja,wykres:tWykres,kalkulator:tKalk,prognoza:tPrognoza,newsy:tNewsy})[tab](it);
 if(tab==="wykres")drawChart(it)}

function tDecyzja(it){const d=it.decision,pl=it.plan,r=it.risk;
 const ev=eventsFor(it.symbol).filter(e=>e.days<=7&&e.impact!=="low");
 const extra=r.why.slice(1);
 $("tab").innerHTML=`<div class="hero bg-${d.key}"><h3 class="${DEC[d.key]}">${esc(d.title)}</h3><ul>${d.reasons.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>
 <div class="stats3">
  <div class="stat"><b>Szansa wzrostu jutro</b><strong class="${p50(it.overall)}">${fmt(it.overall,0)}%</strong></div>
  <div class="stat"><b>Szansa wzrostu w tydzień</b><strong class="${p50(it.p_week)}">${it.p_week==null?"–":fmt(it.p_week,0)+"%"}</strong></div>
  <div class="stat"><b>Ryzyko</b><strong class="r${r.level}">${esc(r.label)}</strong></div></div>
 ${ev.length||extra.length?`<div class="alert ${ev.some(e=>e.days<=1&&e.impact==="high")?"red":""}"><b>Zwróć uwagę</b><ul>${ev.map(e=>`<li>${esc(e.title)} – ${whenTxt(e.days)}${e.time?" o "+hm(new Date(e.date)):""}</li>`).join("")}${extra.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>`:""}
 <section class="box plan"><h3>Co zrobić – krok po kroku</h3><p>${esc(pl.head)}</p><ol>${pl.steps.map(s=>`<li>${esc(s)}</li>`).join("")}</ol>
  <div class="alert" style="margin:12px 0 0">${esc(pl.warn)}</div>
  <ul class="clean checks" aria-label="Warunki wzrostu">${pl.checks.map(c=>`<li><span class="ic ${c.ok?"up":"down"}">${c.ok?"✓":"✗"}</span><span>${esc(c.text)}</span></li>`).join("")}</ul>
  <div class="row" style="margin-top:14px"><button class="btn pri" data-tab="kalkulator">Oblicz bezpieczną wielkość pozycji →</button></div></section>
 <section class="box"><h3>Podsumowanie w prostych słowach</h3><ul class="sum">${it.summary.map(s=>`<li>${esc(s)}</li>`).join("")}</ul></section>
 <p class="note">„Szansa wzrostu” jest skalibrowana na historii: pokazuje tyle, ile podobne odczyty naprawdę znaczyły w przeszłości. Dlatego zwykle jest blisko 50% – przewidywanie jednego dnia jest bardzo trudne. Ocena „Możesz rozważyć wejście” opiera się na warunkach trendu, ryzyku i kalendarzu.</p>`}

// --- wykres ---
const RANGES=[["1D","Dziś",0],["1T","Tydzień",7],["1M","Miesiąc",30],["3M","3 mies.",91],["6M","6 mies.",182],["1R","Rok",365],["5L","5 lat",1e5]];
function tWykres(it){const L=it.levels,P=it.perf,h100=x=>x==null?null:x*100,tvt=it.today_vs_typical;
 const tiles=[["Dziś",it.change],["Tydzień",h100(P["1T"])],["Miesiąc",h100(P["1M"])],["3 mies.",h100(P["3M"])],["Od 1 stycznia",h100(P.YTD)],["Rok",h100(P["1R"])],["5 lat",h100(P["5L"])]]
  .map(([k,v])=>`<div class="tile"><b>${k}</b><span class="${sgn(v)}">${pct(v)}</span></div>`).join("");
 const rsiTxt=it.rsi>70?"przegrzany – urósł za szybko":it.rsi<30?"wyprzedany – spadł za mocno":it.rsi>=50?"lekka przewaga kupujących":"lekka przewaga sprzedających";
 const ma=v=>it.price>v?"cena nad średnią ✓":"cena pod średnią ✗";
 const kv=[["RSI (siła ruchu, 0–100)",fmt(it.rsi,0),rsiTxt],
  ["Typowy ruch dzienny",`±${fmt(L.sd60*100,1)}%`,`ok. ${fmt(it.price*L.sd60)} ${esc(it.currency)}${tvt!=null?` · dziś ruch był ${tvt<0.5?"mniejszy niż zwykle":tvt<1.5?"typowy":fmt(tvt,1)+" raza większy niż zwykle"}`:""}`],
  ["Opór (szczyt 20 sesji)",fmt(L.R),`${pct((L.R/it.price-1)*100)} od obecnej ceny`],
  ["Wsparcie (dołek 20 sesji)",fmt(L.S),`${pct((L.S/it.price-1)*100)} od obecnej ceny`],
  ["Średnia 20 dni",fmt(L.sma20),ma(L.sma20)],["Średnia 50 dni",fmt(L.sma50),ma(L.sma50)],
  ...(L.sma200!=null?[["Średnia 200 dni",fmt(L.sma200),ma(L.sma200)]]:[]),
  ["Roczny szczyt / dołek",`${fmt(L.hi52)} / ${fmt(L.lo52)}`,""]]
  .map(([k,v,h])=>`<dt>${k}</dt><dd>${v}</dd>${h?`<small>${h}</small>`:""}`).join("");
 $("tab").innerHTML=`<section class="box"><div class="seg" role="group" aria-label="Okres wykresu" style="margin-bottom:10px">${RANGES.filter(r=>r[0]!=="1D"||it.intra).map(r=>`<button data-r="${r[0]}" aria-pressed="${r[0]===range}">${r[1]}</button>`).join("")}</div>
  <div class="small mut" id="rch" style="margin-bottom:6px"></div><div class="chartwrap" id="cw"></div>
  <div class="legend" id="lg"><span><i></i>opór ${fmt(L.R)} i wsparcie ${fmt(L.S)} – szczyt i dołek z ostatnich 20 sesji</span></div></section>
 <div class="two"><section class="box"><h3>Teraz – zmiany ceny</h3><div class="tiles">${tiles}</div></section>
 <section class="box"><h3>Ważne poziomy</h3><dl class="kv">${kv}</dl></section></div>`}
function series(it){
 if(range==="1D"&&it.intra){const I=it.intra;return {xs:I.t.map(t=>t*1000),ys:I.c,base:I.prev||I.c[0],intra:true}}
 const H=it.hist,R=RANGES.find(r=>r[0]===range)||RANGES[3],last=H.dd[H.dd.length-1];let s=0;
 for(let i=0;i<H.dd.length;i++)if(H.dd[i]<=last-R[2])s=i;
 const xs=H.dd.slice(s).map(o=>dayDate(H.t0+o).getTime()),ys=H.c.slice(s);return {xs,ys,base:ys[0],long:R[2]>182}}
function drawChart(it){const wrap=$("cw");if(!wrap)return;if(range==="1D"&&!it.intra)range="1M";
 const S=series(it),w=wrap.clientWidth||600,h=w<500?220:280,pl=6,pr=62,pt=10,pb=24,iw=w-pl-pr,ih=h-pt-pb;
 const L=it.levels,showLv=!S.intra&&["1T","1M","3M"].includes(range);
 let mn=Math.min(...S.ys,S.intra?S.base:Infinity),mx=Math.max(...S.ys,S.intra?S.base:-Infinity);if(showLv){mn=Math.min(mn,L.S);mx=Math.max(mx,L.R)}
 const pad=(mx-mn)*0.06||1;mn-=pad;mx+=pad;
 const x0=S.xs[0],x1=S.xs[S.xs.length-1],X=i=>pl+(S.xs[i]-x0)/((x1-x0)||1)*iw,Y=v=>pt+(1-(v-mn)/(mx-mn))*ih;
 const last=S.ys[S.ys.length-1],up=last>=S.base,col=up?"var(--up)":"var(--down)",hex=up?"#22c55e":"#ef4444";
 const path=S.ys.map((v,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1)).join("");
 let grid="";for(let k=0;k<=4;k++){const v=mn+(mx-mn)/4*k,y=Y(v);grid+=`<line x1="${pl}" x2="${pl+iw}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="${pl+iw+6}" y="${y+4}" fill="var(--dim)" font-size="11">${fmt(v)}</text>`}
 const lab=i=>S.intra?hm(new Date(S.xs[i])):dlabel(new Date(S.xs[i]),S.long);
 const xl=[0,Math.floor((S.xs.length-1)/2),S.xs.length-1].map((i,j)=>`<text x="${X(i)}" y="${h-6}" fill="var(--dim)" font-size="11" text-anchor="${["start","middle","end"][j]}">${lab(i)}</text>`).join("");
 const lv=showLv?[L.R,L.S].map(v=>`<line x1="${pl}" x2="${pl+iw}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--mut)" stroke-dasharray="5 4" stroke-width="1.2"/>`).join(""):"";
 const baseLine=S.intra?`<line x1="${pl}" x2="${pl+iw}" y1="${Y(S.base)}" y2="${Y(S.base)}" stroke="var(--dim)" stroke-dasharray="2 4"/>`:"";
 wrap.innerHTML=`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="Wykres ceny ${esc(it.name)}">
  <defs><linearGradient id="ga" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${hex}" stop-opacity=".22"/><stop offset="1" stop-color="${hex}" stop-opacity="0"/></linearGradient></defs>
  ${grid}${lv}${baseLine}<path d="${path}L${X(S.ys.length-1)} ${pt+ih}L${X(0)} ${pt+ih}Z" fill="url(#ga)"/>
  <path d="${path}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>${xl}
  <g id="hov" style="display:none"><line id="hl" y1="${pt}" y2="${pt+ih}" stroke="var(--mut)"/><circle id="hc" r="5" fill="${col}" stroke="var(--card)" stroke-width="2"/></g>
  <rect x="${pl}" y="${pt}" width="${iw}" height="${ih}" fill="transparent" id="hit"/></svg><div class="tip" id="tip"></div>`;
 const ch=(last/S.base-1)*100;
 $("rch").innerHTML=`${S.intra?"Zmiana od wczorajszego zamknięcia":"Zmiana w wybranym okresie"}: <b class="${sgn(ch)}">${pct(ch)}</b>${S.intra?` · ostatnia cena o ${hm(new Date(x1))}`:""}`;
 $("lg").style.display=showLv?"":"none";
 const hit=$("hit"),tip=$("tip"),hov=$("hov");
 const move=e=>{const r=hit.getBoundingClientRect(),x=e.clientX-r.left;let best=0,bd=1e9;
  S.xs.forEach((_,i)=>{const d=Math.abs(X(i)-pl-x);if(d<bd){bd=d;best=i}});
  const px=X(best),py=Y(S.ys[best]);hov.style.display="";$("hl").setAttribute("x1",px);$("hl").setAttribute("x2",px);$("hc").setAttribute("cx",px);$("hc").setAttribute("cy",py);
  const c2=(S.ys[best]/S.base-1)*100;
  tip.innerHTML=`${S.intra?hm(new Date(S.xs[best])):dlabel(new Date(S.xs[best]),true)}<br><b>${fmt(S.ys[best])} ${esc(it.currency)}</b> <span class="${sgn(c2)}">${pct(c2)}</span>`;
  tip.style.display="block";const tw=tip.offsetWidth;tip.style.left=Math.min(Math.max(px-tw/2,0),w-tw)+"px";tip.style.top=Math.max(py-58,0)+"px"};
 hit.addEventListener("pointermove",move);hit.addEventListener("pointerdown",move);
 hit.addEventListener("pointerleave",()=>{hov.style.display="none";tip.style.display="none"})}

// --- kalkulator ryzyka ---
const calcState={};
function calcDefaults(it,dir){const a=it.levels.atr,p=it.price,r=x=>+x.toFixed(dec(p));
 return {dir,entry:r(p),stop:r(dir==="long"?p-2*a:p+2*a),target:r(dir==="long"?p+3*a:p-3*a),
  lev:it.cfd.lev,spread:it.cfd.spread,comm:settings.mode==="cfd"?0:settings.comm||0.39,swap:settings.swap,days:settings.days}}
function tKalk(it){const r=it.risk,c=calcState[it.symbol]||(calcState[it.symbol]=calcDefaults(it,"long"));
 $("tab").innerHTML=`<section class="box"><h3>Ryzyko w liczbach</h3>
 <div class="tiles">
  <div class="tile"><b>Poziom ryzyka</b><span class="r${r.level}">${esc(r.label)}</span></div>
  <div class="tile"><b>Zmienność roczna</b><span>${fmt(r.ann*100,0)}%</span></div>
  <div class="tile"><b>Typowy ruch dzienny</b><span>±${fmt(r.sd*100,1)}%</span></div>
  <div class="tile"><b>Najgorszy dzień w roku</b><span class="down">${pct(r.worst*100)}</span></div>
  <div class="tile"><b>Największy spadek od szczytu</b><span class="down">${pct(r.mdd*100)}</span></div>
  <div class="tile"><b>Raz na 20 dni strata ponad</b><span class="down">${pct(r.var95*100)}</span></div>
  <div class="tile"><b>Największy skok między sesjami</b><span>${fmt(r.gap_max*100,1)}%</span></div></div>
 <ul class="sum" style="margin-top:12px">${r.why.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></section>
 <section class="box"><h3>Kalkulator pozycji – ile kupić, żeby nie stracić za dużo</h3>
 <p class="note" style="margin-top:-4px">Wpisz, ile masz na koncie i ile procent możesz stracić na jednej transakcji. Kalkulator policzy wielkość pozycji, koszty i oceni transakcję. Kapitał i ryzyko zapamiętujemy w tej przeglądarce.</p>
 <div class="form">
  <label>Kapitał na koncie (zł)<input type="number" inputmode="decimal" min="0" step="100" id="k_cap" value="${settings.capital}"></label>
  <label>Ryzyko na transakcję (%)<input type="number" inputmode="decimal" min="0.1" max="10" step="0.1" id="k_risk" value="${settings.risk}"></label>
  <label>Sposób handlu<select id="k_mode"><option value="cfd"${settings.mode==="cfd"?" selected":""}>CFD (z dźwignią)</option><option value="akcje"${settings.mode==="akcje"?" selected":""}>Zakup bez dźwigni</option></select></label>
  <label>Kierunek<select id="k_dir"><option value="long"${c.dir==="long"?" selected":""}>Kupno – zarabiam na wzroście</option><option value="short"${c.dir==="short"?" selected":""}>Sprzedaż – zarabiam na spadku</option></select></label>
  <label>Cena wejścia (${esc(it.currency)})<input type="number" inputmode="decimal" step="any" id="k_entry" value="${c.entry}"></label>
  <label>Stop loss (${esc(it.currency)})<input type="number" inputmode="decimal" step="any" id="k_stop" value="${c.stop}"></label>
  <label>Cel / take profit (${esc(it.currency)})<input type="number" inputmode="decimal" step="any" id="k_target" value="${c.target}"></label>
  <label class="full"><span class="row"><button class="btn sm" id="k_reset" type="button">Ustaw sugerowane poziomy (2×ATR stop, 3×ATR cel)</button></span></label>
 </div>
 <details style="margin-top:10px"><summary class="small">Koszty i dźwignia (zaawansowane)</summary><div class="form" style="margin-top:10px">
  <label>Dźwignia (CFD)<input type="number" min="1" max="30" step="1" id="k_lev" value="${c.lev}"></label>
  <label>Spread (% ceny)<input type="number" min="0" step="0.01" id="k_spread" value="${c.spread}"></label>
  <label>Prowizja (% za stronę)<input type="number" min="0" step="0.01" id="k_comm" value="${c.comm}"></label>
  <label>Koszt nocny CFD (% rocznie)<input type="number" min="0" step="0.5" id="k_swap" value="${c.swap}"></label>
  <label>Ile dni trzymasz pozycję<input type="number" min="0" step="1" id="k_days" value="${c.days}"></label></div>
  <p class="note">Domyślna dźwignia to limit ESMA dla klientów detalicznych (akcje 1:5, złoto i główne indeksy 1:20, inne surowce 1:10, krypto 1:2). Spread to typowa różnica cen kupna i sprzedaży – sprawdź ją u swojego brokera.</p></details>
 <div class="res" id="k_out"></div></section>`;
 ["k_cap","k_risk","k_mode","k_dir","k_entry","k_stop","k_target","k_lev","k_spread","k_comm","k_swap","k_days"].forEach(id=>$(id).addEventListener("input",()=>calcRun(it,id)));
 $("k_reset").onclick=()=>{const d=calcDefaults(it,$("k_dir").value);["entry","stop","target"].forEach(k=>$("k_"+k).value=d[k]);calcRun(it)};
 calcRun(it)}
function calcRun(it,changed){
 const v=id=>parseFloat(String($(id).value).replace(",","."));
 if(changed==="k_dir"){const d=calcDefaults(it,$("k_dir").value);["entry","stop","target"].forEach(k=>$("k_"+k).value=d[k])}
 if(changed==="k_mode"){$("k_comm").value=$("k_mode").value==="cfd"?0:0.39}
 settings.capital=v("k_cap")||0;settings.risk=v("k_risk")||0;settings.mode=$("k_mode").value;settings.swap=v("k_swap")||0;settings.days=v("k_days")||0;if(settings.mode!=="cfd")settings.comm=v("k_comm");saveSettings();
 const c=calcState[it.symbol]={dir:$("k_dir").value,entry:v("k_entry"),stop:v("k_stop"),target:v("k_target"),lev:v("k_lev")||1,spread:v("k_spread")||0,comm:v("k_comm")||0,swap:v("k_swap")||0,days:v("k_days")||0};
 const out=$("k_out"),cfd=settings.mode==="cfd",long=c.dir==="long",fx=D.fx[it.currency]||1,cur=esc(it.currency);
 const errs=[];
 if(!(settings.capital>0))errs.push("Wpisz kapitał większy od zera.");
 if(!(settings.risk>0))errs.push("Wpisz ryzyko większe od zera (zwykle 1%).");
 if(!(c.entry>0&&c.stop>0&&c.target>0))errs.push("Uzupełnij cenę wejścia, stop loss i cel.");
 else if(long&&!(c.stop<c.entry&&c.target>c.entry))errs.push("Przy kupnie stop loss musi być poniżej ceny wejścia, a cel powyżej.");
 else if(!long&&!(c.stop>c.entry&&c.target<c.entry))errs.push("Przy sprzedaży stop loss musi być powyżej ceny wejścia, a cel poniżej.");
 if(!long&&!cfd)errs.push("Bez CFD (zwykły zakup) nie da się zarabiać na spadkach. Wybierz „Kupno” albo „CFD”.");
 if(errs.length){out.innerHTML=errs.map(e=>`<div class="err">${esc(e)}</div>`).join("");return}
 const riskPLN=settings.capital*settings.risk/100,dStop=Math.abs(c.entry-c.stop),dTgt=Math.abs(c.target-c.entry);
 const costPU=(c.entry*c.spread/100+c.entry*c.comm/100*2+(cfd?c.entry*c.swap/100/365*c.days:0))*fx;
 const lev=cfd?Math.max(1,c.lev):1,maxValue=settings.capital*lev;
 const step=it.cfd.unit==="akcji"?1:it.cfd.unit==="BTC"?0.0001:0.01;
 let units=Math.floor(riskPLN/(dStop*fx+costPU)/step)*step,capped=false;
 if(units*c.entry*fx>maxValue){units=Math.floor(maxValue/(c.entry*fx)/step)*step;capped=true}
 units=+units.toFixed(4);
 const value=units*c.entry*fx,margin=value/lev,loss=units*(dStop*fx+costPU),gain=units*(dTgt*fx-costPU),cost=units*costPU;
 const rr=dTgt/dStop,beWin=1/(1+rr),pT=dStop/(dStop+dTgt),ev=pT*gain-(1-pT)*loss;
 const minU=it.cfd.lot&&cfd?it.cfd.lot*0.01:step,minRisk=minU*(dStop*fx+costPU)/settings.capital*100;
 const atrN=dStop/it.levels.atr,gapLoss=value*it.risk.gap_max,riskReal=loss/settings.capital*100;
 const streak=(1-Math.pow(1-riskReal/100,10))*100;
 const soon=eventsFor(it.symbol).filter(e=>e.impact==="high"&&e.days<=2);
 const checks=[
  [riskReal<=2.05,`Ryzykujesz ${fmt(riskReal,1)}% konta (zalecane: najwyżej 1–2%)`],
  [rr>=1.5,`Zysk do ryzyka 1 : ${fmt(rr,1)} (zalecane: co najmniej 1 : 1,5)`],
  [atrN>=1,`Stop loss ${fmt(atrN,1)}×ATR od ceny – ${atrN<1?"za blisko, zwykłe wahania łatwo go wybiją":"nie za blisko"}`],
  [atrN<=4,`Stop loss nie jest zbyt daleko (${atrN>4?"ponad 4×ATR – pozycja będzie bardzo mała":"do 4×ATR"})`],
  [units>=minU,units>=minU?"Pozycja nie jest mniejsza niż minimum u brokera":`Najmniejsza pozycja u większości brokerów to ${fmt(minU,minU>=1?0:2)} ${it.cfd.unit}${it.cfd.lot&&cfd?" (0,01 lota)":""} – przy niej ryzykowałbyś ${fmt(minRisk,1)}% konta. Wybierz dalszy stop, mniejszy instrument albo poczekaj z większym kapitałem.`],
  [!soon.length,soon.length?`Ważne wydarzenie ${whenTxt(soon[0].days)}: ${soon[0].title}`:"Brak ważnych wydarzeń w ciągu 2 dni"],
  [long?it.decision.key!=="no":it.decision.key!=="go",long?(it.decision.key==="no"?"Ocena strony: „Nie wchodź teraz” – grasz pod prąd":"Ocena strony nie odradza kupna"):(it.decision.key==="go"?"Ocena strony sprzyja wzrostom – sprzedaż to gra pod prąd":"Ocena strony nie sprzeciwia się sprzedaży")]];
 const bad=checks.filter(x=>!x[0]).length;
 const vk=bad===0?"go":bad<=2?"wait":"no",vt=bad===0?"Transakcja rozsądna pod względem ryzyka":bad<=2?"Transakcja ryzykowna – popraw zaznaczone punkty":"Nie rób tej transakcji w tej formie";
 const unitTxt=`${fmt(units,step>=1?0:step>=0.01?2:4)} ${esc(it.cfd.unit)}`+(it.cfd.lot&&cfd?` (≈ ${fmt(units/it.cfd.lot,3)} lota, jeśli 1 lot = ${fmt(it.cfd.lot,0)} ${esc(it.cfd.unit)})`:"");
 out.innerHTML=`<div class="big">${long?"Kup":"Sprzedaj"} ${unitTxt}</div>
 <div class="note" style="margin:4px 0 12px">Wartość pozycji: <b>${pln(value)}</b> (${fmt(value/settings.capital*100,0)}% konta)${cfd?` · depozyt u brokera: <b>${pln(margin)}</b>`:""}${capped?" · <span class=\"midc\">ograniczone przez dostępny kapitał</span>":""}${fx!==1?` · kurs ${cur}/PLN ${fmt(fx,4)}`:""}</div>
 <div class="tiles">
  <div class="tile"><b>Strata, jeśli zadziała stop</b><span class="down">−${pln(loss)}</span></div>
  <div class="tile"><b>Zysk, jeśli dojdzie do celu</b><span class="up">+${pln(gain)}</span></div>
  <div class="tile"><b>Zysk : ryzyko</b><span>1 : ${fmt(rr,1)}</span></div>
  <div class="tile"><b>Koszty transakcji</b><span>${pln(cost)}</span></div></div>
 <div class="verdict bg-${vk} ${DEC[vk]}">${vt}</div>
 <ul class="clean checks">${checks.map(([ok,t])=>`<li><span class="ic ${ok?"up":"down"}">${ok?"✓":"✗"}</span><span>${esc(t)}</span></li>`).join("")}</ul>
 <details style="margin-top:12px" open><summary class="small">Co jeszcze warto wiedzieć o tej transakcji</summary><ul class="sum" style="margin-top:8px">
  <li>Żeby wyjść na zero przy takim stosunku zysku do ryzyka, wystarczy trafiać w <b>${fmt(beWin*100,0)}%</b> transakcji.</li>
  <li>Statystycznie (bez żadnej przewagi) cena najpierw dotknie celu w ok. <b>${fmt(pT*100,0)}%</b> przypadków, a stopu w ${fmt((1-pT)*100,0)}%. Średni wynik takiej transakcji to <b class="${sgn(ev)}">${ev>=0?"+":"−"}${pln(Math.abs(ev))}</b> – koszty sprawiają, że bez przewagi lekko się traci.</li>
  <li>Stop loss nie chroni przed skokiem ceny między sesjami. Największy taki skok w ostatnim roku (${fmt(it.risk.gap_max*100,1)}%) oznaczałby stratę ok. <b>${pln(gapLoss)}</b>${gapLoss>loss?" – więcej niż planowane ryzyko":""}.</li>
  <li>Seria 10 strat z rzędu (zdarza się nawet dobrym traderom) zmniejszyłaby konto o ok. <b>${fmt(streak,0)}%</b>.</li>
  ${cfd?`<li>Każda noc z otwartą pozycją CFD kosztuje ok. ${pln(value*c.swap/100/365)} (koszt finansowania).</li>`:""}</ul></details>
 <div class="row" style="margin-top:14px"><button class="btn pri" id="k_save_p">Zapisz jako ćwiczenie (na niby)</button><button class="btn" id="k_save_r">Zapisz jako prawdziwą transakcję</button></div>
 <p class="note">Zapisane transakcje znajdziesz w zakładce „Dziennik”. Zacznij od ćwiczeń na niby – to darmowa nauka bez ryzyka.</p>`;
 const save=paper=>{journal.unshift({id:Date.now(),sym:it.symbol,name:it.name,cur:it.currency,dir:c.dir,entry:c.entry,stop:c.stop,target:c.target,units,costPU,paper,open:true,date:new Date().toISOString(),riskPLN:loss});
  saveJournal();jMode=paper?"paper":"real";location.hash="#dziennik"};
 $("k_save_p").onclick=()=>save(true);$("k_save_r").onclick=()=>save(false)}

// --- prognoza ---
const MCOL={hist:"var(--m-hist)",season:"var(--m-season)",trend:"var(--m-trend)",vol:"var(--m-vol)",news:"var(--m-news)",ref:"var(--m-ref)"};
const MINFO={hist:"Sprawdza, co działo się w przeszłości dzień po sesji, która skończyła się tak samo jak ostatnia (wzrostem albo spadkiem).",
 season:"Sprawdza, jak często ten instrument rósł w ten sam dzień tygodnia, co najbliższa sesja.",
 trend:"Patrzy, czy cena jest nad średnimi z 20 i 50 dni (trend w górę) oraz na RSI – wskaźnik siły ruchu od 0 do 100.",
 vol:"Porównuje średni dzienny ruch z 20 dni z typowymi wahaniami. Wyraźny, równy ruch w jedną stronę przesuwa szansę w tę stronę.",
 ref:"Sprawdza, jak instrument zwykle zachowuje się względem szerszego rynku (S&P 500, WIG20, Nasdaq albo dolar) i czy ten rynek teraz rośnie.",
 news:"Ocena tonu nagłówków z Polski i ze świata. Wiadomości z oficjalnych i najbardziej wiarygodnych źródeł mają większą wagę. Nie da się jej sprawdzić na historii, więc ma mniejszą wagę."};
function tPrognoza(it){const F=it.forecast,bt=it.bt,S=it.setups;
 const rng=F.ranges.map(r=>`<tr><td>${r.label}</td><td>${fmt(r.lo)}</td><td>${fmt(r.hi)}</td><td class="mut">±${fmt((r.hi/it.price-1)*100,1)}%</td></tr>`).join("");
 const an=F.analogs.map(a=>`<li>Po ${a.label}: cena rosła w <b class="${p50(a.up*100)}">${fmt(a.up*100,0)}%</b> przypadków (na ${a.n}; zwykle ${fmt(a.base*100,0)}%), typowo o <b class="${sgn(a.med)}">${pct(a.med*100)}</b>. W połowie przypadków wynik mieścił się między ${pct(a.q1*100)} a ${pct(a.q3*100)}.</li>`).join("");
 const su=S.good&&S.all?`<li>Gdy warunki wzrostu były spełnione: po tygodniu cena była wyżej w <b>${fmt(S.good.up*100,0)}%</b> przypadków (średnio ${pct(S.good.avg*100)}, ${S.good.n} razy).</li>
  ${S.bad?`<li>Gdy warunki były niespełnione: wyżej w <b>${fmt(S.bad.up*100,0)}%</b> przypadków (średnio ${pct(S.bad.avg*100)}).</li>`:""}
  <li>Wszystkie dni razem: wyżej w ${fmt(S.all.up*100,0)}% przypadków (średnio ${pct(S.all.avg*100)}).</li>`:"";
 const meth=it.methods.map(m=>`<div class="mrow"><div class="mtop"><span><i class="sw" style="background:${MCOL[m.key]}"></i>${esc(m.name)}</span><em class="${p50(m.p)}">${m.p==null?"–":fmt(m.p,0)+"%"}</em></div>
  ${bar(m.p,MCOL[m.key])}<small>${esc(m.note)}${m.acc!=null?` · trafność w ostatnim roku: <b class="${m.acc>=52?"up":m.acc<48?"down":"flat"}">${fmt(m.acc,0)}%</b> · waga ×${fmt(m.w,1)}`:" · nie testowana na historii"}</small>
  <details><summary>Co to znaczy?</summary>${MINFO[m.key]}</details></div>`).join("");
 $("tab").innerHTML=`<div class="stats3"><div class="stat"><b>Szansa wzrostu jutro</b><strong class="${p50(it.overall)}">${fmt(it.overall,0)}%</strong></div>
  <div class="stat"><b>W ciągu tygodnia</b><strong class="${p50(it.p_week)}">${it.p_week==null?"–":fmt(it.p_week,0)+"%"}</strong></div>
  <div class="stat"><b>Trafność w roku</b><strong>${bt.overall==null?"–":fmt(bt.overall,0)+"%"}</strong></div></div>
 <div class="two"><section class="box"><h3>Typowe zakresy ceny</h3><p class="note" style="margin:0">W ok. 2 na 3 przypadkach cena powinna zmieścić się w tych przedziałach (liczone z wahań z ostatnich 60 sesji):</p>
  <table class="fc"><thead><tr><th>Kiedy</th><th>Od</th><th>Do</th><th>Ruch</th></tr></thead><tbody>${rng}</tbody></table></section>
 <section class="box"><h3>Co działo się w podobnych sytuacjach</h3>${an?`<p style="margin:0 0 6px" class="small">Sytuacja jak teraz (5 lat historii): <i>${esc(F.analog_state)}</i></p><ul class="sum">${an}</ul>`:`<p class="note">Za mało podobnych sytuacji w historii.</p>`}
  ${su?`<p style="margin:12px 0 6px" class="small">Czy warunki wzrostu z zakładki „Decyzja” działały na tym instrumencie:</p><ul class="sum">${su}</ul>`:""}</section></div>
 <section class="box"><h3>Skąd ten wynik – ${it.methods.length} niezależnych metod</h3>${meth}
  <p class="note" style="margin:10px 0 0">Surowa średnia metod: ${fmt(it.raw,0)}%. Test na historii (${bt.days} sesji): pasek trafiał kierunek w ${bt.overall==null?"–":fmt(bt.overall,0)+"%"} przypadków, a wzrostowych sesji było ${fmt(bt.up_share,0)}%. Dlatego szansa jest skalibrowana: siła sygnału ×${fmt(bt.k,2)} wokół naturalnej częstości wzrostów ${fmt(bt.base,0)}%. Wagi metod liczone są tylko z wcześniejszych danych.</p></section>
 <p class="note">To spekulacja oparta na historii, nie pewnik. Nagłe wydarzenia (wyniki spółki, decyzje banków centralnych, wojny) mogą wszystko zmienić.</p>`}

// --- newsy i wydarzenia ---
function evRow(e,linkNames){const d=new Date(e.date);
 const t=e.time?hm(d):"cały dzień",imp={high:"Wysoki wpływ",mid:"Średni wpływ",low:"Mały wpływ"}[e.impact];
 const fp=[e.forecast&&"prognoza: "+e.forecast,e.previous&&"poprzednio: "+e.previous].filter(Boolean).join(" · ");
 const chips=linkNames?`<div class="chips">${e.symbols.map((s,i)=>`<a class="chip" href="#i=${encodeURIComponent(s)}">${esc((e.names||[])[i]||s)}</a>`).join("")}</div>`:"";
 return `<div class="ev ${e.days<0?"past":""}"><div class="t">${t}</div><div><h4><span class="imp-${e.impact}" title="${imp}">●</span> ${esc(e.title)}</h4>
 <p>${[e.desc,fp,imp,e.source].filter(Boolean).map(esc).join(" · ")}</p>${chips}</div></div>`}
function tNewsy(it){const ev=eventsFor(it.symbol);
 $("tab").innerHTML=`<section class="box"><h3>Nadchodzące wydarzenia</h3>${ev.length?ev.slice(0,12).map(e=>`<div class="day" style="margin-top:8px">${whenTxt(e.days)} · ${dayTxt(e)}</div>${evRow(e,false)}`).join(""):`<p class="note">Brak zaplanowanych ważnych wydarzeń w najbliższym czasie.</p>`}</section>
 <section class="box"><h3>Wiadomości ze świata i z Polski</h3>
  <div class="seg" role="group" aria-label="Okres wiadomości" style="margin-bottom:10px"><button data-n="week" aria-pressed="${ntab==="week"}">Ostatnie 7 dni (${it.news.week.count})</button><button data-n="prev" aria-pressed="${ntab==="prev"}">Tydzień wcześniej (${it.news.prev.count})</button></div>
  <div id="nbody"></div></section>`;renderNews(it)}
function renderNews(it){const N=it.news[ntab];
 $("nbody").innerHTML=`<p style="margin:0">${esc(N.text)}</p>${N.items.length?`<ul class="clean nlist" style="margin-top:8px">${N.items.map(n=>`<li><span class="dotc" style="background:${n.tone>0.2?"var(--up)":n.tone<-0.2?"var(--down)":"var(--dim)"}" title="${n.tone>0.2?"pozytywny":n.tone<-0.2?"negatywny":"neutralny"}"></span><span><a href="${esc(safe(n.link))}" target="_blank" rel="noopener">${esc(n.title)}</a><span class="nmeta">${n.tier<=1?`<span class="tag t${n.tier}">${n.tier===0?"oficjalne":"wiarygodne"}</span>`:""}<span class="tag">${n.lang.toUpperCase()}</span>${esc(n.source)} · ${ago(n.date)}</span></span></li>`).join("")}</ul>
 <p class="note">Najpierw pokazujemy wiadomości z najbardziej wiarygodnych źródeł. Kropka: zielona = ton pozytywny, czerwona = negatywny, szara = neutralny (ocena automatyczna).</p>`:""}`}
function dayTxt(e){const d=e.time?new Date(e.date):new Date(e.date+"T12:00:00Z");return `${WDF[d.getDay()]} ${d.getDate()} ${MONF[d.getMonth()]}`}

// ---------- KALENDARZ ----------
function viewKalendarz(){
 const favSet=new Set(fav),types={all:()=>true,high:e=>e.impact==="high",makro:e=>e.kind==="makro",spolki:e=>e.kind!=="makro"};
 const list=(D.calendar||[]).filter(e=>e.days>=-1).filter(e=>calScope==="all"||e.symbols.some(s=>favSet.has(s))).filter(types[calType]);
 let html="",cur="";
 list.forEach(e=>{const k=e.days+"|"+dayTxt(e);if(k!==cur){cur=k;html+=`<div class="day">${e.days===0?"Dziś · ":e.days===1?"Jutro · ":e.days<0?"Wczoraj · ":""}${dayTxt(e)}</div>`}html+=evRow(e,true)});
 $("app").innerHTML=`<div class="upd">${updTxt()}</div><h2 style="margin:4px 0 6px">Kalendarz wydarzeń</h2>
 <p class="note" style="margin:0 0 12px">Wyniki spółek, dywidendy i ważne dane gospodarcze, które mogą mocno poruszyć ceną. Złota zasada: nie otwieraj nowej pozycji tuż przed wydarzeniem o wysokim wpływie (<span class="imp-high">●</span>). Godziny podane są w Twojej strefie czasowej.</p>
 <div class="ctl"><div class="seg" role="group" aria-label="Zakres"><button data-cs="fav" aria-pressed="${calScope==="fav"}">Moje ulubione</button><button data-cs="all" aria-pressed="${calScope==="all"}">Wszystkie</button></div>
 <div class="seg" role="group" aria-label="Rodzaj"><button data-ct="all" aria-pressed="${calType==="all"}">Wszystko</button><button data-ct="high" aria-pressed="${calType==="high"}">Tylko ważne</button><button data-ct="makro" aria-pressed="${calType==="makro"}">Gospodarka</button><button data-ct="spolki" aria-pressed="${calType==="spolki"}">Spółki</button></div></div>
 <section class="box">${html||`<p class="note">Brak wydarzeń dla wybranych filtrów.</p>`}</section>
 <p class="note">Źródła: ForexFactory (dane gospodarcze z całego świata, aktualizacja co godzinę), Nasdaq / Zacks (daty wyników spółek z USA), Bankier.pl (wyniki, dywidendy i walne zgromadzenia spółek z GPW). Dane z polskiej gospodarki (np. decyzje RPP) nie są jeszcze dostępne z darmowego, automatycznego źródła.</p>`}

// ---------- DZIENNIK ----------
function posCalc(p){const it=item(p.sym),now=it?it.price:p.entry,fx=D.fx[p.cur]||1,s=p.dir==="long"?1:-1,px=p.open?now:p.exit;
 const pnl=(s*(px-p.entry)*fx-p.costPU)*p.units,risk=Math.abs(p.entry-p.stop)*fx*p.units+p.costPU*p.units;
 return {now,pnl,R:risk?pnl/risk:0,hitStop:p.open&&(s>0?now<=p.stop:now>=p.stop),hitTgt:p.open&&(s>0?now>=p.target:now<=p.target)}}
function viewDziennik(){const all=journal.filter(p=>p.paper===(jMode==="paper")),open=all.filter(p=>p.open),closed=all.filter(p=>!p.open);
 const res=closed.map(posCalc),wins=res.filter(r=>r.pnl>0).length,sum=res.reduce((a,r)=>a+r.pnl,0),avgR=res.length?res.reduce((a,r)=>a+r.R,0)/res.length:0;
 const today=new Date().toDateString(),todayLoss=closed.filter(p=>new Date(p.closed).toDateString()===today).map(posCalc).reduce((a,r)=>a+r.pnl,0);
 const lossLimit=settings.capital*0.03;
 const pos=p=>{const r=posCalc(p),it=item(p.sym),cur=esc(p.cur);
  return `<div class="pos"><header><b>${esc(p.name)} · ${p.dir==="long"?"kupno":"sprzedaż"} ${fmt(p.units,p.units%1?2:0)}</b><span class="${sgn(r.pnl)}"><b>${r.pnl>=0?"+":"−"}${pln(Math.abs(r.pnl))}</b> (${r.R>=0?"+":"−"}${fmt(Math.abs(r.R),1)} R)</span></header>
  <dl class="kv"><dt>Wejście</dt><dd>${fmt(p.entry)} ${cur} · ${new Date(p.date).toLocaleDateString("pl-PL")}</dd><dt>Stop / cel</dt><dd>${fmt(p.stop)} / ${fmt(p.target)}</dd>
  <dt>${p.open?"Cena teraz":"Wyjście"}</dt><dd>${fmt(p.open?r.now:p.exit)} ${cur}</dd></dl>
  ${r.hitStop?`<div class="alert red" style="margin:8px 0 0">Cena doszła do stop lossa – zgodnie z planem zamknij pozycję.</div>`:r.hitTgt?`<div class="alert blue" style="margin:8px 0 0">Cena doszła do celu – rozważ zamknięcie i realizację zysku.</div>`:""}
  <div class="row" style="margin-top:8px">${p.open?`<button class="btn sm" data-close="${p.id}">Zamknij pozycję</button>`:""}${it?`<a class="btn sm" style="text-decoration:none" href="#i=${encodeURIComponent(p.sym)}">Analiza</a>`:""}<button class="btn sm" data-del="${p.id}">Usuń</button></div></div>`};
 $("app").innerHTML=`<div class="upd">${updTxt()}</div><h2 style="margin:4px 0 6px">Dziennik transakcji</h2>
 <p class="note" style="margin:0 0 12px">Zapisuj każdą transakcję – to najszybszy sposób, żeby nauczyć się, co Ci wychodzi. Transakcje dodajesz w zakładce „Kalkulator ryzyka” przy instrumencie. Dane są zapisane tylko w tej przeglądarce.</p>
 <div class="ctl"><div class="seg" role="group" aria-label="Rodzaj"><button data-jm="paper" aria-pressed="${jMode==="paper"}">Ćwiczenia (na niby)</button><button data-jm="real" aria-pressed="${jMode==="real"}">Prawdziwe</button></div></div>
 ${todayLoss<-lossLimit?`<div class="alert red"><b>Stop na dziś.</b> Dzisiejsza strata (${pln(todayLoss)}) przekroczyła 3% konta. Zawodowi traderzy w takiej sytuacji kończą handel do jutra.</div>`:""}
 <div class="tiles" style="margin-bottom:12px"><div class="tile"><b>Zamknięte</b><span>${closed.length}</span></div><div class="tile"><b>Trafione</b><span>${closed.length?fmt(wins/closed.length*100,0)+"%":"–"}</span></div>
  <div class="tile"><b>Średnio (R)</b><span class="${sgn(avgR)}">${closed.length?fmt(avgR,2):"–"}</span></div><div class="tile"><b>Wynik</b><span class="${sgn(sum)}">${closed.length?(sum>=0?"+":"−")+pln(Math.abs(sum)):"–"}</span></div></div>
 ${closed.length>=5?`<p class="note">${avgR>0?"Średnio zarabiasz więcej, niż ryzykujesz – tak trzymaj i pilnuj stop lossów.":"Średnio tracisz. Sprawdź, czy trzymasz się stop lossów i czy nie wchodzisz przed ważnymi wydarzeniami. Ćwicz dalej na niby."} 1 R = kwota, którą ryzykowałeś w transakcji.</p>`:""}
 <section class="box"><h3>Otwarte pozycje (${open.length})</h3>${open.length?open.map(pos).join(""):`<p class="note">Brak otwartych pozycji. Wybierz instrument w zakładce „Rynki” → „Kalkulator ryzyka” → „Zapisz”.</p>`}</section>
 <section class="box"><h3>Zamknięte (${closed.length})</h3>${closed.length?closed.map(pos).join(""):`<p class="note">Jeszcze nic nie zamknięto.</p>`}</section>
 <div class="row"><button class="btn sm" id="j_exp">Pobierz kopię dziennika</button><label class="btn sm" style="cursor:pointer">Wczytaj kopię<input type="file" id="j_imp" accept="application/json" hidden></label></div>`;
 $("j_exp").onclick=()=>{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(journal,null,1)],{type:"application/json"}));a.download="dziennik-centrum-rynku.json";a.click()};
 $("j_imp").onchange=e=>{const f=e.target.files[0];if(!f)return;f.text().then(t=>{try{const j=JSON.parse(t);if(Array.isArray(j)){journal=j;saveJournal();viewDziennik()}}catch(_){alert("To nie jest poprawny plik dziennika.")}})}}

// ---------- PORADNIK ----------
function viewPoradnik(){
 $("app").innerHTML=`<div class="upd">${updTxt()}</div><h2 style="margin:4px 0 12px">Poradnik</h2>
 <section class="box guide"><h3>Jak podjąć decyzję – krok po kroku</h3><ol>
  <li><b>Sprawdź otoczenie.</b> W zakładce „Rynki” zobacz, które giełdy są otwarte i czy VIX (indeks strachu) jest niski.</li>
  <li><b>Sprawdź kalendarz.</b> Jeśli w ciągu 1–2 dni są wyniki spółki lub ważne dane (●), poczekaj na nie.</li>
  <li><b>Przeczytaj „Decyzję”.</b> Kliknij instrument. Zielone „Możesz rozważyć wejście” to sygnał do przemyślenia, nie rozkaz.</li>
  <li><b>Policz pozycję.</b> W „Kalkulatorze ryzyka” ustaw stop loss i sprawdź, ile kupić. Ryzykuj 1% konta, najwyżej 2%.</li>
  <li><b>Najpierw ćwicz.</b> Zapisuj transakcje „na niby” przez kilka tygodni. Przejdź na prawdziwe pieniądze dopiero, gdy dziennik pokazuje dodatni wynik.</li>
  <li><b>Trzymaj się planu.</b> Gdy cena dojdzie do stop lossa – wychodzisz. Nie przesuwaj stopu niżej i nie dokupuj, gdy tracisz.</li></ol></section>
 <section class="box"><h3>Zasady bezpiecznego handlu</h3><div class="rules">
  <div class="rule"><b>1% na transakcję</b>Nawet 10 strat z rzędu zabierze wtedy tylko ok. 10% konta.</div>
  <div class="rule"><b>Zawsze stop loss</b>Ustaw go od razu przy otwarciu pozycji, nie „później”.</div>
  <div class="rule"><b>Zysk co najmniej 1,5× ryzyko</b>Wtedy wystarczy trafiać w 40% transakcji, żeby zarabiać.</div>
  <div class="rule"><b>Limit dzienny 3%</b>Po stracie 3% konta w jeden dzień – koniec handlu do jutra.</div>
  <div class="rule"><b>Uważaj na dźwignię</b>Dźwignia 1:10 oznacza, że ruch ceny o 10% może zabrać cały depozyt. Większość klientów detalicznych na CFD traci pieniądze – brokerzy muszą to podawać.</div>
  <div class="rule"><b>Koszty się sumują</b>Spread, prowizje i opłaty za noc na CFD zjadają zysk przy częstym handlu.</div>
  <div class="rule"><b>Nie graj przed wynikami</b>Wyniki spółki potrafią przesunąć cenę o 10% w minutę – stop loss tego nie zatrzyma.</div>
  <div class="rule"><b>Emocje to wróg</b>Po serii strat zrób przerwę. Nie próbuj „odegrać się” większą pozycją.</div></div></section>
 <section class="box"><h3>Źródła informacji – którym ufać</h3>
  <p class="note" style="margin-top:-4px">Strona opiera większość informacji na najbardziej wiarygodnych źródłach. Wiadomości z nich mają większą wagę w ocenie nastroju i są pokazywane jako pierwsze.</p>
  <table class="fc src"><thead><tr><th>Poziom</th><th>Źródła</th></tr></thead><tbody>
  <tr><td><span class="tag t0">oficjalne</span></td><td>Komunikaty spółek ESPI/EBI (GPW), banki centralne (Fed, EBC, NBP), raporty spółek w USA (SEC). To źródło faktów – media tylko je opisują.</td></tr>
  <tr><td><span class="tag t1">wiarygodne</span></td><td>Świat: Reuters, Bloomberg, CNBC, Wall Street Journal, Financial Times, MarketWatch, Associated Press, Yahoo Finance, Morningstar, Kitco (metale), CoinDesk (krypto). Polska: PAP Biznes, Bankier.pl, Parkiet, Puls Biznesu, Rzeczpospolita, ISBnews, StockWatch.pl.</td></tr>
  <tr><td><span class="tag">uzupełniające</span></td><td>Investing.com, Business Insider, Forbes, Barchart, Benzinga, Seeking Alpha, money.pl, Interia Biznes, wnp.pl i podobne – mniejsza waga.</td></tr>
  <tr><td><span class="tag">pozostałe</span></td><td>Najmniejsza waga. Fora i media społecznościowe nie są używane.</td></tr></tbody></table>
  <p class="small" style="margin:8px 0 4px"><b>Skąd strona bierze dane:</b></p><ul class="sum small">
  <li>Ceny: Yahoo Finance (do 15 min opóźnienia; złoto, srebro i ropa przez kontrakty terminowe, WIG20 przez fundusz ETF).</li>
  <li>Kalendarz: ForexFactory (dane gospodarcze), Nasdaq / Zacks (wyniki spółek z USA), Bankier.pl (spółki z GPW).</li>
  <li>Wiadomości: Google News (wybieramy według listy powyżej), Bankier.pl i komunikaty ESPI.</li></ul>
  <p class="note">Ważną informację zawsze sprawdź w źródle pierwotnym (komunikat spółki, komunikat banku centralnego), zanim podejmiesz decyzję.</p></section>
 <section class="box"><h3>Powiadomienia na telefon (opcjonalnie)</h3><p class="small" style="margin:0">Strona może wysyłać darmowe powiadomienia, gdy zmieni się ocena instrumentu albo cena przebije opór lub wsparcie. Potrzebna jest aplikacja <b>ntfy</b> (Android/iPhone) i jednorazowe ustawienie w GitHubie – poproś Claude'a, żeby przeprowadził Cię przez to krok po kroku.</p></section>
 <section class="box"><h3>Ograniczenia strony – ważne</h3><ul class="sum small">
  <li>Przewidywanie jednego dnia jest bardzo trudne: metody trafiają w ok. 47–57% przypadków. Strona porządkuje informacje i pilnuje ryzyka, ale nie zna przyszłości.</li>
  <li>Godziny otwarcia giełd nie uwzględniają świąt.</li>
  <li>Ceny złota, srebra i ropy pochodzą z kontraktów terminowych – u brokera CFD mogą się minimalnie różnić.</li>
  <li>Podsumowania są tworzone automatycznie według reguł, a ton wiadomości oceniany jest słownikiem słów – czasem się pomyli.</li></ul></section>
 <section class="box"><details><summary><b>Słowniczek – co znaczą trudne słowa</b></summary><div class="gl">
  <div><b>Średnia z 20 / 50 / 200 dni</b> – przeciętna cena z tylu ostatnich sesji. Cena nad średnią = trend w górę.</div>
  <div><b>RSI</b> – siła ruchu od 0 do 100. Powyżej 70 „przegrzany”, poniżej 30 „wyprzedany”.</div>
  <div><b>Opór / wsparcie</b> – poziomy, przy których cena ostatnio przestawała rosnąć / spadać (tu: szczyt i dołek z 20 sesji).</div>
  <div><b>Wybicie</b> – zamknięcie dnia powyżej oporu. Często oznacza dalsze wzrosty (ale nie zawsze).</div>
  <div><b>Stop loss</b> – zlecenie, które samo zamyka pozycję przy ustalonej stracie.</div>
  <div><b>Take profit (cel)</b> – zlecenie, które samo zamyka pozycję z zyskiem.</div>
  <div><b>ATR / typowy ruch</b> – o ile zwykle zmienia się cena w ciągu dnia. Stop bliżej niż 1 ATR łatwo „wybija” zwykły szum.</div>
  <div><b>R</b> – kwota, którą ryzykujesz w transakcji. Wynik +2 R = zarobiłeś dwa razy tyle, ile ryzykowałeś.</div>
  <div><b>Dźwignia</b> – pozwala otworzyć pozycję większą niż depozyt. Zwiększa zyski i straty.</div>
  <div><b>Depozyt</b> – część pieniędzy, którą broker blokuje na czas trwania pozycji CFD.</div>
  <div><b>Spread</b> – różnica między ceną kupna i sprzedaży. To ukryty koszt każdej transakcji.</div>
  <div><b>Luka cenowa</b> – skok ceny między zamknięciem a otwarciem sesji. Stop loss wykona się wtedy po gorszej cenie.</div>
  <div><b>Korelacja</b> – jak bardzo dwa rynki poruszają się razem: +1 razem, −1 odwrotnie, 0 bez związku.</div>
  <div><b>Trafność / kalibracja</b> – jak często metoda miała rację w przeszłości i ile naprawdę znaczą jej wyniki.</div>
  <div><b>CFD</b> – kontrakt u brokera naśladujący cenę instrumentu. Pozwala grać na wzrost i spadek, z dźwignią.</div></div></details></section>`}

// ---------- nawigacja ----------
function route(){if(!D)return;const h=decodeURIComponent(location.hash.slice(1));
 let v="rynki";const m=h.match(/^i=([^/]+)(?:\/(\w+))?$/);
 if(m)v="detail";else if(["kalendarz","dziennik","poradnik"].includes(h))v=h;
 document.querySelectorAll(".nav a").forEach(a=>a.setAttribute("aria-current",a.dataset.v===(v==="detail"?"rynki":v)?"page":"false"));
 if(v==="detail")viewDetail(m[1],m[2]);else({rynki:viewRynki,kalendarz:viewKalendarz,dziennik:viewDziennik,poradnik:viewPoradnik})[v]();
 if(!m||!m[2])window.scrollTo(0,0)}
document.addEventListener("click",e=>{const t=e.target;
 const h=t.closest("[data-heart]");if(h){e.stopPropagation();const s=h.dataset.heart;fav=fav.includes(s)?fav.filter(x=>x!==s):[...fav,s];store.set("fav",fav);
  document.querySelectorAll(`[data-heart="${CSS.escape(s)}"]`).forEach(b=>{const f=fav.includes(s);b.setAttribute("aria-pressed",f);b.textContent=f?"♥":"♡"});if($("out"))renderList();return}
 const o=t.closest("[data-open]");if(o){location.hash="i="+encodeURIComponent(o.dataset.open);return}
 if(t.closest("[data-back]")){history.length>1?history.back():(location.hash="#rynki");return}
 const tb=t.closest("[data-tab]");if(tb){const m=decodeURIComponent(location.hash.slice(1)).match(/^i=([^/]+)/);if(m){history.replaceState(null,"","#i="+encodeURIComponent(m[1])+"/"+tb.dataset.tab);route();window.scrollTo(0,$("tab").offsetTop-120)}return}
 const r=t.closest("[data-r]");if(r){range=r.dataset.r;store.set("range2",range);document.querySelectorAll("[data-r]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.r===range));drawChart(item(curSym()));return}
 const n=t.closest("[data-n]");if(n){ntab=n.dataset.n;document.querySelectorAll("[data-n]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.n===ntab));renderNews(item(curSym()));return}
 const l=t.closest("[data-list]");if(l){listTab=l.dataset.list;document.querySelectorAll("[data-list]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.list===listTab));renderList();return}
 const cs=t.closest("[data-cs]");if(cs){calScope=cs.dataset.cs;viewKalendarz();return}
 const ct=t.closest("[data-ct]");if(ct){calType=ct.dataset.ct;viewKalendarz();return}
 const jm=t.closest("[data-jm]");if(jm){jMode=jm.dataset.jm;viewDziennik();return}
 const cl=t.closest("[data-close]");if(cl){const p=journal.find(x=>x.id==cl.dataset.close),it=item(p.sym);
  const v=prompt("Po jakiej cenie zamykasz pozycję?",it?it.price:p.entry);if(v==null)return;const x=parseFloat(String(v).replace(",","."));
  if(!(x>0)){alert("Wpisz poprawną cenę.");return}p.open=false;p.exit=x;p.closed=new Date().toISOString();saveJournal();viewDziennik();return}
 const dl=t.closest("[data-del]");if(dl){if(confirm("Usunąć tę transakcję z dziennika?")){journal=journal.filter(x=>x.id!=dl.dataset.del);saveJournal();viewDziennik()}}});
document.addEventListener("keydown",e=>{const o=e.target.closest&&e.target.closest("[data-open]");if(o&&(e.key==="Enter"||e.key===" ")&&!e.target.closest("[data-heart]")){e.preventDefault();o.click()}});
const curSym=()=>(decodeURIComponent(location.hash.slice(1)).match(/^i=([^/]+)/)||[])[1];
window.addEventListener("hashchange",route);
let rt;window.addEventListener("resize",()=>{clearTimeout(rt);rt=setTimeout(()=>{const it=curSym()&&item(curSym());if(it&&$("cw"))drawChart(it)},150)});
fetch("data.json?"+Date.now()).then(r=>r.json()).then(d=>{D=d;if(!location.hash)history.replaceState(null,"","#rynki");route()})
 .catch(()=>{$("app").innerHTML='<div class="msg" style="margin-top:20px">Nie udało się wczytać danych (data.json). Spróbuj odświeżyć stronę za chwilę.</div>'});
