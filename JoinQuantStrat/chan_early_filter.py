# -*- coding: utf-8 -*-
"""
缠论早期过滤器 - 聚宽研究环境自包含版本

使用前只需:
  1. 上传本文件到聚宽研究环境
  2. 上传 tomorrow_candiate_list.txt (每行一只股票代码, #开头为注释)
  3. 在聚宽研究笔记本中运行本文件代码

内部包含:
  - TopBotType, ZouShi_Type, Chan_Type 枚举定义
  - analyze_MA_zoushi_by_stock 及其全部依赖函数
  - filter_chan_early 过滤函数
  - 研究调用入口
"""
from __future__ import print_function
from enum import Enum
import numpy as np
import talib
from jqdata import *
from numpy.lib.recfunctions import append_fields


# ============================================================
# 枚举定义 (来自 biaoLiStatus.py & chan_common_include.py)
# ============================================================

class TopBotType(Enum):
    noTopBot = 0
    bot2top = 0.5
    top = 1
    top2bot = -0.5
    bot = -1


class ZouShi_Type(Enum):
    INVALID = -2
    Qu_Shi_Down = -1
    Pan_Zheng = 0
    Qu_Shi_Up = 1
    Pan_Zheng_Composite = 2


class Chan_Type(Enum):
    INVALID = 0
    I = 1
    II = 2
    III = 3
    III_weak = 4
    II_weak = 5
    III_strong = 6
    I_weak = 7
    PANBEI = 8
    BEICHI = 9
    INVIGORATE = 10


# ============================================================
# 常量及核心分析函数 (来自 chan_kbar_filter.py)
# ============================================================

LONG_MA_NUM = 10
SHORT_MA_NUM = 5


def direction_match_zhongshu_head(direction, zhongshu):
    return ((direction == TopBotType.top2bot and zhongshu[0] > 0)
            or
            (direction == TopBotType.bot2top and zhongshu[0] < 0))


def check_direction_match_zhongshu_cross(direction, zhongshu, allow_ext=False):
    return direction_match_zhongshu_head(direction, zhongshu) \
           and (len(zhongshu) == 2 or (allow_ext and len(zhongshu) > 2))


def zhongshu_qushi_qualified(stock_high, direction, zhongshu):
    if len(zhongshu[0]) > 2:
        if direction == TopBotType.top2bot and zhongshu[0][-2] > 0:
            zhongshu[0] = zhongshu[0][-2:]
        elif direction == TopBotType.bot2top and zhongshu[0][-2] < 0:
            zhongshu[0] = zhongshu[0][-2:]

    first_idx = 0
    while first_idx < len(zhongshu) - 1:
        first_zs = zhongshu[first_idx]
        second_idx = first_idx + 1
        while second_idx < len(zhongshu):
            second_zs = zhongshu[second_idx]
            if check_direction_match_zhongshu_cross(direction, first_zs) \
               and check_direction_match_zhongshu_cross(direction, second_zs):
                first_zs_range = [
                    (stock_high['ma_long'][first_zs[0]] + stock_high['ma_long'][first_zs[0] + 1]) / 2,
                    (stock_high['ma_long'][-first_zs[1]] + stock_high['ma_long'][-first_zs[1] + 1]) / 2]
                second_zs_range = [
                    (stock_high['ma_long'][second_zs[0]] + stock_high['ma_long'][second_zs[0] + 1]) / 2,
                    (stock_high['ma_long'][-second_zs[1]] + stock_high['ma_long'][-second_zs[1] + 1]) / 2]
                if not (min(first_zs_range) > max(second_zs_range) or max(first_zs_range) < min(second_zs_range)):
                    return False
            elif check_direction_match_zhongshu_cross(direction, first_zs) \
                 and check_direction_match_zhongshu_cross(direction, second_zs):
                first_zs_range = [
                    (stock_high['ma_long'][-first_zs[0]] + stock_high['ma_long'][-first_zs[0] + 1]) / 2,
                    (stock_high['ma_long'][first_zs[1]] + stock_high['ma_long'][first_zs[1] + 1]) / 2]
                second_zs_range = [
                    (stock_high['ma_long'][-second_zs[0]] + stock_high['ma_long'][-second_zs[0] + 1]) / 2,
                    (stock_high['ma_long'][second_zs[1]] + stock_high['ma_long'][second_zs[1] + 1]) / 2]
                if not (min(first_zs_range) > max(second_zs_range) or max(first_zs_range) < min(second_zs_range)):
                    return False
            else:
                return False
            second_idx += 1
        first_idx += 1
    return True


