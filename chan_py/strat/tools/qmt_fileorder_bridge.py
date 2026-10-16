# -*- coding: utf-8 -*-
"""
qmt_fileorder_bridge.py - external rebalance engine over QMT's native file-order channels.

WHY THIS EXISTS
  The broker will restrict what a QMT *strategy* may read (files) and send (HTTP).
  It does NOT restrict QMT's own client-side services. The official manual
  (config\\help\\systemfunction\\迅投QMT极速策略交易系统说明文档.pdf) documents two of them:

    便捷交易 / 文件单   (manual p.290-292, 323-327)
      - the client scans a folder every few milliseconds, reads a protocol file,
        places the orders and deletes the file.
      - protocol (one order per line, half-width commas):
            下单类型, 通道号, 交易市场, 交易代码, 交易数量, 报价类型, 交易价格[, 投资备注]
        下单类型: 23 股票买入 / 24 股票卖出 / 27 融资买入 / 28 融券卖出 / ...
        通道号:   shown in the panel, 0 = 万能通道号
        报价类型: 5 最新价 / 11 指定价 / 42-48 沪深的市价类类型
      - cancel protocol: cancel_order 市场代码 合同编号 [市场代码 合同编号 ...]

    批量预埋单 / CSV预埋单 (manual p.327-333)
      - bidirectional DBF shared file in a watched folder; filename unrestricted.
      - order fields, in this exact order (manual p.329-331):
            order_type, price_type, mode_price, stock_code, volume,
            account_id, acc_type, brokertype, strategy, note
        order_type: 23 股票买入 / 24 股票卖出 / 27/28/29/30/31/32 credit ...
        price_type: 1 最新价 / 3 指定价 / 6 盘后定价 / M1..M7 沪深市价类
        stock_code: 市场+代码, e.g. SH600000
        account_id: 资金账号或账号 key;  acc_type 49=资金账号;  brokertype 2=股票 3=信用
      - the client writes back <name>_result.dbf with:
            ORDERID, MESSAGE, STATUS, STRATEGY, NOTE, MARKET, ORDERSYSID

    数据导出 (manual p.337-338)
      - scheduled export of 资产/持仓/委托/成交 to a chosen folder as DBF/TXT/CSV.
      - THIS IS THE FEEDBACK PATH: the external process reads positions/cash from it,
        so the broker's account state is available outside QMT without xtquant.

  Together: external process  =  selection + AI filter + position diff + order emission
            QMT client (no strategy) = scan folder -> place orders -> export state

WHAT THIS SCRIPT DOES
  positions/cash (数据导出)  ->  diff against the target pool  ->  便捷交易 txt AND/OR 预埋单 dbf
  and optionally reports the *_result.dbf feedback.

SAFETY
  --dry-run is the DEFAULT. Nothing is written to the QMT folders until you pass --execute.
  Always run `--inspect` first, then `--dry-run`, then `--execute`.

USAGE
  python qmt_fileorder_bridge.py --inspect                 # dump export dir + parsed state
  python qmt_fileorder_bridge.py --pool qmt_exchange/rebalance_low_valuation_xxx.json
  python qmt_fileorder_bridge.py --pool <file.json> --execute
  python qmt_fileorder_bridge.py --feedback                # read *_result.dbf
"""

import os
import re
import sys
import csv
import json
import time
import glob
import struct
import argparse
import datetime

# ==================== constants: order types / price types (from the manual) ====================
TXT_ORDER_BUY = "23"
TXT_ORDER_SELL = "24"
TXT_PRICE_LAST = "5"      # 最新价
TXT_PRICE_FIXED = "11"    # 指定价

DBF_PRICE_LAST = "1"      # 最新价
DBF_PRICE_FIXED = "3"     # 指定价

# 数据导出 / 持仓解析的列名候选（用户可在此补充自己的导出列名）
COL_CODE = ["证券代码", "股票代码", "代码", "合约代码", "instrument", "stock_code", "code"]
COL_VOLUME = ["股票余额", "当前拥股", "持仓数量", "证券数量", "数量", "volume", "m_nVolume"]
COL_CANUSE = ["可用余额", "可用数量", "可卖数量", "可用", "can_use", "enable_amount"]
COL_MV = ["市值", "证券市值", "参考市值", "m_dMarketValue", "market_value"]
COL_PRICE = ["最新价", "市价", "现价", "last_price", "price"]
COL_NAME = ["证券名称", "股票名称", "名称", "name"]
CASH_ALIASES = ["可用金额", "可用资金", "资金可用", "可用余额", "m_dAvailable", "available"]
ASSET_ALIASES = ["总资产", "资产总值", "总资产值", "m_dBalance", "total_asset"]


