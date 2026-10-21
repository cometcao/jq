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
    """QUOTES is keyed <plain>.XSHG / <plain>.XSHE; fold any legacy spelling onto that."""
    code = str(code).upper()
    for a in (".XSHG", ".SS", ".SH"):
        if code.endswith(a):
            return code[:-len(a)] + ".XSHG"
    for a in (".XSHE", ".SZ"):
        if code.endswith(a):
            return code[:-len(a)] + ".XSHE"
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


def fake_get_stock_info(code, field=None):
    """The production reference strategy calls get_stock_info('603822.XSHG',
    field="stock_name")[code] - i.e. the platform API knows the JoinQuant dialect only."""
    c = str(code).upper()
    if c.endswith(".XSHG") or c.endswith(".XSHE"):
        return {code: {"stock_name": "FAKE"}}
    return {}


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
    S.get_stock_info = fake_get_stock_info
    S.get_positions = fake_get_positions
    S.order = fake_order
    S.order_market = fake_order_market
    S.run_daily = fake_run_daily


# ----------------------------------------------------------------------------
# scenario
# ----------------------------------------------------------------------------
POOL = ["605189.XSHG", "301167.XSHE", "002758.XSHE", "600697.XSHG", "600739.XSHG",
        "601318.XSHG", "600036.XSHG", "000002.XSHE", "600030.XSHG", "000651.XSHE",
        "600887.XSHG", "601166.XSHG", "600276.XSHG"]

P = {"605189": 17.85, "301167": 12.80, "002758": 8.20, "600697": 11.24,
     "600739": 10.19, "601318": 52.00, "600036": 38.50, "000002": 8.05,
     "600030": 21.30, "000651": 42.10, "600887": 28.40, "601166": 18.20,
     "600276": 45.60, "300750": 200.00}


def build_quotes():
    QUOTES.clear()
    for plain, px in P.items():
        mk = "XSHG" if plain[0] in "56" else "XSHE"
        QUOTES[plain + "." + mk] = {"last": px, "preclose": px}
    # 002758 (Shenzhen) locked at limit up (+10%)
    up = round(P["002758"] * 1.1, 2)
    QUOTES["002758.XSHE"]["last"] = up
    HALTED.clear()
    HALTED.add("600697.XSHG")


