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

int ChanAnalyzer::getPreviousLoc(int loc, const std::vector<StandardKLine>& working_df) {
    for (int i = loc - 1; i >= 0; i--) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            return i;
        }
    }
    return -1;
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
    
    // 第一步：确保前两根K线没有包含关系
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
        // 数据太少，直接返回
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
            int trend = (first.tb != NO_TOPBOT) ? first.tb : isBullType(past, first);
            
            if (inclusion == FIRST_CSECOND) {
                // 第一根包含第二根
                if (trend == BOT2TOP) {
                    second.high = std::max(first.high, second.high);
                    second.low = std::max(first.low, second.low);
                } else {
                    second.high = std::min(first.high, second.high);
                    second.low = std::min(first.low, second.low);
                }
                first.high = 0;
                first.low = 0;
                
                first_idx = second_idx;
                second_idx++;
            } else {
                // 第二根包含第一根
                if (trend == BOT2TOP) {
                    first.high = std::max(first.high, second.high);
                    first.low = std::max(first.low, second.low);
                } else {
                    first.high = std::min(first.high, second.high);
                    first.low = std::min(first.low, second.low);
                }
                second.high = 0;
                second.low = 0;
                
                second_idx++;
            }
        } else {
            // 无包含关系
            first_idx = second_idx;
            second_idx++;
            past_idx = first_idx - 1;
        }
    }
    
    // 清理标准化K线（移除已被合并的线，使用negative标记）
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
    
    // 处理初始状态
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
    
    // 标记第一根K线
    if (standardized[0].tb != TOP && standardized[0].tb != BOT) {
        int first_loc = getNextLoc(0, standardized);
        if (first_loc < static_cast<int>(standardized.size())) {
            TopBotType first_tb = static_cast<TopBotType>(standardized[first_loc].tb);
            standardized[0].tb = (first_tb == TOP) ? BOT : TOP;
        }
    }
    
    // 标记最后一根K线
    if (mark_last_kbar && last_idx < static_cast<int>(standardized.size())) {
        TopBotType last_tb = static_cast<TopBotType>(standardized[last_idx].tb);
        standardized.back().tb = (last_tb == TOP) ? BOT : TOP;
    }
}

