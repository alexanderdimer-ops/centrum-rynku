"use strict";
/* Centrum rynku – cała logika strony. Dane pochodzą z data.json (tworzy go fetch_data.py). */

// ---------- pamięć przeglądarki ----------
const store={get(k,d){try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v)}catch(e){return d}},
 set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
const DEF_FAV=["TPE.WA","CDR.WA","BTC-USD","SI=F","GC=F","AAPL"];
let D=null,fav=store.get("fav",DEF_FAV),listTab="fav",range=store.get("range2","3M"),ntab="week";
let calScope="fav",calType="all",jMode="paper",chartMode=store.get("chartMode","cnd"),selCandle=null;
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
 <header><div><h2>${esc(it.name)}</h2><span class="sub">${esc(it.symbol)} · ${st.open?"otwarty":"zamknięty"}${it.stale?' · <span class="midc">dane z poprzedniej aktualizacji</span>':""}</span></div>
 <div class="px">${fmt(it.price)} ${esc(it.currency)}<span class="chg ${sgn(it.change)}">${pct(it.change,2)}</span></div>${heart(it)}</header>
 ${spark(it)}
 <div class="cfoot"><span class="dec c-${FK[(it.final||{}).key]||it.decision.key} bg-${FK[(it.final||{}).key]||it.decision.key}">${esc((it.final||it.decision).title)}</span>${riskChip(it.risk)}${nextEventChip(it.symbol)}</div></article>`}
function viewRynki(){
 const k=["gpw","us","fut","crypto"].map(k=>{const s=status(k);return `<span class="chip dot ${s.open?"up":"flat"}" title="${esc(s.text)}">${SESS[k].name}: ${s.open?"otwarte":"zamknięte"}</span>`}).join("");
 $("app").innerHTML=`<div class="upd">${updTxt()}</div>
 <div class="status">${k}</div>
 <div class="pulse" aria-label="Puls rynku">${(D.pulse||[]).map(p=>`<div class="pc"><b>${esc(p.name)}</b><strong>${fmt(p.price)}</strong><span class="${sgn(p.change)}">${pct(p.change,2)}</span><small>${esc(p.note)}</small></div>`).join("")}</div>
 <div class="ctl"><div class="seg" role="group" aria-label="Lista"><button data-list="fav" aria-pressed="${listTab==="fav"}">Ulubione</button><button data-list="all" aria-pressed="${listTab==="all"}">Wszystkie</button></div>
 <input id="q" type="search" placeholder="Szukaj na liście" aria-label="Szukaj na liście"></div>
 <div id="out" class="grid"></div>
 <section class="box" style="margin-top:16px"><h3>Dodaj dowolny instrument</h3>
 <p class="note" style="margin-top:-4px">Wpisz nazwę lub symbol – akcję z dowolnej giełdy, kryptowalutę, surowiec albo indeks (np. Sony, KGHM, Ethereum, platyna). Otworzy się GitHub: kliknij tam zielony przycisk „Create”. Po 3–5 minutach instrument pojawi się na liście z pełną analizą. Usunąć go możesz w jego widoku (zakładka Decyzja, na dole).</p>
 <div class="ctl" style="margin:0"><input id="addQ" placeholder="np. Sony albo KGH.WA" aria-label="Nazwa lub symbol do dodania"><button class="btn pri" id="addBtn">Dodaj</button></div><div id="pend">${pendingHtml()}</div></section>`;
 $("addQ").addEventListener("keydown",e=>{if(e.key==="Enter")$("addBtn").click()});
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
 if(tab!=="decyzja")$("tab").insertAdjacentHTML("beforeend",finalLine(it));
 if(tab==="wykres")drawChart(it)}

function tDecyzja(it){const d=it.decision,pl=it.plan,r=it.risk;
 const ev=eventsFor(it.symbol).filter(e=>e.days<=7&&e.impact!=="low");
 const extra=r.why.slice(1);
 $("tab").innerHTML=`${finalBox(it)}<p class="small mut" style="margin:14px 0 6px">Ocena techniczna (wykres):</p><div class="hero bg-${d.key}"><h3 class="${DEC[d.key]}" style="font-size:18px">${esc(d.title)}</h3><ul>${d.reasons.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>
 <div class="stats4">
  <div class="stat"><b>Szansa wzrostu w ciągu ~4 godzin</b><strong class="${p50(it.hours&&it.hours.p)}">${it.hours?fmt(it.hours.p,0)+"%":"–"}</strong></div>
  <div class="stat"><b>Szansa wzrostu jutro</b><strong class="${p50(it.overall)}">${fmt(it.overall,0)}%</strong></div>
  <div class="stat"><b>Szansa wzrostu w tydzień</b><strong class="${p50(it.p_week)}">${it.p_week==null?"–":fmt(it.p_week,0)+"%"}</strong></div>
  <div class="stat"><b>Ryzyko</b><strong class="r${r.level}">${esc(r.label)}</strong></div></div>
 ${potBox(it)}
 ${ev.length||extra.length?`<div class="alert ${ev.some(e=>e.days<=1&&e.impact==="high")?"red":""}"><b>Zwróć uwagę</b><ul>${ev.map(e=>`<li>${esc(e.title)} – ${whenTxt(e.days)}${e.time?" o "+hm(new Date(e.date)):""}</li>`).join("")}${extra.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>`:""}
 <section class="box plan"><h3>Co zrobić – krok po kroku</h3><p>${esc(pl.head)}</p><ol>${pl.steps.map(s=>`<li>${esc(s)}</li>`).join("")}</ol>
  <div class="alert" style="margin:12px 0 0">${esc(pl.warn)}</div>
  <ul class="clean checks" aria-label="Warunki wzrostu">${pl.checks.map(c=>`<li><span class="ic ${c.ok?"up":"down"}">${c.ok?"✓":"✗"}</span><span>${esc(c.text)}</span></li>`).join("")}</ul>
  <div class="row" style="margin-top:14px"><button class="btn pri" data-tab="kalkulator">Oblicz bezpieczną wielkość pozycji →</button></div></section>
 <section class="box"><h3>Podsumowanie w prostych słowach</h3><ul class="sum">${it.summary.map(s=>`<li>${esc(s)}</li>`).join("")}</ul></section>
 ${testBox(it)}
 <p class="note">„Szansa wzrostu” jest liczona z historii: pokazuje tyle, ile podobne odczyty naprawdę znaczyły w przeszłości. Dlatego zwykle jest blisko 50% – przewidywanie jednego dnia jest bardzo trudne. Ocena „Możesz rozważyć wejście” opiera się na warunkach trendu, ryzyku i kalendarzu.</p>
 <p style="margin-top:18px"><button class="btn sm" data-remove>Usuń ${esc(it.name)} z listy</button></p>`}

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
 $("tab").innerHTML=`${storyBox(it)}<section class="box"><div class="seg" role="group" aria-label="Okres wykresu" style="margin-bottom:10px">${RANGES.filter(r=>r[0]!=="1D"||it.intra).map(r=>`<button data-r="${r[0]}" aria-pressed="${r[0]===range}">${r[1]}</button>`).join("")}</div>
  <div class="row" style="justify-content:space-between;margin-bottom:6px"><div class="small mut" id="rch"></div>
  <div class="seg" role="group" aria-label="Rodzaj wykresu"><button data-cm="line" aria-pressed="${chartMode==="line"}">Linia</button><button data-cm="cnd" aria-pressed="${chartMode==="cnd"}">Świece</button></div><button class="btn sm" data-annon aria-pressed="${annOn}">Objaśnienia na wykresie</button></div>
  <div class="chartwrap" id="cw"></div>
  <div class="legend" id="lg"><span><i></i>opór ${fmt(L.R)} i wsparcie ${fmt(L.S)} – szczyt i dołek z ostatnich 20 sesji</span></div>
  <div id="annleg" class="cfoot" style="margin-top:8px"></div><div id="cinfo"></div></section>
 <section class="box" id="patbox"></section>
 <div class="two"><section class="box"><h3>Teraz – zmiany ceny</h3><div class="tiles">${tiles}</div></section>
 <section class="box"><h3>Ważne poziomy</h3><dl class="kv">${kv}</dl></section></div>`}
function series(it){
 if(range==="1D"&&it.intra){const I=it.intra;return {xs:I.t.map(t=>t*1000),ys:I.c,base:I.prev||I.c[0],intra:true}}
 const H=it.hist,R=RANGES.find(r=>r[0]===range)||RANGES[3],last=H.dd[H.dd.length-1];let s=0;
 for(let i=0;i<H.dd.length;i++)if(H.dd[i]<=last-R[2])s=i;
 const xs=H.dd.slice(s).map(o=>dayDate(H.t0+o).getTime()),ys=H.c.slice(s);return {xs,ys,base:ys[0],long:R[2]>182}}
function drawChart(it){const wrap=$("cw");if(!wrap)return;if(range==="1D"&&!it.intra)range="1M";if($("annleg"))$("annleg").innerHTML="";
 if(chartMode==="cnd"&&range!=="5L")return drawCandles(it);
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

function candleData(it){
 if(range==="1D"&&it.intra&&it.intra.cnd){const C=it.intra.cnd;return {t:C.t.map(x=>x*1000),o:C.o,h:C.h,l:C.l,c:C.c,intra:true,pats:[]}}
 const O=it.ohlc,R=RANGES.find(r=>r[0]===range)||RANGES[3],last=O.dd[O.dd.length-1];let s=0;
 for(let i=0;i<O.dd.length;i++)if(O.dd[i]<=last-R[2])s=i;if(range==="1T")s=Math.max(0,O.dd.length-6);
 const pats=(it.patterns||[]).filter(p=>p.i>=s).map(p=>({i:p.i-s,key:p.key}));
 return {t:O.dd.slice(s).map(o=>dayDate(it.hist.t0+o).getTime()),o:O.o.slice(s),h:O.h.slice(s),l:O.l.slice(s),c:O.c.slice(s),intra:false,pats,long:R[2]>182,s0:s}}
function drawCandles(it){const wrap=$("cw"),S=candleData(it),n=S.c.length,w=wrap.clientWidth||600,h=w<500?240:300,pl=6,pr=62,pt=14,pb=24,iw=w-pl-pr,ih=h-pt-pb;
 const L=it.levels,showLv=!S.intra&&["1T","1M","3M"].includes(range)&&!(annOn&&it.chart);
 let mn=Math.min(...S.l),mx=Math.max(...S.h);if(showLv&&!(annOn&&it.chart)){mn=Math.min(mn,L.S);mx=Math.max(mx,L.R)}const pad=(mx-mn)*0.1||1;mn-=pad;mx+=pad;
 const step=iw/n,X=i=>pl+(i+0.5)*step,Y=v=>pt+(1-(v-mn)/(mx-mn))*ih,bw=Math.max(1.5,Math.min(14,step*0.7));
 if(selCandle==null||selCandle>=n)selCandle=n-1;
 let grid="";for(let k=0;k<=4;k++){const v=mn+(mx-mn)/4*k,y=Y(v);grid+=`<line x1="${pl}" x2="${pl+iw}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="${pl+iw+6}" y="${y+4}" fill="var(--dim)" font-size="11">${fmt(v)}</text>`}
 const lv=showLv?[L.R,L.S].map(v=>`<line x1="${pl}" x2="${pl+iw}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--mut)" stroke-dasharray="5 4" stroke-width="1.2"/>`).join(""):"";
 let body="";for(let i=0;i<n;i++){const up=S.c[i]>=S.o[i],col=up?"var(--up)":"var(--down)",x=X(i),y1=Y(Math.max(S.o[i],S.c[i])),y2=Y(Math.min(S.o[i],S.c[i]));
  body+=`<line x1="${x}" x2="${x}" y1="${Y(S.h[i])}" y2="${Y(S.l[i])}" stroke="${col}" stroke-width="1"/><rect x="${x-bw/2}" y="${y1}" width="${bw}" height="${Math.max(1,y2-y1)}" fill="${col}" rx="1"/>`}
 const byI={};S.pats.filter(p=>!annOn||p.i>=n-20).forEach(p=>(byI[p.i]=byI[p.i]||[]).push(p.key));
 let marks="";Object.entries(byI).forEach(([i,keys])=>{i=+i;const d=keys.map(k=>PAT[k].d),dir=d.includes("up")&&!d.includes("down")?"up":d.includes("down")&&!d.includes("up")?"down":"neutral",x=X(i);
  marks+=dir==="up"?`<path d="M${x} ${Y(S.l[i])+6}l-4 7h8z" fill="var(--up)"/>`:dir==="down"?`<path d="M${x} ${Y(S.h[i])-6}l-4 -7h8z" fill="var(--down)"/>`:`<circle cx="${x}" cy="${Y(S.h[i])-8}" r="2.5" fill="var(--mid)"/>`});
 const lab=i=>S.intra?hm(new Date(S.t[i])):dlabel(new Date(S.t[i]),S.long);
 const xl=[0,Math.floor((n-1)/2),n-1].map((i,j)=>`<text x="${X(i)}" y="${h-6}" fill="var(--dim)" font-size="11" text-anchor="${["start","middle","end"][j]}">${lab(i)}</text>`).join("");
 const ann=annSvg(it,S,X,Y,step,pt,ih,pl,iw,S.s0||0);
 wrap.innerHTML=`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="Wykres świecowy ${esc(it.name)}">${grid}${lv}${ann}${body}${marks}
  <rect id="csel" x="${X(selCandle)-step/2}" y="${pt}" width="${step}" height="${ih}" fill="var(--ink)" opacity=".07"/>${xl}
  <rect x="${pl}" y="${pt}" width="${iw}" height="${ih}" fill="transparent" id="hit"/></svg><div class="tip" id="tip"></div>`;
 const ch=(S.c[n-1]/(S.intra&&it.intra.prev?it.intra.prev:S.o[0])-1)*100;
 $("rch").innerHTML=`${S.intra?"Świece 15-minutowe · zmiana od wczoraj":"Świece dzienne · zmiana w okresie"}: <b class="${sgn(ch)}">${pct(ch)}</b>`;
 $("lg").style.display=showLv?"":"none";
 const hit=$("hit"),tip=$("tip"),idx=e=>Math.max(0,Math.min(n-1,Math.floor((e.clientX-hit.getBoundingClientRect().left)/step)));
 hit.addEventListener("pointermove",e=>{const i=idx(e),x=X(i);tip.innerHTML=`${S.intra?hm(new Date(S.t[i])):dlabel(new Date(S.t[i]),true)}<br>O ${fmt(S.o[i])} · H ${fmt(S.h[i])}<br>L ${fmt(S.l[i])} · C <b>${fmt(S.c[i])}</b>`;
  tip.style.display="block";const tw=tip.offsetWidth;tip.style.left=Math.min(Math.max(x-tw/2,0),w-tw)+"px";tip.style.top="0px"});
 hit.addEventListener("pointerleave",()=>tip.style.display="none");
 hit.addEventListener("click",e=>{selCandle=idx(e);$("csel").setAttribute("x",X(selCandle)-step/2);candleInfo(it,S,selCandle)});
 const keys=[...new Set([...ann.matchAll(/data-ann="(\w+)"(?: data-ap="([\d.]+)")?/g)].map(m=>m[1]+"|"+(m[2]||"")))];
 $("annleg").innerHTML=keys.length?`<span class="small mut">Na wykresie:</span>`+keys.map(k=>{const [a,p]=k.split("|");return `<button class="chip" data-annk="${a}" data-ap="${p}">${ANN[a].n}${p?" "+fmt(+p):""}</button>`}).join(""):(S.intra?"":`<span class="small mut">${annOn?"Brak wyraźnych formacji w tym okresie – spróbuj dłuższego okresu (np. 6 mies.).":"Włącz „Objaśnienia na wykresie”, żeby zobaczyć poziomy i formacje."}</span>`);
 candleInfo(it,S,selCandle);patternList(it,S)}
