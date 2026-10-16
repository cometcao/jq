# -*- coding: utf-8 -*-
"""
qmt_channel_probe.py - capability matrix probe for the tightened QMT sandbox.

PURPOSE
  The broker tightened two things for strategies running inside the big QMT
  client: (a) file access, (b) network / HTTP signals. Before choosing a new
  design we must know WHICH LAYER the restriction lives at, because that
  determines what still survives:

    - Python-level patch (builtins.open / socket wrapped) -> other APIs survive
    - client strategy-level policy (APIs removed / whitelist by path)
    - OS-level confinement (ACL / job object / AppContainer) -> nothing survives

HOW TO RUN
  A) INSIDE QMT (this is the run that matters):
     Strategy Trading panel -> New Strategy -> select this file -> run.
     No account binding, NO ORDERS, no schedule_run tasks are registered.
     Read the [PROBE] lines in the panel output.
  B) OUTSIDE QMT (baseline for comparison, unrestricted environment):
     python qmt_channel_probe.py            # full run
     python qmt_channel_probe.py --safe     # skip clipboard + registry writes

PAIR SCRIPT
  Run qmt_channel_listener.py on the same PC to get a live loopback peer; the
  probe then reports whether 127.0.0.1 traffic really flows (this is the key
  test for the "local socket channel" fallback).

DEPLOYMENT RULE
  This file MUST stay pure ASCII (QMT panel re-saves strategy source as GBK
  while the engine decodes it as UTF-8; any non-ASCII byte breaks compilation).
"""

import os
import sys
import io
import json
import time
import socket
import datetime

PROBE_TAG = "[PROBE]"

# ==================== Deployment constants (adjust per machine) ====================
STRATEGY_DIR = r"C:\Users\comet\git\jq\chan_py\strat"
QMT_INSTALL_DIR = r"D:\gjzq\qmt_test_gj"
EMAIL_LIST_FILE = r"C:\Users\comet\Desktop\low_valuation_stocks.json"

CONFIG_FILE = os.path.join(STRATEGY_DIR, "qmt_stdqmt_config.json")
EXCHANGE_DIR = os.path.join(STRATEGY_DIR, "qmt_exchange")
TEMP_DIR = os.environ.get("TEMP") or r"C:\Windows\Temp"

LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PORT = 18923
TCP_TARGETS = [
    ("loopback listener", LOOPBACK_HOST, LOOPBACK_PORT, "tcp_loopback_listener"),
    ("loopback port 80", LOOPBACK_HOST, 80, "tcp_loopback_80"),
    ("www.baidu.com:443", "www.baidu.com", 443, "tcp_baidu_443"),
    ("114.114.114.114:53", "114.114.114.114", 53, "tcp_dns53"),
]
HTTP_TARGETS = [
    "http://127.0.0.1:18923/ping",
    "http://www.baidu.com/",
    "https://www.baidu.com/",
]
# Sector names are written as \uXXXX escapes ON PURPOSE: this file must stay
# pure ASCII (QMT panel re-saves strategy source as GBK while the engine decodes
# it as UTF-8, so any raw non-ASCII byte breaks compilation). Python decodes the
# escapes to real characters at runtime, which is what the API wants.
#   \u6caa\u6df1A\u80a1 = Hu-Shen A shares, \u6caa\u6df1300 = CSI 300,
#   \u4e0a\u8bc1A\u80a1 = SSE A shares,
#   \u521b\u4e1a\u677f = ChiNext, \u79d1\u521b\u677f = STAR market,
#   \u4f4e\u4f30\u503c = low valuation (the strategy's own sector name, if any)
SECTOR_NAMES = ["\u6caa\u6df1A\u80a1", "\u6caa\u6df1300", "\u4e0a\u8bc1A\u80a1",
                "\u521b\u4e1a\u677f", "\u79d1\u521b\u677f",
                "\u6211\u7684\u81ea\u9009",          # My Watchlist (already registered, empty)
                "\u4f4e\u4f30\u503c", "low_valuation"]

