# -*- coding: utf-8 -*-
"""
ptrade_target.py - PTrade execution side: local target-list process (zero API deps)

Self-contained project: config, lock, logs, archive and the upload file all live inside
this ptrade/ directory, so the folder can be copied anywhere as one unit.

Same pipeline as the retired stdqmt/qmt_stdqmt_target.py:
email check -> read list -> AI filter -> write the target file.

Extra vs the QMT-era script: it also writes the single file the PTrade client uploads,
with a FIXED name, so the server side only ever holds today's latest target:

    upload/target_low_valuation.json             <- what the PTrade client mirrors
    archive/rebalance_<strategy>_<ts>.json       <- local archive for reconciliation
    logs/ptrade_target.log                       <- log
    ptrade_target.lock                           <- single instance lock

- Paths: relative values in ptrade_config.json resolve against THIS directory (BASE_DIR),
  not the launch CWD. `email_reader_config.json` is looked up here, then in the launch CWD,
  then in the repo root; `ai_filter_config.json` is loaded by shared/ai_fundamental_filter.py
  and must therefore sit in the LAUNCH CWD (or copy it here and launch from here).
- File generation time: before each strategy trading_time (default trading_time - 5 min,
  immediately after email check completes)
- Empty list WRITTEN BY THE SOURCE = liquidate; list unavailable (missing / older than 14
  days / unreadable) = write nothing and let PTrade keep the previous target (the cloud
  liquidates once that held target is older than MAX_TARGET_AGE_DAYS); AI filter timeout =
  unfiltered list + error log; AI filter exception = skip this round, no file generated
- Startup validation: stock_list_dir must match email save_directory, otherwise refuse to generate
- Never touches: xtquant, tracker, account queries, money calculation
- NEVER run this together with stdqmt/qmt_stdqmt_target.py: both read and then mark the
  same mailbox as read/deleted (the lock files are now separate, so nothing stops you).

Usage (from this directory, or with an explicit --config):
  python ptrade_target.py                # resident mode (wakes on trading days per schedule)
  python ptrade_target.py --now          # generate once for all strategies immediately (no email check)
  python ptrade_target.py --email        # run the email check once immediately (test; no generation)
  python ptrade_target.py --config x.json
"""

import json
import os
import sys
import time
import atexit
import logging
import datetime
import threading

# ---- module search path (MUST come before the two imports below) ----------
# check_email_for_signal.py / ai_fundamental_filter.py live in shared/ now, while this
# script lives in ptrade/. python sets sys.path[0] to the SCRIPT's dir, not the CWD, so
# without this the imports below fail and - because they are wrapped in try/except
# ImportError - the failure is SILENT: the email check turns into a no-op stub and the AI
# compliance filter turns into a pass-through (unfiltered list traded!). Add every place
# the modules may have been deployed to.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (os.path.join(_HERE, "shared"),
              os.path.join(os.path.dirname(_HERE), "shared"),
              _HERE,
              os.getcwd(),
              os.path.join(os.getcwd(), "shared")):
    _cand = os.path.normpath(_cand)
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

try:
    from check_email_for_signal import check_email_and_save_attachment
except (ImportError, ValueError):
    def check_email_and_save_attachment(config):
        pass

try:
    from ai_fundamental_filter import filter_stocks as _ai_filter_stocks
except (ImportError, ValueError):
    def _ai_filter_stocks(codes, **kwargs):
        return codes

DEFAULT_EMAIL_OFFSET_MINUTES = 5
AI_FILTER_MAX_SECONDS = 600

# ---- self-contained project layout -----------------------------------------
# EVERYTHING this project reads/writes belongs to ptrade/: relative paths in
# ptrade_config.json are resolved against BASE_DIR (this file's dir), not the launch CWD,
# so the whole ptrade/ folder can be copied anywhere and keeps working.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_NAME = "ptrade_config.json"
LOCK_FILE = "ptrade_target.lock"
DEFAULT_LOG_FILE = "logs/ptrade_target.log"
DEFAULT_ARCHIVE_DIR = "archive"       # timestamped rebalance_<...>.json (reconciliation)
DEFAULT_UPLOAD_DIR = "upload_file"    # the dir the PTrade client mirrors (same name on both sides)
# One target file PER STRATEGY (multi-strategy ready): target_<strategy>.json. Each file
# carries its own order times + execution parameters, so the cloud needs no extra file.
DEFAULT_UPLOAD_NAME_TPL = "target_%s.json"
WRITE_ARCHIVE = True


