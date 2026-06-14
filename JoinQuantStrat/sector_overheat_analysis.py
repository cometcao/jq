# ============================================================
# 申万二级板块过热监控（忠实原始逻辑：单日成交额占比+单日换手率+周度融资增速+单日融资买入占比）
# ============================================================

from jqdata import *
import pandas as pd
import numpy as np
from datetime import timedelta
from jqdata import *
import os
from datetime import date


print("=" * 70)
print("【板块过热监控（忠实原始逻辑）】")
print("=" * 70)

# ==================== 2. 参数配置 ====================
data_end = None          # None = 自动获取最近交易日
weeks_back = 4           # 融资余额增速回看周数
verbose = False
min_stocks = 3
candidate_file = "tomorrow_candidate_list.txt"

# 拥挤阈值（原始表格）
CROWDED_RATIO = 35.0      # 成交额占比 >35% 拥挤预警
OVERHEAT_TURNOVER = 10.0  # 换手率 >10% 短炒过热
LEVERAGE_RATIO = 10.0     # 融资买入额占比 >10% 杠杆过热

# 自动获取最近交易日
if data_end is None:
    today_date = date.today()
    trade_days = get_trade_days(start_date=today_date, end_date=today_date)
    if len(trade_days) > 0:
        data_end = trade_days[0].strftime('%Y-%m-%d')
    else:
        trade_days = get_trade_days(end_date=today_date, count=1)
        data_end = trade_days[0].strftime('%Y-%m-%d')
    print(f"✅ 自动获取最近交易日：{data_end}")
else:
    print(f"✅ 使用手动指定交易日：{data_end}")

# ==================== 辅助函数 ====================
def get_total_market_amount(date):
    """全市场单日成交额（上证+深证）"""
    try:
        sh = get_price('000001.XSHG', count=1, end_date=date, frequency='daily', fields=['money'])
        sz = get_price('399001.XSHE', count=1, end_date=date, frequency='daily', fields=['money'])
        sh_amount = sh['money'][0] if sh is not None and len(sh) > 0 else 0
        sz_amount = sz['money'][0] if sz is not None and len(sz) > 0 else 0
        return sh_amount + sz_amount
    except:
        return 0

def get_sector_margin_balance(stocks, date):
    """板块融资余额总和"""
    total = 0.0
    for s in stocks:
        try:
            margin = get_mtss(s, date)
            if margin and isinstance(margin, dict):
                v = margin.get('fin_value')
                if v:
                    total += float(v)
        except:
            continue
    return total

def get_sector_fin_buy_amount(stocks, date):
    """板块融资买入额总和"""
    total = 0.0
    for s in stocks:
        try:
            margin = get_mtss(s, date)
            if margin and isinstance(margin, dict):
                v = margin.get('fin_buy_value')
                if v:
                    total += float(v)
        except:
            continue
    return total

def get_sector_amount_one_day(stocks, date):
    """板块单日成交额总和"""
    total = 0.0
    for s in stocks:
        try:
            df = get_price(s, count=1, end_date=date, frequency='daily', fields=['money'], skip_paused=True)
            if df is not None and len(df) > 0:
                total += df['money'].iloc[0]
        except:
            continue
    return total

def get_sector_avg_turnover(stocks, date):
    """板块平均换手率（最新日）"""
    if not stocks:
        return 0.0
    try:
        q = query(valuation.code, valuation.turnover_ratio).filter(valuation.code.in_(stocks))
        df = get_fundamentals(q, date=date)
        if df is not None and not df.empty:
            return df['turnover_ratio'].mean()
    except:
        pass
    return 0.0

def get_industry_info(industry_code, date):
    """获取申万二级行业成分股和名称"""
    try:
        stocks = get_industry_stocks(industry_code, date=date)
        if stocks is None or len(stocks) < min_stocks:
            return None, None
        all_ind = get_industries(name='sw_l1')
        name = all_ind.loc[industry_code, 'name'] if industry_code in all_ind.index else industry_code
        return stocks, name
    except:
        return None, None

def get_stock_industry(stock_code, date):
    """获取单只股票的申万二级行业"""
    try:
        result = get_industry(security=[stock_code], date=date)
        if result and stock_code in result:
            ind = result[stock_code]
            if ind and 'sw_l1' in ind and ind['sw_l1']:
                code = ind['sw_l1'].get('industry_code')
                name = ind['sw_l1'].get('industry_name')
                return code, name
    except:
        pass
    return None, None

def normalize_stock_code(code_str):
    code_str = code_str.strip().upper()
    if '.XSHG' in code_str or '.XSHE' in code_str:
        return code_str
    if code_str.startswith('6'):
        return code_str + '.XSHG'
    else:
        return code_str + '.XSHE'

# ==================== 读取候选股 ====================
print("\n⚙ 读取候选股票文件...")
if not os.path.exists(candidate_file):
    print(f"❌ 文件 {candidate_file} 不存在")
    exit()
