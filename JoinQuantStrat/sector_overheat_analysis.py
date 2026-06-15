# ============================================================
# 申万二级板块过热监控（成交额占比动态阈值，20日窗口，99%置信度）
# 用途：模型选股前的避雷筛选——排除板块拥挤的股票
# ============================================================

from jqdata import *
import pandas as pd
import numpy as np
from datetime import timedelta
from jqdata import *
import os
from datetime import date


print("=" * 70)
print("【申万二级板块过热监控（成交额占比动态阈值）】")
print("=" * 70)

# ==================== 2. 参数配置 ====================
data_end = None               # None = 自动取最近交易日
lookback_days = 20            # 用于计算动态阈值的历史窗口（交易日）
z_score_threshold = 1.96      # 均值+1.96倍标准差触发拥挤预警（对应95%置信度）
weeks_back = 4                # 融资余额增速回看周数
verbose = False
min_stocks = 3
candidate_file = "tomorrow_candidate_list.txt"

# 固定阈值（其他指标）
OVERHEAT_TURNOVER = 10.0      # 换手率 >10%
LEVERAGE_RATIO = 10.0         # 融资买入占比 >10%

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

# 计算历史起始日期（多取一些交易日保证有足够数据）
def get_start_date(end_date, days):
    trade_days_list = get_trade_days(end_date=end_date, count=days + 5)  # 多取5天安全边际
    if len(trade_days_list) > 0:
        return trade_days_list[0].strftime('%Y-%m-%d')
    else:
        return end_date

history_start = get_start_date(data_end, lookback_days)
print(f"📅 历史数据区间：{history_start} → {data_end}（至少{lookback_days}个交易日用于滚动窗口）")

# ==================== 辅助函数 ====================
def get_total_market_amount(date):
    try:
        sh = get_price('000001.XSHG', count=1, end_date=date, frequency='daily', fields=['money'])
        sz = get_price('399001.XSHE', count=1, end_date=date, frequency='daily', fields=['money'])
        sh_amount = sh['money'][0] if sh is not None and len(sh) > 0 else 0
        sz_amount = sz['money'][0] if sz is not None and len(sz) > 0 else 0
        return sh_amount + sz_amount
    except:
        return 0

def get_sector_margin_balance(stocks, date):
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
    try:
        stocks = get_industry_stocks(industry_code, date=date)
        if stocks is None or len(stocks) < min_stocks:
            return None, None
        all_ind = get_industries(name='sw_l2')
        name = all_ind.loc[industry_code, 'name'] if industry_code in all_ind.index else industry_code
        return stocks, name
    except:
        return None, None

def get_stock_industry(stock_code, date):
    try:
        result = get_industry(security=[stock_code], date=date)
        if result and stock_code in result:
            ind = result[stock_code]
            if ind and 'sw_l2' in ind and ind['sw_l2']:
                code = ind['sw_l2'].get('industry_code')
                name = ind['sw_l2'].get('industry_name')
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

print("\n⚙ 识别股票所属申万二级行业...")
stock_to_industry = {}
excluded = []
for stock in candidate_stocks:
    code, name = get_stock_industry(stock, data_end)
    if code:
        stock_to_industry[stock] = (code, name)
    else:
        excluded.append({'股票代码': stock, '原因': '无法识别申万二级行业'})
print(f"✅ 识别 {len(stock_to_industry)} 只，剔除 {len(excluded)} 只")

involved_codes = set(code for code, _ in stock_to_industry.values())
print(f"涉及行业数：{len(involved_codes)}")

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

# ==================== 构建全市场成交额历史序列 ====================
print(f"\n⚙ 构建全市场成交额历史序列（{history_start} → {data_end}）...")
trade_days = get_trade_days(start_date=history_start, end_date=data_end)
market_daily = {}
for td in trade_days:
    td_str = td.strftime('%Y-%m-%d')
    market_daily[td_str] = get_total_market_amount(td_str)
print(f"✅ 共 {len(market_daily)} 个交易日")

