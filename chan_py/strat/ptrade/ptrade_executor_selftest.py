# -*- coding: utf-8 -*-
"""
ptrade_executor_selftest.py - local mock harness for ptrade_rebalance_executor.py

Runs the PTrade strategy on this machine with fake PTrade APIs, so the money math,
the diff logic, the deadband, the limit/halt filters, the dry-run path, the
idempotency and the missing/stale/liquidate target handling are all verified
BEFORE the file is uploaded to the broker's cloud.

    python ptrade_executor_selftest.py

No PTrade account, no network, no broker access is involved.
"""

import os
import sys
import json
import shutil
import tempfile
import datetime

import ptrade_rebalance_executor as S

SHIPPED_DRY_RUN = S.DRY_RUN      # captured before any test mutates it
STRAT = "low_valuation"
TARGET_FILE = S.TARGET_FILES[0]

# ----------------------------------------------------------------------------
# fake PTrade API surface
# ----------------------------------------------------------------------------
ORDERS = []
ORDER_MARKET_CALLS = []
REGISTERED = []
RESEARCH = None
QUOTES = {}      # ptrade-style code -> dict
HALTED = set()
ST_NAMES = set()


class FakeLog(object):
    def info(self, m):
        pass

    def warning(self, m):
        pass

    def error(self, m):
        pass


class Pos(object):
    def __init__(self, code, amount, enable, last, name=""):
        self.code = code
        self.amount = amount
        self.enable_amount = enable
        self.last_sale_price = last
        self.name = name


class Portfolio(object):
    def __init__(self, cash, total, positions):
        self.cash = cash
        self.portfolio_value = total
        self.positions = positions


class Context(object):
    def __init__(self, cash, total, positions):
        self.portfolio = Portfolio(cash, total, positions)


def fake_get_research_path():
    return RESEARCH


def fake_get_snapshot(code):
    if isinstance(code, (list, tuple)):
        code = code[0] if code else ""
    code = _alt_suffix(code)          # tolerate XSHG/XSHE/SS/SH/SZ spellings
    q = QUOTES.get(code)
    if not q:
        return {}
    return {
        "last_px": q.get("last", 0.0),
        "preclose_px": q.get("preclose", 0.0),   # 0.0 = limit price unavailable
        "bid_grp": {1: (q.get("last", 0.0) * 0.999, 1000, 3)},
        "offer_grp": {1: (q.get("last", 0.0) * 1.001, 1000, 3)},
    }


def _alt_suffix(code):
    """QUOTES is keyed <plain>.SS / <plain>.SZ; map any other dialect onto it."""
    code = str(code).upper()
    for a, b in ((".XSHG", ".SS"), (".SH", ".SS"), (".XSHE", ".SZ")):
        if code.endswith(a):
            return code[:-len(a)] + b
    return code


def _same_code(a, b):
    return _alt_suffix(a) == _alt_suffix(b)


def fake_get_stock_status(code, kind):
    """Real PTrade returns a DICT keyed by the security (verified against the production
    reference strategy: `st = get_stock_status(security,'ST'); if st[security]:`).
    Keep the fake in that shape - a truthiness test on the dict marks EVERYTHING halted."""
    if kind == "HALT":
        return {code: any(_same_code(code, c) for c in HALTED)}
    if kind == "ST":
        return {code: any(_same_code(code, c) for c in ST_NAMES)}
    return {code: False}


def fake_get_positions():
    return {}


def fake_order(code, amount, limit_price=None):
    ORDERS.append({"code": code, "amount": int(amount), "limit_price": limit_price})
    return "oid%d" % len(ORDERS)


def fake_order_market(code, amount=None, market_type=None, limit_price=None):
    """The API the proven production reference strategy actually calls."""
    ORDERS.append({"code": code, "amount": int(amount), "limit_price": limit_price})
    ORDER_MARKET_CALLS.append({"code": code, "amount": int(amount),
                               "market_type": market_type, "limit_price": limit_price})
    return "om%d" % len(ORDERS)


def fake_run_daily(context, func, when):
    REGISTERED.append(when)


def _install_fakes():
    S.log = FakeLog()
    S.get_research_path = fake_get_research_path
    S.get_snapshot = fake_get_snapshot
    S.get_stock_status = fake_get_stock_status
    S.get_positions = fake_get_positions
    S.order = fake_order
    S.order_market = fake_order_market
    S.run_daily = fake_run_daily


# ----------------------------------------------------------------------------
# scenario
# ----------------------------------------------------------------------------
POOL = ["605189.SH", "301167.SZ", "002758.SZ", "600697.SH", "600739.SH",
        "601318.SH", "600036.SH", "000002.SZ", "600030.SH", "000651.SZ",
        "600887.SH", "601166.SH", "600276.SH"]

P = {"605189": 17.85, "301167": 12.80, "002758": 8.20, "600697": 11.24,
     "600739": 10.19, "601318": 52.00, "600036": 38.50, "000002": 8.05,
     "600030": 21.30, "000651": 42.10, "600887": 28.40, "601166": 18.20,
     "600276": 45.60, "300750": 200.00}


