# KK-PSF: MAIAC AOD → PM₂.₅

เว็บไซต์ใน `docs/` แสดงค่าประเมิน PM₂.₅ ย้อนหลัง 3 เดือนสำหรับพรุควนเคร็ง โดยใช้ NASA MAIAC มาตรฐาน (`MCD19A2`) สำหรับวันย้อนหลัง และ Near Real-Time (`MCD19A2N`) เมื่อข้อมูลมาตรฐานยังไม่เผยแพร่ ใช้ AOD 470 nm กับโมเดล Extra Trees เดิมของโครงการ ผลลัพธ์คือ **ค่าประเมิน PM₂.₅ จากโมเดล** ไม่ใช่ค่าตรวจวัดจากสถานี ส่วน CAMS จะเพิ่มเมื่อบริการกลับมาใช้งานได้

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

เว็บไซต์ GitHub Pages เผยแพร่ไฟล์ใน `docs/` และแสดงเฉพาะ GeoJSON ที่ตัดตามขอบเขตพรุควนเคร็ง ไฟล์ HDF ต้นฉบับไม่เผยแพร่ ช่วงแรกคือ 16 ส.ค.–15 พ.ย. 2026 (92 วัน) วันที่ไม่มี AOD ผ่าน QA แสดง `NoData` และไม่มีตัวเลข PM₂.₅ เมื่อข้อมูล NASA ของวันยังไม่มี แสดง `NotPublished`

```powershell
python -m maiac.backfill --start 2026-08-16 --end 2026-11-15 --boundary '.\data\boundaries\kkpsf_boundary.geojson' --grid '.\data\boundaries\kkpsf_grid_1km.gpkg' --model 'D:\LAB - PM2.5\FINAL ML-AOD\Final BestModel\Extra Trees Model\ET-2 Model\Extra_Trees_model.pkl'
python -m maiac.export_site --start 2026-08-16 --end 2026-11-15 --boundary '.\data\boundaries\kkpsf_boundary.geojson' --grid '.\data\boundaries\kkpsf_grid_1km.gpkg' --site-data docs/data --require-complete
python -m http.server 8765 --directory docs
```

`backfill` ค้นหาผ่าน NASA CMR เฉพาะ tile `h27v08` และใช้ NRT เป็นแหล่งสำรองสำหรับวันล่าสุด เมื่อรันซ้ำจะข้ามวันที่ประมวลผลแล้ว เว็บไซต์เป็นไฟล์สถิติจึงแสดงข้อมูลตามเวลาที่ส่งออกครั้งล่าสุด

### อัปเดตรายวันผ่าน GitHub Actions

Workflow `.github/workflows/update_maiac.yml` ตั้งเวลา 20:23 น. ประเทศไทยทุกวัน และสั่งรันเองได้ด้วย `workflow_dispatch` โดยใช้ `maiac.refresh_site` คงช่วง 92 วันล่าสุด ตรวจเฉพาะวันที่เพิ่งเพิ่ม วันที่ NASA ยังไม่เผยแพร่ และ 3 วันล่าสุดเพื่อเปลี่ยนจาก NRT เป็นไฟล์มาตรฐานเมื่อมีไฟล์ใหม่ ระบบจะเก็บ `NoData` และ `NotPublished` ตามจริง ถ้าดาวน์โหลดหรือประมวลผลผิดพลาด Workflow จะหยุดก่อนเผยแพร่ ทำให้เว็บเดิมยังคงใช้ได้

ก่อนเปิดใช้งาน ต้องเพิ่ม repository secrets สองค่าใน GitHub: `NASA_EARTHDATA_TOKEN` สำหรับ NASA และ `MODEL_DECRYPT_KEY_B64` สำหรับถอดรหัสไฟล์ `models/Extra_Trees_model.pkl.aesgcm` ที่สร้างจากโมเดลต้นฉบับ ห้ามใส่ค่า secret ใน YAML, HTML, JavaScript, JSON หรือ Git commit จากนั้นตั้ง Pages Source เป็น **GitHub Actions** และรัน Workflow ด้วยมือหนึ่งครั้งเพื่อทดสอบ ก่อนปล่อยให้ตารางเวลาทำงาน หากไม่มี secrets Workflow จะไม่สามารถคำนวณข้อมูลใหม่ได้

## วิธีประมวลผล

1. เลือกเฉพาะไฟล์ `MCD19A2` หรือ `MCD19A2N` ของวันและ MODIS tile ที่ขอบเขตตัดผ่าน สำหรับขอบเขตนี้เลือกเพียงไฟล์ `h27v08` หนึ่งไฟล์ต่อวัน ไม่ดาวน์โหลดข้อมูลทั่วโลก NASA เผยแพร่ไฟล์ต้นทางเป็นระดับไทล์ จึงมีพื้นที่นอกขอบเขตอยู่ภายในไฟล์ต้นทาง แต่ไม่รวมในผลลัพธ์เชิงพื้นที่
2. อ่าน `Optical_Depth_047`, ชั้น QA (`AOD_QA` ในไฟล์ NRT ที่ตรวจพบ; รองรับ `AOT_QA` ด้วย) และ scale/offset/fill/range จาก HDF4
3. เก็บเฉพาะ land, clear, normal adjacency และ best AOD quality ตาม [MAIAC C6.1 User Guide](https://modis-land.gsfc.nasa.gov/pdf/MCD19_UserGuide_C61_V3.1.pdf)
4. หาค่า median ของ overpass ที่ใช้ได้ต่อ pixel ต่อวัน แล้วสุ่มค่าจาก pixel ที่ครอบคลุมจุดตัวแทนภายในแต่ละกริด UTM 1 กม. หากมีหลาย overpass เวลาในผลลัพธ์เป็นเวลาของ overpass ที่มีค่าใกล้ median ที่สุด
5. ส่ง AOD ที่ใช้ได้เข้าโมเดลเดิมด้วย DataFrame คอลัมน์ `AOD 0.47` โดยไม่ฝึกใหม่

วันที่ในชื่อไฟล์และคอลัมน์ `date` เป็นวันของผลิตภัณฑ์ใน UTC; เวลาไทยของ overpass อยู่ใน `data_time_thailand` แยกต่างหาก กริด 1 กม. เป็นกริดสำหรับรายงาน ไม่ได้ทำให้ความละเอียดของดาวเทียมสูงขึ้น

## สถานะข้อมูล

ข้อมูลในเว็บไซต์อยู่ใน `docs/data/history.json` โดยระบุวันเริ่มต้น วันสิ้นสุด สถานะ จำนวนกริดที่มี AOD ผ่าน QA และเวลาส่งออก วันที่ 15 พ.ย. 2026 มี AOD ที่ใช้ได้ **0/1,052 ช่อง** จึงเป็น `NoData` ทั้งหมด ไฟล์ HDF ต้นทาง ผลลัพธ์เต็ม และตัวแปรโทเคนไม่ถูกเพิ่มเข้า repository
