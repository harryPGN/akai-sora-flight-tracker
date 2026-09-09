/* AKAI SORA — frontend logic */
"use strict";

const API = (() => {
  // deploy_website rewrites the literal __PORT_8000__ token to a proxy URL.
  // When served locally by FastAPI the token is untouched -> use same-origin.
  const raw = "__PORT_8000__";
  return raw.startsWith("__PORT") ? "" : raw;
})();
const POLL_MS = 8000;
const TIMEOUT_MS = 7000;   // client fetch timeout — generous vs backend's 4s OpenSky timeout so the demo fallback can arrive
const BACKOFF_MS = 30000;

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const fmt = (n, d=0) => (n===null||n===undefined) ? "—" : Number(n).toFixed(d);
const kmh = (ms) => (ms==null?null:Math.round(ms*3.6));
const kt = (ms) => (ms==null?null:Math.round(ms*1.94384));
const ft = (m) => (m==null?null:Math.round(m*3.28084));

/* ---------- aircraft SVG silhouettes ---------- */
const SVG = {
  jet: '<path d="M12 1.5l1.6 6.4 7.9 3.2-7.9 1.6L12 22.5l-1.6-9.8L2.5 11.1l7.9-3.2z"/>',
  heavy: '<path d="M12 2l1.4 5.6 6.6 2.6-6.6 1.4L12 22l-1.4-10.4L4 10.2l6.6-2.6z"/>',
  turboprop: '<path d="M12 3l1.2 4.6 4.4 1.8-4.4 1L12 21l-1.2-10.6L6.4 9.4l4.4-1.8z"/><circle cx="12" cy="12" r="1.4"/>',
  rotorcraft: '<path d="M3 11h18M12 5v14"/><circle cx="12" cy="11" r="2.4"/>',
  light: '<path d="M12 4l1 4 4 1.5-4 1L12 20l-1-9.5L7 9.5l4-1.5z"/>',
  medium: '<path d="M12 2l1.5 5.8 7 2.8-7 1.4L12 22l-1.5-10L4 9.6l7-2.8z"/>',
};
function symbolSvg(sym){ return SVG[sym] || SVG.medium; }

function makeIcon(flight, {livery, dimGround}){
  const rot = flight.trueTrack!=null ? flight.trueTrack : 0;
  const dim = dimGround && flight.onGround;
  const gold = livery ? " livery" : "";
  const ground = dim ? " ground" : "";
  return L.divIcon({
    className:"acf-marker",
    html:`<svg class="acf-icon${gold}${ground}" viewBox="0 0 24 24" style="transform:rotate(${rot}deg)">${symbolSvg(flight.symbol)}</svg>`,
    iconSize:[26,26], iconAnchor:[13,13], popupAnchor:[0,-12],
  });
}

/* ---------- state ---------- */
let map, layerMarkers, layerPredicted;
let flights = [];
let liverySet = new Set();
let selectedIcao = null;
let lastFetchOk = true;
let backoffUntil = 0;
let pollTimer = null;
let inFlight = false;
const markerByIcao = {};
let LIVERIES = [];
let SPECS = [];

/* ---------- view switching ---------- */
function switchView(name){
  $$(".view").forEach(v=>v.classList.remove("active"));
  $("#view-"+name).classList.add("active");
  $$(".nav-link").forEach(a=>a.classList.toggle("active", a.dataset.view===name));
  if(name==="map" && map){ setTimeout(()=>map.invalidateSize(),120); }
  $("#sidebar").classList.remove("open");
}
$$(".nav-link").forEach(a=>a.addEventListener("click",()=>switchView(a.dataset.view)));
$("#navToggle").addEventListener("click",()=>$("#sidebar").classList.toggle("open"));

/* ---------- status ---------- */
function setStatus(kind, text){
  $("#apiStatus").className = "status-dot "+kind;
  $("#apiStatusText").textContent = text;
}

