// ChanAnalyzer.cpp - Chan Theory Analyzer Implementation
// Implementation of pen and line segment algorithm from kBar_Chan.py

#include "ChanPlugin.h"
#include <algorithm>
#include <limits>
#include <tuple>

#ifndef CHAN_MIN_BI_SPAN
#define CHAN_MIN_BI_SPAN 3
#endif

// 笔的最小间距 (标准化K线 new_index 之差):
//   3 = 新笔 (默认, 缠师后续放宽: 顶底分型不共用K线即可)
//   4 = 老笔 (原文第62课: 顶和底之间至少有一根K线)
#ifndef CHAN_BI_MIN_SPAN
#define CHAN_BI_MIN_SPAN 3
#endif

// 线段标准化开关: 1 = 输出前把线段端点校正为该段极值 (缠论第78课允许的独立步骤,
// 视觉上更规整); 0 = 纯划分结果 (与原文/Python 原版的划分口径一致)
#ifndef CHAN_STANDARDIZE_XD
#define CHAN_STANDARDIZE_XD 1
#endif

ChanAnalyzer::ChanAnalyzer(bool debug) 
    : is_debug(debug), previous_with_xd_gap(false) {
}

void ChanAnalyzer::setData(const std::vector<KLine>& data) {
    original_data = data;
    standardized.clear();
    marked_bi.clear();
    marked_xd.clear();
    gap_XD.clear();
    previous_skipped_idx.clear();
    previous_with_xd_gap = false;
}

void ChanAnalyzer::analyze() {
    if (original_data.empty()) return;
    
    // Step 1: Detect Gaps
    detectGaps();
    
    // Step 2: Standardization Process
    standardize();
    
    // Step 3: Mark Top/Bottom Patterns
    markTopBot();
    
    // Step 4: Define Pen (笔)
    defineBi();
    
    // Step 5: Define Line Segment (线段)
    defineXD();
}

InclusionType ChanAnalyzer::checkInclusion(const StandardKLine& first, const StandardKLine& second) {
    double first_high = first.high;
    double second_high = second.high;
    double first_low = first.low;
    double second_low = second.low;
    
    if (float_less_equal(first_high, second_high) && float_more_equal(first_low, second_low)) {
        return FIRST_CSECOND;
    } else if (float_more_equal(first_high, second_high) && float_less_equal(first_low, second_low)) {
        return SECOND_CFIRST;
    }
    return NO_INCLUSION;
}

TopBotType ChanAnalyzer::isBullType(const StandardKLine& first, const StandardKLine& second) {
    // 原文第65课: "如果gn>=gn-1, 那么称第n-1、n、n+1根K线是向上的"。
    // 注意: 该条的前提是"第n根与第n-1根不是包含关系"; gn==gn-1 时二者必然构成包含
    // 关系(高点相同、低点不同), 违反前提, 因此等号情形在原文口径下不会出现,
    // 此处用严格小于与原文等价(实测改成 >= 反而使标准化序列与原版一致率 14/20 -> 5/20)。
    return float_less(first.high, second.high) ? BOT2TOP : TOP2BOT;
}

TopBotType ChanAnalyzer::checkTopBot(const StandardKLine& current, 
                                    const StandardKLine& first, 
                                    const StandardKLine& second) {
    if (float_more(first.high, current.high) && float_more(first.high, second.high)) {
        return TOP;
    } else if (float_less(first.low, current.low) && float_less(first.low, second.low)) {
        return BOT;
    }
    return NO_TOPBOT;
}

void ChanAnalyzer::detectGaps() {
    if (original_data.empty()) return;
    
    // 为原始数据添加缺口标记
    for (size_t i = 1; i < original_data.size(); i++) {
        KLine& current = original_data[i];
        const KLine& prev = original_data[i-1];
        
        current.gap = 0;
        current.gap_start = 0;
        current.gap_end = 0;
        
        if (float_more(current.low - prev.high, MIN_PRICE_UNIT)) {
            // 向上缺口
            current.gap = 1;
            current.gap_start = prev.high;
            current.gap_end = current.low;
        } else if (float_less(current.high - prev.low, -MIN_PRICE_UNIT)) {
            // 向下缺口
            current.gap = -1;
            current.gap_start = current.high;
            current.gap_end = prev.low;
        }
    }
}

bool ChanAnalyzer::gapExistsInRange(int start_idx, int end_idx) {
    if (original_data.empty()) return false;
    
    for (const auto& kline : original_data) {
        if (kline.date > start_idx && kline.date <= end_idx) {
            if (kline.gap != 0) return true;
        }
    }
    return false;
}

bool ChanAnalyzer::gapExistsInDateRange(double start_date, double end_date) {
    if (original_data.empty()) return false;
    
    for (const auto& kline : original_data) {
        if (kline.date > start_date && kline.date <= end_date) {
            if (kline.gap != 0) return true;
        }
    }
    return false;
}

int ChanAnalyzer::getNextLoc(int loc, const std::vector<StandardKLine>& working_df) {
    for (size_t i = loc + 1; i < working_df.size(); i++) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            return static_cast<int>(i);
        }
    }
    return static_cast<int>(working_df.size());
}

void ChanAnalyzer::standardize(int initial_state) {
    if (original_data.empty()) return;
    
    // 初始化标准化数组
    standardized.resize(original_data.size());
    for (size_t i = 0; i < original_data.size(); i++) {
        const KLine& kline = original_data[i];
        StandardKLine& std_kline = standardized[i];
        
        std_kline.date = kline.date;
        std_kline.close = kline.close;
        std_kline.high = kline.high;
        std_kline.low = kline.low;
        std_kline.real_loc = static_cast<int>(i);
        std_kline.new_index = 0;
        std_kline.tb = NO_TOPBOT;
        std_kline.chan_price = 0;
        std_kline.original_tb = NO_TOPBOT;
        std_kline.xd_tb = NO_TOPBOT;
        std_kline.merged_away = false;
    }
    
    // 第一步：确保前两根K线没有包含关�?
    if (initial_state == TOP || initial_state == BOT) {
        while (standardized.size() > 2) {
            StandardKLine& first = standardized[0];
            StandardKLine& second = standardized[1];
            
            InclusionType inclusion = checkInclusion(first, second);
            if (inclusion != NO_INCLUSION) {
                if (initial_state == BOT) {
                    first.high = second.high;
                    // low保持不变
                } else if (initial_state == TOP) {
                    first.low = second.low;
                    // high保持不变
                }
                standardized.erase(standardized.begin() + 1);
            } else {
                break;
            }
        }
    } else {
        while (standardized.size() > 2) {
            StandardKLine& first = standardized[0];
            StandardKLine& second = standardized[1];
            
            InclusionType inclusion = checkInclusion(first, second);
            if (inclusion != NO_INCLUSION) {
                standardized.erase(standardized.begin());
            } else {
                break;
            }
        }
    }
    
    if (standardized.size() < 3) {
        // 数据太少，直接返�?
        return;
    }
    
    // 第二步：处理包含关系
    size_t past_idx = 0;
    size_t first_idx = 1;
    size_t second_idx = 2;
    
    while (second_idx < standardized.size()) {
        StandardKLine& past = standardized[past_idx];
        StandardKLine& first = standardized[first_idx];
        StandardKLine& second = standardized[second_idx];
        
        InclusionType inclusion = checkInclusion(first, second);
        if (inclusion != NO_INCLUSION) {
            // Python: 先读取first的trend_type，若未设置则用isBullType判断
            int trend = isBullType(past, first);   // 原文第62课: 按当前K线比较定方向, 去掉方向粘滞
            
            if (inclusion == FIRST_CSECOND) {
                if (trend == BOT2TOP) {
                    second.high = std::max(first.high, second.high);
                    second.low = std::max(first.low, second.low);
                } else {
                    second.high = std::min(first.high, second.high);
                    second.low = std::min(first.low, second.low);
                }
                first.merged_away = true;
                
                
                first_idx = second_idx;
                second_idx++;
            } else {
                if (trend == BOT2TOP) {
                    first.high = std::max(first.high, second.high);
                    first.low = std::max(first.low, second.low);
                } else {
                    first.high = std::min(first.high, second.high);
                    first.low = std::min(first.low, second.low);
                }
                second.merged_away = true;
                
                second_idx++;
            }
        } else {
            // 无包含关�?
            first_idx = second_idx;
            second_idx++;
            past_idx = first_idx - 1;
        }
    }
    
    // 清理标准化K线（移除已被合并的线，使用negative标记�?
    std::vector<StandardKLine> cleaned;
    for (const auto& kline : standardized) {
        // 被合并的K线high和low都被设为负数，这里过滤掉
        if (!kline.merged_away) {
            cleaned.push_back(kline);
        }
    }
    standardized = cleaned;
    
    // 重新编号
    for (size_t i = 0; i < standardized.size(); i++) {
        standardized[i].new_index = static_cast<int>(i);
    }
}

void ChanAnalyzer::markTopBot(int initial_state, bool mark_last_kbar) {
    if (standardized.size() < 7) return;
    
    // 初始化所有tb为NO_TOPBOT
    for (auto& kline : standardized) {
        kline.tb = NO_TOPBOT;
    }
    
    // 处理初始状�?
    if (initial_state == TOP || initial_state == BOT) {
        StandardKLine& first = standardized[0];
        StandardKLine& second = standardized[1];
        
        if ((initial_state == TOP && float_more_equal(first.high, second.high)) ||
            (initial_state == BOT && float_less_equal(first.low, second.low))) {
            first.tb = initial_state;
        }
    }
    
    // 标记顶底分型
    int last_idx = 0;
    for (size_t i = 0; i < standardized.size() - 2; i++) {
        StandardKLine& current = standardized[i];
        StandardKLine& first = standardized[i+1];
        StandardKLine& second = standardized[i+2];
        
        TopBotType type = checkTopBot(current, first, second);
        if (type != NO_TOPBOT) {
            first.tb = type;
            last_idx = static_cast<int>(i + 1);
        }
    }
    
    // 标记第一根K�?
    if (standardized[0].tb != TOP && standardized[0].tb != BOT) {
        int first_loc = getNextLoc(0, standardized);
        if (first_loc < static_cast<int>(standardized.size())) {
            TopBotType first_tb = static_cast<TopBotType>(standardized[first_loc].tb);
            standardized[0].tb = (first_tb == TOP) ? BOT : TOP;
        }
    }
    
    // 标记最后一根K�?
    if (mark_last_kbar && last_idx < static_cast<int>(standardized.size())) {
        TopBotType last_tb = static_cast<TopBotType>(standardized[last_idx].tb);
        standardized.back().tb = (last_tb == TOP) ? BOT : TOP;
    }
}

