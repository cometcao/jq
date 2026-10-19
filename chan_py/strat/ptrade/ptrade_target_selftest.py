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