def build_context():
    positions = {
        "605189.XSHG": Pos("605189.XSHG", 3500, 3500, 17.85),   # in pool, within deadband
        "301167.XSHE": Pos("301167.XSHE", 1000, 1000, 12.80),   # in pool, under-weight
        "300750.XSHE": Pos("300750.XSHE", 200, 200, 200.00),    # out of pool -> sell all
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
    """The stable 'latest run' audit file (overwritten every run)."""
    return os.path.join(RESEARCH, S.AUDIT_PREFIX + (strategy or STRAT) + ".json")


def audit_daily_file(strategy=None):
    """The rotating weekday slot the run ALSO writes (retention without os.remove)."""
    return S._audit_daily_path(strategy or STRAT)


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
    check("the code dialect is the fixed JoinQuant one",
          S.CAPS.get("code_dialect") == "XSHG / XSHE (fixed)",
          str(S.CAPS.get("code_dialect")))
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
    check("out-of-pool name fully sold", sells.get("300750.XSHE") == 200, str(sells))
    check("in-pool name inside deadband is untouched", "605189.XSHG" not in sells)
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
          "301167.XSHE" not in buys, str(buys))
    check("limit-up candidate is skipped", "002758.XSHE" not in buys)
    check("halted candidate is skipped", "600697.XSHG" not in buys)
    for c in ("600739.XSHG", "601318.XSHG", "600036.XSHG", "000002.XSHE"):
        check("new slot filled: %s" % c, c in buys)
    check("no more than max_holdings names held after the run",
          len(set(["605189.XSHG", "301167.XSHE"]) | set(buys.keys())) <= S.DEFAULT_PARAMS["max_holdings"],
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


def test_wait_for_proceeds_sees_fills():
    """QMT polled positions after each phase (wait_for_order_completion) and then corrected the
    tracker from the broker. PTrade must at least notice which codes moved, so the tracker can
    be re-derived from reality instead of the plan."""
    print("test_wait_for_proceeds_sees_fills")
    saved_cash, saved_positions, saved_sleep = S._cash, S._positions, S.time.sleep
    try:
        S.time.sleep = lambda s: None           # no real sleeping in the test
        state = {"cash": 0.0, "pos": {"605189.XSHG": 1000, "300750.XSHE": 200}}
        S._cash = lambda ctx: state["cash"]
        S._positions = lambda ctx: dict(
            (c, {"amount": v, "enable": v, "last": 1.0, "name": ""})
            for c, v in state["pos"].items())
        # first poll: nothing has filled yet -> we must not report a fill
        cash1, filled1 = S._wait_for_proceeds(None, 1000.0, 2)
        check("no movement -> no confirmed fills", filled1 == set(), str(filled1))
        # then the sell fills WHILE we are waiting: cash arrives, the code disappears
        def fill_during_sleep(sec):
            state["cash"] = 800.0
            state["pos"] = {"605189.XSHG": 1000}
        S.time.sleep = fill_during_sleep
        cash2, filled2 = S._wait_for_proceeds(None, 1000.0, 3)
        check("a filled sell is reported", filled2 == {"300750.XSHE"}, str(filled2))
        check("the new cash is reported back", cash2 == 800.0, str(cash2))
    finally:
        S._cash, S._positions, S.time.sleep = saved_cash, saved_positions, saved_sleep

    print("test_tracker_after_trade_uses_broker_volumes")
    t = {"low_valuation": {"600697.XSHG": 7000, "002209.XSHE": 6000},
         "other": {"600697.XSHG": 1000}}
    broker = {"600697.XSHG": {"amount": 5000}, "002209.XSHE": {"amount": 0}}
    S._tracker_after_trade(t, "low_valuation", ["600697.XSHG", "002209.XSHE"], broker)
    check("share is broker minus the other strategies", t["low_valuation"]["600697.XSHG"] == 4000,
          str(t["low_valuation"]))
    check("a name the broker no longer holds is removed",
          "002209.XSHE" not in t["low_valuation"], str(t["low_valuation"]))


def test_buys_scale_to_real_cash():
    """Live 2026-10-21: three buys were sized from the ESTIMATE of the sell proceeds (223874)
    while only 150943 had actually settled, so the broker rejected the third with
    [可用资金不足] and one slot stayed empty. Buys must be scaled to the cash that is really
    there, and a skipped buy must be retried once the money lands."""
    print("test_buys_scale_to_real_cash")
    saved_cash, saved_snap = S._cash, S._snap_one
    try:
        px = {"AAA.XSHE": 6.10, "BBB.XSHG": 15.03, "CCC.XSHE": 9.92}
        S._snap_one = lambda pt: {"last": px[pt], "ask1": px[pt] * 1.001,
                                  "preclose": px[pt], "limit_up": round(px[pt] * 1.1, 2),
                                  "limit_down": round(px[pt] * 0.9, 2), "name": ""}
        buys = [("AAA.XSHE", 11600, "new-slot"), ("BBB.XSHG", 4700, "new-slot"),
                ("CCC.XSHE", 7100, "new-slot")]
        S._cash = lambda ctx: 150943.51
        ORDERS[:] = []
        results = []
        skipped = S._execute_buys(None, buys, results, reserve=7735.24)
        check("only the buys the cash covers are sent", len(ORDERS) == 2, str(ORDERS))
        spent = sum(o["amount"] * o["limit_price"] for o in ORDERS)
        check("the cash_reserve_ratio buffer is never spent",
              spent <= 150943.51 - 7735.24, "spent %.2f" % spent)
        check("the unaffordable one is skipped, not rejected",
              len(skipped) == 1 and skipped[0][0] == "CCC.XSHE", str(skipped))
        check("the skip is recorded as no-cash",
              any(r.get("skipped") == "no-cash" for r in results), str(results))

        S._cash = lambda ctx: 230000.0     # the remaining sell proceeds landed
        ORDERS[:] = []
        skipped2 = S._execute_buys(None, skipped, results)
        check("the retry buys the slot once the proceeds arrive",
              len(ORDERS) == 1 and skipped2 == [], str(ORDERS))

        # a position worth less than half the plan is not worth submitting at all
        S._cash = lambda ctx: 12000.0
        ORDERS[:] = []
        tail = S._execute_buys(None, [("CCC.XSHE", 7100, "new-slot")], [])
        check("a tiny remainder is skipped instead of creating a sub-size position",
              ORDERS == [] and len(tail) == 1, str(ORDERS))
    finally:
        S._cash, S._snap_one = saved_cash, saved_snap


def test_audit_retention_uses_fixed_slots():
    """The sandbox cannot delete or list files, so "keep 5 trading days" must be implemented by
    REUSING fixed names, not by deleting: <strategy>.json is always the latest run and
    <strategy>_d1..d5.json are weekday slots (Mon..Fri) overwritten weekly."""
    print("test_audit_retention_uses_fixed_slots")
    S.AUDIT_SLOTS = 5
    latest = S._audit_path(STRAT)
    slots = set()
    for i in range(7):
        day = datetime.date(2026, 10, 19) + datetime.timedelta(days=i)   # Mon..Sun
        slot = S._audit_daily_slot(day)
        slots.add(slot)
        check("weekday %s maps to a slot inside 1..5" % day.strftime("%a"), 1 <= slot <= 5,
              str(slot))
    check("all seven days collapse into the five weekday slots", slots == set([1, 2, 3, 4, 5]),
          str(sorted(slots)))
    check("the latest file has a stable, date-less name",
          S._basename(latest) == S.AUDIT_PREFIX + STRAT + ".json", latest)
    check("the daily file name carries the slot",
          "_d" in S._basename(S._audit_daily_path(STRAT)), S._audit_daily_path(STRAT))
    saved = S.AUDIT_SLOTS
    try:
        S.AUDIT_SLOTS = 1
        check("AUDIT_SLOTS=1 keeps a single rotating file",
              S._basename(S._audit_daily_path(STRAT)).endswith("_d1.json"),
              S._audit_daily_path(STRAT))
    finally:
        S.AUDIT_SLOTS = saved


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
          ORDERS[0]["code"] == S._pt_code("300750.XSHE") and
          ORDERS[0]["amount"] == -200,
          str(ORDERS[0]))
    check("the sell protection is as aggressive as the rules allow (max(last*0.98, limit-down))",
          ORDERS[0]["limit_price"] == 196.0, str(ORDERS[0]))
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
    bid-0.1), limit_down); sell anchors on bid, not on the last trade price.

    Separate from the ORDER protection price: order_market's limit_price is a protection
    bound, and the strategy's rule is "sell with everything you have" -> the sell order is
    sent with the LIMIT-DOWN price (see test_order_protection_prices)."""
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


def test_order_protection_prices():
    """Sell protection is as aggressive as the rules allow: max(last*0.98, limit-down).
    The broker's ~2% deviation rule for quant orders must never be broken, and the exchange
    floor (limit-down) must never be broken either. Buys stay caged and capped at last*1.02."""
    print("test_order_protection_prices")
    check("SELL protection = last*0.98 when the 2% band is the binding floor",
          S._sell_protect(10.0, 9.99, 8.0) == 9.8, str(S._sell_protect(10.0, 9.99, 8.0)))
    check("SELL protection = limit-down when the stock is already at the floor",
          S._sell_protect(9.0, 9.0, 9.0) == 9.0, str(S._sell_protect(9.0, 9.0, 9.0)))
    check("SELL never goes below limit-down",
          S._sell_protect(10.0, 9.99, 9.9) == 9.9, str(S._sell_protect(10.0, 9.99, 9.9)))
    check("SELL never goes more than 2% below the last price",
          S._sell_protect(100.0, 99.9, 90.0) == 98.0, str(S._sell_protect(100.0, 99.9, 90.0)))
    check("SELL falls back to the cage when the last price is unknown",
          S._sell_protect(0, 10.0, 0) == 9.9, str(S._sell_protect(0, 10.0, 0)))
    check("SELL with neither floor nor quote -> 0 (caller skips)",
          S._sell_protect(0, 0, 0) == 0.0, str(S._sell_protect(0, 0, 0)))
    check("BUY protection stays inside the cage (no chasing)",
          S._buy_protect(9.95, 10.0, 11.0) == 10.1, str(S._buy_protect(9.95, 10.0, 11.0)))
    check("BUY is capped at last*1.02 even when the ask is far above",
          S._buy_protect(10.0, 12.0, 20.0) == 10.2, str(S._buy_protect(10.0, 12.0, 20.0)))
    saved = S.BUY_PROTECT_AT_LIMIT_UP
    try:
        S.BUY_PROTECT_AT_LIMIT_UP = True
        check("BUY switched to limit-up is still capped at last*1.02",
              S._buy_protect(10.0, 10.0, 11.0) == 10.2, str(S._buy_protect(10.0, 10.0, 11.0)))
    finally:
        S.BUY_PROTECT_AT_LIMIT_UP = saved
    up, down = S._up_down(S._snap_one(S._pt_code("300750.XSHE")), "300750.XSHE")
    check("limit-down is derived from the snapshot (ChiNext 300xxx -> preclose * 0.8)",
          down == 160.0, "%s / %s" % (up, down))


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
        "605189.XSHG": Pos("605189.XSHG", vol_for("605189", 3.0), vol_for("605189", 3.0), P["605189"]),
        "301167.XSHE": Pos("301167.XSHE", vol_for("301167", 0.5), vol_for("301167", 0.5), P["301167"]),
        "600739.XSHG": Pos("600739.XSHG", vol_for("600739", 1.0), vol_for("600739", 1.0), P["600739"]),
        "601318.XSHG": Pos("601318.XSHG", vol_for("601318", 1.0), vol_for("601318", 1.0), P["601318"]),
    }
    ctx = Context(cash=400000.0, total=total, positions=positions)
    plan = make_plan(ctx, POOL)
    check("gate fired", any("rebalance gate" in n and "ON" in n for n in plan["notes"]),
          str(plan["notes"]))
    sells = dict((c, v) for c, v, _r in plan["sells"])
    check("over-weight name trimmed", sells.get("605189.XSHG", 0) > 0, str(sells))
    buys = dict((c, v) for c, v, _r in plan["buys"])
    check("under-weight name topped up", "301167.XSHE" in buys, str(buys))


def test_buy_skipped_without_limit_up():
    """QMT: a buy with no usable limit-up is skipped, not sent blind."""
    print("test_buy_skipped_without_limit_up")
    saved = dict(QUOTES["600036.XSHG"])
    QUOTES["600036.XSHG"] = {"last": saved["last"]}      # no preclose -> no limit price
    try:
        ctx = build_context()
        _status, target = S._load_target(TARGET_FILE)
        plan = make_plan(ctx, target["_stocks"])
        buys = dict((c, v) for c, v, _r in plan["buys"])
        check("name without limit-up is not bought", "600036.XSHG" not in buys, str(buys))
        check("note explains the skip",
              any("no limit-up available" in n for n in plan["notes"]), str(plan["notes"]))
    finally:
        QUOTES["600036.XSHG"] = saved


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
    ST_NAMES.add("600739.XSHG")
    try:
        q = S._snap_one("600739.XSHG")
        up, down = S._up_down(q, "600739.XSHG")
        px = P["600739"]
        check("ST limit-up = preclose * 1.05",
              abs(up - round(px * 1.05, 2)) < 0.005, "%s vs %s" % (up, round(px * 1.05, 2)))
        check("ST limit-down = preclose * 0.95",
              abs(down - round(px * 0.95, 2)) < 0.005,
              "%s vs %s" % (down, round(px * 0.95, 2)))
    finally:
        ST_NAMES.discard("600739.XSHG")


def test_st_is_never_bought():
    """ST names must never be bought: the 12-rule compliance filter should have removed
    them, so one showing up means the upstream list is broken."""
    print("test_st_is_never_bought")
    ST_NAMES.add("600739.XSHG")
    try:
        ctx = build_context()
        _status, target = S._load_target(TARGET_FILE)
        plan = make_plan(ctx, target["_stocks"])
        buys = dict((c, v) for c, v, _r in plan["buys"])
        check("ST name is not bought", "600739.XSHG" not in buys, str(buys))
        check("ST refusal raises an ERROR entry",
              any("ST name 600739.XSHG" in e for e in plan["errors"]), str(plan["errors"]))
        check("ST refusal is not downgraded to a note",
              not any("ST" in n for n in plan["notes"]), str(plan["notes"]))
    finally:
        ST_NAMES.discard("600739.XSHG")


def test_previous_day_target_is_rejected():
    """TODAY ONLY (2026-10-19): a target that was not generated today must NOT be traded -
    the run raises an ERROR and leaves positions untouched. (Only a target older than
    MAX_TARGET_AGE_DAYS is liquidated, which the next test covers.)"""
    print("test_previous_day_target_is_rejected")
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    write_target(generated=yesterday.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        ctx = build_context()
        status, target = S._load_target(TARGET_FILE)
        check("yesterday's target is NOT ok", status == "not-today", status)
        check("its age is still reported", target.get("_stale_days") == 1,
              str(target.get("_stale_days")))
        ORDERS[:] = []
        _clear_state()
        del S.LOGS[:]
        run_job(ctx, "20261019@0942")
        check("nothing is traded on a not-today list", ORDERS == [], str(ORDERS))
        check("an ERROR explains why",
              any("NOT from today" in l and "ERROR" in l for l in S.LOGS), str(S.LOGS[-3:]))
    finally:
        write_target()


def test_too_old_target_liquidates():
    """No trustworthy list for more than MAX_TARGET_AGE_DAYS -> sell everything.
    The boundary is checked too: exactly MAX_TARGET_AGE_DAYS old is still only
    'not-today' (skip), one day older is 'stale' (liquidate)."""
    print("test_too_old_target_liquidates")
    boundary = datetime.datetime.now() - datetime.timedelta(days=S.MAX_TARGET_AGE_DAYS)
    write_target(generated=boundary.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        status_b, _tb = S._load_target(TARGET_FILE)
        check("exactly MAX_TARGET_AGE_DAYS old is still only 'not-today'",
              status_b == "not-today", status_b)
    finally:
        write_target()
    old = datetime.datetime.now() - datetime.timedelta(days=S.MAX_TARGET_AGE_DAYS + 1)
    write_target(generated=old.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        ctx = build_context()
        status, _t = S._load_target(TARGET_FILE)
        check("older than MAX_TARGET_AGE_DAYS -> stale", status == "stale", status)
        ORDERS[:] = []
        _clear_state()
        run_job(ctx, "20261016@0943")
        sold = dict((o["code"], o["amount"]) for o in ORDERS if o["amount"] < 0)
        check("every holding is sold", len(sold) == 3, str(sold))
        check("no buy during a stale liquidation",
              all(o["amount"] < 0 for o in ORDERS), str(ORDERS))
    finally:
        write_target()


def test_full_book_exits_then_buys():
    """Live 2026-10-20: a FULL book (8/8, cash 0) sold two out-of-pool names and then bought
    NOTHING, because slots were counted on the pre-sell book (slots=0) and the buy budget
    used cash=0 instead of the sell proceeds. PTrade fills asynchronously, so the plan must
    use the slots and the cash that this run's own sells free up."""
    print("test_full_book_exits_then_buys")
    QUOTES["002073.XSHE"] = {"last": 5.50, "preclose": 5.50}
    try:
        pos = {
            "300750.XSHE": Pos("300750.XSHE", 200, 200, 200.00),     # out of pool -> sell
            "002073.XSHE": Pos("002073.XSHE", 13800, 13800, 5.50),   # out of pool -> sell
            "605189.XSHG": Pos("605189.XSHG", 1000, 1000, P["605189"]),
            "301167.XSHE": Pos("301167.XSHE", 1000, 1000, P["301167"]),
            "600697.XSHG": Pos("600697.XSHG", 1000, 1000, P["600697"]),
            "600036.XSHG": Pos("600036.XSHG", 1000, 1000, P["600036"]),
            "000002.XSHE": Pos("000002.XSHE", 1000, 1000, P["000002"]),
            "601318.XSHG": Pos("601318.XSHG", 1000, 1000, P["601318"]),
        }
        ctx = Context(cash=0.0, total=616687.52, positions=pos)   # fully invested
        plan = make_plan(ctx, POOL, dict(S.DEFAULT_PARAMS))
        check("the two out-of-pool names are sold", len(plan["sells"]) == 2,
              str(plan["sells"]))
        check("the slots freed by those sells are used in the SAME run",
              len(plan["buys"]) == 2, str(plan["buys"]))
        check("the projected proceeds fund the buys", plan.get("est_in", 0) > 100000,
              str(plan.get("est_in")))
        notes = " ".join(plan["notes"])
        check("the gate/notes count the 2 slots the sells free, in the same run",
              "slots=2" in notes or "after this run's exits" in notes, notes)
    finally:
        QUOTES.pop("002073.XSHE", None)


