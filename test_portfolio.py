#!/usr/bin/env python3
"""Tests for the trade-log derivation.

This is the arithmetic behind every P&L number in the report, and it is the one
place where a silent error would be both plausible and invisible — a wrong
average cost still renders as a confident percentage.

    python3 test_portfolio.py
"""

import json
import os
import sys
import tempfile

from portfolio import load_portfolio


def derive(trades, meta=None):
    doc = {"meta": meta or {"XYZ": {"name": "Test", "currency": "USD"}}, "trades": trades}
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    try:
        return load_portfolio(path)
    finally:
        os.unlink(path)


def t(date, side, qty, price, ticker="XYZ", **kw):
    return {"date": date, "ticker": ticker, "side": side, "qty": qty, "price": price, **kw}


CASES = [
    ("single buy",
     [t("2026-01-01", "buy", 10, 100)], 10, 100),

    ("two buys average by weight",
     [t("2026-01-01", "buy", 10, 100), t("2026-02-01", "buy", 10, 200)], 20, 150),

    ("uneven weights",
     [t("2026-01-01", "buy", 90, 10), t("2026-02-01", "buy", 10, 110)], 100, 20),

    # Realised gains are not cost basis: selling must not move the average.
    ("partial sell leaves average untouched",
     [t("2026-01-01", "buy", 10, 100), t("2026-02-01", "sell", 4, 300)], 6, 100),

    ("full exit drops the holding",
     [t("2026-01-01", "buy", 10, 100), t("2026-02-01", "sell", 10, 300)], 0, 0),

    ("re-entry starts a fresh average",
     [t("2026-01-01", "buy", 10, 100), t("2026-02-01", "sell", 10, 300),
      t("2026-03-01", "buy", 5, 50)], 5, 50),

    # Trades are applied in date order regardless of file order, or a sell could
    # be processed before the buy that funds it.
    ("out-of-order file is sorted",
     [t("2026-02-01", "sell", 4, 300), t("2026-01-01", "buy", 10, 100)], 6, 100),

    ("same-day ordering uses seq",
     [t("2026-01-01", "buy", 10, 100, seq=0), t("2026-01-01", "sell", 10, 150, seq=1)], 0, 0),

    ("oversell clamps rather than going negative",
     [t("2026-01-01", "buy", 5, 100), t("2026-02-01", "sell", 999, 100)], 0, 0),

    ("fractional shares survive rounding",
     [t("2026-01-01", "buy", 0.49, 24.80)], 0.49, 24.80),
]


def main():
    failures = 0
    for name, trades, want_qty, want_avg in CASES:
        got = derive(trades)
        if want_qty == 0:
            ok = not got
            detail = "no holding" if ok else f"got {got}"
        else:
            p = got[0] if got else None
            ok = (p is not None
                  and abs(p["shares"] - want_qty) < 1e-6
                  and abs(p["avg"] - want_avg) < 1e-4)
            detail = f"qty={p['shares']:g} avg={p['avg']:.4f}" if p else "no holding"
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<44} {detail}")

    # A malformed side must be loud, not silently skipped.
    try:
        derive([t("2026-01-01", "short", 10, 100)])
        print(f"  FAIL  {'invalid side raises':<44} no exception")
        failures += 1
    except ValueError:
        print(f"  PASS  {'invalid side raises':<44} ValueError")

    # The real file must stay parseable and non-empty.
    real = load_portfolio()
    ok = len(real) > 0 and all(p["shares"] > 0 and p["avg"] > 0 for p in real)
    failures += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {'trades.json derives a live portfolio':<44} {len(real)} holdings")

    print()
    print("all passed" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