// 清理前两个顶底分型 (in-place, 匹配Python clean_first_two_tb)
void ChanAnalyzer::cleanFirstTwoTB(std::vector<StandardKLine>& working_df) {
    if (working_df.size() < 3) return;
    
    int first_idx = 0;
    int second_idx = 1;
    int third_idx = 2;
    
    while (third_idx < static_cast<int>(working_df.size())) {
        StandardKLine& first = working_df[first_idx];
        StandardKLine& second = working_df[second_idx];
        StandardKLine& third = working_df[third_idx];
        
        if (first.tb == TOP && second.tb == TOP && float_less(first.high, second.high)) {
            first.tb = NO_TOPBOT;
            first_idx = getNextLoc(first_idx, working_df);
            second_idx = getNextLoc(first_idx, working_df);
            third_idx = getNextLoc(second_idx, working_df);
            continue;
        }
        else if (first.tb == TOP && second.tb == TOP && float_more_equal(first.high, second.high)) {
            second.tb = NO_TOPBOT;
            second_idx = getNextLoc(second_idx, working_df);
            third_idx = getNextLoc(second_idx, working_df);
            continue;
        }
        else if (first.tb == BOT && second.tb == BOT && float_more(first.low, second.low)) {
            first.tb = NO_TOPBOT;
            first_idx = getNextLoc(first_idx, working_df);
            second_idx = getNextLoc(first_idx, working_df);
            third_idx = getNextLoc(second_idx, working_df);
            continue;
        }
        else if (first.tb == BOT && second.tb == BOT && float_less_equal(first.low, second.low)) {
            second.tb = NO_TOPBOT;
            second_idx = getNextLoc(second_idx, working_df);
            third_idx = getNextLoc(second_idx, working_df);
            continue;
        }
        else if (second.new_index - first.new_index < CHAN_BI_MIN_SPAN) {
            if (first.tb == third.tb) {
                if (first.tb == TOP) {
                    if (float_less(first.high, third.high)) {
                        first.tb = NO_TOPBOT;
                        first_idx = getNextLoc(first_idx, working_df);
                        second_idx = getNextLoc(first_idx, working_df);
                        third_idx = getNextLoc(second_idx, working_df);
                        continue;
                    }
                    else {
                        second.tb = NO_TOPBOT;
                        second_idx = getNextLoc(second_idx, working_df);
                        third_idx = getNextLoc(second_idx, working_df);
                        continue;
                    }
                }
                else if (first.tb == BOT) {
                    if (float_more(first.low, third.low)) {
                        first.tb = NO_TOPBOT;
                        first_idx = getNextLoc(first_idx, working_df);
                        second_idx = getNextLoc(first_idx, working_df);
                        third_idx = getNextLoc(second_idx, working_df);
                        continue;
                    }
                    else {
                        second.tb = NO_TOPBOT;
                        second_idx = getNextLoc(second_idx, working_df);
                        third_idx = getNextLoc(second_idx, working_df);
                        continue;
                    }
                }
            }
            else {
                break;
            }
        }
        else if (first.tb == TOP && second.tb == BOT && float_less_equal(first.high, second.low)) {
            first.tb = NO_TOPBOT;
            second.tb = NO_TOPBOT;
            first_idx = getNextLoc(first_idx, working_df);
            second_idx = getNextLoc(first_idx, working_df);
            third_idx = getNextLoc(second_idx, working_df);
            continue;
        }
        else if (first.tb == BOT && second.tb == TOP && float_more_equal(first.low, second.high)) {
            first.tb = NO_TOPBOT;
            second.tb = NO_TOPBOT;
            first_idx = getNextLoc(first_idx, working_df);
            second_idx = getNextLoc(first_idx, working_df);
            third_idx = getNextLoc(second_idx, working_df);
            continue;
        }
        else {
            break;
        }
    }
    
    // 原地移除被清理的元素
    std::vector<StandardKLine> cleaned;
    for (const auto& kline : working_df) {
        if (kline.tb == TOP || kline.tb == BOT) {
            cleaned.push_back(kline);
        }
    }
    working_df.swap(cleaned);
}

