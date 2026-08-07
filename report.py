"""
รายงานสรุปตลาดทุกเช้า (Multi-Timeframe Analysis) - ส่งอีเมล + เก็บไฟล์ประวัติ
=====================================================================
วิเคราะห์ทองคำ (XAUUSD) หลาย Timeframe พร้อมกัน (H4, H1, M15) แล้วสรุปเป็นรายงาน:
  1. แนวโน้มแต่ละ Timeframe (ขึ้น/ลง)
  2. แนวรับ-แนวต้านสำคัญ
  3. แผนเทรด 2 ทาง (ถ้าราคาไปทางไหน ควรทำอะไร)

**ใช้ข้อมูลจาก Yahoo Finance (yfinance) - ไม่ต้องเปิด MT5 หรือล็อกอินอะไรเลย!**

ส่งผลลัพธ์ 2 ทาง:
  1. ส่งอีเมลสรุปให้ทุกครั้งที่รัน
  2. บันทึกไฟล์ .md ไว้ในโฟลเดอร์ reports/ ของ repo (เก็บประวัติทุกวัน ดูย้อนหลังได้)

**สคริปต์นี้รันครั้งเดียวจบแล้วปิดตัวเอง** เหมาะกับการตั้งให้รันอัตโนมัติผ่าน
GitHub Actions (ฟรี ไม่ต้องเปิดคอมที่บ้านเลย)

วิธีใช้งาน (ทดสอบบนเครื่องตัวเอง):
  1. ติดตั้งไลบรารี: pip install yfinance pandas
  2. ใส่ค่าอีเมลด้านล่าง (GMAIL_ADDRESS, GMAIL_APP_PASSWORD, EMAIL_TO)
     - GMAIL_APP_PASSWORD ไม่ใช่รหัสผ่าน Gmail ปกติ ต้องสร้าง "App Password" แยกต่างหาก
       (เข้า myaccount.google.com -> Security -> 2-Step Verification -> App Passwords)
  3. ทดสอบรันมือก่อน: python daily_market_report.py

วิธีตั้งให้รันอัตโนมัติฟรีผ่าน GitHub Actions: ดูคำแนะนำที่ผมส่งให้แยกต่างหาก
"""

import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import pandas as pd
import yfinance as yf

# ========================= ตั้งค่าตรงนี้ =========================

# อ่านจาก Environment Variable ก่อน (สำหรับ GitHub Actions) ถ้าไม่มีค่อยใช้ค่าที่พิมพ์ไว้ตรงนี้
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "ใส่_อีเมล_Gmail_ที่จะส่งออกตรงนี้")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "ใส่_App_Password_ตรงนี้")
EMAIL_TO = os.environ.get("EMAIL_TO", "ใส่_อีเมลปลายทางที่จะรับรายงานตรงนี้")

SYMBOL_NAME = "XAUUSD"
SYMBOL_TICKER = "GC=F"   # ทองคำ (COMEX Gold Futures - ราคาใกล้เคียงกับ Spot Gold มาก)

# Timeframe ที่จะวิเคราะห์ (จากใหญ่ไปเล็ก) พร้อมช่วงเวลาย้อนหลังที่เหมาะสมของแต่ละอัน
# หมายเหตุสำคัญ: Yahoo Finance ไม่รองรับ interval "4h" โดยตรง (ยืนยันจากเอกสารทางการ)
# ค่าที่รองรับจริงมีแค่ 1m,2m,5m,15m,30m,60m/1h,1d,5d,1wk,1mo,3mo เท่านั้น
# ดังนั้น H4 ต้องดึงข้อมูล H1 มาแล้ว "รวมแท่ง" เอง (resample) แทน ไม่ใช่ขอ "4h" ตรงๆ
TIMEFRAMES = {
    "H4": {"interval": "1h", "period": "60d", "resample_to_4h": True},
    "H1": {"interval": "1h", "period": "60d", "resample_to_4h": False},
    "M15": {"interval": "15m", "period": "5d", "resample_to_4h": False},
}

SR_LOOKBACK = 50            # จำนวนแท่งเทียนย้อนหลังที่ใช้หาแนวรับ-แนวต้าน (จาก TF หลักคือ H1)
SR_TOUCH_TOLERANCE_PIPS = 30   # ระยะที่ถือว่า "แตะระดับเดียวกัน" (pips) สำหรับนับจำนวนครั้งที่ราคาแตะ
ADX_PERIOD = 14              # ใช้วัดความแข็งแรงของเทรนด์ (ไม่ใช่แค่ทิศทาง)
REPORTS_FOLDER = "reports"  # โฟลเดอร์เก็บไฟล์ประวัติรายงาน

