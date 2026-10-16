# -*- coding: utf-8 -*-
"""
qmt_basket_bridge.py - publish a stock pool as a QMT 组合交易 basket (EXTERNAL process).

WHY
  QMT's 组合交易 (basket trading) can be driven entirely by CSV files, and the manual
  documents a folder watcher for it:

    启用篮子自动导入 (manual p.364, settings item 17)
      "勾选篮子自动导入并选择路径后，组合交易中的篮子管理内自动导入一栏会将文件夹里的
       篮子自动导入（股票和期货篮子都支持，仅支持CSV文件）。当勾选'自动用最新篮子填充
       组合交易'，下单面板中选择篮子选项会自动填入最新的篮子。"

    合法篮子导入格式为迅投默认格式，在 excel 表格中新建篮子时…保存为 .csv (manual p.177)

  So: this script drops a basket CSV into the watched folder and the client imports it
  by itself - no strategy, no sandbox, no human "import" click.

  After that one human step remains (the client has no scheduled 调仓):
    组合交易 -> 一键买卖 -> 调仓 -> select account -> select this target basket
             -> set 交易总量 -> 确定 -> 下单
  The client then computes the 当前持仓 vs 目标持仓 difference and the buy/sell
  direction for every line by itself (manual p.183-185).

EQUAL WEIGHT
  Use 按股票权重 in the 调仓 panel and every row carries the same 相对权重:
      分配量 = 总金额 × (某支股票相对权重 / 相对权重合计) / 最新价      (manual p.179)
  Equal weights -> equal money per stock = your "每个策略平均分配内部仓位".
  (调仓 supports only 按股票数量 / 按股票权重 - manual p.185.)

USAGE
  python qmt_basket_bridge.py --templates
  python qmt_basket_bridge.py --pool qmt_exchange/rebalance_low_valuation_xxx.json --dir <auto-import folder>
  python qmt_basket_bridge.py --pool <file.json> --dir <folder> --execute
  python qmt_basket_bridge.py --codes "600000.SH,000001.SZ" --dir <folder> --quantity 100 --execute
"""

import os
import re
import csv
import sys
import glob
import json
import argparse
import datetime

DEFAULT_TEMPLATE_DIR = r"D:\gjzq\qmt_test_gj\config\help\baskethelp"

# official header -> fields we fill
HEADER_DEFAULT = ["代码", "市场", "数量", "相对权重", "方向", "量比"]
HEADER_ACCOUNT = ["资金账号", "代码", "市场", "数量", "相对权重", "方向", "量比"]
TEMPLATE_DEFAULT = "默认篮子格式.csv"
TEMPLATE_ACCOUNT = "指定账号默认篮子格式.csv"


def split_code(code):
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


def load_pool(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    codes = data.get("stocks") if isinstance(data, dict) else data
    out, seen = [], set()
    for c in codes or []:
        mk, pl = split_code(c)
        if pl and pl not in seen:
            seen.add(pl)
            out.append((mk, pl))
    return out


def show_templates(folder):
    if not os.path.isdir(folder):
        print("template folder not found: %s" % folder)
        return 1
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        try:
            txt = open(p, "rb").read().decode("gbk")
        except UnicodeDecodeError:
            txt = open(p, "rb").read().decode("utf-8", "ignore")
        print("=" * 70)
        print(name)
        print("-" * 70)
        print(txt.strip()[:900])
    return 0


def write_basket(folder, basket_name, rows, header, encoding, dry_run):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, basket_name + ".csv")
    tmp = path + ".tmp"
    if dry_run:
        print("DRY-RUN would write %s" % path)
        print("  header: %s" % ",".join(header))
        for r in rows[:10]:
            print("  row   : %s" % ",".join(str(x) for x in r))
        if len(rows) > 10:
            print("  ... %d more rows" % (len(rows) - 10))
        return path
    # newline="" + explicit \r\n keeps Excel/QMT happy; the official samples are CRLF
    with open(tmp, "w", encoding=encoding, newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)
    return path