function patInfo(it,key){const P=PAT[key],st=(it.pattern_stats||{})[key],b=it.pattern_base;
 return `<div class="pat"><b class="${DIRCLS[P.d]}">${P.n}</b> <span class="chip">${P.d==="up"?"sygnał wzrostowy":P.d==="down"?"sygnał spadkowy":"niezdecydowanie"}</span>
 <p><b>Jak wygląda:</b> ${P.what}</p><p><b>Co oznacza:</b> ${P.mean}</p><p><b>Dlaczego tak się dzieje:</b> ${P.why}</p>
 ${st?`<p class="note">Na tym instrumencie (5 lat): po tej formacji cena po 3 sesjach była wyżej w <b class="${st.up*100>b*100+3?"up":st.up*100<b*100-3?"down":"flat"}">${fmt(st.up*100,0)}%</b> przypadków (${st.n} razy; zwykle ${fmt(b*100,0)}%). ${Math.abs(st.up-b)<0.03?"Czyli tutaj nie daje wyraźnej przewagi.":st.up>b?"Tutaj zwykle działała na plus.":"Tutaj częściej poprzedzała spadki."}</p>`:""}</div>`}
function candleInfo(it,S,i){const el=$("cinfo");if(!el)return;const keys=S.pats.filter(p=>p.i===i).map(p=>p.key);
 el.innerHTML=`<div class="cbox"><p class="small" style="margin:0 0 6px"><b>Wybrana świeca: ${S.intra?hm(new Date(S.t[i])):dlabel(new Date(S.t[i]),true)}</b> · otwarcie ${fmt(S.o[i])}, najwyżej ${fmt(S.h[i])}, najniżej ${fmt(S.l[i])}, zamknięcie ${fmt(S.c[i])}</p>
 <p class="small" style="margin:0">${candleDesc(S.o[i],S.h[i],S.l[i],S.c[i])}</p>${keys.map(k=>patInfo(it,k)).join("")}
 <p class="note" style="margin:8px 0 0">Kliknij dowolną świecę, żeby zobaczyć jej opis. Trójkąt pod świecą = formacja wzrostowa, nad świecą = spadkowa, kropka = niezdecydowanie${annOn?" (przy włączonych objaśnieniach pokazujemy formacje z ostatnich 20 sesji)":""}.</p></div>`}
function patternList(it,S){const el=$("patbox");if(!el)return;
 if(S.intra){el.innerHTML=`<h3>Jak czytać świece</h3>${howTo()}`;return}
 const rec=S.pats.filter(p=>p.i>=S.c.length-20).reverse();
 el.innerHTML=`<h3>Formacje świecowe z ostatnich 20 sesji</h3>${rec.length?`<ul class="clean nlist">${rec.map(p=>`<li><span class="dotc" style="background:var(--${PAT[p.key].d==="up"?"up":PAT[p.key].d==="down"?"down":"mid"})"></span><span><button class="linkbtn" data-cpick="${p.i}">${PAT[p.key].n}</button> – ${dlabel(new Date(S.t[p.i]),false)}<span class="nmeta">${PAT[p.key].mean}</span></span></li>`).join("")}</ul>`:`<p class="note">Brak wyraźnych formacji w ostatnich 20 sesjach.</p>`}
 <details style="margin-top:10px"><summary class="small"><b>Jak czytać świece – krótka lekcja</b></summary>${howTo()}</details>`}
