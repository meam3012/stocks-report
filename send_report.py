#!/usr/bin/env python3
"""
Daily Portfolio Report — Sender
Generates HTML report and sends via Gmail (SMTP) + WhatsApp (bridge)
Run this script every weekday morning via cron or launchd.
"""

import smtplib
import json
import sys
import os
import requests
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, datetime

# ─── Configuration ────────────────────────────────────────────────────────────
# Gmail: use an App Password (not your main password).
# Generate at: https://myaccount.google.com/apppasswords
GMAIL_USER     = "meam3012@gmail.com"
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")   # set in env or fill here
SEND_TO_EMAIL  = "meam3012@gmail.com"

# WhatsApp bridge (whatsapp-web.js or similar running on localhost)
WHATSAPP_URL   = "http://localhost:8080/api/send"
WHATSAPP_TO    = "972506319165"   # Meir's number

# ─── Import report generator ─────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from generate_report import main as generate_report

# ─── Gmail sender ─────────────────────────────────────────────────────────────

def send_email(html_path: str, subject: str, total_val: float, day_pct: float):
    """Send HTML report via Gmail SMTP with App Password."""
    if not GMAIL_PASSWORD:
        print("⚠️  GMAIL_APP_PASSWORD not set — skipping email")
        return False

    html_content = Path(html_path).read_text(encoding="utf-8")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"📊 דוח תיק <{GMAIL_USER}>"
    msg["To"]      = SEND_TO_EMAIL

    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, SEND_TO_EMAIL, msg.as_bytes())
        print(f"✅ מייל נשלח ל-{SEND_TO_EMAIL}")
        return True
    except Exception as e:
        print(f"❌ שגיאת מייל: {e}")
        return False

# ─── WhatsApp sender ──────────────────────────────────────────────────────────

def build_whatsapp_message(rows: list, indices: list, total_val: float,
                           day_pct: float, day_ils: float, usd_ils: float) -> str:
    today = date.today()
    date_str = today.strftime("%d/%m/%Y")

    arrow = "📈" if day_pct >= 0 else "📉"
    sign  = "+" if day_pct >= 0 else ""

    # Group by signal
    bullish = [r for r in rows if r.get("pct_ma150", 0) >= 10]
    neutral = [r for r in rows if 0 <= r.get("pct_ma150", 0) < 10]
    watch   = [r for r in rows if -10 <= r.get("pct_ma150", 0) < 0]
    bearish = [r for r in rows if r.get("pct_ma150", 0) < -10]

    def row_line(r):
        t = r["ticker"].replace(".TA", "")
        if r["currency"] == "USD":
            p = f"${r['last_close']:.2f}"
        else:
            p = f"₪{r['last_close']/100:.2f}"
        ma = r.get("pct_ma150", 0)
        sign_ma = "+" if ma >= 0 else ""
        return f"  {t:<6} {p:<8} {sign_ma}{ma:.1f}%"

    sp = next((i for i in indices if "S&P" in i["name"]), None)
    ta = next((i for i in indices if "TA"  in i["name"]), None)

    sp_str = f"{sp['value']:,.0f} ({'+' if sp['day_pct']>=0 else ''}{sp['day_pct']:.1f}%)" if sp and sp["value"] else "—"
    ta_str = f"{ta['value']:,.0f} ({'+' if ta['day_pct']>=0 else ''}{ta['day_pct']:.1f}%)" if ta and ta["value"] else "—"

    # Alerts
    alerts = []
    for r in bearish:
        pct_port = r.get("val_ils", 0) / total_val * 100
        if pct_port >= 5:
            t = r["ticker"].replace(".TA", "")
            alerts.append(f"🔴 {t} — מתחת MA150 ב-{r['pct_ma150']:.1f}% ({pct_port:.1f}% מהתיק)")
    for r in rows:
        if abs(r.get("day_pct", 0)) >= 7:
            t = r["ticker"].replace(".TA", "")
            sign_d = "+" if r["day_pct"] >= 0 else ""
            alerts.append(f"🟠 {t} — שינוי חד {sign_d}{r['day_pct']:.1f}% ביום")

    alerts_str = "\n".join(alerts) if alerts else "✅ אין התראות מיוחדות"

    msg = f"""📊 *דוח תיק יומי — מאיר*
📅 {date_str} | USD/ILS: {usd_ils:.2f}

━━━━━━━━━━━━━━━━━━
💰 *שווי תיק: ₪{total_val:,.0f}*
{arrow} שינוי יומי: *{sign}{day_pct:.1f}%* ({sign}{day_ils:,.0f}₪)
━━━━━━━━━━━━━━━━━━

🌍 *שווקים:*
• S&P 500:  {sp_str}
• TA-125:   {ta_str}

━━━━━━━━━━━━━━━━━━
📋 *סיגנלים — שיטת מיכו:*

🟢 *BULLISH ({sum(r['val_ils'] for r in bullish)/total_val*100:.0f}%):*
{chr(10).join(row_line(r) for r in bullish) or "  —"}

🟡 *NEUTRAL ({sum(r['val_ils'] for r in neutral)/total_val*100:.0f}%):*
{chr(10).join(row_line(r) for r in neutral) or "  —"}

🟠 *WATCH ({sum(r['val_ils'] for r in watch)/total_val*100:.0f}%):*
{chr(10).join(row_line(r) for r in watch) or "  —"}

🔴 *BEARISH ({sum(r['val_ils'] for r in bearish)/total_val*100:.0f}%):*
{chr(10).join(row_line(r) for r in bearish) or "  —"}

━━━━━━━━━━━━━━━━━━
⚡ *התראות:*
{alerts_str}

━━━━━━━━━━━━━━━━━━
_שיטת מיכו: מעל MA150 = בולישי | מתחת = סיגנל יציאה_"""

    return msg