/* ---------- map ---------- */
function initMap(){
  map = L.map("flightMap",{zoomControl:true,attributionControl:true}).setView([28,135],4);
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",{
    maxZoom:18, attribution:'Tiles &copy; Esri · Source: Esri, HERE, Garmin · Flight data: OpenSky Network',
  }).addTo(map);
  layerMarkers = L.layerGroup().addTo(map);
  layerPredicted = L.layerGroup().addTo(map);

  // re-fetch when user finishes panning/zooming
  let panT;
  map.on("moveend zoomend",()=>{ clearTimeout(panT); panT=setTimeout(fetchFlights,400); });
}

function bbox(){
  const b = map.getBounds();
  return {lamin:b.getSouth(),lomin:b.getWest(),lamax:b.getNorth(),lomax:b.getEast()};
}

async function fetchFlights(){
  if(inFlight) return;
  const now = Date.now();
  if(now < backoffUntil){ schedulePoll(BACKOFF_MS); return; }
  inFlight = true;
  const ctrl = new AbortController();
  const t = setTimeout(()=>ctrl.abort(), TIMEOUT_MS);
  try{
    const q = new URLSearchParams(bbox()).toString();
    const r = await fetch(`${API}/api/flights?${q}`,{signal:ctrl.signal});
    if(!r.ok) throw new Error("HTTP "+r.status);
    const data = await r.json();
    lastFetchOk = true;
    flights = data.flights;
    liverySet = new Set(data.liveryMatches);
    renderMarkers(data);
    updateHomeStats(data);
    setStatus("ok", `${data.source.toUpperCase()} · ${data.count} aircraft · updated ${new Date().toLocaleTimeString()}`);
    const badge = $("#mapStatus");
    badge.textContent = `Source: ${data.source.toUpperCase()} · ${data.count} aircraft`;
    badge.className = "badge "+(data.source==="opensky"?"live":"demo");
    schedulePoll(POLL_MS);
  }catch(err){
    lastFetchOk = false;
    backoffUntil = Date.now()+BACKOFF_MS;
    setStatus("warn", `Live data slow — using fallback, retry in 30s`);
    $("#mapStatus").textContent = "Data unavailable — back-off 30s";
    $("#mapStatus").className = "badge demo";
    schedulePoll(BACKOFF_MS);
  }finally{
    clearTimeout(t); inFlight=false;
  }
}
function schedulePoll(ms){ clearTimeout(pollTimer); pollTimer=setTimeout(fetchFlights, ms); }

function renderMarkers(data){
  const dimGround = $("#dimGround").checked;
  const followLivery = $("#followLivery").checked;
  const seen = new Set();
  flights.forEach(f=>{
    if(f.latitude==null||f.longitude==null) return;
    const isLivery = liverySet.has(f.icao24);
    seen.add(f.icao24);
    let mk = markerByIcao[f.icao24];
    const icon = makeIcon(f,{livery:followLivery&&isLivery, dimGround});
    if(!mk){
      mk = L.marker([f.latitude,f.longitude],{icon}).addTo(layerMarkers);
      mk.on("click",()=>selectAircraft(f.icao24));
      markerByIcao[f.icao24]=mk;
    }else{
      mk.setLatLng([f.latitude,f.longitude]);
      mk.setIcon(icon);
    }
    if(f.icao24===selectedIcao){ updateDetail(f); }
  });
  // remove stale markers
  Object.keys(markerByIcao).forEach(k=>{
    if(!seen.has(k)){ layerMarkers.removeLayer(markerByIcao[k]); delete markerByIcao[k]; }
  });
}