// 笔定义：(from Python define_bi lines 489-831) 
void ChanAnalyzer::defineBi() {
    if (standardized.empty()) return;
    
    // 分步1：收集所有分型到 working_df (Python line 501-507)
    std::vector<StandardKLine> working_df;
    for (const auto& kline : standardized) {
        if (kline.tb == TOP || kline.tb == BOT) {
            StandardKLine elem = kline;
            elem.chan_price = (elem.tb == TOP) ? elem.high : elem.low;
            elem.original_tb = elem.tb;
            working_df.push_back(elem);
        }
    }
    
    if (working_df.size() < 2) {
        marked_bi = working_df;
        return;
    }
    
    // Python line 507: clean_first_two_tb (in-place)
    cleanFirstTwoTB(working_df);
    
    if (working_df.size() < 2) {
        marked_bi = working_df;
        return;
    }
    
    // 重置 previous_skipped_idx
    previous_skipped_idx.clear();
    
    // Python line 510-513: 初始化三个指�?
    int previous_index = 0;
    int current_index = 1;
    int next_index = 2;
    
    // Python line 514: 主循�?
    while (next_index < static_cast<int>(working_df.size()) && 
           previous_index >= 0 && next_index >= 0) {
        
        StandardKLine& prev = working_df[previous_index];
        StandardKLine& cur  = working_df[current_index];
        StandardKLine& nxt  = working_df[next_index];
        
        // ===== Python line 519-569: Case A - cur.tb == prev.tb (同类�? =====
        if (cur.tb == prev.tb) {
            if (cur.tb == TOP) {
                if (float_less(cur.high, prev.high)) {
                    // Python line 522-525: remove_current
                    auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                    previous_index = std::get<0>(result);
                    current_index = std::get<1>(result);
                    next_index = std::get<2>(result);
                }
                else if (float_more(cur.high, prev.high)) {
                    // Python line 527-530: remove_previous
                    auto result = same_tb_remove_previous(working_df, previous_index, current_index, next_index);
                    previous_index = std::get<0>(result);
                    current_index = std::get<1>(result);
                    next_index = std::get<2>(result);
                }
                else { // equal case
                    bool gap_qualify = check_gap_qualify(working_df, previous_index, current_index, next_index);
                    if (next_index < static_cast<int>(working_df.size()) && 
                        nxt.new_index - cur.new_index < CHAN_BI_MIN_SPAN && !gap_qualify) {
                        // Python line 535-538: remove_current
                        auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                    }
                    else {
                        // Python line 540-543: remove_previous
                        auto result = same_tb_remove_previous(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                    }
                }
            }
            else if (cur.tb == BOT) {
                if (float_more(cur.low, prev.low)) {
                    // Python line 547-550: remove_current
                    auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                    previous_index = std::get<0>(result);
                    current_index = std::get<1>(result);
                    next_index = std::get<2>(result);
                }
                else if (float_less(cur.low, prev.low)) {
                    // Python line 552-555: remove_previous
                    auto result = same_tb_remove_previous(working_df, previous_index, current_index, next_index);
                    previous_index = std::get<0>(result);
                    current_index = std::get<1>(result);
                    next_index = std::get<2>(result);
                }
                else { // equal case
                    bool gap_qualify = check_gap_qualify(working_df, previous_index, current_index, next_index);
                    if (next_index < static_cast<int>(working_df.size()) && 
                        nxt.new_index - cur.new_index < CHAN_BI_MIN_SPAN && !gap_qualify) {
                        auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                    }
                    else {
                        auto result = same_tb_remove_previous(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                    }
                }
            }
            continue;
        }
        
        // ===== Python line 570-633: Case B - cur.tb == nxt.tb (下一分型同类�? =====
        if (cur.tb == nxt.tb) {
            if (cur.tb == TOP) {
                if (float_less(cur.high, nxt.high)) {
                    // Python line 573-576: remove_current
                    auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                    previous_index = std::get<0>(result);
                    current_index = std::get<1>(result);
                    next_index = std::get<2>(result);
                }
                else if (float_more(cur.high, nxt.high)) {
                    // Python line 579-582: remove_next
                    auto result = same_tb_remove_next(working_df, previous_index, current_index, next_index);
                    previous_index = std::get<0>(result);
                    current_index = std::get<1>(result);
                    next_index = std::get<2>(result);
                }
                else { // equality case
                    int pre_pre_index = trace_back_index(working_df, previous_index);
                    if (pre_pre_index < 0) {
                        // Python line 586-589: remove_current
                        auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                        continue;
                    }
                    bool gap_qualify = check_gap_qualify(working_df, pre_pre_index, previous_index, current_index);
                    if (cur.new_index - prev.new_index >= CHAN_BI_MIN_SPAN || gap_qualify) {
                        // Python line 593-596: remove_next
                        auto result = same_tb_remove_next(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                    }
                    else {
                        // Python line 598-601: remove_current
                        auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                    }
                }
            }
            else if (cur.tb == BOT) {
                if (float_more(cur.low, nxt.low)) {
                    // Python line 605-608: remove_current
                    auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                    previous_index = std::get<0>(result);
                    current_index = std::get<1>(result);
                    next_index = std::get<2>(result);
                }
                else if (float_less(cur.low, nxt.low)) {
                    // Python line 610-613: remove_next
                    auto result = same_tb_remove_next(working_df, previous_index, current_index, next_index);
                    previous_index = std::get<0>(result);
                    current_index = std::get<1>(result);
                    next_index = std::get<2>(result);
                }
                else {
                    int pre_pre_index = trace_back_index(working_df, previous_index);
                    if (pre_pre_index < 0) {
                        auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                        continue;
                    }
                    bool gap_qualify = check_gap_qualify(working_df, pre_pre_index, previous_index, current_index);
                    if (cur.new_index - prev.new_index >= CHAN_BI_MIN_SPAN || gap_qualify) {
                        auto result = same_tb_remove_next(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                    }
                    else {
                        auto result = same_tb_remove_current(working_df, previous_index, current_index, next_index);
                        previous_index = std::get<0>(result);
                        current_index = std::get<1>(result);
                        next_index = std::get<2>(result);
                    }
                }
            }
            continue;
        }
        
        // ===== Python line 635-744: Case C - distance checks =====
        bool gap_qualify = check_gap_qualify(working_df, previous_index, current_index, next_index);
        
        // Python line 636-744: prev-cur distance < 4
        if (cur.new_index - prev.new_index < CHAN_BI_MIN_SPAN) {
            // Python line 639-730: cur-next distance >= 4 OR gap_qualify
            if ((next_index < static_cast<int>(working_df.size()) && 
                 nxt.new_index - cur.new_index >= CHAN_BI_MIN_SPAN) || gap_qualify) {
                
                int pre_pre_index = trace_back_index(working_df, previous_index);
                
                // Python line 643-644: check if pre_pre-pre-cur qualifies
                bool pre_pre_qualify = false;
                if (pre_pre_index >= 0) {
                    pre_pre_qualify = check_gap_qualify(working_df, pre_pre_index, previous_index, current_index);
                }
                
                if (!pre_pre_qualify) {
                    // Python line 646-687: cur=BOT, prev=TOP, nxt=TOP pattern
                    if (cur.tb == BOT && prev.tb == TOP && nxt.tb == TOP) {
                        if (float_more_equal(prev.high, nxt.high)) {
                            pre_pre_index = trace_back_index(working_df, previous_index);
                            if (pre_pre_index < 0) {
                                working_df[current_index].tb = NO_TOPBOT;
                                current_index = next_index;
                                next_index = get_next_tb(next_index, working_df);
                                continue;
                            }
                            auto it_pre = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), pre_pre_index);
                            if (it_pre != previous_skipped_idx.end()) {
                                previous_skipped_idx.erase(it_pre);
                            }
                            StandardKLine& pre_pre = working_df[pre_pre_index];
                            if (float_more_equal(pre_pre.low, cur.low)) {
                                working_df[pre_pre_index].tb = NO_TOPBOT;
                                int temp_index = trace_back_index(working_df, pre_pre_index);
                                if (temp_index < 0) {
                                    working_df[current_index].tb = NO_TOPBOT;
                                    current_index = next_index;
                                    next_index = get_next_tb(next_index, working_df);
                                }
                                else {
                                    next_index = current_index;
                                    current_index = previous_index;
                                    previous_index = temp_index;
                                    auto it_prev = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                    if (it_prev != previous_skipped_idx.end()) {
                                        previous_skipped_idx.erase(it_prev);
                                    }
                                }
                            }
                            else {
                                working_df[current_index].tb = NO_TOPBOT;
                                current_index = previous_index;
                                previous_index = trace_back_index(working_df, previous_index);
                                if (previous_index >= 0) {
                                    auto it_prev = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                    if (it_prev != previous_skipped_idx.end()) {
                                        previous_skipped_idx.erase(it_prev);
                                    }
                                }
                            }
                        }
                        else { // prev.high < nxt.high
                            working_df[previous_index].tb = NO_TOPBOT;
                            previous_index = trace_back_index(working_df, previous_index);
                            if (previous_index >= 0) {
                                auto it_prev = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                if (it_prev != previous_skipped_idx.end()) {
                                    previous_skipped_idx.erase(it_prev);
                                }
                            }
                        }
                        continue;
                    }
                    // Python line 689-730: cur=TOP, prev=BOT, nxt=BOT pattern
                    else if (cur.tb == TOP && prev.tb == BOT && nxt.tb == BOT) {
                        if (float_less(prev.low, nxt.low)) {
                            pre_pre_index = trace_back_index(working_df, previous_index);
                            if (pre_pre_index < 0) {
                                working_df[current_index].tb = NO_TOPBOT;
                                current_index = next_index;
                                next_index = get_next_tb(next_index, working_df);
                                continue;
                            }
                            auto it_pre = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), pre_pre_index);
                            if (it_pre != previous_skipped_idx.end()) {
                                previous_skipped_idx.erase(it_pre);
                            }
                            StandardKLine& pre_pre = working_df[pre_pre_index];
                            if (float_less_equal(pre_pre.high, cur.high)) {
                                working_df[pre_pre_index].tb = NO_TOPBOT;
                                int temp_index = trace_back_index(working_df, pre_pre_index);
                                if (temp_index < 0) {
                                    working_df[current_index].tb = NO_TOPBOT;
                                    current_index = next_index;
                                    next_index = get_next_tb(next_index, working_df);
                                }
                                else {
                                    next_index = current_index;
                                    current_index = previous_index;
                                    previous_index = temp_index;
                                    auto it_prev = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                    if (it_prev != previous_skipped_idx.end()) {
                                        previous_skipped_idx.erase(it_prev);
                                    }
                                }
                            }
                            else {
                                working_df[current_index].tb = NO_TOPBOT;
                                current_index = previous_index;
                                previous_index = trace_back_index(working_df, previous_index);
                                if (previous_index >= 0) {
                                    auto it_prev = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                    if (it_prev != previous_skipped_idx.end()) {
                                        previous_skipped_idx.erase(it_prev);
                                    }
                                }
                            }
                        }
                        else { // prev.low >= nxt.low
                            working_df[previous_index].tb = NO_TOPBOT;
                            previous_index = trace_back_index(working_df, previous_index);
                            if (previous_index >= 0) {
                                auto it_prev = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                if (it_prev != previous_skipped_idx.end()) {
                                    previous_skipped_idx.erase(it_prev);
                                }
                            }
                        }
                        continue;
                    }
                } // end if !pre_pre_qualify
                // If pre_pre_qualify is true, just fall through to move forward
            }
            else {
                // Python line 731-744: cur-next distance < 4 AND not gap_qualify
                int temp_index = get_next_tb(next_index, working_df);
                if (temp_index >= static_cast<int>(working_df.size())) {
                    // Python line 733-737: reached end -> work_on_end
                    auto result = work_on_end(working_df, previous_index, current_index, next_index);
                    previous_index = std::get<0>(result);
                    current_index = std::get<1>(result);
                    next_index = std::get<2>(result);
                }
                else {
                    // Python line 739-743: leave it for next round
                    previous_skipped_idx.push_back(previous_index);
                    previous_index = current_index;
                    current_index = next_index;
                    next_index = temp_index;
                }
                continue;
            }
        }
        // Python line 746-759: cur-next distance < 4 AND not gap_qualify
        else if (next_index < static_cast<int>(working_df.size()) && 
                 nxt.new_index - cur.new_index < CHAN_BI_MIN_SPAN && !gap_qualify) {
            int temp_index = get_next_tb(next_index, working_df);
            if (temp_index >= static_cast<int>(working_df.size())) {
                auto result = work_on_end(working_df, previous_index, current_index, next_index);
                previous_index = std::get<0>(result);
                current_index = std::get<1>(result);
                next_index = std::get<2>(result);
            }
            else {
                previous_skipped_idx.push_back(previous_index);
                previous_index = current_index;
                current_index = next_index;
                next_index = temp_index;
            }
            continue;
        }
        // Python line 760-788: distance >= 4 OR gap_qualify with price validation
        else if ((next_index < static_cast<int>(working_df.size()) && 
                  nxt.new_index - cur.new_index >= CHAN_BI_MIN_SPAN) || gap_qualify) {
            
            if (cur.tb == TOP && nxt.tb == BOT && float_more(cur.high, nxt.high)) {
                // Python line 761: pass - valid
            }
            else if (cur.tb == TOP && nxt.tb == BOT && float_less_equal(cur.high, nxt.high)) {
                // Python line 763-767: remove current
                working_df[current_index].tb = NO_TOPBOT;
                current_index = next_index;
                next_index = get_next_tb(next_index, working_df);
                continue;
            }
            else if (cur.tb == TOP && nxt.tb == BOT && float_less_equal(cur.low, nxt.low)) {
                // Python line 769-772: remove next
                working_df[next_index].tb = NO_TOPBOT;
                next_index = get_next_tb(next_index, working_df);
                continue;
            }
            else if (cur.tb == TOP && nxt.tb == BOT && float_more(cur.low, nxt.low)) {
                // Python line 773: pass - valid
            }
            else if (cur.tb == BOT && nxt.tb == TOP && float_less(cur.low, nxt.low)) {
                // Python line 776: pass - valid
            }
            else if (cur.tb == BOT && nxt.tb == TOP && float_more_equal(cur.low, nxt.low)) {
                // Python line 778-782: remove current
                working_df[current_index].tb = NO_TOPBOT;
                current_index = next_index;
                next_index = get_next_tb(next_index, working_df);
                continue;
            }
            else if (cur.tb == BOT && nxt.tb == TOP && float_less(cur.high, nxt.high)) {
                // Python line 783: pass - valid
            }
            else if (cur.tb == BOT && nxt.tb == TOP && float_more_equal(cur.high, nxt.high)) {
                // Python line 785-788: remove next
                working_df[next_index].tb = NO_TOPBOT;
                next_index = get_next_tb(next_index, working_df);
                continue;
            }
        }
        
        // ===== Python line 790-796: handle previous_skipped_idx =====
        if (!previous_skipped_idx.empty()) {
            previous_index = previous_skipped_idx.back();
            previous_skipped_idx.pop_back();
            if (working_df[previous_index].tb == NO_TOPBOT) {
                previous_index = get_next_tb(previous_index, working_df);
            }
            current_index = get_next_tb(previous_index, working_df);
            next_index = get_next_tb(current_index, working_df);
            continue;
        }
        
        // ===== Python line 798-801: Move forward (confirmed TB) =====
        previous_index = current_index;
        current_index = next_index;
        next_index = get_next_tb(next_index, working_df);
    }
    
    // ===== Python line 803-827: Final cleanup at end (work_on_end equivalent) =====
    if (next_index >= static_cast<int>(working_df.size())) {
        // Python line 804-814: Check if last kbar can replace cur/prev
        if (!working_df.empty() && !original_data.empty()) {
            // Only proceed if we have valid pointers
            if (current_index < static_cast<int>(working_df.size()) && 
                previous_index >= 0 && previous_index < static_cast<int>(working_df.size())) {
                
                const KLine& last_origin = original_data.back();
                
                // Python line 805-808: if cur is TOP and last high > cur high, or cur is BOT and last low < cur low
                if (working_df[current_index].tb == TOP && 
                    float_more(last_origin.high, working_df[current_index].high)) {
                    working_df.back().tb = working_df[current_index].tb;
                    working_df[current_index].tb = NO_TOPBOT;
                }
                else if (working_df[current_index].tb == BOT && 
                         float_less(last_origin.low, working_df[current_index].low)) {
                    working_df.back().tb = working_df[current_index].tb;
                    working_df[current_index].tb = NO_TOPBOT;
                }
                
                // Python line 810-814: if cur is now invalid, check prev against last
                if (working_df[current_index].tb == NO_TOPBOT) {
                    if ((working_df[previous_index].tb == TOP && 
                         float_more(last_origin.high, working_df[previous_index].high)) ||
                        (working_df[previous_index].tb == BOT && 
                         float_less(last_origin.low, working_df[previous_index].low))) {
                        working_df.back().tb = working_df[previous_index].tb;
                        working_df[previous_index].tb = NO_TOPBOT;
                    }
                }
                
                // Python line 816-826: handle same type at end
                if (previous_index < static_cast<int>(working_df.size()) && 
                    current_index < static_cast<int>(working_df.size()) &&
                    working_df[previous_index].tb == working_df[current_index].tb) {
                    if (working_df[current_index].tb == TOP) {
                        if (float_more(working_df[current_index].high, working_df[previous_index].high)) {
                            working_df[previous_index].tb = NO_TOPBOT;
                        }
                        else {
                            working_df[current_index].tb = NO_TOPBOT;
                        }
                    }
                    else if (working_df[current_index].tb == BOT) {
                        if (float_less(working_df[current_index].low, working_df[previous_index].low)) {
                            working_df[previous_index].tb = NO_TOPBOT;
                        }
                        else {
                            working_df[current_index].tb = NO_TOPBOT;
                        }
                    }
                }
            }
        }
    }
    
    // Python line 828: final result
    std::vector<StandardKLine> result;
    for (auto& kline : working_df) {
        if (kline.tb == TOP || kline.tb == BOT) {
            kline.chan_price = (kline.tb == TOP) ? kline.high : kline.low;
            result.push_back(kline);
        }
    }
    
    marked_bi = result;
    
    if (is_debug && !marked_bi.empty()) {
        // 调试输出保留但不输出到终�?
    }
}