# ==================== minimal DBF (dBASE III) reader / writer (stdlib only) ====================
DBF_ENCODINGS = ("gbk", "utf-8", "latin-1")


def _dec(b):
    for enc in DBF_ENCODINGS:
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1")


def dbf_read(path):
    """Return (field_names, list_of_dict_rows, deleted_flags)."""
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < 32:
        raise ValueError("%s: too small to be a DBF" % path)
    n_records = struct.unpack("<I", raw[4:8])[0]
    header_len = struct.unpack("<H", raw[8:10])[0]
    record_len = struct.unpack("<H", raw[10:12])[0]
    fields = []
    pos = 32
    while pos < header_len - 1 and raw[pos:pos + 1] != b"\x0d":
        name = _dec(raw[pos:pos + 11].split(b"\x00")[0]).strip()
        ftype = raw[pos + 11:pos + 12].decode("latin-1")
        flen = raw[pos + 16]
        fields.append((name, ftype, flen))
        pos += 32
    rows = []
    base = header_len
    for i in range(n_records):
        rec = raw[base + i * record_len: base + (i + 1) * record_len]
        if len(rec) < record_len:
            break
        deleted = rec[0:1] == b"*"
        cur = 1
        row = {}
        for name, ftype, flen in fields:
            cell = rec[cur:cur + flen]
            cur += flen
            txt = _dec(cell).strip()
            if ftype in ("N", "F"):
                try:
                    row[name] = float(txt) if txt else 0.0
                except ValueError:
                    row[name] = txt
            else:
                row[name] = txt
        rows.append(row)
    return [f[0] for f in fields], rows, None


def dbf_write(path, columns, rows, encoding="gbk"):
    """columns: [(name, length)], rows: list of list of str (same order)."""
    header_len = 32 + 32 * len(columns) + 1
    record_len = 1 + sum(l for _n, l in columns)
    now = datetime.date.today()
    out = bytearray()
    out += struct.pack("<BBBB", 0x03, now.year - 1900, now.month, now.day)
    out += struct.pack("<I", len(rows))
    out += struct.pack("<H", header_len)
    out += struct.pack("<H", record_len)
    out += b"\x00" * 20
    for name, length in columns:
        nb = name.encode(encoding, "replace")[:11]
        out += nb + b"\x00" * (11 - len(nb))
        out += b"C" + b"\x00" * 4 + bytes([length]) + b"\x00" + b"\x00" * 14
    out += b"\x0d"
    for row in rows:
        out += b" "
        for (name, length), val in zip(columns, row):
            cell = str(val).encode(encoding, "replace")[:length]
            out += cell + b" " * (length - len(cell))
    out += b"\x1a"
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(bytes(out))
    os.replace(tmp, path)
    return path


# ==================== 市场 / 涨跌停 / 手数 ====================
def split_code(code):
    """'600000.SH' / 'SH600000' / '600000' -> (market, plain6)."""
    c = str(code).strip().upper().replace("XSHE", "SZ").replace("XSHG", "SH")
    m = re.match(r"^([A-Z]{2})[.\-_]?(\d{6})$", c)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^(\d{6})[.\-_]?([A-Z]{2})$", c)
    if m:
        return m.group(2), m.group(1)
    m = re.match(r"^(\d{6})$", c)
    if m:
        d = m.group(1)
        return ("SH" if d[0] in "56" else "SZ"), d
    return "", ""


def limit_ratio(market, plain, name=""):
    """Daily price-limit ratio by board (ST detection uses the security name)."""
    nm = (name or "").upper()
    if "ST" in nm:
        return 0.05
    if market == "SH" and plain.startswith("688"):
        return 0.20
    if market == "SZ" and plain[:3] in ("300", "301"):
        return 0.20
    if market == "BJ" or plain[:2] in ("43", "83", "87", "88", "92"):
        return 0.30
    return 0.10


def round_tick(price, tick=0.01):
    return round(round(price / tick) * tick, 2)