with open(candidate_file, 'r') as f:
    raw_codes = [line.strip() for line in f if line.strip()]
candidate_stocks = [normalize_stock_code(c) for c in raw_codes]
print(f"✅ 共读取 {len(candidate_stocks)} 只")

# 识别行业
print("\n⚙ 识别股票所属行业...")
stock_to_industry = {}
excluded = []
for stock in candidate_stocks:
    code, name = get_stock_industry(stock, data_end)
    if code:
        stock_to_industry[stock] = (code, name)
    else:
        excluded.append({'股票代码': stock, '原因': '无法识别申万二级行业'})
print(f"✅ 识别 {len(stock_to_industry)} 只，剔除 {len(excluded)} 只")

# 收集涉及行业
involved_codes = set(code for code, _ in stock_to_industry.values())
print(f"涉及行业数：{len(involved_codes)}")

# 获取有效行业成分股
print("\n⚙ 获取行业成分股...")
industry_stocks = {}
industry_names = {}
valid_codes = set()
for code in involved_codes:
    stocks, name = get_industry_info(code, data_end)
    if stocks:
        industry_stocks[code] = stocks
        industry_names[code] = name
        valid_codes.add(code)

# 剔除行业无效的股票
final_stocks = {}
for stock, (code, name) in stock_to_industry.items():
    if code in valid_codes:
        final_stocks[stock] = (code, name)
    else:
        excluded.append({'股票代码': stock, '原因': f'行业 {name} 成分股不足{min_stocks}只'})
print(f"✅ 有效行业数：{len(industry_stocks)}，最终有效股票：{len(final_stocks)} 只")

if not industry_stocks:
    print("❌ 无有效行业")
    exit()

# 全市场成交额（单日）
market_amount = get_total_market_amount(data_end)
print(f"\n全市场成交额（{data_end}）：{market_amount/1e8:.2f} 亿")

# 计算各行业指标
print("\n⚙ 计算行业过热指标...")
industry_status = {}  # {code: {name, metrics, overheat_flags}}
for code, stocks in industry_stocks.items():
    name = industry_names[code]
    if verbose:
        print(f"处理 {name}...")

    # 单日成交额占比
    sector_amount = get_sector_amount_one_day(stocks, data_end)
    ratio = (sector_amount / market_amount * 100) if market_amount else 0

    # 平均换手率
    turnover = get_sector_avg_turnover(stocks, data_end)

    # 融资余额周度增速
    end_margin = get_sector_margin_balance(stocks, data_end)
    start_margin_date = (pd.to_datetime(data_end) - timedelta(weeks=weeks_back)).strftime('%Y-%m-%d')
    start_margin = get_sector_margin_balance(stocks, start_margin_date)
    margin_growth = ((end_margin - start_margin) / start_margin * 100) if (start_margin and start_margin > 0) else None

    # 融资买入额占比（单日）
    fin_buy = get_sector_fin_buy_amount(stocks, data_end)
    fin_ratio = (fin_buy / market_amount * 100) if market_amount else 0

    # 判断过热标志（按原始三个维度）
    flags = []
    if ratio > CROWDED_RATIO:
        flags.append("拥挤预警")
    if turnover > OVERHEAT_TURNOVER:
        flags.append("短炒过热")
    if fin_ratio > LEVERAGE_RATIO:
        flags.append("杠杆过热")
    if not flags:
        flags.append("正常")

    industry_status[code] = {
        'name': name,
        'flags': flags,
        'metrics': {
            '成交额占比(%)': round(ratio, 2),
            '换手率(%)': round(turnover, 2),
            '融资余额增速(%)': round(margin_growth, 2) if margin_growth else None,
            '融资买入占比(%)': round(fin_ratio, 2)
        }
    }

# 输出过热股票（按股票列出其所属板块的状态）
print("\n" + "=" * 100)
print("【候选股票板块拥挤提醒】")
print("=" * 100)

crowded_results = []
for stock, (code, name) in final_stocks.items():
    if code in industry_status:
        status_info = industry_status[code]
        flags = status_info['flags']
        if "正常" not in flags:  # 只要有任何过热标志就输出
            crowded_results.append({
                '股票代码': stock,
                '所属行业': name,
                '过热状态': ', '.join(flags)
            })

if crowded_results:
    df_crowded = pd.DataFrame(crowded_results)
    print(df_crowded.to_string(index=False))
else:
    print("✅ 所有候选股票所属板块均正常，无拥挤风险。")

# 输出被剔除股票
print("\n" + "=" * 100)
print("【被剔除股票名单】（未参与过热判断）")
print("=" * 100)
if excluded:
    df_excluded = pd.DataFrame(excluded)
    print(df_excluded.to_string(index=False))
else:
    print("✅ 没有股票被剔除。")

print("\n✅ 分析完成！")