// work_on_end (Python lines 834-862)
std::tuple<int, int, int> ChanAnalyzer::work_on_end(
    std::vector<StandardKLine>& working_df,
    int pre_idx, int cur_idx, int nex_idx) {
    
    if (pre_idx < 0 || pre_idx >= static_cast<int>(working_df.size()) ||
        cur_idx < 0 || cur_idx >= static_cast<int>(working_df.size()) ||
        nex_idx < 0 || nex_idx >= static_cast<int>(working_df.size())) {
        return std::make_tuple(pre_idx, cur_idx, nex_idx);
    }
    
    StandardKLine& prev = working_df[pre_idx];
    StandardKLine& cur = working_df[cur_idx];
    StandardKLine& nxt = working_df[nex_idx];
    
    // Python line 842-850
    if (cur.tb == TOP) {
        if (float_more(prev.low, nxt.low)) {
            working_df[pre_idx].tb = NO_TOPBOT;
            pre_idx = trace_back_index(working_df, pre_idx);
        }
        else {
            working_df[nex_idx].tb = NO_TOPBOT;
            nex_idx = cur_idx;
            cur_idx = pre_idx;
            pre_idx = trace_back_index(working_df, pre_idx);
        }
    }
    else { // BOT
        if (float_less(prev.high, nxt.high)) {
            working_df[pre_idx].tb = NO_TOPBOT;
            pre_idx = trace_back_index(working_df, pre_idx);
        }
        else {
            working_df[nex_idx].tb = NO_TOPBOT;
            nex_idx = cur_idx;
            cur_idx = pre_idx;
            pre_idx = trace_back_index(working_df, pre_idx);
        }
    }
    
    if (pre_idx >= 0) {
        auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), pre_idx);
        if (it != previous_skipped_idx.end()) {
            previous_skipped_idx.erase(it);
        }
    }
    
    return std::make_tuple(pre_idx, cur_idx, nex_idx);
}

// K线缺口作为线段 (匹配Python kbar_gap_as_xd)
bool ChanAnalyzer::kbarGapAsXdFull(const std::vector<StandardKLine>& working_df, 
                                    int first_idx, int second_idx, int compare_idx) {
    if (first_idx + 1 != second_idx) return false;
    
    const auto& firstElem = working_df[first_idx];
    const auto& secondElem = working_df[second_idx];
    
    if (!gapExistsInRange(firstElem.date, secondElem.date)) return false;
    
    TopBotType gap_direction = NO_TOPBOT;
    if (secondElem.tb == TOP) gap_direction = BOT2TOP;
    else if (secondElem.tb == BOT) gap_direction = TOP2BOT;
    else return false;
    
    auto regions = gapRegion(firstElem.date, secondElem.date, gap_direction);
    if (regions.empty()) return false;
    regions = combineGaps(regions);
    if (regions.empty()) return false;
    
    // Python: sum of ALL gap ranges for golden ratio check
    double total_gap_range = 0.0;
    for (const auto& r : regions) {
        total_gap_range += (r.second - r.first);
    }
    double price_diff = std::abs(firstElem.chan_price - secondElem.chan_price);
    bool gap_range_in_portion = false;
    if (price_diff > MIN_PRICE_UNIT) {
        gap_range_in_portion = float_more_equal(total_gap_range / price_diff, GOLDEN_RATIO);
    }
    if (!gap_range_in_portion) return false;
    
    // Python: check price coverage
    bool item_price_covered = false;
    if (compare_idx < 0 || compare_idx >= static_cast<int>(working_df.size())) {
        item_price_covered = true;
    } else {
        const auto& compare_elem = working_df[compare_idx];
        if (gap_direction == TOP2BOT) {
            item_price_covered = float_less_equal(regions[0].first, compare_elem.chan_price);
        } else if (gap_direction == BOT2TOP) {
            item_price_covered = float_more_equal(regions.back().second, compare_elem.chan_price);
        }
    }
    
    return gap_range_in_portion && item_price_covered;
}

// ========================================================================
// Feature Sequence Element inclusion processing (Chan Theory compliant rewrite)
// ========================================================================

std::vector<FeatureSeqElement> ChanAnalyzer::buildFeatureSeq(
        const std::vector<StandardKLine>& working_df, int start_loc) {
    std::vector<FeatureSeqElement> seq;
    for (int i = start_loc; i < static_cast<int>(working_df.size()); i++) {
        if (working_df[i].original_tb == TOP || working_df[i].original_tb == BOT) {
            FeatureSeqElement elem;
            elem.tb = static_cast<TopBotType>(working_df[i].original_tb);
            double p = (working_df[i].original_tb == TOP)
                ? working_df[i].high : working_df[i].low;
            elem.price = p;
            elem.orig_price = p;
            elem.orig_market_idx = i;
            elem.is_merged = false;
            seq.push_back(elem);
        }
    }
    return seq;
}

bool ChanAnalyzer::hasFeatureSeqInclusion(
        const FeatureSeqElement& e0, const FeatureSeqElement& e1,
        const FeatureSeqElement& e2, const FeatureSeqElement& e3) {
    return (float_less_equal(e0.price, e2.price) &&
            float_more_equal(e1.price, e3.price)) ||
           (float_more_equal(e0.price, e2.price) &&
            float_less_equal(e1.price, e3.price));
}

std::pair<FeatureSeqElement, FeatureSeqElement> ChanAnalyzer::mergeFeatureSeqPair(
        const FeatureSeqElement& e0, const FeatureSeqElement& e1,
        const FeatureSeqElement& e2, const FeatureSeqElement& e3,
        bool merge_max) {
    // 特征序列的包含合并与"笔"的处理方式保持一致: 方向由"前一个特征元素"与"当前特征元素"
    // 的高点比较决定(isBullType), 向上则两端都取 max, 向下则两端都取 min。
    // 合并方向由调用方 processInclusions 计算并传入(merge_max)。
    FeatureSeqElement m_top, m_bot;

    if (merge_max) {
        m_top.tb = TOP;
        m_bot.tb = BOT;
        m_top.price = std::max(e0.price, e2.price);
        m_bot.price = std::max(e1.price, e3.price);
        m_top.orig_price = std::max(e0.orig_price, e2.orig_price);
        m_bot.orig_price = std::max(e1.orig_price, e3.orig_price);
        m_top.orig_market_idx = float_more(e0.orig_price, e2.orig_price)
            ? e0.orig_market_idx : e2.orig_market_idx;
        m_bot.orig_market_idx = float_more(e1.orig_price, e3.orig_price)
            ? e1.orig_market_idx : e3.orig_market_idx;
    } else {
        m_top.tb = BOT;
        m_bot.tb = TOP;
        m_top.price = std::min(e0.price, e2.price);
        m_bot.price = std::min(e1.price, e3.price);
        m_top.orig_price = std::min(e0.orig_price, e2.orig_price);
        m_bot.orig_price = std::min(e1.orig_price, e3.orig_price);
        m_top.orig_market_idx = float_less(e0.orig_price, e2.orig_price)
            ? e0.orig_market_idx : e2.orig_market_idx;
        m_bot.orig_market_idx = float_less(e1.orig_price, e3.orig_price)
            ? e1.orig_market_idx : e3.orig_market_idx;
    }

    m_top.is_merged = true;
    m_bot.is_merged = true;

    return {m_top, m_bot};
}

void ChanAnalyzer::processInclusions(std::vector<FeatureSeqElement>& seq, TopBotType direction) {
    if (seq.empty()) return;

    // 缠论原文：上升线段特征序列 = 向下笔 = (TOP,BOT) 配对，起点必须是 TOP
    //         下降线段特征序列 = 向上笔 = (BOT,TOP) 配对，起点必须是 BOT
    // findInitialDirectionFull 把 initial_loc 设为极值分型，刚好是反向类型，
    // 所以这里跳过领头不匹配的元素，定位到正确的特征序列起点。
    TopBotType expected_start_tb = (direction == BOT2TOP) ? TOP : BOT;
    int start_offset = 0;
    while (start_offset < static_cast<int>(seq.size()) &&
           seq[start_offset].tb != expected_start_tb) {
        start_offset++;
    }

    int i = start_offset;
    while (i + 3 < static_cast<int>(seq.size())) {
        if (hasFeatureSeqInclusion(seq[i], seq[i+1], seq[i+2], seq[i+3])) {
            // 与笔阶段一致: 用前一个特征元素与当前元素的高点比较确定方向
            bool merge_max;
            if (i == start_offset) {
                merge_max = (direction == BOT2TOP);
            } else {
                double prev_high = std::max(seq[i-2].price, seq[i-1].price);
                double cur_high = std::max(seq[i].price, seq[i+1].price);
                // 与笔阶段同一规则(同 isBullType): 严格比较, 等号情形原文前提已排除
                merge_max = float_less(prev_high, cur_high);
            }
            auto [m0, m1] = mergeFeatureSeqPair(
                seq[i], seq[i+1], seq[i+2], seq[i+3], merge_max);
            seq[i] = m0;
            seq[i+1] = m1;
            seq.erase(seq.begin() + i + 2, seq.begin() + i + 4);
            i = std::max(start_offset, i - 2);
        } else {
            i += 2;
        }
    }
}

void ChanAnalyzer::applyCleanSequence(
        const std::vector<FeatureSeqElement>& feature_seq,
        std::vector<StandardKLine>& working_df, int start_loc, int end_loc) {
    int clear_end = (end_loc < 0) ? static_cast<int>(working_df.size()) : end_loc;
    for (int i = start_loc; i < clear_end; i++) {
        if (working_df[i].tb != NO_TOPBOT) {
            working_df[i].tb = NO_TOPBOT;
        }
    }
    for (const auto& elem : feature_seq) {
        int idx = elem.orig_market_idx;
        if (idx >= 0 && idx < static_cast<int>(working_df.size())) {
            working_df[idx].tb = elem.tb;
            working_df[idx].chan_price = elem.orig_price;
        }
    }
}


// ========================================================================
// FeatureSeqElement-based XD endpoint detection (replaces findXDFull)
// Processes one segment: finds first XD or rollback, then returns.
// Caller (defineXD) iterates per segment with rebuild+merge per direction.
// ========================================================================

