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
import time
import argparse
import subprocess
import requests
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
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

# ─── Publishing to GitHub Pages ──────────────────────────────────────────────

GITHUB_PAGES_BASE = "https://meam3012.github.io/stocks-report"
REPO_DIR = Path(__file__).parent


def _git(*args, check=True):
    return subprocess.run(["git", "-C", str(REPO_DIR), *args],
                          capture_output=True, text=True, timeout=120, check=check)


def publish_report(html_path: str) -> bool:
    """Commit + push the report so its GitHub Pages URL actually resolves.

    Without this the email links to a file that only exists on this machine.
    Returns True only once the URL is confirmed live.
    """
    name = Path(html_path).name
    data_path = REPO_DIR / "data.json"
    try:
        # data.json is regenerated every run and also committed by the Action, so a
        # plain rebase conflicts daily. Hold ours aside, sync, then put ours back.
        fresh = data_path.read_bytes() if data_path.exists() else None
        _git("checkout", "--", "data.json", check=False)

        # Local clone drifts behind the GitHub Action's daily commits — rebase first.
        _git("pull", "--rebase", "--autostash", "origin", "main")

        if fresh is not None:
            data_path.write_bytes(fresh)
        _git("add", "data.json", "index.html", name)
        staged = _git("diff", "--staged", "--quiet", check=False)
        if staged.returncode != 0:          # non-zero == there are staged changes
            _git("commit", "-m", f"data: daily update {date.today():%Y-%m-%d}")
        _git("push", "origin", "main")
    except subprocess.CalledProcessError as e:
        print(f"❌ פרסום ל-GitHub נכשל: {(e.stderr or e.stdout or '').strip()[:200]}")
        return False
    except Exception as e:
        print(f"❌ פרסום ל-GitHub נכשל: {e}")
        return False

    # Pages needs a moment to rebuild — confirm before we promise the link works.
    url = f"{GITHUB_PAGES_BASE}/{name}"
    for attempt in range(12):
        try:
            if requests.head(url, timeout=10).status_code == 200:
                print(f"✅ פורסם ל-GitHub Pages ({attempt * 10}s)")
                return True
        except requests.RequestException:
            pass
        time.sleep(10)

    print("⚠️  הדוח נדחף אך ה-URL עדיין לא חי — המייל יישלח עם הדוח כקובץ מצורף")
    return False


# ─── Gmail sender ─────────────────────────────────────────────────────────────

