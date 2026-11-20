# KK-PSF: MAIAC / CAMS AOD → PM₂.₅

เว็บไซต์ใน `docs/` แสดงค่าประเมิน PM₂.₅ ย้อนหลัง 3 เดือนสำหรับพรุควนเคร็ง โดยใช้ NASA MAIAC มาตรฐาน (`MCD19A2`) สำหรับวันย้อนหลัง และ Near Real-Time (`MCD19A2N`) เมื่อข้อมูลมาตรฐานยังไม่เผยแพร่ ใช้ AOD 470 nm กับโมเดล Extra Trees เดิมของโครงการ ผลลัพธ์คือ **ค่าประเมิน PM₂.₅ จากโมเดล** ไม่ใช่ค่าตรวจวัดจากสถานี เพิ่ม CAMS AOD550 จาก ADS API แล้ว โดยเลือกแหล่งข้อมูลในเว็บไซต์แยกจาก MAIAC

## ข้อมูลที่มีแล้ว

- ขอบเขตที่ผู้ใช้ให้: `ขอบเขตพรุควนเคร็ง/ขอบเขตพรุควนเคร็ง.shp` (EPSG:32647); สำเนาที่มีเฉพาะเรขาคณิตสำหรับ repository คือ `data/boundaries/kkpsf_boundary.geojson`
- กริดที่สร้างจากขอบเขต: `data/boundaries/kkpsf_grid_1km.gpkg` (1,052 ช่องเต็มขนาด 1×1 กม. ที่มีพื้นที่ทับซ้อนขอบเขต; พื้นที่ทับซ้อนรวมประมาณ 931.05 ตร.กม.) จำนวนต่างจาก 928 ช่องใน brief เพราะกริดนี้รวมช่องริมขอบเขตทุกช่องที่มีพื้นที่ทับซ้อน และใช้การวางกริดบนพิกัด UTM ที่หารด้วย 1,000 ลงตัว
- MODIS tile สำหรับพื้นที่: `h27v08`
- โมเดลต้นฉบับที่ตรวจสอบแล้ว: `D:\LAB - PM2.5\FINAL ML-AOD\Final BestModel\Extra Trees Model\ET-2 Model\Extra_Trees_model.pkl`; ฟีเจอร์ที่โมเดลคาดหวังคือ `AOD 0.47` เพียงคอลัมน์เดียว ทดสอบโหลดและ `predict()` ด้วย Python 3.12.5 / scikit-learn 1.4.2 แล้ว

ไฟล์โมเดลแบบอ่านได้และโทเคนจะไม่ถูกคัดลอกเข้า repository นี้ งานอัปเดตอัตโนมัติใช้โมเดลที่เข้ารหัสและกุญแจถอดรหัสใน GitHub Actions Secret

## ติดตั้ง

ใช้ PowerShell จากโฟลเดอร์ `D:\LAB AODPM2.5`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

การอ่าน HDF4 ต้องมี `pyhdf` ตาม `requirements.txt` ถ้าติดตั้งไม่สำเร็จ ให้ตรวจสอบว่า Python และแพ็กเกจมี wheel ที่เข้ากันได้กับ Windows รุ่นที่ใช้ ในโฟลเดอร์ `.venv` นี้ติดตั้ง `pyhdf` แล้ว และทดสอบการอ่านไฟล์ HDF4 จำลองผ่านชุดทดสอบแล้ว

## โทเคน Earthdata และการรัน