XDFindResult ChanAnalyzer::findXDOnFeatureSeq(
        std::vector<FeatureSeqElement>& feature_seq,
        std::vector<StandardKLine>& working_df,
        int seq_pos, TopBotType direction,
        int tail_start_market) {

    if (feature_seq.empty()) return {false};
    (void)tail_start_market;

    // 对照 Python find_xd_on_feature_seq(1205-1210): 自行定位目标类型起点
    TopBotType target_tb = (direction == BOT2TOP) ? TOP : BOT;
    int seq_pos_aligned = seq_pos;
    while (seq_pos_aligned < static_cast<int>(feature_seq.size()) &&
           feature_seq[seq_pos_aligned].tb != target_tb) {
        seq_pos_aligned++;
    }
    if (seq_pos_aligned + 5 >= static_cast<int>(feature_seq.size())) {
        return {false};
    }

    int i = seq_pos_aligned;
    // Python 每轮 i += 1: 六个元素是滑动的窗口, 缺口检查在奇偶位置都会执行
    while (i + 5 < static_cast<int>(feature_seq.size())) {
        const FeatureSeqElement& e0 = feature_seq[i];
        const FeatureSeqElement& e1 = feature_seq[i + 1];
        const FeatureSeqElement& e2 = feature_seq[i + 2];
        const FeatureSeqElement& e3 = feature_seq[i + 3];
        const FeatureSeqElement& e4 = feature_seq[i + 4];
        const FeatureSeqElement& e5 = feature_seq[i + 5];

        TopBotType xd_type = NO_TOPBOT;
        bool with_gap = false;
        bool kg2 = false;

        // ---- K线缺口成段 (Python 1225-1241) ----
        if (!previous_with_xd_gap) {
            kg2 = (e2.orig_market_idx + 1 == e3.orig_market_idx) &&
                  kbarGapAsXdFull(working_df, e2.orig_market_idx,
                                  e3.orig_market_idx, e1.orig_market_idx);
            if (kg2) previous_with_xd_gap = true;
        }
        if (!kg2 && previous_with_xd_gap) {
            previous_with_xd_gap = false;
            kg2 = (e1.orig_market_idx + 1 == e2.orig_market_idx) &&
                  kbarGapAsXdFull(working_df, e1.orig_market_idx,
                                  e2.orig_market_idx, e0.orig_market_idx);
            if (kg2) previous_with_xd_gap = true;
        }
        if (kg2) {
            if (direction == BOT2TOP &&
                float_more(e2.orig_price, e4.orig_price)) {
                xd_type = TOP;
            } else if (direction == TOP2BOT &&
                       float_less(e2.orig_price, e4.orig_price)) {
                xd_type = BOT;
            }
            if (xd_type != NO_TOPBOT) with_gap = true;
        }

        // ---- 标准特征序列分型 (Python 1243-1257) ----
        if (xd_type == NO_TOPBOT) {
            if (direction == BOT2TOP) {
                if (e2.tb == TOP &&
                    float_more(e2.orig_price, e0.orig_price) &&
                    float_more(e2.orig_price, e4.orig_price) &&
                    float_more(e3.orig_price, e5.orig_price)) {
                    xd_type = TOP;
                    with_gap = float_less(e0.orig_price, e3.orig_price);
                }
            } else {
                if (e2.tb == BOT &&
                    float_less(e2.orig_price, e0.orig_price) &&
                    float_less(e2.orig_price, e4.orig_price) &&
                    float_less(e3.orig_price, e5.orig_price)) {
                    xd_type = BOT;
                    with_gap = float_more(e0.orig_price, e3.orig_price);
                }
            }
        }

        if (xd_type != NO_TOPBOT) {
            // Python 1259-1262: 记录结果前用 check_previous_elem_to_avoid_xd_gap 收窄
            if (with_gap) {
                with_gap = checkPreviousElemToAvoidXdGap(with_gap,
                                                         feature_seq, i,
                                                         working_df);
            }
            // 原文第67课第二种情况: 有缺口时必须由反向特征序列的反向分型确认;
            // 若一直没有该分型而直接创出更极端新高/新低, 则 A/B/C 只能算一段,
            // 该候选不成立, 继续向后扫描。
            if (with_gap &&
                !secondFeatureSeqConfirms(working_df, e2.orig_market_idx, xd_type)) {
                i += 1;
                continue;
            }
            int new_i = kg2 ? (i + 1) : (i + 3);
            int next_start = (new_i < static_cast<int>(feature_seq.size()))
                ? feature_seq[new_i].orig_market_idx
                : e2.orig_market_idx + 1;
            TopBotType new_dir = (xd_type == TOP) ? TOP2BOT : BOT2TOP;
            return {true, e2.orig_market_idx, xd_type, with_gap, next_start,
                    new_dir, false, 0, kg2};
        }

        i += 1;
    }

    return {false};
}

// ========================================================================
// 线段端点极值修正 (repairXdExtremes)
//
// 缠论要求：线段的端点必须是该线段区间内的极值点。
//   * 上升线段的终点(TOP)必须是该段最高点, 起点(BOT)必须是该段最低点
//   * 下降线段的起点(TOP)必须是该段最高点, 终点(BOT)必须是该段最低点
//
// 主循环 (defineXD while) 一旦在特征序列的第一个分型处提交端点就立刻翻转方向,
// 之后价格继续创出更极端的新高/新低时不会回头修正该端点。原 Python 版只有两处
// 很窄的补救 (gap_XD 弹出 / prev_xd 失效回退), 覆盖不到"趋势延续"这种最常见情形,
// 于是真实顶底被"避开"：线段端点停在半路的小高点/小低点上, 画出的线段会穿过
// 之后的真实极值。
//
// 本函数在相邻端点围成的区间内检查是否存在同类型且更极端的笔端点, 若有则把端点
// 移动到最极端的那一笔上。区间随端点移动而收缩, 因此迭代若干趟即可稳定。
// 约束: 移动后该线段仍需至少包含 3 笔 (缠论线段最小笔数), 故限制移动范围。
// ========================================================================
void ChanAnalyzer::repairXdExtremes(std::vector<StandardKLine>& working_df) {
    std::vector<int> locs;
    for (int j = 0; j < static_cast<int>(working_df.size()); j++) {
        if (working_df[j].xd_tb == TOP || working_df[j].xd_tb == BOT) {
            locs.push_back(j);
        }
    }
    if (locs.empty()) return;

    const int max_passes = 16;
    for (int pass = 0; pass < max_passes; pass++) {
        bool moved = false;
        for (size_t k = 0; k < locs.size(); k++) {
            int cur = locs[k];
            TopBotType tp = static_cast<TopBotType>(working_df[cur].xd_tb);
            if (tp != TOP && tp != BOT) continue;

            int prev = (k > 0) ? locs[k - 1] : -1;
            int next = (k + 1 < locs.size())
                ? locs[k + 1] : static_cast<int>(working_df.size());

            // 端点必须是自己前后两段并集 [prev, next] 内的极值
            int lo_span = (prev >= 0) ? prev + 1 : 0;
            int hi_span = (next < static_cast<int>(working_df.size()))
                ? next - 1 : static_cast<int>(working_df.size()) - 1;
            // 缠论: 线段至少三笔 —— 移动后前段(prev..cur)与后段(cur..next)都要够长
            int lo_move = (prev >= 0) ? prev + CHAN_MIN_BI_SPAN : 0;
            int hi_move = (next < static_cast<int>(working_df.size()))
                ? next - CHAN_MIN_BI_SPAN : hi_span;
            if (lo_move < lo_span) lo_move = lo_span;
            if (hi_move > hi_span) hi_move = hi_span;
            if (lo_move > hi_move) continue;

            double cur_price = working_df[cur].chan_price;
            int best = -1;
            double best_price = cur_price;
            for (int j = lo_move; j <= hi_move; j++) {
                if (j == cur) continue;
                if (working_df[j].original_tb != tp) continue;
                double p = working_df[j].chan_price;
                bool more_extreme = (tp == TOP) ? float_more(p, best_price)
                                                : float_less(p, best_price);
                if (more_extreme) {
                    best_price = p;
                    best = j;
                }
            }

            if (best >= 0) {
                working_df[cur].xd_tb = NO_TOPBOT;
                working_df[best].xd_tb = tp;
                working_df[best].chan_price = best_price;
                locs[k] = best;
                moved = true;
            }
        }
        if (!moved) break;
    }
}

// ========================================================================
// 缺口再确认 (对照 Python check_previous_elem_to_avoid_xd_gap)
// 原文第67课: 第一种情况要求"第一、二元素间不存在特征序列缺口"。若在 e0 之前
// 已存在同类型的特征元素越过 e3, 则该缺口判定不成立 —— Python 原版用这一条把
// with_gap 收窄, C++ 移植时漏掉了, 导致缺口型(第二种情况)分支被过度触发。
// ========================================================================
bool ChanAnalyzer::checkPreviousElemToAvoidXdGap(
        bool with_gap, const std::vector<FeatureSeqElement>& seq, int i,
        std::vector<StandardKLine>& working_df) {
    if (i + 3 >= static_cast<int>(seq.size())) return with_gap;
    int first_idx = seq[i].orig_market_idx;
    int forth_idx = seq[i + 3].orig_market_idx;
    if (first_idx < 0 || first_idx >= static_cast<int>(working_df.size()) ||
        forth_idx < 0 || forth_idx >= static_cast<int>(working_df.size())) {
        return with_gap;
    }
    TopBotType first_tb = seq[i].tb;
    std::vector<int> prev = getPreviousNElem(first_idx, working_df, 0,
                                             first_tb, true);
    if (prev.empty()) return with_gap;

    if (first_tb == TOP) {
        double mx = working_df[prev[0]].chan_price;
        for (size_t k = 1; k < prev.size(); k++) {
            mx = std::max(mx, working_df[prev[k]].chan_price);
        }
        with_gap = float_less(mx, working_df[forth_idx].chan_price);
    } else if (first_tb == BOT) {
        double mn = working_df[prev[0]].chan_price;
        for (size_t k = 1; k < prev.size(); k++) {
            mn = std::min(mn, working_df[prev[k]].chan_price);
        }
        with_gap = float_more(mn, working_df[forth_idx].chan_price);
    }
    return with_gap;
}