def build_quotes():
    QUOTES.clear()
    for plain, px in P.items():
        mk = "SS" if plain[0] in "56" else "SZ"
        QUOTES[plain + "." + mk] = {"last": px, "preclose": px}
    # 002758 (Shenzhen) locked at limit up (+10%)
    up = round(P["002758"] * 1.1, 2)
    QUOTES["002758.SZ"]["last"] = up
    HALTED.clear()
    HALTED.add("600697.SS")


def build_context():
    positions = {
        "605189.SS": Pos("605189.SS", 3500, 3500, 17.85),   # in pool, within deadband
        "301167.SZ": Pos("301167.SZ", 1000, 1000, 12.80),   # in pool, under-weight
        "300750.SZ": Pos("300750.SZ", 200, 200, 200.00),    # out of pool -> sell all
    }
    return Context(cash=330000.0, total=520000.0, positions=positions)


def write_target(stocks=None, generated=None, liquidate=None, trading_times=None,
                 params=None, name=None, target_file=None):
    """Write one strategy's target file (defaults: today, order time = now, 1 strategy)."""
    if generated is None:
        generated = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if trading_times is None:
        trading_times = [datetime.datetime.now().strftime("%H:%M")]
    data = {"strategy": name or STRAT, "generated_at": generated,
            "trading_times": trading_times}
    for k, v in (params or {}).items():
        data[k] = v
    data["stocks"] = POOL if stocks is None else stocks
    if liquidate is not None:
        data["liquidate"] = liquidate
    with open(os.path.join(RESEARCH, target_file or TARGET_FILE), "w") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))


def state_file(strategy=None):
    """State/audit are FLAT in the research dir (the sandbox has no mkdir)."""
    return os.path.join(RESEARCH, S.STATE_PREFIX + (strategy or STRAT) + ".json")


def audit_file(strategy=None):
    return os.path.join(RESEARCH, S.AUDIT_PREFIX + (strategy or STRAT) + "_" +
                        S._date_str() + ".json")


def tracker_of(ctx, strategy=None, params=None):
    """A tracker that gives every broker position to this one strategy (ratio 1.0)."""
    strategy = strategy or STRAT
    broker = S._positions(ctx)
    return {strategy: dict((c, p["amount"]) for c, p in broker.items())}


def make_plan(ctx, stocks, params=None, strategy=None, tracker=None):
    """Single-strategy planning helper (the real code is per strategy + per slice)."""
    params = params or dict(S.DEFAULT_PARAMS)
    strategy = strategy or STRAT
    if tracker is None:
        tracker = tracker_of(ctx, strategy)
    view = S._strategy_view(ctx, params, tracker, strategy)
    return S._plan(view, stocks, params)


def run_job(ctx, tag, target_file=None):
    """Run one strategy's job for the given tag."""
    return S._run(ctx, tag, target_file or TARGET_FILE)


_HERE = os.path.dirname(os.path.abspath(__file__))
SELFTEST_DIR = os.path.join(_HERE, "_selftest", "executor")


def fresh_dir():
    """Fixture lives inside this project (_selftest/ is gitignored) so it works even
    when no system temp directory is usable, and so the artifacts stay inspectable."""
    if os.path.isdir(SELFTEST_DIR):
        shutil.rmtree(SELFTEST_DIR, ignore_errors=True)
    os.makedirs(SELFTEST_DIR)
    return SELFTEST_DIR


def check(label, cond, extra=""):
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", label, extra))
    if not cond:
        raise AssertionError(label)


# ----------------------------------------------------------------------------
# tests
# ----------------------------------------------------------------------------
def test_initialize_and_selfcheck():
    print("test_initialize_and_selfcheck")
    check("ships LIVE (DRY_RUN defaults to False)", SHIPPED_DRY_RUN is False,
          str(SHIPPED_DRY_RUN))
    REGISTERED[:] = []
    S.initialize(build_context())
    check("run_daily registered", len(REGISTERED) >= 1, str(REGISTERED))
    check("registered times are the file's order times",
          REGISTERED == [datetime.datetime.now().strftime("%H:%M")], str(REGISTERED))
    check("sh suffix detected as SS", S.CAPS.get("sh_suffix") == "SS", str(S.CAPS.get("sh_suffix")))
    check("selfcheck saw the target file", S.CAPS.get("exists_" + STRAT) is True,
          str(S.CAPS.get("exists_" + STRAT)))
    check("selfcheck read the portfolio", S.CAPS.get("total_value") == 520000.0,
          str(S.CAPS.get("total_value")))


