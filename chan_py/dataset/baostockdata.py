# -*- coding: utf-8 -*-
"""
Baostock 5分钟数据+复权因子下载器（持久Worker版）
- 主进程负责调度，单个持久子进程（Worker）完成K线下载
- Worker 只在启动/重启时登录一次，极大减少登录次数
- 主进程单线程安全，并对每个任务设定超时，超时自动杀死Worker并重建
- 断点续传 + 无数据记忆 + 智能休眠保持不变
"""

import baostock as bs
import pandas as pd
import time
import os
import json
import random
import signal
import multiprocessing
import logging
from datetime import datetime
from typing import List, Optional, Set, Tuple

# ================== 全局配置 ==================
OUTPUT_BASE_DIR = "./baostock_5min_raw"
FACTOR_OUTPUT_BASE_DIR = "./baostock_5min_factors"
STOCK_CACHE_FILE = "./stock_list_cache.parquet"

START_YEAR, START_MONTH, START_DAY = 2020, 1, 1
FREQ = "5"
ADJUST_FLAG = "3"
FIELDS = "date,time,open,high,low,close,volume,amount"

BASE_INTERVAL = 0.8            # 基础请求间隔（秒）
MAX_RETRIES = 3
MAX_LOGIN_RETRIES = 5
REQUEST_TIMEOUT = 90           # 单只股票单年份下载超时（秒）

# ========== 测试模式 ==========
TEST_MODE = False
TEST_STOCKS = ["sh.600036", "sz.000001", "sh.603107"]

CHECK_PRICE_COMPLETENESS = True
CHECK_FACTOR_COMPLETENESS = True

# ========== 全局中断标志 ==========
interrupted = False

def signal_handler(sig, frame):
    global interrupted
    interrupted = True
    print("\n收到中断信号，将在当前任务完成后退出...")

signal.signal(signal.SIGINT, signal_handler)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ------------------ 全局登录（仅用于股票列表和复权因子）------------------
GLOBAL_LOGIN = None

def init_global_login():
    global GLOBAL_LOGIN
    if GLOBAL_LOGIN is None:
        for attempt in range(MAX_LOGIN_RETRIES):
            try:
                lg = bs.login()
                if lg.error_code == '0':
                    GLOBAL_LOGIN = lg
                    logger.info("全局登录成功")
                    return True
                logger.warning(f"登录失败 (尝试 {attempt+1}/{MAX_LOGIN_RETRIES}): {lg.error_msg}")
                time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"登录异常: {str(e)}")
                time.sleep(2 ** attempt)
        return False
    return True

# ------------------ 股票列表获取 ------------------
def get_filtered_stock_codes(use_cache: bool = True) -> List[str]:
    if TEST_MODE:
        return TEST_STOCKS

    if use_cache and os.path.exists(STOCK_CACHE_FILE):
        logger.info("从缓存加载股票列表...")
        try:
            df_cache = pd.read_parquet(STOCK_CACHE_FILE)
            codes = df_cache['code'].tolist()
            logger.info(f"加载 {len(codes)} 只股票")
            return codes
        except Exception as e:
            logger.warning(f"缓存读取失败: {e}")

    logger.info("从 Baostock 获取股票列表...")
    rs = bs.query_stock_basic()
    if rs.error_code != '0':
        logger.error(f"获取失败: {rs.error_msg}")
        return []
    data_list = []
    while rs.next():
        data_list.append(rs.get_row_data())
    df = pd.DataFrame(data_list, columns=rs.fields)
    df = df[(df['type'] == '1') & (df['status'] == '1')].copy()

    def keep_a_stock(code: str) -> bool:
        if code.startswith(('sh.60', 'sh.688', 'sz.00', 'sz.30', 'bj.')):
            return True
        return False

    df = df[df['code'].apply(keep_a_stock)]
    codes = df['code'].tolist()
    logger.info(f"筛选后共 {len(codes)} 只A股")
    try:
        df[['code']].to_parquet(STOCK_CACHE_FILE, index=False)
    except:
        pass
    return codes