def _resolve(path):
    """Relative path -> resolved against this project's own directory."""
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(BASE_DIR, path))


def _find_shared_config(name):
    """email_reader_config.json is shared with the other project: look next to this script
    (self-contained deploy), then the launch CWD, then the repo root (parent dir)."""
    for d in (BASE_DIR, os.getcwd(), os.path.dirname(BASE_DIR)):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return os.path.join(os.getcwd(), name)      # missing -> caller logs it


# ==================== Logging utilities ====================
def log_section(title, level="INFO"):
    separator = "=" * 60
    if level.upper() == "INFO":
        logging.info(f"\n{separator}")
        logging.info(f"{title}")
        logging.info(f"{separator}")
    elif level.upper() == "WARNING":
        logging.warning(f"\n{separator}")
        logging.warning(f"{title}")
        logging.warning(f"{separator}")
    elif level.upper() == "ERROR":
        logging.error(f"\n{separator}")
        logging.error(f"{title}")
        logging.error(f"{separator}")


def log_important(msg):
    logging.info(f"[IMPORTANT] {msg}")


def log_warning_highlight(msg):
    logging.warning(f"[WARN] {msg}")


def log_error_highlight(msg):
    logging.error(f"[ERROR] {msg}")


# ==================== Single instance protection ====================
def _is_process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def check_single_instance():
    lock_file = _resolve(LOCK_FILE)
    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f:
                pid = int(f.read().strip())
            if _is_process_alive(pid) and time.time() - os.path.getmtime(lock_file) < 3600:
                logging.warning(f"another instance is running (PID={pid}), exiting")
                sys.exit(0)
        except (ValueError, IOError) as e:
            logging.warning(f"failed to read lock file: {e}")
    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.remove(lock_file) if os.path.exists(lock_file) else None)


# ==================== Date utilities ====================
def is_weekday(date):
    return date.weekday() < 5


# ==================== Config loading ====================
def load_config(context, config_file=None):
    """Load the project config (ptrade_config.json), fully self-contained."""
    if not config_file:
        for cand in (_resolve(DEFAULT_CONFIG_NAME), DEFAULT_CONFIG_NAME):
            if os.path.exists(cand):
                config_file = cand
                break
    new_path = config_file or DEFAULT_CONFIG_NAME
    with open(new_path, encoding='utf-8') as f:
        new_cfg = json.load(f)
    logging.info(f"config file: {os.path.abspath(new_path)}")

    # external process log (FileHandler added only once)
    log_file = _resolve(new_cfg.get("log_file", DEFAULT_LOG_FILE))
    os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)
    logger = logging.getLogger()
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_file)
               for h in logger.handlers):
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)

    # strategy validation (capital_ratio sum, trading_times format)
    strategies = new_cfg['strategies']
    total_ratio = sum(s['capital_ratio'] for s in strategies)
    if abs(total_ratio - 1.0) > 0.0001:
        raise ValueError(f"sum of capital_ratio ({total_ratio:.4f}) must equal 1.0 (tolerance +/-0.0001)")
    for s in strategies:
        if s['capital_ratio'] <= 0:
            raise ValueError(f"capital_ratio of strategy '{s['name']}' must be > 0")
        if 'trading_times' not in s:
            s['trading_times'] = ["09:35"]
        if not isinstance(s['trading_times'], list):
            raise ValueError(f"trading_times of strategy '{s['name']}' must be a list")
        for t in s['trading_times']:
            if not isinstance(t, str) or len(t) != 5 or t[2] != ':':
                raise ValueError(f"bad trading time format for strategy '{s['name']}': {t}, expected HH:MM")
            try:
                hour, minute = int(t[:2]), int(t[3:])
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    raise ValueError
            except ValueError:
                raise ValueError(f"invalid trading time for strategy '{s['name']}': {t}")

    # list path override: stock_list_dir + stock_list_files[strategy name]
    stock_list_dir = new_cfg["stock_list_dir"]
    stock_list_files = new_cfg.get("stock_list_files", {})
    overridden = False
    for s in strategies:
        fname = stock_list_files.get(s["name"])
        if fname:
            s["stock_list_file"] = os.path.join(stock_list_dir, fname)
            overridden = True
            logging.info(f"[{s['name']}] list path -> {s['stock_list_file']}")

    # startup validation: stock_list_dir must match email save_directory (only when mapping
    # applied and email config exists)
    email_config = None
    try:
        with open(_find_shared_config("email_reader_config.json"), 'r', encoding='utf-8') as f:
            email_config = json.load(f)
        logging.info("email config loaded")
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info("email_reader_config.json missing or invalid, email check disabled")

    if email_config is not None and overridden:
        save_dir = email_config.get("save_directory", "")
        if os.path.normpath(save_dir) != os.path.normpath(stock_list_dir):
            raise ValueError(
                f"refuse to generate: stock_list_dir({stock_list_dir}) does not match "
                f"email save_directory({save_dir})")

    context['config'] = new_cfg
    context['strategy_configs'] = strategies
    context['email_config'] = email_config
    context['exchange_path'] = _resolve(new_cfg.get("exchange_path", DEFAULT_ARCHIVE_DIR))
    # the single file the PTrade client uploads; both keys are optional in the config
    context['upload_path'] = _resolve(new_cfg.get("ptrade_upload_path", DEFAULT_UPLOAD_DIR))
    context['upload_name_tpl'] = new_cfg.get("ptrade_upload_name_tpl", DEFAULT_UPLOAD_NAME_TPL)
    if new_cfg.get("ptrade_upload_filename"):
        logging.warning("config key 'ptrade_upload_filename' is obsolete -> ignored; "
                        f"each strategy now writes '{context['upload_name_tpl']}' % name")
    if context['upload_path']:
        logging.info(f"upload dir: {context['upload_path']} "
                     f"(per-strategy file: {context['upload_name_tpl']})")
    logging.info(f"archive dir: {context['exchange_path']}")
    logging.info("config loaded successfully")


