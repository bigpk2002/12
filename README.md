# รายงานทอง XAU/USD อัตโนมัติทุกเช้า

ระบบ: ดึงราคาทอง 3 timeframe (4H/1H/15M) → ให้ Gemini (ฟรี) วิเคราะห์ → ส่งเข้า LINE ของตัวเอง

## 1) ติดตั้ง

```bash
pip install -r requirements.txt
cp .env.example .env
# แล้วแก้ .env ใส่ key จริง
```

โหลด env ก่อนรัน (หรือใช้ `python-dotenv` ก็ได้ ในที่นี้ใช้วิธีง่ายสุดคือ export ใน shell / cron):

```bash
export $(grep -v '^#' .env | xargs)
python3 report.py
```

## 2) หา API key แต่ละตัว

### Twelve Data (ราคาทอง, ฟรี)
1. สมัครที่ https://twelvedata.com/pricing (แผน Free: 8 requests/นาที, 800/วัน — พอสำหรับรันวันละครั้ง)
2. เข้า Dashboard → คัดลอก API Key → ใส่ใน `TWELVE_DATA_API_KEY`

### Gemini API key (ให้ AI วิเคราะห์ราคา — ฟรีถาวร ไม่ต้องผูกบัตร)
1. ไปที่ https://aistudio.google.com/apikey (ล็อกอินด้วยบัญชี Google)
2. กด **Create API key** → เลือกหรือสร้างโปรเจกต์ใหม่ก็ได้ (ไม่ต้องเปิด billing)
3. คัดลอกค่า key ที่ได้ → ใส่ใน `GEMINI_API_KEY`
4. Free tier ให้ประมาณ 1,500 requests/วัน ไม่มีวันหมดอายุ งานนี้ใช้แค่วันละครั้งเดียว สบายมาก
5. ข้อควรรู้: บน free tier ข้อมูลที่ส่งเข้าไปอาจถูกนำไปใช้พัฒนาโมเดลของ Google (ไม่ใช่ปัญหาสำหรับข้อมูลราคาทองทั่วไป)

### LINE Messaging API (ส่งข้อความหาตัวเอง)
LINE Notify ปิดบริการไปแล้วตั้งแต่ 31 มี.ค. 2025 ตอนนี้ต้องใช้ Messaging API แทน (ฟรีสำหรับใช้งานส่วนตัว):