// 清理前两个顶底分型 (Python clean_first_two_tb lines 334-415)
std::vector<StandardKLine> ChanAnalyzer::cleanFirstTwoTB(const std::vector<StandardKLine>& working_df) {
    std::vector<StandardKLine> result = working_df;
    
    if (result.size() < 3) return result;
    
    // Python code uses a different indexing scheme: 
    // firstIdx=0, secondIdx=firstIdx+1, thirdIdx=secondIdx+1
    // and uses get_next_loc to find NEXT valid tb after removal
    // This is fundamentally different from simple index-based iteration.
    // The working_df here has already been filtered to only tb entries.
    // But in Python, working_df is the full numpy array of standardized data,
    // filtered to non-noTopBot entries via boolean indexing on line 501.
    // Then clean_first_two_tb works on the filtered array.
    
    // The key insight: result here has contiguous tb entries (0,1,2,...)
    // Python's get_next_loc on a filtered array is just idx+1.
    
    int first_idx = 0;
    int second_idx = 1;
    int third_idx = 2;
    
    while (third_idx < static_cast<int>(result.size())) {
        StandardKLine& first = result[first_idx];
        StandardKLine& second = result[second_idx];
        StandardKLine& third = result[third_idx];
        
        // Python line 348-352: both TOP, first.high < second.high -> remove first
        if (first.tb == TOP && second.tb == TOP && float_less(first.high, second.high)) {
            first.tb = NO_TOPBOT;
            first_idx = getNextLoc(first_idx, result);
            second_idx = getNextLoc(first_idx, result);
            third_idx = getNextLoc(second_idx, result);
            continue;
        }
        // Python line 354-358: both TOP, first.high >= second.high -> remove second
        else if (first.tb == TOP && second.tb == TOP && float_more_equal(first.high, second.high)) {
            second.tb = NO_TOPBOT;
            second_idx = getNextLoc(second_idx, result);
            third_idx = getNextLoc(second_idx, result);
            continue;
        }
        // Python line 359-363: both BOT, first.low > second.low -> remove first
        else if (first.tb == BOT && second.tb == BOT && float_more(first.low, second.low)) {
            first.tb = NO_TOPBOT;
            first_idx = getNextLoc(first_idx, result);
            second_idx = getNextLoc(first_idx, result);
            third_idx = getNextLoc(second_idx, result);
            continue;
        }
        // Python line 365-369: both BOT, first.low <= second.low -> remove second
        else if (first.tb == BOT && second.tb == BOT && float_less_equal(first.low, second.low)) {
            second.tb = NO_TOPBOT;
            second_idx = getNextLoc(second_idx, result);
            third_idx = getNextLoc(second_idx, result);
            continue;
        }
        // Python line 370-395: distance < 4 between first.second
        else if (second.new_index - first.new_index < 4) {
            // Python: if first.tb == third.tb (same type)
            if (first.tb == third.tb) {
                if (first.tb == TOP) {
                    // Python 371-376: both TOP, first.high < third.high -> remove first
                    if (float_less(first.high, third.high)) {
                        first.tb = NO_TOPBOT;
                        first_idx = getNextLoc(first_idx, result);
                        second_idx = getNextLoc(first_idx, result);
                        third_idx = getNextLoc(second_idx, result);
                        continue;
                    }
                    // Python 377-381: both TOP, first.high >= third.high -> remove second
                    else {
                        second.tb = NO_TOPBOT;
                        second_idx = getNextLoc(second_idx, result);
                        third_idx = getNextLoc(second_idx, result);
                        continue;
                    }
                }
                else if (first.tb == BOT) {
                    // Python 382-386: both BOT, first.low > third.low -> remove first
                    if (float_more(first.low, third.low)) {
                        first.tb = NO_TOPBOT;
                        first_idx = getNextLoc(first_idx, result);
                        second_idx = getNextLoc(first_idx, result);
                        third_idx = getNextLoc(second_idx, result);
                        continue;
                    }
                    // Python 388-392: both BOT, first.low <= third.low -> remove second
                    else {
                        second.tb = NO_TOPBOT;
                        second_idx = getNextLoc(second_idx, result);
                        third_idx = getNextLoc(second_idx, result);
                        continue;
                    }
                }
            }
            else {
                // Python line 393-394: something wrong (first.tb != third.tb but distance < 4)
                // Just break to avoid infinite loop
                break;
            }
        }
        // Python line 397-410: overlapping TOP-BOT or BOT-TOP within 4 bars
        else if (first.tb == TOP && second.tb == BOT && float_less_equal(first.high, second.low)) {
            first.tb = NO_TOPBOT;
            second.tb = NO_TOPBOT;
            first_idx = getNextLoc(first_idx, result);
            second_idx = getNextLoc(first_idx, result);
            third_idx = getNextLoc(second_idx, result);
            continue;
        }
        else if (first.tb == BOT && second.tb == TOP && float_more_equal(first.low, second.high)) {
            first.tb = NO_TOPBOT;
            second.tb = NO_TOPBOT;
            first_idx = getNextLoc(first_idx, result);
            second_idx = getNextLoc(first_idx, result);
            third_idx = getNextLoc(second_idx, result);
            continue;
        }
        else {
            break;
        }
    }
    
    // Python line 414: filter out noTopBot entries
    std::vector<StandardKLine> cleaned;
    for (const auto& kline : result) {
        if (kline.tb == TOP || kline.tb == BOT) {
            cleaned.push_back(kline);
        }
    }
    
    return cleaned;
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
    
    // Python line 507: clean_first_two_tb
    working_df = cleanFirstTwoTB(working_df);
    
    if (working_df.size() < 2) {
        marked_bi = working_df;
        return;
    }
    
    // 重置 previous_skipped_idx
    previous_skipped_idx.clear();
    
    // Python line 510-513: 初始化三个指针
    int previous_index = 0;
    int current_index = 1;
    int next_index = 2;
    
    // Python line 514: 主循环
    while (next_index < static_cast<int>(working_df.size()) && 
           previous_index >= 0 && next_index >= 0) {
        
        StandardKLine& prev = working_df[previous_index];
        StandardKLine& cur  = working_df[current_index];
        StandardKLine& nxt  = working_df[next_index];
        
        // ===== Python line 519-569: Case A - cur.tb == prev.tb (同类型) =====
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
        
        // ===== Python line 570-633: Case B - cur.tb == nxt.tb (下一分型同类型) =====
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
        // 调试输出保留但不输出到终端
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

// 线段包含关系处理 (Python xd_inclusion line 1075-1082)
bool ChanAnalyzer::xdInclusionFull(const StandardKLine& firstElem, const StandardKLine& secondElem, 
                                    const StandardKLine& thirdElem, const StandardKLine& forthElem) {
    // 检查线段包含关系：1-3 vs 2-4 的价格交叉
    if ((float_less_equal(firstElem.chan_price, thirdElem.chan_price) && float_more_equal(secondElem.chan_price, forthElem.chan_price)) ||
        (float_more_equal(firstElem.chan_price, thirdElem.chan_price) && float_less_equal(secondElem.chan_price, forthElem.chan_price))) {
        return true;
    }
    return false;
}

// 检查当前是否有缺口 (Python check_current_gap line 1211-1224)
bool ChanAnalyzer::checkCurrentGap(const std::vector<StandardKLine>& working_df, 
                                    int idx0, int idx1, int idx2, int idx3) {
    const auto& first = working_df[idx0];
    const auto& second = working_df[idx1];
    const auto& third = working_df[idx2];
    const auto& forth = working_df[idx3];
    
    // 当第三个是顶分型时，检查 first.chan_price < forth.chan_price
    // 当第三个是底分型时，检查 first.chan_price > forth.chan_price
    if (third.tb == TOP) {
        return float_less(first.chan_price, forth.chan_price);
    } else if (third.tb == BOT) {
        return float_more(first.chan_price, forth.chan_price);
    }
    return false;
}

// K线缺口作为线段 (Python kbar_gap_as_xd line 1031-1072)
bool ChanAnalyzer::kbarGapAsXdFull(const std::vector<StandardKLine>& working_df, 
                                    int first_idx, int second_idx, int compare_idx) {
    // 仅当两个索引相邻时检查
    if (first_idx + 1 != second_idx) return false;
    
    const auto& firstElem = working_df[first_idx];
    const auto& secondElem = working_df[second_idx];
    
    // 检查范围内是否有缺口
    if (!gapExistsInRange(firstElem.date, secondElem.date)) return false;
    
    TopBotType gap_direction = NO_TOPBOT;
    if (secondElem.tb == TOP) gap_direction = BOT2TOP;
    else if (secondElem.tb == BOT) gap_direction = TOP2BOT;
    else return false;
    
    auto gap_ranges = gapRegion(firstElem.date, secondElem.date, gap_direction);
    gap_ranges = combineGaps(gap_ranges);
    
    if (gap_ranges.empty()) return false;
    
    // 获取缺口区域
    double gap_start = gap_ranges[0].first;
    double gap_end = gap_ranges[0].second;
    
    // 检查缺口是否有效 (Python line 1053-1065)
    if (compare_idx >= 0 && compare_idx < static_cast<int>(working_df.size())) {
        const auto& compare_elem = working_df[compare_idx];
        if (secondElem.tb == TOP) {
            // 对于顶分型：缺口高于比较点的低点
            return float_less(gap_start, compare_elem.low) && float_less(compare_elem.high, gap_end);
        } else if (secondElem.tb == BOT) {
            // 对于底分型：缺口低于比较点的高点
            return float_more(gap_end, compare_elem.high) && float_more(compare_elem.low, gap_start);
        }
    }
    
    return true;
}

// 检查线段包含关系是否自由 (Python is_XD_inclusion_free line 1084-1220)
std::pair<bool, bool> ChanAnalyzer::isXDInclusionFreeFull(
        TopBotType direction, const std::vector<int>& next_valid_elems, 
        std::vector<StandardKLine>& working_df) {
    if (next_valid_elems.size() < 2) {
        return std::make_pair(false, false);
    }
    
    bool free = true;
    bool has_kline_gap = false;
    
    // Python line 1095: from y = 0 to y < len(x) - 1
    // Python line 1096: from x = 0 to x < len(results)
    // This creates a triangular comparison matrix
    for (size_t i = 0; i + 1 < next_valid_elems.size(); i++) {
        int idx_i = next_valid_elems[i];
        int idx_i1 = next_valid_elems[i+1];
        
        for (size_t j = 0; j < next_valid_elems.size(); j++) {
            if (j + 1 >= next_valid_elems.size()) break;
            int idx_j = next_valid_elems[j];
            int idx_j1 = next_valid_elems[j+1];
            
            // Python line 1097-1098: xd_inclusion check
            if (xdInclusionFull(working_df[idx_i], working_df[idx_i1], 
                               working_df[idx_j], working_df[idx_j1])) {
                free = false;
                break;
            }
        }
        if (!free) break;
    }
    
    // Python line 1100-1118: Check for kline_gap_as_xd
    for (size_t i = 0; i + 4 < next_valid_elems.size(); i++) {
        if (kbarGapAsXdFull(working_df, next_valid_elems[i+1], next_valid_elems[i+2], next_valid_elems[i])) {
            has_kline_gap = true;
            break;
        }
    }
    
    return std::make_pair(free, has_kline_gap);
}

// 检查K线缺口作为线段 (Python check_kline_gap_as_xd line 1258-1297)
std::tuple<TopBotType, bool, bool> ChanAnalyzer::checkKlineGapAsXdFull(
        const std::vector<int>& next_valid_elems, TopBotType direction, 
        std::vector<StandardKLine>& working_df) {
    if (next_valid_elems.size() < 4) {
        return std::make_tuple(NO_TOPBOT, false, false);
    }
    
    TopBotType xd_gap_result = NO_TOPBOT;
    bool with_kline_gap_as_xd = false;
    
    // 检查 third-fourth 之间的缺口
    if (!previous_with_xd_gap && 
        kbarGapAsXdFull(working_df, next_valid_elems[2], next_valid_elems[3], next_valid_elems[1])) {
        with_kline_gap_as_xd = true;
        previous_with_xd_gap = true;
    }
    
    // 检查 second-third 之间的缺口（之前已有线段缺口）
    if (!with_kline_gap_as_xd && previous_with_xd_gap) {
        previous_with_xd_gap = false;
        if (kbarGapAsXdFull(working_df, next_valid_elems[1], next_valid_elems[2], next_valid_elems[0])) {
            with_kline_gap_as_xd = true;
        }
    }
    
    if (with_kline_gap_as_xd) {
        const auto& third = working_df[next_valid_elems[2]];
        const auto& fifth = (next_valid_elems.size() >= 5) ? working_df[next_valid_elems[4]] : third;
        if (direction == BOT2TOP && float_more(third.chan_price, fifth.chan_price)) {
            xd_gap_result = TOP;
        } else if (direction == TOP2BOT && float_less(third.chan_price, fifth.chan_price)) {
            xd_gap_result = BOT;
        }
    }
    
    return std::make_tuple(xd_gap_result, !with_kline_gap_as_xd, with_kline_gap_as_xd);
}

// 检查XD顶底分型 (Python check_XD_topbot line 1226-1255)
std::pair<TopBotType, bool> ChanAnalyzer::checkXDTopBotFull(
        const StandardKLine& first, const StandardKLine& second,
        const StandardKLine& third, const StandardKLine& forth,
        const StandardKLine& fifth, const StandardKLine& sixth) {
    TopBotType result = NO_TOPBOT;
    bool with_gap = false;
    
    if (third.tb == TOP) {
        with_gap = float_less(first.chan_price, forth.chan_price);
        if (float_more(third.chan_price, first.chan_price) &&
            float_more(third.chan_price, fifth.chan_price) &&
            float_more(forth.chan_price, sixth.chan_price)) {
            result = TOP;
        }
    } else if (third.tb == BOT) {
        with_gap = float_more(first.chan_price, forth.chan_price);
        if (float_less(third.chan_price, first.chan_price) &&
            float_less(third.chan_price, fifth.chan_price) &&
            float_less(forth.chan_price, sixth.chan_price)) {
            result = BOT;
        }
    }
    
    return std::make_pair(result, with_gap);
}

// 综合检查XD顶底 (Python check_XD_topbot_directed line 1321-1342)
std::tuple<TopBotType, bool, bool> ChanAnalyzer::checkXDTopBotDirectedFull(
        const std::vector<int>& next_valid_elems, TopBotType direction,
        std::vector<StandardKLine>& working_df) {
    if (next_valid_elems.size() < 6) {
        return std::make_tuple(NO_TOPBOT, false, false);
    }
    
    // 先检查K线缺口
    auto gap_result = checkKlineGapAsXdFull(next_valid_elems, direction, working_df);
    TopBotType xd_gap_result = std::get<0>(gap_result);
    bool with_current_gap = std::get<1>(gap_result);
    bool with_kline_gap_as_xd = std::get<2>(gap_result);
    
    if (with_kline_gap_as_xd && xd_gap_result != NO_TOPBOT) {
        return std::make_tuple(xd_gap_result, with_current_gap, with_kline_gap_as_xd);
    }
    
    // 检查标准XD顶底
    const auto& first = working_df[next_valid_elems[0]];
    const auto& second = working_df[next_valid_elems[1]];
    const auto& third = working_df[next_valid_elems[2]];
    const auto& forth = working_df[next_valid_elems[3]];
    const auto& fifth = working_df[next_valid_elems[4]];
    const auto& sixth = working_df[next_valid_elems[5]];
    
    auto result = checkXDTopBotFull(first, second, third, forth, fifth, sixth);
    TopBotType xd_result = result.first;
    with_current_gap = result.second;
    
    if ((xd_result == TOP && direction == BOT2TOP) || (xd_result == BOT && direction == TOP2BOT)) {
        if (with_current_gap) {
            with_current_gap = checkPreviousElemToAvoidXdGap(with_current_gap, next_valid_elems, working_df);
        }
        return std::make_tuple(xd_result, with_current_gap, with_kline_gap_as_xd);
    }
    
    return std::make_tuple(NO_TOPBOT, with_current_gap, with_kline_gap_as_xd);
}

// XD候选位置 (Python xd_topbot_candidate line 1423-1480)
int ChanAnalyzer::xdTopbotCandidateFull(const std::vector<int>& next_valid_elems, 
        TopBotType current_direction, std::vector<StandardKLine>& working_df, bool with_current_gap) {
    if (next_valid_elems.size() < 3) return -1;
    
    // 简单检查：找到极值
    std::vector<double> chan_price_list;
    for (int idx : next_valid_elems) {
        chan_price_list.push_back(working_df[idx].chan_price);
    }
    
    if (current_direction == TOP2BOT) {
        double min_val = chan_price_list[0];
        int min_idx = 0;
        for (size_t i = 1; i < chan_price_list.size(); i++) {
            if (float_less(chan_price_list[i], min_val)) {
                min_val = chan_price_list[i];
                min_idx = static_cast<int>(i);
            }
        }
        if (min_idx > 1) {
            return next_valid_elems[min_idx - 1];
        }
    } else if (current_direction == BOT2TOP) {
        double max_val = chan_price_list[0];
        int max_idx = 0;
        for (size_t i = 1; i < chan_price_list.size(); i++) {
            if (float_more(chan_price_list[i], max_val)) {
                max_val = chan_price_list[i];
                max_idx = static_cast<int>(i);
            }
        }
        if (max_idx > 1) {
            return next_valid_elems[max_idx - 1];
        }
    }
    
    // 包含关系检查
    std::vector<int> new_valid_elems;
    if (with_current_gap) {
        new_valid_elems = checkInclusionByDirectionFull(next_valid_elems[1], working_df, current_direction, 4);
    } else {
        new_valid_elems = checkInclusionByDirectionFull(next_valid_elems[1], working_df, current_direction, 6);
    }
    
    if (static_cast<int>(new_valid_elems.size()) >= 4) {
        int end_loc = new_valid_elems[3] + 1;
        if (end_loc > static_cast<int>(working_df.size())) {
            end_loc = static_cast<int>(working_df.size());
        }
        
        // Python logic: find the max/min within range
        if (current_direction == TOP2BOT) {
            double min_val = std::numeric_limits<double>::max();
            int min_data_idx = -1;
            for (int j = next_valid_elems[0]; j < end_loc; j++) {
                if (j < static_cast<int>(working_df.size())) {
                    if (float_less(working_df[j].chan_price, min_val)) {
                        min_val = working_df[j].chan_price;
                        min_data_idx = j;
                    }
                }
            }
            if (min_data_idx >= 0) {
                return new_valid_elems[0];
            }
        } else {
            double max_val = -std::numeric_limits<double>::max();
            int max_data_idx = -1;
            for (int j = next_valid_elems[0]; j < end_loc; j++) {
                if (j < static_cast<int>(working_df.size())) {
                    if (float_more(working_df[j].chan_price, max_val)) {
                        max_val = working_df[j].chan_price;
                        max_data_idx = j;
                    }
                }
            }
            if (max_data_idx >= 0) {
                return new_valid_elems[0];
            }
        }
    }
    
    return -1;
}

// popGap (Python pop_gap line 1482-1499)
std::pair<int, TopBotType> ChanAnalyzer::popGapFull(
        std::vector<StandardKLine>& working_df, 
        const std::vector<int>& next_valid_elems, TopBotType current_direction) {
    // 从可用元素中弹出缺口分段
    if (next_valid_elems.size() < 2) {
        return std::make_pair(-1, NO_TOPBOT);
    }
    
    int pop_idx = next_valid_elems[1];
    TopBotType pop_direction = (working_df[pop_idx].tb == TOP) ? BOT2TOP : TOP2BOT;
    
    return std::make_pair(pop_idx, pop_direction);
}

// 检查前一个元素以避免线段缺口 (Python check_previous_elem_to_avoid_XD_gap line 1208-1225)
bool ChanAnalyzer::checkPreviousElemToAvoidXdGap(
        bool with_gap, const std::vector<int>& next_valid_elems, 
        std::vector<StandardKLine>& working_df) {
    if (!with_gap || next_valid_elems.size() < 4) return with_gap;
    
    // 检查前一个元素是否会因为缺口导致无效
    const auto& first = working_df[next_valid_elems[0]];
    const auto& forth = working_df[next_valid_elems[3]];
    
    // 如果第三个是顶分型且 first.chan_price >= forth.chan_price，则没有缺口
    if (working_df[next_valid_elems[2]].tb == TOP && 
        float_more_equal(first.chan_price, forth.chan_price)) {
        return false;
    }
    
    // 如果第三个是底分型且 first.chan_price <= forth.chan_price，则没有缺口
    if (working_df[next_valid_elems[2]].tb == BOT && 
        float_less_equal(first.chan_price, forth.chan_price)) {
        return false;
    }
    
    return with_gap;
}

// XD定义函数 (基于Python defineXD逻辑)
void ChanAnalyzer::defineXD(int initial_state) {
    if (marked_bi.empty()) return;
    
    // 使用marked_bi作为working_df
    std::vector<StandardKLine> working_df = marked_bi;
    
    // 确保所有marked_bi都有正确的chan_price
    for (auto& kline : working_df) {
        if (kline.chan_price == 0) {
            kline.chan_price = (kline.tb == TOP) ? kline.high : kline.low;
        }
    }
    
    // 调用Full版本进行线段定义
    std::pair<int, TopBotType> initial = findInitialDirectionFull(working_df, static_cast<TopBotType>(initial_state));
    int initial_loc = initial.first;
    TopBotType initial_direction = initial.second;
    
    if (initial_loc < 0 || initial_loc >= static_cast<int>(working_df.size())) {
        return;
    }
    
    // 设置初始xd_tb
    if (initial_state != NO_TOPBOT) {
        working_df[initial_loc].xd_tb = initial_state;
    }
    
    // 开始查找线段
    std::vector<StandardKLine> xd_result;
    int current_idx = initial_loc;
    
    while (current_idx < static_cast<int>(working_df.size())) {
        std::vector<StandardKLine> found_xd = findXDFull(current_idx, initial_direction, working_df);
        
        if (!found_xd.empty()) {
            // 添加找到的线段元素
            for (const auto& kline : found_xd) {
                if (kline.xd_tb != NO_TOPBOT) {
                    xd_result.push_back(kline);
                }
            }
            
            // 更新当前位置
            if (!found_xd.empty()) {
                int last_idx = found_xd.back().new_index;
                for (current_idx = 0; current_idx < static_cast<int>(working_df.size()); current_idx++) {
                    if (working_df[current_idx].new_index >= last_idx) {
                        break;
                    }
                }
            }
            
            // 切换方向
            initial_direction = (initial_direction == BOT2TOP) ? TOP2BOT : BOT2TOP;
        } else {
            current_idx++;
        }
    }
    
    marked_xd = xd_result;
}

// 查找初始方向 (Python find_initial_direction line 957-995)
std::pair<int, TopBotType> ChanAnalyzer::findInitialDirectionFull(
        std::vector<StandardKLine>& working_df, TopBotType initial_status) {
    if (working_df.empty()) {
        return std::make_pair(-1, NO_TOPBOT);
    }
    
    if (initial_status != NO_TOPBOT) {
        // Python line 961-968: 根据初始状态在前6个元素中找极值
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
    
    // Python line 973-994: 无初始状态时，通过检查前4个元素确定方向
    int current_loc = 0;
    TopBotType initial_direction = NO_TOPBOT;
    int initial_loc = 0;
    
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
            initial_direction = (float_less(first.chan_price, third.chan_price) || float_less(second.chan_price, forth.chan_price)) ? BOT2TOP : TOP2BOT;
            initial_loc = current_loc;
            break;
        } else {
            current_loc++;
        }
    }
    
    return std::make_pair(initial_loc, initial_direction);
}

// 查找线段 (Python find_XD line 1423-1540)
std::vector<StandardKLine> ChanAnalyzer::findXDFull(
        int initial_i, TopBotType initial_direction, 
        std::vector<StandardKLine>& working_df) {
    std::vector<StandardKLine> result;
    if (initial_i < 0 || initial_i >= static_cast<int>(working_df.size()) || initial_direction == NO_TOPBOT) {
        return result;
    }
    
    int current_idx = initial_i;
    TopBotType current_direction = initial_direction;
    
    while (current_idx < static_cast<int>(working_df.size())) {
        // Python line 1465-1517: 检查方向一致性，找齐6个元素
        std::vector<int> next_valid_elems = getNextNElem(current_idx, working_df, 6, current_direction, true);
        
        if (static_cast<int>(next_valid_elems.size()) < 6) {
            // Python line 1470: 不够6个时尝试更少的
            next_valid_elems = getNextNElem(current_idx, working_df, 4, current_direction, true);
            
            if (static_cast<int>(next_valid_elems.size()) >= 4) {
                // Python line 1476-1496: 检查4个元素是否构成XD
                auto [xd_type, with_gap, with_kline_gap] = checkXDTopBotDirectedFull(next_valid_elems, current_direction, working_df);
                
                if (xd_type != NO_TOPBOT) {
                    // Python line 1497: XD found
                    working_df[next_valid_elems[2]].xd_tb = xd_type;
                    result.push_back(working_df[next_valid_elems[2]]);
                    break;
                }
            }
            
            // Python line 1502: 找到极值位置
            int candidate = xdTopbotCandidateFull(next_valid_elems, current_direction, working_df, false);
            if (candidate >= 0) {
                current_idx = candidate;
                continue;
            }
            break;
        }
        
        // Python line 1465-1517: 主循环 - 检查方向一致性和XD顶底
        // 先检查前4个是否满足包含关系自由
        std::vector<int> first4(next_valid_elems.begin(), next_valid_elems.begin() + 4);
        auto [is_free, has_kline_gap] = isXDInclusionFreeFull(current_direction, first4, working_df);
        
        if (has_kline_gap) {
            // Python line 1505-1517: 有K线缺口，处理并继续
            auto [xd_type, with_gap, with_kline_gap_flag] = checkXDTopBotDirectedFull(next_valid_elems, current_direction, working_df);
            
            if (xd_type != NO_TOPBOT) {
                working_df[next_valid_elems[2]].xd_tb = xd_type;
                result.push_back(working_df[next_valid_elems[2]]);
                break;
            }
            
            // 弹出处理
            auto [pop_idx, pop_direction] = popGapFull(working_df, next_valid_elems, current_direction);
            if (pop_idx >= 0) {
                current_idx = pop_idx;
                current_direction = pop_direction;
                continue;
            }
            break;
        }
        
        if (is_free) {
            // Python line 1534-1537: 包含关系自由，检查XD顶底
            auto [xd_type, with_gap, with_kline_gap_flag] = checkXDTopBotDirectedFull(next_valid_elems, current_direction, working_df);
            
            if (xd_type != NO_TOPBOT) {
                working_df[next_valid_elems[2]].xd_tb = xd_type;
                result.push_back(working_df[next_valid_elems[2]]);
                break;
            }
            
            // Python line 1541-1546: 检查后4个
            std::vector<int> last4(next_valid_elems.begin() + 2, next_valid_elems.end());
            auto [is_free2, has_kline_gap2] = isXDInclusionFreeFull(current_direction, last4, working_df);
            
            if (has_kline_gap2) {
                auto [pop_idx, pop_direction] = popGapFull(working_df, next_valid_elems, current_direction);
                if (pop_idx >= 0) {
                    current_idx = pop_idx;
                    current_direction = pop_direction;
                    continue;
                }
                break;
            }
            
            if (is_free2) {
                auto [xd_type2, with_gap2, with_kline_gap_flag2] = checkXDTopBotDirectedFull(next_valid_elems, current_direction, working_df);
                
                if (xd_type2 != NO_TOPBOT) {
                    working_df[next_valid_elems[2]].xd_tb = xd_type2;
                    result.push_back(working_df[next_valid_elems[2]]);
                    break;
                }
            }
            
            // Python line 1580: 使用候选位置
            int candidate = xdTopbotCandidateFull(next_valid_elems, current_direction, working_df, false);
            if (candidate >= 0) {
                current_idx = candidate;
                continue;
            }
        }
        
        // 移动到一个新位置
        if (!next_valid_elems.empty()) {
            current_idx = next_valid_elems[0] + 1;
        } else {
            current_idx++;
        }
    }
    
    return result;
}

// 按方向检查包含关系 (Python check_inclusion_by_direction line 1002-1029)
std::vector<int> ChanAnalyzer::checkInclusionByDirectionFull(
        int current_loc, std::vector<StandardKLine>& working_df, 
        TopBotType direction, int count_num) {
    std::vector<int> next_valid_elems;
    int i = current_loc;
    
    while (i < static_cast<int>(working_df.size()) && 
           static_cast<int>(next_valid_elems.size()) < count_num) {
        if (working_df[i].tb != NO_TOPBOT) {
            next_valid_elems.push_back(i);
        }
        i++;
    }
    
    if (static_cast<int>(next_valid_elems.size()) < count_num) return next_valid_elems;
    
    // 检查包含关系
    i = current_loc;
    while (static_cast<int>(next_valid_elems.size()) < count_num * 2) { // 最多尝试到初始数量的两倍
        if (i >= static_cast<int>(working_df.size())) break;
        
        if (working_df[i].tb == NO_TOPBOT) {
            i++;
            continue;
        }
        
        next_valid_elems.push_back(i);
        
        if (count_num == 4) {
            if (static_cast<int>(next_valid_elems.size()) >= 4) {
                bool is_free, has_kline_gap;
                std::tie(is_free, has_kline_gap) = isXDInclusionFreeFull(direction, next_valid_elems, working_df);
                if (is_free) break;
            }
        } else if (count_num == 6) {
            if (static_cast<int>(next_valid_elems.size()) >= 6) {
                std::vector<int> first4(next_valid_elems.begin(), next_valid_elems.begin() + 4);
                bool is_free, has_kline_gap;
                std::tie(is_free, has_kline_gap) = isXDInclusionFreeFull(direction, first4, working_df);
                if (has_kline_gap) break;
                if (is_free) {
                    std::vector<int> last4(next_valid_elems.begin() + 2, next_valid_elems.end());
                    std::tie(is_free, has_kline_gap) = isXDInclusionFreeFull(direction, last4, working_df);
                    if (is_free) break;
                }
            }
        } else { // count_num == 8
            if (static_cast<int>(next_valid_elems.size()) >= 8) {
                std::vector<int> first4(next_valid_elems.begin(), next_valid_elems.begin() + 4);
                bool is_free, has_kline_gap;
                std::tie(is_free, has_kline_gap) = isXDInclusionFreeFull(direction, first4, working_df);
                if (has_kline_gap) break;
                if (is_free) {
                    std::vector<int> mid4(next_valid_elems.begin() + 2, next_valid_elems.begin() + 6);
                    std::tie(is_free, has_kline_gap) = isXDInclusionFreeFull(direction, mid4, working_df);
                    if (has_kline_gap) break;
                    if (is_free) {
                        std::vector<int> last4(next_valid_elems.begin() + 4, next_valid_elems.end());
                        std::tie(is_free, has_kline_gap) = isXDInclusionFreeFull(direction, last4, working_df);
                        if (is_free) break;
                    }
                }
            }
        }
        i++;
    }
    return next_valid_elems;
}

// 确保方向一致性地获取N个元素
std::vector<int> ChanAnalyzer::getNextNElem(int loc, const std::vector<StandardKLine>& working_df, 
        int N, TopBotType start_tb, bool single_direction) {
    std::vector<int> result;
    
    TopBotType last_tb = start_tb;
    for (int i = loc; i < static_cast<int>(working_df.size()); i++) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            if (single_direction && last_tb != NO_TOPBOT) {
                // 检查方向是否一致
                if (last_tb == TOP && working_df[i].tb == BOT) continue;
                if (last_tb == BOT && working_df[i].tb == TOP) continue;
            }
            result.push_back(i);
            last_tb = static_cast<TopBotType>(working_df[i].tb);
            if (static_cast<int>(result.size()) >= N) break;
        }
    }
    
    return result;
}

