# -*- coding: utf-8 -*-
"""
qmt_rebalance_executor.py - Standard QMT migration: QMT built-in framework strategy (execution side)

How to load: QMT Strategy Trading -> New Strategy -> select this file -> run (small/paper
account during validation, production account after official switch)
Dependencies: stdlib only + QMT built-in framework APIs (zero third-party deps)

MODE REQUIREMENT (probe-verified 2026-09-01): the strategy MUST be started in
REAL-TIME TRADING mode (panel shows "[trade]start trading mode"). In simulation
mode ("[trade]start simulation mode") framework orders never reach the order
center: engine logs "setQuickPassorderArguments" + "Send Trading Record" but the
"[trade]passOrder: send order to tradeModule" line is missing and NO order is
created (panel/ORDER query empty). In trading mode the full chain works.

Order API facts (probe-verified):
  - passorder(opType, orderType, accountid, orderCode, prType, price, volume
    [, strategyName, quickTrade, userOrderId], ContextInfo): stock opType 23=buy
    24=sell; orderType 1101=shares; prType 11=fixed price / 5=peer / 6=own-side;
    quickTrade=2 fires immediately (proven: buy 000001 + sell 600051 filled).
  - order_shares() is a DEAD path on live bars (quickTrade=0 silently dropped
    by the engine - probe vS2 evidence). NEVER use it.
  - passorder ALWAYS returns 0 even when the order fills -> submission is
    trusted; fill confirmation comes from position polling (wait_for_order_completion)
    + tracker reconcile (same semantics as the old miniQMT system).
  - Account/order APIs are MODULE-LEVEL: get_trade_detail_data(accountID,'STOCK',
    ACCOUNT/POSITION/ORDER/DEAL) returns objects; account total asset = m_dBalance,
    available cash = m_dAvailable; position code = m_strInstrumentID WITHOUT
    suffix (add exchange from m_strExchangeID).
  - Market data via ContextInfo: get_instrument_detail (UpStopPrice/DownStopPrice),
    get_full_tick (dict, 5-level lists). xtdata has NO market service - removed.

Trigger mechanism (trading times fully config-driven, PURE DAILY TIMERS):
  - ContextInfo.schedule_run is the ONLY trigger source (no handlebar
    dependency, no polling). The panel classifies this script as
    timer-driven (doRun m_drType:3). ContextInfo.run_time was ABANDONED: its
    startTime requires a full "YYYY-MM-DD HH:MM:SS" timestamp and a bare
    "HH:MM" startTime never fires (09-01 night / 09-02 all day / 09-03 13:10
    anchor evidence; see QMT_STDQMT_MIGRATION_PLAN.md sec13.7-13/14).
    schedule_run callback dispatch in drType:3 is pending the 2026-09-03
    manual in-session test (sec14.4-8).
  - Per (strategy, trading_time): schedule_run(exec_on_time, next_future
    HH:MM, -1, 1 day). A PAST time_point fires IMMEDIATELY, so trading
    anchors are ALWAYS the next future occurrence (today if still ahead,
    else tomorrow) - never a past time.
  - At the registered time exec_on_time fires and the strategy flow runs
    (consume today's rebalance file -> trade -> tracker). Email/AI steps are
    guaranteed finished before executor time (files ready at trigger), so NO
    recheck/retry/catch-up machinery exists; a missing file simply skips
    the round ("no file pending for today") and the next round diffs.
  - run_now=true (config): executes the full flow immediately at init =
    manual execution / pipeline verification. Production must run with
    run_now=false (timed mode).

Processing flow (per strategy): atomic .done rename takeover (failure = already processed,
skip) -> parse (failure = skip + warn, no trading)
  -> query asset/positions -> cash allocation/reserve/threshold/target calculation -> diff
  -> limit-up/down check -> passorder -> confirm fills (position polling)
  -> update tracker. Order failures are only logged; next session/next day diff recomputes and fills.
"""

import os
import json
import time
import logging
import datetime

# ==================== Deployment constants (confirm once per install location) ====================
# NOTE: no __file__ inside the QMT framework (strategy source runs as <string>),
# so SCRIPT_DIR is hardcoded like the config path.
SCRIPT_DIR = r"C:\Users\comet\git\jq\chan_py\strat"
NEW_CONFIG_PATH = r"C:\Users\comet\git\jq\chan_py\strat\qmt_stdqmt_config.json"
ORDER_WAIT_TIMEOUT = 30          # order fill confirmation polling timeout (seconds)


