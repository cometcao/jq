# -*- coding: utf-8 -*-
"""
qmt_sector_bridge.py - publish a stock list into a QMT custom sector (EXTERNAL process).

WHY
  QMT custom sectors are stored as plain text files:

      <QMT install>\\datadir\\Sector\\<group>\\<sector name>

  containing comma-separated suffixed codes, e.g. "600000.SH,000001.SZ" (UTF-8,
  no trailing newline). A strategy running inside QMT can read such a sector with
  ContextInfo.get_stock_list_in_sector("<sector name>") - a NATIVE API call that
  needs no file I/O at all.

  So this script replaces the qmt_exchange/rebalance_*.json file bridge:
      target process (has email + AI + network)
        -> qmt_sector_bridge.py  writes datadir\\Sector\\我的\\<sector>
        -> executor inside QMT calls get_stock_list_in_sector("<sector>")

  Nothing inside QMT opens a file, and nothing inside QMT touches the network.

IMPORTANT
  * Only the CONTENT file is written here; sectorConfig.xml (the index) is NOT
    touched. That is deliberate: some sectorConfig.xml files in the wild are
    GBK-encoded while declaring utf-8, so editing them is a trap. Create the
    sector ONCE in the QMT GUI (板块 -> 我的 -> 新建), then only ever rewrite its
    content file from here.
  * Writing the file is not guaranteed to be picked up by a running client.
    Run `qmt_channel_probe.py` with WATCH_SECTOR_NAME set to find out whether the
    sector hot-reloads or needs a client restart (see QMT_CHANNEL_FALLBACK_OPTIONS.md).

USAGE
  python qmt_sector_bridge.py --list
  python qmt_sector_bridge.py --read 我的自选
  python qmt_sector_bridge.py --write 我的自选 --from-json qmt_exchange/rebalance_low_valuation_20260916_0925.json
  python qmt_sector_bridge.py --write 我的自选 --codes "600000.SH,000001.SZ"
  python qmt_sector_bridge.py --from-json <rebalance.json> --export-txt qmt_exchange/basket.txt
  (--sector-root overrides the sector store root; --dry-run prints without writing)
"""

import os
import sys
import json
import time
import shutil
import argparse

DEFAULT_SECTOR_ROOT = r"D:\gjzq\qmt_test_gj\datadir\Sector"
CONFIG_NAME = "sectorConfig.xml"


# ==================== xml helpers (no third-party deps) ====================
def _read_text(path):
    """Read a QMT text file: it may be utf-8 or gbk regardless of its declaration."""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"


def _sector_names_from_config(path):
    """Names of the <Item ... type="2"> entries = actual sectors in this group."""
    names = []
    try:
        text, _enc = _read_text(path)
    except OSError:
        return names
    import re
    for m in re.finditer(r'<Item\b[^>]*\bname="([^"]*)"[^>]*>', text):
        tag = m.group(0)
        if 'type="2"' in tag:
            names.append(m.group(1))
    return names


def discover(root):
    """Return {sector_name: (group_dir, content_path)} for every registered sector."""
    found = {}
    if not os.path.isdir(root):
        return found
    for group in sorted(os.listdir(root)):
        gdir = os.path.join(root, group)
        if not os.path.isdir(gdir):
            continue
        cfg = os.path.join(gdir, CONFIG_NAME)
        if not os.path.isfile(cfg):
            continue
        for name in _sector_names_from_config(cfg):
            found[name] = (gdir, os.path.join(gdir, name))
    return found


# ==================== code list helpers ====================
def normalize_codes(codes):
    """Keep only real suffixed A-share style codes, dedupe, preserve order."""
    seen = set()
    out = []
    for c in codes:
        c = str(c).strip().strip('"').strip("'")
        if not c:
            continue
        c = c.replace("XSHE", "SZ").replace("XSHG", "SH")
        if "." not in c and len(c) == 6:
            c = c + (".SH" if c[0] in "56" else ".SZ")
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def codes_from_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("stocks") or []
    return normalize_codes(data)