// 获取前N个有效元素
std::vector<int> ChanAnalyzer::getPreviousNElem(int loc, const std::vector<StandardKLine>& working_df, 
        int N, TopBotType end_tb, bool single_direction) {
    std::vector<int> result;
    
    TopBotType last_tb = end_tb;
    for (int i = loc - 1; i >= 0; i--) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            if (single_direction && last_tb != NO_TOPBOT) {
                if (last_tb == TOP && working_df[i].tb == BOT) continue;
                if (last_tb == BOT && working_df[i].tb == TOP) continue;
            }
            result.push_back(i);
            last_tb = static_cast<TopBotType>(working_df[i].tb);
            if (static_cast<int>(result.size()) >= N) break;
        }
    }
    
    std::reverse(result.begin(), result.end());
    return result;
}

// 方向断言
bool ChanAnalyzer::directionAssert(const StandardKLine& elem, TopBotType direction) {
    if (direction == BOT2TOP) {
        return elem.tb == BOT;
    } else if (direction == TOP2BOT) {
        return elem.tb == TOP;
    }
    return false;
}

// 恢复TB数据
void ChanAnalyzer::restoreTbData(std::vector<StandardKLine>& working_df, int from_idx, int to_idx) {
    for (int i = from_idx; i <= to_idx && i < static_cast<int>(working_df.size()); i++) {
        if (working_df[i].original_tb != NO_TOPBOT) {
            working_df[i].tb = working_df[i].original_tb;
        }
    }
}