// ========================================================================
// 非法端点对清理 (cleanXdMarks)
//
// 线段端点必须"顶底交替": 一段上涨线段结束于顶, 下一段下跌线段即从该顶开始并以底
// 结束。若相邻两个端点同类型 (Python 原版 defineXD 在回退/缺口分支下会留下这种结果),
// 下游 getXianDuan() 会因为类型不交替而把这一对整体丢弃 —— 表现就是线段凭空少一段、
// 真实顶底被"避开"。这里只清理这种非法相邻: 同类型时保留更极端的一个 (顶取更高、
// 底取更低), 不改变其余划分结果。
// ========================================================================
void ChanAnalyzer::cleanXdMarks(std::vector<StandardKLine>& working_df) {
    const int max_passes = 16;
    for (int pass = 0; pass < max_passes; pass++) {
        std::vector<int> locs;
        for (int j = 0; j < static_cast<int>(working_df.size()); j++) {
            if (working_df[j].xd_tb == TOP || working_df[j].xd_tb == BOT) {
                locs.push_back(j);
            }
        }
        bool changed = false;
        for (size_t k = 0; k + 1 < locs.size(); k++) {
            int a = locs[k];
            int b = locs[k + 1];
            TopBotType ta = static_cast<TopBotType>(working_df[a].xd_tb);
            TopBotType tb = static_cast<TopBotType>(working_df[b].xd_tb);
            if (ta != tb) continue;
            // 同类型相邻: 保留更极端的那个
            bool keep_b = (ta == TOP)
                ? float_more(working_df[b].chan_price, working_df[a].chan_price)
                : float_less(working_df[b].chan_price, working_df[a].chan_price);
            working_df[keep_b ? a : b].xd_tb = NO_TOPBOT;
            changed = true;
            break;
        }
        if (!changed) break;
    }
}

// ========================================================================
// 第二种情况确认 (原文第67课)
//
// 原文: "特征序列的顶分型中, 第一和第二元素间存在特征序列的缺口, 如果从该分型
// 最高点开始的向下一笔开始的序列的特征序列出现底分型, 那么该线段在该顶分型的
// 高点处结束" (底分型情形对称)。
// 第78课补充: "对于线段破坏的第二种情况, 例如线段B对线段A是第二种情况, 而线段C
// 没有形成第二特征序列的分型又直接新高或新低了, 这时候, 不能认为这是三个线段,
// 线段A、B、C加起来只能算是一个线段。"
//
// 实现: 自 pivot(候选端点) 之后取反向笔构造第二特征序列(元素=笔的区间[低,高]),
// 按"沿该反向线段方向"做严格包含处理(第78课: 第二特征序列必须严格按包含关系处理,
// 且不区分假设分界点两侧), 再找反向分型。找不到 -> 该候选不成立, 继续向后扫描。
// 元素不足(数据末尾, 无法判定) -> 不拦(返回 true), 交给尾部推断。
// ========================================================================
bool ChanAnalyzer::secondFeatureSeqConfirms(
        const std::vector<StandardKLine>& working_df,
        int pivot_idx, TopBotType pivot_type) {

    std::vector<int> pts;
    for (int j = pivot_idx + 1; j < static_cast<int>(working_df.size()); j++) {
        if (working_df[j].original_tb != NO_TOPBOT) pts.push_back(j);
    }

    // 第二特征序列元素 = pivot 之后与"反向段"同向的笔, 用 (low, high) 区间表示
    std::vector<std::pair<double, double>> elems;
    for (size_t k = 0; k + 1 < pts.size(); k++) {
        const StandardKLine& a = working_df[pts[k]];
        const StandardKLine& b = working_df[pts[k + 1]];
        if (pivot_type == TOP) {
            // 上一段向上结束后是下跌段, 其特征序列为向上笔 (BOT -> TOP)
            if (a.original_tb == BOT && b.original_tb == TOP) {
                elems.push_back(std::make_pair(a.low, b.high));
            }
        } else {
            // 上一段向下结束后是上涨段, 其特征序列为向下笔 (TOP -> BOT)
            if (a.original_tb == TOP && b.original_tb == BOT) {
                elems.push_back(std::make_pair(b.low, a.high));
            }
        }
    }
    if (elems.size() < 3) return true;   // 无法判定, 不阻拦

    // 包含处理: 与"笔"阶段完全同一套方法 —— 方向由"前一个元素"与"当前元素"的高点比较
    // 决定(isBullType: 前一个高点较低 => 向上 => 两端取 max; 否则向下 => 两端取 min),
    // 且方向一旦在某元素上确定就粘住(trend), 与 standardize 中 first.tb 的用法一致。
    // 仅仅当被合并元素是序列首元素(没有前一个元素)时, 才回退到沿反向线段方向。
    std::vector<std::pair<double, double>> m;
    std::vector<int> tr;      // 0 = 未定, 1 = 向上(max), -1 = 向下(min)
    for (const auto& e : elems) {
        if (m.empty()) { m.push_back(e); tr.push_back(0); continue; }
        std::pair<double, double>& p = m.back();
        bool contains = (p.first <= e.first && p.second >= e.second);
        bool contained = (p.first >= e.first && p.second <= e.second);
        if (contains || contained) {
            bool merge_max;
            if (tr.back() != 0) {
                merge_max = (tr.back() > 0);
            } else if (m.size() >= 2) {
                // 与笔阶段 isBullType(past, first) 一致
                // 同 isBullType: 严格比较 (等号情形原文前提已排除)
                merge_max = float_less(m[m.size() - 2].second, p.second);
            } else {
                merge_max = (pivot_type == BOT);
            }
            tr.back() = merge_max ? 1 : -1;
            if (merge_max) {
                p.first = std::max(p.first, e.first);
                p.second = std::max(p.second, e.second);
            } else {
                p.first = std::min(p.first, e.first);
                p.second = std::min(p.second, e.second);
            }
        } else {
            m.push_back(e);
            tr.push_back(0);
        }
    }
    if (m.size() < 3) return true;

    // 反向分型: TOP pivot -> 找底分型(中间元素低点最低); BOT pivot -> 找顶分型
    for (size_t k = 1; k + 1 < m.size(); k++) {
        if (pivot_type == TOP) {
            if (m[k].first < m[k - 1].first && m[k].first < m[k + 1].first) {
                return true;
            }
        } else {
            if (m[k].second > m[k - 1].second && m[k].second > m[k + 1].second) {
                return true;
            }
        }
    }
    return false;
}