def test_plan_math():
    print("test_plan_math")
    ctx = build_context()
    status, target = S._load_target(TARGET_FILE)
    check("target status ok", status == "ok", status)
    plan = make_plan(ctx, target["_stocks"])

    target_per = (520000.0 - 520000.0 * 0.0125) / 8.0
    check("target_per_stock", abs(plan["target_per"] - target_per) < 0.01,
          "%.2f vs %.2f" % (plan["target_per"], target_per))

    sells = dict((c, v) for c, v, _r in plan["sells"])
    check("out-of-pool name fully sold", sells.get("300750.SZ") == 200, str(sells))
    check("in-pool name inside deadband is untouched", "605189.SH" not in sells)
    check("only one sell expected", len(plan["sells"]) == 1, str(plan["sells"]))

    buys = dict((c, v) for c, v, _r in plan["buys"])
    check("no duplicate code in the buy list",
          len(set(c for c, _v, _r in plan["buys"])) == len(plan["buys"]),
          str(plan["buys"]))
    # fixture: 3 held / cash 330000 -> slots=5, cash_for_buy=323500, avg=64700 vs
    # target 64187.5 -> deviation 0.8% <= 20% -> the combination gate stays OFF, so the
    # in-pool names are NOT touched and only the 4 fillable empty slots are bought.
    check("gate stays off for a balanced book",
          any("rebalance gate" in n and "OFF" in n for n in plan["notes"]),
          str(plan["notes"]))
    check("exactly 4 buys expected (4 new slots, no top-up)",
          len(plan["buys"]) == 4, str(plan["buys"]))
    check("in-pool name untouched while the gate is off",
          "301167.SZ" not in buys, str(buys))
    check("limit-up candidate is skipped", "002758.SZ" not in buys)
    check("halted candidate is skipped", "600697.SH" not in buys)
    for c in ("600739.SH", "601318.SH", "600036.SH", "000002.SZ"):
        check("new slot filled: %s" % c, c in buys)
    check("no more than max_holdings names held after the run",
          len(set(["605189.SH", "301167.SZ"]) | set(buys.keys())) <= S.DEFAULT_PARAMS["max_holdings"],
          str(sorted(buys.keys())))
    for c, v in buys.items():
        check("lot rounding for %s" % c, v > 0 and v % S.LOT == 0, str(v))

    cost = 0.0
    for c, v, _r in plan["buys"]:
        snap = S._snap_one(S._pt_code(c))
        up, _dn = S._up_down(snap, c)
        px = S._buy_price(snap.get("last"), _ask_of(c), up)
        cost += v * px
    budget = 330000.0 + 200 * 200.0 - 520000.0 * 0.0125
    check("buys stay inside the cash budget", cost <= budget * 1.001,
          "%.0f <= %.0f" % (cost, budget))
    check("a clean plan raises no ERROR", plan["errors"] == [], str(plan["errors"]))


def _ask_of(code):
    q = S._snap_one(S._pt_code(code))
    return q.get("ask1") or q.get("last")


def _state_file():
    return state_file()


def _audit_file():
    return audit_file()


def test_dry_run_sends_nothing():
    print("test_dry_run_sends_nothing")
    ORDERS[:] = []
    S.DRY_RUN = True
    ctx = build_context()
    run_job(ctx, "20261016@0935")
    check("dry run placed no order", ORDERS == [], str(ORDERS))
    check("dry run still wrote an audit file", os.path.exists(_audit_file()), _audit_file())
    st = S._read_json(_state_file()) or {}
    check("state marked done", "20261016@0935" in (st.get("done") or []), str(st))


def test_execute_places_sells_then_buys():
    print("test_execute_places_sells_then_buys")
    ORDERS[:] = []
    S.DRY_RUN = False
    ctx = build_context()
    run_job(ctx, "20261016@0936")
    check("orders were placed", len(ORDERS) >= 2, str(len(ORDERS)))
    check("first order is the out-of-pool sell",
          ORDERS[0]["code"] == "300750.SZ" and ORDERS[0]["amount"] == -200,
          str(ORDERS[0]))
    check("sells come before buys",
          all(o["amount"] < 0 for o in ORDERS[:1]) and
          any(o["amount"] > 0 for o in ORDERS[1:]), str(ORDERS))
    for o in ORDERS:
        check("limit price attached to %s" % o["code"],
              o["limit_price"] and o["limit_price"] > 0, str(o))


def test_idempotent_per_time_tag():
    print("test_idempotent_per_time_tag")
    ORDERS[:] = []
    S.DRY_RUN = False
    ctx = build_context()
    run_job(ctx, "20261016@0936")          # same tag as the previous test
    check("re-running the same tag places nothing", ORDERS == [], str(ORDERS))


def _clear_state():
    p = _state_file()
    if os.path.exists(p):
        os.remove(p)


def test_missing_target_is_skipped():
    print("test_missing_target_is_skipped")
    os.remove(os.path.join(RESEARCH, TARGET_FILE))
    _clear_state()
    ORDERS[:] = []
    S.DRY_RUN = False
    ctx = build_context()
    status, _t = S._load_target(TARGET_FILE)
    check("missing status", status == "missing", status)
    run_job(ctx, "20261016@0937")
    check("missing target -> no order (MISSING_FILE_ACTION=skip)", ORDERS == [], str(ORDERS))


def test_old_target_is_flagged_stale():
    print("test_old_target_is_flagged_stale")
    old = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    write_target(generated=old)
    _clear_state()
    ctx = build_context()
    status, _t = S._load_target(TARGET_FILE)
    check("stale status", status == "stale", status)