// 滤波去缺口 (Python filter_gap line 1001-1018)
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
    
    std::vector<std::pair<double, double>> combined;
    combined.push_back(gap_regions[0]);
    
    for (size_t i = 1; i < gap_regions.size(); i++) {
        auto& last = combined.back();
        const auto& current = gap_regions[i];
        
        // 如果有重叠或相邻，合并
        if (float_less_equal(last.second, current.first)) {
            last.second = current.second;
        } else {
            combined.push_back(current);
        }
    }
    
    return combined;
}

// K线缺口作为线段 (原始版本)
bool ChanAnalyzer::kbarGapAsXd(const std::vector<StandardKLine>& working_df, 
                                int first_idx, int second_idx, int compare_idx) {
    return kbarGapAsXdFull(working_df, first_idx, second_idx, compare_idx);
}

// XD包含关系 (原始版本)
bool ChanAnalyzer::xdInclusion(const StandardKLine& first, const StandardKLine& second, 
                                const StandardKLine& third, const StandardKLine& forth) {
    return xdInclusionFull(first, second, third, forth);
}

// 检查XD包含关系是否自由 (原始版本)
std::pair<bool, bool> ChanAnalyzer::isXDInclusionFree(TopBotType direction, 
        const std::vector<int>& next_valid_elems, std::vector<StandardKLine>& working_df) {
    return isXDInclusionFreeFull(direction, next_valid_elems, working_df);
}

