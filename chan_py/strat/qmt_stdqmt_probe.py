# -*- coding: utf-8 -*-
"""
qmt_stdqmt_probe.py - Standard QMT framework channel probe v11.2 (runs inside the QMT client)

HOW TO RUN (v11.2, sell-side test):
  1. Strategy Trading panel -> New Strategy -> select this file.
  2. Binding: ANY symbol works (SH000300 index proven fine - v11 buy test passed
     while bound to the index). Account 8880475040 (paper), 1-minute period.
  3. MODE MUST BE REAL-TIME TRADING (trading mode). Decisive finding: in
     "[trade]start simulation mode" framework orders never reach the order center
     (silently dropped); in "[trade]start trading mode" the full chain works:
     setQuickPassorderArguments -> send order to tradeModule -> push order -> push deal.
  4. DO NOT clear the client logs (engine evidence: [PYTHON PASSORDER] lines).
  5. Start during market hours; ~40s replay (silent) -> [live] line -> one variant
     per real-time bar. Watch the order panel.

Success criterion: a client-side ORDER record / deal callback appears. The
passorder/order_shares RETURN VALUE is NOT the criterion (qt2 orders return 0
even when they fill).

IMPORTANT (v11 lesson): handlebar fires on EVERY data update (~3s), not once per
bar. Any order logic MUST be gated per barpos or it will place duplicate orders
(v11 bug: 15 duplicate buys in 44s). v11.2 runs exactly ONE variant per live bar.

v11.2: SELL-side variants on 600051 (T+1: 000001 bought today is not sellable):
  vS1 passorder(24,1101,qt2,fixed) 100 sh 600051
  vS2 order_shares(600051.SH,-100,FIX)  (executor's sell path, negative shares)
  vS3 passorder(24,1101,qt1,price6=bid1) 100 sh 600051

Facts learned from engine logs (XtClient_Formula_*.log):
  - On strategy start the client replays the full history (e.g. 38073 one-minute bars,
    ~1ms per bar). During replay is_last_bar() is False and ALL order calls are skipped
    or deferred (passorder "cp, skip") - they return 0 and no client order is created.
  - Orders only execute once the strategy catches up to the live bar
    (is_last_bar() == True). This probe stays SILENT during replay and places its
    test orders only on the live bar.
  - Framework facts: ContextInfo has no accID (use set_account); trading functions are
    module-level: order_shares(stockcode, shares[, style, price], ContextInfo[, accId])
    and passorder(opType, orderType, accountid, orderCode, prType, price, volume
    [, strategyName, quickTrade, userOrderId], ContextInfo) - stock opType 23=buy
    24=sell; orderType 1101=shares 1102=amount(RMB); prType 11=fixed price;
    quickTrade 2 = fire immediately even on historical bars.
  - get_trade_detail_data(accountID, strAccountType, strDatatype) with strDatatype in
    POSITION/ORDER/DEAL/ACCOUNT; returns Python objects (obj.m_strInstrumentID ...).
  - Market data via ContextInfo: get_full_tick (dict, askPrice/bidPrice 5-level lists),
    get_instrument_detail (UpStopPrice/DownStopPrice). xtdata has no service in
    standard QMT and is not used.
"""

ACCOUNT_ID = "8880475040"

BUY_CODE = "000001.SZ"
SELL_CODE = "600051"
SELL_CODE_SUFFIXED = "600051.SH"

PROBE11_DONE = [False]
_LIVE_BAR = [None]      # barpos of the first live bar; variants fire from the NEXT bar
_VARIANT_IDX = [0]      # next variant to run
_LAST_VARIANT_BAR = [0] # barpos on which the last variant ran (per-bar gating)


def _safe(label, fn):
    try:
        fn()
    except Exception as e:
        print(f"[{label}] FAILED: {e!r}")


def _attr(obj, *names, default=None):
    for n in names:
        try:
            v = getattr(obj, n, None)
            if v is not None:
                return v
        except Exception:
            pass
    return default


def _obj_fields(obj, names):
    out = {}
    for n in names:
        v = _attr(obj, n)
        if v is not None:
            out[n] = v
    return out


