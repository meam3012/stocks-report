"""Tunable parameters for the daily portfolio report.

Everything here was previously a magic number scattered through
generate_report.py and send_report.py — in several cases the *same* concept
with *different* values per output channel. Change a number here and every
channel follows.

Edit freely; nothing in this file requires understanding the rest of the code.
"""

# ─── Micho method: the MA150 bands ────────────────────────────────────────────
# The moving-average window, in trading days. Positions with a shorter price
# history use whatever they have and are flagged with * in the report.
MA_WINDOW = 150

# Distance from the MA that defines each band, in percent.
BAND_BULLISH = 10     # >= +10%  → BULLISH 🟢
BAND_NEUTRAL = 0      #   0..10  → NEUTRAL 🟡
BAND_WARNING = -10    # -10..0   → WATCH   🟠
#                      < -10%    → BEARISH 🔴

# ─── Alerts ───────────────────────────────────────────────────────────────────
# A position below its MA150 only raises a high alert once it is this large a
# share of the portfolio — small positions would otherwise dominate the box.
ALERT_WEIGHT_PCT = 5.0

# Single-day move that counts as "sharp". The report used 5 and WhatsApp used 7
# for this same idea; they are one number now.
ALERT_DAY_MOVE_PCT = 5.0

# How far above the MA counts as notable strength.
ALERT_STRONG_BULL_PCT = 20.0

# ─── RSI ──────────────────────────────────────────────────────────────────────
RSI_PERIOD     = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD   = 30

# ─── P/E bands (fundamental leg) ──────────────────────────────────────────────
# Only meaningful for profitable single stocks; ETFs and loss-making companies
# have no trailing P/E and are reported as "טכני בלבד" rather than guessed at.
PE_CHEAP = 20
PE_FAIR  = 35

# ─── News ─────────────────────────────────────────────────────────────────────
NEWS_WINDOW_HOURS = 48
NEWS_FETCH_COUNT  = 6    # asked of Yahoo
NEWS_SHOW_COUNT   = 4    # rendered per stock

# ─── Lookback windows, in trading days ────────────────────────────────────────
WEEK_DAYS    = 6
MONTH_DAYS   = 22
CHART_DAYS   = 90    # performance chart length
EXTREME_DAYS = 20    # support/resistance and average-volume window

# ─── History ──────────────────────────────────────────────────────────────────
HISTORY_KEEP = 250          # daily records retained in history.json
HISTORY_MIN_FOR_REAL_CURVE = 30   # below this the perf curve falls back to a
                                  # backcast and is labelled as synthetic

# ─── FX ───────────────────────────────────────────────────────────────────────
# Used only if the live USD/ILS fetch fails. The report flags when it is in use;
# a stale rate here silently misprices every dollar position.
FX_FALLBACK = 3.05

# ─── Delivery ─────────────────────────────────────────────────────────────────
# Publish the report to GitHub Pages and email a link to it.
#
# IMPORTANT: a GitHub Pages site is public even when its repository is private
# — access control for Pages exists only on Enterprise plans. So publishing
# means the holdings, daily values and cost basis are readable by anyone with
# the URL. Set this False to keep everything private: the report and the
# standalone terminal are then attached to the email instead, and the repo is
# still committed to daily so history.json keeps accumulating.
PUBLISH_TO_PAGES = False

GITHUB_PAGES_BASE = "https://meam3012.github.io/stocks-report"
SEND_TO_EMAIL     = "meam3012@gmail.com"
GMAIL_USER        = "meam3012@gmail.com"
WHATSAPP_URL      = "http://localhost:8080/api/send"
WHATSAPP_TO       = "972506319165"