ใช้ [Earthdata bearer token](https://ladsweb.modaps.eosdis.nasa.gov/learn/download-files-using-edl-tokens/) จากหน้า **Generate Token** ที่เปิดอยู่ โทเคนเป็นความลับ ไม่ต้องส่งมาในแชตหรือบันทึกลงไฟล์ในโครงการ ตั้งค่าเฉพาะ PowerShell session ก่อนรัน:

```powershell
$secureToken = Read-Host "NASA Earthdata token" -AsSecureString
$env:NASA_EARTHDATA_TOKEN = [System.Net.NetworkCredential]::new("", $secureToken).Password
```

ตรวจสอบว่า NASA เผยแพร่ไฟล์ของวันที่ต้องการแล้ว (วันที่เป็น UTC):

```powershell
python -m maiac.fetch --date 2026-11-15 --boundary '.\data\boundaries\kkpsf_boundary.geojson' --list-only
```

ตัวอย่างไฟล์ที่พบในคลัง ณ 16 พ.ย. 2026 คือ `MCD19A2N.A2026319.h27v08.061.hdf` สำหรับ **15 พ.ย. 2026** (UTC) การมีไฟล์ไม่ได้ยืนยันว่าทุกช่องมี AOD ใช้ได้ รันดาวน์โหลดและประมวลผลวันที่นั้น:

```powershell
python -m maiac.run --date 2026-11-15 --boundary '.\data\boundaries\kkpsf_boundary.geojson' --grid '.\data\boundaries\kkpsf_grid_1km.gpkg' --model 'D:\LAB - PM2.5\FINAL ML-AOD\Final BestModel\Extra Trees Model\ET-2 Model\Extra_Trees_model.pkl'
```

ถ้าดาวน์โหลด HDF ด้วย browser ไว้แล้ว สามารถข้ามขั้นโทเคนและใช้ไฟล์นั้นได้:

```powershell
python -m maiac.process --hdf 'C:\path\to\MCD19A2N.A2026319.h27v08.061.hdf' --boundary '.\data\boundaries\kkpsf_boundary.geojson' --grid '.\data\boundaries\kkpsf_grid_1km.gpkg' --model 'D:\LAB - PM2.5\FINAL ML-AOD\Final BestModel\Extra Trees Model\ET-2 Model\Extra_Trees_model.pkl'
```

ผลลัพธ์ใน `data/outputs/`: CSV, GeoJSON (EPSG:4326) และ JSON metadata ตามวันที่ UTC ของผลิตภัณฑ์ GeoJSON ตัดรูปทรงกริดให้เหลือเฉพาะส่วนภายในขอบเขตพรุควนเคร็ง ข้อมูลแต่ละกริดระบุแหล่งข้อมูล ความยาวคลื่น เวลา UTC และเวลาไทย สถานะ `NoData` จะคงไว้เมื่อไม่มี AOD ที่ผ่าน QA ไม่มีการเติมค่าเอง

## เว็บไซต์ย้อนหลัง 3 เดือน

แผนที่เปิดด้วยมุมมอง **การประมาณค่าฝุ่น PM₂.₅** (IDW แบบผืนสีต่อเนื่อง) เป็นค่าเริ่มต้น และเลือก **PM₂.₅ ณ ตำแหน่งที่มีข้อมูล** เพื่อดูกริดข้อมูลตั้งต้นได้ ใช้จุดตัวแทนของกริดเดียวกับการสุ่ม MAIAC ใน EPSG:32647 (ระยะหน่วยเมตร) กำลัง 2 และเพื่อนบ้านใกล้ที่สุดไม่เกิน 12 จุด ต้องมีอย่างน้อย 3 พิกัดที่ไม่เรียงบนเส้นเดียวกัน ผืนสีใช้ตาข่ายแสดงผลประมาณ 100 เมตรบน Web Mercator แล้วแปลงพิกัดกลับเป็น UTM เพื่อคำนวณ IDW ด้วย Proj4js ผืนสีตัดตามรูปทรงกริดที่ clip กับขอบเขตแล้วและไม่มีเส้นกริด คลิกตำแหน่งใดภายในพื้นที่เพื่อคำนวณ IDW ณ ตำแหน่งนั้น ความละเอียดข้อมูลต้นทางยังประมาณ 1 กม. ค่าเฉลี่ยที่แสดงยังคำนวณบนกริดรายงาน 1 กม. และถ่วงน้ำหนักด้วยสัดส่วนพื้นที่กริดภายในขอบเขต ขณะที่มุมมองข้อมูลตั้งต้นใช้ค่าเฉลี่ยช่องที่มีข้อมูล

IDW คำนวณในเบราว์เซอร์จากข้อมูลของวันที่เลือก จึงรองรับวันที่เพิ่มจาก Workflow รายวันโดยไม่ต้องฝึกโมเดลเพิ่ม การมีครบทุกช่องไม่ได้ยืนยันความแม่นยำในบริเวณไกลหรือนอกกลุ่มจุดตั้งต้น วันที่มีจุดไม่พอหรือไม่มีข้อมูลจะไม่สร้างค่า IDW สีของทั้งสองมุมมองแบ่งที่ 15, 25, 37.5 และ 75 µg/m³ เพื่ออ้างอิงช่วงความเข้มข้น ไม่ใช่การรายงาน AQI จากสถานี

ตรวจสอบ IDW ด้วย `node --test tests/test_idw.cjs` ซึ่งครอบคลุมค่าที่ทราบคำตอบ จุดซ้ำ/จุดเรียงเป็นเส้นเดียว และการคงค่าตั้งต้นพร้อมขอบเขตค่าจากข้อมูลจริงย้อนหลัง

เว็บไซต์ GitHub Pages เผยแพร่ไฟล์ใน `docs/` และแสดงเฉพาะ GeoJSON ที่ตัดตามขอบเขตพรุควนเคร็ง ไฟล์ HDF ต้นฉบับไม่เผยแพร่ ช่วงแรกคือ 16 ส.ค.–15 พ.ย. 2026 (92 วัน) วันที่ไม่มี AOD ผ่าน QA แสดง `NoData` และไม่มีตัวเลข PM₂.₅ เมื่อข้อมูล NASA ของวันยังไม่มี แสดง `NotPublished`

```powershell
python -m maiac.backfill --start 2026-08-16 --end 2026-11-15 --boundary '.\data\boundaries\kkpsf_boundary.geojson' --grid '.\data\boundaries\kkpsf_grid_1km.gpkg' --model 'D:\LAB - PM2.5\FINAL ML-AOD\Final BestModel\Extra Trees Model\ET-2 Model\Extra_Trees_model.pkl'
python -m maiac.export_site --start 2026-08-16 --end 2026-11-15 --boundary '.\data\boundaries\kkpsf_boundary.geojson' --grid '.\data\boundaries\kkpsf_grid_1km.gpkg' --site-data docs/data --require-complete
python -m http.server 8765 --directory docs
```

`backfill` ค้นหาผ่าน NASA CMR เฉพาะ tile `h27v08` และใช้ NRT เป็นแหล่งสำรองสำหรับวันล่าสุด เมื่อรันซ้ำจะข้ามวันที่ประมวลผลแล้ว เว็บไซต์เป็นไฟล์สถิติจึงแสดงข้อมูลตามเวลาที่ส่งออกครั้งล่าสุด

### อัปเดตรายวันผ่าน GitHub Actions

Workflow `.github/workflows/update_maiac.yml` ตรวจเวลา 20:23 น. ประเทศไทยทุกวัน และสั่งรันเองได้ด้วย `workflow_dispatch` โดยใช้ `maiac.refresh_site` คงช่วง 92 วันล่าสุด ตรวจเฉพาะวันที่เพิ่งเพิ่ม วันที่ NASA ยังไม่เผยแพร่ และ 3 วันล่าสุดเพื่อเปลี่ยนจาก NRT เป็นไฟล์มาตรฐานเมื่อมีไฟล์ใหม่ ระบบจะเก็บ `NoData` และ `NotPublished` ตามจริง ถ้าดาวน์โหลดหรือประมวลผลผิดพลาด Workflow จะหยุดก่อนเผยแพร่ ทำให้เว็บเดิมยังคงใช้ได้

Repository ใช้ secrets ใน GitHub: `NASA_EARTHDATA_TOKEN` สำหรับ NASA และ `MODEL_DECRYPT_KEY_B64` สำหรับถอดรหัสไฟล์ `models/Extra_Trees_model.pkl.aesgcm` ที่สร้างจากโมเดลต้นฉบับ และ `CAMS_ADS_TOKEN` สำหรับ ADS API ห้ามใส่ค่า secret ใน YAML, HTML, JavaScript, JSON หรือ Git commit Pages Source ตั้งเป็น **GitHub Actions** และ Workflow ผ่านการรันด้วยมือแล้ว หาก secret หายหรือหมดอายุ Workflow จะหยุดก่อนเผยแพร่ข้อมูลใหม่

## วิธีประมวลผล

1. เลือกเฉพาะไฟล์ `MCD19A2` หรือ `MCD19A2N` ของวันและ MODIS tile ที่ขอบเขตตัดผ่าน สำหรับขอบเขตนี้เลือกเพียงไฟล์ `h27v08` หนึ่งไฟล์ต่อวัน ไม่ดาวน์โหลดข้อมูลทั่วโลก NASA เผยแพร่ไฟล์ต้นทางเป็นระดับไทล์ จึงมีพื้นที่นอกขอบเขตอยู่ภายในไฟล์ต้นทาง แต่ไม่รวมในผลลัพธ์เชิงพื้นที่
2. อ่าน `Optical_Depth_047`, ชั้น QA (`AOD_QA` ในไฟล์ NRT ที่ตรวจพบ; รองรับ `AOT_QA` ด้วย) และ scale/offset/fill/range จาก HDF4
3. เก็บเฉพาะ land, clear, normal adjacency และ best AOD quality ตาม [MAIAC C6.1 User Guide](https://modis-land.gsfc.nasa.gov/pdf/MCD19_UserGuide_C61_V3.1.pdf)
4. หาค่า median ของ overpass ที่ใช้ได้ต่อ pixel ต่อวัน แล้วสุ่มค่าจาก pixel ที่ครอบคลุมจุดตัวแทนภายในแต่ละกริด UTM 1 กม. หากมีหลาย overpass เวลาในผลลัพธ์เป็นเวลาของ overpass ที่มีค่าใกล้ median ที่สุด
5. ส่ง AOD ที่ใช้ได้เข้าโมเดลเดิมด้วย DataFrame คอลัมน์ `AOD 0.47` โดยไม่ฝึกใหม่

วันที่ในชื่อไฟล์และคอลัมน์ `date` เป็นวันของผลิตภัณฑ์ใน UTC; เวลาไทยของ overpass อยู่ใน `data_time_thailand` แยกต่างหาก กริด 1 กม. เป็นกริดสำหรับรายงาน ไม่ได้ทำให้ความละเอียดของดาวเทียมสูงขึ้น

## สถานะข้อมูล

ข้อมูลในเว็บไซต์อยู่ใน `docs/data/history.json` โดยระบุวันเริ่มต้น วันสิ้นสุด สถานะ จำนวนกริดที่มี AOD ผ่าน QA และเวลาส่งออก วันที่ 15 พ.ย. 2026 มี AOD ที่ใช้ได้ **0/1,052 ช่อง** จึงเป็น `NoData` ทั้งหมด ไฟล์ HDF ต้นทาง ผลลัพธ์เต็ม และตัวแปรโทเคนไม่ถูกเพิ่มเข้า repository


## CAMS AOD550

ตัวเลือกแหล่งข้อมูล **MAIAC / CAMS** เปลี่ยนแผนที่ กราฟย้อนหลัง วันที่ และรายละเอียดพร้อมกัน CAMS ใช้ชุดข้อมูล `cams-global-atmospheric-composition-forecasts` ของ Copernicus/ECMWF (CC-BY) จาก ADS เฉพาะบริเวณ N/W/S/E `[8.4, 99.6, 7.6, 100.4]` ซึ่งเป็นกริดต้นทาง 3×3 จุดรอบขอบเขต ไม่ขอข้อมูลทั้งโลก เมื่อสร้างรูปทรงกริด 0.4° ตามพิกัดศูนย์กลางและตัดตามขอบเขตพรุควนเคร็ง จะเหลือ 5 ส่วนกริด คงความละเอียดต้นทางและไม่ใช้ IDW กับ CAMS

วัน CAMS อ้างอิง Asia/Bangkok ใช้รอบพยากรณ์ 12:00 UTC ของวันก่อนหน้าและ lead hours 5–28 เพื่อครอบคลุม 00:00–23:00 น. ของวันไทย เก็บ forecast reference time, valid time interval และ lead hours ไว้ในแต่ละวัน ค่าเฉลี่ย AOD550 ต้องมีครบ 24 ชั่วโมงและไม่ติดลบ จากนั้นจึงเรียกโมเดลเดิมด้วยฟีเจอร์ชื่อ `AOD 0.47` ตามข้อกำหนดโครงการ ไม่ฝึกโมเดลใหม่ ความแม่นยำเดิมของโมเดลยังไม่ได้รับการยืนยันสำหรับ CAMS AOD550

ข้อมูลเริ่มต้น CAMS มีครบ 92 วัน (17 ส.ค.–16 พ.ย. 2026) ใน `docs/data/cams_history.json` และรูปทรงกริดใน `docs/data/cams_grid.geojson` ค่าเฉลี่ยพื้นที่ถ่วงน้ำหนักด้วยพื้นที่ทับซ้อนขอบเขตของแต่ละกริด CAMS วันที่ข้อมูลขาดบางชั่วโมงเป็น `Incomplete` ไม่มีการทำนายรายวันจากชั่วโมงที่ไม่ครบ; วันที่ไม่มีชั่วโมงในผลคำขอเป็น `NotPublished`

การรันรายวันใช้ `python -m cams.refresh --boundary data/boundaries/kkpsf_boundary.geojson --model <trusted_model.pkl>` โดยอ่าน key จากตัวแปรสภาพแวดล้อม `CAMS_ADS_TOKEN` และคงข้อมูลย้อนหลัง 92 วัน ใช้ข้อมูลเดิมจากเว็บไซต์เพื่อไม่ต้องเรียกย้อนหลังใหม่ทั้งช่วงทุกวัน Workflow รายวันจะอัปเดต CAMS ก่อนเผยแพร่ และรักษาชุดข้อมูล CAMS เดิมหาก ADS ขัดข้อง เพื่อให้ MAIAC อัปเดตต่อได้ ควรดูวันที่ของชุดข้อมูลแต่ละแหล่งบนเว็บไซต์ การขอข้อมูลเกิน 30 วันย้อนหลังจาก ADS อาจเข้าคิวจากเทปช้ากว่าข้อมูลล่าสุด


## ค่าเริ่มต้น พยากรณ์รายชั่วโมง และขนาดฝุ่น

หน้าแรกใช้ CAMS เป็นพื้นฐาน ยกเว้นวันที่มี MAIAC ผ่าน QA อย่างน้อยหนึ่งช่องจะเลือก MAIAC ก่อน หากจุดไม่พอสำหรับ IDW จะแสดงกริดต้นทางพร้อมข้อความอธิบาย เมนูแหล่งข้อมูลมีเพียง **MAIAC / CAMS** โดยระบบเลือกให้ตามข้อมูลของวันนั้น ผู้ใช้สลับแหล่งข้อมูลเองได้โดยยังคงวันที่เดิม เมื่อเลือกวันใหม่ ระบบจะเลือก MAIAC ก่อนถ้ามีข้อมูล มิฉะนั้นเลือก CAMS อีกครั้ง

CAMS เปิดที่ชั่วโมงพยากรณ์ที่ใกล้เวลาปัจจุบันที่สุด ใช้ `docs/data/cams_forecast.json` ซึ่งบันทึก 121 valid times (lead 0–120 ชั่วโมง) จากรอบเดียวที่ ADS ระบุว่ามีครบแล้ว แยกเวลาที่พยากรณ์สำหรับ เวลารอบพยากรณ์ และเวลาอัปเดตอย่างชัดเจน โหมดรายชั่วโมงและค่าเฉลี่ยรายวันแยกกัน ไม่รวมพยากรณ์รายชั่วโมงเข้ากับสถิติย้อนหลังรายวัน 92 วัน ผู้ใช้เลือกวันและชั่วโมงในอนาคตได้เท่าที่ข้อมูลมีจริง ปุ่ม **ใกล้เวลาปัจจุบัน** จะกลับไปเลือกเวลาที่ใกล้ปัจจุบันที่สุด และหากปล่อยหน้านี้ไว้จะปรับชั่วโมงตามนาฬิกาทุกนาที (จากข้อมูลรอบที่โหลดแล้ว)

`cams.forecast.latest_cycle` รวมขั้นเวลาที่ ADS แยกไว้หลายแถวใน constraints ก่อนตรวจว่ามีครบ 0–120 ชั่วโมง ไม่เลือกเวลาในอนาคตและไม่ถอยกลับไปทับรอบใหม่ด้วยรอบเก่า คำขอยังใช้เฉพาะ `[8.4,99.6,7.6,100.4]` ข้อมูลที่ไม่ครบจะไม่ทับไฟล์พยากรณ์เดิม Workflow ดึง CAMS เวลาไทยประมาณ **05:30 และ 17:30** พร้อมลองอีกครั้ง **07:30 และ 19:30** ส่วนงานเต็ม MAIAC และ CAMS รายวันยังทำ **20:23** เวลาเริ่มจริงขึ้นกับคิว GitHub Actions และ ADS ใช้ `--forecast-only` เพื่ออัปเดตพยากรณ์อย่างเดียวโดยไม่ดาวน์โหลดย้อนหลัง

กราฟย้อนหลังเปลี่ยนเป็นค่าเฉลี่ยฝุ่นที่ถ่วงตามพื้นที่ในขอบเขต MAIAC ใช้ค่า IDW บนกริดรายงาน 1 กม. CAMS ใช้น้ำหนักพื้นที่ส่วนกริดต้นทางที่ตัดกับขอบเขต โหมดอัตโนมัติใช้ MAIAC เมื่อทำ IDW ได้ แล้วใช้ CAMS รายวันแทนหากไม่มีค่าเฉลี่ย MAIAC ทั้งพื้นที่ โหมด MAIAC จะแสดงช่องว่างในกราฟเมื่อจุดไม่พอสำหรับ IDW (แม้แผนที่ต้นทางมีบางช่อง) ข้อความประจำแท่งระบุวันที่ ค่าเฉลี่ย และแหล่งข้อมูล

ตัวเลือก PM₂.₅ / PM₁ / PM₀.₁ เปลี่ยนสีแผนที่ popup ค่าเฉลี่ย และกราฟพร้อมกัน โดยคงค่า PM₂.₅ ต้นทาง แล้วใช้สมการที่ผู้จัดทำให้มา (CALLAB):

- PM₁ = 0.80 × PM₂.₅ − 0.71
- PM₀.₁ = 0.14 × PM₂.₅ − 0.40

ผลสมการที่ติดลบเป็น NoData ไม่แทนด้วยศูนย์และไม่นับรวมค่าเฉลี่ย ใช้สี pastel เดิมทั้งสามขนาด ช่วงแบ่ง PM₁ คือ **12 / 20 / 30 / 60** และ PM₀.₁ คือ **2.25 / 3.75 / 5.63 / 11.25 µg/m³** ขอบเขตตัวเลขต่อเนื่อง (เช่น >12–20) จึงไม่มีช่องว่างระหว่างช่วง ตัวเลือก PM₁ / PM₀.₁ แสดงเฉพาะช่วงตัวเลข ไม่มีคำตัดสินผลต่อสุขภาพ และมีคำอธิบายรหัสสีเบื้องต้นตามข้อความของผู้จัดทำ สัดส่วน 80% / 15% ใช้กำหนดช่วงสีเท่านั้น ไม่เปลี่ยนสัมประสิทธิ์ 0.14 ในสมการ PM₀.₁

ทดสอบ: `python -m unittest discover -s tests` และ `node --test tests/test_idw.cjs tests/test_data.cjs` ตรวจเวลาไทย/ใกล้ปัจจุบัน ช่วงสี สมการ ค่าเฉลี่ยตามพื้นที่ การเลือกแหล่งข้อมูล ช่วงพยากรณ์จริงครบ 121 ชั่วโมง และ IDW


## VIIRS NOAA Deep Blue

`viirs/` discovers only NOAA-20 and NOAA-21 L2 Version 2.1, querying CMR with the Kuan Kreng bounding box and at most92 calendar days. Standard LAADS granules replace ASIPS NRT for the same acquisition; SNPP is excluded. Only intersecting swath files are downloaded (not global products). Native pixel centres must lie in the exact study polygon. Land AOD550 best-estimate and QA2/3 samples are aggregated on a boundary-clipped6km UTM reporting grid and Thai calendar day, then passed directly to the original Extra Trees input column `AOD 0.47`, as explicitly approved by the project owner. Metadata records the actual550nm wavelength; no wavelength conversion or model retraining occurs. The reporting grid is not the native swath footprint and does not imply1km resolution.

Outputs `docs/data/viirs_history.json` and `viirs_grid.geojson` are mirrored by the central monitoring platform. Missing values stay NoData; daily means represent available overpasses and reporting-cell support, not a24-hour mean. Observation times/platforms and input granules remain in the snapshot. Provider failures preserve verified previous records and their original check times.

`.github/workflows/viirs_noaa.yml` refreshes every3hours at UTC minute43 using the existing `NASA_EARTHDATA_TOKEN` and `MODEL_DECRYPT_KEY_B64` Actions secrets. Backfill can be dispatched with `max_days=92`; scheduled runs process up to12 changed days. Raw swaths and the decrypted model are not committed.

Validation: `python -m unittest discover -s tests -p test_viirs.py -v`.