def send_email(html_path: str, subject: str, total_val: float, day_pct: float,
               published: bool = True, warnings: list | None = None,
               pnl: float | None = None, pnl_pct: float | None = None):
    """Send a short link-email pointing to the GitHub Pages hosted report."""
    if not GMAIL_PASSWORD:
        print("❌ GMAIL_APP_PASSWORD לא מוגדר — לא ניתן לשלוח מייל")
        return False

    warnings = warnings or []
    report_filename = Path(html_path).name
    report_url = f"{GITHUB_PAGES_BASE}/{report_filename}"

    arrow   = "▲" if day_pct >= 0 else "▼"
    color   = "#3fb950" if day_pct >= 0 else "#f85149"
    sign    = "+" if day_pct >= 0 else ""
    val_fmt = f"₪{total_val:,.0f}"

    # A number computed from a partial portfolio must never look clean.
    warn_html = ""
    if warnings:
        items = "".join(f"<li style='margin:2px 0;'>{w}</li>" for w in warnings)
        warn_html = f"""
        <tr>
          <td style="padding:16px 32px 0;">
            <div style="background:#fff8c5;border:1px solid #d4a72c;border-radius:8px;padding:12px 16px;">
              <p style="margin:0 0 6px;font-size:13px;font-weight:700;color:#7d4e00;">⚠️ שימו לב</p>
              <ul style="margin:0;padding-right:18px;font-size:12px;color:#7d4e00;line-height:1.6;">{items}</ul>
            </div>
          </td>
        </tr>"""

    # Total return sits under the day move — the day move alone says nothing
    # about whether the position is actually in profit.
    pnl_html = ""
    if pnl is not None:
        pcol = "#3fb950" if pnl >= 0 else "#f85149"
        parr = "▲" if pnl >= 0 else "▼"
        pnl_html = f"""
            <p style="margin:18px 0 0;padding-top:14px;border-top:1px solid #d0d7de;
                      text-align:center;font-size:14px;color:#57606a;">
              רווח/הפסד כולל:
              <span style="color:{pcol};font-weight:800;direction:ltr;display:inline-block;">
                {parr} ₪{abs(pnl):,.0f} ({pnl_pct:+.1f}%)
              </span>
            </p>"""

    if published:
        cta_html = f"""
            <a href="{report_url}"
               style="display:inline-block;background:#1f6feb;color:#ffffff;font-size:15px;font-weight:700;
                      text-decoration:none;padding:14px 36px;border-radius:8px;letter-spacing:0.3px;">
              📈 פתח דוח מלא
            </a>
            <p style="margin:12px 0 0;">
              <a href="{GITHUB_PAGES_BASE}/Portfolio%20Terminal.html"
                 style="display:inline-block;border:1px solid #d0d7de;color:#24292f;font-size:14px;
                        font-weight:600;text-decoration:none;padding:11px 28px;border-radius:8px;">
                🖥️ טרמינל אינטראקטיבי
              </a>
            </p>
            <p style="margin:16px 0 0;font-size:11px;color:#8c959f;">
              או העתק: <a href="{report_url}" style="color:#1f6feb;">{report_url}</a>
            </p>"""
    else:
        cta_html = """
            <div style="background:#ddf4ff;border:1px solid #54aeff;border-radius:8px;padding:14px 16px;">
              <p style="margin:0;font-size:13px;color:#0a3069;">
                📎 הדוח המלא מצורף כקובץ למייל הזה (הפרסום המקוון לא הושלם).
              </p>
            </div>"""

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
{warn_html}
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
{pnl_html}
          </td>
        </tr>

        <!-- CTA Button -->
        <tr>
          <td style="padding:0 32px 32px;text-align:center;">
{cta_html}
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

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = f"📊 דוח תיק <{GMAIL_USER}>"
    msg["To"]      = SEND_TO_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # If the hosted link isn't live, the report itself rides along.
    if not published:
        try:
            part = MIMEApplication(Path(html_path).read_bytes(), _subtype="octet-stream")
            part.add_header("Content-Disposition", "attachment", filename=report_filename)
            msg.attach(part)
        except Exception as e:
            print(f"⚠️  צירוף הדוח נכשל: {e}")

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

    # Group by signal. pct_ma150 can legitimately be None (signal() handles that
    # case explicitly) — comparing None to an int raises, so coerce like the HTML does.
    def ma_of(r):
        return r.get("pct_ma150") or 0

    bullish = [r for r in rows if ma_of(r) >= 10]
    neutral = [r for r in rows if 0 <= ma_of(r) < 10]
    watch   = [r for r in rows if -10 <= ma_of(r) < 0]
    bearish = [r for r in rows if ma_of(r) < -10]

    def row_line(r):
        t = r["ticker"].replace(".TA", "")
        if r["currency"] == "USD":
            p = f"${r['last_close']:.2f}"
        else:
            p = f"₪{r['last_close']/100:.2f}"
        ma = ma_of(r)
        sign_ma = "+" if ma >= 0 else ""
        return f"  {t:<6} {p:<8} {sign_ma}{ma:.1f}%"

    sp = next((i for i in indices if "S&P" in i["name"]), None)
    ta = next((i for i in indices if "TA"  in i["name"]), None)

    sp_str = f"{sp['value']:,.0f} ({'+' if sp['day_pct']>=0 else ''}{sp['day_pct']:.1f}%)" if sp and sp["value"] else "—"
    ta_str = f"{ta['value']:,.0f} ({'+' if ta['day_pct']>=0 else ''}{ta['day_pct']:.1f}%)" if ta and ta["value"] else "—"

    # Alerts
    alerts = []
    for r in bearish:
        pct_port = (r.get("val_ils") or 0) / total_val * 100 if total_val else 0
        if pct_port >= 5:
            t = r["ticker"].replace(".TA", "")
            # "מתחת" already carries the direction — abs() avoids rendering "ב--15.0%".
            alerts.append(f"🔴 {t} — מתחת MA150 ב-{abs(ma_of(r)):.1f}% ({pct_port:.1f}% מהתיק)")
    for r in rows:
        day = r.get("day_pct") or 0
        if abs(day) >= 7:
            t = r["ticker"].replace(".TA", "")
            sign_d = "+" if day >= 0 else ""
            alerts.append(f"🟠 {t} — שינוי חד {sign_d}{day:.1f}% ביום")

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
        # The bridge (whatsapp-mcp) expects "recipient" — "phone" returns 400.
        payload = {"recipient": WHATSAPP_TO, "message": message}
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

