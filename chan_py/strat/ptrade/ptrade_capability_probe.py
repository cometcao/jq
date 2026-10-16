# -*- coding: utf-8 -*-
"""
ptrade_capability_probe.py - PTrade sandbox capability probe (paste into the editor)

The trading sandbox forbids os/sys, so the question "what IS allowed" is best answered by
the platform itself. This file imports NOTHING at module level (a banned top-level import
would be rejected before anything runs) and probes with __import__ + builtins instead.

How to use:
  1. Paste this whole file into the PTrade strategy editor (backtest or trading).
  2. Run it once.
  3. Read the log block:
         ============================================================
         PTrade capability probe
         ...
     It reports: which modules import, whether open() works in the research dir, whether a
     SUBDIR can be written (that tells us whether os.makedirs has a replacement), which
     platform functions exist, and the portfolio attributes.

Nothing is traded; it only writes probe_read.txt (and maybe sub/probe.txt) in the research
dir - delete them afterwards.
"""


def _join(base, name):
    """os.path.join replacement (open() accepts '/' everywhere)."""
    if not base:
        return name
    return base.replace("\\", "/").rstrip("/") + "/" + name.lstrip("/")


def _try_import(name):
    try:
        __import__(name)
        return "OK"
    except Exception as e:
        return "FAIL: %s: %s" % (type(e).__name__, e)


def initialize(context):
    log.info("=" * 60)
    log.info("PTrade capability probe")

    for name in ("json", "datetime", "math", "time", "collections", "re",
                 "os", "sys", "traceback", "glob", "pathlib", "numpy", "pandas"):
        log.info("import %-12s -> %s" % (name, _try_import(name)))

    base = "?"
    try:
        base = get_research_path()
        log.info("get_research_path() -> %r" % (base,))
    except Exception as e:
        log.info("get_research_path() FAILED: %s: %s" % (type(e).__name__, e))

    p = _join(base, "probe_read.txt")
    try:
        f = open(p, "w")
        try:
            f.write("hello")
        finally:
            f.close()
        f = open(p)
        try:
            s = f.read()
        finally:
            f.close()
        log.info("open() write+read in research dir -> OK (%r)" % (s,))
    except Exception as e:
        log.info("open() in research dir -> FAIL: %s: %s" % (type(e).__name__, e))

    try:
        f = open(_join(base, "probe_sub/probe.txt"), "w")
        try:
            f.write("x")
        finally:
            f.close()
        log.info("write into a SUBDIR -> OK (so a subdir already exists or is auto-created)")
    except Exception as e:
        log.info("write into a SUBDIR -> FAIL: %s (no mkdir available -> keep files FLAT)"
                 % type(e).__name__)

    for fn in ("order", "order_target", "order_value", "order_percent",
               "get_snapshot", "get_stock_status", "get_stock_info", "get_research_path",
               "run_daily", "run_interval", "set_universe", "get_positions", "get_position",
               "get_all_securities", "get_trading_day", "get_trade_days", "log"):
        log.info("api %-20s -> %s" % (fn, "present" if fn in globals() else "MISSING"))

    try:
        pf = context.portfolio
        attrs = sorted([a for a in dir(pf) if not a.startswith("_")])
        log.info("portfolio attrs: %s" % ",".join(attrs))
        for a in ("portfolio_value", "total_value", "total_asset", "cash",
                  "positions", "position"):
            v = getattr(pf, a, None)
            log.info("portfolio.%-16s -> %s" % (a, "MISSING" if v is None else type(v).__name__))
    except Exception as e:
        log.info("context.portfolio FAILED: %s: %s" % (type(e).__name__, e))

    try:
        pos = None
        for a in ("positions", "position"):
            pos = getattr(context.portfolio, a, None)
            if pos is not None:
                break
        if pos:
            k = list(pos.keys())[0]
            one = pos[k]
            log.info("position attrs: %s"
                     % ",".join(sorted([x for x in dir(one) if not x.startswith("_")])))
        else:
            log.info("no position to inspect (empty account)")
    except Exception as e:
        log.info("position inspection FAILED: %s: %s" % (type(e).__name__, e))

    log.info("=" * 60)


def handle_data(context, data):
    pass