/* ---------- aircraft detail ---------- */
async function selectAircraft(icao24){
  selectedIcao = icao24;
  const f = flights.find(x=>x.icao24===icao24);
  if(f) updateDetail(f);
  // predicted path
  try{
    const r = await fetch(`${API}/api/predict?icao24=${encodeURIComponent(icao24)}&minutes=12`);
    if(r.ok){ const d = await r.json(); drawPredicted(d.path, d.flight); }
  }catch(e){}
}
function updateDetail(f){
  const spec = SPECS.find(s=>s.typecode===(f.typecode||"").toUpperCase());
  const livery = LIVERIES.find(l=>l.icao24.toLowerCase()===f.icao24);
  const el = $("#detailPanel");
  const rows = [
    ["Aircraft type", f.typecode?`${f.typecode}${spec?" · "+spec.model:""}`:"Unknown"],
    ["Registration", f.registration||"—"],
    ["Callsign", f.callsign||"—"],
    ["Origin country", f.originCountry],
    ["Status", f.onGround?"On ground":"Airborne"],
    ["Barometric altitude", fmt(f.baroAltitude)+" m ("+fmt(f.baroAltitude!=null?f.baroAltitude*3.281:0,0)+" ft)"],
    ["Geo altitude", fmt(f.geoAltitude)+" m"],
    ["Ground speed", fmt(kmh(f.velocity))+" km/h ("+fmt(kt(f.velocity))+" kt)"],
    ["True heading", fmt(f.trueTrack,0)+"°"],
    ["Vertical rate", fmt(f.verticalRate!=null?f.verticalRate:0,1)+" m/s"],
    ["Position source", ["ADS-B","ASTERIX","MLAT","FLARM"][f.positionSource]||"Unknown"],
    ["Last contact", new Date(f.lastContact*1000).toLocaleTimeString()],
  ];
  const specRows = spec ? [
    ["Engines", spec.engines],
    ["Thrust", spec.thrustKN+" kN"],
    ["Length / Span", spec.lengthM+" / "+spec.wingspanM+" m"],
    ["MTOW", (spec.mtowKg/1000).toFixed(1)+" t"],
    ["Max range", spec.rangeKm+" km"],
    ["Cruise", spec.cruiseSpeedKmh+" km/h (M"+spec.cruiseMach+")"],
    ["Service ceiling", spec.ceilingM+" m"],
    ["Max passengers", spec.maxPax],
  ] : [];
  el.innerHTML = `
    ${livery&&livery.photoUrl?`<img class="livery-photo" src="${livery.photoUrl}" alt="${livery.liveryName}"><div class="photo-credit">Photo: Wikimedia Commons</div>`:""}
    <div class="detail-head">
      <div class="callsign">${f.callsign||f.icao24.toUpperCase()}</div>
      ${f.livery?`<span class="livery-tag">★ ${f.livery}</span>`:""}
    </div>
    <div class="detail-section">Live Telemetry</div>
    ${rows.map(r=>`<div class="detail-row"><span>${r[0]}</span><span>${r[1]}</span></div>`).join("")}
    ${specRows.length?`<div class="detail-section">Engineering Spec</div>${specRows.map(r=>`<div class="detail-row"><span>${r[0]}</span><span>${r[1]}</span></div>`).join("")}`:""}
  `;
}
function drawPredicted(path, flight){
  layerPredicted.clearLayers();
  if(!path||path.length<2) return;
  // current position solid, future dashed
  L.polyline(path,{color:"#ff2a3a",weight:2,opacity:.9}).addTo(layerPredicted);
  L.circleMarker(path[path.length-1],{radius:3,color:"#ff2a3a"}).addTo(layerPredicted);
}

/* ---------- home ---------- */
function updateHomeStats(data){
  $("#statFlights").textContent = data.count;
  $("#statFlightsSource").textContent = data.source==="opensky"?"live OpenSky":(data.source+" fallback");
  $("#statSource").textContent = data.source==="opensky"?"OpenSky Live":(data.source==="demo"?"Demo data":"Cached");
  $("#statUpdated").textContent = "updated "+new Date().toLocaleTimeString();
}
async function loadHomeStatic(){
  try{
    const [livR, specR] = await Promise.all([
      fetch(`${API}/api/liveries`).then(r=>r.json()),
      fetch(`${API}/api/specs`).then(r=>r.json()),
    ]);
    LIVERIES = livR; SPECS = specR;
    $("#statLiveries").textContent = livR.length;
    $("#statTypes").textContent = specR.length;
    renderLiveryList();
    renderDbTable(specR);
  }catch(e){}
}

