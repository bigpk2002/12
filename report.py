"""
Daily XAU/USD (Gold) trading report generator.
Pipeline: Twelve Data (historical candles, may be delayed) + goldprice.dev (live spot price)
          -> Gemini (analysis, free tier) -> LINE Messaging API (delivery)

Run manually:  python3 report.py
Run on schedule: see README.md for cron / GitHub Actions setup
"""

import os
import re
import sys
import requests
from datetime import datetime

# ---- Config (set these as environment variables, see .env.example) ----
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

GEMINI_MODEL = "gemini-flash-latest"  # auto-updating alias, avoids breakage when versions retire

SYMBOL = "XAU/USD"
TIMEFRAMES = [
    {"interval": "4h", "outputsize": 60, "label": "4H (เทรนด์หลัก)"},
    {"interval": "1h", "outputsize": 60, "label": "1H (โครงสร้างกราฟ)"},
    {"interval": "15min", "outputsize": 60, "label": "15M (จุดเข้า)"},
]


def fetch_candles(interval: str, outputsize: int) -> list[dict]:
    """Fetch OHLC candles for XAU/USD from Twelve Data (delayed on free tier)."""
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": SYMBOL,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
    }
    resp = requests.get(url, params=params, timeout=20)
    data = resp.json()
    if "values" not in data:
        raise RuntimeError(f"Twelve Data error for {interval}: {data}")
    # API returns newest first; reverse to chronological order
    return list(reversed(data["values"]))


def fetch_live_price() -> dict | None:
    """Fetch near-real-time XAU/USD spot price from goldprice.dev (free, no key needed).
    Returns None if unavailable so the report still works without it."""
    try:
        resp = requests.get(
            "https://api.goldprice.dev/v1/prices",
            params={"symbol": "XAU-USD-SPOT"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        row = data["symbols"][0]
        return {
            "price": row.get("price"),
            "bid": row.get("bid"),
            "ask": row.get("ask"),
            "computed_at": row.get("computed_at"),
            "is_stale": row.get("is_stale"),
        }
    except Exception:
        return None


def candles_to_compact_text(candles: list[dict]) -> str:
    """Turn candle list into a compact CSV-like block to keep the prompt small."""
    lines = ["datetime,open,high,low,close"]
    for c in candles:
        lines.append(f"{c['datetime']},{c['open']},{c['high']},{c['low']},{c['close']}")
    return "\n".join(lines)


def build_prompt(market_data_blocks: dict[str, str], live_price: dict | None) -> str:
    sections = []
    for label, block in market_data_blocks.items():
        sections.append(f"### {label}\n{block}")
    joined = "\n\n".join(sections)

    if live_price and live_price.get("price"):
        live_note = (
            f"\nราคาล่าสุดแบบเรียลไทม์ (จาก goldprice.dev, ณ {live_price.get('computed_at')}): "
            f"{live_price.get('price')} USD (bid {live_price.get('bid')} / ask {live_price.get('ask')})\n"
            "หมายเหตุ: ข้อมูลแท่งเทียนด้านล่างจาก Twelve Data แผนฟรีอาจดีเลย์ได้หลายชั่วโมง "
            "ให้ใช้ราคาเรียลไทม์นี้เป็นราคาอ้างอิงปัจจุบัน แต่ใช้แท่งเทียนด้านล่างวิเคราะห์โครงสร้าง/เทรนด์"
        )
    else:
        live_note = "\n(ไม่มีข้อมูลราคาเรียลไทม์ในรอบนี้ ให้ใช้ราคาปิดล่าสุดในแท่งเทียนแทน)"

    return f"""คุณคือนักวิเคราะห์เทคนิคทองคำ (XAU/USD) ให้วิเคราะห์ข้อมูลราคาย้อนหลังหลาย timeframe ด้านล่าง
แล้วสรุปเป็นรายงานสั้น กระชับ อ่านเร็วบนมือถือ ใช้หัวข้อดังนี้เป๊ะๆ:

1. เทรนด์แต่ละ timeframe (4H/1H/15M) - ขึ้น/ลง/แกว่ง
2. โครงสร้างกราฟสำคัญ (higher high/low หรือ lower high/low ล่าสุด)
3. แนวรับ-แนวต้านสำคัญ (ระบุตัวเลขราคาโดยประมาณจากข้อมูลที่ให้)
4. แผนวันนี้: เงื่อนไข buy และเงื่อนไข sell แยกกัน (ถ้าราคาทำอะไรถึงจะเข้า) — เทียบกับราคาเรียลไทม์ปัจจุบันด้วยถ้ามี
   สำหรับ "ทุกเงื่อนไข" ที่เสนอ (ทั้ง buy และ sell ทุกสถานการณ์ย่อย) ต้องระบุครบ 3 ค่าเสมอ ห้ามขาดข้อใดข้อหนึ่ง:
   - Entry: ราคาที่จะเข้า
   - SL (stop loss): จุดตัดขาดทุน
   - TP (take profit): จุดทำกำไร อย่างน้อย 1 เป้าหมาย (ระบุเป็นตัวเลขราคา ไม่ใช่แค่คำว่า "เป้าหมายถัดไป")
5. ข้อควรระวัง (ข่าวสำคัญ/ความผันผวน) ถ้าประเมินจากข้อมูลไม่ได้ให้บอกว่าไม่มีข้อมูลข่าว

ห้ามฟันธงว่าราคาจะไปทางไหนแน่นอน ให้เขียนเป็นเงื่อนไข (ถ้า...แล้ว...) เท่านั้น
ปิดท้ายด้วยประโยคเตือนสั้นๆ ว่านี่คือการวิเคราะห์ทางเทคนิคอัตโนมัติ ไม่ใช่คำแนะนำการลงทุน ผู้ใช้ต้องตัดสินใจและบริหารความเสี่ยงเอง
{live_note}

ข้อมูลราคาย้อนหลัง (อาจดีเลย์):

{joined}
"""


def call_gemini(prompt: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    resp = requests.post(
        url,
        params={"key": GEMINI_API_KEY},
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 4096},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        candidate = data["candidates"][0]
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise RuntimeError(
                f"Gemini returned no visible text (finishReason={candidate.get('finishReason')}). "
                f"Full response: {data}"
            )
        if candidate.get("finishReason") == "MAX_TOKENS":
            text += "\n\n⚠️ (รายงานอาจถูกตัดตอนเพราะโทเค็นไม่พอ)"
        return text
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected Gemini response: {data}")


def _clean_line(line: str) -> str:
    """Strip markdown artifacts (**bold**, leading ###, leading list markers) Gemini tends to add,
    since Flex text doesn't render markdown and would show the raw symbols otherwise."""
    line = line.strip()
    line = line.lstrip("#").strip()
    line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)  # **bold** -> bold
    line = re.sub(r"^\*\s+", "• ", line)  # markdown bullet "* " -> "• "
    line = line.replace("*", "")  # drop any remaining stray asterisks
    return line.strip()


def build_flex_contents(header_lines: list[str], report_text: str) -> dict:
    """Build a LINE Flex Message bubble with a black background:
    - all text is white for readability on black
    - section headers -> bold, slightly larger, extra space above
    - any line mentioning TP / SL / Entry / แนวรับ / แนวต้าน / ราคาสด -> bold + underline
    - the closing disclaimer -> italic, muted grey
    - generous spacing throughout so it's easy to read on a phone
    """
    contents = []

    for line in header_lines:
        contents.append(
            {"type": "text", "text": line, "weight": "bold", "size": "lg", "color": "#FFFFFF", "wrap": True, "margin": "md"}
        )
    contents.append({"type": "separator", "margin": "lg", "color": "#333333"})

    section_header_re = re.compile(r"^(#{1,3}\s*)?\d+\.\s")
    highlight_re = re.compile(
        r"\bTP\b|\bSL\b|\bEntry\b|take profit|stop loss|แนวรับ|แนวต้าน|ราคาสด|ราคาเรียลไทม์",
        re.IGNORECASE,
    )

    for raw_line in report_text.split("\n"):
        stripped_raw = raw_line.strip()
        if stripped_raw and set(stripped_raw) <= {"-", "_", "*"} and len(stripped_raw) >= 3:
            contents.append({"type": "separator", "margin": "lg", "color": "#333333"})
            continue

        line = _clean_line(raw_line)
        if not line:
            continue

        node = {"type": "text", "text": line, "wrap": True, "size": "sm", "margin": "md", "color": "#FFFFFF"}

        if section_header_re.match(raw_line.strip()) or raw_line.strip().startswith("###"):
            node.update({"weight": "bold", "size": "md", "margin": "xl"})
        elif "ไม่ใช่คำแนะนำการลงทุน" in line or line.startswith("⚠️"):
            node.update({"style": "italic", "size": "xs", "color": "#AAAAAA", "margin": "xl"})
        elif highlight_re.search(line):
            node.update({"weight": "bold", "decoration": "underline"})

        contents.append(node)

    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "backgroundColor": "#000000",
            "paddingAll": "xl",
            "contents": contents,
        },
    }