1. ไปที่ https://developers.line.biz/console/ → สร้าง Provider ใหม่ (ชื่ออะไรก็ได้)
2. สร้าง Channel ชนิด **Messaging API**
3. ในหน้า Channel → แท็บ **Messaging API** → เลื่อนลงไปหา **Channel access token** → กด Issue → คัดลอกใส่ `LINE_CHANNEL_ACCESS_TOKEN`
4. หน้าเดียวกันจะมี QR code ของ Official Account ที่เพิ่งสร้าง → **สแกนเพิ่มเพื่อนด้วย LINE ตัวเอง** (ต้องแอดเป็นเพื่อนก่อนถึงจะส่งข้อความหาได้)
5. หา `LINE_USER_ID` ของตัวเอง: วิธีง่ายสุดคือเปิด **Webhook** ในหน้า Channel, ตั้ง webhook URL ชั่วคราว (เช่นใช้ https://webhook.site เพื่อดู payload), ทักแชทหา Official Account ที่สร้าง แล้วดู `userId` ใน payload ที่ส่งมา หรือดูวิธีละเอียดใน https://developers.line.biz/en/docs/messaging-api/getting-user-ids/

## 3) ทดสอบรันครั้งเดียว

```bash
python3 report.py
```

ถ้าสำเร็จ จะมีข้อความรายงานเด้งเข้า LINE ทันที

## 4) ตั้งเวลารันทุกเช้า 9 โมง

**ตัวเลือก A: cron (ถ้ามีเครื่อง/เซิร์ฟเวอร์เปิดทิ้งไว้ตลอด)**

```bash
crontab -e
# เพิ่มบรรทัดนี้ (รันทุกวัน 9:03 - เลี่ยงนาที 00 ตรงเป๊ะเพื่อกัน jitter ของบางระบบ)
3 9 * * * cd /path/to/gold_report && export $(grep -v '^#' .env | xargs) && /usr/bin/python3 report.py >> run.log 2>&1
```

**ตัวเลือก B: Claude Code Scheduled Task / Routine**
ถ้าใช้ Claude Code อยู่แล้ว สามารถตั้งเป็น Desktop scheduled task หรือ cloud Routine ให้รันสคริปต์นี้ทุกเช้า 9 โมงได้เลย โดยไม่ต้องพึ่ง cron ของเครื่องเอง (ดูรายละเอียดที่ https://code.claude.com/docs/en/scheduled-tasks)

**ตัวเลือก C: GitHub Actions (ถ้าอยากรันบน cloud ฟรี ไม่ต้องมีเครื่องเปิดทิ้งไว้)**
ตั้ง schedule trigger ใน `.github/workflows/*.yml` แล้วเก็บ API keys เป็น GitHub Secrets

## 5) รันบน GitHub Actions (ฟรี ไม่ต้องมีเครื่อง/เซิร์ฟเวอร์เปิดทิ้งไว้)

### ขั้นตอนละเอียด

**A. สร้างบัญชีและ repo**
1. สมัคร/ล็อกอิน https://github.com
2. มุมขวาบน กด **+** → **New repository**
3. ตั้งชื่อ เช่น `gold-report` → เลือก **Private** (สำคัญ เพราะจะมีการอ้างอิงถึง secrets) → กด **Create repository**

**B. อัปโหลดไฟล์ทั้งหมด**
วิธีง่ายสุดถ้าไม่คุ้น git command line:
1. ในหน้า repo ที่สร้าง กด **Add file** → **Upload files**
2. ลากไฟล์ทั้งหมดเข้าไปให้ครบ **รวมโฟลเดอร์ `.github/workflows/daily-report.yml` ด้วย** (ต้องคงโครงสร้างโฟลเดอร์นี้ไว้ ห้ามเปลี่ยน path)
3. **ห้ามอัปโหลดไฟล์ `.env`** (มีแต่ `.env.example` พอ) เพราะ key จริงจะไปเก็บที่ GitHub Secrets แทน (ขั้นตอน C)
4. กด **Commit changes**

**C. ใส่ API keys เป็น Secrets** (ปลอดภัยกว่าใส่ในไฟล์ตรงๆ)
1. ในหน้า repo → **Settings** (แท็บบนสุด) → เมนูซ้าย **Secrets and variables** → **Actions**
2. กด **New repository secret** ทีละตัว ใส่ 4 ตัวนี้ (ชื่อต้องตรงเป๊ะตามนี้):
   - `TWELVE_DATA_API_KEY`
   - `GEMINI_API_KEY`
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_USER_ID`

**D. เปิดใช้งาน Actions**
1. ไปแท็บ **Actions** ด้านบน repo
2. ถ้าขึ้นให้กดยืนยันเปิดใช้ Actions ก็กด **I understand my workflows, go ahead and enable them**

**E. ทดสอบรันทันที (ไม่ต้องรอถึง 8:45)**
1. แท็บ **Actions** → เลือก workflow ชื่อ **Daily Gold Report** ทางซ้าย
2. ขวามือจะมีปุ่ม **Run workflow** → กด **Run workflow** อีกที
3. รอสัก 10-20 วินาที รีเฟรชหน้า จะเห็นสถานะกำลังรัน (วงกลมเหลืองหมุน) → ถ้าจบแล้วเป็นติ๊กเขียว = สำเร็จ, กากบาทแดง = error (กดเข้าไปดู log ได้ว่าพังตรงไหน)
4. เช็ค LINE ว่ามีข้อความเด้งมาไหม

**F. ปล่อยให้รันอัตโนมัติทุกวัน**
ไม่ต้องทำอะไรต่อ — workflow จะรันเองทุกวันตามเวลา `45 1 * * *` (UTC) = **08:45 เวลาไทย** ตามที่ตั้งไว้ในไฟล์ `.github/workflows/daily-report.yml`

อยากเปลี่ยนเวลา ให้แก้บรรทัด `cron:` ในไฟล์นั้น (นึกเป็นเวลา UTC เสมอ แล้วลบ 7 ชั่วโมงจากเวลาไทยที่อยากได้)

### กันโดนปิด (60 วันไม่มี activity)
Workflow นี้ใส่ step "Keep-alive commit" ไว้ให้แล้ว — ทุกครั้งที่รันจะ commit ไฟล์ `.last_run` กลับเข้า repo อัตโนมัติ ทำให้ repo ไม่เงียบเกิน 60 วัน ไม่ต้องกลัวโดน GitHub ปิด schedule ให้เอง

## ข้อควรทราบ

- รายงานที่ได้เป็น **สรุปทางเทคนิคตามกฎที่กำหนดในพรอมต์** ไม่ใช่การพยากรณ์ราคาที่แม่นยำ ควรใช้ประกอบการตัดสินใจ ไม่ใช่สัญญาณให้ทำตามทันที
- Twelve Data แผนฟรีมี rate limit ถ้ารันบ่อยเกิน 8 ครั้ง/นาทีจะโดน error 429
- ถ้าอยากได้ timeframe อื่น หรือสัญลักษณ์อื่น (เช่น BTC/USD) แก้ตัวแปร `SYMBOL` และ `TIMEFRAMES` ใน `report.py` ได้เลย