def test_code_dialect_is_xshg_xshe():
    """ONE dialect everywhere (2026-10-19): whatever spelling comes in, everything this
    strategy produces - internal keys, tracker keys, order/snapshot codes - is XSHG/XSHE.
    The QMT-era .SH/.SZ forms are only tolerated when reading old data."""
    print("test_code_dialect_is_xshg_xshe")
    check("legacy Shanghai suffix -> XSHG", S._full_code("600739.SH") == "600739.XSHG",
          S._full_code("600739.SH"))
    check("canonical code passes through", S._full_code("600739.XSHG") == "600739.XSHG",
          S._full_code("600739.XSHG"))
    check("bare 6-digit code -> XSHG", S._full_code("600739") == "600739.XSHG",
          S._full_code("600739"))
    check("legacy Shenzhen suffix -> XSHE", S._full_code("000002.SZ") == "000002.XSHE",
          S._full_code("000002.SZ"))
    check("legacy SH600739 form is still read", S._full_code("SH600739") == "600739.XSHG",
          S._full_code("SH600739"))
    check("the API code IS the internal code",
          S._pt_code("600739.SH") == S._full_code("600739.SH") == "600739.XSHG",
          S._pt_code("600739.SH"))
    check("positions are keyed XSHG/XSHE",
          sorted(S._positions(build_context()).keys()) ==
          ["300750.XSHE", "301167.XSHE", "605189.XSHG"],
          str(sorted(S._positions(build_context()).keys())))
    # an old tracker file must migrate instead of double counting
    old = {"low_valuation": {"600697.SH": 7000, "002209.SZ": 6000}}
    with open(S._tracker_path(), "w") as f:
        json.dump(old, f)
    t = S._tracker_load()
    check("old .SH/.SZ tracker keys migrate to XSHG/XSHE",
          t.get("low_valuation") == {"600697.XSHG": 7000, "002209.XSHE": 6000}, str(t))