// XD定义函数 (基于Python defineXD逻辑, 2026-04-28 迭代版)
void ChanAnalyzer::defineXD(int initial_state) {
    if (marked_bi.empty()) return;
    
    std::vector<StandardKLine> working_df = marked_bi;
    
    for (auto& kline : working_df) {
        if (kline.chan_price == 0) {
            kline.chan_price = (kline.tb == TOP) ? kline.high : kline.low;
        }
    }
    
    std::pair<int, TopBotType> initial = findInitialDirectionFull(working_df, static_cast<TopBotType>(initial_state));
    int initial_loc = initial.first;
    TopBotType initial_direction = initial.second;
    
    if (initial_loc < 0 || initial_loc >= static_cast<int>(working_df.size())) {
        return;
    }
    
    TopBotType direction = initial_direction;
    int tail_start = initial_loc;
    
    gap_XD.clear();
    previous_with_xd_gap = false;
    
    while (tail_start < static_cast<int>(working_df.size())) {
        auto seq = buildFeatureSeq(working_df, tail_start);
        if (seq.size() < 6) break;

        processInclusions(seq, direction);
        applyCleanSequence(seq, working_df, tail_start);

        XDFindResult result = findXDOnFeatureSeq(seq, working_df, 0,
                                                 direction, tail_start);

        if (!result.found) {
            // 对照 Python defineXD(1406-1422): 还有待确认的缺口端点且剩余序列
            // 已越过其价格 -> 弹掉并回退重扫, 而不是直接结束线段划分
            if (!gap_XD.empty() && seq.size() >= 4) {
                double mx = -std::numeric_limits<double>::max();
                double mn = std::numeric_limits<double>::max();
                for (const auto& e : seq) {
                    mx = std::max(mx, e.orig_price);
                    mn = std::min(mn, e.orig_price);
                }
                double pgp = working_df[gap_XD.back()].chan_price;
                bool pop_it = false;
                if (direction == TOP2BOT && float_more(mx, pgp)) {
                    pop_it = true;
                } else if (direction == BOT2TOP && float_less(mn, pgp)) {
                    pop_it = true;
                }
                if (pop_it) {
                    int rollback_idx = gap_XD.back();
                    gap_XD.pop_back();
                    working_df[rollback_idx].xd_tb = NO_TOPBOT;
                    direction = (direction == TOP2BOT) ? BOT2TOP : TOP2BOT;
                    tail_start = rollback_idx;
                    continue;
                }
            }
            break;
        }

        int xd_idx = result.xd_market_idx;
        int rollback_idx = -1;

        // 对照 Python defineXD(1427-1442): 带缺口的新端点若被已存缺口端点反向越过
        if (result.with_gap && !gap_XD.empty()) {
            std::vector<double> check_prices;
            for (int j = xd_idx;
                 j < xd_idx + 4 && j < static_cast<int>(working_df.size()); j++) {
                if (working_df[j].original_tb != NO_TOPBOT) {
                    check_prices.push_back(working_df[j].chan_price);
                }
            }
            if (!check_prices.empty()) {
                double pgp = working_df[gap_XD.back()].chan_price;
                bool hit = false;
                if (direction == TOP2BOT &&
                    float_more(*std::max_element(check_prices.begin(),
                                                 check_prices.end()), pgp)) {
                    hit = true;
                } else if (direction == BOT2TOP &&
                           float_less(*std::min_element(check_prices.begin(),
                                                        check_prices.end()), pgp)) {
                    hit = true;
                }
                if (hit) {
                    rollback_idx = gap_XD.back();
                    gap_XD.pop_back();
                    working_df[rollback_idx].xd_tb = NO_TOPBOT;
                    int to = (result.next_market_start > 0)
                        ? result.next_market_start
                        : static_cast<int>(working_df.size()) - 1;
                    restoreTbData(working_df, rollback_idx, to);
                    direction = (direction == TOP2BOT) ? BOT2TOP : TOP2BOT;
                    tail_start = rollback_idx;
                    continue;
                }
            }
        }

        if (rollback_idx < 0) {
            // 对照 Python defineXD(1444-1460): 上一反类型端点失效则回退
            std::vector<int> prev_locs = getPreviousNElem(
                xd_idx, working_df, 0,
                (result.xd_type == TOP) ? BOT : TOP, true);
            if (!prev_locs.empty()) {
                int prev_idx = prev_locs[0];
                bool invalid = false;
                if (working_df[prev_idx].xd_tb == TOP &&
                    result.xd_type == BOT &&
                    float_less(working_df[prev_idx].chan_price,
                               working_df[xd_idx].chan_price)) {
                    invalid = true;
                } else if (working_df[prev_idx].xd_tb == BOT &&
                           result.xd_type == TOP &&
                           float_more(working_df[prev_idx].chan_price,
                                      working_df[xd_idx].chan_price)) {
                    invalid = true;
                }
                if (invalid) {
                    restoreTbData(working_df, prev_idx,
                                  static_cast<int>(working_df.size()) - 1);
                    working_df[prev_idx].xd_tb = NO_TOPBOT;
                    direction = (result.xd_type == TOP) ? TOP2BOT : BOT2TOP;
                    tail_start = prev_idx;
                    continue;
                }
            }
        }

        working_df[xd_idx].xd_tb = result.xd_type;
        if (result.with_gap) gap_XD.push_back(xd_idx);

        tail_start = result.next_market_start;
        if (!result.is_kg2_backstep && tail_start < xd_idx) {
            tail_start = xd_idx;
        }
        direction = (result.xd_type == TOP) ? TOP2BOT : BOT2TOP;
    }

// ===== 清理非法端点对 (相邻同类型) =====
    cleanXdMarks(working_df);

#if CHAN_STANDARDIZE_XD
    // ===== 线段标准化: 把端点校正为该段极值 (第78课允许的独立步骤) =====
    repairXdExtremes(working_df);
#endif

    // ========== TAIL INFERENCE ==========
    
    std::vector<int> prev_xd_locs;
    for (int j = static_cast<int>(working_df.size()) - 1; j >= 0; j--) {
        if (working_df[j].xd_tb == TOP || working_df[j].xd_tb == BOT) {
            prev_xd_locs.push_back(j);
            if (prev_xd_locs.size() >= 1) break;
        }
    }
    
    if (!prev_xd_locs.empty()) {
        int prev_loc = prev_xd_locs[0];
        
        std::vector<int> pre_pre;
        for (int j = prev_loc - 1; j >= 0; j--) {
            if (working_df[j].xd_tb == TOP || working_df[j].xd_tb == BOT) {
                pre_pre.push_back(j);
                if (pre_pre.size() >= 1) break;
            }
        }
        
        int work_loc = prev_loc + 3;
        if (work_loc < static_cast<int>(working_df.size())) {
            std::vector<double> tcp;
            std::vector<int> tidx;
            for (int j = work_loc;
                 j < static_cast<int>(working_df.size()); j++) {
                if (working_df[j].original_tb != NO_TOPBOT) {
                    tcp.push_back(working_df[j].chan_price);
                    tidx.push_back(j);
                }
            }
            
            if (!tcp.empty()) {
                bool gc = false;
                
                if (!gap_XD.empty()) {
                    double mx = *std::max_element(tcp.begin(), tcp.end());
                    double mn = *std::min_element(tcp.begin(), tcp.end());
                    
                    if (direction == TOP2BOT) {
                        auto it = std::max_element(tcp.begin(), tcp.end());
                        int wl = tidx[std::distance(tcp.begin(), it)];
                        if (float_more(mx,
                                       working_df[prev_loc].chan_price)) {
                            working_df[prev_loc].xd_tb = NO_TOPBOT;
                            working_df[wl].xd_tb = TOP;
                            gc = true;
                        }
                    } else {
                        auto it = std::min_element(tcp.begin(), tcp.end());
                        int wl = tidx[std::distance(tcp.begin(), it)];
                        if (float_less(mn,
                                       working_df[prev_loc].chan_price)) {
                            working_df[prev_loc].xd_tb = NO_TOPBOT;
                            working_df[wl].xd_tb = BOT;
                            gc = true;
                        }
                    }
                    
                    if (gc) {
                        int ci = -1;
                        for (size_t jj = 0; jj < tidx.size(); jj++) {
                            if (working_df[tidx[jj]].xd_tb == TOP ||
                                working_df[tidx[jj]].xd_tb == BOT) {
                                ci = static_cast<int>(jj); break;
                            }
                        }
                        if (ci >= 0) {
                            prev_loc = tidx[ci];
                            work_loc = prev_loc + 3;
                            tcp.clear();
                            tidx.clear();
                            for (int j = work_loc;
                                 j < static_cast<int>(working_df.size());
                                 j++) {
                                if (working_df[j].original_tb != NO_TOPBOT) {
                                    tcp.push_back(working_df[j].chan_price);
                                    tidx.push_back(j);
                                }
                            }
                        }
                    }
                }
                
                if (!tcp.empty()) {
                    double mx = *std::max_element(tcp.begin(), tcp.end());
                    double mn = *std::min_element(tcp.begin(), tcp.end());
                    
                    if (direction == TOP2BOT) {
                        if (float_more(working_df[prev_loc].chan_price, mx) ||
                            (!pre_pre.empty() &&
                             float_more(working_df[pre_pre[0]].chan_price,
                                        mn))) {
                            auto it = std::min_element(tcp.begin(),
                                                       tcp.end());
                            working_df[tidx[std::distance(tcp.begin(), it)]]
                                .xd_tb = BOT;
                        } else if (float_less(working_df[prev_loc].chan_price,
                                              mx)) {
                            auto it = std::max_element(tcp.begin(),
                                                       tcp.end());
                            working_df[tidx[std::distance(tcp.begin(), it)]]
                                .xd_tb = TOP;
                            working_df[prev_loc].xd_tb = NO_TOPBOT;
                        }
                    } else {
                        if (float_less(working_df[prev_loc].chan_price, mn) ||
                            (!pre_pre.empty() &&
                             float_less(working_df[pre_pre[0]].chan_price,
                                        mx))) {
                            auto it = std::max_element(tcp.begin(),
                                                       tcp.end());
                            working_df[tidx[std::distance(tcp.begin(), it)]]
                                .xd_tb = TOP;
                        } else if (float_more(working_df[prev_loc].chan_price,
                                              mn)) {
                            auto it = std::min_element(tcp.begin(),
                                                       tcp.end());
                            working_df[tidx[std::distance(tcp.begin(), it)]]
                                .xd_tb = BOT;
                            working_df[prev_loc].xd_tb = NO_TOPBOT;
                        }
                    }
                }
            }
        }
    }
    
cleanXdMarks(working_df);

#if CHAN_STANDARDIZE_XD
    // ===== 尾部推断后再次标准化 (尾部推断可能新增/移动最后一个端点) =====
    repairXdExtremes(working_df);
#endif

    // ===== 少于三笔的相邻端点对不成线段 (线段待形成) =====
    // 原文第65课: 线段至少三笔; 若相邻两个端点的跨度不足三笔, 那一段尚未成为线段,
    // 不应作为线段输出 —— 去掉后一个端点, 让它并入相邻线段待其形成。
    for (int pass = 0; pass < 16; pass++) {
        std::vector<int> locs;
        for (int j = 0; j < static_cast<int>(working_df.size()); j++) {
            if (working_df[j].xd_tb == TOP || working_df[j].xd_tb == BOT) {
                locs.push_back(j);
            }
        }
        bool changed = false;
        for (size_t k = 0; k + 1 < locs.size(); k++) {
            if (locs[k + 1] - locs[k] < CHAN_MIN_BI_SPAN) {
                working_df[locs[k + 1]].xd_tb = NO_TOPBOT;
                changed = true;
                break;
            }
        }
        if (!changed) break;
    }
    cleanXdMarks(working_df);

    std::vector<StandardKLine> xd_result;
    for (const auto& kline : working_df) {
        if (kline.xd_tb != NO_TOPBOT) {
            xd_result.push_back(kline);
        }
    }
    
    marked_xd = xd_result;
}

// 查找初始方向 (匹配Python find_initial_direction的滑动窗口算法)
std::pair<int, TopBotType> ChanAnalyzer::findInitialDirectionFull(
        std::vector<StandardKLine>& working_df, TopBotType initial_status) {
    if (working_df.empty()) {
        return std::make_pair(-1, NO_TOPBOT);
    }
    
    if (initial_status != NO_TOPBOT) {
        int search_end = std::min(6, static_cast<int>(working_df.size()));
        if (initial_status == TOP) {
            int initial_loc = 0;
            double max_price = working_df[0].chan_price;
            for (int i = 1; i < search_end; i++) {
                if (float_more(working_df[i].chan_price, max_price)) {
                    max_price = working_df[i].chan_price;
                    initial_loc = i;
                }
            }
            working_df[initial_loc].xd_tb = TOP;
            return std::make_pair(initial_loc, TOP2BOT);
        } else if (initial_status == BOT) {
            int initial_loc = 0;
            double min_price = working_df[0].chan_price;
            for (int i = 1; i < search_end; i++) {
                if (float_less(working_df[i].chan_price, min_price)) {
                    min_price = working_df[i].chan_price;
                    initial_loc = i;
                }
            }
            working_df[initial_loc].xd_tb = BOT;
            return std::make_pair(initial_loc, BOT2TOP);
        }
        return std::make_pair(0, NO_TOPBOT);
    }
    
    // Python滑动窗口: 每4个连续元素检查方向
    int current_loc = 0;
    while (current_loc + 3 < static_cast<int>(working_df.size())) {
        const StandardKLine& first = working_df[current_loc];
        const StandardKLine& second = working_df[current_loc + 1];
        const StandardKLine& third = working_df[current_loc + 2];
        const StandardKLine& forth = working_df[current_loc + 3];
        
        bool found_direction = false;
        if (float_less(first.chan_price, second.chan_price)) {
            found_direction = (float_less_equal(first.chan_price, third.chan_price) && float_less(second.chan_price, forth.chan_price)) ||
                              (float_more_equal(first.chan_price, third.chan_price) && float_more(second.chan_price, forth.chan_price));
        } else {
            found_direction = (float_less(first.chan_price, third.chan_price) && float_less_equal(second.chan_price, forth.chan_price)) ||
                              (float_more(first.chan_price, third.chan_price) && float_more_equal(second.chan_price, forth.chan_price));
        }
        
        if (found_direction) {
            TopBotType initial_direction;
            if (float_less(first.chan_price, third.chan_price) || float_less(second.chan_price, forth.chan_price)) {
                initial_direction = BOT2TOP;
            } else {
                initial_direction = TOP2BOT;
            }
            // Python不在此时设置xd_tb
            return std::make_pair(current_loc, initial_direction);
        }
        current_loc++;
    }
    
    return std::make_pair(0, NO_TOPBOT);
}

// 获取前N个有效元素 (匹配Python get_previous_N_elem)
std::vector<int> ChanAnalyzer::getPreviousNElem(int loc, const std::vector<StandardKLine>& working_df, 
        int N, TopBotType end_tb, bool single_direction) {
    std::vector<int> result;
    
    for (int i = loc - 1; i >= 0; i--) {
        if (working_df[i].original_tb == NO_TOPBOT) continue;
        // end_tb不为空且还没有结果时，跳过不匹配end_tb的元素
        if (end_tb != NO_TOPBOT && result.empty() && working_df[i].original_tb != end_tb) {
            continue;
        }
        // single_direction模式下只保留end_tb类型的元素
        if (single_direction) {
            if (working_df[i].original_tb == end_tb) {
                result.insert(result.begin(), i);
            }
        } else {
            result.insert(result.begin(), i);
        }
        if (N != 0 && static_cast<int>(result.size()) >= N) break;
        // N==0时，找到首个有xd_tb标记的元素即停止
        if (N == 0 && (working_df[i].xd_tb == TOP || working_df[i].xd_tb == BOT)) break;
    }
    
    return result;
}