def send_to_line(header_lines: list[str], report_text: str) -> None:
    bubble = build_flex_contents(header_lines, report_text)
    alt_text = (header_lines[0] if header_lines else "รายงานทอง XAU/USD")[:400]
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "to": LINE_USER_ID,
            "messages": [{"type": "flex", "altText": alt_text, "contents": bubble}],
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"LINE push failed ({resp.status_code}): {resp.text}")


def main():
    missing = [
        name
        for name, val in [
            ("TWELVE_DATA_API_KEY", TWELVE_DATA_API_KEY),
            ("GEMINI_API_KEY", GEMINI_API_KEY),
            ("LINE_CHANNEL_ACCESS_TOKEN", LINE_CHANNEL_ACCESS_TOKEN),
            ("LINE_USER_ID", LINE_USER_ID),
        ]
        if not val
    ]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("See .env.example and README.md for setup instructions.", file=sys.stderr)
        sys.exit(1)

    print(f"[{datetime.now()}] Fetching XAU/USD data...")
    market_blocks = {}
    for tf in TIMEFRAMES:
        candles = fetch_candles(tf["interval"], tf["outputsize"])
        market_blocks[tf["label"]] = candles_to_compact_text(candles)

    print("Fetching live spot price...")
    live_price = fetch_live_price()

    print("Building prompt and calling Gemini...")
    prompt = build_prompt(market_blocks, live_price)
    report = call_gemini(prompt)

    header_lines = [f"📊 รายงานทอง XAU/USD - {datetime.now().strftime('%d/%m/%Y %H:%M')}"]
    if live_price and live_price.get("price"):
        header_lines.append(f"💰 ราคาสดตอนนี้: {live_price['price']} USD")

    print("Sending to LINE...")
    send_to_line(header_lines, report)
    print("Done.")


if __name__ == "__main__":
    main()