# ==================== quotes (external process HAS network; QMT strategy does not) ====================
class Quotes:
    """Tencent qt.gtimg.cn primary, Sina fallback. Returns last/bid1/ask1/prev_close."""

    def __init__(self, offline=None):
        self.cache = {}
        self.offline = offline or {}     # {"600000.SH": {"last":..., "prev_close":...}}

    def _key(self, code):
        mk, pl = split_code(code)
        return mk, pl

    def fetch(self, codes):
        want = []
        for c in codes:
            mk, pl = self._key(c)
            if not pl or c in self.cache:
                continue
            want.append(c)
        if want:
            for chunk in [want[i:i + 60] for i in range(0, len(want), 60)]:
                q = ",".join(("sh" if self._key(c)[0] == "SH" else "sz") + self._key(c)[1]
                             for c in chunk)
                got = self._tencent(q)
                if not got:
                    got = self._sina(q)
                for c in chunk:
                    self.cache[c] = got.get(self._key(c)[1], {})
        out = {}
        for c in codes:
            _mk, pl = self._key(c)
            q = self.cache.get(c) or self.offline.get(c) or {}
            if not q:
                q = {k: v for k, v in self.offline.items() if _mk_plain(k) == pl} or {}
            out[c] = q
        return out

    def _tencent(self, q):
        import urllib.request
        url = "http://qt.gtimg.cn/q=" + q
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                txt = r.read().decode("gbk", "ignore")
        except Exception as e:
            print("[quotes] tencent failed: %s" % e)
            return {}
        out = {}
        for line in txt.split(";"):
            m = re.search(r'v_([a-z]{2})(\d{6})="([^"]*)"', line)
            if not m:
                continue
            f = m.group(3).split("~")
            def g(i, d=0.0):
                try:
                    return float(f[i])
                except (IndexError, ValueError):
                    return d
            out[m.group(2)] = {
                "name": f[1] if len(f) > 1 else "",
                "last": g(3),
                "prev_close": g(4),
                "bid1": g(9),
                "ask1": g(19),
                "limit_up": g(47),
                "limit_down": g(48),
            }
        return out

    def _sina(self, q):
        import urllib.request
        url = "http://hq.sinajs.cn/list=" + q
        req = urllib.request.Request(url, headers={"Referer": "http://finance.sina.com.cn"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                txt = r.read().decode("gbk", "ignore")
        except Exception as e:
            print("[quotes] sina failed: %s" % e)
            return {}
        out = {}
        for line in txt.split(";"):
            m = re.search(r'hq_str_([a-z]{2})(\d{6})="([^"]*)"', line)
            if not m:
                continue
            f = m.group(3).split(",")
            if len(f) < 32:
                continue
            def g(i, d=0.0):
                try:
                    return float(f[i])
                except (IndexError, ValueError):
                    return d
            out[m.group(2)] = {
                "name": f[0], "last": g(3), "prev_close": g(2),
                "bid1": g(6), "ask1": g(7), "limit_up": 0.0, "limit_down": 0.0,
            }
        return out


def _mk_plain(code):
    return split_code(code)[1]


# ==================== 数据导出（持仓 / 资产）解析 ====================
def _pick(row, aliases):
    for a in aliases:
        for k in row:
            if k is None:
                continue
            if a == k or a in str(k):
                return row[k]
    return None


def _to_float(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def read_export_table(path):
    """Read a 数据导出 file (csv/txt/dbf) -> (headers, rows[list of dict])."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".dbf":
        names, rows, _ = dbf_read(path)
        return names, rows
    for enc in ("gbk", "utf-8-sig", "utf-8"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                if "\t" in sample and sample.count("\t") > sample.count(","):
                    rd = csv.DictReader(f, delimiter="\t")
                else:
                    rd = csv.DictReader(f)
                rows = [dict(r) for r in rd]
            if rows and len(rows[0]) > 1:
                return list(rows[0].keys()), rows
        except (UnicodeDecodeError, csv.Error, StopIteration):
            continue
    return [], []


def _newest(folder, patterns):
    hits = []
    for pat in patterns:
        hits += glob.glob(os.path.join(folder, pat))
    hits = [h for h in hits if os.path.isfile(h)]
    if not hits:
        return None
    return max(hits, key=os.path.getmtime)


def load_state(cfg, verbose=True):
    """Return dict: positions {code: {...}}, cash, total_asset, sources."""
    ex = cfg["export_dir"]
    state = {"positions": {}, "cash": 0.0, "total_asset": 0.0, "sources": {}}
    if not os.path.isdir(ex):
        raise SystemExit("export_dir not found: %s\n"
                         "Set it in %s to the folder configured in QMT 设置->数据导出." % (ex, cfg.get("_config_path", "?")))

    pos_file = _newest(ex, ["*持仓*", "*position*", "*Position*", "*POSITION*"])
    cash_file = _newest(ex, ["*资产*", "*资金*", "*account*", "*asset*", "*Asset*"])
    if pos_file is None:
        pos_file = _newest(ex, ["*.csv", "*.txt", "*.dbf"])
    state["sources"]["positions"] = pos_file
    state["sources"]["cash"] = cash_file

    if pos_file:
        headers, rows = read_export_table(pos_file)
        if verbose:
            print("[state] positions file: %s" % pos_file)
            print("[state] columns: %s" % headers)
        for r in rows:
            code = _pick(r, COL_CODE)
            if not code:
                continue
            mk, pl = split_code(code)
            if not pl:
                continue
            full = "%s.%s" % (pl, mk)
            vol = _to_float(_pick(r, COL_VOLUME))
            if vol <= 0:
                continue
            state["positions"][full] = {
                "code": full,
                "name": str(_pick(r, COL_NAME) or ""),
                "volume": int(vol),
                "can_use": int(_to_float(_pick(r, COL_CANUSE)) or vol),
                "market_value": _to_float(_pick(r, COL_MV)),
                "last": _to_float(_pick(r, COL_PRICE)),
            }
    if cash_file:
        headers, rows = read_export_table(cash_file)
        if verbose:
            print("[state] cash file: %s columns: %s" % (cash_file, headers))
        for r in rows:
            c = _pick(r, CASH_ALIASES)
            a = _pick(r, ASSET_ALIASES)
            if c is not None:
                state["cash"] = _to_float(c)
            if a is not None:
                state["total_asset"] = _to_float(a)
            if c is not None or a is not None:
                break
    # fall back: derive total asset from positions market value + cash
    if state["total_asset"] <= 0 and state["positions"]:
        state["total_asset"] = sum(p["market_value"] for p in state["positions"].values()) + state["cash"]
    return state


# ==================== 目标组合 & 差额（沿用原 executor 的资金算法） ====================
def build_plan(cfg, pool, state, quotes):
    strat = cfg
    positions = state["positions"]
    total_asset = state["total_asset"]
    cash = state["cash"]
    if total_asset <= 0:
        raise SystemExit("total asset is 0 - check the 数据导出 资产 file / column mapping")

    candidate_pool = pool[:strat.get("candidate_pool_size", len(pool))]
    buy_pool = pool[:strat.get("max_holdings", len(pool))]

    reserve = total_asset * strat.get("cash_reserve_ratio", 0.0)
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / float(strat.get("max_holdings", 1) or 1)

    def px(code):
        q = quotes.get(code) or {}
        return q

    orders = []
    notes = []

    # --- sells: out of pool, then over-allocated ---
    for code, pos in sorted(positions.items()):
        q = px(code)
        last = q.get("last") or pos.get("last") or 0.0
        mv = pos["market_value"] or (last * pos["volume"])
        if code not in candidate_pool:
            if strat.get("limit_check", True) and q.get("limit_up") and last:
                if abs(last - q["limit_up"]) < 0.011:
                    notes.append("%s 涨停不卖" % code)
                    continue
            vol = pos["can_use"] // 100 * 100
            if vol > 0:
                orders.append({"side": "sell", "code": code, "volume": vol,
                               "reason": "池外", "price": last})
            continue
        if mv > target_per_stock and last > 0:
            if strat.get("limit_check", True) and q.get("limit_up") and abs(last - q["limit_up"]) < 0.011:
                notes.append("%s 涨停不卖" % code)
                continue
            value_sell = mv - target_per_stock
            vol = int(value_sell // (last * 100)) * 100
            vol = min(vol, pos["can_use"] // 100 * 100)
            if vol > 0:
                orders.append({"side": "sell", "code": code, "volume": vol,
                               "reason": "超配", "price": last})

    # --- buys: fill missing slots from buy_pool, equal money per slot ---
    held = set(positions.keys())
    slots = strat.get("max_holdings", 0) - len(held)
    avail = max(cash - reserve, 0.0)
    if slots > 0 and avail > 0:
        candidates = [c for c in buy_pool if c not in held][:slots]
        per_stock = (avail / slots) if slots else 0.0
        budget = avail
        for code in candidates:
            q = px(code)
            last = q.get("last") or 0.0
            if last <= 0:
                notes.append("%s 无行情，跳过" % code)
                continue
            if strat.get("limit_check", True) and q.get("limit_down") and abs(last - q["limit_down"]) < 0.011:
                notes.append("%s 跌停不买" % code)
                continue
            # 价格笼子：对手价 ±2% 或 ±0.1 元，取更保守者，且不超过涨跌停
            ask = q.get("ask1") or last
            cage = min(ask * 1.02, ask + 0.1)
            if q.get("limit_up"):
                cage = min(cage, q["limit_up"])
            price = round_tick(max(min(cage, q.get("limit_up") or cage), 0.01))
            amount = min(per_stock, budget)
            vol = int((amount * 0.99) // (price * 100)) * 100
            if vol <= 0:
                notes.append("%s 资金不足一手" % code)
                continue
            orders.append({"side": "buy", "code": code, "volume": vol,
                           "reason": "建仓", "price": price})
            budget -= vol * price * 1.001

    # --- also top up under-allocated holdings (rebalance) ---
    for code, pos in sorted(positions.items()):
        if code not in buy_pool:
            continue
        q = px(code)
        last = q.get("last") or 0.0
        mv = pos["market_value"] or (last * pos["volume"])
        if last <= 0 or mv >= target_per_stock:
            continue
        need = target_per_stock - mv
        ask = q.get("ask1") or last
        cage = min(ask * 1.02, ask + 0.1)
        if q.get("limit_up"):
            cage = min(cage, q["limit_up"])
        price = round_tick(max(cage, 0.01))
        amount = min(need, max(avail, 0.0), budget)
        vol = int((amount * 0.99) // (price * 100)) * 100
        if vol > 0:
            orders.append({"side": "buy", "code": code, "volume": vol,
                           "reason": "补仓", "price": price})
            budget -= vol * price * 1.001

    return {"orders": orders, "notes": notes,
            "total_asset": total_asset, "cash": cash, "reserve": reserve,
            "target_per_stock": target_per_stock,
            "candidate_pool": candidate_pool, "buy_pool": buy_pool}


# ==================== emitters ====================
REASON_ASCII = {"池外": "pool_out", "超配": "over", "建仓": "new", "补仓": "top_up"}


def _note(cfg, reason):
    """投资备注. ASCII by default: the protocol file then has no encoding ambiguity.
    Set note_language='cn' to keep the Chinese reason (file is written as GBK)."""
    if cfg.get("note_language") == "cn":
        tail = reason
    else:
        tail = REASON_ASCII.get(reason, reason)
    return ("%s_%s" % (cfg.get("strategy_name", "strat"), tail))[:32]


def emit_txt(cfg, plan, when):
    """便捷交易 protocol: 下单类型,通道号,交易市场,交易代码,交易数量,报价类型,交易价格[,投资备注]"""
    lines = []
    for o in plan["orders"]:
        mk, pl = split_code(o["code"])
        otype = TXT_ORDER_BUY if o["side"] == "buy" else TXT_ORDER_SELL
        note = _note(cfg, o["reason"])
        price = o["price"] if cfg.get("txt_use_fixed_price", True) else 0
        ptype = TXT_PRICE_FIXED if price else TXT_PRICE_LAST
        lines.append(",".join([otype, str(cfg.get("channel", "0")), mk, pl,
                               str(o["volume"]), ptype, ("%.2f" % price) if price else "0",
                               note]))
    if not lines:
        return None
    folder = cfg["fileorder_dir"]
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "%s_%s.txt" % (cfg.get("strategy_name", "order"), when))
    tmp = path + ".tmp"
    payload = "\n".join(lines) + "\n"
    enc = cfg.get("txt_encoding")
    if not enc:
        try:
            payload.encode("ascii")
            enc = "ascii"
        except UnicodeEncodeError:
            enc = "gbk"          # Chinese 投资备注 -> the client is a zh-CN application
    try:
        with open(tmp, "w", encoding=enc, newline="\n") as f:
            f.write(payload)
        os.replace(tmp, path)
    except Exception as e:
        print("[emit_txt] FAILED: %s" % e)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None
    return path


DBF_COLUMNS = [("order_type", 4), ("price_type", 4), ("mode_price", 12),
               ("stock_code", 12), ("volume", 12), ("account_id", 24),
               ("acc_type", 4), ("brokertype", 4), ("strategy", 24), ("note", 32)]


def emit_dbf(cfg, plan, when):
    """批量预埋单 order file (field order per manual p.329-331)."""
    rows = []
    for o in plan["orders"]:
        mk, pl = split_code(o["code"])
        rows.append([
            TXT_ORDER_BUY if o["side"] == "buy" else TXT_ORDER_SELL,
            DBF_PRICE_FIXED if cfg.get("dbf_use_fixed_price", True) else DBF_PRICE_LAST,
            ("%.2f" % o["price"]) if cfg.get("dbf_use_fixed_price", True) else "",
            mk + pl,
            str(o["volume"]),
            str(cfg.get("account_id", "")),
            str(cfg.get("acc_type", "49")),
            str(cfg.get("brokertype", "2")),
            str(cfg.get("strategy_name", ""))[:24],
            _note(cfg, o["reason"]),
        ])
    if not rows:
        return None
    folder = cfg["preorder_dir"]
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "%s_%s.dbf" % (cfg.get("strategy_name", "order"), when))
    try:
        dbf_write(path, DBF_COLUMNS, rows)
    except Exception as e:
        print("[emit_dbf] FAILED: %s" % e)
        return None
    return path


def read_feedback(cfg, verbose=True):
    outs = []
    for folder in [cfg.get("preorder_dir"), cfg.get("fileorder_dir")]:
        if not folder or not os.path.isdir(folder):
            continue
        for p in sorted(glob.glob(os.path.join(folder, "*_result.dbf"))):
            try:
                names, rows, _ = dbf_read(p)
            except Exception as e:
                outs.append((p, "read failed: %s" % e))
                continue
            if verbose:
                print("[feedback] %s (%d rows)" % (p, len(rows)))
                for r in rows[-10:]:
                    print("    ORDERID=%s STATUS=%s MARKET=%s SYSID=%s MSG=%s"
                          % (r.get("ORDERID"), r.get("STATUS"), r.get("MARKET"),
                             r.get("ORDERSYSID"), r.get("MESSAGE")))
            outs.append((p, rows))
    if not outs and verbose:
        print("[feedback] no *_result.dbf found - did the 预埋单 monitor actually run?")
    return outs


# ==================== config ====================
DEFAULT_CONFIG = {
    "account_id": "",
    "acc_type": "49",
    "brokertype": "2",
    "channel": "0",
    "strategy_name": "low_valuation",
    "export_dir": "",
    "fileorder_dir": "",
    "preorder_dir": "",
    "emit": "both",
    "max_holdings": 8,
    "candidate_pool_size": 13,
    "cash_reserve_ratio": 0.0125,
    "rebalance_threshold": 0.20,
    "limit_check": True,
    "txt_use_fixed_price": True,
    "dbf_use_fixed_price": True,
    "note_language": "ascii",
    "txt_encoding": None,
    "_note": "fileorder/preorder/export dirs are the folders you configure INSIDE the QMT client "
             "(便捷交易文件路径 / 批量预埋单监控路径 / 数据导出保存路径). Keep this file out of git."
}


def load_cfg(path):
    cfg = dict(DEFAULT_CONFIG)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
        cfg["_config_path"] = path
    return cfg


def load_pool(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    codes = data.get("stocks") if isinstance(data, dict) else data
    out = []
    for c in codes or []:
        mk, pl = split_code(c)
        if pl:
            out.append("%s.%s" % (pl, mk))
    return out


# ==================== main ====================
def main():
    ap = argparse.ArgumentParser(description="external rebalance over QMT file-order channels")
    ap.add_argument("--config", default="qmt_fileorder_config.json")
    ap.add_argument("--pool", default=None, help="rebalance_*.json produced by qmt_stdqmt_target.py")
    ap.add_argument("--inspect", action="store_true", help="dump export dir contents and parsed state")
    ap.add_argument("--feedback", action="store_true", help="read *_result.dbf feedback files")
    ap.add_argument("--execute", action="store_true",
                    help="actually write order files into the QMT folders (default is dry-run)")
    ap.add_argument("--emit", choices=["txt", "dbf", "both"], default=None)
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    if args.emit:
        cfg["emit"] = args.emit

    print("=" * 72)
    print("QMT file-order bridge  (%s)" % ("EXECUTE" if args.execute else "DRY-RUN"))
    print("=" * 72)
    for k in ("account_id", "export_dir", "fileorder_dir", "preorder_dir", "emit"):
        print("  %-16s %s" % (k, cfg.get(k)))
    if not cfg.get("export_dir"):
        print("\n!! export_dir is empty. Create %s first (see --help header)." % args.config)
        return 2

    if args.inspect:
        print("\n--- export dir listing ---")
        for p in sorted(glob.glob(os.path.join(cfg["export_dir"], "*"))):
            print("  %8d  %s" % (os.path.getsize(p) if os.path.isfile(p) else 0, os.path.basename(p)))
        if args.feedback:
            read_feedback(cfg)
        try:
            st = load_state(cfg)
        except SystemExit as e:
            print(e)
            return 2
        print("\n--- parsed state ---")
        print("  total_asset=%.2f cash=%.2f positions=%d" % (st["total_asset"], st["cash"], len(st["positions"])))
        for c, p in sorted(st["positions"].items()):
            print("    %-12s vol=%-8d can_use=%-8d mv=%.2f last=%.2f"
                  % (c, p["volume"], p["can_use"], p["market_value"], p["last"]))
        print("\nIf the columns above look wrong, fix COL_* alias lists at the top of this file.")
        return 0

    if args.feedback and not args.pool:
        read_feedback(cfg)
        return 0

    if not args.pool:
        ap.print_help()
        return 2
    pool = load_pool(args.pool)
    print("\npool: %d codes -> %s" % (len(pool), pool[:8]))

    state = load_state(cfg)
    print("state: total_asset=%.2f cash=%.2f positions=%d" % (state["total_asset"], state["cash"], len(state["positions"])))

    codes = set(pool) | set(state["positions"].keys())
    quotes = Quotes().fetch(sorted(codes))
    for c in sorted(codes):
        q = quotes.get(c) or {}
        if not q.get("last"):
            print("  [warn] no quote for %s" % c)

    plan = build_plan(cfg, pool, state, quotes)
    print("\ntarget_per_stock=%.2f reserve=%.2f" % (plan["target_per_stock"], plan["reserve"]))
    print("orders: %d" % len(plan["orders"]))
    for o in plan["orders"]:
        print("  %-4s %-12s %8d sh @ %8.2f   (%s)"
              % (o["side"].upper(), o["code"], o["volume"], o["price"], o["reason"]))
    for n in plan["notes"]:
        print("  note: %s" % n)
    if not plan["orders"]:
        print("nothing to do (already balanced) -> no file written")
        return 0

    when = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if not args.execute:
        print("\nDRY-RUN: would write ->")
        if cfg["emit"] in ("txt", "both"):
            print("    %s\\%s_%s.txt   (便捷交易)"
                  % (cfg.get("fileorder_dir") or "<fileorder_dir?>", cfg["strategy_name"], when))
        if cfg["emit"] in ("dbf", "both"):
            print("    %s\\%s_%s.dbf   (批量预埋单)"
                  % (cfg.get("preorder_dir") or "<preorder_dir?>", cfg["strategy_name"], when))
        print("Re-run with --execute to place these orders.")
        return 0

    written = []
    if cfg["emit"] in ("txt", "both") and cfg.get("fileorder_dir"):
        written.append(emit_txt(cfg, plan, when))
    if cfg["emit"] in ("dbf", "both") and cfg.get("preorder_dir"):
        written.append(emit_dbf(cfg, plan, when))
    ok = [w for w in written if w]
    for w in ok:
        print("WROTE %s" % w)
    if len(ok) != len(written):
        print("!! one or more order files were NOT written - nothing may have been sent")
        return 1
    print("\nThe QMT client should pick the file up within its scan interval and delete it.")
    print("Then check: python %s --feedback" % os.path.basename(__file__))
    return 0


if __name__ == "__main__":
    sys.exit(main())