# ------------------ 持久 Worker 进程类 ------------------
class DownloadWorkerProcess(multiprocessing.Process):
    """
    独立进程，长时间存活。
    启动时登录一次，然后循环读取任务队列，执行下载，将结果写入结果队列。
    """
    def __init__(self, task_queue, result_queue):
        super().__init__()
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.daemon = True  # 主进程退出时自动终止

    def run(self):
        """Worker 主循环"""
        # 登录
        lg = bs.login()
        if lg.error_code != '0':
            logger.error(f"Worker 登录失败: {lg.error_msg}")
            self.result_queue.put(None)  # 通知主进程登录失败
            return
        logger.info("Worker 登录成功，开始处理任务")

        try:
            while True:
                task = self.task_queue.get()
                if task is None:  # 退出信号
                    logger.info("Worker 收到退出信号")
                    break

                stock_code, year = task
                result = self._download(stock_code, year)
                self.result_queue.put(result)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.error(f"Worker 异常: {e}")
        finally:
            bs.logout()
            logger.info("Worker 已登出并退出")

    def _download(self, stock_code: str, year: int) -> Tuple[str, int, bool, int]:
        """执行实际下载，返回 (stock_code, year, success, rows)"""
        try:
            year_start = f"{year}-01-01"
            year_end = f"{year}-12-31"
            if year == START_YEAR:
                year_start = f"{START_YEAR}-{START_MONTH:02d}-{START_DAY:02d}"
            if year == datetime.now().year:
                year_end = datetime.now().strftime("%Y-%m-%d")

            rs = bs.query_history_k_data_plus(
                code=stock_code,
                fields=FIELDS,
                start_date=year_start,
                end_date=year_end,
                frequency=FREQ,
                adjustflag=ADJUST_FLAG,
            )
            if rs.error_code != '0':
                return stock_code, year, False, 0

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            if not data_list:
                return stock_code, year, False, 0

            df = pd.DataFrame(data_list, columns=rs.fields)
            numeric_cols = ["open", "high", "low", "close", "volume", "amount"]
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            df['datetime'] = pd.to_datetime(
                df['time'].astype(str).str[:14],
                format='%Y%m%d%H%M%S',
                errors='coerce'
            )
            df = df.dropna(subset=['datetime'])
            if df.empty:
                return stock_code, year, False, 0
            df = df.drop_duplicates('datetime').sort_values('datetime')
            df.insert(0, 'code', stock_code)
            df = df[['code', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'amount']]

            # 保存文件
            market = stock_code.split('.')[0]
            filepath = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}.parquet")
            if os.path.exists(filepath):
                existing = pd.read_parquet(filepath)
                combined = pd.concat([existing, df], ignore_index=True)
                combined.to_parquet(filepath, index=False)
            else:
                os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
                df.to_parquet(filepath, index=False)

            return stock_code, year, True, len(df)

        except Exception as e:
            logger.error(f"Worker 下载失败 {stock_code} {year}: {e}")
            return stock_code, year, False, 0

# ------------------ 辅助函数（同原版） ------------------
def fetch_adjust_factors(stock_code: str, start_year: int, end_year: int) -> Optional[pd.DataFrame]:
    """获取复权因子（主进程执行，使用全局登录）"""
    start_date = f"{start_year}-01-01"
    end_date = f"{end_year}-12-31"
    for attempt in range(MAX_RETRIES):
        if interrupted:
            return None
        try:
            rs = bs.query_adjust_factor(code=stock_code, start_date=start_date, end_date=end_date)
            if rs.error_code != '0':
                logger.warning(f"{stock_code} 复权因子请求失败 (尝试 {attempt+1}/{MAX_RETRIES}): {rs.error_msg}")
                time.sleep(2 ** attempt)
                continue
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            if not data_list:
                return pd.DataFrame()
            df = pd.DataFrame(data_list, columns=rs.fields)
            factor_cols = ['foreAdjustFactor', 'backAdjustFactor', 'adjustFactor']
            for col in factor_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if 'dividOperateDate' in df.columns:
                df['dividOperateDate'] = pd.to_datetime(df['dividOperateDate'], errors='coerce')
            return df
        except Exception as e:
            logger.error(f"{stock_code} 复权因子异常 (尝试 {attempt+1}/{MAX_RETRIES}): {e}")
            time.sleep(2 ** attempt)
    return None