def _tick_rows(ctx, codes):
    tick = ctx.get_full_tick(codes)
    rows = {}
    for code in codes:
        row = tick.get(code) if tick else None
        if isinstance(row, dict):
            rows[code] = row
            continue
        try:
            cols = list(row.columns)
            rows[code] = {c: row[c].iloc[-1] for c in cols}
        except Exception:
            rows[code] = None
    return rows


def _price5(row, field, fallback):
    try:
        v = row.get(field, [0])
        if isinstance(v, list) and v:
            return float(v[0])
        return float(v)
    except Exception:
        return fallback


def _try_one(label, fn):
    try:
        r = fn()
    except Exception as e:
        print(f"[order] {label} raised: {e!r}")
        return 0
    print(f"[order] {label} -> {r}")
    return r if (r and r > 0) else 0


def _order_rows():
    try:
        data = get_trade_detail_data(ACCOUNT_ID, 'STOCK', 'ORDER')
        return data if isinstance(data, (list, tuple)) else []
    except Exception:
        return []


def _v_sell_qt2_fixed(ctx, bid):
    return passorder(24, 1101, ACCOUNT_ID, SELL_CODE_SUFFIXED, 11, bid, 100,
                     "p11", 2, "s1", ctx)


def _v_sell_order_shares(ctx, bid):
    return order_shares(SELL_CODE_SUFFIXED, -100, "FIX", bid, ctx, ACCOUNT_ID)


def _v_sell_qt1_price6(ctx, bid):
    return passorder(24, 1101, ACCOUNT_ID, SELL_CODE_SUFFIXED, 6, 0, 100,
                     "p11", 1, "s2", ctx)


_VARIANTS = [
    ("vS1 passorder qt2 fixed", _v_sell_qt2_fixed),
    ("vS2 order_shares -100 FIX", _v_sell_order_shares),
    ("vS3 passorder qt1 price6", _v_sell_qt1_price6),
]


def probe11(ctx):
    """Sell-side variants, ONE per live bar. handlebar fires on every data update
    (~3s), so per-bar gating is mandatory; the chain advances only on new barpos."""

    if PROBE11_DONE[0]:
        return
    barpos = ctx.barpos
    if barpos == _LAST_VARIANT_BAR[0]:
        return
    _LAST_VARIANT_BAR[0] = barpos

    idx = _VARIANT_IDX[0]
    if idx >= len(_VARIANTS):
        PROBE11_DONE[0] = True
        print("[probe11] all variants done")
        _dump_trade_status()
        return

    rows = _tick_rows(ctx, [SELL_CODE_SUFFIXED])
    sell_row = rows.get(SELL_CODE_SUFFIXED)
    bid = _price5(sell_row, 'bidPrice', _price5(sell_row, 'lastPrice', 0.0)) if sell_row else 0.0
    if bid <= 0:
        print(f"[probe11] no bid for {SELL_CODE_SUFFIXED}, skip variant {idx}")
        _VARIANT_IDX[0] += 1
        return

    label, fn = _VARIANTS[idx]
    print(f"[probe11] {label} bid={bid}")
    _try_one(label, lambda: fn(ctx, bid))
    n = len(_order_rows())
    print(f"[probe11] after {label}: ORDER count={n}")
    _VARIANT_IDX[0] += 1


def _dump_trade_status():
    try:
        data = get_trade_detail_data(ACCOUNT_ID, 'STOCK', 'ORDER')
        items = [str(_obj_fields(o, ('m_strOrderSysID', 'm_strInstrumentID', 'm_nVolume',
                                      'm_dPrice', 'm_nOrderStatus', 'm_strStatus')))
                 for o in (data or [])[-3:]]
        print(f"[status] ORDER count={len(data) if data else 0} {items}")
    except Exception as e:
        print(f"[status] ORDER query failed: {e!r}")
    try:
        data = get_trade_detail_data(ACCOUNT_ID, 'STOCK', 'DEAL')
        items = [str(_obj_fields(o, ('m_strOrderSysID', 'm_strInstrumentID', 'm_nVolume',
                                      'm_dPrice')))
                 for o in (data or [])[-3:]]
        print(f"[status] DEAL count={len(data) if data else 0} {items}")
    except Exception as e:
        print(f"[status] DEAL query failed: {e!r}")