# ---- OPTIONAL: sector hot-reload watch -------------------------------------
# Set WATCH_SECTOR_NAME to a sector name (e.g. "\u6211\u7684\u81ea\u9009") to make the
# probe keep re-reading that sector from handlebar. Use it to answer the one
# question the file->sector channel depends on: after an EXTERNAL process
# rewrites D:\...\datadir\Sector\<group>\<sector>, does the strategy see the new
# content live, or only after a client restart?
# Leave it as None for the normal one-shot capability matrix.
WATCH_SECTOR_NAME = None
WATCH_INTERVAL_SECONDS = 10

ENABLE_CLIPBOARD_TEST = True     # NOTE: overwrites the current clipboard content
ENABLE_REGISTRY_WRITE_TEST = True
ENABLE_NAMED_PIPE_TEST = True
ENABLE_NETWORK_PROBE = True      # NOTE: really connects out (DNS/TCP/HTTP) - see --safe
SAFE_MODE = False                # set True to force the no-touch mode when loaded in QMT
NET_TIMEOUT = 3.0

RESULTS = []
FLAGS = {}


def _exc(e):
    parts = [type(e).__name__, str(e)]
    errno = getattr(e, "errno", None)
    winerror = getattr(e, "winerror", None)
    if errno is not None:
        parts.append("errno=%s" % errno)
    if winerror is not None:
        parts.append("winerror=%s" % winerror)
    return " | ".join(str(p) for p in parts)


def _add(section, item, status, detail=""):
    RESULTS.append((section, item, status, detail))
    print("%s %-12s %-34s %-7s %s" % (PROBE_TAG, section, item, status, detail))


def _ok(section, item, detail=""):
    _add(section, item, "OK", detail)


def _bad(section, item, detail=""):
    _add(section, item, "BLOCKED", detail)


def _skip(section, item, detail=""):
    _add(section, item, "SKIP", detail)


def _try(section, item, fn, flag=None, detail_fn=None):
    """Run fn(); record OK/BLOCKED. Returns (ok, value)."""
    try:
        value = fn()
    except Exception as e:
        _bad(section, item, _exc(e))
        if flag:
            FLAGS[flag] = False
        return False, None
    detail = detail_fn(value) if detail_fn else (value if isinstance(value, str) else "")
    _ok(section, item, detail)
    if flag:
        FLAGS[flag] = True
    return True, value


# ==================== 1. environment ====================
def probe_environment():
    _add("env", "python version", "INFO", sys.version.replace("\n", " "))
    _add("env", "executable", "INFO", sys.executable)
    _add("env", "process id", "INFO", str(os.getpid()))
    _add("env", "cwd", "INFO", os.getcwd())
    _add("env", "has __file__", "INFO", str("__file__" in globals()))
    _add("env", "sys.path[:6]", "INFO", " ; ".join(sys.path[:6]))
    interesting = [k for k in sorted(os.environ)
                   if "QMT" in k.upper() or "XT" in k.upper() or "PROXY" in k.upper()]
    _add("env", "env keys QMT/XT/PROXY", "INFO", ",".join(interesting) or "(none)")
    _add("env", "env key count", "INFO", str(len(os.environ)))
    try:
        import platform
        _add("env", "platform", "INFO", platform.platform())
    except Exception as e:
        _bad("env", "platform", _exc(e))
    try:
        _add("env", "hostname", "INFO", socket.gethostname())
    except Exception as e:
        _bad("env", "hostname", _exc(e))


# ==================== 2. imports ====================
IMPORT_CANDIDATES = [
    "json", "os", "sys", "io", "time", "datetime", "math", "re", "random",
    "hashlib", "base64", "threading", "queue", "socket", "ssl", "select",
    "struct", "http.client", "urllib.request", "urllib.parse", "ftplib",
    "smtplib", "imaplib", "poplib", "email", "subprocess", "ctypes",
    "winreg", "tkinter", "sqlite3", "tempfile", "shutil", "glob", "pathlib",
    "csv", "configparser", "logging", "traceback", "copy", "pickle",
    "zipfile", "gzip", "zlib", "multiprocessing", "asyncio",
    "numpy", "pandas", "scipy", "requests", "talib", "xtquant", "xtdata",
]