def send_whatsapp(message: str) -> bool:
    """Send via local WhatsApp bridge (whatsapp-web.js)."""
    try:
        payload = {"phone": WHATSAPP_TO, "message": message}
        r = requests.post(WHATSAPP_URL, json=payload, timeout=10)
        if r.status_code == 200:
            print(f"✅ WhatsApp נשלח ל-{WHATSAPP_TO}")
            return True
        else:
            print(f"❌ WhatsApp שגיאה {r.status_code}: {r.text[:100]}")
            return False
    except requests.ConnectionError:
        print("⚠️  WhatsApp bridge לא פעיל (localhost:8080) — מדלג")
        return False
    except Exception as e:
        print(f"❌ WhatsApp שגיאה: {e}")
        return False

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*50}")
    print(f"📊 דוח תיק יומי — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}\n")

    # 1. Generate report
    html_path, summary = generate_report()

    total_val = summary["total_val"]
    day_pct   = summary["port_day_pct"]
    day_ils   = summary["port_day_ils"]
    usd_ils   = summary["usd_ils"]
    rows      = summary["rows"]

    # Need indices for WhatsApp — re-fetch quickly
    from generate_report import fetch_index
    import time
    indices = [fetch_index("^GSPC", "S&P 500"), fetch_index("^TA125.TA", "TA-125")]
    time.sleep(0.2)

    # 2. Build subject
    arrow   = "▲" if day_pct >= 0 else "▼"
    sign    = "+" if day_pct >= 0 else ""
    today   = date.today().strftime("%d/%m/%Y")
    subject = f"📊 דוח תיק {today} | ₪{total_val:,.0f} | {arrow}{sign}{day_pct:.1f}%"

    # 3. Send email
    print("\n📧 שולח מייל...")
    send_email(html_path, subject, total_val, day_pct)

    # 4. Send WhatsApp
    print("\n📱 שולח WhatsApp...")
    wa_msg = build_whatsapp_message(rows, indices, total_val, day_pct, day_ils, usd_ils)
    send_whatsapp(wa_msg)

    print(f"\n{'='*50}")
    print(f"✅ סיים | תיק: ₪{total_val:,.0f} | {sign}{day_pct:.1f}%")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()