def analyze_MA_form_ZhongShu(stock_high, start_idx, end_idx):
    s_idx = abs(start_idx)
    e_idx = abs(end_idx)
    first_cross_price = (stock_high['ma_long'][s_idx] + stock_high['ma_long'][s_idx + 1]) / 2
    second_cross_price = (stock_high['ma_long'][e_idx] + stock_high['ma_long'][e_idx + 1]) / 2
    i = s_idx + 1
    while i <= e_idx:
        if stock_high[i]['high'] > max(first_cross_price, second_cross_price) \
           and stock_high[i]['low'] < min(first_cross_price, second_cross_price):
            return True
        i = i + 1
    return False


def analyze_MA_exhaustion_by_direction(direction, zoushi_result, first, second, debug=False):
    if debug:
        print(first)
        print(second)

    fst_max_idx = np.where(first['high'] == max(first['high']))[0][0]
    fst_min_idx = np.where(first['low'] == min(first['low']))[0][-1]
    snd_max_idx = np.where(second['high'] == max(second['high']))[0][0]
    snd_min_idx = np.where(second['low'] == min(second['low']))[0][-1]

    tail_direction_match = False

    if int(fst_min_idx) == int(fst_max_idx) or int(snd_min_idx) == int(snd_max_idx):
        return False, tail_direction_match

    if (direction == TopBotType.top2bot and snd_min_idx > snd_max_idx) \
       or (direction == TopBotType.bot2top and snd_min_idx < snd_max_idx):
        tail_direction_match = True

    if zoushi_result == ZouShi_Type.Qu_Shi_Down:
        first_slope = (max(first['high']) - min(first['low'])) / (fst_min_idx - fst_max_idx)
        second_slope = (max(second['high']) - min(second['low'])) / (snd_min_idx - snd_max_idx)
        return abs(second_slope) < abs(first_slope), tail_direction_match
    elif zoushi_result == ZouShi_Type.Qu_Shi_Up:
        first = first[int(first['low'].argmin()):]
        second = second[int(second['low'].argmin()):]
        first_slope = (max(first['high']) - min(first['low'])) / (fst_max_idx - fst_min_idx)
        second_slope = (max(second['high']) - min(second['low'])) / (snd_max_idx - snd_min_idx)
        return abs(second_slope) < abs(first_slope), tail_direction_match
    elif zoushi_result == ZouShi_Type.Pan_Zheng:
        first_slope = (max(first['high']) - min(first['low'])) / (fst_min_idx - fst_max_idx)
        second_slope = (max(second['high']) - min(second['low'])) / (snd_min_idx - snd_max_idx)
        return abs(second_slope) < abs(first_slope), tail_direction_match
    elif zoushi_result == ZouShi_Type.Pan_Zheng_Composite:
        first_slope = (max(first['high']) - min(first['low'])) / (fst_min_idx - fst_max_idx)
        second_slope = (max(second['high']) - min(second['low'])) / (snd_min_idx - snd_max_idx)
        return abs(second_slope) < abs(first_slope), tail_direction_match
    else:
        return False, tail_direction_match