// 按方向检查包含关系 (原始版本)
std::vector<int> ChanAnalyzer::checkInclusionByDirection(int current_loc, 
        std::vector<StandardKLine>& working_df, TopBotType direction, int count_num) {
    return checkInclusionByDirectionFull(current_loc, working_df, direction, count_num);
}

// XD候选位置 (原始版本)
int ChanAnalyzer::xdTopbotCandidate(const std::vector<int>& next_valid_elems, 
        TopBotType current_direction, std::vector<StandardKLine>& working_df, bool with_current_gap) {
    return xdTopbotCandidateFull(next_valid_elems, current_direction, working_df, with_current_gap);
}

// popGap (原始版本)
std::pair<int, TopBotType> ChanAnalyzer::popGap(std::vector<StandardKLine>& working_df, 
        const std::vector<int>& next_valid_elems, TopBotType current_direction) {
    return popGapFull(working_df, next_valid_elems, current_direction);
}

// K线缺口作为线段 (Full版本)
std::tuple<TopBotType, bool, bool> ChanAnalyzer::checkKlineGapAsXd(
        const std::vector<int>& next_valid_elems, TopBotType direction, 
        std::vector<StandardKLine>& working_df) {
    return checkKlineGapAsXdFull(next_valid_elems, direction, working_df);
}