function howTo(){return `<div class="howto"><svg viewBox="0 0 150 120" width="150" height="120" aria-hidden="true"><line x1="40" x2="40" y1="8" y2="112" stroke="var(--up)" stroke-width="2"/><rect x="28" y="30" width="24" height="55" fill="var(--up)" rx="2"/><line x1="110" x2="110" y1="8" y2="112" stroke="var(--down)" stroke-width="2"/><rect x="98" y="30" width="24" height="55" fill="var(--down)" rx="2"/>
 <text x="56" y="14" fill="var(--mut)" font-size="9">najwyżej</text><text x="56" y="112" fill="var(--mut)" font-size="9">najniżej</text><text x="56" y="34" fill="var(--mut)" font-size="9">zamkn.</text><text x="56" y="86" fill="var(--mut)" font-size="9">otwarcie</text></svg>
 <ul class="sum small"><li>Każda świeca to jedna sesja (lub 15 minut na wykresie „Dziś”).</li><li><b>Korpus</b> (gruba część) – od ceny otwarcia do zamknięcia. <span class="up">Zielony</span>: zamknięcie wyżej niż otwarcie. <span class="down">Czerwony</span>: niżej.</li>
 <li><b>Cienie</b> (cienkie kreski) – najwyższa i najniższa cena w trakcie sesji. Długi cień pokazuje, że cena tam była, ale ją odepchnięto.</li><li>Pojedyncza świeca mówi niewiele – liczy się miejsce, w którym się pojawia (po wzrostach czy po spadkach) i potwierdzenie następnego dnia.</li>
 <li>Strona sama wyszukuje typowe formacje i pokazuje, jak działały na danym instrumencie w ostatnich 5 latach.</li></ul></div>`}

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
 const Hh=it.hours,Pp=it.potential;
 $("tab").innerHTML=`<div class="stats4"><div class="stat"><b>W ciągu ~4 godzin</b><strong class="${p50(Hh&&Hh.p)}">${Hh?fmt(Hh.p,0)+"%":"–"}</strong></div><div class="stat"><b>Szansa wzrostu jutro</b><strong class="${p50(it.overall)}">${fmt(it.overall,0)}%</strong></div>
  <div class="stat"><b>W ciągu tygodnia</b><strong class="${p50(it.p_week)}">${it.p_week==null?"–":fmt(it.p_week,0)+"%"}</strong></div>
  <div class="stat"><b>Trafność w roku</b><strong>${bt.overall==null?"–":fmt(bt.overall,0)+"%"}</strong></div></div>
 <section class="box"><h3>Potencjał teraz: <span class="${Pp.score>=70?"up":Pp.score<=35?"down":"midc"}">${Pp.score}/100</span></h3>
  ${Pp.plus.length?`<p class="small" style="margin:0 0 4px"><b>Za:</b></p><ul class="sum small">${Pp.plus.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>`:""}
  ${Pp.minus.length?`<p class="small" style="margin:8px 0 4px"><b>Przeciw:</b></p><ul class="sum small">${Pp.minus.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>`:""}
  ${Hh?`<p class="note">Szansa w ciągu ~4 godzin: z ${Hh.n} podobnych sytuacji na świecach godzinowych z 6 miesięcy (zwykle wzrost w ${fmt(Hh.base,0)}%). Trafność tej metody w teście: ${Hh.acc==null?"–":fmt(Hh.acc,0)+"%"}.</p>`:""}</section>
 <div class="two"><section class="box"><h3>Typowe zakresy ceny</h3><p class="note" style="margin:0">W ok. 2 na 3 przypadkach cena powinna zmieścić się w tych przedziałach (liczone z wahań z ostatnich 60 sesji):</p>
  <table class="fc"><thead><tr><th>Kiedy</th><th>Od</th><th>Do</th><th>Ruch</th></tr></thead><tbody>${rng}</tbody></table></section>
 <section class="box"><h3>Co działo się w podobnych sytuacjach</h3>${an?`<p style="margin:0 0 6px" class="small">Sytuacja jak teraz (5 lat historii): <i>${esc(F.analog_state)}</i></p><ul class="sum">${an}</ul>`:`<p class="note">Za mało podobnych sytuacji w historii.</p>`}
  ${su?`<p style="margin:12px 0 6px" class="small">Czy warunki wzrostu z zakładki „Decyzja” działały na tym instrumencie:</p><ul class="sum">${su}</ul>`:""}</section></div>
 ${stratBox(it)}${mlBox(it)}${extrasBox(it)}
 <section class="box"><h3>Skąd ten wynik – ${it.methods.length} niezależnych metod</h3>${meth}
  <p class="note" style="margin:10px 0 0">Surowa średnia metod: ${fmt(it.raw,0)}%. Test na historii (${bt.days} sesji): pasek trafiał kierunek w ${bt.overall==null?"–":fmt(bt.overall,0)+"%"} przypadków, a wzrostowych sesji było ${fmt(bt.up_share,0)}%. Dlatego szansa jest skalibrowana: siła sygnału ×${fmt(bt.k,2)} wokół naturalnej częstości wzrostów ${fmt(bt.base,0)}%. Wagi metod liczone są tylko z wcześniejszych danych.</p></section>
 <p class="note">To spekulacja oparta na historii, nie pewnik. Nagłe wydarzenia (wyniki spółki, decyzje banków centralnych, wojny) mogą wszystko zmienić.</p>`}

// --- newsy i wydarzenia ---
function evRow(e,linkNames){const d=new Date(e.date);
 const t=e.time?hm(d):"cały dzień",imp={high:"Wysoki wpływ",mid:"Średni wpływ",low:"Mały wpływ"}[e.impact];
 const fp=[e.forecast&&"prognoza: "+e.forecast,e.previous&&"poprzednio: "+e.previous].filter(Boolean).join(" · ");
 const chips=linkNames?`<div class="chips">${e.symbols.map((s,i)=>`<a class="chip" href="#i=${encodeURIComponent(s)}">${esc((e.names||[])[i]||s)}</a>`).join("")}</div>`:"";
 return `<div class="ev ${e.days<0?"past":""}"><div class="t">${t}</div><div><h4><span class="imp-${e.impact}" title="${imp}">●</span> ${esc(e.title)}</h4>
 <p>${[e.desc,fp,imp,e.source].filter(Boolean).map(esc).join(" · ")}</p>${e.hint?`<p><b>Co to oznacza dla ceny:</b> ${esc(e.hint)}</p>`:""}${chips}</div></div>`}
function tNewsy(it){const ev=eventsFor(it.symbol);
 $("tab").innerHTML=`<section class="box"><h3>Nadchodzące wydarzenia</h3>${ev.length?ev.slice(0,12).map(e=>`<div class="day" style="margin-top:8px">${whenTxt(e.days)} · ${dayTxt(e)}</div>${evRow(e,false)}`).join(""):`<p class="note">Brak zaplanowanych ważnych wydarzeń w najbliższym czasie.</p>`}</section>
 <section class="box"><h3>Wiadomości ze świata i z Polski</h3>
  <div class="seg" role="group" aria-label="Okres wiadomości" style="margin-bottom:10px"><button data-n="week" aria-pressed="${ntab==="week"}">Ostatnie 7 dni (${it.news.week.count})</button><button data-n="prev" aria-pressed="${ntab==="prev"}">Tydzień wcześniej (${it.news.prev.count})</button></div>
  <div id="nbody"></div></section>`;renderNews(it)}
function renderNews(it){const N=it.news[ntab];
 $("nbody").innerHTML=`<p style="margin:0">${esc(N.text)}</p>${N.items.length?`<ul class="clean nlist" style="margin-top:8px">${N.items.map(n=>newsLi(Object.assign({dir:n.tone>0.2?"up":n.tone<-0.2?"down":"neutral"},n))).join("")}</ul>
 <p class="note">Pod każdą wiadomością: co może oznaczać dla ceny i dlaczego (ocena automatyczna – reguły rynkowe, np. „silny dolar szkodzi złotu”, i słownik słów). Najpierw pokazujemy najbardziej wiarygodne źródła.</p>`:""}`}
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


// ---------- ŚWIECE JAPOŃSKIE: objaśnienia do nauki ----------
const PAT={
 hammer:{n:"Młot",d:"up",what:"Mały korpus u góry i długi dolny cień (co najmniej 2× dłuższy od korpusu), po spadkach.",mean:"Możliwe odwrócenie spadków w górę.",why:"W trakcie sesji sprzedający zepchnęli cenę nisko, ale kupujący ją odkupili i podnieśli prawie do otwarcia. To znak, że po spadkach pojawił się popyt."},
 inv_hammer:{n:"Odwrócony młot",d:"up",what:"Mały korpus na dole i długi górny cień, po spadkach.",mean:"Słaby sygnał możliwego odbicia – potrzebuje potwierdzenia następną świecą wzrostową.",why:"Kupujący spróbowali podnieść cenę. Na razie nie utrzymali zdobyczy, ale sprzedający tracą przewagę."},
 hanging_man:{n:"Wisielec",d:"down",what:"Wygląda jak młot (długi dolny cień), ale pojawia się po wzrostach.",mean:"Ostrzeżenie przed możliwym końcem wzrostów.",why:"W trakcie sesji pojawiła się silna sprzedaż. Kupujący jeszcze odrobili spadek, ale pokazało to, że podaż rośnie."},
 shooting_star:{n:"Spadająca gwiazda",d:"down",what:"Mały korpus na dole i długi górny cień, po wzrostach.",mean:"Możliwe odwrócenie wzrostów w dół.",why:"Kupujący wypchnęli cenę wysoko, ale sprzedający zbili ją z powrotem. Wyżej zabrakło chętnych do kupna."},
 bull_engulf:{n:"Objęcie hossy",d:"up",what:"Duża świeca wzrostowa, której korpus całkowicie „obejmuje” korpus poprzedniej świecy spadkowej.",mean:"Jeden z silniejszych sygnałów odwrócenia spadków.",why:"Kupujący nie tylko zatrzymali spadki, ale w jeden dzień odrobili cały ruch poprzedniego dnia z nawiązką."},
 bear_engulf:{n:"Objęcie bessy",d:"down",what:"Duża świeca spadkowa obejmująca korpus poprzedniej świecy wzrostowej, po wzrostach.",mean:"Jeden z silniejszych sygnałów odwrócenia wzrostów.",why:"Sprzedający przejęli kontrolę i zabrali cały wzrost poprzedniego dnia."},
 bull_harami:{n:"Harami hossy",d:"up",what:"Mała świeca wzrostowa mieszcząca się w korpusie poprzedniej dużej świecy spadkowej.",mean:"Spadki tracą siłę – możliwe odwrócenie (sygnał słabszy niż objęcie).",why:"Po mocnym spadku rynek się uspokoił i nie kontynuował ruchu w dół."},
 bear_harami:{n:"Harami bessy",d:"down",what:"Mała świeca spadkowa wewnątrz korpusu poprzedniej dużej świecy wzrostowej.",mean:"Wzrosty tracą siłę.",why:"Po mocnym wzroście zabrakło kontynuacji – kupujący się wahają."},
 piercing:{n:"Przenikanie",d:"up",what:"Po świecy spadkowej następna otwiera się niżej, ale zamyka powyżej połowy jej korpusu.",mean:"Możliwe odwrócenie spadków.",why:"Rynek otworzył się słabo, ale kupujący odrobili ponad połowę wczorajszego spadku."},
 dark_cloud:{n:"Zasłona ciemnej chmury",d:"down",what:"Po świecy wzrostowej następna otwiera się wyżej, ale zamyka poniżej połowy jej korpusu.",mean:"Możliwe odwrócenie wzrostów.",why:"Mimo mocnego otwarcia sprzedający zabrali ponad połowę wczorajszego wzrostu."},
 morning_star:{n:"Gwiazda poranna",d:"up",what:"Trzy świece: duża spadkowa, mała (niezdecydowanie), duża wzrostowa.",mean:"Klasyczny sygnał odwrócenia spadków w górę.",why:"Spadki wyhamowały (mała świeca), a potem kupujący zdecydowanie przejęli inicjatywę."},
 evening_star:{n:"Gwiazda wieczorna",d:"down",what:"Trzy świece: duża wzrostowa, mała, duża spadkowa.",mean:"Klasyczny sygnał odwrócenia wzrostów w dół.",why:"Wzrosty wyhamowały, a potem sprzedający przejęli inicjatywę."},
 three_soldiers:{n:"Trzej biali żołnierze",d:"up",what:"Trzy kolejne duże świece wzrostowe, każda zamyka się wyżej.",mean:"Silny, równy popyt – trend w górę.",why:"Przez trzy dni kupujący konsekwentnie przeważali, bez większej walki."},
 three_crows:{n:"Trzy czarne wrony",d:"down",what:"Trzy kolejne duże świece spadkowe, każda zamyka się niżej.",mean:"Silna podaż – trend w dół.",why:"Przez trzy dni sprzedający konsekwentnie przeważali."},
 bull_marubozu:{n:"Marubozu wzrostowe",d:"up",what:"Duża świeca wzrostowa prawie bez cieni – otwarcie przy dołku, zamknięcie przy szczycie.",mean:"Kupujący dominowali przez całą sesję – często kontynuacja wzrostów.",why:"Od otwarcia do zamknięcia cena praktycznie tylko rosła."},
 bear_marubozu:{n:"Marubozu spadkowe",d:"down",what:"Duża świeca spadkowa prawie bez cieni.",mean:"Sprzedający dominowali przez całą sesję – często kontynuacja spadków.",why:"Od otwarcia do zamknięcia cena praktycznie tylko spadała."},
 doji:{n:"Doji",d:"neutral",what:"Otwarcie i zamknięcie prawie na tym samym poziomie – korpus jak kreska.",mean:"Niezdecydowanie. Po silnym trendzie może zapowiadać jego koniec.",why:"Kupujący i sprzedający byli w równowadze – żadna strona nie wygrała sesji."}};
const DIRTXT={up:"↑ może wspierać wzrost",down:"↓ może ciążyć cenie",neutral:"→ raczej bez wyraźnego wpływu"};
const DIRCLS={up:"up",down:"down",neutral:"flat"};
function candleDesc(o,h,l,c){const r=Math.max(h-l,1e-12),b=Math.abs(c-o),up=c>=o,uw=h-Math.max(o,c),lw=Math.min(o,c)-l;
 const parts=[`Świeca ${up?"wzrostowa (zielona) – zamknięcie wyżej niż otwarcie":"spadkowa (czerwona) – zamknięcie niżej niż otwarcie"}.`];
 parts.push(b/r>0.6?"Duży korpus: jedna strona wyraźnie wygrała sesję.":b/r<0.25?"Mały korpus: niezdecydowanie, siły były wyrównane.":"Średni korpus.");
 if(uw/r>0.4)parts.push("Długi górny cień: cena była wyżej, ale sprzedający ją zbili – opór u góry.");
 if(lw/r>0.4)parts.push("Długi dolny cień: cena była niżej, ale kupujący ją podnieśli – popyt na dole.");
 return parts.join(" ")}

// ---------- dodawanie / usuwanie instrumentów (przez zgłoszenie na GitHubie) ----------
const REPO="https://github.com/alexanderdimer-ops/centrum-rynku";
let pending=store.get("pending",[]);
function issueUrl(title){return `${REPO}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent("Kliknij zielony przycisk „Create” (lub „Submit new issue”). Automat sam zmieni listę i odpowie tutaj w ciągu 2–3 minut. Niczego więcej nie trzeba robić.")}`}
function requestAdd(q){q=q.trim();if(!q)return;pending=pending.filter(p=>Date.now()-p.t<36e5);pending.push({q,t:Date.now()});store.set("pending",pending);window.open(issueUrl("Dodaj: "+q),"_blank","noopener")}
function requestRemove(it){if(confirm(`Usunąć ${it.name} z listy dla wszystkich urządzeń? Otworzy się GitHub – kliknij tam „Create”.`))window.open(issueUrl("Usuń: "+it.symbol),"_blank","noopener")}
function pendingHtml(){pending=pending.filter(p=>Date.now()-p.t<36e5&&!D.items.some(i=>(i.name+" "+i.symbol).toLowerCase().includes(p.q.toLowerCase())));store.set("pending",pending);
 return pending.length?`<p class="note">W trakcie dodawania: ${pending.map(p=>esc(p.q)).join(", ")} – pojawi się po ok. 3–5 minutach od kliknięcia „Create” na GitHubie (odśwież stronę).</p>`:""}

// ---------- TERAZ WARTO ----------
function candidates(){const own=new Set(D.items.map(i=>i.symbol));
 const mine=D.items.map(it=>({symbol:it.symbol,name:it.name,group:it.group,currency:it.currency,price:it.price,change:it.change,score:it.potential.score,
  plus:it.potential.plus,minus:it.potential.minus,risk:it.risk.level,risk_label:it.risk.label,stop:it.plan.stop,target:it.plan.target,own:true,dec:it.decision.key,
  news:it.news.week.items.filter(n=>n.dir!=="neutral").slice(0,2),spark:it.hist.c.slice(-30)}));
 const ext=((D.scan||{}).items||[]).filter(x=>!own.has(x.symbol));
 return mine.concat(ext)}
function oppCard(x){const st=x.score>=80?"go":x.score>=70?"wait":"no";
 const sp=(()=>{const c=x.spark||[];if(c.length<2)return "";const mn=Math.min(...c),mx=Math.max(...c),k=mx-mn||1;return `<svg class="spark" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true"><polyline points="${c.map((v,i)=>`${(i/(c.length-1)*100).toFixed(2)},${(38-(v-mn)/k*34).toFixed(2)}`).join(" ")}" fill="none" stroke="${c[c.length-1]>=c[0]?"var(--up)":"var(--down)"}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`})();
 return `<article class="box opp"><header class="row" style="justify-content:space-between;align-items:flex-start"><div><h3 style="margin:0">${esc(x.name)}</h3><span class="sub">${esc(x.symbol)} · ${esc(x.group)} · ${x.own?"z Twojej listy":"spoza listy"}</span></div>
 <div class="px">${fmt(x.price)} ${esc(x.currency)}<span class="chg ${sgn(x.change)}">${pct(x.change,2)}</span></div></header>
 ${sp}<div class="row" style="gap:10px"><div style="flex:1">${bar(x.score,`var(--${st==="go"?"up":st==="wait"?"mid":"down"})`)}</div><b class="c-${st}">Potencjał ${x.score}/100</b></div>
 <div class="cfoot" style="margin-top:8px">${x.own&&item(x.symbol)&&item(x.symbol).final?`<span class="dec c-${FK[item(x.symbol).final.key]} bg-${FK[item(x.symbol).final.key]}">${esc(item(x.symbol).final.title)}</span>`:""}<span class="chip dot r${x.risk}">Ryzyko: ${esc(x.risk_label.toLowerCase())}</span>${x.earnings_days!=null&&x.earnings_days>=0&&x.earnings_days<=14?`<span class="chip" style="color:var(--info)">Wyniki ${whenTxt(x.earnings_days)}</span>`:""}</div>
 <p class="small" style="margin:10px 0 4px"><b>Dlaczego teraz:</b></p><ul class="sum small">${x.plus.slice(0,4).map(t=>`<li>${esc(t)}</li>`).join("")}</ul>
 ${x.minus.length?`<p class="small" style="margin:8px 0 4px"><b>Na co uważać:</b></p><ul class="sum small">${x.minus.slice(0,3).map(t=>`<li>${esc(t)}</li>`).join("")}</ul>`:""}
 ${(x.news||[]).length?`<ul class="clean nlist small" style="margin-top:6px">${x.news.slice(0,2).map(newsLi).join("")}</ul>`:""}
 <p class="small mut" style="margin:8px 0">Przykładowy plan: stop loss ok. ${fmt(x.stop)}, cel ok. ${fmt(x.target)} (2× i 3× typowy ruch dzienny).</p>
 <div class="row">${x.own?`<a class="btn sm pri" style="text-decoration:none" href="#i=${encodeURIComponent(x.symbol)}">Pełna analiza i kalkulator</a>`:`<button class="btn sm pri" data-add="${esc(x.symbol)}">Dodaj do mojej listy</button>`}</div></article>`}
function newsLi(n){return `<li><span class="dotc" style="background:var(--${n.dir==="up"?"up":n.dir==="down"?"down":"dim"})"></span><span><a href="${esc(safe(n.link))}" target="_blank" rel="noopener">${esc(n.title)}</a>
 <span class="nmeta"><b class="${DIRCLS[n.dir]||"flat"}">${DIRTXT[n.dir]||DIRTXT.neutral}</b> – ${esc(n.why||"")}</span>
 <span class="nmeta">${n.tier<=1?`<span class="tag t${n.tier}">${n.tier===0?"oficjalne":"wiarygodne"}</span>`:""}${n.lang?`<span class="tag">${n.lang.toUpperCase()}</span>`:""}${esc(n.source)} · ${ago(n.date)}</span></span></li>`}
function changeLi(c){return `<li><span class="dotc" style="background:var(--${c.dir==="up"?"up":"down"})"></span><span><a href="#i=${encodeURIComponent(c.symbol)}"><b>${esc(c.name)}</b></a> – ${esc(c.text)}<span class="nmeta">${ago(c.time)}</span></span></li>`}
function viewTeraz(){
 const PK=D.picks;let top,risky;
 if(PK){top=PK[terazH]||[];risky=PK[terazH+"_risky"]||0}else{const all=candidates();risky=all.filter(x=>x.score>=70&&x.risk>=4).length;top=all.filter(x=>x.score>=70&&x.risk<=3&&x.dec!=="no").sort((a,b)=>b.score-a.score).slice(0,6)}
 const ann=PK?["short","mid","long"].map(h=>{const x=(PK[h]||[])[0];return x?`<li><b>${HZN[h]}:</b> <a href="${x.own?"#i="+encodeURIComponent(x.symbol):"#teraz"}" ${x.own?"":`data-th="${h}"`}>${esc(x.name)}</a> – potencjał ${x.score}/100. ${esc((x.plus||[])[0]||"")}</li>`:`<li><b>${HZN[h]}:</b> teraz nic nie wyróżnia się wystarczająco – lepiej poczekać.</li>`}).join(""):"";
 const warn=D.items.filter(it=>it.potential.score<=35||it.decision.key==="no").filter(it=>fav.includes(it.symbol)).slice(0,6);
 const ch=(D.changes||[]),chFav=ch.filter(c=>fav.includes(c.symbol)),chOther=ch.filter(c=>!fav.includes(c.symbol));
 store.set("seenChanges",ch.length?ch[0].time:"");updBadge();
 const scanT=D.scan?new Date(D.scan.time):null;
 $("app").innerHTML=`<div class="upd">${updTxt()}</div><h2 style="margin:4px 0 6px">Teraz warto</h2>
 <p class="note" style="margin:0 0 12px">Instrumenty, które w tej chwili mają najlepszy układ: trend, wybicia, siła względem rynku, obroty, wiadomości i historia podobnych sytuacji – minus ryzyko i nadchodzące wyniki. Przeskanowano ${((D.scan||{}).items||[]).length+D.items.length} instrumentów z Twojej listy i z rynku${scanT?` (skan: ${hm(scanT)})`:""}. Wybierz horyzont: krótko (najbliższa sesja), średnio (tydzień) albo długo (miesiące). To lista do sprawdzenia, nie gotowe polecenie kupna – skuteczność propozycji sprawdzisz w zakładce „Wyniki”.</p>
 ${ann?`<section class="box hero bg-go" style="border-color:transparent"><h3 style="font-size:17px;margin-bottom:6px">Ogłoszenia – w co warto teraz zajrzeć</h3><ul style="margin:0">${ann}</ul></section>`:""}
 ${ch.length?`<section class="box"><h3>Zmiany od ostatnich aktualizacji</h3>${chFav.length?`<ul class="clean nlist">${chFav.slice(0,4).map(changeLi).join("")}</ul>${chFav.length>4?`<details><summary class="small">Starsze zmiany w ulubionych (${chFav.length-4})</summary><ul class="clean nlist">${chFav.slice(4,20).map(changeLi).join("")}</ul></details>`:""}`:`<p class="note">Brak zmian w ulubionych.</p>`}
  ${chOther.length?`<details style="margin-top:6px"><summary class="small">Pozostałe instrumenty (${chOther.length})</summary><ul class="clean nlist">${chOther.slice(0,15).map(changeLi).join("")}</ul></details>`:""}
  <div class="row" style="margin-top:8px"><button class="btn sm" id="notifBtn">${"Notification" in window&&Notification.permission==="granted"?"Powiadomienia w przeglądarce: włączone":"Włącz powiadomienia w przeglądarce"}</button></div></section>`:""}
 <div class="row" style="justify-content:space-between;margin:18px 0 10px"><h3 style="margin:0">Największy potencjał teraz</h3>
 <div class="seg" role="group" aria-label="Horyzont">${Object.entries(HZN).map(([k,l])=>`<button data-th="${k}" aria-pressed="${k===terazH}">${l}</button>`).join("")}</div></div>
 ${top.length?`<div class="grid">${top.slice(0,6).map(oppCard).join("")}</div>`:`<div class="msg">W tej chwili nic nie ma wyraźnie dobrego układu. Najlepszą decyzją bywa poczekać – brak transakcji to też pozycja.</div>`}
 ${risky?`<p class="note">Pominięto ${risky} instrumentów z bardzo wysokim ryzykiem – mają dobry układ, ale są zbyt zmienne dla początkującego.</p>`:""}
 ${warn.length?`<h3 style="margin:18px 0 10px">Na co uważać wśród ulubionych</h3><section class="box"><ul class="clean nlist">${warn.map(it=>`<li><span class="dotc" style="background:var(--down)"></span><span><a href="#i=${encodeURIComponent(it.symbol)}"><b>${esc(it.name)}</b></a> – ${esc(it.decision.title)}. ${esc((it.potential.minus[0]||it.decision.reasons[0]||""))}</span></li>`).join("")}</ul></section>`:""}
 <h3 style="margin:18px 0 10px">Najważniejsze wiadomości ze świata</h3>
 <section class="box">${((D.world||{}).items||[]).length?`<ul class="clean nlist">${D.world.items.slice(0,10).map(n=>newsLi(n).replace("</span></span></li>",`${n.names&&n.names.length?` · dotyczy: ${n.names.map(esc).join(", ")}`:""}</span></span></li>`)).join("")}</ul>`:`<p class="note">Brak świeżych wiadomości z wiarygodnych źródeł.</p>`}
 <p class="note">Tylko z najbardziej wiarygodnych źródeł (Reuters, Bloomberg, CNBC, WSJ, FT, Yahoo Finance, PAP, Bankier i in.), z ostatnich 2 dni. Opis wpływu na cenę jest automatyczny.</p></section>`;
 const nb=$("notifBtn");if(nb)nb.onclick=()=>{if(!("Notification" in window)){alert("Ta przeglądarka nie obsługuje powiadomień.");return}Notification.requestPermission().then(()=>viewTeraz())}}
function updBadge(){const a=document.querySelector('.nav a[data-v="teraz"]');if(!a||!D)return;const seen=store.get("seenChanges","");
 const n=(D.changes||[]).filter(c=>fav.includes(c.symbol)&&c.time>seen).length;a.dataset.badge=n?n:"";}

// ---------- automatyczne odświeżanie ----------
function toast(html){let t=$("toast");if(!t){t=document.createElement("div");t.id="toast";document.body.appendChild(t)}
 t.innerHTML=html;t.className="show";clearTimeout(t._h);t._h=setTimeout(()=>t.className="",9000)}
const DATA_URL="https://raw.githubusercontent.com/alexanderdimer-ops/centrum-rynku/dane/data.json";
function loadData(){const local=()=>fetch("data.json?"+Date.now()).then(r=>r.json());
 if(location.hostname==="localhost"||location.hostname==="127.0.0.1")return local();
 return fetch(DATA_URL+"?"+Date.now()).then(r=>{if(!r.ok)throw 0;return r.json()}).then(d=>local().then(l=>l.updated>d.updated?l:d).catch(()=>d)).catch(local)}
function refresh(){loadData().then(d=>{if(!D||d.updated===D.updated)return;
 const old=new Set((D.changes||[]).map(c=>c.time+c.symbol+c.kind));D=d;
 const fresh=(d.changes||[]).filter(c=>!old.has(c.time+c.symbol+c.kind)&&fav.includes(c.symbol));
 const busy=document.activeElement&&/INPUT|SELECT/.test(document.activeElement.tagName)||/\/kalkulator$/.test(location.hash);
 resolveTests();if(!busy)route();updBadge();
 toast(fresh.length?`<b>Nowe dane – ${fresh.length} ${fresh.length===1?"zmiana":"zmiany"} w ulubionych:</b><br>${fresh.slice(0,3).map(c=>`${esc(c.name)}: ${esc(c.text)}`).join("<br>")}`:`Zaktualizowano dane (${hm(new Date(d.updated))}).`);
 if(fresh.length&&"Notification" in window&&Notification.permission==="granted")fresh.slice(0,3).forEach(c=>new Notification(c.name+" – Centrum rynku",{body:c.text}))}).catch(()=>{})}
setInterval(refresh,2*60*1000);


// ---------- POTENCJAŁ W TRZECH HORYZONTACH ----------
const HZN={short:"Krótko (1 dzień)",mid:"Średnio (tydzień)",long:"Długo (miesiące)"};
let potH=store.get("potH","mid"),terazH=store.get("terazH","mid");
const potOf=(it,h)=>h==="mid"?it.potential:it.potential[h];
const scoreCls=s=>s==null?"flat":s>=70?"up":s<=35?"down":"midc";
function potBox(it){const P=potOf(it,potH)||{};
 return `<section class="box"><h3>Potencjał wzrostu – wybierz horyzont</h3>
 <div class="stats3 pot">${Object.entries(HZN).map(([k,l])=>{const s=(potOf(it,k)||{}).score;return `<button class="stat${k===potH?" sel":""}" data-pot="${k}"><b>${l}</b><strong class="${scoreCls(s)}">${s==null?"–":s+"/100"}</strong></button>`}).join("")}</div>
 ${P.plus&&P.plus.length?`<p class="small" style="margin:0 0 4px"><b>Za:</b></p><ul class="sum small">${P.plus.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>`:""}
 ${P.minus&&P.minus.length?`<p class="small" style="margin:8px 0 4px"><b>Przeciw:</b></p><ul class="sum small">${P.minus.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>`:""}
 <p class="note">Krótko: układ na wykresie godzinowym, dzisiejsze tempo, ostatnia świeca, wiadomości z doby. Średnio: trend, wybicia, siła względem rynku, wiadomości. Długo: średnia z 200 dni, siła w pół roku i roku, odległość od szczytu, zmienność i historia podobnych układów.</p></section>`}

// ---------- TWOJE TESTY PRZEWIDYWAŃ ----------
let myTests=store.get("myTests",[]);
const TH={"4h":4*36e5,"1d":864e5,"1w":7*864e5};
const THN={"4h":"4 godziny","1d":"1 dzień","1w":"tydzień"};
function testBox(it){const pr={"4h":it.hours&&it.hours.p,"1d":it.overall,"1w":it.p_week};
 return `<section class="box"><h3>Sprawdź, czy strona ma rację</h3><p class="small" style="margin-top:-4px">Kliknij, a strona „na niby” wejdzie teraz w ${esc(it.name)} po ${fmt(it.price)} ${esc(it.currency)} i po wybranym czasie sama sprawdzi, czy przewidywanie się sprawdziło. Wyniki znajdziesz w zakładce „Wyniki”.</p>
 <div class="row">${Object.keys(TH).filter(h=>pr[h]!=null).map(h=>`<button class="btn sm" data-test="${h}">Za ${THN[h]} (szansa wzrostu ${fmt(pr[h],0)}%)</button>`).join("")}</div></section>`}
function addTest(it,h){const pr={"4h":it.hours&&it.hours.p,"1d":it.overall,"1w":it.p_week}[h];
 myTests.unshift({id:Date.now(),s:it.symbol,n:it.name,cur:it.currency,t:Date.now(),px:it.price,h,p:pr,dec:it.decision.title});store.set("myTests",myTests);
 toast(`Zapisano test: ${esc(it.name)} – sprawdzę za ${THN[h]}. Wynik w zakładce „Wyniki”.`)}
function priceAt(it,ms){
 if(it.intra&&it.intra.t.length){const I=it.intra;if(I.t[0]*1000<=ms&&I.t[I.t.length-1]*1000>=ms){for(let k=0;k<I.t.length;k++)if(I.t[k]*1000>=ms)return I.c[k]}}
 const H=it.hist,day=Math.floor(ms/864e5)+719163;for(let k=0;k<H.dd.length;k++)if(H.t0+H.dd[k]>=day&&H.t0+H.dd[k]<=day+4&&H.t0+H.dd[k]<Math.floor(Date.now()/864e5)+719163)return H.c[k];
 return Date.now()-ms<36e5*3?it.price:null}
function resolveTests(){let ch=false;myTests.forEach(x=>{if(x.res!=null)return;const due=x.t+TH[x.h];if(Date.now()<due)return;const it=item(x.s);if(!it)return;
 const px=priceAt(it,due);if(px==null)return;x.res=px;x.up=px>x.px;x.ok=(x.p>50)===x.up;ch=true});if(ch)store.set("myTests",myTests)}

// ---------- WYNIKI (samotestowanie strony) ----------
function viewWyniki(){resolveTests();const T=D.track||{},HT=D.hist_test||{},P=T.preds||{};
 const tile=(l,s,ex)=>`<div class="tile"><b>${l}</b><span class="${s?s.hit>=55?"up":s.hit<48?"down":"flat":"flat"}">${s?fmt(s.hit,0)+"%":"–"}</span><small class="dim" style="display:block;font-size:11.5px">${s?`${s.n} spr. · wzrosty ${fmt(s.up,0)}%`:ex}</small></div>`;
 const sim=T.sim,closed=T.sims_closed||[],open=T.sims_open||[];
 const curve=(T.curve||[]).map(x=>x.eq);const cw=600,chh=120;
 const curveSvg=curve.length>1?(()=>{const mn=Math.min(0,...curve),mx=Math.max(0,...curve),k=mx-mn||1;const pts=curve.map((v,i)=>`${(i/(curve.length-1)*cw).toFixed(1)},${(chh-6-(v-mn)/k*(chh-12)).toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${cw} ${chh}" preserveAspectRatio="none" style="width:100%;height:120px;display:block" aria-label="Wynik wirtualnych transakcji w czasie"><line x1="0" x2="${cw}" y1="${chh-6-(0-mn)/k*(chh-12)}" y2="${chh-6-(0-mn)/k*(chh-12)}" stroke="var(--line2)" stroke-dasharray="4 4"/><polyline points="${pts}" fill="none" stroke="${curve[curve.length-1]>=0?"var(--up)":"var(--down)"}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`})():"";
 const bins=Object.entries(T.bins||{}).map(([h,b])=>`<tr><td>${{"4h":"4 godziny","1d":"1 dzień","1w":"tydzień","1m":"miesiąc"}[h]}</td>${b.map(x=>`<td>${x.n?`${fmt(x.up,0)}% <span class="dim">(${x.n})</span>`:"–"}</td>`).join("")}</tr>`).join("");
 const ps=Object.values(T.per_sym||{}).sort((a,b)=>b.hit-a.hit);
 const mine=myTests.slice(0,40),mDone=mine.filter(x=>x.res!=null),mHit=mDone.filter(x=>x.ok).length;
 const hs=HT.signal,he=HT.every;
 $("app").innerHTML=`<div class="upd">${updTxt()}</div><h2 style="margin:4px 0 6px">Wyniki – czy strona ma rację?</h2>
 <p class="note" style="margin:0 0 12px">Strona sama, bez Twojego udziału, zapisuje swoje przewidywania dla wszystkich instrumentów i po czasie sprawdza, czy się sprawdziły. Otwiera też wirtualne transakcje, gdy mówi „Możesz rozważyć wejście”. Na tej podstawie sama się poprawia: koryguje szanse i zaostrza wymagania, gdy jej propozycje wychodzą słabo.</p>
 ${learnBox()}
 <section class="box"><h3>Trafność przewidywań kierunku (na żywo)</h3><div class="tiles">${tile("Za 4 godziny",P["4h"],"pierwsze po 4 godz.")}${tile("Za 1 dzień",P["1d"],"pierwsze jutro")}${tile("Za tydzień",P["1w"],"pierwsze za tydzień")}${tile("Za miesiąc",P["1m"],"pierwsze za miesiąc")}</div>
  <p class="note">Trafność = jak często strona dobrze wskazała kierunek (wzrost/spadek). 50% to rzut monetą. Czeka na sprawdzenie: ${T.pending||0} przewidywań.</p>
  ${bins?`<details><summary class="small">Kalibracja – czy „szansa 60%” naprawdę oznacza 60%?</summary><table class="fc"><thead><tr><th>Horyzont</th><th>&lt;45%</th><th>45–50%</th><th>50–55%</th><th>55–60%</th><th>60%+</th></tr></thead><tbody>${bins}</tbody></table><p class="note">W komórkach: jak często cena naprawdę rosła przy takiej podanej szansie (w nawiasie liczba przypadków). Gdy uzbiera się ≥30 przypadków, strona sama koryguje podawane szanse.</p></details>`:""}</section>
 <section class="box"><h3>Wirtualne transakcje strony</h3>
  <p class="small" style="margin-top:-4px">Gdy strona mówi „Możesz rozważyć wejście”, kupuje „na niby” ze stop lossem (2×ATR) i celem (3×ATR). Wychodzi na stopie, na celu albo po 14 dniach. Wynik liczony w R (1 R = planowane ryzyko).</p>
  <div class="tiles"><div class="tile"><b>Zamknięte</b><span>${sim?sim.n:0}</span></div><div class="tile"><b>Zyskowne</b><span>${sim?fmt(sim.hit,0)+"%":"–"}</span></div><div class="tile"><b>Średnio na transakcję</b><span class="${sim?sgn(sim.avg):"flat"}">${sim?(sim.avg>=0?"+":"−")+fmt(Math.abs(sim.avg),2)+" R":"–"}</span></div><div class="tile"><b>Otwarte teraz</b><span>${open.length}</span></div></div>
  ${curveSvg?`<p class="small" style="margin:12px 0 4px">Łączny wynik w czasie (R):</p>${curveSvg}`:""}
  ${open.length?`<details style="margin-top:10px"><summary class="small">Otwarte (${open.length})</summary><ul class="clean nlist small">${open.map(x=>{const it=item(x.s),r=it?(it.price-x.px)/(x.px-x.stop):0;return `<li><span class="dotc" style="background:var(--${r>=0?"up":"down"})"></span><span><b>${esc(x.n||x.s)}</b> od ${new Date(x.t).toLocaleDateString("pl-PL")} po ${fmt(x.px)} · stop ${fmt(x.stop)} · cel ${fmt(x.target)} · teraz <b class="${sgn(r)}">${r>=0?"+":"−"}${fmt(Math.abs(r),2)} R</b></span></li>`}).join("")}</ul></details>`:""}
  ${closed.length?`<details style="margin-top:6px"><summary class="small">Ostatnio zamknięte (${closed.length})</summary><ul class="clean nlist small">${closed.map(x=>`<li><span class="dotc" style="background:var(--${x.R>0?"up":"down"})"></span><span><b>${esc(x.n||x.s)}</b> · ${{stop:"stop loss",cel:"cel osiągnięty",czas:"koniec czasu"}[x.res]} · <b class="${sgn(x.R)}">${x.R>=0?"+":"−"}${fmt(Math.abs(x.R),2)} R</b><span class="nmeta">${new Date(x.t).toLocaleDateString("pl-PL")} → ${new Date(x.end).toLocaleDateString("pl-PL")}</span></span></li>`).join("")}</ul></details>`:""}</section>
 ${mlWyniki()}
 <section class="box"><h3>Test na historii (ostatnie ~4 lata)</h3>${hs&&he?`<p class="small" style="margin-top:-4px">Gdyby strona działała wcześniej i wchodziła przy spełnionych warunkach wzrostu (stop 2×ATR, cel 3×ATR, maks. 10 sesji):</p>
  <div class="tiles"><div class="tile"><b>Transakcji</b><span>${hs.n}</span></div><div class="tile"><b>Zyskowne</b><span>${fmt(hs.win*100,0)}%</span></div><div class="tile"><b>Średnio</b><span class="${sgn(hs.avgR)}">${hs.avgR>=0?"+":"−"}${fmt(Math.abs(hs.avgR),2)} R</span></div><div class="tile"><b>Wejście w losowy dzień</b><span>${he.avgR>=0?"+":"−"}${fmt(Math.abs(he.avgR),2)} R</span></div></div>
  <p class="note">${hs.avgR>he.avgR+0.03?`Sygnały strony dawały średnio lepszy wynik niż wchodzenie w przypadkowe dni (${fmt(hs.avgR,2)} R wobec ${fmt(he.avgR,2)} R) – jest mała, ale realna przewaga.`:`Sygnały strony nie były wyraźnie lepsze od wchodzenia w przypadkowe dni – traktuj je jako porządkowanie informacji, nie gotowy przepis na zysk.`} Wynik nie uwzględnia kosztów (spread, prowizje), które zmniejszają zysk. Rynki w tym okresie w większości rosły, co pomaga każdej strategii kupna.</p>`:`<p class="note">Brak danych.</p>`}</section>
 <section class="box"><h3>Propozycje z „Teraz warto”</h3><div class="tiles">${["short","mid","long"].map(h=>{const s=(T.picks||{})[h];return `<div class="tile"><b>${HZN[h]}</b><span class="${s?sgn(s.avg):"flat"}">${s?`${fmt(s.hit,0)}% zysk.`:"–"}</span><small class="dim" style="display:block;font-size:11.5px">${s?`${s.n} propozycji · średnio ${pct(s.avg*100)}`:"czeka na wyniki"}</small></div>`}).join("")}</div>
  <p class="note">Próg wejścia na listę teraz: krótko ${T.threshold?T.threshold.short:62}, średnio ${T.threshold?T.threshold.mid:70}, długo ${T.threshold?T.threshold.long:70} punktów. Strona sama go podnosi, gdy jej propozycje wypadają słabo, i obniża, gdy wypadają dobrze.</p></section>
 ${ps.length?`<section class="box"><h3>Na których instrumentach strona przewiduje najlepiej</h3><table class="fc"><thead><tr><th>Instrument</th><th>Sprawdzeń</th><th>Trafność</th></tr></thead><tbody>${ps.map(x=>`<tr><td>${esc(x.name)}</td><td>${x.n}</td><td class="${x.hit>=55?"up":x.hit<48?"down":"flat"}">${fmt(x.hit,0)}%</td></tr>`).join("")}</tbody></table></section>`:""}
 <section class="box"><h3>Twoje testy</h3>${mine.length?`<p class="small" style="margin-top:-4px">Sprawdzone: ${mDone.length}, trafione: ${mHit}${mDone.length?` (${fmt(mHit/mDone.length*100,0)}%)`:""}.</p><ul class="clean nlist small">${mine.map(x=>`<li><span class="dotc" style="background:var(--${x.res==null?"dim":x.ok?"up":"down"})"></span><span><b>${esc(x.n)}</b> · za ${THN[x.h]} · szansa wzrostu ${fmt(x.p,0)}% · wejście ${fmt(x.px)} ${esc(x.cur)}
  <span class="nmeta">${x.res==null?`czeka do ${new Date(x.t+TH[x.h]).toLocaleString("pl-PL",{dateStyle:"short",timeStyle:"short"})}`:`wynik: ${fmt(x.res)} (${pct((x.res/x.px-1)*100)}) – ${x.ok?"przewidywanie trafne ✓":"przewidywanie chybione ✗"}`}</span></span></li>`).join("")}</ul>`:`<p class="note">Nie masz jeszcze testów. Wejdź w dowolny instrument → zakładka „Decyzja” → „Sprawdź, czy strona ma rację”.</p>`}</section>`}

// ---------- OBJAŚNIENIA NA WYKRESIE ----------
let annOn=store.get("annOn",true);
const ANN={res:{n:"Opór",t:"Poziom, przy którym cena kilka razy zawracała w dół – tam czekali sprzedający. Przebicie oporu w górę to sygnał siły (wybicie)."},
 sup:{n:"Wsparcie",t:"Poziom, przy którym cena kilka razy odbijała w górę – tam czekali kupujący. Spadek pod wsparcie to sygnał słabości."},
 tl_up:{n:"Linia trendu wzrostowego",t:"Łączy coraz wyższe dołki. Dopóki cena jest nad nią, kupujący kontrolują rynek. Przebicie w dół to ostrzeżenie."},
 tl_down:{n:"Linia trendu spadkowego",t:"Łączy coraz niższe szczyty. Dopóki cena jest pod nią, kontrolują sprzedający. Przebicie w górę może oznaczać koniec spadków."},
 top:{n:"Podwójny szczyt",t:"Cena dwa razy doszła do tego samego poziomu i dwa razy zawróciła – kupujący nie dali rady. Potwierdzeniem jest spadek pod dołek między szczytami (linia szyi)."},
 bottom:{n:"Podwójny dołek",t:"Cena dwa razy spadła do tego samego poziomu i dwa razy odbiła – sprzedający nie dali rady. Potwierdzeniem jest wybicie nad szczyt między dołkami (linia szyi)."},
 golden:{n:"Złoty krzyż",t:"Średnia z 50 dni przecina średnią z 200 dni w górę. Sygnał, że długoterminowy trend zmienia się na wzrostowy."},
 death:{n:"Krzyż śmierci",t:"Średnia z 50 dni przecina średnią z 200 dni w dół. Sygnał długoterminowej słabości."},
 breakout:{n:"Wybicie",t:"Zamknięcie powyżej najwyższej ceny z 20 sesji – kupujący przełamali opór. Często początek dalszych wzrostów (ale bywa fałszywe)."},
 breakdown:{n:"Przełamanie w dół",t:"Zamknięcie poniżej najniższej ceny z 20 sesji – sprzedający przełamali wsparcie."},
 buyers:{n:"Przewaga kupujących",t:"Zielone tło: cena jest nad rosnącą średnią z 20 dni – kupujący mają kontrolę."},
 sellers:{n:"Przewaga sprzedających",t:"Czerwone tło: cena jest pod opadającą średnią z 20 dni – sprzedający mają kontrolę."}};
function annSvg(it,S,X,Y,step,pt,ih,pl,iw,s0){const A=it.chart;if(!A||!annOn||S.intra)return "";const n=S.c.length,inv=i=>i-s0,vis=i=>i>=0&&i<n;let g="";
 A.regime.forEach(r=>{const a=Math.max(0,inv(r.from)),b=Math.min(n-1,inv(r.to));if(b<0||a>n-1||b<a)return;
  g+=`<rect data-ann="${r.side>0?"buyers":"sellers"}" x="${X(a)-step/2}" y="${pt}" width="${(b-a+1)*step}" height="${ih}" fill="var(--${r.side>0?"up":"down"})" opacity=".07"/>`});
 A.levels.forEach(l=>{const y=Y(l.price);if(y<pt||y>pt+ih)return;const col=l.kind==="res"?"var(--down)":"var(--up)";
  g+=`<g data-ann="${l.kind}" data-ap="${l.price}" style="cursor:pointer"><line x1="${pl}" x2="${pl+iw}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="1.3" stroke-dasharray="6 4" opacity=".85"/>
  <rect x="${pl+2}" y="${y-15}" width="${l.kind==="res"?118:132}" height="14" rx="3" fill="var(--bg)" opacity=".85"/><text x="${pl+6}" y="${y-4}" fill="${col}" font-size="11" font-weight="600">${l.kind==="res"?"Opór":"Wsparcie"} ${fmt(l.price)} (${l.touches}×)</text></g>`});
 const T=A.trendline;if(T&&vis(inv(T.i1))){const x1=X(inv(T.i1)),x2=X(inv(T.i2));
  g+=`<g data-ann="tl_${T.kind}" style="cursor:pointer"><line x1="${x1}" x2="${x2}" y1="${Y(T.p1)}" y2="${Y(T.p2)}" stroke="var(--info)" stroke-width="2"/><text x="${x2-4}" y="${Y(T.p2)+(T.kind==="up"?16:-8)}" fill="var(--info)" font-size="11" text-anchor="end" font-weight="600">linia trendu</text></g>`}
 const Dd=A.double;if(Dd&&vis(inv(Dd.i1))){const x1=X(inv(Dd.i1)),x2=X(inv(Dd.i2)),col=Dd.type==="top"?"var(--down)":"var(--up)",dy=Dd.type==="top"?-10:14;
  g+=`<g data-ann="${Dd.type}" style="cursor:pointer"><circle cx="${x1}" cy="${Y(Dd.p1)}" r="5" fill="none" stroke="${col}" stroke-width="2"/><circle cx="${x2}" cy="${Y(Dd.p2)}" r="5" fill="none" stroke="${col}" stroke-width="2"/>
  <line x1="${x1}" x2="${X(n-1)}" y1="${Y(Dd.neck)}" y2="${Y(Dd.neck)}" stroke="${col}" stroke-dasharray="2 3"/><text x="${(x1+x2)/2}" y="${Y((Dd.p1+Dd.p2)/2)+dy}" fill="${col}" font-size="11" text-anchor="middle" font-weight="600">${Dd.type==="top"?"podwójny szczyt":"podwójny dołek"}</text></g>`}
 A.events.forEach(e=>{const i=inv(e.i);if(!vis(i))return;const up=e.key==="golden"||e.key==="breakout",y=up?Y(S.l[i])+30:Y(S.h[i])-22,col=up?"var(--up)":"var(--down)",lab=ANN[e.key].n;
  g+=`<g data-ann="${e.key}" style="cursor:pointer"><line x1="${X(i)}" x2="${X(i)}" y1="${up?Y(S.l[i])+4:Y(S.h[i])-4}" y2="${y+(up?-10:4)}" stroke="${col}" stroke-width="1"/><text x="${X(i)}" y="${y}" fill="${col}" font-size="10.5" text-anchor="middle" font-weight="600">${lab}</text></g>`});
 return g}
function annInfo(key,price){const a=ANN[key];if(!a)return;const el=$("cinfo");el.innerHTML=`<div class="cbox"><p style="margin:0"><b>${a.n}${price?" "+fmt(+price):""}</b></p><p class="small" style="margin:6px 0 0">${a.t}</p></div>`}
function storyBox(it){const A=it.chart;if(!A)return "";return `<section class="box"><h3>Co teraz widać na wykresie</h3><ul class="sum">${A.story.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>
 <p class="note">Strona sama analizuje wykres z ostatniego roku. Na wykresie świecowym zaznacza: tło zielone/czerwone (kto ma przewagę), opory i wsparcia (ile razy cena tam zawracała), linię trendu, podwójne szczyty/dołki, wybicia i krzyże średnich. Kliknij element, żeby zobaczyć, co oznacza.</p></section>`}


// ---------- UCZENIE MASZYNOWE I DODATKOWE ŹRÓDŁA ----------
function mlInfo(h){const M=(D.ml||{})[h];return M||null}
function mlBox(it){const m=it.ml;if(!m)return "";const t=mlInfo("1w"),w=t?t.weight:0;
 const tl=(l,v)=>`<div class="stat"><b>${l}</b><strong class="${p50(v)}">${v==null?"–":fmt(v,0)+"%"}</strong></div>`;
 return `<section class="box"><h3>Uczenie maszynowe</h3>
 <p class="small" style="margin-top:-4px">Model uczy się codziennie od nowa na 5 latach historii ok. 60 instrumentów (17 cech: tempo ruchu, średnie, RSI, zmienność, obroty, świece, szeroki rynek). Poniżej jego szanse wzrostu dla ${esc(it.name)}:</p>
 <div class="stats3">${tl("Jutro",m["1d"])}${tl("Za tydzień",m["1w"])}${tl("Za miesiąc",m["1m"])}</div>
 ${m.why?`${m.why.plus.length?`<p class="small" style="margin:0 0 4px"><b>Co według modelu podnosi szansę:</b> ${m.why.plus.map(esc).join(", ")}.</p>`:""}${m.why.minus.length?`<p class="small" style="margin:0"><b>Co obniża:</b> ${m.why.minus.map(esc).join(", ")}.</p>`:""}`:""}
 ${t?`<p class="note">Uczciwy test (ostatni rok, którego model nie widział podczas nauki): trafność za tydzień ${fmt(t.test.acc,1)}% wobec ${fmt(t.test.majority,1)}% przy zawsze „wzrost”. ${w>0?`Model ma przewagę, więc wpływa na wyniki strony z wagą ${fmt(w*100,0)}%.`:`Model nie ma teraz przewagi, więc <b>nie wpływa</b> na wyniki strony. Sprawdza się codziennie i sam się włączy, gdy zacznie wygrywać.`}</p>`:""}</section>`}
function extrasBox(it){const X=it.extras||{};const rows=[];
 if(X.analysts){const A=X.analysts;rows.push(["Prognozy analityków (12 mies.)",`${esc(A.text)} Najniższa ${fmt(A.low)} USD, najwyższa ${fmt(A.high)} USD. <span class="dim">Źródło: Nasdaq.</span>`])}
 if(X.cot)rows.push(["Pozycje dużych graczy (COT)",`${esc(X.cot.text)} <span class="dim">Raport CFTC z ${esc(X.cot.date)}${X.cot.name.includes("WTI")?"; dla ropy Brent używamy raportu ropy WTI":""}.</span>`]);
 if(X.sector)rows.push(["Branża",esc(X.sector.text)]);
 if(X.earn)rows.push(["Reakcje na poprzednie wyniki",`${esc(X.earn.text)}<br>${X.earn.items.map(e=>`${new Date(e.date).toLocaleDateString("pl-PL")}: <b class="${sgn(e.move)}">${pct(e.move*100)}</b>${e.surprise!=null?` (zysk ${e.surprise>=0?"lepszy":"gorszy"} od prognoz o ${fmt(Math.abs(e.surprise),1)}%)`:""}`).join(" · ")}`]);
 if(X.season&&X.season.text)rows.push(["Sezonowość miesięczna",`${esc(X.season.text)}${X.season.next?` W kolejnym miesiącu: wzrost w ${fmt(X.season.next.up*100,0)}% lat.`:""}`]);
 if(!rows.length)return "";
 return `<section class="box"><h3>Dodatkowe źródła informacji</h3><dl class="kv ex">${rows.map(([k,v])=>`<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
 <p class="note">Te informacje wpływają na ocenę potencjału (głównie średnio- i długoterminowego). Raporty COT dotyczą złota, srebra i ropy, prognozy analityków i branża – spółek z USA.</p></section>`}
function mlWyniki(){const M=D.ml;if(!M)return "";const H={"1d":"Jutro","1w":"Za tydzień","1m":"Za miesiąc"};
 const live=M.live||{};const L=live["1w"]||live["1d"];
 return `<section class="box"><h3>Uczenie maszynowe – jak radzi sobie model</h3>
 <p class="small" style="margin-top:-4px">Model uczy się od nowa każdego dnia (ostatnio: ${esc(M.date||"–")}). Ostatni rok danych jest odkładany i model sprawdzany jest tylko na nim – to uczciwy test, bez „podglądania” wyników.</p>
 <table class="fc"><thead><tr><th>Horyzont</th><th>Trafność w teście</th><th>Zawsze „wzrost”</th><th>Wpływ na stronę</th></tr></thead><tbody>
 ${Object.entries(H).filter(([h])=>M[h]).map(([h,l])=>`<tr><td>${l}</td><td>${fmt(M[h].test.acc,1)}%</td><td>${fmt(M[h].test.majority,1)}%</td><td>${M[h].weight>0?fmt(M[h].weight*100,0)+"%":"wyłączony"}</td></tr>`).join("")}</tbody></table>
 ${M["1w"]&&M["1w"].lessons.length?`<p class="small" style="margin:10px 0 4px"><b>Czego model się nauczył z historii:</b></p><ul class="sum small">${M["1w"].lessons.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:""}
 <p class="note">Wniosek na dziś: z samego wykresu model nie znajduje trwałej przewagi – to normalne na płynnych rynkach, dlatego strona go nie słucha, dopóki nie zacznie wygrywać. ${L?`Drugi model uczy się na własnych, sprawdzonych przewidywaniach strony (z newsami, analitykami, COT i oceną potencjału): zebrano ${L.n} z ${L.need} potrzebnych przypadków${L.test?`, trafność w teście ${fmt(L.test.acc,1)}%`:""}.`:""}</p></section>`}


// ---------- WERDYKT KOŃCOWY (suma wszystkich analiz) ----------
const FK={strong_buy:"go",buy:"go",wait:"wait",avoid:"no",strong_avoid:"no"};
function finalBox(it){const F=it.final;if(!F)return "";const k=FK[F.key];
 return `<section class="hero bg-${k} final"><p class="small mut" style="margin:0 0 2px">Werdykt końcowy – suma wszystkich analiz</p>
 <h3 class="c-${k}" style="font-size:24px">${esc(F.title)}</h3>
 <ul class="clean fr">${F.reasons.map(r=>`<li><span class="${r.dir==="up"?"up":"down"}">${r.dir==="up"?"＋":"－"}</span>${esc(r.t)}</li>`).join("")}</ul>
 <p class="small" style="margin:8px 0 0"><b>Pewność:</b> ${esc(F.confidence)} · <b>Co zmieniłoby ocenę:</b> ${esc(F.change)}</p></section>`}
function finalLine(it){const F=it.final;if(!F)return "";const k=FK[F.key];
 return `<div class="fline bg-${k}"><span class="mut small">Podsumowanie:</span> <b class="c-${k}">${esc(F.title)}</b> <span class="small mut">(pewność: ${esc(F.confidence)})</span> <button class="linkbtn small" data-tab="decyzja">dlaczego?</button></div>`}

// ---------- STRATEGIE ODKRYTE PRZEZ STRONĘ ----------
const STS={ok:["potwierdzona w teście","up"],weak:["słaba w teście","midc"],fail:["odrzucona w teście","down"]};
function stratBox(it){const S=it.strategies;if(!S)return "";const live=(D.track||{}).rules_live||[];
 const lv=id=>live.find(x=>x.rid===id+"|"+it.symbol);
 const wt=(S.weekday||{}).intra||{},wn=(S.weekday||{}).next||{},WDN=["Pon","Wt","Śr","Czw","Pt","Sob","Nd"];
 const days=[0,1,2,3,4,5,6].filter(w=>wt[w]||wn[w]);
 return `<section class="box"><h3>Strategie odkryte przez stronę</h3>
 <p class="small" style="margin-top:-4px">Strona sama sprawdziła ${S.tested} hipotez dla ${esc(it.name)} (dni tygodnia, serie wzrostów i spadków, luki na otwarciu, pierwsza godzina handlu, RSI, średnie, początek/koniec miesiąca, zachowanie szerokiego rynku). Każdą sprawdza na trzech okresach: odkrycie → potwierdzenie → test na najnowszych danych, których nie używała. Potem śledzi je na żywo.</p>
 ${S.now.length?`<div class="alert blue"><b>Działa teraz:</b><ul>${S.now.map(r=>`<li>${esc(r.text)} → cena ${r.dir==="up"?"<b class=\"up\">rośnie</b>":"<b class=\"down\">spada</b>"} ${esc(r.when)} (trafność ${fmt(r.acc,0)}% z ${r.n} przypadków)</li>`).join("")}</ul></div>`:""}
 ${S.rules.length?`<ul class="clean nlist">${S.rules.slice(0,10).map(r=>{const L=lv(r.id),st=STS[r.status];return `<li><span class="dotc" style="background:var(--${r.dir==="up"?"up":"down"})"></span><span><b>${esc(r.text[0].toUpperCase()+r.text.slice(1))}</b> → cena ${r.dir==="up"?"rośnie":"spada"} ${esc(r.target)}
  <span class="nmeta">odkrycie ${fmt(r.disc[1],0)}% (${r.disc[0]}) · potwierdzenie ${fmt(r.val[1],0)}% (${r.val[0]}) · test ${r.test[1]==null?"–":fmt(r.test[1],0)+"%"} (${r.test[0]}) · zwykle ${fmt(r.base,0)}% · <b class="${st[1]}">${st[0]}</b>${L?` · na żywo <b class="${L.hit>=65?"up":L.hit<50?"down":"flat"}">${fmt(L.hit,0)}%</b> (${L.n})`:""}</span></span></li>`}).join("")}</ul>`:`<p class="note">Żadna hipoteza nie przeszła ostrych testów – na tym instrumencie nie widać powtarzalnych prostych wzorców.</p>`}
 ${days.length?`<details style="margin-top:8px"><summary class="small"><b>Sprawdź „mity” o dniach tygodnia</b></summary><table class="fc"><thead><tr><th>Dzień</th><th>Od otwarcia do zamknięcia</th><th>Na tej sesji (zamknięcie do zamknięcia)</th></tr></thead><tbody>
 ${days.map(w=>`<tr><td>${WDN[w]}</td><td>${wt[w]?`wzrost w <b class="${wt[w].up>=55?"up":wt[w].up<45?"down":"flat"}">${fmt(wt[w].up,0)}%</b> <span class="dim">(${wt[w].n}; ostatnio ${fmt(wt[w].recent_up,0)}%)</span>`:"–"}</td><td>${wn[w]?`<b class="${wn[w].up>=55?"up":wn[w].up<45?"down":"flat"}">${fmt(wn[w].up,0)}%</b> <span class="dim">(${wn[w].n})</span>`:"–"}</td></tr>`).join("")}</tbody></table>
 <p class="note">Np. teoria „w piątki od otwarcia rośnie” – tu widać, jak było naprawdę w ostatnich ~4 latach („ostatnio” = 50 ostatnich takich dni).</p></details>`:""}</section>`}

// ---------- WYNIKI: postęp nauki, dzień / tydzień / miesiąc, dziennik ----------
const KN={pred_4h:"4 godz.",pred_1d:"1 dzień",pred_1w:"tydzień",pred_1m:"miesiąc",rule:"strategie",sim:"transakcje",pick:"propozycje"};
function periodTable(rows,lab){if(!rows||!rows.length)return `<p class="note">Pierwsze wyniki pojawią się, gdy strona rozliczy pierwsze przewidywania (po 4 godzinach / dniu).</p>`;
 const keys=Object.keys(KN).filter(k=>rows.some(r=>r[k]));
 return `<div style="overflow-x:auto"><table class="fc"><thead><tr><th>${lab}</th>${keys.map(k=>`<th>${KN[k]}</th>`).join("")}</tr></thead><tbody>
 ${rows.map(r=>`<tr><td>${esc(r.d)}</td>${keys.map(k=>r[k]?`<td class="${r[k].hit>=65?"up":r[k].hit>=55?"":r[k].hit<50?"down":"flat"}">${fmt(r[k].hit,0)}% <span class="dim">(${r[k].n})</span></td>`:"<td>–</td>").join("")}</tr>`).join("")}</tbody></table></div>`}
let perTab="day";
function learnBox(){const T=D.track||{},SS=D.strat||{},RL=T.rules_live||[];
 const best=[...RL].filter(r=>r.n>=5).sort((a,b)=>b.hit-a.hit)[0],conf=RL.filter(r=>r.status==="confirmed").length,rej=RL.filter(r=>r.status==="rejected").length;
 const P=T.preds||{},bestH=Object.entries(P).filter(([,v])=>v&&v.n>=20).sort((a,b)=>b[1].hit-a[1].hit)[0];
 return `<section class="box"><h3>Postęp nauki – cel: trafność co najmniej 65%</h3>
 <div class="tiles"><div class="tile"><b>Sprawdzone hipotezy</b><span>${SS.tested||0}</span></div><div class="tile"><b>Odkryte reguły</b><span>${SS.found||0}</span></div>
 <div class="tile"><b>Przeszły test</b><span class="up">${SS.ok||0}</span></div><div class="tile"><b>Potwierdzone na żywo (≥65%)</b><span class="${conf?"up":"flat"}">${conf}</span></div>
 <div class="tile"><b>Odrzucone na żywo</b><span class="${rej?"down":"flat"}">${rej}</span></div><div class="tile"><b>Najlepsza na żywo</b><span class="${best&&best.hit>=65?"up":"flat"}">${best?fmt(best.hit,0)+"%":"–"}</span><small class="dim" style="display:block;font-size:11.5px">${best?best.n+" sprawdzeń":"czeka na dane"}</small></div></div>
 <p class="note">Strona pracuje bez przerwy: co ~5 minut zapisuje przewidywania i sprawdza stare, codziennie od nowa szuka strategii i trenuje model. Reguła jest uznana za potwierdzoną, gdy na żywo trafi w co najmniej 65% z min. 15 przypadków; poniżej 50% – zostaje odrzucona. ${bestH?`Najlepszy horyzont przewidywań na żywo: ${KN["pred_"+bestH[0]]} – ${fmt(bestH[1].hit,0)}%.`:""} Osiągnięcie 65% nie jest gwarantowane – rynki są trudne do przewidzenia; strona pokaże uczciwie, czy i gdzie się udało.</p></section>
 <section class="box"><h3>Wyniki własnych testów</h3>
 <div class="seg" role="group" aria-label="Okres" style="margin-bottom:10px"><button data-per="day" aria-pressed="${perTab==="day"}">Dzień po dniu</button><button data-per="week" aria-pressed="${perTab==="week"}">Tydzień po tygodniu</button><button data-per="month" aria-pressed="${perTab==="month"}">Miesiąc po miesiącu</button></div>
 ${periodTable({day:T.by_day,week:T.by_week,month:T.by_month}[perTab],{day:"Dzień",week:"Tydzień",month:"Miesiąc"}[perTab])}
 <p class="note">W komórkach: trafność (w nawiasie liczba rozliczonych) według dnia rozliczenia. Kolumny: przewidywania kierunku na 4 godz. / dzień / tydzień / miesiąc, strategie odkryte przez stronę, wirtualne transakcje (zyskowne), propozycje z „Teraz warto” (zyskowne).</p></section>
 ${(SS.best||[]).length?`<section class="box"><h3>Najlepsze strategie znalezione przez stronę</h3><ul class="clean nlist small">${SS.best.map(r=>{const L=RL.find(x=>x.rid===r.id+"|"+r.sym);return `<li><span class="dotc" style="background:var(--${r.dir==="up"?"up":"down"})"></span><span><a href="#i=${encodeURIComponent(r.sym)}/prognoza"><b>${esc(r.name)}</b></a>: ${esc(r.text)} → ${r.dir==="up"?"wzrost":"spadek"} ${esc(r.target)}<span class="nmeta">test na nowych danych ${fmt(r.test[1],0)}% (${r.test[0]}) · cała historia ${fmt(r.all[1],0)}% (${r.all[0]})${L?` · na żywo ${fmt(L.hit,0)}% (${L.n})`:" · na żywo: czeka"}</span></span></li>`}).join("")}</ul>
 <p class="note">Uwaga: część reguł wypada świetnie w historii, ale słabiej na nowych danych – to normalne przy testowaniu wielu hipotez. Dlatego liczy się wynik „na żywo”.</p></section>`:""}
 ${(T.log||[]).length?`<section class="box"><h3>Dziennik nauki</h3><ul class="clean nlist small">${T.log.slice(0,25).map(x=>`<li><span class="dotc" style="background:var(--${x.kind==="good"||x.kind==="new"?"up":x.kind==="bad"?"down":"info"})"></span><span>${esc(x.text)}<span class="nmeta">${ago(x.t)}</span></span></li>`).join("")}</ul></section>`:""}`}

// ---------- nawigacja ----------
function route(){if(!D)return;const h=decodeURIComponent(location.hash.slice(1));
 let v="rynki";const m=h.match(/^i=([^/]+)(?:\/(\w+))?$/);
 if(m)v="detail";else if(["teraz","kalendarz","dziennik","wyniki","poradnik"].includes(h))v=h;
 document.querySelectorAll(".nav a").forEach(a=>a.setAttribute("aria-current",a.dataset.v===(v==="detail"?"rynki":v)?"page":"false"));
 if(v==="detail")viewDetail(m[1],m[2]);else({rynki:viewRynki,teraz:viewTeraz,kalendarz:viewKalendarz,dziennik:viewDziennik,wyniki:viewWyniki,poradnik:viewPoradnik})[v]();
 updBadge();
 if(!m||!m[2])window.scrollTo(0,0)}
document.addEventListener("click",e=>{const t=e.target;
 const h=t.closest("[data-heart]");if(h){e.stopPropagation();const s=h.dataset.heart;fav=fav.includes(s)?fav.filter(x=>x!==s):[...fav,s];store.set("fav",fav);
  document.querySelectorAll(`[data-heart="${CSS.escape(s)}"]`).forEach(b=>{const f=fav.includes(s);b.setAttribute("aria-pressed",f);b.textContent=f?"♥":"♡"});if($("out"))renderList();updBadge();return}
 const pe=t.closest("[data-per]");if(pe){perTab=pe.dataset.per;viewWyniki();return}
 const po=t.closest("[data-pot]");if(po){potH=po.dataset.pot;store.set("potH",potH);route();return}
 const te=t.closest("[data-test]");if(te){addTest(item(curSym()),te.dataset.test);return}
 const th=t.closest("[data-th]");if(th){terazH=th.dataset.th;store.set("terazH",terazH);viewTeraz();return}
 const ao=t.closest("[data-annon]");if(ao){annOn=!annOn;store.set("annOn",annOn);ao.setAttribute("aria-pressed",annOn);drawChart(item(curSym()));return}
 const ak=t.closest("[data-annk]");if(ak){annInfo(ak.dataset.annk,ak.dataset.ap);return}
 const ad=t.closest("[data-add]");if(ad){requestAdd(ad.dataset.add);return}
 if(t.closest("#addBtn")){const q=$("addQ");requestAdd(q.value);q.value="";$("pend").innerHTML=pendingHtml();return}
 if(t.closest("[data-remove]")){requestRemove(item(curSym()));return}
 const cm=t.closest("[data-cm]");if(cm){chartMode=cm.dataset.cm;store.set("chartMode",chartMode);document.querySelectorAll("[data-cm]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.cm===chartMode));selCandle=null;drawChart(item(curSym()));return}
 const cp=t.closest("[data-cpick]");if(cp){selCandle=+cp.dataset.cpick;drawChart(item(curSym()));$("cw").scrollIntoView({behavior:"smooth",block:"center"});return}
 const o=t.closest("[data-open]");if(o){location.hash="i="+encodeURIComponent(o.dataset.open);return}
 if(t.closest("[data-back]")){history.length>1?history.back():(location.hash="#rynki");return}
 const tb=t.closest("[data-tab]");if(tb){const m=decodeURIComponent(location.hash.slice(1)).match(/^i=([^/]+)/);if(m){history.replaceState(null,"","#i="+encodeURIComponent(m[1])+"/"+tb.dataset.tab);route();window.scrollTo(0,$("tab").offsetTop-120)}return}
 const r=t.closest("[data-r]");if(r){range=r.dataset.r;selCandle=null;store.set("range2",range);document.querySelectorAll("[data-r]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.r===range));drawChart(item(curSym()));return}
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
loadData().then(d=>{D=d;resolveTests();if(!location.hash)history.replaceState(null,"","#teraz");route()})
 .catch(()=>{$("app").innerHTML='<div class="msg" style="margin-top:20px">Nie udało się wczytać danych (data.json). Spróbuj odświeżyć stronę za chwilę.</div>'});