def append_to_parquet(df: pd.DataFrame, filepath: str):
    if df.empty:
        return
    if os.path.exists(filepath):
        existing = pd.read_parquet(filepath)
        combined = pd.concat([existing, df], ignore_index=True)
        combined.to_parquet(filepath, index=False)
    else:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        df.to_parquet(filepath, index=False)

# ------------------ 元数据管理（无数据记忆） ------------------
def get_price_metadata(market: str, year: int) -> Set[str]:
    meta_path = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}_metadata.json")
    if not os.path.exists(meta_path):
        return set()
    try:
        with open(meta_path, 'r') as f:
            data = json.load(f)
            return set(data.get('completed_codes', []))
    except:
        return set()

def update_price_metadata(market: str, year: int, code: str):
    existing = get_price_metadata(market, year)
    existing.add(code)
    meta_path = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}_metadata.json")
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, 'w') as f:
        json.dump({'completed_codes': list(existing)}, f, indent=2)

def get_no_data_metadata(market: str, year: int) -> Set[str]:
    meta_path = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}_no_data.json")
    if not os.path.exists(meta_path):
        return set()
    try:
        with open(meta_path, 'r') as f:
            data = json.load(f)
            return set(data.get('no_data_codes', []))
    except:
        return set()

def update_no_data_metadata(market: str, year: int, code: str):
    existing = get_no_data_metadata(market, year)
    existing.add(code)
    meta_path = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}_no_data.json")
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, 'w') as f:
        json.dump({'no_data_codes': list(existing)}, f, indent=2)

def is_kline_need_process(market: str, year: int, code: str) -> bool:
    if not CHECK_PRICE_COMPLETENESS:
        return True
    if code in get_price_metadata(market, year):
        return False
    if code in get_no_data_metadata(market, year):
        return False
    return True

def get_factor_metadata(market: str) -> Set[str]:
    meta_path = os.path.join(FACTOR_OUTPUT_BASE_DIR, f"{market}_factor_metadata.json")
    if not os.path.exists(meta_path):
        return set()
    try:
        with open(meta_path, 'r') as f:
            data = json.load(f)
            return set(data.get('completed_codes', []))
    except:
        return set()

def update_factor_metadata(market: str, code: str):
    existing = get_factor_metadata(market)
    existing.add(code)
    meta_path = os.path.join(FACTOR_OUTPUT_BASE_DIR, f"{market}_factor_metadata.json")
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, 'w') as f:
        json.dump({'completed_codes': list(existing)}, f, indent=2)

def is_factor_completed(market: str, code: str) -> bool:
    if not CHECK_FACTOR_COMPLETENESS:
        return False
    return code in get_factor_metadata(market)

def smart_sleep(start_time: float):
    elapsed = time.time() - start_time
    if elapsed < 0.5:
        sleep_time = BASE_INTERVAL * 0.8 + random.uniform(0, 0.2)
    elif elapsed > 2.0:
        sleep_time = BASE_INTERVAL * 1.2 + random.uniform(0, 0.3)
    else:
        sleep_time = BASE_INTERVAL + random.uniform(0, 0.2)
    time.sleep(sleep_time)

# ------------------ 处理单一年份（使用 Worker 池） ------------------
def start_worker(task_queue, result_queue):
    """创建并启动一个 Worker"""
    worker = DownloadWorkerProcess(task_queue, result_queue)
    worker.start()
    # 等待几毫秒，让 Worker 完成登录并将 ready 信号放入结果队列（我们改用 None 标记失败）
    # 但更简单：直接开始使用，超时机制会处理异常
    return worker