class KBar(object):
    """缠论K线分析 (仅包含 analyze_MA_zoushi 链路所需的类方法)"""

    @classmethod
    def analyze_kbar_MA_zoushi(cls, stock_high):
        ma_diff = stock_high['ma_short'] - stock_high['ma_long']
        ma_cross = []
        for i in range(len(ma_diff) - 1):
            if ma_diff[i] < 0 and ma_diff[i + 1] > 0:
                ma_cross.append(i)
            elif ma_diff[i] > 0 and ma_diff[i + 1] < 0:
                ma_cross.append(-i)

        zhongshu = []
        current_zs = []
        i = 0
        while i < len(ma_cross) - 1:
            current_idx = i + 1
            while current_idx < len(ma_cross):
                if current_zs:
                    if analyze_MA_form_ZhongShu(stock_high, ma_cross[i], ma_cross[current_idx]):
                        current_zs.append(ma_cross[current_idx])
                        current_idx = current_idx + 1
                    else:
                        break
                else:
                    if abs(ma_cross[current_idx]) - abs(ma_cross[i]) >= 3 \
                       and analyze_MA_form_ZhongShu(stock_high, ma_cross[i], ma_cross[current_idx]):
                        current_zs.append(ma_cross[i])
                        current_zs.append(ma_cross[current_idx])
                        current_idx = current_idx + 1
                    else:
                        break

            if current_zs:
                zhongshu.append(current_zs)
                current_zs = []
            i = current_idx
        return zhongshu, ma_cross

    @classmethod
    def analyze_kbar_MA_zoushi_exhaustion(cls, stock_high, zoushi_types, direction, zhongshu, all_cross, debug=False):
        zoushi_result = ZouShi_Type.INVALID
        exhaustion_result = Chan_Type.INVALID

        if len(zhongshu) > 1:
            if direction == TopBotType.top2bot and zhongshu_qushi_qualified(stock_high, direction, zhongshu):
                zoushi_result = ZouShi_Type.Qu_Shi_Down
            elif direction == TopBotType.bot2top and zhongshu_qushi_qualified(stock_high, direction, zhongshu):
                zoushi_result = ZouShi_Type.Qu_Shi_Up
            else:
                zoushi_result = ZouShi_Type.Pan_Zheng_Composite
        elif len(zhongshu) > 0 and check_direction_match_zhongshu_cross(direction, zhongshu[-1], allow_ext=True):
            zoushi_result = ZouShi_Type.Pan_Zheng
        else:
            return zoushi_result, exhaustion_result

        if zoushi_result not in zoushi_types:
            return zoushi_result, exhaustion_result

        if len(zhongshu) == 1:
            zs = zhongshu[0]
            first_part = stock_high[:abs(zs[0]) + 1]
            second_part = stock_high[abs(zs[-1]) + 1:]
            exhaustion_check, direction_check = analyze_MA_exhaustion_by_direction(
                direction, zoushi_result, first_part, second_part, debug)
            exhaustion_result = Chan_Type.INVALID if not direction_check \
                else Chan_Type.PANBEI if exhaustion_check else Chan_Type.INVIGORATE
        else:
            zs1 = zhongshu[-2]
            zs2 = zhongshu[-1]
            first_part = stock_high[abs(zs1[-1]) + 1:abs(zs2[0]) + 1]
            second_part = stock_high[abs(zs2[-1]) + 1:]
            exhaustion_check, direction_check = analyze_MA_exhaustion_by_direction(
                direction, zoushi_result, first_part, second_part, debug)
            exhaustion_result = Chan_Type.INVALID if not direction_check \
                else Chan_Type.PANBEI if exhaustion_check else Chan_Type.INVIGORATE

        return zoushi_result, exhaustion_result


def analyze_MA_zoushi_by_stock(stock, period, count, end_dt, df, zoushi_types, direction, debug=False):
    stock_high = get_bars(stock,
                           count=count + LONG_MA_NUM,
                           end_dt=end_dt,
                           unit=period,
                           fields=['date', 'open', 'high', 'low', 'close'],
                           df=df,
                           include_now=True)

    ma_long = talib.MA(stock_high['close'], LONG_MA_NUM)
    ma_short = talib.MA(stock_high['close'], SHORT_MA_NUM)
    ma_long[np.isnan(ma_long)] = 0
    ma_short[np.isnan(ma_short)] = 0
    stock_high = append_fields(stock_high,
                                ['ma_long', 'ma_short'],
                                [ma_long, ma_short],
                                [float, float],
                                usemask=False)
    stock_high = stock_high[LONG_MA_NUM:]

    zhongshu_results, all_cross = KBar.analyze_kbar_MA_zoushi(stock_high)

    if debug:
        print(zhongshu_results)

    return KBar.analyze_kbar_MA_zoushi_exhaustion(stock_high,
                                                  zoushi_types=zoushi_types,
                                                  direction=direction,
                                                  zhongshu=zhongshu_results,
                                                  all_cross=all_cross,
                                                  debug=debug)


# ============================================================
# 缠论早期过滤器 (来自 Utility/chan_early_filter.py)
# ============================================================

def _get_count(period):
    if period == '1d':
        return 180
    elif period == '120m':
        return 237
    elif period == '90m':
        return 356
    elif period == '60m':
        return 712
    elif period == '30m':
        return 1200
    elif period == '15m':
        return 1500
    elif period == '5m':
        return 1800
    elif period == '1m':
        return 1800
    else:
        return 1800


