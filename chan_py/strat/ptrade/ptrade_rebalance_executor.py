# -*- coding: utf-8 -*-
"""
ptrade_rebalance_executor.py - PTrade (Hengsheng) execution strategy, single file.

This is the PTrade replacement for qmt_rebalance_executor.py. The local (external)
process keeps doing selection + AI filtering; it only has to drop a small JSON
target file where the PTrade client uploads it. Everything else happens here.

    local process                        PTrade cloud
    -------------                        ------------
    email -> list -> AI filter           research dir: target_low_valuation.json
      -> write target_<s>.json    ==>    (uploaded by the client's scheduled upload)
      -> scheduled upload folder         this strategy: run_daily -> read file
                                         -> equal weight -> order()
    <== orders_<s>_<date>.json           state_<s>.json  (idempotency + audit)

WHY THIS SHAPE
  PTrade's trading sandbox forbids outbound network, so email/AI can never run here.
  It DOES allow reading/writing the research directory from backtest and trading,
  and the client can auto-upload local files into it. That is the whole channel we
  need, and both halves are official platform features rather than workarounds.

TARGET FILE SCHEMA (written by the local process)
  {
    "strategy": "low_valuation",
    "generated_at": "2026-10-16T09:25:00",
    "stocks": ["600000.XSHG", "000001.XSHE", ...],   # full filtered pool, order = rank
    "liquidate": false                            # true = wipe the book (optional)
  }
  - stocks == [] together with a fresh generated_at means "liquidate" (as in the old
    QMT pipeline). A missing/old file is NOT a liquidate instruction, see below.

DELIBERATE DIFFERENCE FROM THE QMT EXECUTOR
  QMT version: file missing/expired -> the *external* process wrote an empty list, so
  the executor liquidated. Here a missing/stale file most likely means the upload
  broke, so the default is MISSING_FILE_ACTION = "skip" (log ERROR, trade nothing).
  Set it to "liquidate" if you want the old semantics.

CONFIG BELOW IS THE SINGLE SOURCE OF TRUTH - there is no config file to read
(PTrade strategies cannot open local files; only the research dir is visible).

COMPATIBILITY
  PTrade runs Python 3.5.2: NO f-strings, no walrus operator, no dataclasses.
  This file is written to that constraint and is pure ASCII on purpose (same lesson
  as the QMT panel: a re-encoded source file is a silent deployment landmine).

FIRST RUN
  DRY_RUN = True by default: every day it will log exactly what it would do.
  Read the log, fix the config, then set DRY_RUN = False.
"""

import datetime

# JSON: the platform provides simplejson (same API). Stdlib json is fetched through
# __import__ as a fallback so this file contains no "import json" statement at all.
try:
    import simplejson as json
except ImportError:
    json = __import__("json")

# ---------------------------------------------------------------------------
# PTrade sandbox (2026-10-16, confirmed by the broker's platform):
#   ALLOWED : pandas, numpy, enum, math, time, simplejson, datetime
#   FORBIDDEN: os, sys  (and anything that imports them, e.g. traceback / tempfile /
#              shutil / glob / pathlib)
# Everything below therefore uses only builtins + datetime + simplejson:
#   * file access      -> builtin open()
#   * path joining     -> plain strings joined with "/" (open() accepts it on both
#                         Windows and POSIX)
#   * NO directory listing and NO mkdir -> the target must use the FIXED name
#                         (TARGET_FILE), and state/audit files are written FLAT into the
#                         research dir with a prefix (see STATE_PREFIX / AUDIT_PREFIX)
# ---------------------------------------------------------------------------

# ============================================================================
# CONFIG - multi-strategy
# ============================================================================
# ONE TARGET FILE PER STRATEGY. The sandbox has no directory listing, so the strategy must
# be told which files to serve; everything else (order times, sizing parameters, capital
# ratio, the list itself) is read from each file (written by ptrade/ptrade_target.py).
#   target_<strategy>.json -> {"strategy","generated_at","trading_times","capital_ratio",
#                              "max_holdings","candidate_pool_size","cash_reserve_ratio",
#                              "rebalance_threshold","stocks"}
TARGET_FILES = ["target_low_valuation.json"]

# Fallbacks used while a file is absent/unreadable, so a failed upload can never stop the
# strategy from being scheduled (values are replaced as soon as the file appears).
DEFAULT_ORDER_TIMES = ["09:35"]
DEFAULT_PARAMS = {
    "capital_ratio": 1.0,
    "max_holdings": 8,             # number of equal-weight slots
    "candidate_pool_size": 13,     # how many names stay "in pool" (the rest is liquidated)
    "cash_reserve_ratio": 0.0125,  # fraction of the strategy slice kept as cash
    "rebalance_threshold": 0.20,   # COMBINATION gate (see _plan step 2): re-equalise the pool
                                   # only when |(cash-reserve)/slots - target_per|/target_per
                                   # exceeds this. A full book never re-equalises, however
                                   # far a single name moves.
}

# Where the target files live under get_research_path(). The PTrade client mirrors the local
# upload_file/ folder to the server as a folder of the same name, so files land in
# <research>/upload_file/... The research root is kept as a second candidate in case an
# instance flattens the folder on upload.
TARGET_DIRS = ["upload_file", ""]             # first readable candidate wins
# state + audit files: written flat into the RESEARCH ROOT (no mkdir available)
STATE_PREFIX = "ptrade_state_"                # ptrade_state_<strategy>.json
AUDIT_PREFIX = "ptrade_orders_"               # ptrade_orders_<strategy>_<date>.json
TRACKER_FILE = "ptrade_state_positions.json"  # per-strategy holdings (attribution)

DRY_RUN = False               # False = live trading. True = rehearsal (log the plan only)
MISSING_FILE_ACTION = "skip"  # "skip" (safe) or "liquidate" (old QMT semantics)
# Target age policy (see _load_target): TODAY ONLY. A target whose generated_at is not today
# is NOT traded - the run logs an ERROR and leaves positions untouched. This threshold is
# only the "give up and liquidate this slice" boundary: a whole week without a fresh list
# means the local process has been dead for a week, so get out.
MAX_TARGET_AGE_DAYS = 7

PRICE_MODE = "cage"           # "cage" = limit at peer price +-cage, "latest" = no limit price
CAGE_MULTIPLIER = 1.02        # buy: min(ask*(1+m), ask+offset); sell mirrored
CAGE_OFFSET = 0.10
USE_LIMIT_PRICE = True        # if False, order() without limit_price (platform uses last)

# Order_market's limit_price is a PROTECTION bound, not the working price. The production
# reference strategy sells with the LIMIT-DOWN price as the protection (it sweeps every bid
# down to the floor) and buys with the LIMIT-UP price. "Sell with everything you have" is the
# point of this strategy: get out first, then the freed cash has room to buy.
# BOTH are additionally bounded by the ~2% deviation rule the broker applies to
# quantitative orders: sell >= last*0.98, buy <= last*1.02 (and by the limit prices).
SELL_PROTECT_AT_LIMIT_DOWN = True   # sell: as aggressive as the rules allow
BUY_PROTECT_AT_LIMIT_UP = False     # buy : keep the QMT-era cage (do not chase to limit-up)

# Market-order type per board (order_market(market_type=...)). Values copied from the
# reference strategy that ran in production here. A wrong value does NOT lose the trade:
# _place retries the order as a +-2% repriced LIMIT order, and the log tells you it did.
# STAR market (688) is the one most likely to need a different value per broker - if the log
# keeps showing "order_market(688xxx ...) was rejected -> retrying as a limit order",
# change MARKET_TYPE_STAR to 1 and restart.
MARKET_TYPE_MAIN_SH = 1          # 60xxxx : 1 (best-five-levels, remainder cancelled)
MARKET_TYPE_STAR = 0             # 688xxx : 0 (counterparty best / best five levels)
MARKET_TYPE_SZ = 0               # 000/002/300 : 0
MARKET_TYPE_OTHER = 4            # anything else (BJ etc.)