def probe_imports():
    allowed, blocked = [], []
    for name in IMPORT_CANDIDATES:
        try:
            mod = __import__(name)
            allowed.append(name)
            _ok("import", name, str(getattr(mod, "__file__", "builtin")))
        except Exception as e:
            blocked.append(name)
            _bad("import", name, _exc(e))
    FLAGS["import_blocked"] = len(blocked)
    _add("import", "summary", "INFO", "ok=%d blocked=%d [%s]"
         % (len(allowed), len(blocked), ",".join(blocked)))


# ==================== 3. open() identity / sandbox layer ====================
def probe_open_identity():
    """If open() is a Python function (not a builtin), the sandbox is a
    Python-level patch -> other APIs (os.open, ctypes, winreg, sockets) usually
    still work. If it is a builtin and still blocked, the confinement is below
    the interpreter."""
    _add("open", "type(open)", "INFO", str(type(open)))
    _add("open", "open is io.open", "INFO", str(open is io.open))
    _add("open", "open.__module__", "INFO", str(getattr(open, "__module__", None)))
    _add("open", "open.__qualname__", "INFO", str(getattr(open, "__qualname__", None)))
    try:
        import builtins
        _add("open", "builtins.open is open", "INFO", str(builtins.open is open))
    except Exception as e:
        _bad("open", "builtins check", _exc(e))
    _add("open", "has os.open", "INFO", str(hasattr(os, "open")))
    _add("open", "has sys.audit", "INFO", str(hasattr(sys, "audit")))
    _add("open", "has sys.addaudithook", "INFO", str(hasattr(sys, "addaudithook")))
    _add("open", "io.FileIO", "INFO", str(getattr(io, "FileIO", None)))


# ==================== 4. file read ====================
def probe_file_read():
    first_exchange_file = None
    try:
        for fn in sorted(os.listdir(EXCHANGE_DIR)):
            if fn.endswith(".json") or fn.endswith(".done"):
                first_exchange_file = os.path.join(EXCHANGE_DIR, fn)
                break
    except Exception:
        pass

    targets = [
        ("repo config json", CONFIG_FILE),
        ("repo exchange dir", EXCHANGE_DIR),
        ("repo exchange file", first_exchange_file),
        ("email list file", EMAIL_LIST_FILE),
        ("qmt install dir", QMT_INSTALL_DIR),
        ("qmt python dir", os.path.join(QMT_INSTALL_DIR, "python")),
        ("qmt deployed script", os.path.join(QMT_INSTALL_DIR, "python",
                                             "qmt_rebalance_executor.py")),
        ("qmt userdata_mini", os.path.join(QMT_INSTALL_DIR, "userdata_mini")),
        ("temp dir", TEMP_DIR),
        ("cwd", os.getcwd()),
    ]
    read_ok = 0
    read_tried = 0
    for label, path in targets:
        if not path:
            _skip("read", label, "not found / not configured")
            continue
        if not os.path.exists(path):
            _skip("read", label, "does not exist: %s" % path)
            continue
        read_tried += 1

        def _do(p=path):
            if os.path.isdir(p):
                names = os.listdir(p)
                return "listdir %d entries" % len(names)
            with open(p, "rb") as f:
                return "open+read %d bytes" % len(f.read(64))

        ok, _ = _try("read", label, _do)
        if ok:
            read_ok += 1
    FLAGS["file_read_ok"] = read_ok
    FLAGS["file_read_tried"] = read_tried
    _add("read", "summary", "INFO", "readable %d/%d existing targets" % (read_ok, read_tried))


# ==================== 5. file write ====================
WRITE_TARGETS = [
    ("repo dir", STRATEGY_DIR),
    ("repo exchange dir", EXCHANGE_DIR),
    ("qmt install dir", QMT_INSTALL_DIR),
    ("qmt python dir", os.path.join(QMT_INSTALL_DIR, "python")),
    ("temp dir", TEMP_DIR),
]


