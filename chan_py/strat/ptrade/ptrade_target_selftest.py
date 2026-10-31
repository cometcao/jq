# -*- coding: utf-8 -*-
"""
Offline cross-check of the local -> cloud file contract:

    ptrade_target.py                 (producer, local)
        -> <upload>/target_low_valuation.json         (the file PTrade mirrors)
    ptrade_rebalance_executor.py     (consumer, cloud)

No email, no network, no orders. It verifies exactly the part that can break silently:
the upload directory, the fixed file name, the JSON fields and the "today only" rule.

Run:  python ptrade_target_selftest.py
"""

import datetime
import json
import os
import shutil
import sys

# ai_fundamental_filter.py builds its API clients at import time and needs the keys to
# exist; this test never calls them, so dummy values are enough.
os.environ.setdefault("ZHIPU_API_KEY", "selftest")
os.environ.setdefault("DASHSCOPE_API_KEY", "selftest")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURE = os.path.join(HERE, "_selftest", "target")

FAILED = []


def check(name, ok, detail=""):
    print("  [%s] %s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILED.append(name)


def _has(mod):
    """Is a module importable here, without importing it (no side effects)?"""
    try:
        import importlib.util
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def main():
    print("test_import_paths_resolve")
    import importlib.util
    import ptrade_target as T
    shared = os.path.join(REPO, "shared")
    for mod in ("check_email_for_signal", "ai_fundamental_filter"):
        spec = importlib.util.find_spec(mod)
        check("search path resolves %s" % mod,
              spec is not None and bool(spec.origin) and
              spec.origin == os.path.join(shared, mod + ".py"),
              str(spec and spec.origin))
    check("email module is the real one (not the silent stub)",
          getattr(T.check_email_and_save_attachment, "__module__", "") ==
          "check_email_for_signal",
          getattr(T.check_email_and_save_attachment, "__module__", ""))
    if _has("requests") and _has("openai") and _has("baostock"):
        check("ai filter is the real one (not the silent stub)",
              getattr(T._ai_filter_stocks, "__module__", "") == "ai_fundamental_filter",
              getattr(T._ai_filter_stocks, "__module__", ""))
    else:
        print("  [SKIP] ai-filter stub check: requests/openai/baostock are missing in "
              "THIS python (the production python has them)")

    print("test_upload_file_is_produced")
    if os.path.isdir(FIXTURE):
        shutil.rmtree(FIXTURE, ignore_errors=True)
    archive = os.path.join(FIXTURE, "archive")
    upload = os.path.join(FIXTURE, "upload_file")      # same folder name as on the server
    os.makedirs(archive)
    os.makedirs(upload)

    strat = {"name": "low_valuation", "trading_times": ["09:35"], "capital_ratio": 1.0,
             "max_holdings": 8, "candidate_pool_size": 13, "cash_reserve_ratio": 0.0125,
             "rebalance_threshold": 0.20}
    # The email attachment speaks the JoinQuant dialect (XSHG/XSHE) and _load_stock_list
    # now passes it through untouched, so the written file must carry exactly that.
    codes = ["605189.XSHG", "301167.XSHE", "600739.XSHG"]
    now = datetime.datetime.now()
    T._write_rebalance_file(strat, codes, archive, now, upload, "target_%s.json")

    up_names = sorted(os.listdir(upload))
    ar_names = sorted(os.listdir(archive))
    check("upload dir holds one per-strategy file",
          up_names == ["target_low_valuation.json"], str(up_names))
    check("archive keeps the timestamped copy",
          len(ar_names) == 1 and ar_names[0].startswith("rebalance_low_valuation_")
          and ar_names[0].endswith(".json"), str(ar_names))
    check("no .tmp leftovers",
          not any(n.endswith(".tmp") for n in up_names + ar_names),
          str(up_names + ar_names))
    with open(os.path.join(upload, "target_low_valuation.json"), encoding="utf-8") as f:
        raw_payload = json.load(f)
    check("the source dialect is preserved verbatim in the file",
          raw_payload.get("stocks") == codes, str(raw_payload.get("stocks")))

    print("test_external_sender_payloads_are_validated")
    # A partner strategy emails its list, so the payload is outside our control: enforce the
    # dialect, keep the sender's ranking order, drop junk instead of writing it into the target.
    codes2, invalid, empty = T._normalize_codes(
        ["605189.XSHG", "301167.XSHE", "605189.XSHG", "600000.SS", "000001.sz",
         "600739", "abc.XSHG", "", "  600036.XSHG  "])
    check("legacy + lowercase spellings are folded onto XSHG/XSHE",
          codes2 == ["605189.XSHG", "301167.XSHE", "600000.XSHG", "000001.XSHE",
                     "600036.XSHG"], str(codes2))
    check("junk entries are reported, not traded", invalid == ["600739", "abc.XSHG"],
          str(invalid))
    check("duplicates are removed but the ranking order is kept", codes2[0] == "605189.XSHG",
          str(codes2))
    wrapped, invalid2, _e2 = T._normalize_codes({"stocks": ["600036.XSHG"], "note": "x"})
    check("an object with a 'stocks' array is accepted", wrapped == ["600036.XSHG"],
          str(wrapped))
    bad, invalid3, _e3 = T._normalize_codes({"list": ["600036.XSHG"]})
    check("an object without 'stocks' is rejected", bad == [] and bool(invalid3),
          "%s / %s" % (bad, invalid3))
    _c4, _i4, empty4 = T._normalize_codes([])
    check("an explicit empty array stays an explicit liquidation signal", empty4 is True, "")

    print("test_ai_filter_switch")
    # A partner strategy that does its own compliance work can switch our 12-rule AI filter
    # off per strategy; the payload must then be the sender's list, order untouched.
    import shutil as _sh
    demo = os.path.join(FIXTURE, "ai_switch")
    _sh.rmtree(demo, ignore_errors=True)
    os.makedirs(os.path.join(demo, "upload_file"))
    os.makedirs(os.path.join(demo, "archive"))
    lst = os.path.join(demo, "ttc2_stocks.json")
    with open(lst, "w", encoding="utf-8") as f:
        json.dump(["600519.XSHG", "000858.XSHE", "300750.XSHE"], f)
    ctx = {"exchange_path": os.path.join(demo, "archive"),
           "upload_path": os.path.join(demo, "upload_file"),
           "upload_name_tpl": "target_%s.json"}
    calls = []
    orig = T._ai_filter_with_budget

    def _no_ai(*a, **k):
        calls.append(1)
        raise AssertionError("AI filter must not run when ai_filter is false")

    T._ai_filter_with_budget = _no_ai
    try:
        T._generate_pair(ctx, {"name": "ttc2", "capital_ratio": 0.3, "max_holdings": 6,
                               "stock_list_file": lst, "ai_filter": False,
                               "trading_times": ["09:35"]}, "09:35")
    finally:
        T._ai_filter_with_budget = orig
    check("ai_filter=false skips the AI filter entirely", calls == [], str(calls))
    with open(os.path.join(demo, "upload_file", "target_ttc2.json"), encoding="utf-8") as f:
        payload = json.load(f)
    check("the list is written exactly as sent (order preserved)",
          payload.get("stocks") == ["600519.XSHG", "000858.XSHE", "300750.XSHE"],
          str(payload.get("stocks")))
    check("ai_filter itself is not leaked into the target file", "ai_filter" not in payload,
          str(sorted(payload.keys())))
    _sh.rmtree(demo, ignore_errors=True)

    print("test_pipeline_rehearsal_for_unregistered_strategy")
    # The point: prove email -> attachment -> target_<name>.json BEFORE the strategy is added
    # to ptrade_config.json (no capital split, no scheduling, cloud never reads the file).
    demo2 = os.path.join(FIXTURE, "pipeline")
    _sh.rmtree(demo2, ignore_errors=True)
    lists = os.path.join(demo2, "lists")
    outs = os.path.join(demo2, "out")
    os.makedirs(lists)
    os.makedirs(outs)
    with open(os.path.join(lists, "ttc2_stocks.json"), "w", encoding="utf-8") as f:
        json.dump(["600519.XSHG", "000858.XSHE"], f)
    ctx2 = {"config": {"stock_list_dir": lists, "upload_name_tpl": "target_%s.json"},
            "email_config": None,
            "upload_path": outs, "upload_name_tpl": "target_%s.json"}
    rc = T.run_pipeline_test(ctx2, "ttc2", do_email_check=False)
    check("the rehearsal succeeds without a config entry", rc == 0, str(rc))
    out = os.path.join(outs, "target_ttc2.json")
    check("it writes this strategy's upload file", os.path.exists(out), out)
    with open(out, encoding="utf-8") as f:
        rehearsal = json.load(f)
    check("the rehearsal file is marked as a test", rehearsal.get("pipeline_test") is True,
          str(sorted(rehearsal.keys())))
    check("it carries NO live sizing parameters",
          not any(k in rehearsal for k in ("capital_ratio", "max_holdings", "trading_times")),
          str(sorted(rehearsal.keys())))
    check("the codes survive in the sender's order",
          rehearsal.get("stocks") == ["600519.XSHG", "000858.XSHE"],
          str(rehearsal.get("stocks")))
    rc2 = T.run_pipeline_test({"config": {"stock_list_dir": lists},
                               "email_config": None, "upload_path": outs,
                               "upload_name_tpl": "target_%s.json"}, "nope",
                              do_email_check=False)
    check("a missing attachment fails loudly with exit code 2", rc2 == 2, str(rc2))
    _sh.rmtree(demo2, ignore_errors=True)

    print("test_disabled_strategy_switch")
    # enabled=false: the payload says so (the server then ignores the strategy completely),
    # and the ratio-sum check leaves it out, so a paused strategy may sit at capital_ratio 0
    # without disturbing the live strategy's slice.
    demo3 = os.path.join(FIXTURE, "disabled")
    _sh.rmtree(demo3, ignore_errors=True)
    os.makedirs(os.path.join(demo3, "out"))
    lst3 = os.path.join(demo3, "ttc2_stocks.json")
    with open(lst3, "w", encoding="utf-8") as f:
        json.dump(["600519.XSHG"], f)
    T._write_rebalance_file({"name": "ttc2", "enabled": False, "capital_ratio": 0.0},
                            ["600519.XSHG"], None, datetime.datetime.now(),
                            os.path.join(demo3, "out"), "target_%s.json")
    with open(os.path.join(demo3, "out", "target_ttc2.json"), encoding="utf-8") as f:
        off = json.load(f)
    check("a disabled strategy's file says enabled=false", off.get("enabled") is False,
          str(sorted(off.keys())))

    def _cfg(second):
        return {"log_file": os.path.join(demo3, "t.log"), "stock_list_dir": demo3,
                "strategies": [
                    {"name": "low_valuation", "stock_list_file": lst3,
                     "capital_ratio": 1.0, "trading_times": ["09:35"]},
                    second]}

    def _load(second):
        path = os.path.join(demo3, "cfg.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_cfg(second), f)
        ctx = {}
        T.load_config(ctx, path)
        return ctx

    ctx_off = _load({"name": "ttc2", "stock_list_file": lst3, "enabled": False,
                     "trading_times": ["09:35"]})
    check("a disabled strategy defaults to capital_ratio 0 and the sum still passes",
          ctx_off["strategy_configs"][1]["capital_ratio"] == 0.0,
          str(ctx_off["strategy_configs"][1]))
    raised = False
    try:
        _load({"name": "ttc2", "stock_list_file": lst3, "enabled": True,
               "capital_ratio": 0.3, "trading_times": ["09:35"]})
    except ValueError as e:
        raised = "must equal 1.0" in str(e)
    check("an ENABLED strategy that breaks the 1.0 sum is still rejected", raised, "")
    _sh.rmtree(demo3, ignore_errors=True)

    print("test_cloud_side_reads_it")
    import ptrade_rebalance_executor as S
    S.get_research_path = lambda: upload        # the one platform call we cannot make here
    status, target = S._load_target("target_low_valuation.json")
    check("cloud status ok", status == "ok", status)
    check("cloud keeps the SAME dialect (XSHG/XSHE) - no rewriting at all",
          bool(target) and target.get("_stocks") == ["605189.XSHG", "301167.XSHE",
                                                     "600739.XSHG"],
          str(target and target.get("_stocks")))
    check("cloud found it under <research>/upload_file/ (the real layout)",
          bool(target) and target["_path"].replace("\\", "/").endswith(
              "upload_file/target_low_valuation.json"),
          str(target and target.get("_path")))
    check("order time travelled in the file",
          bool(target) and S._order_times(target) == ["09:35"],
          str(target and S._order_times(target)))
    check("sizing parameters travelled in the file",
          bool(target) and S._params_from(target)["max_holdings"] == 8,
          str(target and S._params_from(target)))

    print("test_yesterdays_upload_is_rejected")
    T._write_rebalance_file(strat, codes, None, now - datetime.timedelta(days=1),
                            upload, "target_%s.json")
    status2, t2 = S._load_target("target_low_valuation.json")
    check("yesterday's upload is NOT traded (today-only rule)",
          status2 == "not-today", status2)
    check("its age is reported to the planner",
          bool(t2) and t2.get("_stale_days") == 1, str(t2 and t2.get("_stale_days")))

    print("")
    print("fixture: %s" % FIXTURE)
    if FAILED:
        print("FAILED: %s" % ", ".join(FAILED))
        return 1
    print("ALL TARGET CONTRACT TESTS PASSED")
    return 0


if __name__ == "__main__":
    os.chdir(REPO)          # ai_filter_config.json is looked up relative to the CWD
    sys.exit(main())