def prune(folder, prefix, keep):
    if not keep or keep <= 0:
        return []
    hits = sorted(glob.glob(os.path.join(folder, prefix + "*.csv")), key=os.path.getmtime)
    removed = []
    for p in hits[:-keep]:
        try:
            os.remove(p)
            removed.append(os.path.basename(p))
        except OSError:
            pass
    return removed


def main():
    ap = argparse.ArgumentParser(description="publish a pool as a QMT 组合交易 basket CSV")
    ap.add_argument("--dir", default=None,
                    help="the folder you configured in QMT 设置->启用篮子自动导入")
    ap.add_argument("--template-dir", default=DEFAULT_TEMPLATE_DIR)
    ap.add_argument("--templates", action="store_true", help="show the 6 official basket CSV templates")
    ap.add_argument("--pool", default=None, help="rebalance_*.json (uses its 'stocks')")
    ap.add_argument("--codes", default=None, help="comma separated codes")
    ap.add_argument("--name", default=None, help="basket name (= csv file name); default <strategy>_<date>")
    ap.add_argument("--strategy", default="low_valuation")
    ap.add_argument("--quantity", type=int, default=0,
                    help="fill 数量 with this many shares (0 = pure weight basket, for 按股票权重)")
    ap.add_argument("--weight", default="1.000", help="相对权重 per row (equal by default)")
    ap.add_argument("--account-key", default=None,
                    help="account key/资金账号 -> use the 指定账号 template (one account per row)")
    ap.add_argument("--encoding", default="gbk", choices=["gbk", "utf-8-sig", "utf-8"])
    ap.add_argument("--keep", type=int, default=5, help="keep only the newest N baskets made by this script")
    ap.add_argument("--execute", action="store_true", help="actually write the CSV (default dry-run)")
    args = ap.parse_args()

    if args.templates:
        return show_templates(args.template_dir)

    if args.pool:
        codes = load_pool(args.pool)
    elif args.codes:
        codes, seen = [], set()
        for c in args.codes.split(","):
            mk, pl = split_code(c)
            if pl and pl not in seen:
                seen.add(pl)
                codes.append((mk, pl))
    else:
        ap.print_help()
        return 2

    if not codes:
        print("empty pool -> nothing to publish (in the old system an empty list meant 清仓)")
        return 1

    if not args.dir:
        print("!! --dir is required: it is the folder configured in QMT 设置->启用篮子自动导入")
        return 2

    basket = args.name or ("%s_%s" % (args.strategy, datetime.date.today().strftime("%Y%m%d")))
    weight = args.weight
    rows = []
    if args.account_key:
        header = HEADER_ACCOUNT
        for mk, pl in codes:
            rows.append([args.account_key, pl, mk, args.quantity, weight, 0, 0])
    else:
        header = HEADER_DEFAULT
        for mk, pl in codes:
            rows.append([pl, mk, args.quantity, weight, 0, 0])

    print("basket  : %s   (%d stocks, %s)" % (basket, len(rows), "指定账号" if args.account_key else "默认"))
    print("target  : %s" % os.path.join(args.dir, basket + ".csv"))
    print("mode    : %s" % ("按股票数量 (数量=%d)" % args.quantity if args.quantity else
                            "按股票权重 (相对权重全为 %s -> 等权)" % weight))
    path = write_basket(args.dir, basket, rows, header, args.encoding, dry_run=not args.execute)

    if args.execute:
        back = open(path, "rb").read()
        print("wrote %s (%d bytes, %s)" % (path, len(back), args.encoding))
        rm = prune(args.dir, args.strategy, args.keep)
        if rm:
            print("pruned old baskets: %s" % ", ".join(rm))
        print()
        print("Then in QMT (one time per rebalance, ~15 seconds):")
        print("  交易 -> 组合交易 -> 一键买卖 -> 调仓")
        print("   1) click the account on the left (当前持仓 appears)")
        print("   2) pick target basket %r on the right (目标持仓)" % basket)
        print("   3) choose 按股票权重, set 交易总量, 确定")
        print("   4) 下单  -> the client computes the diff and the buy/sell direction itself")
    else:
        print("\nRe-run with --execute to write it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