def probe_file_write():
    write_ok = 0
    write_tried = 0
    for label, directory in WRITE_TARGETS:
        if not directory or not os.path.isdir(directory):
            _skip("write", label, "dir missing: %s" % directory)
            continue
        write_tried += 1
        tmp = os.path.join(directory, ".qmt_probe_write.tmp")
        final = os.path.join(directory, "qmt_probe_write_test.json")

        def _do(t=tmp, f=final):
            with open(t, "w", encoding="utf-8") as fh:
                fh.write('{"probe": "ok"}')
            os.replace(t, f)                     # atomic rename (bridge pattern)
            with open(f, "r", encoding="utf-8") as fh:
                back = json.load(fh)
            os.remove(f)
            return "write+replace+read+remove ok (%s)" % back.get("probe")

        ok, _ = _try("write", label, _do)
        if ok:
            write_ok += 1
        else:
            for leftover in (tmp, final):
                try:
                    if os.path.exists(leftover):
                        os.remove(leftover)
                except Exception:
                    pass
    FLAGS["file_write_ok"] = write_ok
    FLAGS["file_write_tried"] = write_tried
    _add("write", "summary", "INFO", "writable %d/%d dirs" % (write_ok, write_tried))


# ==================== 6. low-level read variants on one real file ====================
def probe_lowlevel_variants():
    if not os.path.exists(CONFIG_FILE):
        _skip("lowlevel", "all variants", "config file missing: %s" % CONFIG_FILE)
        return

    def _builtin():
        with open(CONFIG_FILE, "rb") as f:
            return f.read(32)

    def _ioopen():
        with io.open(CONFIG_FILE, "rb") as f:
            return f.read(32)

    def _pathlib():
        import pathlib
        return pathlib.Path(CONFIG_FILE).read_bytes()[:32]

    def _osopen():
        fd = os.open(CONFIG_FILE, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            return os.read(fd, 32)
        finally:
            os.close(fd)

    def _codecs():
        import codecs
        with codecs.open(CONFIG_FILE, "rb") as f:
            return f.read(32)

    def _numpy():
        import numpy as np
        return np.fromfile(CONFIG_FILE, dtype=np.uint8, count=32).tobytes()

    def _pandas():
        import pandas as pd
        return str(type(pd.read_json(CONFIG_FILE)))

    def _ctypes_read():
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                    ctypes.c_void_p]
        k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                 ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        handle = k32.CreateFileW(CONFIG_FILE, 0x80000000, 1, None, 3, 0x80, None)
        if not handle or handle == wintypes.HANDLE(-1).value:
            raise OSError(ctypes.get_last_error(), "CreateFileW failed")
        try:
            buf = ctypes.create_string_buffer(32)
            got = wintypes.DWORD(0)
            if not k32.ReadFile(handle, buf, 32, ctypes.byref(got), None):
                raise OSError(ctypes.get_last_error(), "ReadFile failed")
            return buf.raw[:got.value]
        finally:
            k32.CloseHandle(handle)

    variants = [
        ("builtins.open", _builtin),
        ("io.open", _ioopen),
        ("pathlib.read_bytes", _pathlib),
        ("os.open+os.read", _osopen),
        ("codecs.open", _codecs),
        ("numpy.fromfile", _numpy),
        ("pandas.read_json", _pandas),
        ("ctypes CreateFileW", _ctypes_read),
    ]
    for label, fn in variants:
        _try("lowlevel", label, fn, detail_fn=lambda v: "got %d bytes/type" % len(str(v)))


# ==================== 7. registry ====================
def probe_registry():
    if not ENABLE_REGISTRY_WRITE_TEST:
        _skip("registry", "write test", "disabled")
        return
    key_path = r"Software\QMTChannelProbe"

    def _do():
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        try:
            winreg.SetValueEx(key, "probe", 0, winreg.REG_SZ, "ok")
            value, _t = winreg.QueryValueEx(key, "probe")
        finally:
            winreg.CloseKey(key)
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            except Exception:
                pass
        return value

    _try("registry", "HKCU write+read", _do, flag="registry_ok",
         detail_fn=lambda v: "value=%s" % v)