def test_platform_status_dict_is_handled():
    """Live 2026-10-19: get_stock_status() returns a dict keyed by the security, so testing
    the dict itself marked EVERY name halted and blocked every out-of-pool sell."""
    print("test_platform_status_dict_is_handled")
    saved = S.get_stock_status
    try:
        S.get_stock_status = lambda code, kind: {code: code.startswith("601318")}
        check("dict answer: halted name detected", S._is_halted("601318.XSHG") is True,
              repr(S._is_halted("601318.XSHG")))
        check("dict answer: healthy name is NOT halted",
              S._is_halted("600739.XSHG") is False, repr(S._is_halted("600739.XSHG")))
        check("dict answer: ST uses the same decoding",
              S._is_st("601318.XSHG") is True and S._is_st("600739.XSHG") is False)
        S.get_stock_status = lambda code, kind: {code: False}
        check("dict {code: False} is false even though the dict is truthy",
              S._is_halted("600739.XSHG") is False)
        S.get_stock_status = lambda code, kind: True
        check("plain bool answer still works", S._is_halted("600739.XSHG") is True)
        S.get_stock_status = lambda code, kind: {}
        check("empty dict -> not halted", S._is_halted("600739.XSHG") is False)
        S.get_stock_status = lambda code, kind: "0"
        check("string '0' -> not halted", S._is_halted("600739.XSHG") is False)
    finally:
        S.get_stock_status = saved