// 检查XD顶底 (原始版本)
std::pair<TopBotType, bool> ChanAnalyzer::checkXDTopBot(const StandardKLine& first, const StandardKLine& second,
        const StandardKLine& third, const StandardKLine& forth,
        const StandardKLine& fifth, const StandardKLine& sixth) {
    return checkXDTopBotFull(first, second, third, forth, fifth, sixth);
}

// XD顶底方向 (原始版本)
std::tuple<TopBotType, bool, bool> ChanAnalyzer::checkXDTopBotDirected(
        const std::vector<int>& next_valid_elems, TopBotType direction, 
        std::vector<StandardKLine>& working_df) {
    return checkXDTopBotDirectedFull(next_valid_elems, direction, working_df);
}

// 查找XD (原始版本)
std::vector<StandardKLine> ChanAnalyzer::findXD(int initial_i, TopBotType initial_direction, 
        std::vector<StandardKLine>& working_df) {
    return findXDFull(initial_i, initial_direction, working_df);
}

// 增强的线段定义函数
void ChanAnalyzer::defineXDEnhanced(int initial_state) {
    // 直接调用主版本
    defineXD(initial_state);
}

// 查找初始方向
TopBotType ChanAnalyzer::findInitialDirection(const std::vector<StandardKLine>& working_df, TopBotType initial_status) {
    if (working_df.empty()) {
        return initial_status;
    }
    
    if (initial_status != NO_TOPBOT) {
        return initial_status;
    }
    
    // 根据第一个分型确定方向
    if (working_df[0].tb == BOT) {
        return BOT2TOP;
    } else if (working_df[0].tb == TOP) {
        return TOP2BOT;
    }
    
    // 如果没有分型，尝试根据前两个分型确定方向
    if (working_df.size() >= 2) {
        if (working_df[0].chan_price < working_df[1].chan_price) {
            return BOT2TOP;
        } else {
            return TOP2BOT;
        }
    }
    
    // 默认返回上升方向
    return BOT2TOP;
}