def filter_chan_early(stock_list, check_level_up=None, check_level_down=None):
    """
    缠论早期过滤: 任一 UP_EARLY 或 DOWN_EARLY 条件触发即移除.

    UP_EARLY:  任一级别呈上升走势+背驰 → 移除
    DOWN_EARLY: 所有级别呈下降/盘整+发力 → 移除

    :param check_level_up:   上升检查的级别列表, 默认 ["1m", "5m", "30m", "60m", "1d"]
    :param check_level_down: 下降检查的级别列表, 默认 ["1d"]
    """
    expected_zoushi_up = [ZouShi_Type.Qu_Shi_Up, ZouShi_Type.Pan_Zheng, ZouShi_Type.Pan_Zheng_Composite]
    expected_exhaustion_up = [Chan_Type.BEICHI, Chan_Type.PANBEI]
    if check_level_up is None:
        check_level_up = ["1m", "5m", "30m", "60m", "1d"]

    expected_zoushi_down = [ZouShi_Type.Qu_Shi_Down, ZouShi_Type.Pan_Zheng]
    expected_exhaustion_down = [Chan_Type.INVIGORATE]
    if check_level_down is None:
        check_level_down = ["1d"]

    stock_to_remove = set()
    remove_reasons = {}

    # ==================== UP_EARLY ====================
    print("--- UP_EARLY (levels: {0}) ---".format(check_level_up))
    for stock in stock_list:
        for level in check_level_up:
            try:
                stock_data = get_bars(stock,
                                       count=_get_count(level),
                                       end_dt=None,
                                       unit=level,
                                       fields=['date', 'high', 'low'],
                                       df=False,
                                       include_now=True)
            except Exception as e:
                print("  [UP_EARLY 跳过] {0}: {1} 数据失败: {2}".format(stock, level, e))
                continue

            min_loc = int(np.where(stock_data['low'] == min(stock_data['low']))[0][-1])
            bot_count = len(stock_data['low']) - min_loc
            if bot_count <= 0:
                continue

            rz, rex = analyze_MA_zoushi_by_stock(
                stock=stock, period=level, count=bot_count,
                end_dt=None, df=False,
                zoushi_types=expected_zoushi_up,
                direction=TopBotType.bot2top)

            if rz in expected_zoushi_up and rex in expected_exhaustion_up:
                reason = "UP_EARLY: {0}级 zoushi={1} exhaustion={2}".format(level, rz, rex)
                remove_reasons[stock] = reason
                stock_to_remove.add(stock)
                print("  [移除] {0}: {1}".format(stock, reason))
                break
            else:
                print("  [保留] {0}: {1}级 zoushi={2} exhaustion={3}".format(stock, level, rz, rex))

    # ==================== DOWN_EARLY ====================
    print("--- DOWN_EARLY (levels: {0}) ---".format(check_level_down))
    for stock in stock_list:
        ok = True
        for level in check_level_down:
            try:
                stock_data = get_bars(stock,
                                       count=_get_count(level),
                                       end_dt=None,
                                       unit=level,
                                       fields=['date', 'high', 'low'],
                                       df=False,
                                       include_now=True)
            except Exception as e:
                print("  [DOWN_EARLY 跳过] {0}: {1} 数据失败: {2}".format(stock, level, e))
                ok = False
                break

            max_loc = int(np.where(stock_data['high'] == max(stock_data['high']))[0][-1])
            top_count = len(stock_data['high']) - max_loc
            if top_count > 0:
                rz, rex = analyze_MA_zoushi_by_stock(
                    stock=stock, period=level, count=top_count,
                    end_dt=None, df=False,
                    zoushi_types=expected_zoushi_down,
                    direction=TopBotType.top2bot)
                if rz in expected_zoushi_down and rex in expected_exhaustion_down:
                    pass
                else:
                    ok = False
                    print("  [保留] {0}: {1}级 zoushi={2} exhaustion={3}".format(stock, level, rz, rex))
                    break
            else:
                ok = False
                break

        if ok:
            reason = "DOWN_EARLY: {0}级 zoushi下降/盘整+发力".format(", ".join(check_level_down))
            if stock in remove_reasons:
                remove_reasons[stock] += "; " + reason
            else:
                remove_reasons[stock] = reason
            stock_to_remove.add(stock)
            print("  [移除] {0}: {1}".format(stock, reason))

    # ==================== 汇总 ====================
    print("=" * 60)
    print("输入 {0} 只, 移除 {1} 只, 剩余 {2} 只".format(
        len(stock_list), len(stock_to_remove), len(stock_list) - len(stock_to_remove)))
    if remove_reasons:
        print("移除明细:")
        for stock, reason in sorted(remove_reasons.items()):
            print("  {0}: {1}".format(stock, reason))
    print("=" * 60)
    return [s for s in stock_list if s not in stock_to_remove]


# ============================================================
# 研究调用入口 (仅在直接执行时运行)
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("缠论早期过滤器 - 研究环境测试")
    print("=" * 60)

    # 1. 读取候选股票列表
    filename = 'tomorrow_candidate_list.txt'
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        candidate_list = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                candidate_list.append(line)
        print("\n从 {0} 读取到 {1} 只候选股票".format(filename, len(candidate_list)))
    except Exception as e:
        print("\n读取 {0} 失败: {1}".format(filename, e))
        candidate_list = ['000001.XSHE', '000002.XSHE', '600000.XSHG']
        print("使用默认测试列表: {0}".format(candidate_list))

    # 2. 执行过滤
    print()
    filtered = filter_chan_early(candidate_list)

    # 3. 输出最终结果
    print()
    print("=" * 40)
    print("最终结果: {0} 只通过".format(len(filtered)))
    print("=" * 40)
    for stock in filtered:
        print(stock)


