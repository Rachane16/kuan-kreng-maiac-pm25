/* Static MAIAC viewer. No NASA credentials or model are used in the browser. */
(() => {
  const $ = (id) => document.getElementById(id);
  const dateInput = $("date-input");
  const slider = $("date-range");
  const status = $("selection-status");
  let history;
  let datasets, selectedSource='maiac', camsLayer, savedMaiacMode='idw';
  const maiacOptions=$('display-mode').innerHTML;
  let map;
  let gridLayer;
  let layerById = new Map();
  let selectedIndex = 0;
  let targets = [];
  let basemaps;
  let activeBasemap;
  const idwCache = new Map();
  const surfaceCache = new Map();
  let surfaceLayer, surfaceJob=0, currentSampler=null, gridData, utmProject;

  async function showSurface(day, points) {
    const job=++surfaceJob;
    if(surfaceLayer){map.removeLayer(surfaceLayer);surfaceLayer=null;}
    currentSampler=KKIDW.createSampler(points);
    if(!currentSampler)return;
    const note=$('view-note');
    note.textContent=`กำลังสร้างผืนสี IDW · ใช้ ${points.length.toLocaleString('th-TH')} จุดตั้งต้น`;
    try {
      let surface=surfaceCache.get(day.date);
      if(!surface){
        surface=await KKSurface.render(gridData,gridLayer.getBounds(),currentSampler,utmProject,()=>job!==surfaceJob);
        if(!surface || job!==surfaceJob)return;
        surfaceCache.set(day.date,surface);
        if(surfaceCache.size>3)surfaceCache.delete(surfaceCache.keys().next().value);
      }
      if(job!==surfaceJob)return;
      surfaceLayer=L.imageOverlay(surface.url,gridLayer.getBounds(),{opacity:.64,interactive:false,className:'idw-surface'}).addTo(map);
      note.textContent=`ผืนสีต่อเนื่อง IDW · ใช้ ${points.length.toLocaleString('th-TH')} จุดตั้งต้น · คลิกแผนที่เพื่อดูค่าประมาณ ณ ตำแหน่งนั้น`;
    } catch(error) {
      if(job!==surfaceJob)return;
      currentSampler=null;
      note.textContent='ไม่สามารถสร้างผืนสี IDW ได้ กรุณาลองเลือกวันที่อีกครั้ง';
    }
  }

  const thaiDate = (iso) => new Date(`${iso}T00:00:00Z`).toLocaleDateString("th-TH", {
    timeZone: "UTC", day: "numeric", month: "short", year: "numeric"
  });
  const thaiTime = (iso) => iso ? new Date(iso).toLocaleString("th-TH", {
    timeZone: "Asia/Bangkok", day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit"
  }) : "ไม่ระบุเวลา";
  const percent = (n, total) => total ? (100 * n / total).toFixed(n && n / total < .01 ? 1 : 0) + "%" : "0%";
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[c]);

  function color(value) {
    return value <= 15 ? "#95dcff" : value <= 25 ? "#beea8f" : value <= 37.5 ? "#ffe593" : value <= 75 ? "#ffc295" : "#da8b85";
  }

  function statusText(day) {
    if(selectedSource==='cams'){
      if(day.status==='Available')return `CAMS มีข้อมูลครบ 24 ชั่วโมง ${day.available_cells} ช่องกริดต้นทาง`;
      if(day.status==='Incomplete')return 'ข้อมูล CAMS ของวันเลือกยังไม่ครบ 24 ชั่วโมง';
      if(day.status==='NoData')return 'CAMS ไม่มี AOD ที่ใช้ประเมินรายวันได้ครบ 24 ชั่วโมง';
      return 'ยังไม่มีข้อมูล CAMS ที่ประมวลผลแล้วสำหรับวันที่เลือก';
    }
    if (day.status === "Available") return `พบ AOD ผ่าน QA ${day.available_cells.toLocaleString("th-TH")} ช่องในวันที่เลือก`;
    if (day.status === "NoData") return "NASA มีไฟล์ของวันนี้ แต่ไม่มี AOD ในพื้นที่ที่ผ่าน QA";
    if (day.status === "NotPublished") return "NASA ยังไม่มีไฟล์ของวันที่เลือกสำหรับพื้นที่นี้";
    return "ยังไม่ได้ตรวจข้อมูลของวันที่เลือก";
  }

  function popupContent(gridId, sample, estimate) {
    const heading = `<div class="popup-label">กริด 1 × 1 กม.</div><div class="popup-id">${escapeHtml(gridId)}</div>`;
    if (!sample && estimate) return heading + `<div class="popup-value">${estimate.value.toFixed(2)} <small>µg/m³</small></div>`
      + `<div class="popup-meta"><strong>ค่าประมาณด้วย IDW</strong><br>ไม่มี AOD ผ่าน QA ณ ช่องนี้<br>จุดตั้งต้นใกล้ที่สุด: ${(estimate.distance / 1000).toFixed(2)} กม.<br>ใช้ ${estimate.neighbours} จุดใกล้ที่สุดของวันเดียวกัน</div>`;
    if (!sample) return heading + `<div class="popup-nodata">ไม่มี AOD ผ่าน QA ในวันนี้</div>`;
    return heading + `<div class="popup-value">${Number(sample[2]).toFixed(2)} <small>µg/m³</small></div>`
      + `<div class="popup-meta">PM₂.₅ ประเมินจากโมเดล<br>AOD 470 nm: ${Number(sample[1]).toFixed(3)}<br>เวลาผ่านพื้นที่: ${escapeHtml(thaiTime(sample[3]))}<br>รอบผ่านที่ใช้ได้: ${Number(sample[4])}</div>`;
  }

  function render() {
    const day = history.days[selectedIndex];
    const samples = new Map(day.cells.map(item => [item[0], item]));
    const isCams=selectedSource==='cams';
    const idwMode = !isCams && $("display-mode").value === "idw";
    if (idwMode && !idwCache.has(day.date)) {
      const points = targets.filter(t => samples.has(t.id)).map(t => ({...t, value:Number(samples.get(t.id)[2])}));
      idwCache.set(day.date, KKIDW.interpolate(points, targets));
    }
    const result = idwMode ? idwCache.get(day.date) : null;
    const estimates = new Map(result?.values.map(item => [item.id, item]) || []);
    const idwAvailable = result?.status === "available";
    const points=targets.filter(t=>samples.has(t.id)).map(t=>({...t,value:Number(samples.get(t.id)[2])}));
    map.closePopup();
    if(!(idwMode && idwAvailable)) {
      surfaceJob++;currentSampler=null;
      if(surfaceLayer){map.removeLayer(surfaceLayer);surfaceLayer=null;}
    }
    const messageText = idwMode && day.available_cells > 0 && !idwAvailable
      ? "ข้อมูลไม่เพียงพอสำหรับ IDW ต้องมีอย่างน้อย 3 จุดที่ไม่เรียงเป็นเส้นเดียวกัน" : statusText(day);
    $("view-note").textContent = idwMode
      ? idwAvailable ? `กำลังแสดงผืนสีต่อเนื่อง IDW · ใช้ ${samples.size.toLocaleString("th-TH")} จุดตั้งต้น`
        : `IDW ยังไม่พร้อม · ${messageText}`
      : isCams ? 'CAMS AOD 550 nm · ค่าเฉลี่ย 24 ชั่วโมงตามเวลาไทย · กริดต้นทาง 0.4° ตัดตามขอบเขตพื้นที่' : "ค่าประเมินจากโมเดล ณ ตำแหน่งที่มี AOD ผ่าน QA";
    $("mean-label").textContent = isCams ? 'ค่าเฉลี่ยพื้นที่จาก CAMS' : idwMode ? "ค่าเฉลี่ยกริด 1 กม. (รวม IDW)" : "ค่าเฉลี่ยของช่องที่มีข้อมูล";
    $("nodata-label").textContent = isCams ? 'ไม่มีข้อมูล CAMS รายวัน' : idwMode ? "ไม่มีค่าประมาณ IDW" : "ไม่มี AOD ผ่าน QA";
    $('cams-time-row').hidden=!isCams;
    $('cams-period').textContent=isCams && day.forecast_base_time ? `${thaiTime(day.period_start_utc)} ถึง ${thaiTime(day.period_end_utc)} (ไม่รวมเวลาสิ้นสุด)` : '—';
    dateInput.value = day.date;
    slider.value = selectedIndex;
    $("map-title").textContent = thaiDate(day.date);
    $("coverage-value").textContent = day.available_cells.toLocaleString("th-TH");
    $("coverage-percent").textContent = percent(day.available_cells, history.grid_count);
    $("coverage-detail").textContent = `จากทั้งหมด ${history.grid_count.toLocaleString("th-TH")} ช่อง`;
    $("coverage-progress").style.width = `${100 * day.available_cells / history.grid_count}%`;
    const areaWeight = targets.reduce((sum,t) => sum + t.weight, 0);
    const mean = idwMode ? idwAvailable ? targets.reduce((sum,t) => sum + estimates.get(t.id).value*t.weight,0)/areaWeight : null : day.mean_pm25;
    $("mean-pm25").textContent = mean === null ? "—" : Number(mean).toFixed(2);
    status.className = `selection-status ${day.status === "Available" ? "available" : "nodata"}`;
    status.lastElementChild.textContent = idwMode ? messageText + (idwAvailable ? " · เติมพื้นที่ด้วย IDW แล้ว" : "") : statusText(day);
    const message = $("map-message");
    message.hidden = idwMode ? idwAvailable : day.status === "Available";
    message.textContent = messageText;
    $("prev-day").disabled = selectedIndex === 0;
    $("next-day").disabled = selectedIndex === history.days.length - 1;
    document.querySelectorAll(".history-bar").forEach((bar, i) => {
      bar.classList.toggle("selected", i === selectedIndex);
      bar.setAttribute("aria-pressed", i === selectedIndex ? "true" : "false");
    });
    if(!isCams)layerById.forEach((layer, gridId) => {
      const sample = samples.get(gridId);
      const estimate = estimates.get(gridId);
      const value = idwMode ? estimate?.value : sample ? Number(sample[2]) : undefined;
      const hasValue = Number.isFinite(value);
      layer.setStyle({
        stroke: !idwMode,
        color: hasValue ? "#536a68" : "#a2b3b0", weight: hasValue ? .55 : .38,
        opacity: hasValue ? .7 : .6,
        fillColor: hasValue ? color(value) : "#bfcbca",
        fillOpacity: idwMode ? 0 : hasValue ? .76 : .34
      });
      layer.unbindPopup();
      if(!idwMode)layer.bindPopup(popupContent(gridId,sample,estimate));
      else if(!idwAvailable)layer.bindPopup(`<div class="popup-nodata">${escapeHtml(messageText)}</div>`);
    });
    if(isCams)camsLayer.eachLayer(layer=>{
      const sample=samples.get(layer.feature.properties.grid_id);
      layer.setStyle({color:'#718b81',weight:.8,fillColor:sample?color(Number(sample[2])):'#bfcbca',fillOpacity:sample ? .72 : .25});
      const base=day.forecast_base_time?thaiTime(day.forecast_base_time):'—';
      const value=sample?`<div class="popup-value">${Number(sample[2]).toFixed(2)} <small>µg/m³</small></div><div class="popup-meta">AOD 550 nm เฉลี่ย: ${Number(sample[1]).toFixed(4)}<br>ข้อมูลครบ ${sample[3]} ชั่วโมง<br>รอบพยากรณ์: ${escapeHtml(base)}<br>Lead time: ${day.lead_time_hours?.join('–')} ชั่วโมง</div>`:'<div class="popup-nodata">ไม่มีข้อมูล CAMS รายวัน</div>';
      layer.unbindPopup();layer.bindPopup(`<div class="popup-label">CAMS · กริดต้นทาง 0.4°</div>${value}`);
    });
    const url = new URL(location.href);
    url.searchParams.set("date", day.date);
    url.searchParams.set('source',selectedSource);
    if(!isCams)url.searchParams.set("view", idwMode ? "idw" : "source");else url.searchParams.delete('view');
    window.history.replaceState(null, "", url);
    if(idwMode && idwAvailable)showSurface(day,points);
  }

  function selectIndex(index) {
    selectedIndex = Math.max(0, Math.min(history.days.length - 1, Number(index)));
    render();
  }

  function buildChart() {
    const chart = $("history-chart");
    chart.replaceChildren();
    const maxCoverage = Math.max(1, ...history.days.map(item => item.available_cells));
    history.days.forEach((day, index) => {
      const bar = document.createElement("button");
      bar.type = "button";
      bar.className = `history-bar ${day.status === "Available" ? "" : day.status === "NotChecked" ? "unchecked" : "nodata"}`;
      bar.style.setProperty("--bar-height", `${Math.max(5, 80 * day.available_cells / maxCoverage)}px`);
      bar.title = `${thaiDate(day.date)} · ${day.available_cells} ช่อง`;
      bar.setAttribute("aria-label", bar.title);
      bar.addEventListener("click", () => selectIndex(index));
      chart.appendChild(bar);
    });
    const daysWithData = history.days.filter(day => day.status === "Available").length;
    $("history-count").textContent = `${daysWithData} / ${history.days.length} วันมีข้อมูล`;
    $("chart-start").textContent = thaiDate(history.start_date);
    $("chart-end").textContent = thaiDate(history.end_date);
  }

  function selectSource(source, wantedDate) {
    if(selectedSource==='maiac')savedMaiacMode=$('display-mode').value;
    selectedSource=source;history=datasets[source];
    const isCams=source==='cams';
    dateInput.setAttribute('aria-label',isCams?'เลือกวันที่ของข้อมูล CAMS':'เลือกวันที่ของข้อมูล MAIAC');
    document.title=`พรุควนเคร็ง | ${isCams?'CAMS':'MAIAC'} PM₂.₅`;
    $('hero-eyebrow').innerHTML=`<span class="eyebrow-line"></span> ${isCams?'CAMS BASED ESTIMATION':'SATELLITE BASED ESTIMATION'}`;
    $('data-source').value=source;
    $('display-mode').innerHTML=isCams?'<option value="cams">การประมาณค่าฝุ่น PM₂.₅</option>':maiacOptions;
    $('display-mode').disabled=isCams;
    if(!isCams)$('display-mode').value=savedMaiacMode;
    if(isCams){if(map.hasLayer(gridLayer))map.removeLayer(gridLayer);camsLayer.addTo(map);}
    else {if(map.hasLayer(camsLayer))map.removeLayer(camsLayer);gridLayer.addTo(map);}
    $('source-description').textContent=isCams?'Copernicus CAMS · AOD 550 nm':'NASA MCD19A2 / MCD19A2N · AOD 470 nm';
    $('resolution-description').textContent=isCams?'0.4° × 0.4° (ประมาณ 44 กม.)':'MAIAC ประมาณ 1 กม.';
    $('map-resolution').textContent=isCams?'กริดต้นทาง 0.4° · ตัดตามขอบเขต':'EPSG:4326 · กริดรายงาน 1 × 1 กม.';
    $('date-timezone-label').textContent=isCams?'วันเฉลี่ยข้อมูล CAMS อ้างอิงเวลาไทย (UTC+7)':'วันที่ของผลิตภัณฑ์ NASA อ้างอิง UTC';
    $('coverage-heading').textContent=isCams?'ช่องกริด CAMS ที่มีข้อมูลครบ 24 ชม.':'พื้นที่กริดที่มี AOD ใช้ได้';
    $('chart-description').textContent=isCams?'ความสูงของแท่งแสดงจำนวนกริด CAMS ต้นทางที่มีข้อมูลครบ 24 ชั่วโมง เลือกแท่งเพื่อเปิดวันที่นั้น':'ความสูงของแท่งแสดงจำนวนช่องที่มี AOD ผ่าน QA เลือกแท่งเพื่อเปิดวันที่นั้น';
    $('cams-method-note').hidden=!isCams;
    $('maiac-method-steps').hidden=isCams;
    $('provider-link').href=isCams?'https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=overview':'https://lpdaac.usgs.gov/products/mcd19a2v061/';
    $('provider-link').textContent=isCams?'Copernicus CAMS · CC-BY ↗':'NASA MAIAC ↗';
    $('provider-documentation').href=isCams?'https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=documentation':'https://lpdaac.usgs.gov/documents/1500/MCD19_User_Guide_V61.pdf';
    $('provider-documentation').textContent=isCams?'คู่มือ CAMS ↗':'คู่มือ QA ↗';
    $('page-title').innerHTML=isCams?'การประมาณค่าฝุ่น PM₂.₅ จาก CAMS<br><em>ในพื้นที่ป่าพรุควนเคร็ง</em>':'การประมาณค่าฝุ่น PM₂.₅ จากดาวเทียม<br><em>ในพื้นที่ป่าพรุควนเคร็ง</em>';
    $('hero-description').textContent=isCams?'ค่าประเมิน PM₂.₅ จาก AOD 550 nm เฉลี่ยรายวันตามเวลาไทย · กริดต้นทาง 0.4°':'ค่าประเมิน PM₂.₅ รายวันจาก AOD บนกริด 1 × 1 กม.';
    $('range-label').textContent=`${history.days.length} วัน`;
    $('range-start').textContent=thaiDate(history.start_date);$('range-end').textContent=thaiDate(history.end_date);
    $('generated-time').textContent=history.generated_at_utc?thaiTime(history.generated_at_utc):'ยังไม่มีชุดข้อมูล';
    dateInput.min=history.start_date;dateInput.max=history.end_date;slider.max=history.days.length-1;
    buildChart();
    const index=history.days.findIndex(d=>d.date===wantedDate);
    $('latest-with-data').disabled=!history.days.some(d=>d.status==='Available');
    selectIndex(index>=0?index:history.days.length-1);
  }

  async function init() {
    try {
      const [gridResponse, historyResponse, boundaryResponse, camsGridResponse, camsHistoryResponse] = await Promise.all([
        fetch("./data/grid.geojson"), fetch("./data/history.json", {cache: "no-store"}), fetch("./data/boundary.geojson"),
        fetch('./data/cams_grid.geojson'),fetch('./data/cams_history.json',{cache:'no-store'})
      ]);
      if (!gridResponse.ok || !historyResponse.ok || !boundaryResponse.ok) throw new Error("โหลดไฟล์ข้อมูลไม่สำเร็จ");
      const [grid, dataset, boundary] = await Promise.all([gridResponse.json(), historyResponse.json(), boundaryResponse.json()]);
      if(!camsGridResponse.ok || !camsHistoryResponse.ok)throw new Error('โหลดข้อมูล CAMS ไม่สำเร็จ');
      const [camsGrid,camsDataset]=await Promise.all([camsGridResponse.json(),camsHistoryResponse.json()]);
      const camsDays=new Map(camsDataset.days.map(d=>[d.date,d]));
      datasets={maiac:dataset,cams:{...camsDataset,start_date:dataset.start_date,end_date:dataset.end_date,
        days:dataset.days.map(d=>camsDays.get(d.date)||{date:d.date,status:'NotPublished',available_cells:0,mean_pm25:null,cells:[]})}};
      if (!window.L || !dataset.days?.length || !grid.features?.length) throw new Error("ข้อมูลแผนที่ไม่สมบูรณ์");
      history = dataset;
      gridData=grid;
      if(!window.proj4 || !window.KKSurface)throw new Error('เครื่องมือแสดงผืนสี IDW ยังไม่พร้อม');
      utmProject=proj4('EPSG:4326','+proj=utm +zone=47 +datum=WGS84 +units=m +no_defs');
      targets = grid.features.map(f => ({id:f.properties.grid_id, x:f.properties.sample_x, y:f.properties.sample_y, weight:f.properties.coverage_fraction}));
      if (targets.some(t => ![t.x,t.y,t.weight].every(Number.isFinite))) throw new Error("พิกัดกริดสำหรับ IDW ไม่สมบูรณ์");
      $("range-label").textContent = `${dataset.days.length} วัน`;
      $("range-start").textContent = thaiDate(dataset.start_date);
      $("range-end").textContent = thaiDate(dataset.end_date);
      $("generated-time").textContent = thaiTime(dataset.generated_at_utc);
      dateInput.min = dataset.start_date;
      dateInput.max = dataset.end_date;
      slider.max = dataset.days.length - 1;
      map = L.map("map", {zoomControl: false, preferCanvas: true, scrollWheelZoom: true});
      L.control.zoom({position: "bottomright"}).addTo(map);
      basemaps = {osm:L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18, opacity: .85
      }), imagery:L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        attribution:"Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",maxZoom:18
      }), topo:L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}", {
        attribution:"Tiles &copy; Esri — Sources: Esri, USGS, NOAA, and the GIS User Community",maxZoom:18
      })};
      activeBasemap = basemaps.osm.addTo(map);
      $("basemap").addEventListener("change", () => { map.removeLayer(activeBasemap); activeBasemap=basemaps[$("basemap").value].addTo(map); });
      gridLayer = L.geoJSON(grid, {
        style: {color: "#a2b3b0", weight: .38, fillColor: "#bfcbca", fillOpacity: .34},
        onEachFeature(feature, layer) {
          layerById.set(feature.properties.grid_id, layer);
          layer.on('click',event=>{
            if(selectedSource!=='maiac' || $('display-mode').value!=='idw' || !currentSampler)return;
            const [x,y]=utmProject.forward([event.latlng.lng,event.latlng.lat]);
            const estimate=currentSampler(x,y);
            L.popup().setLatLng(event.latlng).setContent(`<div class="popup-label">IDW ณ ตำแหน่งที่เลือก</div><div class="popup-value">${estimate.value.toFixed(2)} <small>µg/m³</small></div>`).openOn(map);
          });
        }
      }).addTo(map);
      camsLayer=L.geoJSON(camsGrid,{style:{color:'#718b81',weight:.8,fillOpacity:.25}});
      // Dedicated pane keeps the study boundary above both the raster and grid.
      map.createPane('study-boundary');
      map.getPane('study-boundary').style.zIndex=450;
      map.getPane('study-boundary').style.pointerEvents='none';
      const boundaryStyle={pane:'study-boundary',interactive:false,fill:false,dashArray:'8 6',lineCap:'round',lineJoin:'round'};
      L.geoJSON(boundary,{style:{...boundaryStyle,color:'#ffffff',weight:4.5,opacity:.85},interactive:false,pane:'study-boundary'}).addTo(map);
      L.geoJSON(boundary,{style:{...boundaryStyle,color:'#285447',weight:2,opacity:1},interactive:false,pane:'study-boundary'}).addTo(map);
      map.fitBounds(gridLayer.getBounds(), {padding: [22, 22]});
      const queryDate = new URLSearchParams(location.search).get("date");
      $("display-mode").value = new URLSearchParams(location.search).get("view") === "source" ? "source" : "idw";
      selectSource(new URLSearchParams(location.search).get('source')==='cams'?'cams':'maiac',queryDate);
      $('data-source').addEventListener('change',()=>selectSource($('data-source').value,dateInput.value));
      dateInput.addEventListener("change", () => {
        const index = dataset.days.findIndex(day => day.date === dateInput.value);
        if (index >= 0) selectIndex(index);
      });
      slider.addEventListener("input", () => selectIndex(slider.value));
      $("display-mode").addEventListener("change", render);
      $("prev-day").addEventListener("click", () => selectIndex(selectedIndex - 1));
      $("next-day").addEventListener("click", () => selectIndex(selectedIndex + 1));
      $("latest-with-data").addEventListener("click", () => selectIndex(history.days.findLastIndex(day=>day.status==='Available')));
    } catch (error) {
      $("map-title").textContent = "แผนที่ยังไม่พร้อม";
      status.lastElementChild.textContent = error.message;
      const message = $("map-message");
      message.hidden = false;
      message.textContent = "ไม่สามารถโหลดข้อมูลแผนที่ได้ กรุณาลองใหม่";
    }
  }

  init();
  document.querySelectorAll('a[href="#method"]').forEach(link => link.addEventListener("click", () => { $("method").open = true; }));
})();
