# -*- coding: utf-8 -*-
"""
qmt_manual_extract.py - extract searchable text from the bundled QMT manual PDF.

WHY
  config\\help\\systemfunction\\迅投QMT极速策略交易系统说明文档.pdf (64 MB, 472 pages) is the
  authoritative reference for client features - 组合交易, 便捷交易/文件单, 批量预埋单,
  数据导出, 篮子自动导入, multi-account routing and so on. But its Chinese text is stored
  as FONT GLYPH IDs (the outline titles even carry raw glyph ids inside the UTF-16 strings),
  so pdftotext-style tools and plain text search both fail on it.

  This script rebuilds the text with no third-party dependency:
    1. parse the PDF objects and inflate every FlateDecode stream
    2. collect each font's /ToUnicode CMap (CID -> Unicode)
    3. walk /Type /Page objects, decode the hex strings in their content streams
       (Identity-H => 2-byte CIDs => 4 hex chars per character)

USAGE
  python qmt_manual_extract.py --toc
  python qmt_manual_extract.py --search 便捷交易
  python qmt_manual_extract.py --search 篮子 调仓 --context 300
  python qmt_manual_extract.py --page 329
  python qmt_manual_extract.py --dump qmt_manual.txt      # full text for grep/editor search
"""

import os
import re
import sys
import zlib
import argparse

DEFAULT_PDF = r"D:\gjzq\qmt_test_gj\config\help\systemfunction\迅投QMT极速策略交易系统说明文档.pdf"


# ==================== PDF plumbing ====================
class Pdf(object):
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.raw = f.read()
        self.seg = {}
        starts = [(m.start(), int(m.group(1)))
                  for m in re.finditer(rb"(?<![0-9])(\d+)\s+0\s+obj\b", self.raw)]
        for i, (s, num) in enumerate(starts):
            e = starts[i + 1][0] if i + 1 < len(starts) else len(self.raw)
            self.seg[num] = (s, e)
        self._cmap = None
        self._texts = None

    def body(self, n):
        s, e = self.seg.get(n, (0, 0))
        return self.raw[s:e]

    def stream(self, n):
        b = self.body(n)
        i = b.find(b"stream")
        if i < 0:
            return None
        d = b[i + 6:]
        if d[:2] == b"\r\n":
            d = d[2:]
        elif d[:1] in (b"\n", b"\r"):
            d = d[1:]
        j = d.rfind(b"endstream")
        if j >= 0:
            d = d[:j]
        try:
            return zlib.decompress(d)
        except zlib.error:
            return d

    def cmap(self):
        if self._cmap is not None:
            return self._cmap
        master = {}
        refs = sorted(set(int(x) for x in re.findall(rb"/ToUnicode\s+(\d+)\s+0\s+R", self.raw)))
        for r in refs:
            d = self.stream(r)
            if not d:
                continue
            for blk in re.findall(rb"beginbfchar(.*?)endbfchar", d, re.S):
                for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
                    master[int(a, 16)] = bytes.fromhex(b.decode()).decode("utf-16-be", "ignore")
            for blk in re.findall(rb"beginbfrange(.*?)endbfrange", d, re.S):
                for a, b, c in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
                    lo, hi, st = int(a, 16), int(b, 16), int(c, 16)
                    for i in range(lo, min(hi, lo + 5000) + 1):
                        master[i] = chr(st + (i - lo))
        self._cmap = master
        return master

    def _decode_hex(self, h):
        m = self.cmap()
        return "".join(m.get(int(h[i:i + 4], 16), "") for i in range(0, len(h) - 3, 4))

    def page_text(self, data):
        parts = []
        for m in re.finditer(rb"<([0-9A-Fa-f\s]+)>|\(((?:[^()\\]|\\.)*)\)", data):
            if m.group(1):
                h = re.sub(rb"\s", b"", m.group(1)).decode()
                h = h[:len(h) // 4 * 4]
                parts.append(self._decode_hex(h))
            else:
                parts.append(m.group(2).decode("latin-1"))
        return "".join(parts)

    def pages(self):
        """{page_no: text} in object order."""
        if self._texts is not None:
            return self._texts
        out = {}
        idx = 0
        for n in sorted(self.seg):
            b = self.body(n)
            if not re.search(rb"/Type\s*/Page[^s]", b):
                continue
            idx += 1
            m = re.search(rb"/Contents\s+(\d+)\s+0\s+R", b)
            if not m:
                continue
            d = self.stream(int(m.group(1)))
            if d:
                out[idx] = self.page_text(d)
        self._texts = out
        return out

    def toc(self):
        titles = []
        for m in re.finditer(rb"/Title\s*\(((?:[^()\\]|\\.)*)\)", self.raw):
            s = m.group(1)
            if s[:2] != b"\xfe\xff":
                continue
            b = s[2:]
            out = []
            for i in range(0, len(b) - 1, 2):
                u = (b[i] << 8) | b[i + 1]
                out.append(" " if u == 0 else (chr(u) if u < 128 else self.cmap().get(u, "\ufffd")))
            titles.append("".join(out))
        return titles


def main():
    ap = argparse.ArgumentParser(description="extract text from the bundled QMT manual PDF")
    ap.add_argument("--pdf", default=DEFAULT_PDF)
    ap.add_argument("--toc", action="store_true", help="print the bookmark/outline titles")
    ap.add_argument("--page", type=int, default=None, help="print one page (PDF page order)")
    ap.add_argument("--search", nargs="+", default=None, help="keywords to find")
    ap.add_argument("--context", type=int, default=260, help="chars of context per hit")
    ap.add_argument("--dump", default=None, help="write the full text to this file")
    ap.add_argument("--max-hits", type=int, default=8, help="max hits per keyword")
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        print("manual not found: %s\nuse --pdf to point at it" % args.pdf)
        return 2
    pdf = Pdf(args.pdf)

    if args.toc:
        for t in pdf.toc():
            print(t.strip())
        return 0

    pages = pdf.pages()
    if not pages:
        print("no page text recovered - the PDF layout may differ from the expected Word export")
        return 1

    if args.page:
        print(pages.get(args.page, "(no text on page %d)" % args.page))
        return 0

    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            for i in sorted(pages):
                f.write("\n\n========== PAGE %d ==========\n" % i)
                f.write(pages[i])
        print("wrote %s (%d pages)" % (args.dump, len(pages)))
        return 0

    if args.search:
        for kw in args.search:
            hits = [(i, t) for i, t in sorted(pages.items()) if kw in t]
            print("=" * 72)
            print("keyword %r -> %d pages %s" % (kw, len(hits), [i for i, _ in hits[:20]]))
            for i, t in hits[:args.max_hits]:
                pos = t.find(kw)
                print("-" * 72)
                print("[page %d]" % i)
                print(t[max(0, pos - args.context): pos + args.context])
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