def parse_args():
    p = argparse.ArgumentParser(description="Daily portfolio report — generate, publish, send")
    p.add_argument("--no-email",     action="store_true", help="skip the email")
    p.add_argument("--no-whatsapp",  action="store_true", help="skip WhatsApp (bridge is local-only)")
    p.add_argument("--no-publish",   action="store_true", help="skip commit/push to GitHub Pages")
    p.add_argument("--whatsapp-only", action="store_true",
                   help="shorthand for --no-email --no-publish (local run; the Action owns the email)")
    a = p.parse_args()
    if a.whatsapp_only:
        a.no_email = a.no_publish = True
    return a


def main():
    args = parse_args()

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
    failed    = summary.get("failed", [])
    short_ma  = summary.get("short_ma", [])

    # Anything that makes the headline numbers less trustworthy goes in the email.
    warnings = []
    if failed:
        warnings.append(
            f"<b>{len(failed)} מתוך {summary.get('expected', '?')} מניות לא נמשכו "
            f"({', '.join(failed)})</b> — שווי התיק והשינוי היומי מחושבים על תיק חלקי."
        )
    if short_ma:
        warnings.append(
            f"היסטוריה קצרה מ-150 ימי מסחר ב-{', '.join(short_ma)} — "
            f"סיגנל ה-MA150 שלהן מחושב על חלון קצר יותר."
        )

    # Need indices for WhatsApp — re-fetch quickly
    from generate_report import fetch_index
    indices = [fetch_index("^GSPC", "S&P 500"), fetch_index("^TA125.TA", "TA-125")]
    time.sleep(0.2)

    # 2. Publish so the emailed link actually resolves
    published = False
    if args.no_publish:
        print("\n⏭️  מדלג על פרסום (--no-publish)")
    else:
        print("\n🚀 מפרסם ל-GitHub Pages...")
        published = publish_report(html_path)

    # 3. Build subject
    arrow   = "▲" if day_pct >= 0 else "▼"
    sign    = "+" if day_pct >= 0 else ""
    today   = date.today().strftime("%d/%m/%Y")
    prefix  = "⚠️ " if failed else "📊 "
    subject = f"{prefix}דוח תיק {today} | ₪{total_val:,.0f} | {arrow}{sign}{day_pct:.1f}%"
    if failed:
        subject += f" | חסרות {len(failed)} מניות"

    # 4. Send email
    email_ok = True
    if args.no_email:
        print("\n⏭️  מדלג על מייל (--no-email)")
    else:
        print("\n📧 שולח מייל...")
        email_ok = send_email(html_path, subject, total_val, day_pct,
                              published=published, warnings=warnings,
                              pnl=summary.get("total_pnl"),
                              pnl_pct=summary.get("total_pnl_pct"))

    # 5. Send WhatsApp
    if args.no_whatsapp:
        print("\n⏭️  מדלג על WhatsApp (--no-whatsapp)")
    else:
        print("\n📱 שולח WhatsApp...")
        wa_msg = build_whatsapp_message(rows, indices, total_val, day_pct, day_ils, usd_ils)
        send_whatsapp(wa_msg)

    print(f"\n{'='*50}")
    print(f"✅ סיים | תיק: ₪{total_val:,.0f} | {sign}{day_pct:.1f}%")
    if failed:
        print(f"⚠️  תיק חלקי — חסרות: {', '.join(failed)}")
    print(f"{'='*50}\n")

    # Exit non-zero so a silent failure can't look like success.
    if failed or not email_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