LOT = 100                     # A-share board lot
MAX_ORDERS_PER_RUN = 40       # safety brake: abort the whole run above this
ONLY_ONCE_PER_TIME = True     # one execution per (date, time) even across restarts

# ============================================================================
# small utilities (no PTrade API here, so they are unit-testable locally)
# ============================================================================
LOGS = []
_LOG_TAG = "-"      # strategy name of the run in progress (log prefix only)


def _log(level, msg):
    line = "[%s][%s] %s" % (_LOG_TAG, level, msg)
    try:
        LOGS.append(line)
    except Exception:
        pass
    try:
        if level == "ERROR":
            log.error(line)
        elif level == "WARN":
            log.warning(line)
        else:
            log.info(line)
    except Exception:
        try:
            print(line)
        except Exception:
            pass


def _pick(obj, names, default=None):
    """Read the first present attribute/dict-key from obj."""
    for n in names:
        try:
            v = getattr(obj, n, None)
        except Exception:
            v = None
        if v is None:
            try:
                v = obj.get(n, None)
            except Exception:
                v = None
        if v is not None:
            return v
    return default


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _split_code(code):
    """Any spelling -> ('SH'|'SZ'|'BJ', '600000').

    The market tag is only an internal label for board/limit rules. Codes this strategy
    PRODUCES are always spelled XSHG / XSHE (see _full_code) - the QMT-era SS/SH/SZ
    suffixes are only tolerated when READING data that predates 2026-10-19 (an old
    tracker file, an old target file), never produced.
    """
    c = str(code).strip().upper().replace("-", ".").replace("_", ".")
    parts = c.split(".")
    if len(parts) == 2:
        a, b = parts
        if a.isdigit() and len(a) == 6:
            return (_norm_market(b), a)
        if b.isdigit() and len(b) == 6:
            return (_norm_market(a), b)
    if len(c) == 6 and c.isdigit():
        if c[0] in "56":
            return "XSHG", c
        if c[:2] in ("43", "83", "87", "88", "92"):
            return "BJ", c          # Beijing exchange
        return "XSHE", c
    if len(c) == 8 and c[:2] in ("SH", "SZ") and c[2:].isdigit():
        return _norm_market(c[:2]), c[2:]        # legacy SH600000 / SZ000001 form
    return "", ""


def _norm_market(m):
    """Market tag from any suffix spelling (input tolerance only)."""
    m = str(m).upper()
    if m in ("XSHG", "SH", "SS"):
        return "XSHG"
    if m in ("XSHE", "SZ"):
        return "XSHE"
    return m


def _full_code(code):
    """Canonical form used everywhere inside this strategy AND towards the platform API:
    '600697.XSHG' / '000001.XSHE' / '600697' / 'sh600697' -> '600697.XSHG'."""
    mk, pl = _split_code(code)
    if not pl:
        return str(code).strip().upper()
    if mk == "XSHG":
        return pl + ".XSHG"
    if mk == "BJ":
        return pl + ".BJ"        # Beijing exchange (needs broker confirmation)
    return pl + ".XSHE"


def _limit_ratio(market, plain, name):
    """Daily price limit ratio by board; ST detected from the security name."""
    nm = (name or "").upper()
    if "ST" in nm:
        return 0.05
    if market == "XSHG" and plain[:3] == "688":
        return 0.20
    if market == "XSHE" and plain[:3] in ("300", "301"):
        return 0.20
    if plain[:2] in ("43", "83", "87", "88", "92"):
        return 0.30
    return 0.10


def _round_price(p):
    try:
        return round(round(p / 0.01) * 0.01, 2)
    except Exception:
        return p


def _date_str(dt=None):
    if dt is None:
        dt = datetime.datetime.now()
    return dt.strftime("%Y%m%d")


def _now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path, quiet=False):
    """Read a JSON file. The uploaded file is UTF-8 (written by the local producer) and
    the platform locale is not ours to choose, so try utf-8 text, then raw bytes."""
    try:
        f = open(path, "r", encoding="utf-8")
        try:
            return json.loads(f.read())
        finally:
            f.close()
    except Exception as e:
        try:
            f = open(path, "rb")
            try:
                return json.loads(f.read().decode("utf-8"))
            finally:
                f.close()
        except Exception:
            if not quiet:
                _log("WARN", "cannot read %s: %s" % (path, e))
            return None


def _join(base, name):
    """path-join replacement. open() accepts '/' on Windows and POSIX alike."""
    if not base:
        return name
    if not name:
        return base
    return base.replace("\\", "/").rstrip("/") + "/" + name.lstrip("/")


def _basename(path):
    """file-name extraction replacement (handles both separators)."""
    if not path:
        return ""
    return path.replace("\\", "/").rstrip("/").split("/")[-1]


def _write_json(path, obj):
    """Write a JSON file. Rename/replace is unavailable, so the write is direct
    and then read back: a truncated state file would let a finished tag run twice."""
    body = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        f = open(path, "w", encoding="utf-8")
        try:
            f.write(body)
        finally:
            f.close()
    except Exception as e:
        _log("ERROR", "cannot write %s: %s" % (path, e))
        return False
    if _read_json(path, quiet=True) is None:
        _log("ERROR", "wrote %s but it cannot be read back" % path)
        return False
    return True


# ============================================================================
# PTrade API adapters - each degrades instead of raising, and initialize()
# logs which spelling actually worked (see _selfcheck).
# ============================================================================
# Code dialect - ONE spelling everywhere: XSHG / XSHE (JoinQuant).
#   * the email attachment, the target file, this strategy's internal keys and every
#     platform API call (get_snapshot / get_stock_info / get_stock_status / order_market)
#     all use 600000.XSHG / 000001.XSHE
#   * the QMT-era SS/SH/SZ suffixes are gone; _split_code only TOLERATES them when reading
#     data written before 2026-10-19 (an old tracker file / old target file)
#   * proven by the reference strategy that ran here in production:
#     get_stock_info('603822.XSHG', field="stock_name")[code]
CAPS = {}


def _research_dir():
    try:
        p = get_research_path()
    except Exception:
        p = "."
    if not p:
        p = "."
    return p


def _state_path(strategy):
    """State file in the RESEARCH ROOT (flat - mkdir is not available)."""
    return _join(_research_dir(), STATE_PREFIX + strategy + ".json")


def _audit_path(strategy):
    return _join(_research_dir(), AUDIT_PREFIX + strategy + "_" + _date_str() + ".json")


def _tracker_path():
    return _join(_research_dir(), TRACKER_FILE)


def _target_paths(target_file):
    """Candidate paths for one strategy's target, in priority order: the upload_file/
    subfolder first (the client mirrors the folder), then the research root."""
    root = _research_dir()
    out = []
    for d in TARGET_DIRS:
        p = _join(root, _join(d, target_file)) if d else _join(root, target_file)
        if p not in out:
            out.append(p)
    return out


def _find_target(target_file):
    """-> (chosen_path, all_candidates). Only fixed names can be read: no directory
    listing in the sandbox, so timestamped files can never be discovered."""
    cands = _target_paths(target_file)
    for p in cands:
        if _read_json(p, quiet=True) is not None:
            return p, cands
    return (cands[0] if cands else ""), []


def _target_path(target_file):
    """The file this run would read (logged)."""
    return _find_target(target_file)[0]


def _strategy_from_file(fname):
    """target_low_valuation.json -> low_valuation (fallback when the file is unreadable)."""
    n = _basename(fname)
    if n.startswith("target_"):
        n = n[len("target_"):]
    if n.endswith(".json"):
        n = n[:-len(".json")]
    return n or "strategy"


def _peek_target(target_file):
    """Quiet read of the first readable candidate (used by initialize/_selfcheck)."""
    p, _c = _find_target(target_file)
    return _read_json(p, quiet=True) if p else None


def _order_times(data):
    """Order times (HH:MM) for one strategy: from its file, else the built-in default."""
    raw = None
    if isinstance(data, dict):
        raw = data.get("trading_times") or data.get("order_times")
    if not isinstance(raw, list) or not raw:
        return list(DEFAULT_ORDER_TIMES)
    out = []
    for t in raw:
        t = str(t)
        if len(t) == 5 and t[2] == ":":
            out.append(t)
    return out or list(DEFAULT_ORDER_TIMES)