def test_place_prefers_order_market():
    """The proven production reference strategy orders via order_market(limit_price=...)."""
    print("test_place_prefers_order_market")
    saved = S.order_market
    try:
        ORDER_MARKET_CALLS[:] = []
        ORDERS[:] = []
        S._place(None, "600739.XSHG", 300, 10.30)
        check("order_market is used when available", len(ORDER_MARKET_CALLS) == 1,
              str(ORDER_MARKET_CALLS))
        call = ORDER_MARKET_CALLS[0] if ORDER_MARKET_CALLS else {}
        check("shares and the protective limit are passed through",
              call.get("amount") == 300 and call.get("limit_price") == 10.30, str(call))
        check("market_type follows the board map (60x -> 1)", call.get("market_type") == 1,
              str(call.get("market_type")))
        ORDER_MARKET_CALLS[:] = []
        S._place(None, "000002.XSHG", -800, None)
        check("sells pass a negative amount (300/00x -> market_type 0)",
              ORDER_MARKET_CALLS and ORDER_MARKET_CALLS[-1]["amount"] == -800 and
              ORDER_MARKET_CALLS[-1]["market_type"] == 0, str(ORDER_MARKET_CALLS[-1:]))
        del S.order_market
        ORDERS[:] = []
        S._place(None, "600739.XSHG", -300, None)
        check("falls back to order() when order_market is missing",
              len(ORDERS) == 1 and ORDERS[0]["amount"] == -300, str(ORDERS))
    finally:
        S.order_market = saved


