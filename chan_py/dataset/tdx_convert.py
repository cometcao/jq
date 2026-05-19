# -*- coding: utf-8 -*-
"""
通达信 5分钟数据 → Parquet 转换与合并工具
- 从 TDX 本地 .lc5 文件读取 5 分钟 K 线
- 转换成与 baostockdata.py 一致的格式
- 安全追加到年份文件 + 生成 delta 文件便于传输
- 支持将 delta 文件合并回主文件
- 原子写入 + 去重 + .bak 保护，绝不破坏已有数据
"""

import os
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from glob import glob
from typing import Optional, List, Set

import pandas as pd
from mootdx.reader import Reader

# ================== 全局配置 ==================
TDX_DIR = r"D:\gjzq\gjty"
OUTPUT_BASE_DIR = "./baostock_5min_raw"

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================== 工具函数 ==================

def detect_market(code: str) -> str:
    """从纯数字代码判断市场：600036 → sh, 000001 → sz, 4xxxxx → bj"""
    if code.startswith('sh.') or code.startswith('sz.') or code.startswith('bj.'):
        return code.split('.')[0]
    c = code.lstrip('sh').lstrip('sz').lstrip('bj')
    if len(c) != 6:
        c = code
    if c.startswith(('60', '68')):
        return 'sh'
    elif c.startswith(('00', '30', '13', '15', '16', '18', '20')):
        return 'sz'
    elif c.startswith(('4', '8')):
        return 'bj'
    return 'sh'


def safe_append_parquet(df: pd.DataFrame, filepath: str):
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
                f"读取 Parquet 文件失败，原文件已备份至 {backup_path}。"
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


def get_sync_date(market: str, year: int, code: str, output_dir: str = OUTPUT_BASE_DIR) -> Optional[str]:
    meta_path = os.path.join(output_dir, f"{market}_{year}_sync_dates.json")
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, 'r') as f:
            data = json.load(f)
            return data.get(code)
    except:
        return None


def update_sync_date(market: str, year: int, code: str, date_str: str, output_dir: str = OUTPUT_BASE_DIR):
    meta_path = os.path.join(output_dir, f"{market}_{year}_sync_dates.json")
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


# ================== TDX 数据读取 ==================

def scan_tdx_codes(tdx_dir: str = TDX_DIR) -> List[str]:
    """扫描通达信 fzline 目录，返回所有可用的股票代码列表（如 ['sh600036', 'sz000001']）"""
    codes = []
    for market in ['sh', 'sz', 'bj']:
        fzline_dir = os.path.join(tdx_dir, 'vipdoc', market, 'fzline')
        if not os.path.isdir(fzline_dir):
            continue
        for f in glob(os.path.join(fzline_dir, '*.lc5')):
            filename = os.path.basename(f)
            name = os.path.splitext(filename)[0]
            codes.append(name)
    return sorted(codes)


def read_tdx_5min(code: str, tdx_dir: str = TDX_DIR) -> Optional[pd.DataFrame]:
    """
    读取单只股票的 TDX 5分钟数据，转换为与 Baostock 一致的格式。
    code: '600036' 或 'sh600036' 或 'sh.600036'
    返回 DataFrame，列为 [code, datetime, open, high, low, close, volume, amount]
    """
    market = detect_market(code)
    numeric = code.split('.')[-1] if '.' in code else code.lstrip('sh').lstrip('sz').lstrip('bj')

    try:
        reader = Reader.factory(market='std', tdxdir=tdx_dir)
        df = reader.fzline(numeric)
    except Exception as e:
        logger.error(f"mootdx 读取 {code} 失败: {e}")
        return None

    if df is None or df.empty:
        return None

    df = df.reset_index()
    df = df.rename(columns={'date': 'datetime'})

    df['code'] = f"{market}.{numeric}"
    if 'volume' in df.columns:
        df['volume'] = df['volume'].fillna(0).astype('int64')
    for col in ['open', 'high', 'low', 'close', 'amount']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df[['code', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'amount']]
    df = df.dropna(subset=['datetime'])
    df = df.drop_duplicates(['code', 'datetime']).sort_values('datetime')

    return df


