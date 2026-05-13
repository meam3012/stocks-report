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

GITHUB_PAGES_BASE = "https://meam3012.github.io/stocks-report"

def send_email(html_path: str, subject: str, total_val: float, day_pct: float):
    """Send a short link-email pointing to the GitHub Pages hosted report."""
    if not GMAIL_PASSWORD:
        print("⚠️  GMAIL_APP_PASSWORD not set — skipping email")
        return False

    report_filename = Path(html_path).name
    report_url = f"{GITHUB_PAGES_BASE}/{report_filename}"

    arrow   = "▲" if day_pct >= 0 else "▼"
    color   = "#3fb950" if day_pct >= 0 else "#f85149"
    sign    = "+" if day_pct >= 0 else ""
    val_fmt = f"₪{total_val:,.0f}"

    html_body = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f6f8fa;font-family:Arial,sans-serif;direction:rtl;text-align:right;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f8fa;padding:32px 0;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;border:1px solid #d0d7de;overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#1f2937,#111827);padding:28px 32px;">
            <p style="margin:0;font-size:20px;font-weight:800;color:#e6edf3;">📊 דוח תיק יומי — מאיר</p>
            <p style="margin:6px 0 0;font-size:13px;color:#8b949e;">שיטת מיכו | MA150 | {date.today().strftime('%d/%m/%Y')}</p>
          </td>
        </tr>

        <!-- Key numbers -->
        <tr>
          <td style="padding:28px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="text-align:center;padding:0 8px;">
                  <p style="margin:0;font-size:12px;color:#57606a;text-transform:uppercase;letter-spacing:0.5px;">שווי תיק</p>
                  <p style="margin:6px 0 0;font-size:28px;font-weight:800;color:#1f2328;direction:ltr;">{val_fmt}</p>
                </td>
                <td style="text-align:center;padding:0 8px;border-right:1px solid #d0d7de;">
                  <p style="margin:0;font-size:12px;color:#57606a;text-transform:uppercase;letter-spacing:0.5px;">שינוי יומי</p>
                  <p style="margin:6px 0 0;font-size:28px;font-weight:800;color:{color};direction:ltr;">{arrow} {sign}{day_pct:.1f}%</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- CTA Button -->
        <tr>
          <td style="padding:0 32px 32px;text-align:center;">
            <a href="{report_url}"
               style="display:inline-block;background:#1f6feb;color:#ffffff;font-size:15px;font-weight:700;
                      text-decoration:none;padding:14px 36px;border-radius:8px;letter-spacing:0.3px;">
              📈 פתח דוח מלא
            </a>
            <p style="margin:16px 0 0;font-size:11px;color:#8c959f;">
              או העתק: <a href="{report_url}" style="color:#1f6feb;">{report_url}</a>
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f6f8fa;padding:16px 32px;border-top:1px solid #d0d7de;text-align:center;">
            <p style="margin:0;font-size:11px;color:#8c959f;">נוצר אוטומטית | Yahoo Finance | שיטת מיכו</p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"📊 דוח תיק <{GMAIL_USER}>"
    msg["To"]      = SEND_TO_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, SEND_TO_EMAIL, msg.as_bytes())
        print(f"✅ מייל נשלח ל-{SEND_TO_EMAIL} → {report_url}")
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
