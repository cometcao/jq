# -*- coding: utf-8 -*-
"""
qmt_stdqmt_target.py - Standard QMT migration: external target-list process (zero API deps)

Flow: email check -> read list (read email landed files directly) -> AI filter ->
write rebalance_<strategy>_<timestamp>.json
- File generation time: before each strategy trading_time (default trading_time - 5 min,
  immediately after email check completes)
- Empty list (missing/expired/read failed) = liquidate; AI filter timeout =
  unfiltered list + error log; AI filter exception = skip this round, no file generated
- Startup validation: stock_list_dir must match email save_directory, otherwise refuse to generate
- Never touches: xtquant, tracker, account queries, money calculation

Usage:
  python qmt_stdqmt_target.py                # resident mode (wakes on trading days per schedule)
  python qmt_stdqmt_target.py --now          # generate once for all strategies immediately (no email check)
  python qmt_stdqmt_target.py --config x.json
"""

import json
import os
import sys
import time
import atexit
import logging
import datetime
import threading

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
LOCK_FILE = "stdqmt_target.lock"


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
    lock_file = LOCK_FILE
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
    """Load the single new config (qmt_stdqmt_config.json), fully self-contained."""
    new_path = config_file or "qmt_stdqmt_config.json"
    with open(new_path, encoding='utf-8') as f:
        new_cfg = json.load(f)

    # external process log (FileHandler added only once)
    log_file = new_cfg.get("log_file", "logs/stdqmt_plan.log")
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
        with open("email_reader_config.json", 'r', encoding='utf-8') as f:
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
    context['exchange_path'] = new_cfg.get("exchange_path", "qmt_exchange")
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
    """Return (status, codes): ok=filter result / timeout=unfiltered list / error=skip this round."""
    result = {}

    def worker():
        try:
            result['codes'] = _ai_filter_stocks(codes, debug=True)
            result['ok'] = True
        except Exception as e:
            result['ok'] = False
            result['error'] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(max(budget_seconds, 1))
    if t.is_alive():
        logging.error(f"[{strat['name']}] AI filter timeout (budget {budget_seconds:.0f}s), "
                      f"ignoring AI result, using unfiltered list")
        return "timeout", codes
    if not result.get('ok'):
        logging.error(f"[{strat['name']}] AI filter exception: {result.get('error')} "
                      f"-> skip this round, no file generated")
        return "error", None
    return "ok", result['codes']


# ==================== Generate rebalance file ====================
def _write_rebalance_file(strat, stocks, exchange_path, generated_at):
    filename = f"rebalance_{strat['name']}_{generated_at.strftime('%Y%m%d_%H%M')}.json"
    os.makedirs(exchange_path, exist_ok=True)
    path = os.path.join(exchange_path, filename)
    data = {
        "strategy": strat["name"],
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "stocks": stocks,
    }
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp, path)
    action = "liquidate" if not stocks else f"{len(stocks)} stocks"
    logging.info(f"[{strat['name']}] generated {filename} ({action})")


def _generate_pair(context, strat, trading_time_str, force=False):
    start = datetime.datetime.now()
    codes, note = _load_stock_list(strat)
    if note != "ok" or not codes:
        _write_rebalance_file(strat, [], context['exchange_path'], start)
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
    _write_rebalance_file(strat, final_codes, context['exchange_path'], datetime.datetime.now())


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
def main_loop(run_now=False, config_file=None):
    check_single_instance()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    logging.info("standard QMT target-list process starting")

    context = {}
    try:
        load_config(context, config_file)
    except Exception as e:
        logging.error(f"failed to load config: {e}")
        sys.exit(1)

    context['schedule'] = _build_schedule(context['strategy_configs'])
    wake_times = sorted(context['schedule'].keys())
    email_check_times = set()
    for gen, pairs in context['schedule'].items():
        for strat, _t in pairs:
            if strat.get("email_check_offset_minutes", DEFAULT_EMAIL_OFFSET_MINUTES) > 0:
                email_check_times.add(gen)
    logging.info(f"generation times: {wake_times}")
    logging.info(f"email check times: {sorted(email_check_times)}")

    generated = set()
    last_email_check_time = None

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
            # --- email check (before generation, failure does not block) ---
            if (context['email_config'] is not None and current_time_str in email_check_times
                    and (last_email_check_time is None or (now - last_email_check_time).total_seconds() > 60)):
                try:
                    logging.info(f"[email] checking at {current_time_str}")
                    check_email_and_save_attachment(context['email_config'])
                except Exception as e:
                    logging.error(f"[email] check failed (continuing): {e}")
                last_email_check_time = now
                time.sleep(1)

            # --- generate due list files ---
            _generate_due(context, generated)

            # --- wait for next wake point ---
            next_time = _next_wake(now, wake_times)
            wait_seconds = (next_time - now).total_seconds()
            if wait_seconds > 60:
                log_section("waiting phase - trading day")
                logging.info(f"waiting until: {next_time.strftime('%Y-%m-%d %H:%M:%S')} "
                             f"({wait_seconds/60:.0f} minutes later)")
                time.sleep(wait_seconds)
            else:
                time.sleep(min(wait_seconds, 5) if wait_seconds > 0 else 5)
        else:
            # non-trading day -> sleep until the first wake point of the next trading day
            next_day = now + datetime.timedelta(days=1)
            while not is_weekday(next_day.date()):
                next_day += datetime.timedelta(days=1)
            h, m = map(int, wake_times[0].split(':'))
            next_time = next_day.replace(hour=h, minute=m, second=0, microsecond=0)
            log_section("waiting phase - non-trading day")
            logging.info(f"waiting until: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep((next_time - now).total_seconds())


if __name__ == "__main__":
    run_now = "--now" in sys.argv
    cfg_file = None
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            cfg_file = sys.argv[i + 1]
    main_loop(run_now, cfg_file)
