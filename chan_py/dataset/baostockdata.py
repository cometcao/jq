# -*- coding: utf-8 -*-
"""
Baostock 5分钟数据+复权因子下载器（安全稳固版）
- 主进程管理调度，持久子进程（Worker）负责K线下载
- Worker 登录一次，循环处理任务，极大减少登录次数
- 严格区分：成功有数据 / 成功无数据 / 临时失败
- 临时失败不记录任何元数据，下次启动自动重试
- Parquet 损坏时自动备份原文件（.bak）并重建，绝不丢失历史数据
- 断点续传、智能休眠、超时重启Worker
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
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple

# ================== 全局配置 ==================
OUTPUT_BASE_DIR = "./baostock_5min_raw"
FACTOR_OUTPUT_BASE_DIR = "./baostock_5min_factors"
STOCK_CACHE_FILE = "./stock_list_cache.parquet"

START_YEAR, START_MONTH, START_DAY = 2020, 1, 1
FREQ = "5"
ADJUST_FLAG = "3"
FIELDS = "date,time,open,high,low,close,volume,amount"

BASE_INTERVAL = 0.8
MAX_RETRIES = 3
MAX_LOGIN_RETRIES = 5
REQUEST_TIMEOUT = 90           # 单任务超时（秒）

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

# ------------------ 全局登录（用于股票列表和复权因子）------------------
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

# ------------------ 持久 Worker 进程 ------------------
class DownloadWorkerProcess(multiprocessing.Process):
    def __init__(self, task_queue, result_queue):
        super().__init__()
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.daemon = True

    def run(self):
        lg = bs.login()
        if lg.error_code != '0':
            logger.error(f"Worker 登录失败: {lg.error_msg}")
            self.result_queue.put(None)
            return
        logger.info("Worker 登录成功，开始处理任务")

        try:
            while True:
                task = self.task_queue.get()
                if task is None:
                    logger.info("Worker 收到退出信号")
                    break

                stock_code, year, start_date, end_date, is_incremental = task
                result = self._download(stock_code, year, start_date, end_date, is_incremental)
                self.result_queue.put(result)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.error(f"Worker 异常: {e}")
        finally:
            bs.logout()
            logger.info("Worker 已登出并退出")

    def _download(self, stock_code: str, year: int, start_date: str, end_date: str,
                  is_incremental: bool = False) -> Tuple[str, int, str, int]:
        """
        返回: (stock_code, year, status, rows)
        status: 'success_data' / 'success_no_data' / 'failure'
        """
        try:
            rs = bs.query_history_k_data_plus(
                code=stock_code,
                fields=FIELDS,
                start_date=start_date,
                end_date=end_date,
                frequency=FREQ,
                adjustflag=ADJUST_FLAG,
            )
            if rs.error_code != '0':
                return stock_code, year, 'failure', 0

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            if not data_list:
                return stock_code, year, 'success_no_data', 0

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
                return stock_code, year, 'success_no_data', 0
            df = df.drop_duplicates('datetime').sort_values('datetime')
            df.insert(0, 'code', stock_code)
            df = df[['code', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'amount']]

            market = stock_code.split('.')[0]
            filepath = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}.parquet")
            self._safe_append_to_parquet(df, filepath)

            if is_incremental and not df.empty:
                today_str = datetime.now().strftime("%Y%m%d")
                delta_filepath = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}_delta_{today_str}.parquet")
                self._safe_append_to_parquet(df, delta_filepath)

            return stock_code, year, 'success_data', len(df)

        except Exception as e:
            logger.error(f"Worker 下载失败 {stock_code} {year}: {e}")
            return stock_code, year, 'failure', 0

    @staticmethod
    def _safe_append_to_parquet(df: pd.DataFrame, filepath: str):
        """原子写入追加保存：先写临时文件，成功后再替换，绝不因写失败而损坏文件"""
        if df.empty:
            return
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        if os.path.exists(filepath):
            try:
                existing = pd.read_parquet(filepath)
            except Exception as e:
                backup_path = filepath + ".bak"
                logger.error(
                    f"‼️ 读取 Parquet 文件失败，原文件已备份至 {backup_path}。"
                    f"将用当前数据重新开始。错误: {e}"
                )
                os.rename(filepath, backup_path)
                existing = pd.DataFrame()
            combined = pd.concat([existing, df], ignore_index=True)
            combined = combined.drop_duplicates(['code', 'datetime'])
        else:
            combined = df

        tmp_path = filepath + ".tmp"
        combined.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, filepath)

# ------------------ 辅助函数 ------------------
def fetch_adjust_factors(stock_code: str, start_year: int, end_year: int) -> Optional[pd.DataFrame]:
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
    """主进程使用的追加函数（复权因子），原子写入保护"""
    if df.empty:
        return
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if os.path.exists(filepath):
        try:
            existing = pd.read_parquet(filepath)
        except Exception as e:
            backup_path = filepath + ".bak"
            logger.error(
                f"‼️ 复权因子文件读取失败，原文件备份至 {backup_path}。"
                f"将用当前数据重新开始。错误: {e}"
            )
            os.rename(filepath, backup_path)
            existing = pd.DataFrame()
        combined = pd.concat([existing, df], ignore_index=True)
    else:
        combined = df

    tmp_path = filepath + ".tmp"
    combined.to_parquet(tmp_path, index=False)
    os.replace(tmp_path, filepath)

# ------------------ 元数据管理 ------------------
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

def is_factor_completed(market: str, code: str) -> bool:
    if not CHECK_FACTOR_COMPLETENESS:
        return False
    meta_path = os.path.join(FACTOR_OUTPUT_BASE_DIR, f"{market}_factor_metadata.json")
    if not os.path.exists(meta_path):
        return False
    try:
        with open(meta_path, 'r') as f:
            data = json.load(f)
            return code in data.get('completed_codes', [])
    except:
        return False

def update_factor_metadata(market: str, code: str):
    meta_path = os.path.join(FACTOR_OUTPUT_BASE_DIR, f"{market}_factor_metadata.json")
    existing = set()
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r') as f:
                data = json.load(f)
                existing = set(data.get('completed_codes', []))
        except:
            pass
    existing.add(code)
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, 'w') as f:
        json.dump({'completed_codes': list(existing)}, f, indent=2)

def get_sync_date(market: str, year: int, code: str) -> Optional[str]:
    meta_path = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}_sync_dates.json")
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, 'r') as f:
            data = json.load(f)
            return data.get(code)
    except:
        return None

def update_sync_date(market: str, year: int, code: str, date_str: str):
    meta_path = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}_sync_dates.json")
    existing = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r') as f:
                existing = json.load(f)
        except:
            pass
    existing[code] = date_str
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, 'w') as f:
        json.dump(existing, f, indent=2)

def get_factor_sync_date(market: str, code: str) -> Optional[str]:
    meta_path = os.path.join(FACTOR_OUTPUT_BASE_DIR, f"{market}_factor_sync_dates.json")
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, 'r') as f:
            data = json.load(f)
            return data.get(code)
    except:
        return None

def update_factor_sync_date(market: str, code: str, date_str: str):
    meta_path = os.path.join(FACTOR_OUTPUT_BASE_DIR, f"{market}_factor_sync_dates.json")
    existing = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r') as f:
                existing = json.load(f)
        except:
            pass
    existing[code] = date_str
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, 'w') as f:
        json.dump(existing, f, indent=2)

def smart_sleep(start_time: float):
    elapsed = time.time() - start_time
    if elapsed < 0.5:
        sleep_time = BASE_INTERVAL * 0.8 + random.uniform(0, 0.2)
    elif elapsed > 2.0:
        sleep_time = BASE_INTERVAL * 1.2 + random.uniform(0, 0.3)
    else:
        sleep_time = BASE_INTERVAL + random.uniform(0, 0.2)
    time.sleep(sleep_time)

def _load_last_dates_from_parquet(market: str, year: int) -> dict:
    """从已有parquet文件中批量读取每只股票的最后日期，返回 {code: 'YYYY-MM-DD'}"""
    filepath = os.path.join(OUTPUT_BASE_DIR, f"{market}_{year}.parquet")
    if not os.path.exists(filepath):
        return {}
    try:
        df = pd.read_parquet(filepath, columns=['code', 'datetime'])
        if df.empty:
            return {}
        max_dates = df.groupby('code')['datetime'].max()
        result = {}
        for code, dt in max_dates.items():
            if pd.notna(dt):
                result[code] = dt.strftime("%Y-%m-%d")
        return result
    except Exception as e:
        logger.warning(f"读取 {filepath} 获取最后日期失败: {e}")
        return {}

# ------------------ 处理单一年份 ------------------
def start_worker(task_queue, result_queue):
    worker = DownloadWorkerProcess(task_queue, result_queue)
    worker.start()
    return worker

def process_year(target_year: int, all_stocks: List[str]) -> None:
    logger.info(f"\n{'='*60}\n开始处理 {target_year} 年数据\n{'='*60}")

    # 加载已完成和无数据集合
    market_completed = {}
    market_no_data = {}
    for market in ['sh', 'sz', 'bj']:
        market_completed[market] = get_price_metadata(market, target_year)
        market_no_data[market] = get_no_data_metadata(market, target_year)

    year_start = f"{target_year}-01-01"
    year_end = f"{target_year}-12-31"
    if target_year == START_YEAR:
        year_start = f"{START_YEAR}-{START_MONTH:02d}-{START_DAY:02d}"
    if target_year == datetime.now().year:
        year_end = datetime.now().strftime("%Y-%m-%d")

    # 当前年迁移：从已有 parquet 读取最后日期，避免全量重下
    parquet_last_dates = {}
    if target_year == datetime.now().year:
        for market in ['sh', 'sz', 'bj']:
            parquet_last_dates[market] = _load_last_dates_from_parquet(market, target_year)

    pending = []
    task_info = {}
    for code in all_stocks:
        market = code.split('.')[0]
        if market not in market_completed:
            continue
        if code in market_no_data[market]:
            continue

        sync_date = get_sync_date(market, target_year, code)

        if sync_date is not None:
            if sync_date >= year_end:
                continue
            start_dt = datetime.strptime(sync_date, "%Y-%m-%d") + timedelta(days=1)
            query_start = start_dt.strftime("%Y-%m-%d")
            query_end = year_end
            is_incremental = True
            pending.append(code)
            task_info[code] = (query_start, query_end, is_incremental)
        elif code in market_completed[market]:
            if target_year < datetime.now().year:
                update_sync_date(market, target_year, code, f"{target_year}-12-31")
                continue
            else:
                # 当前年迁移：从 parquet 文件推断最后日期
                last_date = parquet_last_dates.get(market, {}).get(code)
                if last_date is not None:
                    sync_date = last_date
                    update_sync_date(market, target_year, code, sync_date)
                    if sync_date >= year_end:
                        continue
                    start_dt = datetime.strptime(sync_date, "%Y-%m-%d") + timedelta(days=1)
                    query_start = start_dt.strftime("%Y-%m-%d")
                    query_end = year_end
                    is_incremental = True
                    pending.append(code)
                    task_info[code] = (query_start, query_end, is_incremental)
                else:
                    query_start = year_start
                    query_end = year_end
                    is_incremental = False
                    pending.append(code)
                    task_info[code] = (query_start, query_end, is_incremental)
        else:
            query_start = year_start
            query_end = year_end
            is_incremental = False
            pending.append(code)
            task_info[code] = (query_start, query_end, is_incremental)

    if not pending:
        logger.info(f"{target_year} 年所有股票已处理（成功或无数据），跳过。")
        return

    logger.info(f"{target_year}年：待处理 {len(pending)} 只，启动 Worker。")

    ctx = multiprocessing.get_context('spawn')
    task_queue = ctx.Queue()
    result_queue = ctx.Queue()
    worker = start_worker(task_queue, result_queue)

    price_success = 0
    total_rows = 0
    failure_count = 0

    from tqdm import tqdm
    with tqdm(total=len(pending), desc=f"{target_year}年", unit="只", ncols=130) as pbar:
        for code in pending:
            if interrupted:
                logger.warning("用户中断，停止当前年份处理")
                break

            market = code.split('.')[0]
            pbar.set_description(f"{target_year}年 {code}")

            q_start, q_end, is_incr = task_info[code]
            task_queue.put((code, target_year, q_start, q_end, is_incr))

            try:
                res = result_queue.get(timeout=REQUEST_TIMEOUT)
            except Exception as e:
                logger.error(f"接收结果超时或异常: {e}")
                res = None

            if res is None:
                logger.error("Worker 无响应或返回空，重启...")
                worker.terminate()
                worker.join()
                worker = start_worker(task_queue, result_queue)
                failure_count += 1
                pbar.update(1)
                pbar.set_postfix_str(f"成功:{price_success} 失败:{failure_count} 行数:{total_rows:,}")
                smart_sleep(time.time())
                continue

            result_code, result_year, status, rows = res

            if status == 'success_data':
                update_price_metadata(market, target_year, code)
                update_sync_date(market, target_year, code, task_info[code][1])
                price_success += 1
                total_rows += rows
                logger.info(f"✅ {code} {target_year}年K线已保存，{rows} 行")
            elif status == 'success_no_data':
                update_no_data_metadata(market, target_year, code)
                update_sync_date(market, target_year, code, task_info[code][1])
                logger.info(f"{code} {target_year}年无数据，已记录跳过")
            else:  # 'failure'
                logger.warning(f"{code} {target_year}年临时失败，不标记，下次重试")
                failure_count += 1

            # 处理复权因子
            factor_sync = get_factor_sync_date(market, code)
            cur_date = datetime.now().strftime("%Y-%m-%d")
            need_factor = (
                not is_factor_completed(market, code)
                or factor_sync is None
                or factor_sync < cur_date
            )
            if need_factor:
                df_factor = fetch_adjust_factors(code, START_YEAR, datetime.now().year)
                if df_factor is not None and not df_factor.empty:
                    factor_path = os.path.join(FACTOR_OUTPUT_BASE_DIR, f"{market}_adjust_factors.parquet")
                    append_to_parquet(df_factor, factor_path)
                    update_factor_metadata(market, code)
                    today_str = datetime.now().strftime("%Y%m%d")
                    factor_delta_path = os.path.join(FACTOR_OUTPUT_BASE_DIR, f"{market}_adjust_factors_delta_{today_str}.parquet")
                    append_to_parquet(df_factor, factor_delta_path)
                    update_factor_sync_date(market, code, cur_date)
                    logger.info(f"✅ {code} 复权因子已保存，{len(df_factor)} 条")
                elif df_factor is not None and df_factor.empty:
                    update_factor_sync_date(market, code, cur_date)
                    logger.info(f"{code} 无复权因子数据")
                else:
                    logger.warning(f"{code} 复权因子临时失败，下次重试")

            pbar.update(1)
            pbar.set_postfix_str(f"成功:{price_success} 失败:{failure_count} 行数:{total_rows:,}")
            smart_sleep(time.time())

    task_queue.put(None)
    worker.join(timeout=5)
    if worker.is_alive():
        worker.terminate()

    logger.info(f"{target_year}年完成：成功 {price_success} 只，失败 {failure_count} 只，累计 {total_rows:,} 行")

# ------------------ 主程序 ------------------
def main():
    logger.info("=== Baostock 5分钟数据+复权因子下载器（安全稳固版）===")
    os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
    os.makedirs(FACTOR_OUTPUT_BASE_DIR, exist_ok=True)

    if not init_global_login():
        logger.error("主进程登录失败")
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