async function loadNews(){
  try{
    const items = await fetch(`${API}/api/news`).then(r=>r.json());
    $("#newsList").innerHTML = items.slice(0,8).map(n=>`
      <li><a href="${n.link}" target="_blank" rel="noopener">${n.title}</a>
      <div class="news-sum">${n.summary||""}</div></li>`).join("");
  }catch(e){ $("#newsList").innerHTML="<li>News unavailable.</li>"; }
}

async function loadWeather(){
  const ap = $("#wxAirport").value.trim().toUpperCase()||"VHHH";
  $("#weatherResult").innerHTML="<span class='muted small'>Loading…</span>";
  try{
    const d = await fetch(`${API}/api/weather?airport=${ap}`).then(r=>r.json());
    if(!d.available){ $("#weatherResult").innerHTML=`<span class='muted small'>${d.error||"No data"}</span>`; return; }
    $("#weatherResult").innerHTML=`
      <div class="wx-row"><span>Station</span><span>${d.station} — ${d.name||""}</span></div>
      <div class="wx-row"><span>Temperature</span><span>${fmt(d.temperatureC,1)} °C</span></div>
      <div class="wx-row"><span>Dew point</span><span>${fmt(d.dewpointC,1)} °C</span></div>
      <div class="wx-row"><span>Wind</span><span>${d.windDir}° ${d.windSpeedKt} kt</span></div>
      <div class="wx-row"><span>Visibility</span><span>${d.visibilityM?Math.round(d.visibilityM)+" m":"—"}</span></div>
      <div class="wx-row"><span>Ceiling</span><span>${d.ceilingM?Math.round(d.ceilingM)+" m":"—"}</span></div>
      <div class="wx-row"><span>Category</span><span>${d.fltCat||"—"}</span></div>
      <div class="wx-row"><span>QNH</span><span>${d.altimHpa||"—"} hPa</span></div>
      <div class="metar-raw">${d.raw||""}</div>`;
  }catch(e){ $("#weatherResult").innerHTML="<span class='muted small'>Error</span>"; }
}
async function loadDisruption(){
  const ap = $("#disrAirport").value.trim().toUpperCase()||"VHHH";
  $("#disruptionResult").innerHTML="<span class='muted small'>Analyzing…</span>";
  try{
    const d = await fetch(`${API}/api/disruption?airport=${ap}`).then(r=>r.json());
    if(d.index===null){ $("#disruptionResult").innerHTML=`<span class='muted small'>${d.metar&&d.metar.error?d.metar.error:"No data"}</span>`; return; }
    const f=d.factors||{};
    $("#disruptionResult").innerHTML=`
      <div style="display:flex;justify-content:space-between"><strong>${d.label}</strong><span>${d.index}/100</span></div>
      <div class="disr-bar"><span style="width:${d.index}%"></span></div>
      <div class="muted small">Wind ${f.wind||0} · Visibility ${f.lowVisibility||0} · Ceiling ${f.lowCeiling||0} · Cat ${f.flightCategory||0}</div>
      <div class="muted small" style="margin-top:6px">${d.metar?d.metar.raw:""}</div>`;
  }catch(e){ $("#disruptionResult").innerHTML="<span class='muted small'>Error</span>"; }
}