def test_empty_pool_liquidates():
    print("test_empty_pool_liquidates")
    write_target(stocks=[])
    ctx = build_context()
    status, _t = S._load_target(TARGET_FILE)
    check("empty pool -> liquidate status", status == "liquidate", status)
    _clear_state()
    ORDERS[:] = []
    S.DRY_RUN = False
    run_job(ctx, "20261016@0938")
    check("liquidation sold every holding", len(ORDERS) == 3, str(ORDERS))
    check("liquidation placed no buy", all(o["amount"] < 0 for o in ORDERS), str(ORDERS))


def test_cash_starved_build():
    print("test_cash_starved_build")
    write_target()
    _clear_state()
    ctx = Context(cash=30000.0, total=30000.0, positions={})
    plan = make_plan(ctx, POOL)
    check("starved account still buys at least one lot", len(plan["buys"]) >= 1, str(plan["buys"]))
    spent = 0.0
    for c, v, _r in plan["buys"]:
        q = S._snap_one(S._pt_code(c))
        up, _dn = S._up_down(q, c)
        spent += v * S._buy_price(q.get("last"), q.get("ask1"), up)
    check("starved account does not overspend", spent <= 30000.0 * 1.001,
          "%.0f" % spent)


def test_cage_respects_limits():
    """QMT cage: buy min(min(ask*1.02, ask+0.1), limit_up); sell max(max(bid*0.98,
    bid-0.1), limit_down); sell anchors on bid, not on the last trade price."""
    print("test_cage_respects_limits")
    check("buy cage = ask+0.1 when that is tighter",
          S._buy_price(10.0, 10.0, 11.0) == 10.1, str(S._buy_price(10.0, 10.0, 11.0)))
    check("buy price never above limit-up",
          S._buy_price(10.0, 10.0, 10.05) == 10.05, str(S._buy_price(10.0, 10.0, 10.05)))
    check("sell cage = bid-0.1 when that is looser",
          S._sell_price(10.0, 10.0, 9.0) == 9.9, str(S._sell_price(10.0, 10.0, 9.0)))
    check("sell price never below limit-down",
          S._sell_price(10.0, 10.0, 9.95) == 9.95, str(S._sell_price(10.0, 10.0, 9.95)))
    check("sell anchors on bid, not last",
          S._sell_price(10.0, 9.5, 1.0) == 9.4, str(S._sell_price(10.0, 9.5, 1.0)))