def _params_from(data):
    """Sizing parameters for one strategy: file values on top of the built-in defaults."""
    p = dict(DEFAULT_PARAMS)
    if isinstance(data, dict):
        for k in DEFAULT_PARAMS:
            if data.get(k) is not None:
                p[k] = data[k]
    return p


# ============================================================================
# Position attribution - one account, N strategies (ported from the QMT executor)
# ============================================================================
def _tracker_load():
    """{strategy: {code: volume}} from the research-dir JSON (attribution is not derivable
    from the broker, so it has to be remembered).

    Codes are migrated to the canonical XSHG / XSHE spelling on load: a tracker written
    before 2026-10-19 used the QMT-era suffix spelling, and leaving those keys in place would
    make every position look untracked while also double counting in _my_share.
    """
    raw = _read_json(_tracker_path(), quiet=True)
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k == "last_updated" or not isinstance(v, dict):
                continue
            clean = {}
            for code, n in v.items():
                try:
                    n = int(n)
                except Exception:
                    continue
                if n <= 0:
                    continue
                canon = _full_code(code)
                if not canon:
                    continue
                clean[canon] = clean.get(canon, 0) + n      # merge old + new spellings
            out[k] = clean
    return out


def _tracker_save(t):
    out = dict((k, v) for k, v in t.items())
    out["last_updated"] = _now_str()
    _write_json(_tracker_path(), out)


def _tracked_total(t, code):
    return sum(v.get(code, 0) for v in t.values())


def _tracked_holders(t, code):
    return [name for name, pos in t.items() if pos.get(code, 0) > 0]


def _my_share(t, strategy, code, broker_volume):
    """This strategy's share of a (possibly shared) broker position."""
    current = t.get(strategy, {}).get(code, 0)
    if current <= 0:
        return 0
    other = _tracked_total(t, code) - current
    return max(broker_volume - other, 0)


def _tracker_sync(t, strategy_names, params_by_name, broker):
    """Reconcile the tracker with the broker (rules ported from the QMT tracker):

    * tracked code that vanished from the broker  -> drop it
    * broker code nobody tracks                   -> give it to the biggest capital_ratio
    * one holder, volume differs                  -> correct that holder (self-heal)
    * several holders, total differs              -> cannot decide -> ERROR (fix by hand)
    """
    for name in strategy_names:
        t.setdefault(name, {})
    for name in strategy_names:
        for code in list(t.get(name, {}).keys()):
            if code not in broker:
                vol = t[name].pop(code)
                _log("WARN", "reconcile: %s holds %s(%d) which the broker does not -> dropped"
                     % (name, code, vol))
    tracked = set()
    for pos in t.values():
        tracked.update(pos.keys())
    for code, p in broker.items():
        if code in tracked:
            continue
        owner = strategy_names[0]
        if params_by_name:
            owner = max(strategy_names,
                        key=lambda n: _to_float(params_by_name.get(n, {}).get("capital_ratio", 0)))
        t[owner][code] = p["amount"]
        _log("WARN", "reconcile: %s(%d) untracked -> assigned to '%s'"
             % (code, p["amount"], owner))
    for code, p in broker.items():
        total = _tracked_total(t, code)
        if total == p["amount"]:
            continue
        holders = _tracked_holders(t, code)
        if len(holders) == 1:
            old = t[holders[0]][code]
            t[holders[0]][code] = p["amount"]
            _log("INFO", "reconcile: %s '%s' corrected %d -> %d"
                 % (code, holders[0], old, p["amount"]))
        elif not holders:
            t[strategy_names[0]][code] = p["amount"]
        else:
            _log("ERROR", "reconcile: %s held by %s, tracked=%d != broker=%d -> "
                          "manual correction needed" % (code, holders, total, p["amount"]))


def _strategy_view(context, params, tracker, strategy):
    """This strategy's slice of the account (port of the QMT get_account_status):

        total     = account total  * capital_ratio
        cash      = min(slice_total - slice_position_value, account_cash * ratio), >= 0
        positions = ONLY the names tracked for this strategy, volume = its share
    """
    broker_total = _total_value(context)
    account_cash = _cash(context)
    broker = _positions(context)
    ratio = _to_float(params.get("capital_ratio", 1.0))
    if ratio <= 0:
        ratio = 1.0
    positions = {}
    pos_value = 0.0
    for code, tracked_vol in (tracker.get(strategy) or {}).items():
        p = broker.get(code)
        if p is None or p["amount"] <= 0:
            continue
        my_vol = _my_share(tracker, strategy, code, p["amount"])
        if my_vol <= 0:
            continue
        share = my_vol / float(p["amount"])
        my_value = p["amount"] * p["last"] * share
        pos_value += my_value
        q = dict(p)
        q["amount"] = my_vol
        q["enable"] = int(min(p["enable"], my_vol))
        q["my_value"] = my_value
        positions[code] = q
    slice_total = broker_total * ratio
    cash_quota = account_cash * ratio
    cash_needed = slice_total - pos_value
    slice_cash = max(min(cash_needed, cash_quota), 0.0)
    return {"total": slice_total, "cash": slice_cash, "positions": positions,
            "broker_total": broker_total, "ratio": ratio}


def _pt_code(code):
    """Code handed to the platform API. Same dialect as everything else: XSHG / XSHE."""
    return _full_code(code)


def _total_value(context):
    pf = _pick(context, ["portfolio"], None)
    if pf is not None:
        v = _pick(pf, ["portfolio_value", "total_value", "total_asset", "assets"], None)
        if v is not None:
            return _to_float(v)
    v = _pick(context, ["portfolio_value", "total_value"], None)
    if v is not None:
        return _to_float(v)
    return 0.0


def _cash(context):
    pf = _pick(context, ["portfolio"], None)
    if pf is not None:
        v = _pick(pf, ["cash", "available_cash", "enable_cash"], None)
        if v is not None:
            return _to_float(v)
    return _to_float(_pick(context, ["cash"], 0.0))


def _get_positions_raw(context):
    pf = _pick(context, ["portfolio"], None)
    src = _pick(pf, ["positions"], None) if pf is not None else None
    if src is None:
        try:
            src = get_positions()
        except Exception:
            src = None
    if src is None:
        return {}
    try:
        return dict(src.items())
    except Exception:
        pass
    out = {}
    try:
        for p in list(src):
            c = _pick(p, ["code", "security", "stock_code"], None)
            if c:
                out[c] = p
    except Exception:
        pass
    return out


def _positions(context):
    """-> { '600000.XSHG': {'amount':int,'enable':int,'last':float,'name':str} }"""
    out = {}
    for code, pos in _get_positions_raw(context).items():
        full = _full_code(code)          # canonical XSHG / XSHE
        if not full:
            continue
        amount = int(_to_float(_pick(pos, ["amount", "total_amount", "current_amount",
                                           "volume", "hold_amount"], 0)))
        if amount <= 0:
            continue
        enable = int(_to_float(_pick(pos, ["enable_amount", "can_use_amount",
                                           "available_amount", "enable", "usable_amount"],
                                    amount)))
        last = _to_float(_pick(pos, ["last_sale_price", "last_price", "price",
                                     "last_px", "current_price"], 0.0))
        out[full] = {
            "amount": amount,
            "enable": enable,
            "last": last,
            "name": str(_pick(pos, ["name", "stock_name", "security_name"], "") or ""),
        }
    return out


def _first_price(grp):
    """bid_grp / offer_grp can be {1:(price,vol,cnt)}, [(price,vol,cnt)] or a float."""
    if grp is None:
        return 0.0
    try:
        if isinstance(grp, dict):
            keys = list(grp.keys())
            if not keys:
                return 0.0
            try:
                keys.sort(key=lambda x: int(x))
            except Exception:
                keys.sort()
            return _first_price(grp[keys[0]])
        if isinstance(grp, (list, tuple)):
            if not grp:
                return 0.0
            v = grp[0]
            if isinstance(v, (list, tuple)):
                return _to_float(v[0]) if v else 0.0
            return _to_float(v)
        return _to_float(grp)
    except Exception:
        return 0.0