# ==================== Scheduling ====================
def _email_time_for(trading_time, offset_minutes):
    h, m = map(int, trading_time.split(':'))
    total = (h * 60 + m - offset_minutes) % 1440
    return f"{total // 60:02d}:{total % 60:02d}"


def _build_schedule(strategies):
    """gen_time -> [(strat, trading_time), ...]. gen_time defaults to trading_time - 5 min
    (equals trading_time when offset<=0)."""
    schedule = {}
    for s in strategies:
        offset = s.get("email_check_offset_minutes", DEFAULT_EMAIL_OFFSET_MINUTES)
        for t in s['trading_times']:
            gen = _email_time_for(t, offset) if offset > 0 else t
            schedule.setdefault(gen, []).append((s, t))
    return schedule


def _next_wake(now, wake_times):
    for t in wake_times:
        h, m = map(int, t.split(':'))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target > now:
            return target
    tomorrow = now + datetime.timedelta(days=1)
    while not is_weekday(tomorrow.date()):
        tomorrow += datetime.timedelta(days=1)
    h, m = map(int, wake_times[0].split(':'))
    return tomorrow.replace(hour=h, minute=m, second=0, microsecond=0)


def _sleep_until(target):
    while True:
        remaining = (target - datetime.datetime.now()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 60))


# ==================== List loading (copied from old read_stock_lists, slicing removed) ====================
def _load_stock_list(strat):
    """Return (codes, note). note in ok/missing/expired/read_error; the latter three
    follow old semantics -> empty list = liquidate."""
    file_path = strat["stock_list_file"]
    if not os.path.exists(file_path):
        logging.warning(f"[{strat['name']}] list file does not exist: {file_path} -> liquidate")
        return [], "missing"
    file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
    days_old = (datetime.datetime.now() - file_mtime).days
    if days_old > 14:
        logging.warning(f"[{strat['name']}] list file expired: {file_path} "
                        f"({days_old} days ago) -> liquidate")
        return [], "expired"
    try:
        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)
        codes = [item.replace('XSHE', 'SZ').replace('XSHG', 'SH') for item in data]
        return codes, "ok"
    except Exception as e:
        logging.error(f"[{strat['name']}] failed to read list file: {e} -> liquidate")
        return [], "read_error"