# =================================================================


def get_pip_size(symbol: str) -> float:
    if "XAU" in symbol:
        return 0.1
    return 0.01 if "JPY" in symbol else 0.0001


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """คำนวณ ADX เพื่อวัดความแข็งแรงของเทรนด์ (ไม่ใช่แค่ทิศทางขึ้น/ลง)"""
    high, low, close = df["High"], df["Low"], df["Close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di) * 100
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def get_tf_data(ticker: str, interval: str, period: str, resample_to_4h: bool = False) -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if df.empty:
        return pd.DataFrame()
    # yfinance บางเวอร์ชันคืนคอลัมน์แบบ 2 ชั้น (MultiIndex) ต้องแปลงให้เป็นชั้นเดียวก่อน
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if resample_to_4h:
        # รวมแท่ง H1 ทุก 4 แท่งเป็น 1 แท่ง H4 เอง (เพราะ Yahoo ไม่มี interval 4h ให้โดยตรง)
        df = df.resample("4h").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
        }).dropna()

    df["ema20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["adx"] = compute_adx(df, ADX_PERIOD)
    return df


def get_trend_bias(df: pd.DataFrame) -> str:
    """แนวโน้มจาก EMA20 เทียบ EMA50 พร้อมบอกความแข็งแรงของเทรนด์จาก ADX ประกอบ"""
    if df.empty or len(df) < 50:
        return "ข้อมูลไม่พอ"
    last = df.iloc[-1]
    direction = "ขาขึ้น (Bullish)" if last["ema20"] > last["ema50"] else "ขาลง (Bearish)"
    adx_val = float(last["adx"]) if pd.notna(last["adx"]) else 0
    if adx_val >= 25:
        strength = "แข็งแรง"
    elif adx_val >= 15:
        strength = "ปานกลาง"
    else:
        strength = "อ่อน/ไซด์เวย์"
    return f"{direction} (แรง: {strength}, ADX {adx_val:.0f})"


def get_support_resistance(df: pd.DataFrame, lookback: int, pip_size: float, tolerance_pips: float, current_price: float):
    """หาแนวรับ-แนวต้านแบบนับจำนวนครั้งที่ราคาแตะระดับใกล้เคียงกัน (pivot ที่ถูกทดสอบซ้ำน่าเชื่อถือกว่า)
    ค้นหาแนวต้านเฉพาะจากจุดที่อยู่ 'เหนือ' ราคาปัจจุบัน และแนวรับเฉพาะจุดที่อยู่ 'ใต้' ราคาปัจจุบันเท่านั้น
    (กันปัญหาแนวต้านต่ำกว่าแนวรับ ซึ่งผิดตรรกะ)"""
    recent = df.tail(lookback)
    tolerance = tolerance_pips * pip_size

    highs_above = [h for h in recent["High"].tolist() if h > current_price]
    lows_below = [l for l in recent["Low"].tolist() if l < current_price]

    # ถ้าไม่มีจุดไหนอยู่เหนือ/ใต้ราคาปัจจุบันเลย (เช่น ราคาหลุดกรอบไปแล้ว) ใช้ค่าสูงสุด/ต่ำสุดทั้งหมดแทน
    if not highs_above:
        highs_above = recent["High"].tolist()
    if not lows_below:
        lows_below = recent["Low"].tolist()

    def find_best_level(prices: list) -> tuple:
        """หาระดับราคาที่มีจุดมาแตะ/รวมกลุ่มกันมากที่สุด (นับเป็น pivot ที่แข็งแรงที่สุด)"""
        best_level, best_count = prices[0], 0
        for p in prices:
            count = sum(1 for other in prices if abs(other - p) <= tolerance)
            if count > best_count:
                best_level, best_count = p, count
        return best_level, best_count

    resistance, r_touches = find_best_level(highs_above)
    support, s_touches = find_best_level(lows_below)

    # กันเหนียวขั้นสุดท้าย: ถ้ายังผิดตรรกะอยู่ (ไม่ควรเกิดขึ้นแล้ว) ใช้ max/min ธรรมดาแทน
    if resistance <= support:
        resistance = float(recent["High"].max())
        support = float(recent["Low"].min())
        r_touches = s_touches = 1

    return support, resistance, s_touches, r_touches


def build_report() -> str:
    tf_bias = {}
    h1_df = pd.DataFrame()
    for tf_name, cfg in TIMEFRAMES.items():
        df = get_tf_data(SYMBOL_TICKER, cfg["interval"], cfg["period"], cfg.get("resample_to_4h", False))
        tf_bias[tf_name] = get_trend_bias(df)
        if tf_name == "H1":
            h1_df = df  # เก็บไว้ใช้หาแนวรับ-แนวต้านจาก TF หลัก

    if h1_df.empty:
        return "ไม่สามารถดึงข้อมูลราคาได้ในขณะนี้ ลองใหม่อีกครั้ง"

    pip = get_pip_size(SYMBOL_NAME)
    current_price = float(h1_df.iloc[-1]["Close"])
    support, resistance, s_touches, r_touches = get_support_resistance(
        h1_df, SR_LOOKBACK, pip, SR_TOUCH_TOLERANCE_PIPS, current_price
    )

    # แผนเทรด 2 ทาง (อธิบายเงื่อนไขคร่าวๆ อิงจากแนวรับ-แนวต้าน)
    dist_to_resistance = (resistance - current_price) / pip
    dist_to_support = (current_price - support) / pip

    report = (
        f"รายงานสรุปตลาด {SYMBOL_NAME}\n"
        f"วันที่: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"ราคาปัจจุบัน: {current_price:.2f}\n\n"
        f"แนวโน้มแต่ละ Timeframe:\n"
        f"H4: {tf_bias.get('H4', '-')}\n"
        f"H1: {tf_bias.get('H1', '-')}\n"
        f"M15: {tf_bias.get('M15', '-')}\n\n"
        f"แนวรับ-แนวต้าน (อิง H1 ย้อนหลัง {SR_LOOKBACK} แท่ง, นับจุดที่ราคาแตะซ้ำ):\n"
        f"แนวต้าน: {resistance:.2f} (ถูกแตะ {r_touches} ครั้ง, ห่างจากราคาปัจจุบัน {dist_to_resistance:.0f} pips)\n"
        f"แนวรับ: {support:.2f} (ถูกแตะ {s_touches} ครั้ง, ห่างจากราคาปัจจุบัน {dist_to_support:.0f} pips)\n\n"
        f"แผนเทรด 2 ทาง:\n"
        f"ฝั่ง Buy: ถ้าราคาทะลุ {resistance:.2f} ขึ้นไปได้ชัดเจน "
        f"แสดงว่าแนวโน้มขาขึ้นแข็งแรง น่าติดตามหาจังหวะ Buy ตามแนวโน้ม\n"
        f"ฝั่ง Sell: ถ้าราคาหลุด {support:.2f} ลงไปชัดเจน "
        f"แสดงว่าแนวโน้มขาลงแข็งแรง น่าติดตามหาจังหวะ Sell ตามแนวโน้ม\n\n"
        f"หมายเหตุ: นี่คือการวิเคราะห์อัตโนมัติจากราคาย้อนหลังเท่านั้น ไม่รวมข่าวเศรษฐกิจ "
        f"กรุณาเช็คปฏิทินข่าวเพิ่มเติมเองก่อนตัดสินใจเทรด"
    )
    return report


def send_email(subject: str, body: str):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, [EMAIL_TO], msg.as_string())
        print("ส่งอีเมลสำเร็จแล้ว")
    except Exception as e:
        print(f"[Email Error] ส่งอีเมลไม่สำเร็จ: {e}")


def save_report_to_file(report: str):
    os.makedirs(REPORTS_FOLDER, exist_ok=True)
    filename = os.path.join(REPORTS_FOLDER, f"{datetime.now().strftime('%Y-%m-%d')}.md")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# {report}")
    print(f"บันทึกไฟล์ประวัติแล้ว: {filename}")


def main():
    print("เริ่มสร้างรายงานสรุปตลาด (ใช้ข้อมูลจาก Yahoo Finance ไม่ต้องพึ่ง MT5)...")
    report = build_report()
    print(report)

    today_str = datetime.now().strftime("%Y-%m-%d")
    send_email(subject=f"รายงานสรุปตลาดทอง {today_str}", body=report)
    save_report_to_file(report)


if __name__ == "__main__":
    main()


# =========================================================================
# วิธีตั้งให้รันอัตโนมัติทุกวัน: ดูไฟล์คำแนะนำ GitHub Actions ที่ส่งแยกให้
# (ไม่ต้องเปิดคอมที่บ้านเลย ฟรี 100%)
# =========================================================================