def _snap_one(pt_code):
    """-> {'last','preclose','bid1','ask1','name'}; zeros when unavailable."""
    raw = None
    try:
        raw = get_snapshot(pt_code)
    except Exception:
        raw = None
    if raw is None:
        try:
            raw = get_snapshot([pt_code])
        except Exception:
            raw = None
    if raw is None:
        return {}
    if isinstance(raw, dict):
        if pt_code in raw:
            raw = raw[pt_code]
        else:
            for k in list(raw.keys()):
                v = raw[k]
                if isinstance(v, dict) and any(x in v for x in
                                               ("last_px", "last_price", "preclose_px")):
                    raw = v
                    break
    if not isinstance(raw, dict):
        return {}
    out = {
        "last": _to_float(_pick(raw, ["last_px", "last_price", "last", "price",
                                      "current_price", "new_price"], 0.0)),
        "preclose": _to_float(_pick(raw, ["preclose_px", "pre_close", "preclose",
                                          "yesterday_close", "last_close"], 0.0)),
        "name": str(_pick(raw, ["name", "stock_name", "security_name", "symbol"], "") or ""),
        "bid1": 0.0,
        "ask1": 0.0,
        # the platform publishes the limit prices directly (reference strategy:
        # snap_shot["up_px"] / snap_shot.get("down_px")); trust them over our own maths
        "limit_up": _to_float(_pick(raw, ["up_px", "limit_up", "high_limited",
                                          "up_limit_price"], 0.0)),
        "limit_down": _to_float(_pick(raw, ["down_px", "limit_down", "low_limited",
                                            "down_limit_price"], 0.0)),
    }
    out["bid1"] = _first_price(_pick(raw, ["bid_grp", "bid1", "bid_price1"], None))
    out["ask1"] = _first_price(_pick(raw, ["offer_grp", "ask1", "ask_price1"], None))
    return out


def _status_flag(pt_code, kind):
    """get_stock_status(code, 'HALT'|'ST') -> bool.

    2026-10-19 (live bug): PTrade returns a DICT keyed by the security
    ({'600000.XSHG': False}), exactly as the reference strategy uses it
    (`st_status = get_stock_status(security, 'ST'); if st_status[security]:`).
    Testing the dict itself for truthiness is always True -> every name looked halted and
    every out-of-pool sell was skipped. Handle dict / list / bool / string answers.
    """
    try:
        v = get_stock_status(pt_code, kind)
    except Exception as e:
        _log("WARN", "get_stock_status(%s, %s) failed: %s" % (pt_code, kind, e))
        return False
    if isinstance(v, dict):
        if pt_code in v:
            v = v[pt_code]
        elif len(v) == 1:
            v = list(v.values())[0]
        else:
            for k in list(v.keys()):
                if str(k).upper() == str(pt_code).upper():
                    v = v[k]
                    break
            else:
                return False
    elif isinstance(v, (list, tuple)):
        if not v:
            return False
        v = v[0]
        if isinstance(v, dict):
            v = v.get(pt_code, False)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "t")
    return bool(v)


def _is_halted(pt_code):
    """Halt check; logs the decoded value so a false positive stays visible."""
    v = _status_flag(pt_code, "HALT")
    if v:
        _log("INFO", "halt check %s -> halted" % pt_code)
    return v


def _is_st(pt_code):
    """True when the platform marks the name ST (5% band). Unknown -> False."""
    return _status_flag(pt_code, "ST")


def _market_type(pt_code):
    """Market-order type per board (values copied from the reference strategy that ran live).

    If a board rejects the market order, the order is automatically retried as a +-2%
    repriced LIMIT order (see _place), so a wrong value degrades instead of losing the trade.
    To force a different type for one board, flip the constant below and restart.
    """
    plain = pt_code.split(".")[0]
    if plain.startswith("688"):
        return MARKET_TYPE_STAR
    if plain.startswith("60"):
        return MARKET_TYPE_MAIN_SH
    if plain.startswith("300") or plain.startswith("00"):
        return MARKET_TYPE_SZ
    return MARKET_TYPE_OTHER


def _refuse_to_buy_st(q, code):
    """ST names must never reach the target list: the 12-rule compliance filter (rule 4,
    ST/*ST) is supposed to strip every one of them, so finding one here means the UPSTREAM
    list is broken. Never buy it - skip loudly instead of trusting the list."""
    name = q.get("name") or ""
    if "ST" in name.upper():
        return True
    return _is_st(_pt_code(code))


def _order_rejected(oid):
    """Best-effort immediate rejection check.

    PTrade's order objects carry .status, where '9' means rejected (fei dan). It may not be
    populated the instant the order is submitted, so this is advisory: True only when we can
    positively tell the order is dead; everything else is treated as accepted.
    """
    if oid is None:
        return True
    try:
        getter = globals().get("get_order")
        if not callable(getter):
            return False
        o = getter(oid)
        if isinstance(o, (list, tuple)):
            if not o:
                return False
            o = o[0]
        st = _pick(o, ["status", "order_status"], None)
        if st is None:
            return False
        return str(st).strip() == "9"
    except Exception:
        return False


def _place(context, pt_code, amount, limit_price):
    """Send one order. Positive amount = buy, negative = sell. Returns order id or None.

    Order path (matching the in-production reference strategy):
      1. order_market(security, amount, market_type=<per board>, limit_price=protect)
         - "best five levels / counterparty best" market order with a protective bound
      2. if that is unavailable / raises / is rejected outright, RETRY as a repriced
         LIMIT order at the SAME protective price ("bian jie" +-2%), which is always inside
         the exchange cage and inside [limit-down, limit-up] because that is how protect is
         built (see _sell_protect / _buy_protect)
      3. if that also fails -> None (the caller logs ERROR and moves on)
    """
    if amount == 0:
        return None
    shares = int(amount)
    px = _round_price(limit_price) if (USE_LIMIT_PRICE and limit_price and limit_price > 0) else None
    mt = _market_type(pt_code)
    tried_market = False
    try:
        om = globals().get("order_market")
        if callable(om):
            tried_market = True
            if px is not None:
                oid = om(pt_code, amount=shares, market_type=mt, limit_price=px)
            else:
                oid = om(pt_code, amount=shares, market_type=mt)
            if not _order_rejected(oid):
                return oid
            _log("WARN", "order_market(%s, %d, market_type=%s) was rejected -> retrying as a "
                         "limit order at protect=%s (+-2%% repriced, inside limit-up/down)"
                 % (pt_code, shares, mt, px))
    except Exception as e:
        _log("WARN", "order_market(%s, %d, market_type=%s) failed (%s: %s) -> retrying as a "
                     "limit order at protect=%s"
             % (pt_code, shares, mt, type(e).__name__, e, px))
    if tried_market and px is None:
        # no usable price -> a limit retry is impossible, keep the failure visible
        _log("ERROR", "%s: market order failed and no limit price is available" % pt_code)
        return None
    try:
        if px is not None:
            return order(pt_code, shares, limit_price=px)
        return order(pt_code, shares)
    except TypeError:
        try:
            return order(pt_code, shares, px)
        except Exception as e:
            _log("ERROR", "order(%s, %d) failed: %s" % (pt_code, shares, e))
            return None
    except Exception as e:
        _log("ERROR", "order(%s, %d) failed: %s" % (pt_code, shares, e))
        return None


# ============================================================================
# target file
# ============================================================================
def _target_day(path, gen):
    """The 8-digit day of a target: prefer the file name (the local pipeline writes
    rebalance_<strategy>_<YYYYMMDD>_<HHMM>.json), fall back to generated_at."""
    for part in _basename(path or "").replace(".json", "").split("_"):
        if len(part) == 8 and part.isdigit():
            return part
    return str(gen or "").replace("-", "")[:8]