# ==================== AI filter (time budget + conservative on exceptions) ====================
def _ai_filter_with_budget(strat, codes, budget_seconds):
    """Return (status, codes): ok=filter result (may be partial on deadline) /
    timeout=hard fallback to unfiltered list / error=skip this round."""
    result = {}
    stats = {}
    budget = max(budget_seconds, 1)
    deadline = datetime.datetime.now() + datetime.timedelta(seconds=budget)

    def worker():
        try:
            result['codes'] = _ai_filter_stocks(codes, debug=True, deadline=deadline, stats=stats)
            result['ok'] = True
        except Exception as e:
            result['ok'] = False
            result['error'] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(budget + 30)
    if t.is_alive():
        logging.error(f"[{strat['name']}] AI filter hard timeout (budget {budget_seconds:.0f}s + 30s), "
                      f"ignoring AI result, using unfiltered list")
        return "timeout", codes
    if not result.get('ok'):
        logging.error(f"[{strat['name']}] AI filter exception: {result.get('error')} "
                      f"-> skip this round, no file generated")
        return "error", None
    llm_failed = stats.get('llm_failed', 0)
    if stats.get('deadline_hit'):
        processed = stats.get('processed') or []
        qualified = stats.get('qualified') or []
        logging.warning(f"[{strat['name']}] AI filter deadline hit: processed {len(processed)}/{len(codes)}, "
                        f"qualified {len(qualified)}, "
                        f"{len(codes) - len(processed)} passed through unfiltered, "
                        f"llm_failed {llm_failed}")
    elif codes and llm_failed >= len(codes):
        logging.error(f"[{strat['name']}] AI 全部调用失败，本轮等于未过滤（{llm_failed}/{len(codes)} 只透传）")
    elif llm_failed:
        logging.warning(f"[{strat['name']}] AI 调用失败透传 {llm_failed}/{len(codes)} 只")
    return "ok", result['codes']


# ==================== Generate rebalance file ====================
def _atomic_write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp, path)


# Execution fields copied into every target file: the cloud reads its order time and its
# sizing parameters from there, so a strategy needs no separate params file. Keys missing
# from the config are omitted (the strategy then falls back to its own defaults).
EXEC_FIELDS = ("trading_times", "capital_ratio", "max_holdings", "candidate_pool_size",
               "cash_reserve_ratio", "rebalance_threshold")