def test_up_down_prefers_platform_limits():
    print("test_up_down_prefers_platform_limits")
    up, down = S._up_down({"preclose": 10.0, "limit_up": 11.0, "limit_down": 9.0,
                           "name": ""}, "600739.XSHG")
    check("platform up_px/down_px are used when published", (up, down) == (11.0, 9.0),
          "%s / %s" % (up, down))
    up2, down2 = S._up_down({"preclose": 10.0, "name": ""}, "600739.XSHG")
    check("falls back to preclose * board band",
          abs(up2 - 11.0) < 0.011 and abs(down2 - 9.0) < 0.011, "%s / %s" % (up2, down2))


def test_order_fallback_when_market_order_fails():
    """A board (e.g. STAR 688) may reject a market order. The rule: retry as a +-2% repriced
    LIMIT order at the same protective price (still inside limit-up/down), never send blind."""
    print("test_order_fallback_when_market_order_fails")
    saved_om = getattr(S, "order_market", None)
    saved_get = getattr(S, "get_order", None)
    try:
        # (a) order_market returns nothing -> rejected -> limit retry at the same protect price
        S.order_market = lambda code, amount=None, market_type=None, limit_price=None: None
        ORDER_MARKET_CALLS[:] = []
        ORDERS[:] = []
        del S.LOGS[:]
        oid = S._place(None, "688001.XSHG", 100, 12.24)
        check("a rejected market order is retried as a limit order",
              len(ORDERS) == 1 and ORDERS[0]["limit_price"] == 12.24, str(ORDERS))
        check("the retry is visible in the log",
              any("retrying as a limit order" in l for l in S.LOGS), str(S.LOGS[-2:]))
        check("an order id is still returned", oid is not None, str(oid))

        # (b) the market-order API raises (unsupported) -> same fallback
        def boom(*a, **k):
            raise RuntimeError("market order not supported")
        S.order_market = boom
        ORDERS[:] = []
        S._place(None, "688001.XSHG", -100, 11.76)
        check("an unsupported market-order API still ends up as a limit order",
              len(ORDERS) == 1 and ORDERS[0]["amount"] == -100 and
              ORDERS[0]["limit_price"] == 11.76, str(ORDERS))

        # (c) the platform reports the submission as rejected ('9') -> fallback
        S.order_market = fake_order_market
        S.get_order = lambda oid: [type("O", (), {"status": "9"})()]
        ORDERS[:] = []
        S._place(None, "688001.XSHG", 100, 12.24)
        check("a '9' (rejected) status triggers the limit retry",
              len(ORDERS) == 2 and ORDERS[-1]["limit_price"] == 12.24, str(ORDERS))

        # (d) STAR market type is a one-line knob
        check("STAR market type comes from MARKET_TYPE_STAR",
              S._market_type("688001.XSHG") == S.MARKET_TYPE_STAR,
              str(S._market_type("688001.XSHG")))
        saved_star = S.MARKET_TYPE_STAR
        try:
            S.MARKET_TYPE_STAR = 1
            check("MARKET_TYPE_STAR can be flipped without touching the logic",
                  S._market_type("688001.XSHG") == 1, str(S._market_type("688001.XSHG")))
        finally:
            S.MARKET_TYPE_STAR = saved_star
    finally:
        if saved_om is not None:
            S.order_market = saved_om
        if saved_get is not None:
            S.get_order = saved_get
        elif hasattr(S, "get_order"):
            del S.get_order


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
        "605189.XSHG": Pos("605189.XSHG", 1000, 1000, P["605189"]),   # shared: alpha 600 + beta 400
        "301167.XSHE": Pos("301167.XSHE", 200, 200, P["301167"]),     # beta only
    }
    ctx = Context(cash=10000.0, total=520000.0, positions=positions)
    tracker = {"alpha": {"605189.XSHG": 600},
               "beta": {"605189.XSHG": 400, "301167.XSHE": 200}}
    a = dict(S.DEFAULT_PARAMS)
    a["capital_ratio"] = 0.6
    b = dict(S.DEFAULT_PARAMS)
    b["capital_ratio"] = 0.4

    va = S._strategy_view(ctx, a, tracker, "alpha")
    vb = S._strategy_view(ctx, b, tracker, "beta")
    check("alpha sees only its 600 of the shared name",
          va["positions"].get("605189.XSHG", {}).get("amount") == 600, str(va["positions"]))
    check("beta sees its 400 of the shared name",
          vb["positions"].get("605189.XSHG", {}).get("amount") == 400, str(vb["positions"]))
    check("beta also sees its own name", vb["positions"].get("301167.XSHE", {}).get("amount") == 200,
          str(vb["positions"]))
    check("alpha does not see beta's own name", "301167.XSHE" not in va["positions"],
          str(va["positions"]))
    check("slice totals follow capital_ratio",
          abs(va["total"] - 520000.0 * 0.6) < 0.01 and
          abs(vb["total"] - 520000.0 * 0.4) < 0.01,
          "%s / %s" % (va["total"], vb["total"]))

    sold_a = dict((c, v) for c, v, _r in S._liquidate_plan(va, "test")["sells"])
    sold_b = dict((c, v) for c, v, _r in S._liquidate_plan(vb, "test")["sells"])
    check("alpha's exit sells exactly its 600 shares", sold_a == {"605189.XSHG": 600}, str(sold_a))
    check("beta's exit sells its 400 + its own name",
          sold_b == {"605189.XSHG": 400, "301167.XSHE": 200}, str(sold_b))

    print("test_tracker_sync_assigns_untracked")
    # a broker code nobody tracks is handed to the biggest capital_ratio strategy
    t = {"alpha": {}, "beta": {}}
    broker = S._positions(ctx)
    S._tracker_sync(t, ["alpha", "beta"], {"alpha": a, "beta": b}, broker)
    check("untracked names go to the biggest capital_ratio holder",
          t["alpha"].get("605189.XSHG") == 1000 and t["alpha"].get("301167.XSHE") == 200,
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
             test_wait_for_proceeds_sees_fills,
             test_buys_scale_to_real_cash,
             test_audit_retention_uses_fixed_slots,
             test_dry_run_sends_nothing, test_execute_places_sells_then_buys,
             test_idempotent_per_time_tag, test_missing_target_is_skipped,
             test_old_target_is_flagged_stale, test_empty_pool_liquidates,
             test_cash_starved_build, test_cage_respects_limits,
             test_order_protection_prices,
             test_full_book_never_rebalances, test_gate_fires_on_cash_imbalance,
             test_buy_skipped_without_limit_up, test_duplicate_pool_codes_deduped,
             test_st_uses_five_percent_band, test_st_is_never_bought,
             test_previous_day_target_is_rejected, test_too_old_target_liquidates,
             test_two_strategies_share_a_position,
             test_full_book_exits_then_buys,
             test_code_dialect_is_xshg_xshe,
             test_platform_status_dict_is_handled,
             test_place_prefers_order_market,
             test_up_down_prefers_platform_limits,
             test_price_cage_is_compliant,
             test_order_fallback_when_market_order_fails,
             test_target_found_in_upload_file_subfolder, test_only_fixed_name_is_read]
    for t in tests:
        t()
    print("\nALL %d TESTS PASSED" % len(tests))
    print("fixture kept at: %s" % RESEARCH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
