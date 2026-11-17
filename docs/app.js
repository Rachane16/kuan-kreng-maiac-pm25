/* Static dashboard: credentials and model stay in the scheduled data pipeline. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),D=KKData;
  const dateInput=$('date-input'),slider=$('date-range'),status=$('selection-status');
  let datasets,forecast={hours:[]},dates=[],selectedIndex=0,sourcePreference='auto',selectedSource='maiac';
  let pollutant='pm25',camsMode='hourly',selectedHour=null,savedMaiacMode='idw',followNow=true;
  let map,gridLayer,camsLayer,gridData,targets=[],utmProject,activeBasemap,basemaps;
  const layerById=new Map(),idwCache=new Map(),surfaceCache=new Map();
  let surfaceLayer,surfaceJob=0,currentSampler=null;
  const thaiDate=iso=>new Date(`${iso}T00:00:00Z`).toLocaleDateString('th-TH',{timeZone:'UTC',day:'numeric',month:'short',year:'numeric'});
  const thaiTime=iso=>iso?new Date(iso).toLocaleString('th-TH',{timeZone:'Asia/Bangkok',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):'—';
  const escapeHtml=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const blank=date=>({date,status:'NotPublished',available_cells:0,mean_pm25:null,cells:[]});
  const dayFor=(source,date)=>datasets[source].byDate.get(date)||blank(date);
  const valueText=value=>value===null||!Number.isFinite(value)?'—':value.toFixed(2);
  const pmValue=pm25=>D.concentration(pm25,pollutant);
  const color=pm25=>D.color(pmValue(pm25),pollutant)||'#bfcbca';
  const popupValue=pm25=>`<div class="popup-value">${valueText(pmValue(pm25))} <small>µg/m³ · ${D.labels[pollutant]}</small></div>`;

  function idw(day){
    if(!idwCache.has(day.date)){
      const samples=new Map(day.cells.map(c=>[c[0],c]));
      const points=targets.filter(t=>samples.has(t.id)).map(t=>({...t,value:Number(samples.get(t.id)[2])}));
      const sampler=KKIDW.createSampler(points);
      const values=sampler?targets.map(t=>({...t,...sampler(t.x,t.y)})):[];
      idwCache.set(day.date,{points,sampler,values,cells:values.map(v=>[v.id,null,v.value])});
    }
    return idwCache.get(day.date);
  }
  function clearSurface(){surfaceJob++;currentSampler=null;if(surfaceLayer){map.removeLayer(surfaceLayer);surfaceLayer=null;}}
  async function showSurface(day,result){
    const job=++surfaceJob,key=`${day.date}:${pollutant}`,chosen=pollutant;
    currentSampler=result.sampler;
    try{
      let surface=surfaceCache.get(key);
      if(!surface){
        surface=await KKSurface.render(gridData,gridLayer.getBounds(),currentSampler,utmProject,()=>job!==surfaceJob,pm25=>{
          const hex=D.color(D.concentration(pm25,chosen),chosen);
          return hex?[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)):null;
        });
        if(!surface||job!==surfaceJob)return;
        surfaceCache.set(key,surface);if(surfaceCache.size>3)surfaceCache.delete(surfaceCache.keys().next().value);
      }
      if(job!==surfaceJob)return;
      surfaceLayer=L.imageOverlay(surface.url,gridLayer.getBounds(),{opacity:.64,interactive:false,className:'idw-surface'}).addTo(map);
    }catch(error){if(job===surfaceJob)$('view-note').textContent='สร้างผืนสี IDW ไม่สำเร็จ กรุณาเลือกวันที่อีกครั้ง';}
  }
  function updateLegend(){
    const label=D.labels[pollutant],limits=D.breaks[pollutant],health=['ดีมาก','ดี','ปานกลาง','เริ่มมีผลต่อสุขภาพ','มีผลต่อสุขภาพ'];
    $('legend-title').textContent=`ความเข้มข้น ${label} (µg/m³${pollutant==='pm25'?' · สีอ้างอิงกรมควบคุมมลพิษ':' · รหัสสีเบื้องต้น'})`;
    $('legend-levels').innerHTML=D.palette.map((hex,i)=>{
      const range=i===0?`0–${limits[0]}`:i===4?`>${limits[3]}`:`>${limits[i-1]}–${limits[i]}`;
      return `<span><i style="background:${hex}"></i>${pollutant==='pm25'?`<b>${health[i]}</b> `:''}${range}</span>`;
    }).join('');
    $('legend-note').textContent=pollutant==='pm25'?'ใช้สีเพื่อเทียบช่วงค่าประเมิน ไม่ใช่การรายงาน AQI จากสถานี':
      'รหัสสีของ PM₁ และ PM₀.₁ เป็นรหัสสีเบื้องต้น ยังไม่สามารถใช้ในการเชื่อมโยงกับผลกระทบต่อสุขภาพได้ในขณะนี้ ขอบเขตของรหัสสีคำนวณจากสัดส่วนของ PM₁ (80%) และ PM₀.₁ (15%) ของ PM₂.₅ ที่ได้จากค่าเฉลี่ยจากการวิจัยระยะยาวในหลายภูมิภาคและหลายประเทศในเอเชียตะวันออกเฉียงใต้ ส่วนการกำหนดสีของ PM₁ และ PM₀.₁ กับผลกระทบต่อสุขภาพอยู่ระหว่างการวิจัย';
  }
  function chartRecord(date){
    const maiac=dayFor('maiac',date),cams=dayFor('cams',date);
    if(sourcePreference!=='cams'&&maiac.available_cells){
      const result=idw(maiac);
      if(result.sampler)return {value:D.areaMean(result.cells,datasets.maiac.weights,pollutant),source:'MAIAC · IDW ทั้งพื้นที่'};
      if(sourcePreference==='maiac')return {value:null,source:'MAIAC มีจุดไม่พอสำหรับค่าเฉลี่ย IDW ทั้งพื้นที่'};
    }
    if(sourcePreference!=='maiac'&&cams.available_cells===datasets.cams.grid_count)
      return {value:D.areaMean(cams.cells,datasets.cams.weights,pollutant),source:'CAMS · AOD เฉลี่ยครบ 24 ชม.'};
    return {value:null,source:'ไม่มีค่าเฉลี่ยทั้งพื้นที่'};
  }
  function buildChart(){
    const chart=$('history-chart');chart.replaceChildren();
    const days=datasets.maiac.days,records=days.map(d=>chartRecord(d.date));
    const max=Math.max(1,...records.map(r=>r.value??0));
    records.forEach((r,i)=>{
      const bar=document.createElement('button');bar.type='button';bar.dataset.date=days[i].date;
      bar.className=`history-bar${r.value===null?' nodata':''}`;
      bar.style.setProperty('--bar-height',`${r.value===null?4:Math.max(5,80*r.value/max)}px`);
      bar.title=`${thaiDate(days[i].date)} · ${D.labels[pollutant]} ${valueText(r.value)} µg/m³ · ${r.source}`;
      bar.setAttribute('aria-label',bar.title);bar.addEventListener('click',()=>chooseDate(days[i].date,'daily'));chart.appendChild(bar);
    });
    $('history-count').textContent=`${records.filter(r=>r.value!==null).length} / ${days.length} วันมีค่าเฉลี่ย`;
    $('chart-start').textContent=thaiDate(days[0].date);$('chart-end').textContent=thaiDate(days.at(-1).date);
    $('chart-description').textContent=`ความสูงของแท่งแสดงค่าเฉลี่ย ${D.labels[pollutant]} ทั้งพื้นที่ (µg/m³) ถ่วงตามพื้นที่ · ${sourcePreference==='auto'?'ใช้ MAIAC ที่ทำ IDW ได้ก่อน แล้วใช้ CAMS รายวันทดแทน':sourcePreference==='maiac'?'MAIAC ที่มีจุดเพียงพอสำหรับ IDW':'CAMS จาก AOD เฉลี่ยครบ 24 ชั่วโมง'} · ชี้หรือเลือกแท่งเพื่อดูค่าและวันที่`;
  }
  function configureSource(){
    const isCams=selectedSource==='cams',label=D.labels[pollutant];
    $('data-source').value=selectedSource;$('cams-controls').hidden=!isCams;$('cams-time-mode').value=camsMode;
    $('forecast-time-label').hidden=camsMode!=='hourly';$('nearest-now').disabled=!forecast.hours.some(h=>h.status==='Available');
    const display=$('display-mode');
    display.innerHTML=isCams?`<option value="cams">การประมาณค่าฝุ่น ${label}</option>`:`<option value="idw">การประมาณค่าฝุ่น ${label}</option><option value="source">${label} ณ ตำแหน่งที่มีข้อมูล</option>`;
    display.disabled=isCams;if(!isCams)display.value=savedMaiacMode;
    if(isCams){if(map.hasLayer(gridLayer))map.removeLayer(gridLayer);camsLayer.addTo(map);}else{if(map.hasLayer(camsLayer))map.removeLayer(camsLayer);gridLayer.addTo(map);}
    document.title=`พรุควนเคร็ง | ${selectedSource.toUpperCase()} ${label}`;
    $('hero-eyebrow').innerHTML=`<span class="eyebrow-line"></span> ${isCams?'CAMS FORECAST ESTIMATION':'SATELLITE BASED ESTIMATION'}`;
    $('page-title').innerHTML=`การประมาณค่าฝุ่น ${label} ${isCams?'จาก CAMS':'จากดาวเทียม'}<br><em>ในพื้นที่ป่าพรุควนเคร็ง</em>`;
    $('hero-description').textContent=(isCams?'AOD 550 nm จาก Copernicus CAMS · กริดต้นทาง 0.4°':'AOD 470 nm จาก NASA MAIAC · กริดรายงาน 1 × 1 กม.')+(pollutant==='pm25'?'':` · ${label} คำนวณด้วย Empirical Model (CALLAB)`);
    $('source-description').textContent=isCams?'Copernicus CAMS · AOD 550 nm':'NASA MCD19A2 / MCD19A2N · AOD 470 nm';
    $('resolution-description').textContent=isCams?'0.4° × 0.4° (ประมาณ 44 กม.)':'MAIAC ประมาณ 1 กม.';
    $('map-resolution').textContent=isCams?'กริดต้นทาง 0.4° · ตัดตามขอบเขต':'EPSG:4326 · กริดรายงาน 1 × 1 กม.';
    $('date-timezone-label').textContent=isCams?'วันและเวลาของ CAMS อ้างอิงเวลาไทย (UTC+7)':'วันที่ของผลิตภัณฑ์ NASA อ้างอิง UTC';
    dateInput.setAttribute('aria-label',isCams?'เลือกวันที่ของข้อมูล CAMS':'เลือกวันที่ของข้อมูล MAIAC');
    $('coverage-heading').textContent=isCams?'ช่องกริด CAMS ที่ใช้ประเมินได้':'พื้นที่กริดที่มี AOD ใช้ได้';
    $('mean-unit').textContent=`µg/m³ · ${label} ประเมิน`;
    $('provider-link').href=isCams?'https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=overview':'https://lpdaac.usgs.gov/products/mcd19a2v061/';
    $('provider-link').textContent=isCams?'Copernicus CAMS · CC-BY ↗':'NASA MAIAC ↗';
    $('provider-documentation').href=isCams?'https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=documentation':'https://lpdaac.usgs.gov/documents/1500/MCD19_User_Guide_V61.pdf';
    $('provider-documentation').textContent=isCams?'คู่มือ CAMS ↗':'คู่มือ QA ↗';updateLegend();
  }
  function render(){
    const date=dates[selectedIndex],maiac=dayFor('maiac',date);
    selectedSource=D.sourceForDay(sourcePreference,maiac);
    const isCams=selectedSource==='cams',hourly=isCams&&camsMode==='hourly';
    let day=dayFor(selectedSource,date);
    const hours=forecast.hours.filter(h=>D.thaiDay(h.valid_time)===date);
    if(hourly){const wanted=hours.find(h=>h.valid_time===selectedHour)||D.nearest(hours);selectedHour=wanted?.valid_time||null;day=wanted?{...wanted,date}:blank(date);}
    configureSource();
    const timeSelect=$('forecast-time');timeSelect.replaceChildren();
    hours.forEach(h=>{const option=document.createElement('option');option.value=h.valid_time;option.textContent=thaiTime(h.valid_time);timeSelect.appendChild(option);});
    if(!hours.length){const option=document.createElement('option');option.textContent='ไม่มีพยากรณ์ในวันที่เลือก';timeSelect.appendChild(option);}
    timeSelect.disabled=!hours.length;if(selectedHour)timeSelect.value=selectedHour;
    const samples=new Map(day.cells.map(c=>[c[0],c])),result=!isCams&&day.available_cells?idw(day):null;
    const sparseFallback=sourcePreference==='auto'&&savedMaiacMode==='idw'&&day.available_cells>0&&!result?.sampler;
    const idwMode=!isCams&&savedMaiacMode==='idw'&&!sparseFallback,idwAvailable=idwMode&&!!result?.sampler;
    const estimates=new Map(result?.values.map(v=>[v.id,v])||[]);
    map.closePopup();clearSurface();
    let message=isCams?(hourly?'ยังไม่มีพยากรณ์รายชั่วโมงที่ใช้ได้สำหรับวันที่เลือก':'ยังไม่มีข้อมูล CAMS รายวันที่ครบ 24 ชั่วโมง'):day.status==='NoData'?'NASA มีไฟล์ แต่ไม่มี AOD ในพื้นที่ที่ผ่าน QA':'NASA ยังไม่มีข้อมูลที่ใช้ได้สำหรับวันที่เลือก';
    if(!isCams&&day.available_cells>0)message=`พบ MAIAC AOD ผ่าน QA ${day.available_cells.toLocaleString('th-TH')} ช่อง`;
    if(idwMode&&!idwAvailable&&day.available_cells>0)message='IDW ต้องมีอย่างน้อย 3 จุดที่ไม่เรียงเป็นเส้นเดียวกัน';
    const hasMapData=idwMode?idwAvailable:day.available_cells>0;
    if(isCams&&hasMapData)message=hourly?`CAMS พยากรณ์สำหรับ ${thaiTime(day.valid_time)} น.`:`CAMS ข้อมูลครบ 24 ชั่วโมง · ${thaiDate(date)}`;
    const autoNote=sourcePreference==='auto'?`อัตโนมัติเลือก ${isCams?'CAMS เพราะไม่มี MAIAC ของวันที่เลือก':'MAIAC'} · `:'';
    let note=idwMode?(idwAvailable?`ผืนสีต่อเนื่อง IDW · ${result.points.length} จุดตั้งต้นของวันเดียวกัน`:'ยังสร้าง IDW ทั้งพื้นที่ไม่ได้'):isCams?(hourly?`ค่าประมาณจาก AOD พยากรณ์ · รอบ ${thaiTime(day.forecast_base_time)} น.`:'ค่าเฉลี่ย AOD ครบ 24 ชั่วโมงตามเวลาไทย แล้วประเมิน PM₂.₅'):`ค่าประเมิน ณ ช่องที่มี AOD ผ่าน QA${sparseFallback?' · จุดไม่พอสำหรับ IDW จึงแสดงข้อมูลตั้งต้น':''}`;
    if(hourly&&selectedHour){const delta=(Date.now()-Date.parse(selectedHour))/3600000;if(delta>2)note+=` · ข้อมูลใกล้ที่สุดเก่ากว่าปัจจุบัน ${Math.floor(delta)} ชม. โปรดตรวจเวลา`;}
    $('view-note').textContent=autoNote+note+(pollutant!=='pm25'?` · ${D.labels[pollutant]} จากสมการ CALLAB`:'');
    $('mean-label').textContent=isCams?'ค่าเฉลี่ยพื้นที่จาก CAMS':idwMode?'ค่าเฉลี่ยทั้งพื้นที่ (IDW)':'ค่าเฉลี่ยเฉพาะช่องที่มีข้อมูล';
    $('nodata-label').textContent=isCams?'ไม่มีค่า CAMS ที่ใช้ได้':idwMode?'ไม่มีค่าประมาณ IDW':'ไม่มี AOD ผ่าน QA';
    const weights=datasets[selectedSource].weights;
    const mean=idwMode?(idwAvailable?D.areaMean(result.cells,weights,pollutant):null):D.areaMean(day.cells,weights,pollutant);
    $('mean-pm25').textContent=valueText(mean);$('cams-time-row').hidden=!isCams;
    $('cams-period').textContent=hourly?(day.valid_time?`${thaiTime(day.valid_time)} น. · รอบ ${thaiTime(day.forecast_base_time)} น.`:'—'):day.period_start_utc?`${thaiTime(day.period_start_utc)} ถึง ${thaiTime(day.period_end_utc)} (ไม่รวมเวลาสิ้นสุด)`:'—';
    $('generated-time').textContent=thaiTime(hourly?forecast.generated_at_utc:datasets[selectedSource].generated_at_utc);
    dateInput.value=date;slider.value=selectedIndex;$('map-title').textContent=hourly&&day.valid_time?`${thaiTime(day.valid_time)} น.`:thaiDate(date);
    $('coverage-value').textContent=day.available_cells.toLocaleString('th-TH');const total=datasets[selectedSource].grid_count;
    $('coverage-percent').textContent=`${(100*day.available_cells/total).toFixed(0)}%`;$('coverage-detail').textContent=`จากทั้งหมด ${total.toLocaleString('th-TH')} ช่อง`;$('coverage-progress').style.width=`${100*day.available_cells/total}%`;
    status.className=`selection-status ${hasMapData?'available':'nodata'}`;status.lastElementChild.textContent=message;
    $('map-message').hidden=hasMapData;$('map-message').textContent=message;
    $('prev-day').disabled=selectedIndex===0;$('next-day').disabled=selectedIndex===dates.length-1;
    document.querySelectorAll('.history-bar').forEach(bar=>{const active=bar.dataset.date===date;bar.classList.toggle('selected',active);bar.setAttribute('aria-pressed',String(active));});
    const dailySummary=chartRecord(date);
    $('chart-readout').textContent=`${thaiDate(date)} · ${D.labels[pollutant]} ${valueText(dailySummary.value)} µg/m³ · ${dailySummary.source}`;
    if(!isCams)layerById.forEach((layer,id)=>{
      const sample=samples.get(id),estimate=estimates.get(id),pm25=idwMode?estimate?.value:sample?.[2],valid=pmValue(pm25)!==null;
      layer.setStyle({stroke:!idwMode,color:valid?'#536a68':'#a2b3b0',weight:valid?.55:.38,opacity:.7,fillColor:color(pm25),fillOpacity:idwMode?0:valid?.76:.34});layer.unbindPopup();
      if(!idwMode)layer.bindPopup(`<div class="popup-label">กริด 1 × 1 กม. · ${escapeHtml(id)}</div>`+(sample?popupValue(Number(sample[2]))+`<div class="popup-meta">AOD 470 nm: ${Number(sample[1]).toFixed(3)}<br>เวลาผ่านพื้นที่: ${escapeHtml(thaiTime(sample[3]))}</div>`:'<div class="popup-nodata">ไม่มี AOD ผ่าน QA ในวันนี้</div>'));
      else if(!idwAvailable)layer.bindPopup(`<div class="popup-nodata">${escapeHtml(message)}</div>`);
    });
    if(isCams)camsLayer.eachLayer(layer=>{
      const sample=samples.get(layer.feature.properties.grid_id),valid=sample&&pmValue(Number(sample[2]))!==null;
      layer.setStyle({color:'#718b81',weight:.8,fillColor:sample?color(Number(sample[2])):'#bfcbca',fillOpacity:valid?.72:.25});layer.unbindPopup();
      layer.bindPopup(`<div class="popup-label">CAMS · ${D.labels[pollutant]} · กริดต้นทาง 0.4°</div>`+(sample?popupValue(Number(sample[2]))+`<div class="popup-meta">${hourly?'พยากรณ์ ณ':'เฉลี่ยรายวัน'} ${escapeHtml(hourly?thaiTime(day.valid_time):thaiDate(date))}<br>AOD 550 nm: ${Number(sample[1]).toFixed(4)}<br>รอบพยากรณ์: ${escapeHtml(thaiTime(day.forecast_base_time))}<br>Lead time: ${day.lead_time_hours?.join('–')} ชม.</div>`:'<div class="popup-nodata">ไม่มีค่า CAMS ที่ใช้ได้</div>'));
    });
    const url=new URL(location.href);url.searchParams.set('date',date);url.searchParams.set('source',sourcePreference);url.searchParams.set('pollutant',pollutant);url.searchParams.set('view',savedMaiacMode);url.searchParams.set('period',camsMode);
    if(hourly&&selectedHour)url.searchParams.set('at',selectedHour);else url.searchParams.delete('at');window.history.replaceState(null,'',url);
    if(idwAvailable)showSurface(day,result);
  }
  function chooseDate(date,mode){
    const index=dates.indexOf(date);if(index<0)return;
    selectedIndex=index;selectedHour=null;
    // Every newly selected day starts with MAIAC when available, otherwise CAMS.
    // A manual source switch applies to this day and never changes its date.
    const wasManual=sourcePreference!=='auto';sourcePreference='auto';
    camsMode=mode||(date>=D.thaiDay()?'hourly':'daily');
    followNow=date===D.thaiDay()&&camsMode==='hourly';
    if(wasManual)buildChart();
    render();
  }
  function nearestNow(){const hour=D.nearest(forecast.hours);if(!hour)return;sourcePreference='cams';camsMode='hourly';selectedHour=hour.valid_time;selectedIndex=dates.indexOf(D.thaiDay(hour.valid_time));followNow=true;buildChart();render();}
  async function init(){
    try{
      const paths=['grid.geojson','history.json','boundary.geojson','cams_grid.geojson','cams_history.json','cams_forecast.json'];
      const responses=await Promise.all(paths.map(p=>fetch(`./data/${p}`,{cache:p.endsWith('.json')?'no-store':'default'})));
      if(responses.slice(0,5).some(r=>!r.ok))throw Error('โหลดข้อมูลแผนที่ไม่สำเร็จ');
      const [grid,maiac,boundary,camsGrid,cams]=await Promise.all(responses.slice(0,5).map(r=>r.json()));if(responses[5].ok)forecast=await responses[5].json();
      datasets={maiac,cams};for(const source of ['maiac','cams'])datasets[source].byDate=new Map(datasets[source].days.map(d=>[d.date,d]));
      gridData=grid;targets=grid.features.map(f=>({id:f.properties.grid_id,x:f.properties.sample_x,y:f.properties.sample_y,weight:f.properties.coverage_fraction}));
      if(targets.some(t=>![t.x,t.y,t.weight].every(Number.isFinite)))throw Error('พิกัดกริด IDW ไม่สมบูรณ์');
      datasets.maiac.weights=new Map(targets.map(t=>[t.id,t.weight]));datasets.cams.weights=new Map(camsGrid.features.map(f=>[f.properties.grid_id,f.properties.overlap_m2]));
      const last=[maiac.end_date,cams.end_date,D.thaiDay(),...forecast.hours.map(h=>D.thaiDay(h.valid_time))].sort().at(-1);
      for(let date=maiac.start_date;date<=last;date=new Date(Date.parse(date+'T00:00:00Z')+86400000).toISOString().slice(0,10))dates.push(date);
      dateInput.min=dates[0];dateInput.max=dates.at(-1);slider.max=dates.length-1;$('range-label').textContent=`${maiac.days.length} วันย้อนหลัง + พยากรณ์`;
      $('range-start').textContent=thaiDate(dates[0]);$('range-end').textContent=thaiDate(dates.at(-1));
      utmProject=proj4('EPSG:4326','+proj=utm +zone=47 +datum=WGS84 +units=m +no_defs');
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
            L.popup().setLatLng(event.latlng).setContent(`<div class="popup-label">${D.labels[pollutant]} · IDW ณ ตำแหน่งที่เลือก</div><div class="popup-value">${valueText(pmValue(estimate.value))} <small>µg/m³</small></div>`).openOn(map);
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

      const query=new URLSearchParams(location.search);sourcePreference=['maiac','cams'].includes(query.get('source'))?query.get('source'):'auto';
      pollutant=['pm1','pm01'].includes(query.get('pollutant'))?query.get('pollutant'):'pm25';document.querySelector(`input[name="pollutant"][value="${pollutant}"]`).checked=true;
      savedMaiacMode=query.get('view')==='source'?'source':'idw';const date=dates.includes(query.get('date'))?query.get('date'):D.thaiDay();selectedIndex=dates.indexOf(date);
      camsMode=['daily','hourly'].includes(query.get('period'))?query.get('period'):(date>=D.thaiDay()?'hourly':'daily');selectedHour=query.get('at');followNow=!query.has('at');
      if(sourcePreference==='cams'&&!query.has('date')){const hour=D.nearest(forecast.hours);if(hour){selectedHour=hour.valid_time;selectedIndex=dates.indexOf(D.thaiDay(hour.valid_time));camsMode='hourly';}}
      buildChart();render();
      $('data-source').addEventListener('change',()=>{sourcePreference=$('data-source').value;buildChart();render();});
      dateInput.addEventListener('change',()=>chooseDate(dateInput.value));slider.addEventListener('input',()=>chooseDate(dates[Number(slider.value)]));
      $('prev-day').addEventListener('click',()=>chooseDate(dates[selectedIndex-1]));$('next-day').addEventListener('click',()=>chooseDate(dates[selectedIndex+1]));
      $('display-mode').addEventListener('change',()=>{savedMaiacMode=$('display-mode').value;render();});$('cams-time-mode').addEventListener('change',()=>{camsMode=$('cams-time-mode').value;selectedHour=null;followNow=false;render();});
      $('forecast-time').addEventListener('change',()=>{selectedHour=$('forecast-time').value;followNow=false;render();});$('nearest-now').addEventListener('click',nearestNow);
      document.querySelectorAll('input[name="pollutant"]').forEach(input=>input.addEventListener('change',()=>{pollutant=input.value;buildChart();render();}));
      $('latest-with-data').addEventListener('click',()=>{const latest=datasets.maiac.days.findLast(d=>sourcePreference==='maiac'?d.available_cells>0:sourcePreference==='cams'?dayFor('cams',d.date).available_cells>0:d.available_cells>0||dayFor('cams',d.date).available_cells>0);if(latest)chooseDate(latest.date,'daily');});
      setInterval(()=>{if(selectedSource==='cams'&&camsMode==='hourly'&&dates[selectedIndex]===D.thaiDay()&&followNow&&!document.hidden){const closest=D.nearest(forecast.hours);if(closest&&closest.valid_time!==selectedHour){selectedHour=closest.valid_time;render();}}},60000);
    }catch(error){$('map-title').textContent='แผนที่ยังไม่พร้อม';status.lastElementChild.textContent=error.message;$('map-message').hidden=false;$('map-message').textContent='ไม่สามารถโหลดข้อมูลแผนที่ได้ กรุณาลองใหม่';}
  }
  init();document.querySelectorAll('a[href="#method"]').forEach(link=>link.addEventListener('click',()=>{$('method').open=true;}));
})();