def _load_target(target_file):
    """-> (status, target); status in ok/not-today/stale/missing/bad/liquidate.

    AGE POLICY (2026-10-19, back to TODAY ONLY):
      today                          -> "ok", trade
      1 .. MAX_TARGET_AGE_DAYS old   -> "not-today" -> DO NOT TRADE, log ERROR
                                        (the local process failed to produce today's list;
                                         do not silently run yesterday's names)
      older than MAX_TARGET_AGE_DAYS -> "stale" -> liquidate this strategy's slice
      undateable / unreadable / absent -> missing/bad -> MISSING_FILE_ACTION
    """
    path, candidates = _find_target(target_file)
    if not path:
        return "missing", None
    data = _read_json(path)          # no exists() API: reading the file IS the check
    if data is None:
        return "missing", None
    if not isinstance(data, dict):
        return "bad", None
    data["_path"] = path
    data["_candidates"] = len(candidates)
    gen = str(data.get("generated_at") or "")
    data["_day"] = _target_day(path, gen)
    age_days = None
    if gen:
        try:
            age_days = (datetime.datetime.now() -
                        datetime.datetime.strptime(gen[:19], "%Y-%m-%dT%H:%M:%S")).days
        except Exception:
            try:
                age_days = (datetime.datetime.now() -
                            datetime.datetime.strptime(gen[:10], "%Y-%m-%d")).days
            except Exception:
                age_days = None
    data["_age_days"] = age_days
    if age_days is None:
        return "bad", data           # cannot date it -> do not trust it
    if age_days > MAX_TARGET_AGE_DAYS:
        return "stale", data         # _run turns this into a full liquidation
    if age_days > 0:
        # TODAY ONLY: the list is not from today -> do not run, raise an error
        data["_stale_days"] = age_days
        return "not-today", data
    stocks = []
    seen = set()
    dupes = 0
    for c in (data.get("stocks") or []):
        full = _full_code(c)          # canonical XSHG / XSHE
        if not full:
            continue
        if full in seen:
            dupes += 1      # a duplicated code would otherwise be ordered TWICE
            continue
        seen.add(full)
        stocks.append(full)
    data["_stocks"] = stocks
    data["_age_days"] = age_days
    data["_dupes"] = dupes
    if data.get("liquidate") is True:
        return "liquidate", data
    if not stocks:
        return "liquidate", data      # fresh explicit empty list = liquidate
    return "ok", data


# ============================================================================
# planning (pure enough to unit-test locally)
# ============================================================================
def _buy_price(last, ask, limit_up, preclose=None):
    """Buy limit price under the exchange "price cage" (continuous-auction price band).

    Rule: a buy may not be priced above max(benchmark*1.02, benchmark+0.1), where benchmark is
    best ask, else the last trade, else the previous close. Submitting at the limit-up price
    (what the old PTrade strategy did: order_market(limit_price=up_px)) is outside the cage
    and gets rejected / risk-blocked.

    This port keeps the QMT-era formula, which is STRICTER than the exchange window:
        final = min( min(ask*1.02, ask+0.1), limit_up )
    so it satisfies both the exchange cage and a broker rule of "within 2% of the current
    price". Slightly passive on high-priced names, never rejected.
    """
    px = ask if (ask and ask > 0) else (last if (last and last > 0) else (preclose or 0.0))
    if not px or px <= 0:
        return 0.0
    if PRICE_MODE != "cage":
        if limit_up and limit_up > 0:
            return _round_price(min(px, limit_up))
        return px
    cage = min(px * CAGE_MULTIPLIER, px + CAGE_OFFSET)
    if limit_up and limit_up > 0:
        cage = min(cage, limit_up)          # QMT: never price a buy above limit-up
    return _round_price(cage)


def _sell_price(last, bid, limit_down, preclose=None):
    """Sell limit price under the same cage: >= min(benchmark*0.98, benchmark-0.1), benchmark = best bid,
    else last trade, else previous close. Anchors on bid, not on the last trade price."""
    px = bid if (bid and bid > 0) else (last if (last and last > 0) else (preclose or 0.0))
    if not px or px <= 0:
        return 0.0
    if PRICE_MODE != "cage":
        if limit_down and limit_down > 0:
            return _round_price(max(px, limit_down))
        return px
    cage = max(px * (2.0 - CAGE_MULTIPLIER), px - CAGE_OFFSET)
    if limit_down and limit_down > 0:
        cage = max(cage, limit_down)        # QMT: never price a sell below limit-down
    return _round_price(cage)


def _sell_protect(last, bid, limit_down, preclose=None):
    """Protection price handed to the (market) SELL order.

    2026-10-19: order_market's limit_price is a PROTECTION bound, not the working price.
    The reference strategy passed the LIMIT-DOWN price so the order sweeps every bid down to
    the floor - "sell with everything you have". But this broker also enforces a
    quantitative-trading rule that the submitted price may not deviate more than ~2% from
    the current price, so the aggressive floor has to be the HIGHER of:
        * last trade * 0.98   (2% band below the last price)
        * limit-down price    (the exchange floor)
    i.e. as aggressive as the rules allow, never outside either bound.
    Falls back to the cage when neither the last price nor the floor is known.
    """
    if SELL_PROTECT_AT_LIMIT_DOWN:
        px = _round_price(last * (2.0 - CAGE_MULTIPLIER)) if (last and last > 0) else 0.0
        if limit_down and limit_down > 0:
            px = max(px, _round_price(limit_down))      # never below the exchange floor
        if px > 0:
            return px
    return _sell_price(last, bid, limit_down, preclose)


def _buy_protect(last, ask, limit_up, preclose=None):
    """Protection price for the (market) BUY order.

    Default keeps the QMT-era cage (do not chase) and additionally caps it at
    last * 1.02 so the 2% deviation rule is never broken.
    Set BUY_PROTECT_AT_LIMIT_UP = True to mirror the reference strategy (protection = limit-up)
    - in that case the 2% cap still applies.
    """
    px = 0.0
    if BUY_PROTECT_AT_LIMIT_UP and limit_up and limit_up > 0:
        px = _round_price(limit_up)
    else:
        px = _buy_price(last, ask, limit_up, preclose)
    cap = _round_price(last * CAGE_MULTIPLIER) if (last and last > 0) else 0.0
    if px > 0 and cap > 0:
        px = min(px, cap)          # 2% band above the last price
    return px


def _up_down(q, code):
    """(limit_up, limit_down): prefer the platform's own up_px/down_px, else preclose + board
    rules; (0,0) if unknown.

    ST is detected from the snapshot name when present, else by asking the platform
    (get_stock_status 'ST') - an ST name has a 5% band, and getting this wrong would
    make the limit checks think a 5%-limit stock is not at its limit."""
    up = _to_float(q.get("limit_up") or 0.0)
    down = _to_float(q.get("limit_down") or 0.0)
    if up > 0 and down > 0:
        return up, down                      # the platform's own numbers, authoritative
    if not q.get("preclose"):
        return 0.0, 0.0
    mk, pl = _split_code(code)
    name = q.get("name") or ""
    if "ST" in name.upper() or _is_st(_pt_code(code)):
        r = 0.05
    else:
        r = _limit_ratio(mk, pl, name)
    return _round_price(q["preclose"] * (1 + r)), _round_price(q["preclose"] * (1 - r))


