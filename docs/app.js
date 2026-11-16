/* Static MAIAC viewer. No NASA credentials or model are used in the browser. */
(() => {
  const $ = (id) => document.getElementById(id);
  const dateInput = $("date-input");
  const slider = $("date-range");
  const status = $("selection-status");
  let history;
  let map;
  let gridLayer;
  let layerById = new Map();
  let selectedIndex = 0;
  let scaleMax = 50;

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
    const stops = [[50, 181, 169], [172, 216, 140], [244, 210, 107], [237, 147, 90], [207, 91, 100]];
    const scaled = Math.max(0, Math.min(3.999, value / scaleMax * 4));
    const i = Math.floor(scaled), t = scaled - i;
    return `rgb(${stops[i].map((n, k) => Math.round(n + (stops[i + 1][k] - n) * t)).join(",")})`;
  }

  function statusText(day) {
    if (day.status === "Available") return `พบ AOD ผ่าน QA ${day.available_cells.toLocaleString("th-TH")} ช่องในวันที่เลือก`;
    if (day.status === "NoData") return "NASA มีไฟล์ของวันนี้ แต่ไม่มี AOD ในพื้นที่ที่ผ่าน QA";
    if (day.status === "NotPublished") return "NASA ยังไม่มีไฟล์ของวันที่เลือกสำหรับพื้นที่นี้";
    return "ยังไม่ได้ตรวจข้อมูลของวันที่เลือก";
  }

  function popupContent(gridId, sample) {
    const heading = `<div class="popup-label">กริด 1 × 1 กม.</div><div class="popup-id">${escapeHtml(gridId)}</div>`;
    if (!sample) return heading + `<div class="popup-nodata">ไม่มี AOD ผ่าน QA ในวันนี้</div>`;
    return heading + `<div class="popup-value">${Number(sample[2]).toFixed(2)} <small>µg/m³</small></div>`
      + `<div class="popup-meta">PM₂.₅ ประเมินจากโมเดล<br>AOD 470 nm: ${Number(sample[1]).toFixed(3)}<br>เวลาผ่านพื้นที่: ${escapeHtml(thaiTime(sample[3]))}<br>รอบผ่านที่ใช้ได้: ${Number(sample[4])}</div>`;
  }

  function render() {
    const day = history.days[selectedIndex];
    const samples = new Map(day.cells.map(item => [item[0], item]));
    dateInput.value = day.date;
    slider.value = selectedIndex;
    $("map-title").textContent = thaiDate(day.date);
    $("coverage-value").textContent = day.available_cells.toLocaleString("th-TH");
    $("coverage-percent").textContent = percent(day.available_cells, history.grid_count);
    $("coverage-detail").textContent = `จากทั้งหมด ${history.grid_count.toLocaleString("th-TH")} ช่อง`;
    $("coverage-progress").style.width = `${100 * day.available_cells / history.grid_count}%`;
    $("mean-pm25").textContent = day.mean_pm25 === null ? "—" : Number(day.mean_pm25).toFixed(2);
    status.className = `selection-status ${day.status === "Available" ? "available" : "nodata"}`;
    status.lastElementChild.textContent = statusText(day);
    const message = $("map-message");
    message.hidden = day.status === "Available";
    message.textContent = statusText(day);
    $("prev-day").disabled = selectedIndex === 0;
    $("next-day").disabled = selectedIndex === history.days.length - 1;
    document.querySelectorAll(".history-bar").forEach((bar, i) => {
      bar.classList.toggle("selected", i === selectedIndex);
      bar.setAttribute("aria-pressed", i === selectedIndex ? "true" : "false");
    });
    layerById.forEach((layer, gridId) => {
      const sample = samples.get(gridId);
      layer.setStyle({
        color: sample ? "#5c7472" : "#a2b3b0", weight: sample ? .6 : .38,
        opacity: sample ? .75 : .6,
        fillColor: sample ? color(Number(sample[2])) : "#bfcbca",
        fillOpacity: sample ? .86 : .34
      });
      layer.unbindPopup();
      layer.bindPopup(popupContent(gridId, sample));
    });
    const url = new URL(location.href);
    url.searchParams.set("date", day.date);
    window.history.replaceState(null, "", url);
  }

  function selectIndex(index) {
    selectedIndex = Math.max(0, Math.min(history.days.length - 1, Number(index)));
    render();
  }

  function buildChart() {
    const chart = $("history-chart");
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

  async function init() {
    try {
      const [gridResponse, historyResponse] = await Promise.all([
        fetch("./data/grid.geojson"), fetch("./data/history.json", {cache: "no-store"})
      ]);
      if (!gridResponse.ok || !historyResponse.ok) throw new Error("โหลดไฟล์ข้อมูลไม่สำเร็จ");
      const [grid, dataset] = await Promise.all([gridResponse.json(), historyResponse.json()]);
      if (!window.L || !dataset.days?.length || !grid.features?.length) throw new Error("ข้อมูลแผนที่ไม่สมบูรณ์");
      history = dataset;
      const pmValues = dataset.days.flatMap(day => day.cells.map(cell => Number(cell[2]))).filter(Number.isFinite);
      scaleMax = Math.max(20, Math.ceil(pmValues.reduce((max, value) => Math.max(max, value), 0) / 10) * 10);
      $("legend-mid").textContent = Math.round(scaleMax / 2);
      $("legend-max").textContent = scaleMax;
      $("range-label").textContent = `${dataset.days.length} วัน`;
      $("range-start").textContent = thaiDate(dataset.start_date);
      $("range-end").textContent = thaiDate(dataset.end_date);
      $("generated-time").textContent = thaiTime(dataset.generated_at_utc);
      dateInput.min = dataset.start_date;
      dateInput.max = dataset.end_date;
      slider.max = dataset.days.length - 1;
      map = L.map("map", {zoomControl: false, preferCanvas: true, scrollWheelZoom: false});
      L.control.zoom({position: "bottomright"}).addTo(map);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18, opacity: .75
      }).addTo(map);
      gridLayer = L.geoJSON(grid, {
        style: {color: "#a2b3b0", weight: .38, fillColor: "#bfcbca", fillOpacity: .34},
        onEachFeature(feature, layer) { layerById.set(feature.properties.grid_id, layer); }
      }).addTo(map);
      map.fitBounds(gridLayer.getBounds(), {padding: [22, 22]});
      buildChart();
      const queryDate = new URLSearchParams(location.search).get("date");
      const queryIndex = dataset.days.findIndex(day => day.date === queryDate);
      selectIndex(queryIndex >= 0 ? queryIndex : dataset.days.length - 1);
      dateInput.addEventListener("change", () => {
        const index = dataset.days.findIndex(day => day.date === dateInput.value);
        if (index >= 0) selectIndex(index);
      });
      slider.addEventListener("input", () => selectIndex(slider.value));
      $("prev-day").addEventListener("click", () => selectIndex(selectedIndex - 1));
      $("next-day").addEventListener("click", () => selectIndex(selectedIndex + 1));
      const latestIndex = dataset.days.findLastIndex(day => day.status === "Available");
      $("latest-with-data").disabled = latestIndex < 0;
      $("latest-with-data").addEventListener("click", () => selectIndex(latestIndex));
    } catch (error) {
      $("map-title").textContent = "แผนที่ยังไม่พร้อม";
      status.lastElementChild.textContent = error.message;
      const message = $("map-message");
      message.hidden = false;
      message.textContent = "ไม่สามารถโหลดข้อมูลแผนที่ได้ กรุณาลองใหม่";
    }
  }

  init();
})();