# ==================== Custom exceptions ====================
class MarketDataException(Exception):
    pass


def _field(row, name, default=0.0):
    """Read a field from a framework object (attribute) or dict, whichever the API returns."""
    try:
        v = getattr(row, name, None)
    except Exception:
        v = None
    if v is None:
        try:
            v = row.get(name, default)
        except Exception:
            return default
    return v


def _tick_val(row, field, fallback=0.0):
    """Read a tick field that may be a 5-level list (take level 1) or a scalar."""
    try:
        v = _field(row, field, [0])
        if isinstance(v, (list, tuple)) and v:
            return float(v[0])
        return float(v)
    except Exception:
        return fallback


# ==================== Market data utilities (ContextInfo APIs, no xtdata) ====================
class MarketUtils:
    _cache = {}

    def __init__(self, ctx):
        self.ctx = ctx

    def get_limit_price(self, code, limit_type='high_limit'):
        cache_key = f"{code}_{limit_type}_{time.strftime('%Y%m%d')}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        detail = self.ctx.get_instrument_detail(code)
        if detail is None:
            raise MarketDataException(f"cannot get limit price details for {code}")
        price = _tick_val(detail, 'UpStopPrice' if limit_type == 'high_limit' else 'DownStopPrice', 0.0)
        if price > 0:
            self._cache[cache_key] = price
            return price
        raise MarketDataException(f"invalid {limit_type} price for {code}: {price}")

    def is_limit_status(self, code, limit_type='high_limit', tolerance=0.001):
        try:
            limit_price = self.get_limit_price(code, limit_type)
            if limit_price <= 0:
                return False
            tick = self.ctx.get_full_tick([code])
            row = tick.get(code) if tick else None
            if not row:
                return False
            current = _tick_val(row, 'lastPrice', 0.0)
            if current <= 0:
                return False
            return abs(current - limit_price) < tolerance
        except Exception as e:
            logging.warning(f"error checking limit status for {code}: {e}")
            return False

    @staticmethod
    def round_to_tick(price, tick=0.01):
        return round(price / tick) * tick


# ==================== Framework adapter layer (probe-verified fields/APIs) ====================
class Position:
    def __init__(self, stock_code, volume, market_value, can_use_volume=0):
        self.stock_code = stock_code
        self.volume = volume
        self.market_value = market_value
        self.can_use_volume = can_use_volume


class Asset:
    def __init__(self, total_asset, cash):
        self.total_asset = total_asset
        self.cash = cash


class FrameworkAdapter:
    """Adapter for QMT built-in framework: module-level get_trade_detail_data + passorder.
    Field names/signatures probe-verified (2026-09-01)."""

    ASSET_FIELD_TOTAL = "m_dBalance"      # ~total asset (probe: balance ~= cash + stock value)
    ASSET_FIELD_CASH = "m_dAvailable"     # available cash (probe-verified)
    POS_FIELD_CODE = "m_strInstrumentID"
    POS_FIELD_VOLUME = "m_nVolume"
    POS_FIELD_CANUSE = "m_nCanUseVolume"
    POS_FIELD_MARKETVALUE = "m_dMarketValue"
    POS_FIELD_EXCHANGE = "m_strExchangeID"

    PRTYPE_FIX = 11          # fixed price
    PRTYPE_PEER = 5          # peer (opponent) price
    ORDER_TYPE_SHARES = 1101

    def __init__(self, ctx, account_id):
        self.ctx = ctx
        self.account_id = account_id
        self._seq = 0

    def _uid(self):
        self._seq += 1
        return f"x{self._seq}"

    def _suffixed(self, inst, exchange):
        if "." in inst:
            return inst
        return f"{inst}.{exchange}" if exchange else inst

    def query_asset(self):
        data = get_trade_detail_data(self.account_id, 'STOCK', 'ACCOUNT')
        if not data:
            return None
        row = data[0] if isinstance(data, (list, tuple)) else data
        return Asset(
            total_asset=float(_field(row, self.ASSET_FIELD_TOTAL, 0.0)),
            cash=float(_field(row, self.ASSET_FIELD_CASH, 0.0)),
        )

    def query_positions(self):
        data = get_trade_detail_data(self.account_id, 'STOCK', 'POSITION')
        positions = {}
        for row in data or []:
            volume = int(_field(row, self.POS_FIELD_VOLUME, 0))
            if volume <= 0:
                continue
            inst = str(_field(row, self.POS_FIELD_CODE, ''))
            if not inst:
                continue
            exchange = str(_field(row, self.POS_FIELD_EXCHANGE, ''))
            positions[self._suffixed(inst, exchange)] = Position(
                stock_code=self._suffixed(inst, exchange),
                volume=volume,
                market_value=float(_field(row, self.POS_FIELD_MARKETVALUE, 0.0)),
                can_use_volume=int(_field(row, self.POS_FIELD_CANUSE, volume)),
            )
        return positions

    def place_order(self, code, volume, price, is_buy, remark=""):
        """Submit via passorder(quickTrade=2). Framework passorder ALWAYS returns 0
        even when the order fills, so submission is trusted and fill confirmation
        comes from position polling (wait_for_order_completion) + tracker reconcile.
        Returns True (submitted) or None (skipped / exception)."""
        if volume <= 0:
            return None
        try:
            op_type = 23 if is_buy else 24
            if price and price > 0:
                pr_type = self.PRTYPE_FIX
                order_price = price
            else:
                pr_type = self.PRTYPE_PEER
                order_price = 0
            uid = self._uid()
            passorder(op_type, self.ORDER_TYPE_SHARES, self.account_id, code,
                      pr_type, order_price, volume,
                      (remark or "executor")[:32], 2, uid, self.ctx)
            logging.info(f"{'Buy' if is_buy else 'Sell'} {code} {volume}sh @ "
                         f"{order_price or 'peer'} ({remark}) submitted uid={uid}")
            return True
        except Exception as e:
            logging.error(f"order exception {code}: {e}")
            return None