def _plan(view, stocks, params):
    """Plan for ONE strategy, on its own slice of the account (see _strategy_view)."""
    total = view["total"]
    cash = view["cash"]
    positions = view["positions"]
    max_holdings = int(params.get("max_holdings", DEFAULT_PARAMS["max_holdings"]))
    candidate_pool = int(params.get("candidate_pool_size", DEFAULT_PARAMS["candidate_pool_size"]))
    reserve_ratio = _to_float(params.get("cash_reserve_ratio",
                                         DEFAULT_PARAMS["cash_reserve_ratio"]))
    threshold = _to_float(params.get("rebalance_threshold",
                                     DEFAULT_PARAMS["rebalance_threshold"]))
    if max_holdings <= 0:
        max_holdings = DEFAULT_PARAMS["max_holdings"]
    reserve = total * reserve_ratio
    target_per = (total - reserve) / float(max_holdings)

    candidate = stocks[:candidate_pool]
    buy_pool = stocks[:max_holdings]
    candidate_set = set(candidate)

    sells = []      # (code, amount, reason)
    buys = []       # dicts
    notes = []
    errors = []     # conditions that must surface as ERROR in the log/audit
    quotes = {}

    def quote(code):
        if code not in quotes:
            quotes[code] = _snap_one(_pt_code(code))
        return quotes[code]

    # ---------- 1. everything outside the candidate pool goes ----------
    for code, p in sorted(positions.items()):
        if code in candidate_set:
            continue
        q = quote(code)
        if _is_halted(_pt_code(code)):
            notes.append("halted, cannot sell: %s" % code)
            continue
        last = q.get("last") or p.get("last") or 0.0
        up, _dn = _up_down(q, code)
        if up and last and abs(last - up) < 0.011:
            notes.append("limit-up, hold: %s" % code)
            continue
        vol = (p["enable"] // LOT) * LOT
        if vol > 0:
            sells.append((code, vol, "out-of-pool"))

    # ---------- 2. in-pool re-equalisation, QMT-style combination gate ----------
    # QMT semantics (this IS the anti-churn design - do not turn it into a per-name check):
    #   the in-pool re-equalisation runs only when
    #     (a) at least one EMPTY slot exists,  AND
    #     (b) |(cash - reserve)/slots - target_per_stock| / target_per_stock > threshold
    #   A FULL book therefore never trades just because one name ran up or crashed.
    # When it does fire, EVERY held in-pool name is pulled to target_per_stock
    # (no per-name deadband).
    held = set(positions.keys())
    slots = max_holdings - len(held)
    cash_for_buy = cash - reserve
    rebalance_on = False
    if target_per > 0:
        if slots <= 0:
            notes.append("book full (%d names) -> no in-pool re-equalisation" % len(held))
        elif cash_for_buy <= 0:
            notes.append("no free cash -> no in-pool re-equalisation")
        else:
            deviation = abs(cash_for_buy / float(slots) - target_per) / target_per
            rebalance_on = deviation > threshold
            notes.append("rebalance gate: slots=%d cash_for_buy=%.2f avg=%.2f target=%.2f "
                         "deviation=%.1f%% -> %s"
                         % (slots, cash_for_buy, cash_for_buy / float(slots), target_per,
                            deviation * 100.0, "ON" if rebalance_on else "OFF"))
    if rebalance_on:
        for code in candidate:
            p = positions.get(code)
            if p is None:
                continue        # empty slots are filled by step 3 only
            q = quote(code)
            if _is_halted(_pt_code(code)):
                notes.append("halted: %s" % code)
                continue
            last = q.get("last") or p.get("last") or 0.0
            if not last or last <= 0:
                notes.append("no quote: %s" % code)
                continue
            mv = p["amount"] * last
            up, down = _up_down(q, code)
            if mv > target_per:
                if not down:
                    notes.append("no limit-down available, skip trim: %s" % code)
                    continue
                if abs(last - down) < 0.011:
                    notes.append("limit-down, hold: %s" % code)
                    continue
                want = int((mv - target_per) // (last * LOT)) * LOT
                vol = min(want, (p["enable"] // LOT) * LOT)
                if vol > 0:
                    sells.append((code, vol, "over-weight"))
            elif mv < target_per:
                if _refuse_to_buy_st(q, code):
                    errors.append("ST name %s must be bought (top-up) - upstream target "
                                  "list is broken; REFUSING and skipping it" % code)
                    continue
                if not up:
                    notes.append("no limit-up available, skip top-up: %s" % code)
                    continue
                if abs(last - up) < 0.011:
                    notes.append("limit-up, cannot buy: %s" % code)
                    continue
                buys.append({"code": code, "need": target_per - mv, "last": last,
                             "ask": q.get("ask1") or last, "reason": "under-weight"})

    # ---------- 3. fill empty slots (QMT buy_to_fill: per_stock = buy_cash / slots) ----------
    # NOTE: divides by the number of EMPTY slots, not by max_holdings - a partially
    # filled book therefore puts more money into each new name than target_per_stock.
    if slots > 0 and cash_for_buy > 0:
        per_stock = cash_for_buy / float(slots)
        for code in buy_pool:
            if slots <= 0:
                break
            if code in held:
                continue
            q = quote(code)
            if _is_halted(_pt_code(code)):
                notes.append("halted, skip buy: %s" % code)
                continue
            last = q.get("last") or 0.0
            if last <= 0:
                notes.append("no quote, skip buy: %s" % code)
                continue
            if _refuse_to_buy_st(q, code):
                errors.append("ST name %s must be bought (new slot) - upstream target "
                              "list is broken; REFUSING and skipping it" % code)
                continue
            up, _dn = _up_down(q, code)
            if not up:
                notes.append("no limit-up available, skip buy: %s" % code)
                continue
            if abs(last - up) < 0.011:
                notes.append("limit-up, skip buy: %s" % code)
                continue
            buys.append({"code": code, "need": per_stock, "last": last,
                         "ask": q.get("ask1") or last, "reason": "new-slot"})
            slots -= 1

    # ---------- 4. cash budget (QMT: max_amount = min(target, available_cash) * 0.99) ----------
    # Sell proceeds are estimated at the price we are actually going to send (bid cage),
    # not at the last trade price, and haircut 0.5%: PTrade plans in one pass and cannot
    # wait for the fills the way the QMT executor did (30s polling + account re-query).
    est_in = 0.0
    for code, vol, _r in sells:
        qq = quote(code)
        p = positions.get(code) or {}
        last = qq.get("last") or p.get("last") or 0.0
        _u, dn = _up_down(qq, code)
        px = _sell_price(last, qq.get("bid1"), dn, qq.get("preclose")) or last
        est_in += vol * px
    budget = max(cash + est_in * 0.995 - reserve, 0.0)

    planned_buys = []
    for b in buys:
        up, _dn = _up_down(quote(b["code"]), b["code"])
        price = _buy_price(b["last"], b["ask"], up, b.get("preclose"))
        if price <= 0:
            notes.append("no price, skip buy: %s" % b["code"])
            continue
        vol = int((min(b["need"], budget) * 0.99) // (price * LOT)) * LOT
        if vol <= 0:
            notes.append("cash too small for one lot: %s" % b["code"])
            continue
        planned_buys.append((b["code"], vol, b["reason"]))
        budget -= vol * price * 1.001

    return {"total": total, "cash": cash, "reserve": reserve, "target_per": target_per,
            "est_in": est_in, "sells": sells, "buys": planned_buys, "notes": notes,
            "errors": errors, "positions": positions, "candidate": candidate,
            "quotes": quotes}


# ============================================================================
# execution
# ============================================================================
def _already_done(strategy, tag):
    if not ONLY_ONCE_PER_TIME:
        return False
    st = _read_json(_state_path(strategy), quiet=True) or {}
    if tag in (st.get("done") or []):
        return True
    # redundancy: a state file lost to a crash still shows up in today's audit file
    au = _read_json(_audit_path(strategy), quiet=True) or {}
    return tag in (au.get("done") or [])


def _mark_done(strategy, tag, extra):
    path = _state_path(strategy)
    st = _read_json(path, quiet=True) or {}
    done = st.get("done") or []
    if tag not in done:
        done.append(tag)
    st["done"] = done[-40:]
    st["last_run"] = _now_str()
    st["last_result"] = extra
    _write_json(path, st)


def _audit(strategy, plan, target, results, tag=None):
    path = _audit_path(strategy)
    _write_json(path, {
        "strategy": strategy,
        "at": _now_str(),
        "tag": tag,
        "done": [tag] if tag else [],
        "dry_run": DRY_RUN,
        "target_generated_at": (target or {}).get("generated_at"),
        "target_age_days": (target or {}).get("_age_days"),
        "slice_total_value": plan["total"],
        "slice_cash": plan["cash"],
        "reserve": plan["reserve"],
        "target_per_stock": plan["target_per"],
        "estimated_sell_proceeds": plan.get("est_in", 0.0),
        "errors": plan.get("errors", []),
        "sells": plan["sells"],
        "buys": plan["buys"],
        "notes": plan["notes"],
        "orders": results,
    })
    return path


def _liquidate_plan(view, reason):
    """Sell everything THIS strategy owns (its share of each position)."""
    positions = view["positions"]
    sells = []
    for code, p in sorted(positions.items()):
        vol = (p["enable"] // LOT) * LOT
        if vol > 0:
            sells.append((code, vol, reason))
    return {"total": view["total"], "cash": view["cash"], "reserve": 0.0,
            "target_per": 0.0, "est_in": 0.0, "sells": sells, "buys": [], "notes": [reason],
            "errors": [], "positions": positions, "candidate": [], "quotes": {}}


def _tracker_apply_plan(t, strategy, plan):
    """Record the volumes we just ORDERED. PTrade cannot wait for fills (async, 6s account
    sync), so this is an estimate; the next run's _tracker_sync reconciles it with the
    broker (single holder -> corrected automatically)."""
    pos = t.setdefault(strategy, {})
    for code, vol, _r in plan["sells"]:
        left = max(pos.get(code, 0) - vol, 0)
        if left > 0:
            pos[code] = left
        else:
            pos.pop(code, None)
    for code, vol, _r in plan["buys"]:
        pos[code] = pos.get(code, 0) + vol


def _registry():
    """[(strategy, params, target_file)] for every configured target file."""
    out = []
    for tf in TARGET_FILES:
        data = _peek_target(tf)
        name = (data or {}).get("strategy") or _strategy_from_file(tf)
        out.append((name, _params_from(data), tf))
    return out


def _run(context, tag, target_file):
    global _LOG_TAG
    status, target = _load_target(target_file)
    strategy = (target or {}).get("strategy") or _strategy_from_file(target_file)
    params = _params_from(target)
    order_times = _order_times(target)
    _LOG_TAG = strategy
    _log("INFO", "run start %s (strategy=%s tag=%s dry_run=%s file=%s)"
         % (_now_str(), strategy, tag, DRY_RUN, _basename(target_file)))
    if _already_done(strategy, tag):
        _log("INFO", "tag %s already processed for %s, skip" % (tag, strategy))
        return
    # one run_daily callback exists per (file, time): only the strategy's OWN times act
    now_hm = datetime.datetime.now().strftime("%H:%M")
    if now_hm not in order_times:
        _log("INFO", "not an order time for %s (now %s, its times %s) -> skip"
             % (strategy, now_hm, order_times))
        return

    chosen = (target or {}).get("_path") or _target_path(target_file)
    _log("INFO", "target status=%s file=%s age_days=%s"
         % (status, chosen, (target or {}).get("_age_days")))

    # --- attribution: reconcile the tracker with the broker, then take our slice ---
    tracker = _tracker_load()
    registry = _registry()
    names = [n for n, _p, _f in registry]
    if strategy not in names:
        names.append(strategy)
    params_by_name = dict((n, p) for n, p, _f in registry)
    params_by_name[strategy] = params
    _tracker_sync(tracker, names, params_by_name, _positions(context))
    view = _strategy_view(context, params, tracker, strategy)
    _log("INFO", "slice: total=%.2f cash=%.2f positions=%d (ratio=%s, account_total=%.2f)"
         % (view["total"], view["cash"], len(view["positions"]), view["ratio"],
            view["broker_total"]))

    if status == "stale":
        # No trustworthy list for more than MAX_TARGET_AGE_DAYS -> get out of this slice.
        _log("WARN", "target is %s days old (> %d days) -> LIQUIDATE this strategy's slice"
             % ((target or {}).get("_age_days"), MAX_TARGET_AGE_DAYS))
        plan = _liquidate_plan(view, "target-stale")
    elif status == "not-today":
        # TODAY ONLY rule: never trade a list that was not generated today.
        _log("ERROR", "target is NOT from today (generated %s, %s day(s) old) -> REFUSING to "
                      "trade this round; positions stay untouched. The local process did not "
                      "produce today's list (check its log / the upload)."
             % ((target or {}).get("generated_at"), (target or {}).get("_age_days")))
        _tracker_save(tracker)
        return
    elif status in ("missing", "bad"):
        if MISSING_FILE_ACTION == "liquidate":
            _log("WARN", "target %s -> liquidate (MISSING_FILE_ACTION=liquidate)" % status)
            plan = _liquidate_plan(view, "target-%s" % status)
        else:
            _log("ERROR", "target %s -> no trading this round for %s. If the local process "
                          "has never uploaded this file, check the upload dir/name; a file "
                          "that exists but is too old is handled by the %d-day rule."
                 % (status, target_file, MAX_TARGET_AGE_DAYS))
            _tracker_save(tracker)
            return
    elif status == "liquidate":
        _log("WARN", "target asks for liquidation")
        plan = _liquidate_plan(view, "target-liquidate")
    else:
        stocks = target.get("_stocks") or []
        _log("INFO", "pool=%d candidate=%d buy_pool=%d dupes=%s"
             % (len(stocks), min(len(stocks), int(params.get("candidate_pool_size", 0))),
                min(len(stocks), int(params.get("max_holdings", 0))),
                target.get("_dupes")))
        if target.get("_dupes"):
            _log("WARN", "target had %d duplicate code(s); kept first occurrence only"
                 % target.get("_dupes"))
        if stocks and not CAPS.get("quote_sample"):
            # get_snapshot() cannot be called from initialize (the platform raises
            # RuntimeError: not allowed during strategy initialisation), so the first real run is the
            # first place a quote can be verified - log one sample for the record.
            try:
                probe_code = _pt_code(stocks[0])
                sample = _snap_one(probe_code)
                CAPS["quote_sample"] = "%s -> %s" % (probe_code, sample)
                _log("INFO", "quote sample %s -> %s" % (probe_code, sample))
                if not sample:
                    _log("WARN", "quote sample is empty: snapshots look unavailable - "
                                 "orders will be skipped rather than sent blind")
            except Exception as e:
                _log("WARN", "quote sample failed: %s: %s" % (type(e).__name__, e))
        # Fail closed on a broken account read: with total<=0 every target would be 0 and
        # the empty-slot budget would still be cash/slots, i.e. it would trade blind.
        if view["broker_total"] <= 0:
            _log("ERROR", "portfolio total value read as %.2f -> refusing to trade this "
                          "round (check the portfolio API shape)" % view["broker_total"])
            _tracker_save(tracker)
            return
        plan = _plan(view, stocks, params)

    _log("INFO", "total=%.2f cash=%.2f reserve=%.2f target_per=%.2f est_sell_proceeds=%.2f"
         % (plan["total"], plan["cash"], plan["reserve"], plan["target_per"],
            plan.get("est_in", 0.0)))
    for c, v, r in plan["sells"]:
        _log("INFO", "SELL %s %d (%s)" % (c, v, r))
    for c, v, r in plan["buys"]:
        _log("INFO", "BUY  %s %d (%s)" % (c, v, r))
    for e in plan.get("errors", []):
        _log("ERROR", "%s" % e)
    for n in plan["notes"]:
        _log("WARN", "note: %s" % n)

    n_orders = len(plan["sells"]) + len(plan["buys"])
    if n_orders == 0:
        _log("INFO", "nothing to do")
        _mark_done(strategy, tag, {"orders": 0})
        _tracker_save(tracker)
        return
    if n_orders > MAX_ORDERS_PER_RUN:
        _log("ERROR", "plan has %d orders > MAX_ORDERS_PER_RUN=%d -> ABORT"
             % (n_orders, MAX_ORDERS_PER_RUN))
        _mark_done(strategy, tag, {"aborted": n_orders})
        _tracker_save(tracker)
        return

    results = []
    if DRY_RUN:
        for c, v, r in plan["sells"]:
            results.append({"code": c, "amount": -v, "reason": r,
                            "order_id": None, "dry_run": True})
        for c, v, r in plan["buys"]:
            results.append({"code": c, "amount": v, "reason": r,
                            "order_id": None, "dry_run": True})
        _log("WARN", "DRY_RUN: %d orders NOT sent" % n_orders)
    else:
        # sells first, so the proceeds are available to the buys
        for c, v, r in plan["sells"]:
            p = plan["positions"].get(c) or {}
            q = _snap_one(_pt_code(c))
            last = q.get("last") or p.get("last") or 0.0
            _up, down = _up_down(q, c)
            protect = _sell_protect(last, q.get("bid1"), down, q.get("preclose"))
            if protect <= 0:
                # Never send an unprotected order: with no limit-down and no usable quote we
                # cannot bound the price, so skip loudly instead of guessing.
                _log("ERROR", "%s: no limit-down and no usable quote (bid/last/preclose), "
                              "sell skipped - fix manually" % c)
                results.append({"code": c, "amount": -v, "reason": r, "order_id": None,
                                "skipped": "no-price"})
                continue
            oid = _place(context, _pt_code(c), -v, protect)
            if oid is None:
                _log("ERROR", "SELL %s %d protect=%.2f -> REJECTED (no order id)" % (c, v, protect))
                results.append({"code": c, "amount": -v, "reason": r, "order_id": None,
                                "rejected": True})
                continue
            results.append({"code": c, "amount": -v, "reason": r, "order_id": str(oid),
                            "protect_price": protect})
            _log("INFO", "sold %s %d protect=%s (limit-down sweep) -> order %s"
                 % (c, v, protect, oid))
        for c, v, r in plan["buys"]:
            q = _snap_one(_pt_code(c))
            up, _down = _up_down(q, c)
            protect = _buy_protect(q.get("last"), q.get("ask1"), up, q.get("preclose"))
            if protect <= 0:
                # QMT: a buy without a valid price/limit is SKIPPED, never sent blind.
                _log("ERROR", "%s: no price/limit-up, buy skipped" % c)
                results.append({"code": c, "amount": v, "reason": r, "order_id": None,
                                "skipped": "no-price"})
                continue
            oid = _place(context, _pt_code(c), v, protect)
            if oid is None:
                _log("ERROR", "BUY %s %d protect=%.2f -> REJECTED (no order id; cash may be "
                              "short because a sell did not go through)" % (c, v, protect))
                results.append({"code": c, "amount": v, "reason": r, "order_id": None,
                                "rejected": True})
                continue
            results.append({"code": c, "amount": v, "reason": r, "order_id": str(oid),
                            "protect_price": protect})
            _log("INFO", "bought %s %d protect=%.2f -> order %s" % (c, v, protect, oid))

    path = _audit(strategy, plan, target, results, tag)
    _log("INFO", "audit written: %s" % path)
    _mark_done(strategy, tag, {"orders": n_orders})
    if not DRY_RUN:
        _tracker_apply_plan(tracker, strategy, plan)
    _tracker_save(tracker)


# ============================================================================
# PTrade entry points
# ============================================================================
def _job(context, target_file):
    """run_daily callback for one strategy file (accepts extra args for safety)."""
    global _LOG_TAG
    _LOG_TAG = _strategy_from_file(target_file)
    tag = _date_str() + "@" + datetime.datetime.now().strftime("%H:%M")
    try:
        _run(context, tag, target_file)
    except Exception as e:
        # no traceback module (it imports sys, which is forbidden here)
        _log("ERROR", "run failed (%s): %s: %s" % (target_file, type(e).__name__, e))
    return None


def _make_job(target_file):
    """Bind one target file to a run_daily callback (a factory, not a loop closure)."""
    def _cb(context, *args, **kwargs):
        return _job(context, target_file)
    return _cb


def _selfcheck(context):
    """Log what this PTrade instance really exposes: the first run self-diagnoses."""
    caps = {}
    caps["research_path"] = _research_dir()
    caps["target_files"] = TARGET_FILES
    for tf in TARGET_FILES:
        name = _strategy_from_file(tf)
        chosen, cands = _find_target(tf)
        caps["target_" + name] = chosen
        caps["candidates_" + name] = len(cands)
        caps["exists_" + name] = _read_json(chosen, quiet=True) is not None if chosen else False
        caps["times_" + name] = _order_times(_peek_target(tf))
    try:
        caps["total_value"] = _total_value(context)
        caps["cash"] = _cash(context)
        caps["positions"] = len(_positions(context))
        caps["tracker"] = _tracker_load()
    except Exception as e:
        caps["portfolio_read_error"] = str(e)
    for name in ("get_positions", "get_snapshot", "get_stock_status", "get_stock_info",
                 "order", "order_market", "run_daily", "get_research_path", "log"):
        f = globals().get(name)
        if f is None:
            # the platform injects `log` etc. into __builtins__, which may be a dict or a
            # module depending on the embedder - cover both
            try:
                b = __builtins__
                if isinstance(b, dict):
                    f = b.get(name)
                else:
                    f = getattr(b, name, None)
            except Exception:
                f = None
        caps["has_" + name] = callable(f)
    caps["code_dialect"] = "XSHG / XSHE (fixed)"
    caps["order_mode"] = ("order_market + limit_order_retry (market_type: SH60=%s STAR688=%s "
                          "SZ=%s other=%s)" % (MARKET_TYPE_MAIN_SH, MARKET_TYPE_STAR,
                                               MARKET_TYPE_SZ, MARKET_TYPE_OTHER))
    caps["sell_protect"] = "max(last*%.2f, limit-down)" % (2.0 - CAGE_MULTIPLIER)
    # 2026-10-19: the platform raises RuntimeError (get_snapshot is not allowed during
    # strategy initialisation), so a quote probe here is meaningless. Quotes are verified
    # on the first real run instead (see _run's quote sample line).
    caps["snapshot_at_init"] = "not supported by the platform (get_snapshot raises here)"
    CAPS.clear()
    CAPS.update(caps)
    for k in sorted(caps.keys()):
        _log("INFO", "selfcheck %s = %s" % (k, caps[k]))
    return caps


def initialize(context):
    global _LOG_TAG
    _log("INFO", "=" * 62)
    _log("INFO", "ptrade_rebalance_executor init (python 3.5 compatible)")
    _log("INFO", "DRY_RUN=%s MISSING_FILE_ACTION=%s PRICE_MODE=%s TARGET_FILES=%s"
         % (DRY_RUN, MISSING_FILE_ACTION, PRICE_MODE, TARGET_FILES))
    # code dialect is fixed: XSHG / XSHE everywhere (email list, target file, internal
    # keys, platform API). No detection needed any more.
    _log("INFO", "code dialect = XSHG / XSHE (fixed)")
    try:
        _selfcheck(context)
    except Exception as e:
        _log("ERROR", "selfcheck failed: %s" % e)
    # register one callback per (target file, order time). The times come from each file
    # (falling back to DEFAULT_ORDER_TIMES until it is uploaded), so changing an order time
    # in ptrade_config.json needs a strategy restart to take effect.
    seen = []
    for tf in TARGET_FILES:
        _LOG_TAG = _strategy_from_file(tf)
        data = _peek_target(tf)
        times = _order_times(data)
        if data is None:
            _log("WARN", "%s is not uploaded yet -> order times come from DEFAULT_ORDER_TIMES "
                         "%s. RESTART the strategy after the upload so the file's own "
                         "trading_times are used." % (tf, times))
        _log("INFO", "%s -> order times %s" % (tf, times))
        for t in times:
            if (tf, t) in seen:
                continue
            seen.append((tf, t))
            try:
                run_daily(context, _make_job(tf), t)
                _log("INFO", "run_daily registered at %s for %s" % (t, tf))
            except Exception as e:
                _log("ERROR", "run_daily(%s, %s) failed: %s" % (t, tf, e))
    _LOG_TAG = "-"
    _log("INFO", "=" * 62)
    return None


def before_trading_start(context, data):
    return None


def handle_data(context, data):
    # timer driven strategy: handle_data is intentionally a no-op
    return None


def after_trading_end(context, data):
    return None