def codes_from_file(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    return normalize_codes(raw.replace("\n", ",").split(","))


# ==================== write ====================
def write_sector(content_path, codes, dry_run=False, backup=True):
    payload = ",".join(codes)          # QMT format: comma separated, no trailing newline
    old = None
    if os.path.isfile(content_path):
        with open(content_path, "rb") as f:
            old = f.read()
    if backup and old is not None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        shutil.copyfile(content_path, content_path + ".bak_" + stamp)
    if dry_run:
        return payload
    tmp = content_path + ".tmp"
    # newline="" so no platform newline is appended; QMT writes it the same way
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(payload)
    os.replace(tmp, content_path)
    return payload


def read_sector(content_path):
    if not os.path.isfile(content_path):
        return None
    text, _enc = _read_text(content_path)
    return [c for c in text.strip().split(",") if c]


def export_txt(codes, path):
    """Tongdaxin-style import file (market prefix 1=SH 0=SZ) for the GUI route."""
    lines = []
    for c in codes:
        code, _, mkt = c.partition(".")
        prefix = "1" if mkt.upper() == "SH" else "0"
        lines.append(prefix + code)
    with open(path, "w", encoding="gbk", newline="\r\n") as f:
        f.write("\n".join(lines))
    return path


# ==================== commands ====================
def cmd_list(root):
    sectors = discover(root)
    if not sectors:
        print("no sector store found under %s" % root)
        return 1
    print("%-24s %-10s %-8s %s" % ("sector", "group", "codes", "content file"))
    for name, (gdir, cpath) in sorted(sectors.items()):
        codes = read_sector(cpath)
        n = "-" if codes is None else str(len(codes))
        print("%-24s %-10s %-8s %s" % (name, os.path.basename(gdir), n, cpath))
    return 0


def main():
    ap = argparse.ArgumentParser(description="publish a stock list into a QMT custom sector")
    ap.add_argument("--sector-root", default=os.environ.get("QMT_SECTOR_ROOT", DEFAULT_SECTOR_ROOT))
    ap.add_argument("--sector", default=None, help="target sector name, e.g. 我的自选")
    ap.add_argument("--list", action="store_true", help="list registered sectors and their content")
    ap.add_argument("--read", metavar="NAME", default=None, help="print a sector's current codes")
    ap.add_argument("--write", metavar="NAME", default=None, help="write codes into this sector")
    ap.add_argument("--codes", default=None, help="comma separated codes")
    ap.add_argument("--from-file", default=None, help="text file with comma/newline separated codes")
    ap.add_argument("--from-json", default=None,
                    help="rebalance_*.json produced by qmt_stdqmt_target.py (uses its 'stocks')")
    ap.add_argument("--export-txt", default=None, help="also write a Tongdaxin-import txt here")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    if args.list:
        return cmd_list(args.sector_root)

    if args.read:
        sectors = discover(args.sector_root)
        if args.read not in sectors:
            print("sector %r not registered in %s" % (args.read, args.sector_root))
            print("registered: %s" % ", ".join(sorted(sectors)))
            return 2
        _gdir, cpath = sectors[args.read]
        codes = read_sector(cpath)
        if codes is None:
            print("sector %r content file does not exist yet: %s (empty sector)" % (args.read, cpath))
            return 0
        print("%d codes: %s" % (len(codes), ",".join(codes)))
        return 0

    if args.from_json:
        codes = codes_from_json(args.from_json)
    elif args.from_file:
        codes = codes_from_file(args.from_file)
    elif args.codes:
        codes = normalize_codes(args.codes.split(","))
    else:
        codes = None

    if args.export_txt:
        if not codes:
            print("--export-txt needs --from-json / --from-file / --codes")
            return 2
        export_txt(codes, args.export_txt)
        print("tongdaxin import file: %s (%d lines)" % (args.export_txt, len(codes)))
        if not (args.write or args.sector):
            return 0        # export-only run: no sector needed

    target = args.write or args.sector
    if not target:
        if args.export_txt:
            return 0
        ap.print_help()
        return 2

    if not codes:
        print("nothing to write: pass --from-json / --from-file / --codes")
        return 2

    sectors = discover(args.sector_root)
    if target not in sectors:
        print("REFUSING: sector %r is not registered in %s" % (target, args.sector_root))
        print("Create it once in the QMT GUI (板块 -> 我的 -> 新建/重命名), then rerun.")
        print("registered sectors: %s" % ", ".join(sorted(sectors)))
        return 3

    _gdir, cpath = sectors[target]
    payload = write_sector(cpath, codes, dry_run=args.dry_run, backup=not args.no_backup)
    print("%s %s: %d codes -> %s"
          % ("DRY-RUN would write" if args.dry_run else "wrote", target, len(codes), cpath))
    if args.dry_run:
        print(payload[:200] + ("..." if len(payload) > 200 else ""))
    else:
        back = read_sector(cpath) or []
        ok = back == codes
        print("verify: read back %d codes, match=%s" % (len(back), ok))
        if not ok:
            return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