def process_year(target_year: int, all_stocks: List[str]) -> None:
    logger.info(f"\n{'='*60}\n开始处理 {target_year} 年数据\n{'='*60}")

    # 预加载已完成和无数据集合
    market_completed = {}
    market_no_data = {}
    for market in ['sh', 'sz', 'bj']:
        market_completed[market] = get_price_metadata(market, target_year)
        market_no_data[market] = get_no_data_metadata(market, target_year)

    pending = []
    for code in all_stocks:
        market = code.split('.')[0]
        if market not in market_completed:
            continue
        if code in market_completed[market] or code in market_no_data[market]:
            continue
        pending.append(code)

    if not pending:
        logger.info(f"{target_year} 年所有股票已处理（成功或无数据），跳过。")
        return

    logger.info(f"{target_year}年：总任务 {len(pending)} 只，开始处理。")

    # 创建队列和 Worker
    ctx = multiprocessing.get_context('spawn')
    task_queue = ctx.Queue()
    result_queue = ctx.Queue()
    worker = start_worker(task_queue, result_queue)

    price_success = 0
    total_rows = 0

    from tqdm import tqdm
    with tqdm(total=len(pending), desc=f"{target_year}年", unit="只", ncols=130) as pbar:
        for idx, code in enumerate(pending):
            if interrupted:
                logger.warning("用户中断，停止当前年份处理")
                break

            market = code.split('.')[0]
            pbar.set_description(f"{target_year}年 {code}")

            # 发送任务给 Worker
            task_queue.put((code, target_year))

            # 等待结果，带超时
            try:
                res = result_queue.get(timeout=REQUEST_TIMEOUT)
                if res is None:  # Worker 登录失败
                    logger.error("Worker 异常退出，尝试重启...")
                    worker.terminate()
                    worker.join()
                    # 重启 Worker
                    worker = start_worker(task_queue, result_queue)
                    update_no_data_metadata(market, target_year, code)
                    pbar.update(1)
                    pbar.set_postfix_str(f"K线成功:{price_success}/{len(pending)} | 行数:{total_rows:,}")
                    smart_sleep(time.time())
                    continue

                result_code, result_year, success, rows = res
                if success:
                    update_price_metadata(market, target_year, code)
                    price_success += 1
                    total_rows += rows
                    logger.info(f"✅ {code} {target_year}年K线已保存，{rows} 行")
                else:
                    update_no_data_metadata(market, target_year, code)
                    logger.info(f"{code} {target_year}年无数据或失败，已记录跳过")

            except Exception as e:
                # 超时或其他队列异常
                logger.error(f"{code} {target_year} 任务超时或通信异常: {e}")
                # 强制终止 Worker 并重启
                worker.terminate()
                worker.join()
                worker = start_worker(task_queue, result_queue)
                update_no_data_metadata(market, target_year, code)

            # 处理复权因子（仍由主进程完成，因为全局已登录）
            if not is_factor_completed(market, code):
                logger.info(f"开始获取 {code} 复权因子...")
                df_factor = fetch_adjust_factors(code, START_YEAR, datetime.now().year)
                if df_factor is not None and not df_factor.empty:
                    factor_path = os.path.join(FACTOR_OUTPUT_BASE_DIR, f"{market}_adjust_factors.parquet")
                    append_to_parquet(df_factor, factor_path)
                    update_factor_metadata(market, code)
                    logger.info(f"✅ {code} 复权因子已保存，{len(df_factor)} 条")
                else:
                    logger.info(f"{code} 无复权因子数据")

            pbar.update(1)
            pbar.set_postfix_str(f"K线成功:{price_success}/{len(pending)} | 行数:{total_rows:,}")

            # 智能休眠
            smart_sleep(time.time())

    # 通知 Worker 退出
    task_queue.put(None)
    worker.join(timeout=5)
    if worker.is_alive():
        worker.terminate()

    logger.info(f"{target_year}年完成：成功写入K线 {price_success} 只，累计行数 {total_rows:,}")

# ------------------ 主程序 ------------------
def main():
    logger.info("=== Baostock 5分钟数据+复权因子下载器（持久Worker版）===")
    os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
    os.makedirs(FACTOR_OUTPUT_BASE_DIR, exist_ok=True)

    # 全局登录一次（用于股票列表、复权因子）
    if not init_global_login():
        logger.error("主进程登录失败，程序退出")
        return

    if TEST_MODE:
        logger.info(f"【测试模式】仅下载: {TEST_STOCKS}")
        all_stocks = TEST_STOCKS
    else:
        all_stocks = get_filtered_stock_codes(use_cache=True)
        if not all_stocks:
            logger.error("获取股票列表失败")
            return
        logger.info(f"【全市场模式】共 {len(all_stocks)} 只股票")

    current_year = datetime.now().year
    for year in range(START_YEAR, current_year + 1):
        if interrupted:
            break
        process_year(year, all_stocks)
        time.sleep(2)

    bs.logout()
    logger.info("\n🎉 程序结束")

if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n用户强制中断")
    finally:
        try:
            bs.logout()
        except:
            pass