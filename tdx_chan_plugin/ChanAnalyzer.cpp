// ChanAnalyzer.cpp - Chan Theory Analyzer Implementation
// Implementation of pen and line segment algorithm from kBar_Chan.py

#include "ChanPlugin.h"
#include <algorithm>
#include <limits>
#include <tuple>

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
            int trend = (first.tb != NO_TOPBOT) ? first.tb : isBullType(past, first);
            
            if (inclusion == FIRST_CSECOND) {
                if (trend == BOT2TOP) {
                    second.high = std::max(first.high, second.high);
                    second.low = std::max(first.low, second.low);
                } else {
                    second.high = std::min(first.high, second.high);
                    second.low = std::min(first.low, second.low);
                }
                first.high = 0;
                first.low = 0;
                
                // 存储trend供后续迭代使用 (匹配Python趋势类型存储)
                second.tb = trend;
                
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
                second.high = 0;
                second.low = 0;
                
                // 存储trend供后续迭代使用
                first.tb = trend;
                
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
        if (kline.high > 0 && kline.low > 0) {
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
        else if (second.new_index - first.new_index < 4) {
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
                        nxt.new_index - cur.new_index < 4 && !gap_qualify) {
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
                        nxt.new_index - cur.new_index < 4 && !gap_qualify) {
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
                    if (cur.new_index - prev.new_index >= 4 || gap_qualify) {
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
                    if (cur.new_index - prev.new_index >= 4 || gap_qualify) {
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
        if (cur.new_index - prev.new_index < 4) {
            // Python line 639-730: cur-next distance >= 4 OR gap_qualify
            if ((next_index < static_cast<int>(working_df.size()) && 
                 nxt.new_index - cur.new_index >= 4) || gap_qualify) {
                
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
                 nxt.new_index - cur.new_index < 4 && !gap_qualify) {
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
                  nxt.new_index - cur.new_index >= 4) || gap_qualify) {
            
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
        const FeatureSeqElement& e2, const FeatureSeqElement& e3) {
    // 缠论原文：特征序列包含处理沿线段方向合并。
    // e0.tb==TOP 表示 (TOP,BOT) 配对 = 向下笔 = 上升线段特征序列 → MAX 合并 (TOP/BOT 两侧都取 max)
    // e0.tb==BOT 表示 (BOT,TOP) 配对 = 向上笔 = 下降线段特征序列 → MIN 合并 (TOP/BOT 两侧都取 min)
    // 调用方需先经 processInclusions 对齐起点，使 e0.tb 与线段方向匹配。
    FeatureSeqElement m_top, m_bot;

    if (e0.tb == TOP) {
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
            auto [m0, m1] = mergeFeatureSeqPair(
                seq[i], seq[i+1], seq[i+2], seq[i+3]);
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

    int i = seq_pos;

    while (i + 5 < static_cast<int>(feature_seq.size())) {
        TopBotType xd_tb_type = (direction == BOT2TOP) ? TOP : BOT;
        bool prev_gap = !gap_XD.empty();

        if (feature_seq[i].tb != xd_tb_type) {
            i += 2;
            continue;
        }

        if (prev_gap) {
            // ========== GAP PATH ==========

            bool cgap = false;
            if (feature_seq[i + 2].tb == TOP) {
                cgap = float_less(feature_seq[i].orig_price,
                                  feature_seq[i + 3].orig_price);
            } else {
                cgap = float_more(feature_seq[i].orig_price,
                                  feature_seq[i + 3].orig_price);
            }

            int i1 = feature_seq[i + 1].orig_market_idx;
            int i2 = feature_seq[i + 2].orig_market_idx;
            bool kg = (i1 + 1 == i2) && kbarGapAsXdFull(working_df, i1, i2,
                feature_seq[i].orig_market_idx);

            if (feature_seq[i + 2].tb == xd_tb_type) {
                bool with_gap;
                TopBotType st = NO_TOPBOT;
                if (feature_seq[i + 2].tb == TOP) {
                    with_gap = float_less(feature_seq[i].orig_price,
                                          feature_seq[i + 3].orig_price);
                    if (float_more(feature_seq[i + 2].orig_price,
                                   feature_seq[i].orig_price) &&
                        float_more(feature_seq[i + 2].orig_price,
                                   feature_seq[i + 4].orig_price) &&
                        float_more(feature_seq[i + 3].orig_price,
                                   feature_seq[i + 5].orig_price)) {
                        st = TOP;
                    }
                } else {
                    with_gap = float_more(feature_seq[i].orig_price,
                                          feature_seq[i + 3].orig_price);
                    if (float_less(feature_seq[i + 2].orig_price,
                                   feature_seq[i].orig_price) &&
                        float_less(feature_seq[i + 2].orig_price,
                                   feature_seq[i + 4].orig_price) &&
                        float_less(feature_seq[i + 3].orig_price,
                                   feature_seq[i + 5].orig_price)) {
                        st = BOT;
                    }
                }
                if (st == xd_tb_type) {
                    int mx = feature_seq[i + 2].orig_market_idx;
                    if (cgap) {
                        gap_XD.push_back(mx);
                    } else {
                        gap_XD.clear();
                    }
                    working_df[mx].xd_tb = st;
                    TopBotType new_dir = (st == TOP) ? TOP2BOT : BOT2TOP;
                    int new_i = kg ? (i + 1) : (i + 3);
                    return {true, mx, st, cgap,
                            feature_seq[new_i].orig_market_idx,
                            new_dir, false, 0, kg};
                }
            }

            // popGap
            if (!gap_XD.empty()) {
                int pg = gap_XD.back();
                double pgp = working_df[pg].chan_price;
                bool ovr = false;

                if (direction == TOP2BOT) {
                    for (int j = i; j < i + 6 &&
                         j < static_cast<int>(feature_seq.size()); j++) {
                        if (float_more(feature_seq[j].orig_price, pgp)) {
                            ovr = true; break;
                        }
                    }
                } else {
                    for (int j = i; j < i + 6 &&
                         j < static_cast<int>(feature_seq.size()); j++) {
                        if (float_less(feature_seq[j].orig_price, pgp)) {
                            ovr = true; break;
                        }
                    }
                }

                if (ovr) {
                    gap_XD.pop_back();
                    working_df[pg].xd_tb = NO_TOPBOT;
                    int to = feature_seq[
                        std::min(i + 5,
                                 static_cast<int>(feature_seq.size()) - 1)
                    ].orig_market_idx;
                    restoreTbData(working_df, pg, to);
                    TopBotType new_dir = (direction == TOP2BOT) ? BOT2TOP : TOP2BOT;
                    return {false, 0, NO_TOPBOT, false, 0,
                            new_dir, true, pg, false};
                }
            }

            i += 2;

        } else {
            // ========== NO GAP PATH ==========

            // xdTopbotCandidate shortcut
            if (i + 4 < static_cast<int>(feature_seq.size())) {
                int cand = -1;
                if (direction == TOP2BOT) {
                    double v = feature_seq[i].orig_price;
                    int mi = 0;
                    for (int k = 2; k <= 4; k += 2) {
                        if (float_less(feature_seq[i + k].orig_price, v)) {
                            v = feature_seq[i + k].orig_price;
                            mi = k / 2;
                        }
                    }
                    if (mi > 1) cand = i + (mi - 1) * 2;
                } else {
                    double v = feature_seq[i].orig_price;
                    int mi = 0;
                    for (int k = 2; k <= 4; k += 2) {
                        if (float_more(feature_seq[i + k].orig_price, v)) {
                            v = feature_seq[i + k].orig_price;
                            mi = k / 2;
                        }
                    }
                    if (mi > 1) cand = i + (mi - 1) * 2;
                }
                if (cand >= i + 2) {
                    i = cand; continue;
                }
            }

            // Kline gap XD detection
            int i1 = feature_seq[i + 1].orig_market_idx;
            int i2 = feature_seq[i + 2].orig_market_idx;
            int i3 = feature_seq[i + 3].orig_market_idx;
            bool kg_found = false;
            TopBotType kg_result = NO_TOPBOT;

            if (!previous_with_xd_gap && i2 + 1 == i3 &&
                kbarGapAsXdFull(working_df, i2, i3, i1)) {
                kg_found = true;
                previous_with_xd_gap = true;
            }
            if (!kg_found && previous_with_xd_gap) {
                previous_with_xd_gap = false;
                if (i1 + 1 == i2 &&
                    kbarGapAsXdFull(working_df, i1, i2,
                                    feature_seq[i].orig_market_idx)) {
                    kg_found = true;
                }
            }
            if (kg_found) {
                if (direction == BOT2TOP &&
                    float_more(feature_seq[i + 2].orig_price,
                               feature_seq[i + 4].orig_price)) {
                    kg_result = TOP;
                } else if (direction == TOP2BOT &&
                           float_less(feature_seq[i + 2].orig_price,
                                      feature_seq[i + 4].orig_price)) {
                    kg_result = BOT;
                }
            }
            if (kg_found && kg_result == xd_tb_type) {
                int mx = feature_seq[i + 2].orig_market_idx;
                working_df[mx].xd_tb = kg_result;
                gap_XD.push_back(mx);
                TopBotType new_dir = (kg_result == TOP) ? TOP2BOT : BOT2TOP;
                bool kkg = (i1 + 1 == i2) &&
                    kbarGapAsXdFull(working_df, i1, i2,
                                    feature_seq[i].orig_market_idx);
                int new_i = kkg ? (i + 1) : (i + 3);
                return {true, mx, kg_result, true,
                        feature_seq[new_i].orig_market_idx,
                        new_dir, false, 0, kkg};
            }

            // Standard XD endpoint check
            if (feature_seq[i + 2].tb == xd_tb_type) {
                bool with_gap;
                TopBotType st = NO_TOPBOT;
                if (feature_seq[i + 2].tb == TOP) {
                    with_gap = float_less(feature_seq[i].orig_price,
                                          feature_seq[i + 3].orig_price);
                    if (float_more(feature_seq[i + 2].orig_price,
                                   feature_seq[i].orig_price) &&
                        float_more(feature_seq[i + 2].orig_price,
                                   feature_seq[i + 4].orig_price) &&
                        float_more(feature_seq[i + 3].orig_price,
                                   feature_seq[i + 5].orig_price)) {
                        st = TOP;
                    }
                } else {
                    with_gap = float_more(feature_seq[i].orig_price,
                                          feature_seq[i + 3].orig_price);
                    if (float_less(feature_seq[i + 2].orig_price,
                                   feature_seq[i].orig_price) &&
                        float_less(feature_seq[i + 2].orig_price,
                                   feature_seq[i + 4].orig_price) &&
                        float_less(feature_seq[i + 3].orig_price,
                                   feature_seq[i + 5].orig_price)) {
                        st = BOT;
                    }
                }

                if (st == xd_tb_type) {
                    int prev_xd = -1;
                    for (int j = feature_seq[i].orig_market_idx - 1;
                         j >= 0; j--) {
                        if (working_df[j].xd_tb == TOP ||
                            working_df[j].xd_tb == BOT) {
                            prev_xd = j; break;
                        }
                    }

                    if (prev_xd >= 0) {
                        bool invalid = false;
                        if (working_df[prev_xd].xd_tb == TOP && st == BOT &&
                            float_less(working_df[prev_xd].chan_price,
                                       feature_seq[i + 2].orig_price)) {
                            invalid = true;
                        } else if (working_df[prev_xd].xd_tb == BOT &&
                                   st == TOP &&
                                   float_more(working_df[prev_xd].chan_price,
                                              feature_seq[i + 2].orig_price)) {
                            invalid = true;
                        }
                        if (invalid) {
                            restoreTbData(working_df, prev_xd,
                                feature_seq[i + 5].orig_market_idx + 1);
                            working_df[prev_xd].xd_tb = NO_TOPBOT;
                            TopBotType new_dir = (st == TOP) ? TOP2BOT : BOT2TOP;
                            return {false, 0, NO_TOPBOT, false, 0,
                                    new_dir, true, prev_xd, false};
                        }
                    }

                    if (with_gap) {
                        gap_XD.push_back(
                            feature_seq[i + 2].orig_market_idx);
                    }

                    int mx = feature_seq[i + 2].orig_market_idx;
                    working_df[mx].xd_tb = st;
                    TopBotType new_dir = (st == TOP) ? TOP2BOT : BOT2TOP;

                    int ki1 = feature_seq[i + 1].orig_market_idx;
                    int ki2 = feature_seq[i + 2].orig_market_idx;
                    bool kg2 = (ki1 + 1 == ki2) &&
                        kbarGapAsXdFull(working_df, ki1, ki2,
                                        feature_seq[i].orig_market_idx);
                    int new_i = kg2 ? (i + 1) : (i + 3);
                    return {true, mx, st, with_gap,
                            feature_seq[new_i].orig_market_idx,
                            new_dir, false, 0, kg2};
                }
            }

            i += 2;
        }
    }

    return {false, 0, NO_TOPBOT, false, 0, NO_TOPBOT, false, 0, false};
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
        
        int seq_pos = 0;
        TopBotType target_tb = (direction == BOT2TOP) ? TOP : BOT;
        while (seq_pos < static_cast<int>(seq.size()) &&
               seq[seq_pos].tb != target_tb) {
            seq_pos++;
        }
        if (seq_pos + 5 >= static_cast<int>(seq.size())) break;
        
        auto result = findXDOnFeatureSeq(seq, working_df, seq_pos, direction, tail_start);
        
        if (result.is_rollback) {
            tail_start = result.rollback_start;
            direction = result.new_direction;
            continue;
        }
        
        if (!result.found) break;
        
        tail_start = result.next_market_start;
        if (!result.is_kg2_backstep && tail_start < result.xd_market_idx) {
            tail_start = result.xd_market_idx;
        }
        direction = result.new_direction;
    }
    
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