/* ---------- livery tracker ---------- */
function renderLiveryList(){
  const q = ($("#liverySearch").value||"").toLowerCase();
  const items = LIVERIES.filter(l=>!q || l.airline.toLowerCase().includes(q)
    || l.liveryName.toLowerCase().includes(q) || l.registration.toLowerCase().includes(q));
  $("#liveryList").innerHTML = items.map(l=>{
    const flying = liverySet.has(l.icao24.toLowerCase());
    const dot = flying?"":" offline";
    return `<li class="livery-item" data-icao="${l.icao24.toLowerCase()}">
      <span class="livery-gold-dot${dot}"></span>
      <div><div class="l-name">${l.liveryName}</div>
      <div class="l-meta">${l.airline} · ${l.registration} · ${l.model}</div></div>
    </li>`;
  }).join("");
  $$("#liveryList .livery-item").forEach(el=>{
    el.addEventListener("click",()=>showLivery(el.dataset.icao));
  });
}
function showLivery(icao){
  const l = LIVERIES.find(x=>x.icao24.toLowerCase()===icao);
  if(!l) return;
  $$("#liveryList .livery-item").forEach(e=>e.classList.toggle("sel",e.dataset.icao===icao));
  const flying = liverySet.has(icao);
  const f = flying ? flights.find(x=>x.icao24===icao) : null;
  const spec = SPECS.find(s=>s.typecode===(l.typecode||"").toUpperCase());
  $("#liveryDetail").innerHTML = `
    ${l.photoUrl?`<img class="livery-photo" src="${l.photoUrl}" alt="${l.liveryName}"><div class="photo-credit">Photo: Wikimedia Commons · ${l.registration}</div>`:"<div class='detail-empty'>No photo available</div>"}
    <div class="detail-head">
      <div class="callsign">${l.liveryName}</div>
      <span class="livery-tag">★ Special Livery</span>
    </div>
    <div class="detail-section">Identity</div>
    <div class="detail-row"><span>Airline</span><span>${l.airline}</span></div>
    <div class="detail-row"><span>Registration</span><span>${l.registration}</span></div>
    <div class="detail-row"><span>ICAO24</span><span>${l.icao24}</span></div>
    <div class="detail-row"><span>Aircraft</span><span>${l.model}${spec?" · "+l.typecode:""}</span></div>
    <div class="detail-row"><span>Country</span><span>${l.country}</span></div>
    <div class="detail-row"><span>Theme</span><span>${l.theme}</span></div>
    <div class="detail-section">Live Status</div>
    <div class="detail-row"><span>Tracking</span><span>${flying?"In flight now":"Not currently transmitting"}</span></div>
    ${f?`<div class="detail-row"><span>Ground speed</span><span>${fmt(kmh(f.velocity))} km/h</span></div>
    <div class="detail-row"><span>Altitude</span><span>${fmt(f.baroAltitude)} m</span></div>
    <div class="detail-row"><span>Heading</span><span>${fmt(f.trueTrack,0)}°</span></div>
    <div class="detail-row"><span>Last contact</span><span>${new Date(f.lastContact*1000).toLocaleTimeString()}</span></div>`
    :`<div class="detail-row"><span>ADS-B</span><span>Off — last known position unavailable</span></div>`}
    ${spec?`<div class="detail-section">Engineering Spec</div>
    <div class="detail-row"><span>Engines</span><span>${spec.engines}</span></div>
    <div class="detail-row"><span>MTOW</span><span>${(spec.mtowKg/1000).toFixed(1)} t</span></div>
    <div class="detail-row"><span>Range</span><span>${spec.rangeKm} km</span></div>`:""}
    <div class="detail-section">About</div>
    <div class="detail-row"><span style="max-width:280px">${l.description}</span></div>
  `;
  // if flying, fly map to it
  if(flying && map){
    switchView("map");
    setTimeout(()=>{ map.flyTo([f.latitude,f.longitude],7,{duration:1.2}); selectAircraft(icao); },200);
  }
}