# ==================== 对每个行业计算动态阈值和当前占比 ====================
print("\n⚙ 计算各行业成交额占比历史序列及动态阈值...")

industry_status = {}

for code, stocks in industry_stocks.items():
    name = industry_names[code]
    if verbose:
        print(f"处理 {name}...")

    # 获取该行业在历史区间内每日的成交额（使用当前成分股回测历史）
    sector_daily = {}
    for td_str in market_daily.keys():
        total = 0.0
        for s in stocks:
            try:
                df = get_price(s, count=1, end_date=td_str, frequency='daily', fields=['money'], skip_paused=True)
                if df is not None and len(df) > 0:
                    total += df['money'].iloc[0]
            except:
                continue
        sector_daily[td_str] = total

    # 计算每日成交额占比
    ratio_list = []
    for td_str in market_daily.keys():
        market = market_daily.get(td_str, 0)
        sector = sector_daily.get(td_str, 0)
        if market > 0:
            ratio_list.append(sector / market * 100)
        else:
            ratio_list.append(0.0)

    # 转换为Series
    s = pd.Series(ratio_list, index=market_daily.keys())
    
    # 滚动计算均值+2.58倍标准差（窗口为 lookback_days）
    rolling_mean = s.rolling(lookback_days).mean()
    rolling_std = s.rolling(lookback_days).std()
    rolling_threshold = rolling_mean + z_score_threshold * rolling_std
    
    # 当前占比及当日阈值
    current_ratio = s.iloc[-1] if len(s) > 0 else 0.0
    current_threshold = rolling_threshold.iloc[-1] if len(rolling_threshold) > 0 else np.inf
    
    # 判断成交额占比是否拥挤
    crowded_flag = (current_ratio > current_threshold)
    
    # 其他指标（固定阈值）
    turnover = get_sector_avg_turnover(stocks, data_end)
    end_margin = get_sector_margin_balance(stocks, data_end)
    start_margin_date = (pd.to_datetime(data_end) - timedelta(weeks=weeks_back)).strftime('%Y-%m-%d')
    start_margin = get_sector_margin_balance(stocks, start_margin_date)
    margin_growth = ((end_margin - start_margin) / start_margin * 100) if (start_margin and start_margin > 0) else None
    fin_buy = get_sector_fin_buy_amount(stocks, data_end)
    market_today = get_total_market_amount(data_end)
    fin_ratio = (fin_buy / market_today * 100) if market_today > 0 else 0

    flags = []
    if crowded_flag:
        flags.append("拥挤预警(动态)")
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
            '成交额占比(%)': round(current_ratio, 2),
            '动态阈值(20日均值+2.58σ)': round(current_threshold, 2),
            '换手率(%)': round(turnover, 2),
            '融资余额增速(%)': round(margin_growth, 2) if margin_growth else None,
            '融资买入占比(%)': round(fin_ratio, 2)
        }
    }

# ==================== 输出过热股票（避雷列表） ====================
print("\n" + "=" * 100)
print(f"【候选股票板块拥挤提醒】（成交额占比动态阈值：{lookback_days}日均值+{z_score_threshold}倍标准差，对应99%置信度）")
print("=" * 100)

crowded_results = []
for stock, (code, name) in final_stocks.items():
    if code in industry_status:
        flags = industry_status[code]['flags']
        if "正常" not in flags:
            crowded_results.append({
                '股票代码': stock,
                '所属行业': name,
                '过热状态': ', '.join(flags)
            })

if crowded_results:
    df_crowded = pd.DataFrame(crowded_results)
    print("⚠️ 以下股票所属板块存在拥挤风险，建议从候选池中剔除：")
    print(df_crowded.to_string(index=False))
else:
    print("✅ 所有候选股票所属板块均正常，无拥挤风险。")

print("\n" + "=" * 100)
print("【被剔除股票名单】（无法识别行业或行业成分股不足）")
print("=" * 100)
if excluded:
    df_excluded = pd.DataFrame(excluded)
    print(df_excluded.to_string(index=False))
else:
    print("✅ 没有股票被剔除。")

print("\n✅ 分析完成！")