# ==================== 8. clipboard ====================
def probe_clipboard():
    if not ENABLE_CLIPBOARD_TEST:
        _skip("clipboard", "read/write", "disabled")
        return

    def _do():
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        try:
            marker = "qmtprobe-%d" % int(time.time())
            root.clipboard_clear()
            root.clipboard_append(marker)
            root.update()
            return root.clipboard_get()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    _try("clipboard", "tk set+get", _do, flag="clipboard_ok",
         detail_fn=lambda v: "roundtrip=%s (clipboard was overwritten)" % v)


# ==================== 9. named pipe ====================
def probe_named_pipe():
    if not ENABLE_NAMED_PIPE_TEST:
        _skip("pipe", "CreateNamedPipeW", "disabled")
        return
    pipe_name = r"\\.\pipe\qmt_channel_probe_%d" % os.getpid()

    def _do():
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateNamedPipeW.restype = wintypes.HANDLE
        k32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                         wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                         wintypes.DWORD, ctypes.c_void_p]
        handle = k32.CreateNamedPipeW(pipe_name, 3, 0, 1, 4096, 4096, 0, None)
        if not handle or handle == wintypes.HANDLE(-1).value:
            raise OSError(ctypes.get_last_error(), "CreateNamedPipeW failed")
        k32.CloseHandle(handle)
        return pipe_name

    _try("pipe", "create+close", _do, flag="pipe_ok", detail_fn=lambda v: str(v))


# ==================== 10. network ====================
def probe_network():
    if not ENABLE_NETWORK_PROBE:
        _skip("net", "all network tests", "disabled by --safe (no outbound traffic)")
        return

    def _create():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.close()
        return "socket() ok"

    _try("net", "socket create", _create, flag="socket_create")

    def _dns():
        return socket.gethostbyname("www.baidu.com")

    _try("net", "DNS www.baidu.com", _dns, flag="dns_ok")

    for label, host, port, flagkey in TCP_TARGETS:
        def _connect(h=host, p=port):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(NET_TIMEOUT)
            t0 = time.time()
            try:
                s.connect((h, p))
            finally:
                s.close()
            return "connected in %.3fs" % (time.time() - t0)

        _try("net", "tcp %s" % label, _connect, flag=flagkey)

    def _raw_http(host, port, use_tls=False):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(NET_TIMEOUT * 2)
        try:
            s.connect((host, port))
            if use_tls:
                import ssl
                s = ssl.create_default_context().wrap_socket(s, server_hostname=host)
            req = ("GET / HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n" % host).encode("ascii")
            s.sendall(req)
            return s.recv(48).decode("latin-1").replace("\r\n", " / ")
        finally:
            try:
                s.close()
            except Exception:
                pass

    _try("net", "raw HTTP 127.0.0.1:%d" % LOOPBACK_PORT,
         lambda: _raw_http(LOOPBACK_HOST, LOOPBACK_PORT), flag="http_loopback_raw")
    _try("net", "raw HTTP www.baidu.com:80",
         lambda: _raw_http("www.baidu.com", 80), flag="http_ext_raw")
    _try("net", "raw HTTPS www.baidu.com:443",
         lambda: _raw_http("www.baidu.com", 443, use_tls=True), flag="https_ext_raw")

    def _urllib(url):
        import urllib.request
        resp = urllib.request.urlopen(url, timeout=int(NET_TIMEOUT * 2))
        try:
            return "status=%s body=%r" % (resp.getcode(), resp.read(24))
        finally:
            resp.close()

    for url in HTTP_TARGETS:
        _try("net", "urllib %s" % url, lambda u=url: _urllib(u),
             flag="urllib_%s" % url.split(":")[0])

    try:
        import requests
        def _requests():
            r = requests.get("http://www.baidu.com/", timeout=NET_TIMEOUT * 2)
            return "status=%s" % r.status_code
        _try("net", "requests.get baidu", _requests, flag="requests_get")
    except ImportError:
        _skip("net", "requests.get baidu", "requests not importable")