/* ---------- aircraft database ---------- */
function renderDbTable(specs){
  const q = ($("#dbSearch").value||"").toLowerCase();
  const rows = specs.filter(s=>!q || s.model.toLowerCase().includes(q) || s.manufacturer.toLowerCase().includes(q) || s.typecode.toLowerCase().includes(q));
  $("#dbBody").innerHTML = rows.map(s=>`
    <tr data-tc="${s.typecode}">
      <td>${s.typecode}</td><td>${s.model}</td><td>${s.category}</td><td>${s.engines}</td>
      <td>${s.thrustKN}</td><td>${s.lengthM}</td><td>${s.wingspanM}</td>
      <td>${(s.mtowKg/1000).toFixed(1)}</td><td>${s.rangeKm}</td><td>${s.cruiseSpeedKmh}</td>
      <td>${s.ceilingM}</td><td>${s.maxPax}</td>
    </tr>`).join("");
  $$("#dbBody tr").forEach(tr=>tr.addEventListener("click",()=>showSpec(tr.dataset.tc)));
}
function showSpec(tc){
  const s = SPECS.find(x=>x.typecode===tc);
  if(!s) return;
  $("#dbDetail").innerHTML = `
    <div class="card" style="padding:16px;margin-top:12px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong style="font-size:18px">${s.model}</strong>
        <span class="badge">${s.typecode}</span>
      </div>
      <div style="color:var(--muted);font-size:13px;margin-bottom:10px">${s.manufacturer} · ${s.category} · ${s.inService?"In service":"Retired"}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 24px;font-size:13px">
        <div class="detail-row"><span>Engines</span><span>${s.engines}</span></div>
        <div class="detail-row"><span>Thrust</span><span>${s.thrustKN} kN</span></div>
        <div class="detail-row"><span>Length</span><span>${s.lengthM} m</span></div>
        <div class="detail-row"><span>Wingspan</span><span>${s.wingspanM} m</span></div>
        <div class="detail-row"><span>Height</span><span>${s.heightM} m</span></div>
        <div class="detail-row"><span>MTOW</span><span>${(s.mtowKg/1000).toFixed(1)} t</span></div>
        <div class="detail-row"><span>Max landing</span><span>${(s.mlwKg/1000).toFixed(1)} t</span></div>
        <div class="detail-row"><span>Fuel capacity</span><span>${s.fuelCapacityL} L</span></div>
        <div class="detail-row"><span>Range</span><span>${s.rangeKm} km</span></div>
        <div class="detail-row"><span>Cruise speed</span><span>${s.cruiseSpeedKmh} km/h</span></div>
        <div class="detail-row"><span>Cruise Mach</span><span>M${s.cruiseMach}</span></div>
        <div class="detail-row"><span>Service ceiling</span><span>${s.ceilingM} m</span></div>
        <div class="detail-row"><span>Max passengers</span><span>${s.maxPax}</span></div>
        <div class="detail-row"><span>First flight</span><span>${s.firstFlightYear}</span></div>
      </div>
    </div>`;
  $("#dbDetail").scrollIntoView({behavior:"smooth"});
}

/* ---------- wire up ---------- */
$("#disrBtn").addEventListener("click",loadDisruption);
$("#wxBtn").addEventListener("click",loadWeather);
$("#disrAirport").addEventListener("keydown",e=>{if(e.key==="Enter")loadDisruption();});
$("#wxAirport").addEventListener("keydown",e=>{if(e.key==="Enter")loadWeather();});
$("#liverySearch").addEventListener("input",renderLiveryList);
$("#dbSearch").addEventListener("input",()=>renderDbTable(SPECS));
$("#dimGround").addEventListener("change",()=>{ if(flights.length) renderMarkers({flights}); });
$("#followLivery").addEventListener("change",()=>{ if(flights.length) renderMarkers({flights}); });

/* ---------- boot ---------- */
(async function init(){
  initMap();
  setStatus("warn","connecting to OpenSky…");
  await loadHomeStatic();
  loadNews();
  loadWeather(); loadDisruption();
  fetchFlights();
})();