def order_callback(ContextInfo, orderInfo):
    try:
        fields = _obj_fields(orderInfo, ('m_strOrderSysID', 'm_strInstrumentID', 'm_nVolume',
                                         'm_dPrice', 'm_nOrderStatus', 'm_strStatus'))
        print(f"[cb] order: {fields}")
    except Exception as e:
        print(f"[cb] order_callback failed: {e!r}")


def deal_callback(ContextInfo, dealInfo):
    try:
        fields = _obj_fields(dealInfo, ('m_strOrderSysID', 'm_strInstrumentID',
                                        'm_nVolume', 'm_dPrice'))
        print(f"[cb] deal: {fields}")
    except Exception as e:
        print(f"[cb] deal_callback failed: {e!r}")


def orderError_callback(ContextInfo, passOrderInfo, msg):
    try:
        code = _attr(passOrderInfo, 'orderCode', 'm_strInstrumentID', default='')
        print(f"[cb] orderError code={code} msg={msg}")
    except Exception as e:
        print(f"[cb] orderError_callback failed: {e!r}")


def init(ContextInfo):
    print("=== probe init start ===")

    def set_account_stock():
        ContextInfo.set_account(ACCOUNT_ID, 'STOCK')
        print(f"[account] set_account({ACCOUNT_ID}, 'STOCK') OK")
    _safe("account set_account", set_account_stock)

    def market():
        rows = _tick_rows(ContextInfo, [BUY_CODE, SELL_CODE_SUFFIXED])
        for code in (BUY_CODE, SELL_CODE_SUFFIXED):
            row = rows.get(code)
            if row is not None:
                print(f"[market] {code} last={row.get('lastPrice')} "
                      f"ask1={_price5(row, 'askPrice', None)} bid1={_price5(row, 'bidPrice', None)}")
    _safe("market", market)

    def account():
        data = get_trade_detail_data(ACCOUNT_ID, 'STOCK', 'ACCOUNT')
        if data:
            fields = _obj_fields(data[0], ('m_strAccountID', 'm_dBalance',
                                           'm_dAvailable', 'm_dStockValue'))
            print(f"[account] {fields}")
    _safe("account", account)

    def positions():
        data = get_trade_detail_data(ACCOUNT_ID, 'STOCK', 'POSITION')
        for obj in (data or []):
            print(f"[position] {_attr(obj, 'm_strInstrumentID', default='')} "
                  f"vol={_attr(obj, 'm_nVolume', default=0)} "
                  f"canUse={_attr(obj, 'm_nCanUseVolume', default=0)}")
    _safe("position", positions)

    def orders_deals():
        data = get_trade_detail_data(ACCOUNT_ID, 'STOCK', 'ORDER')
        items = [str(_obj_fields(o, ('m_strOrderSysID', 'm_strInstrumentID', 'm_nVolume',
                                      'm_dPrice', 'm_nOrderStatus')))
                 for o in (data or [])[-5:]]
        print(f"[orders] init ORDER count={len(data) if data else 0} {items}")
        data = get_trade_detail_data(ACCOUNT_ID, 'STOCK', 'DEAL')
        items = [str(_obj_fields(o, ('m_strOrderSysID', 'm_strInstrumentID', 'm_nVolume',
                                      'm_dPrice')))
                 for o in (data or [])[-3:]]
        print(f"[orders] init DEAL count={len(data) if data else 0} {items}")
    _safe("orders_deals", orders_deals)

    print("=== probe init done (silent replay until live bar) ===")


def _diag(ctx, name):
    try:
        return str(getattr(ctx, name))
    except Exception as e:
        return f"ERR:{e!r}"


def handlebar(ContextInfo):
    # silent during history replay; place test orders only on real-time bars
    try:
        if not ContextInfo.is_last_bar():
            return
    except Exception:
        return
    if _LIVE_BAR[0] is None:
        _LIVE_BAR[0] = ContextInfo.barpos
        print(f"[live] barpos={ContextInfo.barpos} "
              f"do_back_test={_diag(ContextInfo, 'do_back_test')} "
              f"in_pythonworker={_diag(ContextInfo, 'in_pythonworker')} "
              f"(orders fire on the next bar)")
        return
    if ContextInfo.barpos == _LIVE_BAR[0]:
        return  # same bar as catch-up end; wait for the next (real-time) bar
    if not PROBE11_DONE[0]:
        probe11(ContextInfo)