def _payload(strat, stocks, generated_at):
    data = {
        "strategy": strat["name"],
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    for k in EXEC_FIELDS:
        if strat.get(k) is not None:
            data[k] = strat[k]
    data["stocks"] = stocks
    return data


def _write_rebalance_file(strat, stocks, exchange_path, generated_at,
                          upload_path=None, upload_name_tpl=None):
    """Writes the local archive and this strategy's upload file (target_<strategy>.json)."""
    data = _payload(strat, stocks, generated_at)
    action = "liquidate" if not stocks else f"{len(stocks)} stocks"
    if WRITE_ARCHIVE and exchange_path:
        filename = f"rebalance_{strat['name']}_{generated_at.strftime('%Y%m%d_%H%M')}.json"
        _atomic_write_json(os.path.join(exchange_path, filename), data)
        logging.info(f"[{strat['name']}] archive {filename} ({action})")
    if upload_path and upload_name_tpl:
        # one file per strategy: the cloud registers the strategies it must serve and reads
        # each one's order times + parameters from its own file
        upload_name = upload_name_tpl % strat["name"]
        _atomic_write_json(os.path.join(upload_path, upload_name), data)
        logging.info(f"[{strat['name']}] upload {os.path.join(upload_path, upload_name)} "
                     f"({action})")


def _generate_pair(context, strat, trading_time_str, force=False):
    start = datetime.datetime.now()
    codes, note = _load_stock_list(strat)
    if note != "ok":
        # List unavailable (no mail yet / attachment missing / too old to trust / unreadable):
        # write NOTHING so the upload dir keeps the PREVIOUS trading day's target and the
        # PTrade side goes on using it. The endgame is decided on the cloud side by that
        # file's age (older than MAX_TARGET_AGE_DAYS -> liquidate).
        logging.error(f"[{strat['name']}] list unavailable ({note}) -> no file written this "
                      f"round; PTrade keeps using the previous target")
        return
    if not codes:
        # The source explicitly handed us an empty list -> liquidate (old semantics).
        _write_rebalance_file(strat, [], context['exchange_path'], start,
                              context.get('upload_path'), context.get('upload_name_tpl'))
        return
    # AI budget: min(10 min, time remaining to trading_time); --now has no trading_time constraint
    if force or trading_time_str is None:
        budget = AI_FILTER_MAX_SECONDS
    else:
        h, m = map(int, trading_time_str.split(':'))
        deadline = start.replace(hour=h, minute=m, second=0, microsecond=0)
        if start > deadline:
            budget = 0
        else:
            budget = min(AI_FILTER_MAX_SECONDS, (deadline - start).total_seconds())
    status, filtered = _ai_filter_with_budget(strat, codes, budget)
    if status == "error":
        return  # skip this round, no file generated
    final_codes = filtered if status == "ok" else codes  # timeout -> unfiltered list
    _write_rebalance_file(strat, final_codes, context['exchange_path'],
                          datetime.datetime.now(),
                          context.get('upload_path'), context.get('upload_name_tpl'))


def _generate_due(context, generated_set, force=False):
    """Generate due (strategy, trading_time) list files; in-memory dedup prevents re-generation."""
    now = datetime.datetime.now()
    current = now.strftime("%H:%M")
    today = now.strftime("%Y%m%d")
    schedule = context['schedule']
    for gen_time, pairs in schedule.items():
        if not force and gen_time > current:
            continue
        for strat, trading_time in pairs:
            key = (today, strat['name'], trading_time)
            if key in generated_set:
                continue
            if not force and trading_time < current:
                continue  # trading time already passed, do not backfill
            generated_set.add(key)
            logging.info(f"[{strat['name']}] generating list (for {trading_time} session, "
                         f"generation time {gen_time})")
            _generate_pair(context, strat, trading_time, force)


# ==================== Main flow ====================
def main_loop(run_now=False, config_file=None, run_email=False):
    if not run_email:
        check_single_instance()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    logging.info("ptrade target-list process starting")

    context = {}
    try:
        load_config(context, config_file)
    except Exception as e:
        logging.error(f"failed to load config: {e}")
        sys.exit(1)

    context['schedule'] = _build_schedule(context['strategy_configs'])
    wake_times = sorted(context['schedule'].keys())
    email_check_times = set()
    email_check_deadline = {}
    for gen, pairs in context['schedule'].items():
        for strat, _t in pairs:
            if strat.get("email_check_offset_minutes", DEFAULT_EMAIL_OFFSET_MINUTES) > 0:
                email_check_times.add(gen)
                if _t > email_check_deadline.get(gen, ''):
                    email_check_deadline[gen] = _t
    logging.info(f"generation times: {wake_times}")
    logging.info(f"email check times: {sorted(email_check_times)}")

    generated = set()
    email_checked_date = None
    email_checked = set()

    if run_email:
        log_section("email test mode (--email, no generation)")
        if context['email_config'] is not None:
            try:
                logging.info("[email] test check")
                check_email_and_save_attachment(context['email_config'])
            except Exception as e:
                logging.error(f"[email] test check failed: {e}")
        else:
            logging.warning("[email] test check skipped: email_reader_config.json missing or invalid")
        log_section("email test done")
        return

    if run_now:
        log_section("immediate mode (--now, no email check)")
        _generate_due(context, generated, force=True)
        log_section("immediate run done")
        return

    log_section("resident mode")
    while True:
        now = datetime.datetime.now()
        current_time_str = now.strftime("%H:%M")

        if is_weekday(now.date()):
            today = now.date()
            if email_checked_date != today:
                email_checked_date = today
                email_checked = set()

            # --- email check (before generation, failure does not block) ---
            if context['email_config'] is not None:
                due = [g for g in sorted(email_check_times)
                       if g <= current_time_str
                       and g not in email_checked
                       and email_check_deadline.get(g, '') >= current_time_str]
                if due:
                    email_checked.update(due)
                    try:
                        logging.info(f"[email] checking at {current_time_str}")
                        check_email_and_save_attachment(context['email_config'])
                    except Exception as e:
                        logging.error(f"[email] check failed (continuing): {e}")
                    time.sleep(1)

            # --- generate due list files ---
            _generate_due(context, generated)

            # --- wait for next wake point (recompute now: email check + AI filter
            # may have taken minutes; the stale loop-top now shifted the wake) ---
            now = datetime.datetime.now()
            next_time = _next_wake(now, wake_times)
            wait_seconds = (next_time - now).total_seconds()
            if wait_seconds > 60:
                log_section("waiting phase - trading day")
                logging.info(f"waiting until: {next_time.strftime('%Y-%m-%d %H:%M:%S')} "
                             f"({wait_seconds/60:.0f} minutes later)")
            _sleep_until(next_time)
        else:
            # non-trading day -> sleep until the first wake point of the next trading day
            next_day = now + datetime.timedelta(days=1)
            while not is_weekday(next_day.date()):
                next_day += datetime.timedelta(days=1)
            h, m = map(int, wake_times[0].split(':'))
            next_time = next_day.replace(hour=h, minute=m, second=0, microsecond=0)
            log_section("waiting phase - non-trading day")
            logging.info(f"waiting until: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
            _sleep_until(next_time)


if __name__ == "__main__":
    run_now = "--now" in sys.argv
    run_email = "--email" in sys.argv
    cfg_file = None
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            cfg_file = sys.argv[i + 1]
    main_loop(run_now, cfg_file, run_email)