// 实现缺失的函数：same_tb_remove_previous
std::tuple<int, int, int> ChanAnalyzer::same_tb_remove_previous(
    std::vector<StandardKLine>& working_df, 
    int previous_index, 
    int current_index, 
    int next_index) {
    
    // 移除前一个分型
    working_df[previous_index].tb = NO_TOPBOT;
    
    // 回溯到更早的分型
    int new_previous_index = trace_back_index(working_df, previous_index);
    
    if (new_previous_index < 0) {
        // 没有更早的分型，使用当前分型作为前一个
        new_previous_index = current_index;
        current_index = next_index;
        next_index = get_next_tb(next_index, working_df);
    } else {
        // 移除之前跳过的索引
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
        // 没有更早的分型
        new_previous_index = temp_index;
        current_index = next_index;
        next_index = get_next_tb(next_index, working_df);
    } else {
        // 移除之前跳过的索引
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
    
    // 移除下一个分型
    working_df[next_index].tb = NO_TOPBOT;
    
    int temp_index = previous_index;
    
    // 回溯到更早的分型
    int new_previous_index = trace_back_index(working_df, previous_index);
    
    if (new_previous_index < 0) {
        // 没有更早的分型
        new_previous_index = temp_index;
        next_index = get_next_tb(next_index, working_df);
    } else {
        // 调整索引
        next_index = current_index;
        current_index = temp_index;
        
        // 移除之前跳过的索引
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
    
    // 检查在指定范围内是否存在缺口 (Python check_gap_qualify lines 417-443)
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
    // 回溯查找前一个有效分型 (Python trace_back_index lines 249-259)
    for (int i = current_index - 1; i >= 0; i--) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            return i;
        }
    }
    return -1;  // Python returns None -> -1 in C++
}

// 实现缺失的函数：get_next_tb
int ChanAnalyzer::get_next_tb(int current_index, const std::vector<StandardKLine>& working_df) {
    // 查找下一个有效分型 (Python get_next_tb lines 323-332)
    for (int i = current_index + 1; i < static_cast<int>(working_df.size()); i++) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            return i;
        }
    }
    return static_cast<int>(working_df.size()); // 返回末尾索引
}

std::vector<Bi> ChanAnalyzer::getBi() const {
    std::vector<Bi> result;
    
    // 将连续的分型配对形成笔
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