# ==================== 11. QMT native APIs (the channel that must survive) ====================
CTX_API_NAMES = [
    "get_market_data", "get_market_data_ex", "get_full_tick", "get_instrument_detail",
    "get_stock_list_in_sector", "get_sector_list", "get_index_stocks",
    "get_financial_data", "get_trading_dates", "get_divid_factors",
    "get_his_st_data", "get_longhubang", "get_turnover_rate", "get_all_stock",
    "schedule_run", "cancel_schedule_run", "run_time", "set_account",
    "is_last_bar", "do_back_test", "subscribe_quote", "unsubscribe_quote",
    "download_history_data", "download_history_data2", "barpos", "stockcode",
    "period", "get_bar_timetag", "accID", "get_quote",
]


def probe_qmt_api(ctx):
    if ctx is None:
        _skip("qmtapi", "all", "external run: no ContextInfo")
        return
    present, absent = [], []
    for name in CTX_API_NAMES:
        if hasattr(ctx, name):
            present.append(name)
        else:
            absent.append(name)
    _add("qmtapi", "present", "INFO", ",".join(present))
    _add("qmtapi", "absent", "INFO", ",".join(absent))

    try:
        names = [n for n in dir(ctx) if not n.startswith("_")]
        _add("qmtapi", "dir(ctx) count", "INFO", str(len(names)))
        for i in range(0, len(names), 6):
            _add("qmtapi", "dir(ctx) [%d]" % i, "INFO", " ".join(names[i:i + 6]))
    except Exception as e:
        _bad("qmtapi", "dir(ctx)", _exc(e))

    def _sectors():
        sectors = ctx.get_sector_list()
        return sectors

    ok, sectors = _try("sector", "get_sector_list", _sectors, flag="sector_list",
                       detail_fn=lambda v: "count=%s" % (len(v) if v is not None else "?"))
    if ok and sectors:
        sample = sorted(str(s) for s in sectors)[:40]
        _add("sector", "sample", "INFO", " | ".join(sample))

    for name in SECTOR_NAMES:
        if name == "all":
            continue

        def _list(n=name):
            codes = ctx.get_stock_list_in_sector(n)
            return codes

        _try("sector", "list '%s'" % name, _list, flag="sector_read",
             detail_fn=lambda v: "count=%s first=%s"
             % (len(v) if v is not None else "?", (list(v)[:3] if v else [])))


# ==================== 12. verdict ====================
def print_verdict():
    read_tried = FLAGS.get("file_read_tried", 0)
    read_ok = FLAGS.get("file_read_ok", 0)
    write_ok = FLAGS.get("file_write_ok", 0)

    if read_tried == 0:
        file_verdict = "NO_TARGET_EXISTS (fix the paths in this file first)"
    elif read_ok == 0:
        file_verdict = "FILE_READ_BLOCKED_EVERYWHERE"
    elif read_ok < read_tried:
        file_verdict = "FILE_READ_PARTIAL (some paths allowed -> check the OK lines)"
    else:
        file_verdict = "FILE_READ_ALLOWED"

    lowlevel_ok = [r[1] for r in RESULTS
                   if r[0] == "lowlevel" and r[2] == "OK" and r[1] != "builtins.open"]
    if read_ok == 0 and lowlevel_ok:
        layer = "PYTHON_LEVEL_PATCH (bypass-capable APIs still work: %s)" % ",".join(lowlevel_ok)
    elif read_ok == 0:
        layer = "BELOW_INTERPRETER (client policy or OS confinement)"
    else:
        layer = "n/a"

    net_bits = []
    for key in ("socket_create", "dns_ok", "tcp_loopback_listener", "tcp_baidu_443",
                "tcp_dns53", "http_loopback_raw", "http_ext_raw",
                "https_ext_raw", "requests_get"):
        if key in FLAGS:
            net_bits.append("%s=%s" % (key, FLAGS[key]))

    _add("verdict", "file access", "INFO", "%s (read %d/%d, write %d/%d)"
         % (file_verdict, read_ok, read_tried, write_ok, FLAGS.get("file_write_tried", 0)))
    _add("verdict", "restriction layer", "INFO", layer)
    _add("verdict", "network", "INFO", " ".join(net_bits) or "(no network results)")
    _add("verdict", "registry write", "INFO", str(FLAGS.get("registry_ok")))
    _add("verdict", "named pipe", "INFO", str(FLAGS.get("pipe_ok")))
    _add("verdict", "clipboard", "INFO", str(FLAGS.get("clipboard_ok")))
    _add("verdict", "sector api", "INFO", "list=%s read=%s"
         % (FLAGS.get("sector_list"), FLAGS.get("sector_read")))
    _add("verdict", "blocked imports", "INFO", str(FLAGS.get("import_blocked")))