// 方向断言 (匹配Python direction_assert: BOT2TOP要求elem为TOP, TOP2BOT要求elem为BOT)
bool ChanAnalyzer::directionAssert(const StandardKLine& elem, TopBotType direction) {
    if (direction == BOT2TOP) {
        return elem.tb == TOP;
    } else if (direction == TOP2BOT) {
        return elem.tb == BOT;
    }
    return false;
}

// 恢复TB数据
void ChanAnalyzer::restoreTbData(std::vector<StandardKLine>& working_df, int from_idx, int to_idx) {
    for (int i = from_idx; i < to_idx && i < static_cast<int>(working_df.size()); i++) {
        if (working_df[i].original_tb != NO_TOPBOT) {
            working_df[i].tb = working_df[i].original_tb;
        }
    }
}

// 滤波去缺�?(Python filter_gap line 1001-1018)
std::vector<std::pair<double, double>> ChanAnalyzer::gapRegion(double start_date, double end_date, TopBotType gap_direction) {
    std::vector<std::pair<double, double>> result;
    
    // Python gap_region line 313-321
    for (const auto& kline : original_data) {
        if (kline.date > start_date && kline.date <= end_date) {
            if (gap_direction == NO_TOPBOT) {
                if (kline.gap != 0) {
                    result.push_back(std::make_pair(kline.gap_start, kline.gap_end));
                }
            } else if (gap_direction == TOP2BOT) {
                if (kline.gap == -1) {
                    result.push_back(std::make_pair(kline.gap_start, kline.gap_end));
                }
            } else if (gap_direction == BOT2TOP) {
                if (kline.gap == 1) {
                    result.push_back(std::make_pair(kline.gap_start, kline.gap_end));
                }
            }
        }
    }
    
    return result;
}

// 合并缺口 (Python combine_gaps line 997-1006)
std::vector<std::pair<double, double>> ChanAnalyzer::combineGaps(const std::vector<std::pair<double, double>>& gap_regions) {
    if (gap_regions.empty()) return {};
    if (gap_regions.size() <= 1) return gap_regions;
    
    // 先排序 (匹配Python: sorted(gap_regions, key=lambda tup: tup[0]))
    std::vector<std::pair<double, double>> sorted_regions = gap_regions;
    std::sort(sorted_regions.begin(), sorted_regions.end(),
              [](const std::pair<double, double>& a, const std::pair<double, double>& b) {
                  return a.first < b.first;
              });
    
    std::vector<std::pair<double, double>> new_gaps;
    std::pair<double, double> temp_range(0, 0);
    bool has_temp = false;
    
    for (size_t i = 0; i + 1 < sorted_regions.size(); i++) {
        const auto& current_range = sorted_regions[i];
        const auto& next_range = sorted_regions[i + 1];
        
        if (!has_temp) {
            // Python: temp_range is None
            if (float_more_equal(current_range.second, next_range.first)) {
                temp_range = std::make_pair(current_range.first, next_range.second);
                has_temp = true;
            } else {
                new_gaps.push_back(current_range);
                temp_range = next_range;
                has_temp = true;
            }
        } else {
            if (float_more_equal(temp_range.second, next_range.first)) {
                temp_range = std::make_pair(temp_range.first, next_range.second);
            } else {
                new_gaps.push_back(temp_range);
                temp_range = next_range;
            }
        }
    }
    
    if (has_temp) {
        new_gaps.push_back(temp_range);
    }
    
    return new_gaps;
}



// 实现缺失的函数：same_tb_remove_previous
std::tuple<int, int, int> ChanAnalyzer::same_tb_remove_previous(
    std::vector<StandardKLine>& working_df, 
    int previous_index, 
    int current_index, 
    int next_index) {
    
    // 移除前一个分�?
    working_df[previous_index].tb = NO_TOPBOT;
    
    // 回溯到更早的分型
    int new_previous_index = trace_back_index(working_df, previous_index);
    
    if (new_previous_index < 0) {
        // 没有更早的分型，使用当前分型作为前一�?
        new_previous_index = current_index;
        current_index = next_index;
        next_index = get_next_tb(next_index, working_df);
    } else {
        // 移除之前跳过的索�?
        auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), new_previous_index);
        if (it != previous_skipped_idx.end()) {
            previous_skipped_idx.erase(it);
        }
    }
    
    return std::make_tuple(new_previous_index, current_index, next_index);
}

// 实现缺失的函数：same_tb_remove_current
std::tuple<int, int, int> ChanAnalyzer::same_tb_remove_current(
    std::vector<StandardKLine>& working_df, 
    int previous_index, 
    int current_index, 
    int next_index) {
    
    // 移除当前分型
    working_df[current_index].tb = NO_TOPBOT;
    
    int temp_index = previous_index;
    current_index = previous_index;
    
    // 回溯到更早的分型
    int new_previous_index = trace_back_index(working_df, previous_index);
    
    if (new_previous_index < 0) {
        // 没有更早的分�?
        new_previous_index = temp_index;
        current_index = next_index;
        next_index = get_next_tb(next_index, working_df);
    } else {
        // 移除之前跳过的索�?
        auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), new_previous_index);
        if (it != previous_skipped_idx.end()) {
            previous_skipped_idx.erase(it);
        }
    }
    
    return std::make_tuple(new_previous_index, current_index, next_index);
}

// 实现缺失的函数：same_tb_remove_next
std::tuple<int, int, int> ChanAnalyzer::same_tb_remove_next(
    std::vector<StandardKLine>& working_df, 
    int previous_index, 
    int current_index, 
    int next_index) {
    
    // 移除下一个分�?
    working_df[next_index].tb = NO_TOPBOT;
    
    int temp_index = previous_index;
    
    // 回溯到更早的分型
    int new_previous_index = trace_back_index(working_df, previous_index);
    
    if (new_previous_index < 0) {
        // 没有更早的分�?
        new_previous_index = temp_index;
        next_index = get_next_tb(next_index, working_df);
    } else {
        // 调整索引
        next_index = current_index;
        current_index = temp_index;
        
        // 移除之前跳过的索�?
        auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), new_previous_index);
        if (it != previous_skipped_idx.end()) {
            previous_skipped_idx.erase(it);
        }
    }
    
    return std::make_tuple(new_previous_index, current_index, next_index);
}

// 实现缺失的函数：check_gap_qualify
bool ChanAnalyzer::check_gap_qualify(
    const std::vector<StandardKLine>& working_df,
    int previous_index,
    int current_index,
    int next_index) {
    
    // 检查在指定范围内是否存在缺�?(Python check_gap_qualify lines 417-443)
    if (next_index < 0 || next_index >= static_cast<int>(working_df.size()) ||
        current_index < 0 || current_index >= static_cast<int>(working_df.size())) {
        return false;
    }
    
    // Python line 421: gap exists between current and next
    if (gapExistsInDateRange(working_df[current_index].date, working_df[next_index].date)) {
        // Python line 422-424: determine gap direction
        TopBotType gap_direction = NO_TOPBOT;
        if (working_df[next_index].tb == TOP) {
            gap_direction = BOT2TOP;
        } else if (working_df[next_index].tb == BOT) {
            gap_direction = TOP2BOT;
        }
        
        if (gap_direction == NO_TOPBOT) {
            return false;
        }
        
        // Python line 425-426: get gap region
        auto gap_ranges = gapRegion(working_df[current_index].date, 
                                   working_df[next_index].date, 
                                   gap_direction);
        gap_ranges = combineGaps(gap_ranges);
        
        // Python line 427-442: check each gap
        for (const auto& gap : gap_ranges) {
            if (previous_index < 0 || previous_index >= static_cast<int>(working_df.size())) {
                return true;
            }
            
            // Python line 431-435: for TOP previous
            if (working_df[previous_index].tb == TOP) {
                bool qualify = float_less(gap.first, working_df[previous_index].low) &&
                              float_less_equal(working_df[previous_index].low, working_df[previous_index].high) &&
                              float_less(working_df[previous_index].high, gap.second);
                if (qualify) {
                    return true;
                }
            // Python line 436-440: for BOT previous
            } else if (working_df[previous_index].tb == BOT) {
                bool qualify = float_more(gap.second, working_df[previous_index].high) &&
                              float_more_equal(working_df[previous_index].high, working_df[previous_index].low) &&
                              float_more(working_df[previous_index].low, gap.first);
                if (qualify) {
                    return true;
                }
            }
        }
    }
    
    return false;
}

// 实现缺失的函数：trace_back_index
int ChanAnalyzer::trace_back_index(const std::vector<StandardKLine>& working_df, int current_index) {
    // 回溯查找前一个有效分�?(Python trace_back_index lines 249-259)
    for (int i = current_index - 1; i >= 0; i--) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            return i;
        }
    }
    return -1;  // Python returns None -> -1 in C++
}

// 实现缺失的函数：get_next_tb
int ChanAnalyzer::get_next_tb(int current_index, const std::vector<StandardKLine>& working_df) {
    // 查找下一个有效分�?(Python get_next_tb lines 323-332)
    for (int i = current_index + 1; i < static_cast<int>(working_df.size()); i++) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            return i;
        }
    }
    return static_cast<int>(working_df.size()); // 返回末尾索引
}

std::vector<Bi> ChanAnalyzer::getBi() const {
    std::vector<Bi> result;
    
    // 将连续的分型配对形成�?
    for (size_t i = 0; i + 1 < marked_bi.size(); i++) {
        const StandardKLine& start = marked_bi[i];
        const StandardKLine& end = marked_bi[i+1];
        
        // 确保分型类型交替
        if ((start.tb == BOT && end.tb == TOP) || 
            (start.tb == TOP && end.tb == BOT)) {
            
            Bi bi;
            bi.start_date = start.date;
            bi.end_date = end.date;
            bi.start_price = start.chan_price;
            bi.end_price = end.chan_price;
            bi.type = start.tb;
            bi.start_index = start.real_loc;
            bi.end_index = end.real_loc;
            
            result.push_back(bi);
        }
    }
    
    return result;
}

std::vector<XianDuan> ChanAnalyzer::getXianDuan() const {
    std::vector<XianDuan> result;
    
    // 将连续的线段分型配对形成线段
    for (size_t i = 0; i + 1 < marked_xd.size(); i++) {
        const StandardKLine& start = marked_xd[i];
        const StandardKLine& end = marked_xd[i+1];
        
        // 确保分型类型交替
        if ((start.xd_tb == BOT && end.xd_tb == TOP) || 
            (start.xd_tb == TOP && end.xd_tb == BOT)) {
            
            XianDuan xd;
            xd.start_date = start.date;
            xd.end_date = end.date;
            xd.start_price = start.chan_price;
            xd.end_price = end.chan_price;
            xd.type = start.xd_tb;
            xd.start_index = start.real_loc;
            xd.end_index = end.real_loc;
            
            result.push_back(xd);
        }
    }
    
    return result;
}