def test_full_book_never_rebalances():
    """THE anti-churn property: a full book must never trade because a single name
    ran up (or crashed). Regression guard - do not relax it."""
    print("test_full_book_never_rebalances")
    target = (520000.0 - 520000.0 * S.DEFAULT_PARAMS["cash_reserve_ratio"]) / S.DEFAULT_PARAMS["max_holdings"]
    positions = {}
    for i, code in enumerate(POOL[:S.DEFAULT_PARAMS["max_holdings"]]):
        plain, mk = code.split(".")
        mult = 3.0 if i == 0 else (1.0 / 3.0 if i == 1 else 1.0)
        vol = max(int((target * mult) // P[plain] // S.LOT) * S.LOT, S.LOT)
        positions[code] = Pos(code, vol, vol, P[plain])
    ctx = Context(cash=5000.0, total=520000.0, positions=positions)
    plan = make_plan(ctx, POOL)
    check("full book: no sells", plan["sells"] == [], str(plan["sells"]))
    check("full book: no buys", plan["buys"] == [], str(plan["buys"]))
    check("full book: note explains why",
          any("book full" in n for n in plan["notes"]), str(plan["notes"]))


def test_gate_fires_on_cash_imbalance():
    """When the gate DOES fire (empty slots + cash/empty-slot far from target) every
    held in-pool name is pulled to target: over-weight trimmed, under-weight topped up."""
    print("test_gate_fires_on_cash_imbalance")
    total = 520000.0
    target = (total - total * S.DEFAULT_PARAMS["cash_reserve_ratio"]) / S.DEFAULT_PARAMS["max_holdings"]

    def vol_for(plain, mult):
        return max(int((target * mult) // P[plain] // S.LOT) * S.LOT, S.LOT)

    positions = {
        "605189.SH": Pos("605189.SH", vol_for("605189", 3.0), vol_for("605189", 3.0), P["605189"]),
        "301167.SZ": Pos("301167.SZ", vol_for("301167", 0.5), vol_for("301167", 0.5), P["301167"]),
        "600739.SH": Pos("600739.SH", vol_for("600739", 1.0), vol_for("600739", 1.0), P["600739"]),
        "601318.SH": Pos("601318.SH", vol_for("601318", 1.0), vol_for("601318", 1.0), P["601318"]),
    }
    ctx = Context(cash=400000.0, total=total, positions=positions)
    plan = make_plan(ctx, POOL)
    check("gate fired", any("rebalance gate" in n and "ON" in n for n in plan["notes"]),
          str(plan["notes"]))
    sells = dict((c, v) for c, v, _r in plan["sells"])
    check("over-weight name trimmed", sells.get("605189.SH", 0) > 0, str(sells))
    buys = dict((c, v) for c, v, _r in plan["buys"])
    check("under-weight name topped up", "301167.SZ" in buys, str(buys))


def test_buy_skipped_without_limit_up():
    """QMT: a buy with no usable limit-up is skipped, not sent blind."""
    print("test_buy_skipped_without_limit_up")
    saved = dict(QUOTES["600036.SS"])
    QUOTES["600036.SS"] = {"last": saved["last"]}      # no preclose -> no limit price
    try:
        ctx = build_context()
        _status, target = S._load_target(TARGET_FILE)
        plan = make_plan(ctx, target["_stocks"])
        buys = dict((c, v) for c, v, _r in plan["buys"])
        check("name without limit-up is not bought", "600036.SH" not in buys, str(buys))
        check("note explains the skip",
              any("no limit-up available" in n for n in plan["notes"]), str(plan["notes"]))
    finally:
        QUOTES["600036.SS"] = saved


def test_duplicate_pool_codes_deduped():
    """A duplicated code in the target list must not become two orders."""
    print("test_duplicate_pool_codes_deduped")
    dup_pool = [POOL[0], POOL[1], POOL[0], POOL[4], POOL[4], POOL[5]]
    write_target(stocks=dup_pool)
    try:
        ctx = build_context()
        status, target = S._load_target(TARGET_FILE)
        check("target status ok", status == "ok", status)
        check("duplicates removed, order preserved",
              target["_stocks"] == [POOL[0], POOL[1], POOL[4], POOL[5]],
              str(target["_stocks"]))
        check("duplicate counter", target["_dupes"] == 2, str(target["_dupes"]))
        plan = make_plan(ctx, target["_stocks"])
        codes = [c for c, _v, _r in plan["buys"]]
        check("no duplicate buy orders", len(codes) == len(set(codes)), str(codes))
    finally:
        write_target()


def test_st_uses_five_percent_band():
    """ST names have a 5% band; if that were missed the limit checks would think an
    ST stock sitting at +5% is not at its limit."""
    print("test_st_uses_five_percent_band")
    ST_NAMES.add("600739.SS")
    try:
        q = S._snap_one("600739.SS")
        up, down = S._up_down(q, "600739.SH")
        px = P["600739"]
        check("ST limit-up = preclose * 1.05",
              abs(up - round(px * 1.05, 2)) < 0.005, "%s vs %s" % (up, round(px * 1.05, 2)))
        check("ST limit-down = preclose * 0.95",
              abs(down - round(px * 0.95, 2)) < 0.005,
              "%s vs %s" % (down, round(px * 0.95, 2)))
    finally:
        ST_NAMES.discard("600739.SS")


def test_st_is_never_bought():
    """ST names must never be bought: the 12-rule compliance filter should have removed
    them, so one showing up means the upstream list is broken."""
    print("test_st_is_never_bought")
    ST_NAMES.add("600739.SS")
    try:
        ctx = build_context()
        _status, target = S._load_target(TARGET_FILE)
        plan = make_plan(ctx, target["_stocks"])
        buys = dict((c, v) for c, v, _r in plan["buys"])
        check("ST name is not bought", "600739.SH" not in buys, str(buys))
        check("ST refusal raises an ERROR entry",
              any("ST name 600739.SH" in e for e in plan["errors"]), str(plan["errors"]))
        check("ST refusal is not downgraded to a note",
              not any("ST" in n for n in plan["notes"]), str(plan["notes"]))
    finally:
        ST_NAMES.discard("600739.SS")


def test_previous_day_target_is_used():
    """List unavailable -> the local process writes nothing -> the PREVIOUS trading day's
    target is still in the research dir and must be traded (not skipped, not liquidated)
    as long as it is within MAX_TARGET_AGE_DAYS."""
    print("test_previous_day_target_is_used")
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    write_target(generated=yesterday.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        ctx = build_context()
        status, target = S._load_target(TARGET_FILE)
        check("yesterday's target is accepted", status == "ok", status)
        check("its age is reported", target.get("_stale_days") == 1,
              str(target.get("_stale_days")))
        ORDERS[:] = []
        _clear_state()
        run_job(ctx, "20261016@0942")
        sells = [o for o in ORDERS if o["amount"] < 0]
        buys = [o for o in ORDERS if o["amount"] > 0]
        check("it trades the previous list instead of liquidating",
              len(sells) == 1 and len(buys) >= 1, str(ORDERS))
    finally:
        write_target()


def test_too_old_target_liquidates():
    """No trustworthy list for more than MAX_TARGET_AGE_DAYS -> sell everything."""
    print("test_too_old_target_liquidates")
    old = datetime.datetime.now() - datetime.timedelta(days=S.MAX_TARGET_AGE_DAYS + 3)
    write_target(generated=old.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        ctx = build_context()
        status, _t = S._load_target(TARGET_FILE)
        check("too old -> stale", status == "stale", status)
        ORDERS[:] = []
        _clear_state()
        run_job(ctx, "20261016@0943")
        sold = dict((o["code"], o["amount"]) for o in ORDERS if o["amount"] < 0)
        check("every holding is sold", len(sold) == 3, str(sold))
        check("no buy during a stale liquidation",
              all(o["amount"] < 0 for o in ORDERS), str(ORDERS))
    finally:
        write_target()


def test_suffix_detected_from_position_codes():
    """The code suffix must come from the platform's own spelling, because snapshot probes
    are empty before the open (live 2026-10-19: it kept 'SS' while the platform uses the
    JoinQuant dialect XSHG/XSHE, so every 600xxx quote/order carried a wrong suffix)."""
    print("test_suffix_detected_from_position_codes")
    saved = (S._CODE_SUFFIX_SH[0], S._CODE_SUFFIX_SZ[0])
    try:
        xshg = {"600697.XSHG": Pos("600697.XSHG", 7000, 7000, 10.19),
                "002209.XSHE": Pos("002209.XSHE", 6000, 6000, 8.20)}
        ctx = Context(cash=10000.0, total=520000.0, positions=xshg)
        sh, sz, ev = S._detect_suffixes(ctx)
        check("XSHG/XSHE detected from raw position codes",
              sh == "XSHG" and sz == "XSHE", "%s / %s / %s" % (sh, sz, ev))
        check("the evidence names the raw code", "600697.XSHG" in ev, ev)

        sh2, sz2, ev2 = S._detect_suffixes(build_context())
        check("SS/SZ detected from .SS position codes",
              sh2 == "SS" and sz2 == "SZ", "%s / %s / %s" % (sh2, sz2, ev2))

        empty = Context(cash=1.0, total=1.0, positions={})
        sh3, sz3, ev3 = S._detect_suffixes(empty)
        check("no evidence -> documented default with a loud note",
              "NO EVIDENCE" in ev3 and
              (sh3, sz3) == (S.SH_SUFFIX_CANDIDATES[0], S.SZ_SUFFIX_CANDIDATES[0]),
              "%s / %s / %s" % (sh3, sz3, ev3))

        # a platform spelled .XSHG must produce orders/comparisons in that dialect
        S._CODE_SUFFIX_SH[0] = "XSHG"
        S._CODE_SUFFIX_SZ[0] = "XSHE"
        check("_pt_code spells Shanghai codes the platform's way",
              S._pt_code("600739.SH") == "600739.XSHG", S._pt_code("600739.SH"))
        check("_pt_code spells Shenzhen codes the platform's way",
              S._pt_code("000002.SZ") == "000002.XSHE", S._pt_code("000002.SZ"))
        check("quotes still resolve through the dialect mapping",
              S._snap_one("600739.XSHG").get("last") == P["600739"],
              str(S._snap_one("600739.XSHG")))
    finally:
        S._CODE_SUFFIX_SH[0] = saved[0]
        S._CODE_SUFFIX_SZ[0] = saved[1]


def test_platform_status_dict_is_handled():
    """Live 2026-10-19: get_stock_status() returns a dict keyed by the security, so testing
    the dict itself marked EVERY name halted and blocked every out-of-pool sell."""
    print("test_platform_status_dict_is_handled")
    saved = S.get_stock_status
    try:
        S.get_stock_status = lambda code, kind: {code: code.startswith("601318")}
        check("dict answer: halted name detected", S._is_halted("601318.SS") is True,
              repr(S._is_halted("601318.SS")))
        check("dict answer: healthy name is NOT halted",
              S._is_halted("600739.SS") is False, repr(S._is_halted("600739.SS")))
        check("dict answer: ST uses the same decoding",
              S._is_st("601318.SS") is True and S._is_st("600739.SS") is False)
        S.get_stock_status = lambda code, kind: {code: False}
        check("dict {code: False} is false even though the dict is truthy",
              S._is_halted("600739.SS") is False)
        S.get_stock_status = lambda code, kind: True
        check("plain bool answer still works", S._is_halted("600739.SS") is True)
        S.get_stock_status = lambda code, kind: {}
        check("empty dict -> not halted", S._is_halted("600739.SS") is False)
        S.get_stock_status = lambda code, kind: "0"
        check("string '0' -> not halted", S._is_halted("600739.SS") is False)
    finally:
        S.get_stock_status = saved


def test_place_prefers_order_market():
    """The proven production reference strategy orders via order_market(limit_price=...)."""
    print("test_place_prefers_order_market")
    saved = S.order_market
    try:
        ORDER_MARKET_CALLS[:] = []
        ORDERS[:] = []
        S._place(None, "600739.SS", 300, 10.30)
        check("order_market is used when available", len(ORDER_MARKET_CALLS) == 1,
              str(ORDER_MARKET_CALLS))
        call = ORDER_MARKET_CALLS[0] if ORDER_MARKET_CALLS else {}
        check("shares and the protective limit are passed through",
              call.get("amount") == 300 and call.get("limit_price") == 10.30, str(call))
        check("market_type follows the board map (60x -> 1)", call.get("market_type") == 1,
              str(call.get("market_type")))
        ORDER_MARKET_CALLS[:] = []
        S._place(None, "000002.SS", -800, None)
        check("sells pass a negative amount (300/00x -> market_type 0)",
              ORDER_MARKET_CALLS and ORDER_MARKET_CALLS[-1]["amount"] == -800 and
              ORDER_MARKET_CALLS[-1]["market_type"] == 0, str(ORDER_MARKET_CALLS[-1:]))
        del S.order_market
        ORDERS[:] = []
        S._place(None, "600739.SS", -300, None)
        check("falls back to order() when order_market is missing",
              len(ORDERS) == 1 and ORDERS[0]["amount"] == -300, str(ORDERS))
    finally:
        S.order_market = saved


def test_up_down_prefers_platform_limits():
    print("test_up_down_prefers_platform_limits")
    up, down = S._up_down({"preclose": 10.0, "limit_up": 11.0, "limit_down": 9.0,
                           "name": ""}, "600739.SH")
    check("platform up_px/down_px are used when published", (up, down) == (11.0, 9.0),
          "%s / %s" % (up, down))
    up2, down2 = S._up_down({"preclose": 10.0, "name": ""}, "600739.SH")
    check("falls back to preclose * board band",
          abs(up2 - 11.0) < 0.011 and abs(down2 - 9.0) < 0.011, "%s / %s" % (up2, down2))


def test_price_cage_is_compliant():
    """Exchange price cage (连续竞价价格笼子) + stricter broker rules forbid working an order
    at the limit-up / limit-down price. The old PTrade strategy did exactly that
    (order_market(limit_price=up_px) / down_px); the QMT version replaced it with a cage
    around the counterparty quote, and this port keeps that."""
    print("test_price_cage_is_compliant")
    check("buy cage = min(ask*1.02, ask+0.1)", S._buy_price(9.95, 10.00, 11.00) == 10.10,
          str(S._buy_price(9.95, 10.00, 11.00)))
    check("buy never exceeds the limit-up price",
          S._buy_price(10.95, 10.99, 11.00) <= 11.00, str(S._buy_price(10.95, 10.99, 11.00)))
    check("buy is clamped by a tight limit-up",
          S._buy_price(10.90, 10.95, 10.96) <= 10.96, str(S._buy_price(10.90, 10.95, 10.96)))
    check("sell cage = max(bid*0.98, bid-0.1)", S._sell_price(10.05, 10.00, 9.00) == 9.90,
          str(S._sell_price(10.05, 10.00, 9.00)))
    check("sell is clamped by a tight limit-down",
          S._sell_price(9.05, 9.01, 9.00) >= 9.00, str(S._sell_price(9.05, 9.01, 9.00)))
    # benchmark fallback per the exchange rule: counterparty -> last trade -> previous close
    check("buy falls back to last when ask is missing",
          S._buy_price(10.00, 0, 11.00) == 10.10, str(S._buy_price(10.00, 0, 11.00)))
    check("buy falls back to preclose when ask and last are missing",
          S._buy_price(0, 0, 11.00, 10.00) == 10.10, str(S._buy_price(0, 0, 11.00, 10.00)))
    check("sell falls back to last/preclose instead of the limit-down price",
          S._sell_price(0, 0, 9.00, 10.00) == 9.90, str(S._sell_price(0, 0, 9.00, 10.00)))
    check("no benchmark at all -> 0.0 so the caller skips (never an unprotected order)",
          S._sell_price(0, 0, 0, None) == 0.0 and S._buy_price(0, 0, 0, None) == 0.0)
    check("a buy no longer prices at the limit-up price when the last trade is lower",
          S._buy_price(10.00, 0, 11.00, 10.00) < 11.00,
          str(S._buy_price(10.00, 0, 11.00, 10.00)))


def test_target_found_in_upload_file_subfolder():
    """The PTrade client mirrors the local upload_file/ folder as a folder of the same
    name, so the real server path is <research>/upload_file/target_low_valuation.json."""
    print("test_target_found_in_upload_file_subfolder")
    fixed = os.path.join(RESEARCH, TARGET_FILE)
    if os.path.exists(fixed):
        os.remove(fixed)                       # no copy in the research root
    sub = os.path.join(RESEARCH, "upload_file")
    if not os.path.isdir(sub):
        os.makedirs(sub)
    sub_file = os.path.join(sub, TARGET_FILE)
    f = open(sub_file, "w")
    try:
        f.write(json.dumps({"strategy": "low_valuation",
                            "generated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                            "stocks": POOL}, ensure_ascii=False))
    finally:
        f.close()
    try:
        path, cands = S._find_target(TARGET_FILE)
        check("subfolder candidate is tried first",
              cands and cands[0].replace("\\", "/").endswith(
                  "upload_file/" + TARGET_FILE), str(cands))
        check("the subfolder target is the one chosen",
              path.replace("\\", "/").endswith("upload_file/" + TARGET_FILE), path)
        ctx = build_context()
        status, target = S._load_target(TARGET_FILE)
        check("it loads as a valid target", status == "ok" and len(target["_stocks"]) == len(POOL),
              status)
    finally:
        if os.path.exists(sub_file):
            os.remove(sub_file)
        write_target()


def test_two_strategies_share_a_position():
    """Two strategies on ONE account: the tracker hands each its own share, and a strategy
    may only ever sell its own shares (the ported QMT attribution)."""
    print("test_two_strategies_share_a_position")
    positions = {
        "605189.SS": Pos("605189.SS", 1000, 1000, P["605189"]),   # shared: alpha 600 + beta 400
        "301167.SZ": Pos("301167.SZ", 200, 200, P["301167"]),     # beta only
    }
    ctx = Context(cash=10000.0, total=520000.0, positions=positions)
    tracker = {"alpha": {"605189.SH": 600},
               "beta": {"605189.SH": 400, "301167.SZ": 200}}
    a = dict(S.DEFAULT_PARAMS)
    a["capital_ratio"] = 0.6
    b = dict(S.DEFAULT_PARAMS)
    b["capital_ratio"] = 0.4

    va = S._strategy_view(ctx, a, tracker, "alpha")
    vb = S._strategy_view(ctx, b, tracker, "beta")
    check("alpha sees only its 600 of the shared name",
          va["positions"].get("605189.SH", {}).get("amount") == 600, str(va["positions"]))
    check("beta sees its 400 of the shared name",
          vb["positions"].get("605189.SH", {}).get("amount") == 400, str(vb["positions"]))
    check("beta also sees its own name", vb["positions"].get("301167.SZ", {}).get("amount") == 200,
          str(vb["positions"]))
    check("alpha does not see beta's own name", "301167.SZ" not in va["positions"],
          str(va["positions"]))
    check("slice totals follow capital_ratio",
          abs(va["total"] - 520000.0 * 0.6) < 0.01 and
          abs(vb["total"] - 520000.0 * 0.4) < 0.01,
          "%s / %s" % (va["total"], vb["total"]))

    sold_a = dict((c, v) for c, v, _r in S._liquidate_plan(va, "test")["sells"])
    sold_b = dict((c, v) for c, v, _r in S._liquidate_plan(vb, "test")["sells"])
    check("alpha's exit sells exactly its 600 shares", sold_a == {"605189.SH": 600}, str(sold_a))
    check("beta's exit sells its 400 + its own name",
          sold_b == {"605189.SH": 400, "301167.SZ": 200}, str(sold_b))

    print("test_tracker_sync_assigns_untracked")
    # a broker code nobody tracks is handed to the biggest capital_ratio strategy
    t = {"alpha": {}, "beta": {}}
    broker = S._positions(ctx)
    S._tracker_sync(t, ["alpha", "beta"], {"alpha": a, "beta": b}, broker)
    check("untracked names go to the biggest capital_ratio holder",
          t["alpha"].get("605189.SH") == 1000 and t["alpha"].get("301167.SZ") == 200,
          str(t))


def test_only_fixed_name_is_read():
    """The sandbox has no os.listdir, so ONLY the fixed name can be read: a timestamped
    rebalance_<...>.json on its own must not be picked up. The local producer writes the
    fixed name into its upload_file/ dir, and that is what must be uploaded."""
    print("test_only_fixed_name_is_read")
    fixed = os.path.join(RESEARCH, TARGET_FILE)
    if os.path.exists(fixed):
        os.remove(fixed)
    stamped = os.path.join(RESEARCH, "rebalance_low_valuation_%s_0935.json"
                           % datetime.datetime.now().strftime("%Y%m%d"))
    f = open(stamped, "w")
    try:
        f.write(json.dumps({"strategy": "low_valuation",
                            "generated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                            "stocks": POOL}, ensure_ascii=False))
    finally:
        f.close()
    try:
        ctx = build_context()
        status, _t = S._load_target(TARGET_FILE)
        check("timestamped-only file is not discoverable -> missing", status == "missing", status)
        path, _c = S._find_target(TARGET_FILE)
        check("the strategy only looks at the fixed name",
              os.path.basename(path) == TARGET_FILE, path)
    finally:
        os.remove(stamped)
        write_target()      # restore the fixture for any later run


def main():
    global RESEARCH
    RESEARCH = fresh_dir()
    _install_fakes()
    build_quotes()
    write_target()
    S.DRY_RUN = True
    tests = [test_initialize_and_selfcheck, test_plan_math,
             test_dry_run_sends_nothing, test_execute_places_sells_then_buys,
             test_idempotent_per_time_tag, test_missing_target_is_skipped,
             test_old_target_is_flagged_stale, test_empty_pool_liquidates,
             test_cash_starved_build, test_cage_respects_limits,
             test_full_book_never_rebalances, test_gate_fires_on_cash_imbalance,
             test_buy_skipped_without_limit_up, test_duplicate_pool_codes_deduped,
             test_st_uses_five_percent_band, test_st_is_never_bought,
             test_previous_day_target_is_used, test_too_old_target_liquidates,
             test_two_strategies_share_a_position,
             test_suffix_detected_from_position_codes,
             test_platform_status_dict_is_handled,
             test_place_prefers_order_market,
             test_up_down_prefers_platform_limits,
             test_price_cage_is_compliant,
             test_target_found_in_upload_file_subfolder, test_only_fixed_name_is_read]
    for t in tests:
        t()
    print("\nALL %d TESTS PASSED" % len(tests))
    print("fixture kept at: %s" % RESEARCH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