# ==================== 13. dump the log ====================
def dump_log():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    body = "\n".join("%s %-12s %-34s %-7s %s" % ((PROBE_TAG,) + tuple(row))
                     for row in RESULTS)
    targets = [
        os.path.join(STRATEGY_DIR, "logs", "qmt_channel_probe_%s.txt" % stamp),
        os.path.join(TEMP_DIR, "qmt_channel_probe_%s.txt" % stamp),
    ]
    for path in targets:
        try:
            directory = os.path.dirname(path)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            with open(path, "w", encoding="utf-8") as f:
                f.write(body + "\n")
            _ok("dumplog", "written", path)
        except Exception as e:
            _bad("dumplog", "write failed", "%s -> %s" % (path, _exc(e)))


# ==================== entry points ====================
def run_probe(ctx=None, safe=False):
    global ENABLE_CLIPBOARD_TEST, ENABLE_REGISTRY_WRITE_TEST, ENABLE_NETWORK_PROBE
    if safe:
        ENABLE_CLIPBOARD_TEST = False
        ENABLE_REGISTRY_WRITE_TEST = False
        ENABLE_NETWORK_PROBE = False
    started = time.time()
    print("%s ==================== begin ====================" % PROBE_TAG)
    probe_environment()
    probe_imports()
    probe_open_identity()
    probe_file_read()
    probe_file_write()
    probe_lowlevel_variants()
    probe_registry()
    probe_clipboard()
    probe_named_pipe()
    probe_network()
    probe_qmt_api(ctx)
    print_verdict()
    _add("env", "elapsed", "INFO", "%.1fs" % (time.time() - started))
    dump_log()
    print("%s ==================== end ====================" % PROBE_TAG)


def init(ContextInfo):
    try:
        run_probe(ContextInfo, safe=SAFE_MODE)
        if WATCH_SECTOR_NAME:
            print("%s watch mode armed for sector %r every %ds (handlebar)"
                  % (PROBE_TAG, WATCH_SECTOR_NAME, WATCH_INTERVAL_SECONDS))
    except Exception as e:
        print("%s FATAL init: %r" % (PROBE_TAG, e))
        try:
            print("%s %s" % (PROBE_TAG, "".join(
                __import__("traceback").format_exc())))
        except Exception:
            pass


_WATCH_LAST = [0.0]
_WATCH_PREV = [None]


def handlebar(ContextInfo):
    """Only used by the optional sector hot-reload watch; otherwise silent."""
    if not WATCH_SECTOR_NAME:
        return
    now = time.time()
    if now - _WATCH_LAST[0] < WATCH_INTERVAL_SECONDS:
        return
    _WATCH_LAST[0] = now
    try:
        codes = list(ContextInfo.get_stock_list_in_sector(WATCH_SECTOR_NAME) or [])
    except Exception as e:
        print("%s watch: sector read failed: %s" % (PROBE_TAG, _exc(e)))
        return
    changed = codes != _WATCH_PREV[0]
    _WATCH_PREV[0] = codes
    print("%s watch %s: count=%d changed=%s first=%s"
          % (PROBE_TAG, time.strftime("%H:%M:%S"), len(codes), changed, codes[:5]))


if __name__ == "__main__":
    run_probe(None, safe=("--safe" in sys.argv))
