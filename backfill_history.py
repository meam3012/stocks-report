#!/usr/bin/env python3
"""One-off: rebuild history.json from the data.json committed each day since May.

Without this, MA150-crossing events and streaks stay empty until enough new runs
accumulate. Every daily commit already carries the numbers we need, so ~3 months
of real history is recoverable rather than waited for.

Safe to re-run: it rebuilds from git and merges with whatever history.json holds,
preferring live records over reconstructed ones for the same date.

    python3 backfill_history.py [--dry-run]
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent
OUT = REPO / "history.json"

# data.json stores display units (TASE already divided by 100) and no explicit
# pct_ma150, so it is derived from price vs ma150 — both in the same units.
HEB_MONTHS = {
    "ינואר": 1, "פברואר": 2, "מרץ": 3, "אפריל": 4, "מאי": 5, "יוני": 6,
    "יולי": 7, "אוגוסט": 8, "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
}


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=True).stdout


def band_of(pct):
    if pct is None:
        return "neutral"
    if pct >= 10:
        return "bullish"
    if pct >= 0:
        return "neutral"
    if pct >= -10:
        return "warning"
    return "bearish"


def parse_as_of(as_of):
    """'3 במאי 2026, 22:35 IDT' -> '2026-05-03'. Returns None if unparseable."""
    m = re.match(r"\s*(\d{1,2})\s+ב(\S+)\s+(\d{4})", as_of or "")
    if not m:
        return None
    day, mon_he, year = m.groups()
    mon = HEB_MONTHS.get(mon_he)
    return f"{year}-{mon:02d}-{int(day):02d}" if mon else None


def record_from_data(data, commit_date):
    positions = {}
    total = 0.0
    for p in data.get("positions", []):
        price, ma150, qty = p.get("price"), p.get("ma150"), p.get("qty")
        pct = (price / ma150 - 1) * 100 if price and ma150 else None
        # Reconstruct the ILS value the same way the report does.
        val = p.get("valueILS")
        if val is None and price and qty is not None:
            fx = data.get("fxRate") or 1
            val = price * qty * (1 if p.get("market") == "IL" else fx)
        total += val or 0
        # history.json keys positions by the PORTFOLIO ticker, which carries .TA
        tic = f"{p['sym']}.TA" if p.get("market") == "IL" else p["sym"]
        positions[tic] = {
            "qty": qty,
            "price": round(price, 4) if price is not None else None,
            "pct_ma150": round(pct, 2) if pct is not None else None,
            "band": band_of(pct),
            "rsi": p.get("rsi"),
            "val_ils": round(val, 2) if val is not None else None,
        }

    totals = data.get("totals") or {}
    return {
        "date": parse_as_of(data.get("asOf")) or commit_date,
        "total_val": round(totals.get("valueILS") or total, 2),
        "day_pct": totals.get("dayPctILS", 0),
        "fx": data.get("fxRate"),
        "positions": positions,
        "reconstructed": True,
    }


def main():
    dry = "--dry-run" in sys.argv

    shas = git("log", "--format=%H %ad", "--date=short", "--", "data.json").split("\n")
    shas = [s.split() for s in shas if s.strip()]
    print(f"נמצאו {len(shas)} קומיטים של data.json")

    rebuilt = {}
    for sha, cdate in shas:
        try:
            data = json.loads(git("show", f"{sha}:data.json"))
            rec = record_from_data(data, cdate)
            # Earlier commits win only if we haven't seen that date yet; git log is
            # newest-first, so the first record for a date is the final one that day.
            rebuilt.setdefault(rec["date"], rec)
        except Exception as e:
            print(f"  ⚠️  דילוג על {sha[:7]} ({cdate}): {type(e).__name__}")

    # day_pct is unreliable in old files (no totals key) — recompute from the series.
    ordered = [rebuilt[d] for d in sorted(rebuilt)]
    for i, rec in enumerate(ordered):
        if i == 0:
            continue
        prev = ordered[i - 1]["total_val"]
        if prev:
            rec["day_pct"] = round((rec["total_val"] - prev) / prev * 100, 2)

    # Live records already written by the report take precedence.
    existing = {}
    if OUT.exists():
        existing = {h["date"]: h for h in json.loads(OUT.read_text(encoding="utf-8"))}
    merged = {**rebuilt, **{d: h for d, h in existing.items() if not h.get("reconstructed")}}
    final = [merged[d] for d in sorted(merged)][-250:]

    print(f"נבנו {len(rebuilt)} ימים | קיימים חיים: {len(existing)} | סה\"כ: {len(final)}")
    if final:
        print(f"טווח: {final[0]['date']} → {final[-1]['date']}")

    if dry:
        print("--dry-run: לא נכתב כלום")
        return
    OUT.write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ נכתב {OUT}")


if __name__ == "__main__":
    main()