# ================== 核心流程 ==================

def process_date(date_str: str, tdx_dir: str = TDX_DIR, output_dir: str = OUTPUT_BASE_DIR):
    """
    从 TDX 读取指定日期的 5 分钟数据，追加到年份文件和 delta 文件。
    date_str: '20260515' 或 '2026-05-15'
    """
    date_str = date_str.replace('-', '')
    target_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    year = int(date_str[:4])
    date_display = date_str

    logger.info(f"=== 转换 TDX 5分钟数据: {target_date} ===")
    logger.info(f"TDX 目录: {tdx_dir}")
    logger.info(f"输出目录: {output_dir}")

    codes = scan_tdx_codes(tdx_dir)
    logger.info(f"扫描到 {len(codes)} 个 .lc5 文件")

    try:
        reader = Reader.factory(market='std', tdxdir=tdx_dir)
    except Exception as e:
        logger.error(f"mootdx 初始化失败: {e}")
        return

    success_count = 0
    total_rows = 0
    skip_count = 0
    fail_count = 0

    all_frames = []
    sync_updates = {}  # market -> {code: date_str}

    for i, code in enumerate(codes):
        if i > 0 and i % 500 == 0:
            logger.info(f"进度: {i}/{len(codes)} | 成功:{success_count} 跳过:{skip_count} 失败:{fail_count}")

        market = detect_market(code)
        numeric = code.split('.')[-1] if '.' in code else code.lstrip('sh').lstrip('sz').lstrip('bj')
        full_code = f"{market}.{numeric}"

        try:
            df = reader.fzline(numeric)
        except Exception as e:
            logger.error(f"读取 {full_code} 失败: {e}")
            fail_count += 1
            continue

        if df is None or df.empty:
            skip_count += 1
            continue

        df = df.reset_index()
        df = df.rename(columns={'date': 'datetime'})
        df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
        df_day = df[df['datetime'].dt.strftime('%Y-%m-%d') == target_date].copy()

        if df_day.empty:
            skip_count += 1
            continue

        df_day['code'] = full_code
        if 'volume' in df_day.columns:
            df_day.loc[:, 'volume'] = df_day['volume'].fillna(0).astype('int64')
        for col in ['open', 'high', 'low', 'close', 'amount']:
            if col in df_day.columns:
                df_day.loc[:, col] = pd.to_numeric(df_day[col], errors='coerce')

        df_day = df_day[['code', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        df_day = df_day.dropna(subset=['datetime'])
        df_day = df_day.drop_duplicates(['code', 'datetime']).sort_values('datetime')

        if df_day.empty:
            skip_count += 1
            continue

        all_frames.append(df_day)
        success_count += 1
        total_rows += len(df_day)

        if market not in sync_updates:
            sync_updates[market] = {}
        sync_updates[market][full_code] = target_date

    if not all_frames:
        logger.info("没有找到目标日期的数据")
        return

    logger.info(f"读取完成: {success_count} 只有数据, 正在写入...")
    combined = pd.concat(all_frames, ignore_index=True)

    for market in ['sh', 'sz', 'bj']:
        market_df = combined[combined['code'].str.startswith(market + '.')]
        if market_df.empty:
            continue

        year_file = os.path.join(output_dir, f"{market}_{year}.parquet")
        delta_file = os.path.join(output_dir, f"{market}_{year}_delta_{date_display}.parquet")

        safe_append_parquet(market_df, year_file)
        safe_append_parquet(market_df, delta_file)

        logger.info(f"  {market}: {len(market_df):,} 行 → {os.path.basename(year_file)}")

    for market, code_dates in sync_updates.items():
        for code, date_str_sync in code_dates.items():
            update_sync_date(market, year, code, date_str_sync, output_dir)

    logger.info(f"\n{'='*60}")
    logger.info(f"转换完成: 成功 {success_count} 只, 跳过 {skip_count} 只, 失败 {fail_count} 只")
    logger.info(f"累计 {total_rows:,} 行数据已写入")
    logger.info(f"增量文件: {output_dir}/{{market}}_{year}_delta_{date_display}.parquet")


# ================== Delta 合并功能 ==================

def merge_delta_file(delta_path: str, output_dir: str = OUTPUT_BASE_DIR, delete_after: bool = False):
    """
    将单个 delta 文件合并到对应的年份主文件中。
    delta_path: baostock_5min_raw/sh_2026_delta_20260515.parquet
    """
    if not os.path.exists(delta_path):
        logger.warning(f"文件不存在: {delta_path}")
        return

    filename = os.path.basename(delta_path)
    try:
        parts = filename.replace('.parquet', '').split('_delta_')
        market_year = parts[0]
        market = market_year.split('_')[0]
        year = int(market_year.split('_')[1])
    except (IndexError, ValueError) as e:
        logger.error(f"无法解析文件名 {filename}: {e}")
        return

    year_file = os.path.join(output_dir, f"{market}_{year}.parquet")

    logger.info(f"合并 {filename} → {market}_{year}.parquet")

    try:
        df = pd.read_parquet(delta_path)
    except Exception as e:
        logger.error(f"读取 delta 文件失败: {e}")
        return

    if df.empty:
        logger.info("delta 文件为空，跳过")
        if delete_after:
            os.remove(delta_path)
            logger.info(f"已删除空文件: {delta_path}")
        return

    safe_append_parquet(df, year_file)

    logger.info(f"已合并 {len(df)} 行到 {market}_{year}.parquet")

    if delete_after:
        os.remove(delta_path)
        logger.info(f"已删除: {delta_path}")


def merge_all_deltas(output_dir: str = OUTPUT_BASE_DIR, year: Optional[int] = None,
                     delete_after: bool = False):
    """批量合并所有 delta 文件到对应年份主文件。可指定年份。"""
    pattern = f"*_delta_*.parquet"
    if year is not None:
        pattern = f"*_{year}_delta_*.parquet"

    delta_files = sorted(glob(os.path.join(output_dir, pattern)))

    if not delta_files:
        logger.info(f"未找到 delta 文件 (pattern: {pattern})")
        return

    logger.info(f"找到 {len(delta_files)} 个 delta 文件")

    for delta_path in delta_files:
        merge_delta_file(delta_path, output_dir, delete_after)


# ================== CLI ==================

def main():
    parser = argparse.ArgumentParser(
        description="通达信 5分钟数据转换与合并工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tdx_convert.py --date 20260515           # 转换 TDX 数据
  python tdx_convert.py --date 2026-05-15         # 同上 (带分隔符)
  python tdx_convert.py --merge                   # 合并所有 delta 到年份文件
  python tdx_convert.py --merge --year 2026       # 只合并 2026 年的 delta
  python tdx_convert.py --merge --year 2026 --delete  # 合并后删除 delta
  python tdx_convert.py --tdxdir "D:\\gjzq\\gjty" --date 20260515
        """
    )
    parser.add_argument("--date", type=str, default=None, help="要转换的日期 (YYYYMMDD 或 YYYY-MM-DD)")
    parser.add_argument("--tdxdir", type=str, default=TDX_DIR, help=f"通达信安装目录 (默认: {TDX_DIR})")
    parser.add_argument("--output", type=str, default=OUTPUT_BASE_DIR, help=f"输出目录 (默认: {OUTPUT_BASE_DIR})")
    parser.add_argument("--merge", action="store_true", help="合并 delta 文件到年份主文件")
    parser.add_argument("--year", type=int, default=None, help="合并时限定年份")
    parser.add_argument("--delete", action="store_true", help="合并后删除 delta 文件")

    args = parser.parse_args()

    if args.merge:
        merge_all_deltas(args.output, args.year, args.delete)
    elif args.date:
        process_date(args.date, args.tdxdir, args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