# ==================== Cash allocation (as-is) ====================
def calculate_cash_allocation(strat, total_asset, cash):
    reserve = total_asset * strat["cash_reserve_ratio"]
    available_cash = cash - reserve
    return reserve, max(available_cash, 0)


# ==================== Strategy position tracking (migrated in full) ====================
class StrategyPositionTracker:
    def __init__(self, tracking_file):
        self.tracking_file = tracking_file
        self.data = self._load()

    def _load(self):
        if not os.path.exists(self.tracking_file):
            return {}
        try:
            with open(self.tracking_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            data = {}
            for k, v in raw.items():
                if k == 'last_updated':
                    continue
                if isinstance(v, dict):
                    data[k] = {code: int(vol) for code, vol in v.items() if int(vol) > 0}
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"position tracking file corrupted, re-initializing: {e}")
            return {}

    def save(self):
        output = {"last_updated": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        output.update(self.data)
        tmp_file = self.tracking_file + '.tmp'
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        os.replace(tmp_file, self.tracking_file)

    def get_positions(self, strategy_name):
        return dict(self.data.get(strategy_name, {}))

    def update_position(self, strategy_name, code, volume):
        if strategy_name not in self.data:
            self.data[strategy_name] = {}
        if volume <= 0:
            self.data[strategy_name].pop(code, None)
        else:
            self.data[strategy_name][code] = int(volume)

    def get_tracked_volume(self, code):
        return sum(pos.get(code, 0) for pos in self.data.values())

    def get_strategies_holding(self, code):
        return [name for name, positions in self.data.items() if positions.get(code, 0) > 0]

    def sync_with_broker(self, broker_positions, strategy_names, strategy_configs=None):
        for name in strategy_names:
            if name not in self.data:
                self.data[name] = {}
        for strat_name in strategy_names:
            to_remove = [code for code in self.data.get(strat_name, {}) if code not in broker_positions]
            for code in to_remove:
                vol = self.data[strat_name].pop(code)
                logging.warning(f"reconcile: {strat_name}'s {code}({vol}sh) not in broker, removed")
        all_tracked = set()
        for pos in self.data.values():
            all_tracked.update(pos.keys())
        for code, pos in broker_positions.items():
            if code not in all_tracked:
                if strategy_configs:
                    try:
                        max_ratio_strat = max(strategy_configs, key=lambda s: s['capital_ratio'])['name']
                        self.data[max_ratio_strat][code] = pos.volume
                        logging.warning(f"reconcile: {code}({pos.volume}sh) untracked, "
                                        f"assigned to '{max_ratio_strat}'")
                    except Exception as e:
                        self.data[strategy_names[0]][code] = pos.volume
                        logging.warning(f"reconcile: assigning {code} failed {e}, "
                                        f"temporarily assigned to '{strategy_names[0]}'")
                else:
                    self.data[strategy_names[0]][code] = pos.volume
                    logging.warning(f"reconcile: {code}({pos.volume}sh) untracked, "
                                    f"temporarily assigned to '{strategy_names[0]}'")
        for code, pos in broker_positions.items():
            tracked_total = self.get_tracked_volume(code)
            if tracked_total == pos.volume:
                continue
            holders = self.get_strategies_holding(code)
            if len(holders) == 1:
                old = self.data[holders[0]][code]
                self.data[holders[0]][code] = pos.volume
                logging.info(f"reconcile: {code} '{holders[0]}' corrected {old} -> {pos.volume}")
            elif len(holders) == 0:
                self.data[strategy_names[0]][code] = pos.volume
            else:
                logging.error(
                    f"reconcile: {code} held by {holders}, "
                    f"tracked={tracked_total} != broker={pos.volume}, manual correction needed")


# ==================== Account status (strategy scope, via adapter) ====================
def get_account_status(context):
    adapter = context['adapter']
    strat = context['current_strategy']
    tracker = context['position_tracker']

    asset = adapter.query_asset()
    if asset is None:
        raise Exception("failed to query asset")
    broker_positions = adapter.query_positions()

    if not context.get('_sync_done'):
        strategy_names = [s['name'] for s in context['strategy_configs']]
        tracker.sync_with_broker(broker_positions, strategy_names, context['strategy_configs'])
        context['_sync_done'] = True

    tracked = tracker.get_positions(strat['name'])
    strategy_positions = {}
    strategy_position_value = 0.0
    for code in tracked:
        if code in broker_positions:
            strategy_positions[code] = broker_positions[code]
            strategy_position_value += broker_positions[code].market_value

    total_asset = asset.total_asset
    strategy_total = total_asset * strat['capital_ratio']
    strategy_cash_quota = asset.cash * strat['capital_ratio']
    strategy_cash_needed = strategy_total - strategy_position_value
    strategy_cash = max(min(strategy_cash_needed, strategy_cash_quota), 0)

    context.update({
        'broker_total_asset': total_asset,
        'broker_cash': asset.cash,
        'total_asset': strategy_total,
        'cash': strategy_cash,
        'positions': strategy_positions,
        'broker_positions': broker_positions,
    })
    logging.info(
        f"[{strat['name']}] account total asset: {total_asset:.2f}, "
        f"strategy quota: {strategy_total:.2f}, available: {strategy_cash:.2f}, "
        f"positions: {len(strategy_positions)}")


# ==================== Shared holdings share (migration fix) ====================
def _my_share(tracker, strat_name, code, pos):
    """This strategy's share in the broker position = broker total - other strategies'
    tracked volume."""
    current = tracker.get_positions(strat_name).get(code, 0)
    if current <= 0:
        return 0
    other_vol = tracker.get_tracked_volume(code) - current
    return max(pos.volume - other_vol, 0)


# ==================== Tracker update helpers (as-is) ====================
def _update_tracker_after_trade(context, codes):
    strat = context['current_strategy']
    tracker = context['position_tracker']
    broker_positions = context['broker_positions']
    for code in codes:
        broker_pos = broker_positions.get(code)
        if broker_pos is None or broker_pos.volume == 0:
            tracker.update_position(strat['name'], code, 0)
        else:
            current_vol = tracker.get_positions(strat['name']).get(code, 0)
            other_vol = tracker.get_tracked_volume(code) - current_vol
            my_new = max(broker_pos.volume - other_vol, 0)
            tracker.update_position(strat['name'], code, my_new)
            logging.debug(f"[{strat['name']}] tracker update: {code} current={current_vol}, "
                          f"others={other_vol}, broker={broker_pos.volume}, new={my_new}")


# ==================== Order waiting (polls positions via adapter, 30s timeout) ====================
def _log_order_status(context, codes):
    try:
        data = get_trade_detail_data(context['adapter'].account_id, 'STOCK', 'ORDER') or []
        for code in codes:
            base = code.split('.')[0]
            rows = [o for o in data if str(_field(o, 'm_strInstrumentID', '')) == base]
            if rows:
                statuses = [f"sysid={_field(o, 'm_strOrderSysID', '')} "
                            f"status={_field(o, 'm_nOrderStatus', '')}"
                            for o in rows[-3:]]
                logging.warning(f"[{context['current_strategy']['name']}] order status for "
                                f"{code}: {statuses}")
    except Exception as e:
        logging.warning(f"order status query failed: {e}")


def wait_for_order_completion(context, affected_codes, initial_positions, timeout=ORDER_WAIT_TIMEOUT):
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(1)
        new_positions = context['adapter'].query_positions()
        for code in affected_codes:
            old_vol = initial_positions[code].volume if code in initial_positions else 0
            new_vol = new_positions[code].volume if code in new_positions else 0
            if old_vol != new_vol:
                return new_positions
    _log_order_status(context, affected_codes)
    return None


# ==================== Trading actions (cash algorithm as-is, orders via adapter; includes shared-holdings sell fix) ====================
def sell_out_of_pool(context):
    strat = context['current_strategy']
    tracker = context['position_tracker']
    positions = context['positions']
    candidate = context['candidate_pool']

    sell_codes = []
    for code, pos in positions.items():
        if code not in candidate:
            if not context['market'].is_limit_status(code, 'high_limit'):
                vol = _my_share(tracker, strat['name'], code, pos)
                if vol > 0:
                    oid = place_sell_order(context, code, vol, f"sell_out_{strat['name']}")
                    if oid:
                        sell_codes.append(code)

    if sell_codes:
        new_pos = wait_for_order_completion(context, sell_codes, context['broker_positions'])
        if new_pos is not None:
            context['broker_positions'] = new_pos
            _update_tracker_after_trade(context, sell_codes)
        else:
            logging.warning(f"[{strat['name']}] sell wait timed out")

    get_account_status(context)


def _calculate_rebalance_targets(strat, total_asset):
    reserve = total_asset * strat["cash_reserve_ratio"]
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / strat["max_holdings"]
    return reserve, cash_for_stocks, target_per_stock


def rebalance(context):
    strat = context['current_strategy']
    tracker = context['position_tracker']
    positions = context['positions']
    total_asset = context['total_asset']

    reserve, cash_for_stocks, target_per_stock = _calculate_rebalance_targets(strat, total_asset)

    # --- sell over-allocated (per this strategy's share) ---
    sell_codes = []
    for code, pos in positions.items():
        share_vol = _my_share(tracker, strat['name'], code, pos)
        if share_vol <= 0:
            continue
        share_value = pos.market_value * (share_vol / pos.volume) if pos.volume else 0.0
        if share_value > target_per_stock:
            if not context['market'].is_limit_status(code, 'high_limit'):
                value_sell = share_value - target_per_stock
                price = share_value / share_vol
                vol_sell = int(value_sell // (price * 100)) * 100
                vol_sell = min(vol_sell, share_vol // 100 * 100)
                if vol_sell > 0:
                    oid = place_sell_order(context, code, vol_sell, f"rb_sell_{strat['name']}")
                    if oid:
                        sell_codes.append(code)

    if sell_codes:
        new_pos = wait_for_order_completion(context, sell_codes, context['broker_positions'])
        if new_pos is not None:
            context['broker_positions'] = new_pos
            _update_tracker_after_trade(context, sell_codes)
        else:
            logging.warning(f"[{strat['name']}] rebalance sell timed out")

    get_account_status(context)

    # --- buy under-allocated (per this strategy's share) ---
    total_asset = context['total_asset']
    positions = context['positions']
    available_cash = context['cash']
    reserve, cash_for_stocks, target_per_stock = _calculate_rebalance_targets(strat, total_asset)

    buy_codes = []
    for code, pos in positions.items():
        share_vol = _my_share(tracker, strat['name'], code, pos)
        share_value = pos.market_value * (share_vol / pos.volume) if pos.volume else 0.0
        if share_value < target_per_stock:
            if not context['market'].is_limit_status(code, 'low_limit'):
                value_buy = target_per_stock - share_value
                buy_price, vol_buy = calculate_trade_price_and_volume(context, code, value_buy, available_cash, is_buy=True)
                if vol_buy > 0 and buy_price is not None:
                    oid = place_buy_order(context, code, vol_buy, buy_price, f"rb_buy_{strat['name']}")
                    if oid:
                        buy_codes.append(code)
                        available_cash -= vol_buy * buy_price * 1.001
                else:
                    logging.info(f"[{strat['name']}] cannot compute buy price/volume for {code}, skip")

    if buy_codes:
        new_pos = wait_for_order_completion(context, buy_codes, context['broker_positions'])
        if new_pos is not None:
            context['broker_positions'] = new_pos
            _update_tracker_after_trade(context, buy_codes)

    get_account_status(context)


def check_rebalance_and_execute(context):
    strat = context['current_strategy']
    positions = context['positions']
    total_asset = context['total_asset']
    cash = context['cash']

    slots = strat["max_holdings"] - len(positions)
    if slots <= 0:
        return
    reserve, cash_for_buy = calculate_cash_allocation(strat, total_asset, cash)
    if cash_for_buy <= 0:
        return
    avg_alloc = cash_for_buy / slots
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / strat["max_holdings"]
    deviation = abs(avg_alloc - target_per_stock) / target_per_stock if target_per_stock > 0 else 0
    if deviation > strat["rebalance_threshold"]:
        logging.info(f"[{strat['name']}] rebalance triggered: deviation {deviation:.1%}")
        rebalance(context)


def buy_to_fill(context):
    strat = context['current_strategy']
    positions = context['positions']
    buy_pool = context['buy_pool']
    total_asset = context['total_asset']
    cash = context['cash']

    current_codes = set(positions.keys())
    slots = strat["max_holdings"] - len(current_codes)
    if slots <= 0:
        return
    _, buy_cash = calculate_cash_allocation(strat, total_asset, cash)
    if buy_cash <= 0:
        logging.warning(f"[{strat['name']}] insufficient available cash")
        return
    candidates = [c for c in buy_pool if c not in current_codes][:slots]
    if not candidates:
        return
    per_stock = buy_cash / slots
    available_cash = buy_cash

    buy_codes = []
    for code in candidates:
        buy_price, vol = calculate_trade_price_and_volume(context, code, per_stock, available_cash, is_buy=True)
        if vol > 0 and buy_price is not None:
            oid = place_buy_order(context, code, vol, buy_price, f"buy_{strat['name']}")
            if oid:
                logging.info(f"[{strat['name']}] Buy {code}: {vol}sh @ {buy_price:.2f}")
                buy_codes.append(code)
                available_cash -= vol * buy_price * 1.001
        else:
            logging.info(f"[{strat['name']}] Skipping {code}")

    if buy_codes:
        new_pos = wait_for_order_completion(context, buy_codes, context['broker_positions'])
        if new_pos is not None:
            context['broker_positions'] = new_pos
            _update_tracker_after_trade(context, buy_codes)

    get_account_status(context)


# ==================== Price & order placement (migrated as-is, orders via adapter) ====================
def calculate_trade_price_and_volume(context, code, target_amount, available_cash, is_buy=True):
    if is_buy:
        limit_type = 'high_limit'
        price_field = 'askPrice'
        cage_multiplier = 1.02
        cage_offset = 0.1
        compare_func = min
        operation = "buy"
    else:
        limit_type = 'low_limit'
        price_field = 'bidPrice'
        cage_multiplier = 0.98
        cage_offset = -0.1
        compare_func = max
        operation = "sell"

    market = context['market']
    limit_price = market.get_limit_price(code, limit_type)
    if limit_price <= 0:
        logging.warning(f"Cannot get {limit_type} price for {code}, skip")
        return (None, 0) if is_buy else None

    try:
        tick = market.ctx.get_full_tick([code])
        row = tick.get(code) if tick else None
        if row is None:
            logging.warning(f"Cannot get tick data for {code}")
            return (None, 0) if is_buy else None

        market_price = _tick_val(row, price_field, 0.0)
        if market_price <= 0:
            logging.info(f"stock {code} {price_field} is 0 ({operation} state), "
                         f"ordering at {limit_type} {limit_price:.2f}")
            final_price = limit_price
        else:
            cage_limit = compare_func(market_price * cage_multiplier, market_price + cage_offset)
            final_price = compare_func(cage_limit, limit_price)
        final_price = market.round_to_tick(final_price)

        if is_buy:
            safety_factor = 0.99
            max_amount = min(target_amount, available_cash) * safety_factor
            volume = int(max_amount // (final_price * 100)) * 100
            if volume <= 0:
                logging.info(f"Insufficient funds to buy one lot of {code}")
                return None, 0
            return final_price, volume
        else:
            return final_price
    except Exception as e:
        logging.error(f"Error calculating {operation} price for {code}: {e}")
        return (None, 0) if is_buy else None


def place_sell_order(context, code, volume, remark=""):
    if volume <= 0:
        return None
    sell_price = calculate_trade_price_and_volume(context, code, 0, 0, is_buy=False)
    if sell_price is None:
        logging.warning(f"cannot compute sell price for {code}, falling back to peer price")
        return context['adapter'].place_order(code, volume, 0, False, remark)
    return context['adapter'].place_order(code, volume, sell_price, False, remark)


def place_buy_order(context, code, volume, price=None, remark=""):
    if volume <= 0:
        return None
    return context['adapter'].place_order(code, volume, price, True, remark)


# ==================== Execution engine ====================
class RebalanceEngine:
    def __init__(self, ctx):
        self.ctx = ctx
        self.new_cfg, self.strategies, self.tracker, self.adapter = self._load_and_prepare()
        # MANDATORY: bind the trading account. The engine only enters trading mode
        # (bindTradeCallBackFunc -> data subscription -> replay -> live bars) after
        # set_account; without it handlebar never runs (probe-verified 2026-09-01).
        try:
            ctx.set_account(self.adapter.account_id, 'STOCK')
            logging.info(f"set_account({self.adapter.account_id}, 'STOCK') OK")
        except Exception as e:
            logging.error(f"set_account failed: {e}")
        self.market = MarketUtils(ctx)
        self.exchange_path = self._resolve(self.new_cfg.get("exchange_path", "qmt_exchange"))
        self.run_now = bool(self.new_cfg.get("run_now", False))

    def _resolve(self, path):
        if os.path.isabs(path):
            return path
        return os.path.join(SCRIPT_DIR, path)

    def _load_and_prepare(self):
        with open(NEW_CONFIG_PATH, encoding='utf-8') as f:
            new_cfg = json.load(f)

        # config validation (capital_ratio sum, trading_times format)
        strategies = new_cfg['strategies']
        total_ratio = sum(s['capital_ratio'] for s in strategies)
        if abs(total_ratio - 1.0) > 0.0001:
            raise ValueError(f"sum of capital_ratio ({total_ratio:.4f}) must equal 1.0 (+/-0.0001)")
        for s in strategies:
            if s['capital_ratio'] <= 0:
                raise ValueError(f"capital_ratio of strategy '{s['name']}' must be > 0")
            if 'trading_times' not in s:
                s['trading_times'] = ["09:35"]
            if not isinstance(s['trading_times'], list):
                raise ValueError(f"trading_times of strategy '{s['name']}' must be a list")
            for t in s['trading_times']:
                if not isinstance(t, str) or len(t) != 5 or t[2] != ':':
                    raise ValueError(f"bad trading time format for strategy '{s['name']}': {t}")
                try:
                    hour, minute = int(t[:2]), int(t[3:])
                    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                        raise ValueError
                except ValueError:
                    raise ValueError(f"invalid trading time for strategy '{s['name']}': {t}")

        # absolutize paths (exchange_path / position_tracking_file / executor_log_file)
        tracking_file = self._resolve(new_cfg.get("position_tracking_file", "strategy_positions.json"))
        log_file = self._resolve(new_cfg.get("executor_log_file", "logs/qmt_executor.log"))
        self._setup_logging(log_file)

        tracker = StrategyPositionTracker(tracking_file)
        adapter = FrameworkAdapter(self.ctx, new_cfg["account_id"])
        logging.info(f"config loaded: {len(strategies)} strategies, tracker={tracking_file}")
        return new_cfg, strategies, tracker, adapter

    def _setup_logging(self, log_file):
        os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)
        logger = logging.getLogger()
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_file)
                   for h in logger.handlers):
            fh = logging.FileHandler(log_file, encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(fh)

    def start(self):
        self._register_triggers()
        if self.run_now:
            logging.warning("run_now=true: executing full flow in init context "
                            "(manual execution / pipeline verification). Set "
                            "run_now=false for production timed mode.")
            self.manual_execute()
        else:
            logging.info("executor starting in timed mode (daily tasks "
                         "registered; no polling)")

    def _register_triggers(self):
        # Timer mechanism (2026-09-03): ContextInfo.run_time with a bare "HH:MM"
        # startTime NEVER fires in this client - fun.xml requires a full
        # "YYYY-MM-DD HH:MM:SS" startTime, so the bare-time task never resolves
        # (09-01 night / 09-02 all day / 09-03 13:10 anchor evidence; see
        # QMT_STDQMT_MIGRATION_PLAN.md sec13.7-13/14). The mature API is
        # ContextInfo.schedule_run(func, time_point, repeat_times, interval,
        # name):
        #   - time_point: datetime (a PAST time_point fires IMMEDIATELY, so
        #     trading anchors must always be the NEXT FUTURE occurrence)
        #   - repeat_times=-1: repeat forever until cancel_schedule_run
        #   - interval: datetime.timedelta between repeats
        #   - returns a unique task seq (logged; proves registration reached C++)
        # One daily task per (strategy, trading_time): at the registered time
        # exec_on_time fires and the flow runs. No recheck/poll/catch-up tasks.
        now = datetime.datetime.now()
        for strat in self.strategies:
            for t in strat['trading_times']:
                try:
                    hour, minute = int(t[:2]), int(t[3:])
                    first = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if first <= now:
                        first += datetime.timedelta(days=1)
                    seq = self.ctx.schedule_run(exec_on_time, first, -1,
                                                datetime.timedelta(days=1),
                                                f"{strat['name']}_{t}")
                    logging.info(f"daily task registered {t} [{strat['name']}] "
                                 f"first={first:%Y-%m-%d %H:%M:%S} seq={seq}")
                except Exception as e:
                    logging.error(f"schedule_run daily registration failed {t}: {e}")

    def manual_execute(self):
        logging.info("manual execution: processing all strategies now "
                     "(run_now=true entry)")
        for strat in self.strategies:
            try:
                self._process_strategy(strat)
            except Exception as e:
                logging.exception(f"[{strat['name']}] execution exception: {e}")

    def exec_on_time(self):
        current = datetime.datetime.now().strftime("%H:%M")
        for strat in self.strategies:
            for t in strat['trading_times']:
                if t == current:
                    try:
                        self._process_strategy(strat)
                    except Exception as e:
                        logging.exception(f"[{strat['name']}] processing exception: {e}")

    def _latest_unprocessed_file(self, strat_name):
        today = datetime.date.today().strftime("%Y%m%d")
        prefix = f"rebalance_{strat_name}_{today}"
        best = None
        if not os.path.isdir(self.exchange_path):
            return None
        for fn in os.listdir(self.exchange_path):
            if fn.startswith(prefix) and fn.endswith(".json"):
                if best is None or fn > best:
                    best = fn
        return os.path.join(self.exchange_path, best) if best else None

    def _process_strategy(self, strat):
        """Find and process the latest unprocessed file of the day for this strategy.
        Return True = file present (taken over/processed)."""
        name = strat['name']
        f = self._latest_unprocessed_file(name)
        if f is None:
            logging.info(f"[{name}] no file pending for today")
            return False
        done_path = f + '.done'
        try:
            os.replace(f, done_path)  # atomic takeover: rename failure = already processed
        except FileNotFoundError:
            logging.info(f"[{name}] {os.path.basename(f)} already processed, skip")
            return True
        try:
            with open(done_path, encoding='utf-8') as fh:
                data = json.load(fh)
            stocks = list(data.get('stocks') or [])
        except Exception as e:
            logging.error(f"[{name}] failed to parse {os.path.basename(done_path)}: {e} "
                          f"-> skip this round (no trading)")
            return True
        logging.info(f"[{name}] processing {os.path.basename(done_path)} ({len(stocks)} stocks)")
        self._execute_strategy(strat, stocks)
        return True

    def _execute_strategy(self, strat, stocks):
        context = {
            'current_strategy': strat,
            'strategy_configs': self.strategies,
            'position_tracker': self.tracker,
            'adapter': self.adapter,
            'market': self.market,
            '_sync_done': False,
        }
        candidate_size = strat.get('candidate_pool_size', len(stocks))
        max_holdings = strat.get('max_holdings', len(stocks))
        context['candidate_pool'] = stocks[:candidate_size]
        context['buy_pool'] = stocks[:max_holdings]
        logging.info(f"[{strat['name']}] candidate pool: {len(context['candidate_pool'])} stocks, "
                     f"buy pool: {len(context['buy_pool'])} stocks")
        try:
            get_account_status(context)
            sell_out_of_pool(context)
            check_rebalance_and_execute(context)
            buy_to_fill(context)
        except Exception as e:
            logging.exception(f"[{strat['name']}] rebalance execution exception "
                              f"(order failures only logged; next session/next day diff fills)")
        finally:
            self.tracker.save()


engine = None


def init(ContextInfo):
    global engine
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    try:
        engine = RebalanceEngine(ContextInfo)
        engine.start()
    except Exception as e:
        logging.exception(f"executor init failed: {e}")


def exec_on_time(ContextInfo):
    if engine is not None:
        engine.exec_on_time()
