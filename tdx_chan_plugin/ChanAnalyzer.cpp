// ChanAnalyzer.cpp - 缠论分析器实现
// 实现 kBar_Chan.py 中的笔和线段算法

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
    
    // 步骤1: 检测缺口
    detectGaps();
    
    // 步骤2: 标准化处理
    standardize();
    
    // 步骤3: 标记顶底分型
    markTopBot();
    
    // 步骤4: 定义笔
    defineBi();
    
    // 步骤5: 定义线段
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

std::vector<StandardKLine> ChanAnalyzer::cleanFirstTwoTB(const std::vector<StandardKLine>& working_df) {
    std::vector<StandardKLine> result = working_df;
    
    if (result.size() < 3) return result;
    
    int first_idx = 0;
    int second_idx = 1;
    int third_idx = 2;
    
    while (third_idx < static_cast<int>(result.size())) {
        StandardKLine& first = result[first_idx];
        StandardKLine& second = result[second_idx];
        StandardKLine& third = result[third_idx];
        
        // 处理两个相邻的同类型分型
        if (first.tb == second.tb) {
            if (first.tb == TOP) {
                if (float_less(first.high, second.high)) {
                    first.tb = NO_TOPBOT;
                    first_idx = getNextLoc(first_idx, result);
                } else {
                    second.tb = NO_TOPBOT;
                    second_idx = getNextLoc(second_idx, result);
                }
            } else if (first.tb == BOT) {
                if (float_more(first.low, second.low)) {
                    first.tb = NO_TOPBOT;
                    first_idx = getNextLoc(first_idx, result);
                } else {
                    second.tb = NO_TOPBOT;
                    second_idx = getNextLoc(second_idx, result);
                }
            }
        } else if (second.new_index - first.new_index < 4) {
            // 分型之间距离太近
            if (first.tb == third.tb) {
                if (first.tb == TOP) {
                    if (float_less(first.high, third.high)) {
                        first.tb = NO_TOPBOT;
                        first_idx = getNextLoc(first_idx, result);
                    } else {
                        second.tb = NO_TOPBOT;
                        second_idx = getNextLoc(second_idx, result);
                    }
                } else if (first.tb == BOT) {
                    if (float_more(first.low, third.low)) {
                        first.tb = NO_TOPBOT;
                        first_idx = getNextLoc(first_idx, result);
                    } else {
                        second.tb = NO_TOPBOT;
                        second_idx = getNextLoc(second_idx, result);
                    }
                }
            }
        } else if ((first.tb == TOP && second.tb == BOT && float_less_equal(first.high, second.low)) ||
                   (first.tb == BOT && second.tb == TOP && float_more_equal(first.low, second.high))) {
            // 无效的分型组合
            first.tb = NO_TOPBOT;
            second.tb = NO_TOPBOT;
            first_idx = getNextLoc(first_idx, result);
            second_idx = getNextLoc(first_idx, result);
        } else {
            break;
        }
        
        third_idx = getNextLoc(second_idx, result);
    }
    
    // 移除无效分型
    std::vector<StandardKLine> cleaned;
    for (const auto& kline : result) {
        if (kline.tb == TOP || kline.tb == BOT) {
            cleaned.push_back(kline);
        }
    }
    
    return cleaned;
}

void ChanAnalyzer::defineBi() {
    if (standardized.empty()) return;
    
    // 注意: detectGaps() 已在 analyze() 中调用，此处无需重复调用
    
    // 创建工作副本 - 只包含有分型的K线
    std::vector<StandardKLine> working_df;
    for (const auto& kline : standardized) {
        if (kline.tb == TOP || kline.tb == BOT) {
            working_df.push_back(kline);
        }
    }
    
    if (working_df.size() < 3) {
        marked_bi = working_df;
        return;
    }
    
    // 清理前两个分型
    working_df = cleanFirstTwoTB(working_df);
    
    if (working_df.size() < 3) {
        marked_bi = working_df;
        return;
    }
    
    // 完整笔定义算法 - 实现Python版本的核心逻辑
    int previous_index = 0;
    int current_index = 1;
    int next_index = 2;
    
    while (next_index < static_cast<int>(working_df.size()) && 
           previous_index >= 0 && next_index >= 0) {
        
        StandardKLine& previous = working_df[previous_index];
        StandardKLine& current = working_df[current_index];
        StandardKLine& next = working_df[next_index];
        
        // 检查缺口资格 (Python defineBi line 635)
        bool gap_qualify = check_gap_qualify(working_df, previous_index, current_index, next_index);
        
        // 处理相同类型的相邻分型 (Python defineBi line 519-569)
        if (current.tb == previous.tb) {
            if (current.tb == TOP) {
                if (float_less(current.high, previous.high)) {
                    // 当前顶分型低于前一个顶分型，移除当前
                    std::tie(previous_index, current_index, next_index) = 
                        same_tb_remove_current(working_df, previous_index, current_index, next_index);
                } else if (float_more(current.high, previous.high)) {
                    // 当前顶分型高于前一个顶分型，移除前一个
                    std::tie(previous_index, current_index, next_index) = 
                        same_tb_remove_previous(working_df, previous_index, current_index, next_index);
                } else {
                    // 相等情况，检查缺口资格 (Python line 531-543)
                    if (working_df[next_index].new_index - working_df[current_index].new_index < 4 && !gap_qualify) {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_current(working_df, previous_index, current_index, next_index);
                    } else {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_previous(working_df, previous_index, current_index, next_index);
                    }
                }
                continue;
            } else if (current.tb == BOT) {
                if (float_more(current.low, previous.low)) {
                    // 当前底分型高于前一个底分型，移除当前
                    std::tie(previous_index, current_index, next_index) = 
                        same_tb_remove_current(working_df, previous_index, current_index, next_index);
                } else if (float_less(current.low, previous.low)) {
                    // 当前底分型低于前一个底分型，移除前一个
                    std::tie(previous_index, current_index, next_index) = 
                        same_tb_remove_previous(working_df, previous_index, current_index, next_index);
                } else {
                    // 相等情况 (Python line 556-568)
                    if (working_df[next_index].new_index - working_df[current_index].new_index < 4 && !gap_qualify) {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_current(working_df, previous_index, current_index, next_index);
                    } else {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_previous(working_df, previous_index, current_index, next_index);
                    }
                }
                continue;
            }
        } else if (current.tb == next.tb) {
            // current和next是相同类型 (Python line 570-633)
            if (current.tb == TOP) {
                if (float_less(current.high, next.high)) {
                    std::tie(previous_index, current_index, next_index) = 
                        same_tb_remove_current(working_df, previous_index, current_index, next_index);
                } else if (float_more(current.high, next.high)) {
                    std::tie(previous_index, current_index, next_index) = 
                        same_tb_remove_next(working_df, previous_index, current_index, next_index);
                } else {
                    // 相等情况 (Python line 583-601)
                    int pre_pre_index = trace_back_index(working_df, previous_index);
                    if (pre_pre_index < 0) {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_current(working_df, previous_index, current_index, next_index);
                        continue;
                    }
                    bool pre_gap_qualify = check_gap_qualify(working_df, pre_pre_index, previous_index, current_index);
                    if (working_df[current_index].new_index - working_df[previous_index].new_index >= 4 || pre_gap_qualify) {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_next(working_df, previous_index, current_index, next_index);
                    } else {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_current(working_df, previous_index, current_index, next_index);
                    }
                }
                continue;
            } else if (current.tb == BOT) {
                if (float_more(current.low, next.low)) {
                    std::tie(previous_index, current_index, next_index) = 
                        same_tb_remove_current(working_df, previous_index, current_index, next_index);
                } else if (float_less(current.low, next.low)) {
                    std::tie(previous_index, current_index, next_index) = 
                        same_tb_remove_next(working_df, previous_index, current_index, next_index);
                } else {
                    // 相等情况 (Python line 614-632)
                    int pre_pre_index = trace_back_index(working_df, previous_index);
                    if (pre_pre_index < 0) {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_current(working_df, previous_index, current_index, next_index);
                        continue;
                    }
                    bool pre_gap_qualify = check_gap_qualify(working_df, pre_pre_index, previous_index, current_index);
                    if (working_df[current_index].new_index - working_df[previous_index].new_index >= 4 || pre_gap_qualify) {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_next(working_df, previous_index, current_index, next_index);
                    } else {
                        std::tie(previous_index, current_index, next_index) = 
                            same_tb_remove_current(working_df, previous_index, current_index, next_index);
                    }
                }
                continue;
            }
        }
        
        // Python line 635-759: 检查距离和缺口资格
        if (current.new_index - previous.new_index < 4) {
            // 距离不足4根K线 (Python line 636-744)
            // 检查next和current之间距离以及缺口资格
            bool next_gap_qualify = gap_qualify;  // 已在上面计算
            if ((next.new_index - current.new_index) >= 4 || next_gap_qualify) {
                // Python line 640-730: 需要更复杂的判断
                int pre_pre_index = trace_back_index(working_df, previous_index);
                
                // 检查pre_pre和previous之间的缺口资格
                bool pre_pre_gap_qualify = false;
                if (pre_pre_index >= 0) {
                    pre_pre_gap_qualify = check_gap_qualify(working_df, pre_pre_index, previous_index, current_index);
                }
                
                if (pre_pre_gap_qualify) {
                    // previous和current之间的笔有效，继续
                    // fall through to confirm
                } else if (current.tb == BOT && previous.tb == TOP && next.tb == TOP) {
                    // Python line 646-687: 顶-底-顶 结构
                    if (float_more_equal(previous.high, next.high)) {
                        // 需要检查pre_pre
                        if (pre_pre_index < 0) {
                            working_df[current_index].tb = NO_TOPBOT;
                            current_index = next_index;
                            next_index = get_next_tb(next_index, working_df);
                            continue;
                        }
                        if (pre_pre_index >= 0 && working_df[pre_pre_index].low >= current.low) {
                            working_df[pre_pre_index].tb = NO_TOPBOT;
                            int temp_idx = trace_back_index(working_df, pre_pre_index);
                            if (temp_idx < 0) {
                                working_df[current_index].tb = NO_TOPBOT;
                                current_index = next_index;
                                next_index = get_next_tb(next_index, working_df);
                            } else {
                                next_index = current_index;
                                current_index = previous_index;
                                previous_index = temp_idx;
                                auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                if (it != previous_skipped_idx.end()) {
                                    previous_skipped_idx.erase(it);
                                }
                            }
                            continue;
                        } else {
                            working_df[current_index].tb = NO_TOPBOT;
                            current_index = previous_index;
                            previous_index = trace_back_index(working_df, previous_index);
                            if (previous_index >= 0) {
                                auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                if (it != previous_skipped_idx.end()) {
                                    previous_skipped_idx.erase(it);
                                }
                            }
                            continue;
                        }
                    } else {
                        // previous.high < next.high
                        working_df[previous_index].tb = NO_TOPBOT;
                        previous_index = trace_back_index(working_df, previous_index);
                        if (previous_index >= 0) {
                            auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                            if (it != previous_skipped_idx.end()) {
                                previous_skipped_idx.erase(it);
                            }
                        }
                        continue;
                    }
                } else if (current.tb == TOP && previous.tb == BOT && next.tb == BOT) {
                    // Python line 689-730: 底-顶-底 结构
                    if (float_less(previous.low, next.low)) {
                        if (pre_pre_index < 0) {
                            working_df[current_index].tb = NO_TOPBOT;
                            current_index = next_index;
                            next_index = get_next_tb(next_index, working_df);
                            continue;
                        }
                        if (pre_pre_index >= 0 && working_df[pre_pre_index].high <= current.high) {
                            working_df[pre_pre_index].tb = NO_TOPBOT;
                            int temp_idx = trace_back_index(working_df, pre_pre_index);
                            if (temp_idx < 0) {
                                working_df[current_index].tb = NO_TOPBOT;
                                current_index = next_index;
                                next_index = get_next_tb(next_index, working_df);
                            } else {
                                next_index = current_index;
                                current_index = previous_index;
                                previous_index = temp_idx;
                                auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                if (it != previous_skipped_idx.end()) {
                                    previous_skipped_idx.erase(it);
                                }
                            }
                            continue;
                        } else {
                            working_df[current_index].tb = NO_TOPBOT;
                            current_index = previous_index;
                            previous_index = trace_back_index(working_df, previous_index);
                            if (previous_index >= 0) {
                                auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                                if (it != previous_skipped_idx.end()) {
                                    previous_skipped_idx.erase(it);
                                }
                            }
                            continue;
                        }
                    } else {
                        // previous.low >= next.low
                        working_df[previous_index].tb = NO_TOPBOT;
                        previous_index = trace_back_index(working_df, previous_index);
                        if (previous_index >= 0) {
                            auto it = std::find(previous_skipped_idx.begin(), previous_skipped_idx.end(), previous_index);
                            if (it != previous_skipped_idx.end()) {
                                previous_skipped_idx.erase(it);
                            }
                        }
                        continue;
                    }
                }
            } else {
                // next和current距离也不足4 (Python line 731-744)
                int temp_index = get_next_tb(next_index, working_df);
                if (temp_index >= static_cast<int>(working_df.size())) {
                    // 到达末尾，需要处理
                    // 简化处理：移除最后一个
                    working_df[next_index].tb = NO_TOPBOT;
                    next_index = current_index;
                    current_index = previous_index;
                    previous_index = trace_back_index(working_df, previous_index);
                    continue;
                } else {
                    // 标记索引以便回溯
                    previous_skipped_idx.push_back(previous_index);
                    previous_index = current_index;
                    current_index = next_index;
                    next_index = temp_index;
                    continue;
                }
            }
        } else if ((next.new_index - current.new_index) < 4 && !gap_qualify) {
            // current和previous距离足够，但next和current不足 (Python line 746-759)
            int temp_index = get_next_tb(next_index, working_df);
            if (temp_index >= static_cast<int>(working_df.size())) {
                // 到达末尾
                working_df[next_index].tb = NO_TOPBOT;
                next_index = current_index;
                current_index = previous_index;
                previous_index = trace_back_index(working_df, previous_index);
                continue;
            } else {
                previous_skipped_idx.push_back(previous_index);
                previous_index = current_index;
                current_index = next_index;
                next_index = temp_index;
                continue;
            }
        }
        
        // 确认笔有效后的额外检查 (Python line 760-788)
        if (current.tb == TOP && next.tb == BOT) {
            if (float_less_equal(current.high, next.high)) {
                working_df[current_index].tb = NO_TOPBOT;
                current_index = next_index;
                next_index = get_next_tb(next_index, working_df);
                continue;
            }
            if (float_more_equal(current.low, next.low)) {
                working_df[next_index].tb = NO_TOPBOT;
                next_index = get_next_tb(next_index, working_df);
                continue;
            }
        } else if (current.tb == BOT && next.tb == TOP) {
            if (float_more_equal(current.low, next.low)) {
                working_df[current_index].tb = NO_TOPBOT;
                current_index = next_index;
                next_index = get_next_tb(next_index, working_df);
                continue;
            }
            if (float_less_equal(current.high, next.high)) {
                working_df[next_index].tb = NO_TOPBOT;
                next_index = get_next_tb(next_index, working_df);
                continue;
            }
        }
        
        // 处理跳过的索引 (Python line 790-796)
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
        
        // 确认笔，移动到下一个
        previous_index = current_index;
        current_index = next_index;
        next_index = get_next_tb(next_index, working_df);
    }
    
    // 处理末尾情况 (Python line 804-826)
    if (next_index >= static_cast<int>(working_df.size()) && 
        current_index < static_cast<int>(working_df.size()) &&
        previous_index >= 0) {
        // 检查最后一根K线
        double last_high = 0, last_low = 999999;
        for (const auto& k : original_data) {
            if (k.high > last_high) last_high = k.high;
            if (k.low < last_low) last_low = k.low;
        }
        
        if (working_df[current_index].tb == TOP && float_more(last_high, working_df[current_index].high)) {
            working_df.back().tb = TOP;
            working_df[current_index].tb = NO_TOPBOT;
        } else if (working_df[current_index].tb == BOT && float_less(last_low, working_df[current_index].low)) {
            working_df.back().tb = BOT;
            working_df[current_index].tb = NO_TOPBOT;
        }
        
        if (working_df[current_index].tb == NO_TOPBOT && previous_index >= 0) {
            if (working_df[previous_index].tb == TOP && float_more(last_high, working_df[previous_index].high)) {
                working_df.back().tb = TOP;
                working_df[previous_index].tb = NO_TOPBOT;
            } else if (working_df[previous_index].tb == BOT && float_less(last_low, working_df[previous_index].low)) {
                working_df.back().tb = BOT;
                working_df[previous_index].tb = NO_TOPBOT;
            }
        }
        
        // 如果previous和current是相同类型，保留更高的顶或更低的底
        if (previous_index >= 0 && current_index < static_cast<int>(working_df.size()) &&
            working_df[previous_index].tb == working_df[current_index].tb) {
            if (working_df[current_index].tb == TOP) {
                if (float_more(working_df[current_index].high, working_df[previous_index].high)) {
                    working_df[previous_index].tb = NO_TOPBOT;
                } else {
                    working_df[current_index].tb = NO_TOPBOT;
                }
            } else if (working_df[current_index].tb == BOT) {
                if (float_less(working_df[current_index].low, working_df[previous_index].low)) {
                    working_df[previous_index].tb = NO_TOPBOT;
                } else {
                    working_df[current_index].tb = NO_TOPBOT;
                }
            }
        }
    }
    
    // 清理无效分型
    std::vector<StandardKLine> valid_bi;
    for (const auto& kline : working_df) {
        if (kline.tb == TOP || kline.tb == BOT) {
            valid_bi.push_back(kline);
        }
    }
    
    // 设置chan_price
    for (auto& bi : valid_bi) {
        if (bi.tb == TOP) {
            bi.chan_price = bi.high;
        } else if (bi.tb == BOT) {
            bi.chan_price = bi.low;
        }
        bi.original_tb = bi.tb;
    }
    
    marked_bi = valid_bi;
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
    
    auto regions = gapRegion(firstElem.date, secondElem.date, gap_direction);
    regions = combineGaps(regions);
    if (regions.empty()) return false;
    
    // 计算缺口范围总和
    double gap_range = 0;
    for (const auto& r : regions) {
        gap_range += (r.second - r.first);
    }
    
    double price_diff = std::abs(firstElem.chan_price - secondElem.chan_price);
    if (price_diff < MIN_PRICE_UNIT) return false;
    
    // 缺口范围占价格差的比例 >= 黄金分割比
    bool gap_range_in_portion = float_more_equal(gap_range / price_diff, GOLDEN_RATIO);
    
    bool item_price_covered = false;
    if (compare_idx < 0) {
        item_price_covered = true;
    } else if (compare_idx >= static_cast<int>(working_df.size())) {
        item_price_covered = true;
    } else {
        const auto& compareElem = working_df[compare_idx];
        if (gap_direction == TOP2BOT) {
            item_price_covered = float_less_equal(regions[0].first, compareElem.chan_price);
        } else if (gap_direction == BOT2TOP) {
            item_price_covered = float_more_equal(regions.back().second, compareElem.chan_price);
        }
    }
    
    return gap_range_in_portion && item_price_covered;
}

// 线段包含关系处理并返回是否无包含、是否有K线缺口线段 (Python is_XD_inclusion_free line 1084-1159)
std::pair<bool, bool> ChanAnalyzer::isXDInclusionFreeFull(TopBotType direction, 
        const std::vector<int>& next_valid_elems, std::vector<StandardKLine>& working_df) {
    if (next_valid_elems.size() < 4) {
        return std::make_pair(false, false);
    }
    
    const auto& firstElem = working_df[next_valid_elems[0]];
    const auto& secondElem = working_df[next_valid_elems[1]];
    const auto& thirdElem = working_df[next_valid_elems[2]];
    const auto& forthElem = working_df[next_valid_elems[3]];
    
    // 根据方向验证tb
    if (direction == TOP2BOT) {
        if (!(firstElem.tb == BOT && thirdElem.tb == BOT && secondElem.tb == TOP && forthElem.tb == TOP)) {
            return std::make_pair(false, false);
        }
    } else if (direction == BOT2TOP) {
        if (!(firstElem.tb == TOP && thirdElem.tb == TOP && secondElem.tb == BOT && forthElem.tb == BOT)) {
            return std::make_pair(false, false);
        }
    }
    
    if (xdInclusionFull(firstElem, secondElem, thirdElem, forthElem)) {
        // 检查是否有K线缺口可以忽略包含
        if (kbarGapAsXdFull(working_df, next_valid_elems[0], next_valid_elems[1], -1) ||
            kbarGapAsXdFull(working_df, next_valid_elems[2], next_valid_elems[3], -1) ||
            kbarGapAsXdFull(working_df, next_valid_elems[1], next_valid_elems[2], -1)) {
            return std::make_pair(true, true); // 有缺口，忽略包含
        }
        
        // 处理包含关系 - 移除哪两个取决于方向和价格
        if (direction == TOP2BOT) {
            if (float_less(firstElem.chan_price, thirdElem.chan_price)) {
                working_df[next_valid_elems[1]].tb = NO_TOPBOT;
                working_df[next_valid_elems[2]].tb = NO_TOPBOT;
            } else {
                working_df[next_valid_elems[0]].tb = NO_TOPBOT;
                working_df[next_valid_elems[3]].tb = NO_TOPBOT;
            }
        } else { // BOT2TOP
            if (float_more(firstElem.chan_price, thirdElem.chan_price)) {
                working_df[next_valid_elems[1]].tb = NO_TOPBOT;
                working_df[next_valid_elems[2]].tb = NO_TOPBOT;
            } else {
                working_df[next_valid_elems[0]].tb = NO_TOPBOT;
                working_df[next_valid_elems[3]].tb = NO_TOPBOT;
            }
        }
        return std::make_pair(false, false); // 有包含，已处理
    }
    
    return std::make_pair(true, false); // 无包含
}

// 按方向检查包含 (Python check_inclusion_by_direction line 1162-1208)
std::vector<int> ChanAnalyzer::checkInclusionByDirectionFull(int current_loc, 
        std::vector<StandardKLine>& working_df, TopBotType direction, int count_num) {
    std::vector<int> next_valid_elems;
    int i = current_loc;
    bool first_run = true;
    
    while (first_run || (i + count_num - 1 < static_cast<int>(working_df.size()))) {
        first_run = false;
        next_valid_elems.clear();
        
        // 获取下一个count_num个元素
        int loc = i;
        while (loc < static_cast<int>(working_df.size()) && 
               static_cast<int>(next_valid_elems.size()) < count_num) {
            if (working_df[loc].tb != NO_TOPBOT) {
                next_valid_elems.push_back(loc);
            }
            loc++;
        }
        
        if (static_cast<int>(next_valid_elems.size()) < count_num) break;
        
        if (count_num == 4) {
            bool is_free, has_kline_gap;
            std::tie(is_free, has_kline_gap) = isXDInclusionFreeFull(direction, next_valid_elems, working_df);
            if (is_free) break;
        } else if (count_num == 6) {
            std::vector<int> first4(next_valid_elems.begin(), next_valid_elems.begin() + 4);
            bool is_free, has_kline_gap;
            std::tie(is_free, has_kline_gap) = isXDInclusionFreeFull(direction, first4, working_df);
            if (has_kline_gap) break;
            if (is_free) {
                std::vector<int> last4(next_valid_elems.begin() + 2, next_valid_elems.end());
                std::tie(is_free, has_kline_gap) = isXDInclusionFreeFull(direction, last4, working_df);
                if (is_free) break;
            }
        } else { // count_num == 8
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
        i++;
    }
    return next_valid_elems;
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
        
        // 找受影响的价格范围
        double min_price = working_df[new_valid_elems[0]].chan_price;
        double max_price = working_df[new_valid_elems[0]].chan_price;
        for (int i = new_valid_elems[0]; i < end_loc; i++) {
            if (float_less(working_df[i].chan_price, min_price)) min_price = working_df[i].chan_price;
            if (float_more(working_df[i].chan_price, max_price)) max_price = working_df[i].chan_price;
        }
        
        int result_idx = -1;
        if (current_direction == TOP2BOT) {
            if (float_less(min_price, working_df[next_valid_elems[1]].chan_price)) {
                result_idx = next_valid_elems[1];
            }
        } else {
            if (float_more(max_price, working_df[next_valid_elems[1]].chan_price)) {
                result_idx = next_valid_elems[1];
            }
        }
        
        if (result_idx >= 0) {
            restoreTbData(working_df, next_valid_elems[1], new_valid_elems.back());
        }
        return result_idx;
    }
    
    return -1;
}

// 弹出缺口 (Python pop_gap line 1491-1531)
std::pair<int, TopBotType> ChanAnalyzer::popGapFull(std::vector<StandardKLine>& working_df, 
        const std::vector<int>& next_valid_elems, TopBotType current_direction) {
    if (gap_XD.empty() || next_valid_elems.empty()) {
        return std::make_pair(-1, NO_TOPBOT);
    }
    
    int prev_gap_idx = gap_XD.back();
    if (prev_gap_idx < 0 || prev_gap_idx >= static_cast<int>(working_df.size())) {
        return std::make_pair(-1, NO_TOPBOT);
    }
    
    const auto& prev_gap_elem = working_df[prev_gap_idx];
    
    // 检查范围内的价格
    int start = next_valid_elems.front();
    int end = next_valid_elems.back();
    if (start < 0 || end >= static_cast<int>(working_df.size())) {
        return std::make_pair(-1, NO_TOPBOT);
    }
    
    if (current_direction == TOP2BOT) {
        double max_price = working_df[start].chan_price;
        for (int i = start; i <= end; i++) {
            if (float_more(working_df[i].chan_price, max_price)) {
                max_price = working_df[i].chan_price;
            }
        }
        if (float_more(max_price, prev_gap_elem.chan_price)) {
            int popped = gap_XD.back();
            gap_XD.pop_back();
            working_df[popped].xd_tb = NO_TOPBOT;
            restoreTbData(working_df, popped, next_valid_elems.back());
            current_direction = (current_direction == TOP2BOT) ? BOT2TOP : TOP2BOT;
            return std::make_pair(popped, current_direction);
        }
    } else if (current_direction == BOT2TOP) {
        double min_price = working_df[start].chan_price;
        for (int i = start; i <= end; i++) {
            if (float_less(working_df[i].chan_price, min_price)) {
                min_price = working_df[i].chan_price;
            }
        }
        if (float_less(min_price, prev_gap_elem.chan_price)) {
            int popped = gap_XD.back();
            gap_XD.pop_back();
            working_df[popped].xd_tb = NO_TOPBOT;
            restoreTbData(working_df, popped, next_valid_elems.back());
            current_direction = (current_direction == BOT2TOP) ? TOP2BOT : BOT2TOP;
            return std::make_pair(popped, current_direction);
        }
    }
    
    return std::make_pair(-1, current_direction);
}

// 完整线段定义 - 实现Python find_XD (line 1533-1785)
std::vector<StandardKLine> ChanAnalyzer::findXDFull(int initial_i, TopBotType initial_direction, 
        std::vector<StandardKLine>& working_df) {
    if (initial_i < 0 || initial_i >= static_cast<int>(working_df.size())) {
        return working_df;
    }
    
    TopBotType current_direction = initial_direction;
    int i = initial_i;
    
    while (i + 5 < static_cast<int>(working_df.size())) {
        bool previous_gap = !gap_XD.empty();
        
        if (previous_gap) {
            // 有之前的缺口：做包含检查
            std::vector<int> next_valid_elems = checkInclusionByDirectionFull(i, working_df, current_direction, 4);
            if (static_cast<int>(next_valid_elems.size()) < 4) break;
            
            // 方向断言
            const auto& first_elem = working_df[next_valid_elems[0]];
            bool direction_ok = (current_direction == BOT2TOP && first_elem.tb == TOP) ||
                                (current_direction == TOP2BOT && first_elem.tb == BOT);
            if (!direction_ok) {
                if (static_cast<int>(next_valid_elems.size()) > 1) {
                    i = next_valid_elems[1];
                } else {
                    i++;
                }
                continue;
            }
            
            // 检查当前缺口
            bool current_gap = checkCurrentGap(working_df, next_valid_elems[0], next_valid_elems[1],
                                                next_valid_elems[2], next_valid_elems[3]);
            
            // 根据缺口情况获取更多元素
            if (current_gap) {
                next_valid_elems = checkInclusionByDirectionFull(next_valid_elems[0], working_df, current_direction, 6);
            } else {
                next_valid_elems = checkInclusionByDirectionFull(next_valid_elems[0], working_df, current_direction, 8);
            }
            
            if (static_cast<int>(next_valid_elems.size()) < 6) break;
            
            // 检查XD顶底
            auto result = checkXDTopBotDirectedFull(next_valid_elems, current_direction, working_df);
            TopBotType current_status = std::get<0>(result);
            bool with_current_gap = std::get<1>(result);
            bool with_kline_gap_as_xd = std::get<2>(result);
            
            if (current_status != NO_TOPBOT) {
                if (with_current_gap) {
                    gap_XD.push_back(next_valid_elems[2]);
                } else {
                    gap_XD.clear();
                }
                working_df[next_valid_elems[2]].xd_tb = current_status;
                current_direction = (current_status == TOP) ? TOP2BOT : BOT2TOP;
                i = with_kline_gap_as_xd ? next_valid_elems[1] : next_valid_elems[3];
                continue;
            } else {
                auto pop_result = popGapFull(working_df, next_valid_elems, current_direction);
                if (pop_result.first >= 0) {
                    i = pop_result.first;
                    current_direction = pop_result.second;
                    continue;
                }
                i = next_valid_elems[2];
            }
        } else {
            // 无之前的缺口
            // 获取下4个元素
            std::vector<int> next_elems;
            int loc = i;
            while (loc < static_cast<int>(working_df.size()) && static_cast<int>(next_elems.size()) < 4) {
                if (working_df[loc].tb != NO_TOPBOT) next_elems.push_back(loc);
                loc++;
            }
            if (static_cast<int>(next_elems.size()) < 4) break;
            
            // 检查当前缺口
            bool current_gap = checkCurrentGap(working_df, next_elems[0], next_elems[1],
                                                next_elems[2], next_elems[3]);
            
            // 获取同方向的3个元素
            TopBotType start_tb = (current_direction == BOT2TOP) ? TOP : BOT;
            std::vector<int> next_single_elems;
            loc = i;
            while (loc < static_cast<int>(working_df.size()) && static_cast<int>(next_single_elems.size()) < 3) {
                if (working_df[loc].tb == start_tb) {
                    next_single_elems.push_back(loc);
                }
                loc++;
            }
            
            if (static_cast<int>(next_single_elems.size()) < 3) {
                i++;
                continue;
            }
            
            // 方向断言
            bool direction_ok = (current_direction == BOT2TOP && working_df[next_single_elems[0]].tb == TOP) ||
                                (current_direction == TOP2BOT && working_df[next_single_elems[0]].tb == BOT);
            if (!direction_ok) {
                i = next_elems[1];
                continue;
            }
            
            // 候选位置检查
            int possible_idx = xdTopbotCandidateFull(next_single_elems, current_direction, working_df, current_gap);
            if (possible_idx >= 0) {
                i = possible_idx;
                continue;
            }
            
            // 获取下6个元素
            std::vector<int> next_valid_elems;
            loc = next_single_elems[0];
            while (loc < static_cast<int>(working_df.size()) && static_cast<int>(next_valid_elems.size()) < 6) {
                if (working_df[loc].tb != NO_TOPBOT) next_valid_elems.push_back(loc);
                loc++;
            }
            if (static_cast<int>(next_valid_elems.size()) < 6) break;
            
            // 检查XD顶底
            auto result = checkXDTopBotDirectedFull(next_valid_elems, current_direction, working_df);
            TopBotType current_status = std::get<0>(result);
            bool with_current_gap = std::get<1>(result);
            bool with_kline_gap_as_xd = std::get<2>(result);
            
            if (current_status != NO_TOPBOT) {
                // 检查前一个线段分型
                TopBotType reverse_tb = (current_status == TOP) ? BOT : TOP;
                std::vector<int> prev_elems;
                int ploc = next_valid_elems[0] - 1;
                while (ploc >= 0) {
                    if (working_df[ploc].original_tb == reverse_tb || working_df[ploc].tb == reverse_tb) {
                        if (!prev_elems.empty() || true) {
                            prev_elems.insert(prev_elems.begin(), ploc);
                            if (working_df[ploc].xd_tb == reverse_tb) break;
                        } else {
                            prev_elems.insert(prev_elems.begin(), ploc);
                        }
                    }
                    ploc--;
                }
                
                if (!prev_elems.empty()) {
                    int prev_xd_idx = -1;
                    for (int idx : prev_elems) {
                        if (working_df[idx].xd_tb == reverse_tb) {
                            prev_xd_idx = idx;
                            break;
                        }
                    }
                    
                    if (prev_xd_idx >= 0) {
                        bool invalid = false;
                        if (working_df[prev_xd_idx].xd_tb == TOP && current_status == BOT) {
                            if (float_less(working_df[prev_xd_idx].chan_price, working_df[next_valid_elems[2]].chan_price)) {
                                invalid = true;
                            }
                        } else if (working_df[prev_xd_idx].xd_tb == BOT && current_status == TOP) {
                            if (float_more(working_df[prev_xd_idx].chan_price, working_df[next_valid_elems[2]].chan_price)) {
                                invalid = true;
                            }
                        }
                        
                        if (invalid) {
                            restoreTbData(working_df, prev_xd_idx, next_valid_elems.back());
                            working_df[prev_xd_idx].xd_tb = NO_TOPBOT;
                            current_direction = (current_status == TOP) ? TOP2BOT : BOT2TOP;
                            i = prev_xd_idx;
                            continue;
                        }
                    }
                }
                
                if (with_current_gap) {
                    gap_XD.push_back(next_valid_elems[2]);
                }
                
                working_df[next_valid_elems[2]].xd_tb = current_status;
                current_direction = (current_status == TOP) ? TOP2BOT : BOT2TOP;
                i = with_kline_gap_as_xd ? next_valid_elems[1] : next_valid_elems[3];
                continue;
            } else {
                i = next_valid_elems[2];
            }
        }
    }
    
    // 处理末尾 (Python line 1687-1783)
    // 获取最后一个已确认的线段分型
    std::vector<int> prev_xd_locs;
    for (int idx = static_cast<int>(working_df.size()) - 1; idx >= 0; idx--) {
        if (working_df[idx].xd_tb == TOP || working_df[idx].xd_tb == BOT) {
            prev_xd_locs.push_back(idx);
            if (static_cast<int>(prev_xd_locs.size()) >= 2) break;
        }
    }
    
    if (!prev_xd_locs.empty()) {
        int prev_xd_loc = prev_xd_locs[0];
        int working_xd_loc = prev_xd_loc + 3;
        
        if (working_xd_loc < static_cast<int>(working_df.size())) {
            // 获取剩余的分型
            std::vector<int> remaining;
            for (int idx = working_xd_loc; idx < static_cast<int>(working_df.size()); idx++) {
                if (working_df[idx].tb != NO_TOPBOT) {
                    remaining.push_back(idx);
                }
            }
            
            if (!remaining.empty()) {
                // 处理缺口情况
                if (!gap_XD.empty()) {
                    if (current_direction == TOP2BOT) {
                        int max_loc = remaining[0];
                        for (int idx : remaining) {
                            if (float_more(working_df[idx].chan_price, working_df[max_loc].chan_price)) {
                                max_loc = idx;
                            }
                        }
                        if (float_more(working_df[max_loc].chan_price, working_df[prev_xd_loc].chan_price)) {
                            working_df[prev_xd_loc].xd_tb = NO_TOPBOT;
                            working_df[max_loc].xd_tb = TOP;
                        }
                    } else if (current_direction == BOT2TOP) {
                        int min_loc = remaining[0];
                        for (int idx : remaining) {
                            if (float_less(working_df[idx].chan_price, working_df[min_loc].chan_price)) {
                                min_loc = idx;
                            }
                        }
                        if (float_less(working_df[min_loc].chan_price, working_df[prev_xd_loc].chan_price)) {
                            working_df[prev_xd_loc].xd_tb = NO_TOPBOT;
                            working_df[min_loc].xd_tb = BOT;
                        }
                    }
                }
                
                // 假设当前线段结束
                double max_price = working_df[remaining[0]].chan_price;
                double min_price = working_df[remaining[0]].chan_price;
                for (int idx : remaining) {
                    if (float_more(working_df[idx].chan_price, max_price)) max_price = working_df[idx].chan_price;
                    if (float_less(working_df[idx].chan_price, min_price)) min_price = working_df[idx].chan_price;
                }
                
                if (current_direction == TOP2BOT) {
                    if (float_more(working_df[prev_xd_loc].chan_price, max_price)) {
                        // 前一个顶是最高，假设末尾底是线段底
                        int min_loc = remaining[0];
                        for (int idx : remaining) {
                            if (float_less(working_df[idx].chan_price, working_df[min_loc].chan_price)) {
                                min_loc = idx;
                            }
                        }
                        working_df[min_loc].xd_tb = BOT;
                    } else if (float_less(working_df[prev_xd_loc].chan_price, max_price)) {
                        // 找到更高的顶
                        int max_loc = remaining[0];
                        for (int idx : remaining) {
                            if (float_more(working_df[idx].chan_price, working_df[max_loc].chan_price)) {
                                max_loc = idx;
                            }
                        }
                        working_df[max_loc].xd_tb = TOP;
                        working_df[prev_xd_loc].xd_tb = NO_TOPBOT;
                    }
                } else if (current_direction == BOT2TOP) {
                    if (float_less(working_df[prev_xd_loc].chan_price, min_price)) {
                        int max_loc = remaining[0];
                        for (int idx : remaining) {
                            if (float_more(working_df[idx].chan_price, working_df[max_loc].chan_price)) {
                                max_loc = idx;
                            }
                        }
                        working_df[max_loc].xd_tb = TOP;
                    } else if (float_more(working_df[prev_xd_loc].chan_price, min_price)) {
                        int min_loc = remaining[0];
                        for (int idx : remaining) {
                            if (float_less(working_df[idx].chan_price, working_df[min_loc].chan_price)) {
                                min_loc = idx;
                            }
                        }
                        working_df[min_loc].xd_tb = BOT;
                        working_df[prev_xd_loc].xd_tb = NO_TOPBOT;
                    }
                }
            }
        }
    }
    
    return working_df;
}

// 查找初始方向 (Python find_initial_direction line 957-995)
std::pair<int, TopBotType> ChanAnalyzer::findInitialDirectionFull(
        std::vector<StandardKLine>& working_df, TopBotType initial_status) {
    int initial_loc = 0;
    TopBotType initial_direction = NO_TOPBOT;
    
    if (initial_status != NO_TOPBOT) {
        // 查找前6个元素中的极值
        int search_end = std::min(6, static_cast<int>(working_df.size()));
        if (initial_status == TOP) {
            double max_price = working_df[0].chan_price;
            for (int i = 1; i < search_end; i++) {
                if (float_more(working_df[i].chan_price, max_price)) {
                    max_price = working_df[i].chan_price;
                    initial_loc = i;
                }
            }
        } else {
            double min_price = working_df[0].chan_price;
            for (int i = 1; i < search_end; i++) {
                if (float_less(working_df[i].chan_price, min_price)) {
                    min_price = working_df[i].chan_price;
                    initial_loc = i;
                }
            }
        }
        working_df[initial_loc].xd_tb = initial_status;
        initial_direction = (initial_status == TOP) ? TOP2BOT : BOT2TOP;
    } else {
        // 自动检测方向
        int current_loc = 0;
        while (current_loc + 3 < static_cast<int>(working_df.size())) {
            const auto& first = working_df[current_loc];
            const auto& second = working_df[current_loc + 1];
            const auto& third = working_df[current_loc + 2];
            const auto& forth = working_df[current_loc + 3];
            
            bool found_direction = false;
            if (float_less(first.chan_price, second.chan_price)) {
                found_direction = (float_less_equal(first.chan_price, third.chan_price) && float_less(second.chan_price, forth.chan_price)) ||
                                  (float_more_equal(first.chan_price, third.chan_price) && float_more(second.chan_price, forth.chan_price));
            } else {
                found_direction = (float_less(first.chan_price, third.chan_price) && float_less_equal(second.chan_price, forth.chan_price)) ||
                                  (float_more(first.chan_price, third.chan_price) && float_more_equal(second.chan_price, forth.chan_price));
            }
            
            if (found_direction) {
                initial_direction = (float_less(first.chan_price, third.chan_price) || float_less(second.chan_price, forth.chan_price)) 
                                    ? BOT2TOP : TOP2BOT;
                initial_loc = current_loc;
                break;
            }
            current_loc++;
        }
    }
    
    return std::make_pair(initial_loc, initial_direction);
}

// 完整线段定义 - 替代简化版
void ChanAnalyzer::defineXD(int initial_state) {
    if (marked_bi.empty()) return;
    
    // 工作副本 - 添加 original_tb 和 xd_tb 字段
    std::vector<StandardKLine> working_df = marked_bi;
    for (auto& kline : working_df) {
        kline.original_tb = kline.tb;
        kline.xd_tb = NO_TOPBOT;
    }
    
    if (working_df.size() == 0) {
        marked_xd = working_df;
        return;
    }
    
    // 清除缺口状态
    gap_XD.clear();
    previous_skipped_idx.clear();
    previous_with_xd_gap = false;
    
    // 查找初始方向
    auto init_result = findInitialDirectionFull(working_df, static_cast<TopBotType>(initial_state));
    int initial_i = init_result.first;
    TopBotType initial_direction = init_result.second;
    
    // 执行完整线段查找
    working_df = findXDFull(initial_i, initial_direction, working_df);
    
    // 过滤出有xd_tb的分型
    std::vector<StandardKLine> valid_xd;
    for (const auto& kline : working_df) {
        if (kline.xd_tb == TOP || kline.xd_tb == BOT) {
            valid_xd.push_back(kline);
        }
    }
    
    marked_xd = valid_xd;
}

std::vector<Bi> ChanAnalyzer::getBi() const {
    std::vector<Bi> result;
    
    // 将连续的顶底分型配对形成笔
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
            bi.start_index = start.new_index;
            bi.end_index = end.new_index;
            
            result.push_back(bi);
        }
    }
    
    return result;
}

// 按方向检查包含关系
std::vector<int> ChanAnalyzer::checkInclusionByDirection(int current_loc, std::vector<StandardKLine>& working_df, TopBotType direction, int count_num) {
    std::vector<int> result;
    
    if (current_loc >= static_cast<int>(working_df.size()) || count_num <= 0) {
        return result;
    }
    
    // 根据方向查找后续的分型
    int loc = current_loc;
    while (result.size() < static_cast<size_t>(count_num) && loc < static_cast<int>(working_df.size())) {
        if (working_df[loc].tb == TOP || working_df[loc].tb == BOT) {
            if (directionAssert(working_df[loc], direction)) {
                result.push_back(loc);
            }
        }
        loc++;
    }
    
    // 如果没有找到足够的分型，尝试查找下一个分型（不考虑方向）
    if (result.size() < static_cast<size_t>(count_num)) {
        result.clear();
        loc = current_loc;
        while (result.size() < static_cast<size_t>(count_num) && loc < static_cast<int>(working_df.size())) {
            if (working_df[loc].tb == TOP || working_df[loc].tb == BOT) {
                result.push_back(loc);
            }
            loc++;
        }
    }
    
    return result;
}

// 方向断言检查
bool ChanAnalyzer::directionAssert(const StandardKLine& elem, TopBotType direction) {
    if (direction == TOP2BOT) {
        return elem.tb == TOP;
    } else if (direction == BOT2TOP) {
        return elem.tb == BOT;
    }
    return true; // 对于NO_TOPBOT，接受任何方向
}

// 获取后续N个元素
std::vector<int> ChanAnalyzer::getNextNElem(int loc, const std::vector<StandardKLine>& working_df, int N, TopBotType start_tb, bool single_direction) {
    std::vector<int> result;
    
    if (loc >= static_cast<int>(working_df.size()) || N <= 0) {
        return result;
    }
    
    int i = loc;
    while (i < static_cast<int>(working_df.size()) && static_cast<int>(result.size()) < N) {
        const StandardKLine& current = working_df[i];
        
        if (current.tb != NO_TOPBOT) {
            if (start_tb != NO_TOPBOT && result.empty() && current.tb != start_tb) {
                i++;
                continue;
            }
            
            if (single_direction && start_tb != NO_TOPBOT && current.tb != start_tb) {
                i++;
                continue;
            }
            
            result.push_back(i);
        }
        i++;
    }
    
    return result;
}

// 获取前N个元素
std::vector<int> ChanAnalyzer::getPreviousNElem(int loc, const std::vector<StandardKLine>& working_df, int N, TopBotType end_tb, bool single_direction) {
    std::vector<int> result;
    
    if (loc <= 0 || N < 0) {
        return result;
    }
    
    int i = loc - 1;
    while (i >= 0 && (N == 0 || static_cast<int>(result.size()) < N)) {
        const StandardKLine& current = working_df[i];
        
        if (current.original_tb != NO_TOPBOT) {
            if (end_tb != NO_TOPBOT && result.empty() && current.original_tb != end_tb) {
                i--;
                continue;
            }
            
            if (single_direction) {
                if (current.original_tb == end_tb) {
                    result.insert(result.begin(), i);
                }
            } else {
                result.insert(result.begin(), i);
            }
            
            if (N == 0 && (current.xd_tb == TOP || current.xd_tb == BOT)) {
                break;
            }
        }
        i--;
    }
    
    return result;
}

// 恢复分型数据
void ChanAnalyzer::restoreTbData(std::vector<StandardKLine>& working_df, int from_idx, int to_idx) {
    if (from_idx >= static_cast<int>(working_df.size()) || to_idx >= static_cast<int>(working_df.size()) || from_idx > to_idx) {
        return;
    }
    
    for (int i = from_idx; i <= to_idx && i < static_cast<int>(working_df.size()); i++) {
        working_df[i].tb = working_df[i].original_tb;
    }
    
    if (is_debug) {
        // 简化调试输出
        // 实际实现中可以添加详细的调试信息
    }
}

// 线段顶底分型检查
std::pair<TopBotType, bool> ChanAnalyzer::checkXDTopBot(const StandardKLine& first, const StandardKLine& second, const StandardKLine& third, 
                                                       const StandardKLine& fourth, const StandardKLine& fifth, const StandardKLine& sixth) {
    // 检查上升线段：底分型->顶分型->底分型->顶分型->底分型->顶分型
    // 标准上升线段：BOT->TOP->BOT->TOP->BOT->TOP
    // 其中第三个底分型需要高于第一个底分型
    
    if (first.tb == BOT && second.tb == TOP && third.tb == BOT && 
        fourth.tb == TOP && fifth.tb == BOT && sixth.tb == TOP) {
        
        // 检查价格关系：第三个底分型高于第一个底分型
        if (float_more(fifth.chan_price, first.chan_price)) {
            return std::make_pair(BOT, false); // 找到上升线段的底分型，无缺口
        }
    }
    // 检查下降线段：顶分型->底分型->顶分型->底分型->顶分型->底分型
    else if (first.tb == TOP && second.tb == BOT && third.tb == TOP && 
             fourth.tb == BOT && fifth.tb == TOP && sixth.tb == BOT) {
        
        // 检查价格关系：第三个顶分型低于第一个顶分型
        if (float_less(fifth.chan_price, first.chan_price)) {
            return std::make_pair(TOP, false); // 找到下降线段的顶分型，无缺口
        }
    }
    
    // 检查带缺口的情况
    // 简化处理：如果有价格跳空，可能形成缺口线段
    bool with_gap = false;
    
    // 检查是否有明显的价格跳空
    if (float_less(second.low, first.high - MIN_PRICE_UNIT * 5) || 
        float_more(second.high, first.low + MIN_PRICE_UNIT * 5)) {
        with_gap = true;
    }
    
    // 简化处理：返回无分型
    return std::make_pair(NO_TOPBOT, with_gap);
}

// K线缺口作为线段检查
std::tuple<TopBotType, bool, bool> ChanAnalyzer::checkKlineGapAsXd(const std::vector<int>& next_valid_elems, const std::vector<StandardKLine>& working_df, TopBotType direction) {
    // 简化实现：检查是否有K线缺口可以作为线段
    bool with_kline_gap_as_xd = false;
    bool with_current_gap = false;
    TopBotType result = NO_TOPBOT;
    
    if (next_valid_elems.size() >= 4) {
        const StandardKLine& first = working_df[next_valid_elems[0]];
        const StandardKLine& second = working_df[next_valid_elems[1]];
        const StandardKLine& third = working_df[next_valid_elems[2]];
        const StandardKLine& fourth = working_df[next_valid_elems[3]];
        
        // 检查是否有明显的价格跳空
        if (direction == BOT2TOP) {
            // 上升方向：检查是否有向上的跳空
            if (float_more(third.low, second.high + MIN_PRICE_UNIT * 3)) {
                with_kline_gap_as_xd = true;
                result = TOP; // 跳空可能形成线段顶分型
                with_current_gap = true;
            }
        } else if (direction == TOP2BOT) {
            // 下降方向：检查是否有向下的跳空
            if (float_less(third.high, second.low - MIN_PRICE_UNIT * 3)) {
                with_kline_gap_as_xd = true;
                result = BOT; // 跳空可能形成线段底分型
                with_current_gap = true;
            }
        }
    }
    
    return std::make_tuple(result, with_current_gap, with_kline_gap_as_xd);
}

// 检查前一个元素以避免线段缺口
bool ChanAnalyzer::checkPreviousElemToAvoidXdGap(bool with_gap, const std::vector<int>& next_valid_elems, std::vector<StandardKLine>& working_df) {
    if (next_valid_elems.empty() || next_valid_elems.size() < 4) {
        return with_gap;
    }
    
    const StandardKLine& first = working_df[next_valid_elems[0]];
    const StandardKLine& fourth = working_df[next_valid_elems[3]];
    
    // 获取前一个同类型分型
    std::vector<int> previous_elem = getPreviousNElem(next_valid_elems[0], working_df, 0, 
                                                     static_cast<TopBotType>(first.tb), true);
    
    if (!previous_elem.empty()) {
        if (first.tb == TOP) {
            // 对于顶分型，检查前一个顶分型的价格是否低于第四个分型的价格
            double max_prev_price = -std::numeric_limits<double>::max();
            for (int idx : previous_elem) {
                if (working_df[idx].chan_price > max_prev_price) {
                    max_prev_price = working_df[idx].chan_price;
                }
            }
            with_gap = float_less(max_prev_price, fourth.chan_price);
        } else if (first.tb == BOT) {
            // 对于底分型，检查前一个底分型的价格是否高于第四个分型的价格
            double min_prev_price = std::numeric_limits<double>::max();
            for (int idx : previous_elem) {
                if (working_df[idx].chan_price < min_prev_price) {
                    min_prev_price = working_df[idx].chan_price;
                }
            }
            with_gap = float_more(min_prev_price, fourth.chan_price);
        }
    }
    
    if (!with_gap && is_debug) {
        // 调试输出
    }
    
    return with_gap;
}

// 线段识别核心函数
std::tuple<TopBotType, bool, bool> ChanAnalyzer::checkXDTopBotDirected(const std::vector<int>& next_valid_elems, TopBotType direction, const std::vector<StandardKLine>& working_df) {
    if (next_valid_elems.size() < 6) {
        return std::make_tuple(NO_TOPBOT, false, false);
    }
    
    const StandardKLine& first = working_df[next_valid_elems[0]];
    const StandardKLine& second = working_df[next_valid_elems[1]];
    const StandardKLine& third = working_df[next_valid_elems[2]];
    const StandardKLine& fourth = working_df[next_valid_elems[3]];
    const StandardKLine& fifth = working_df[next_valid_elems[4]];
    const StandardKLine& sixth = working_df[next_valid_elems[5]];
    
    bool with_kline_gap_as_xd = false;
    
    // 首先检查K线缺口作为线段的情况
    auto gap_result = checkKlineGapAsXd(next_valid_elems, working_df, direction);
    TopBotType xd_gap_result = std::get<0>(gap_result);
    bool with_current_gap = std::get<1>(gap_result);
    with_kline_gap_as_xd = std::get<2>(gap_result);
    
    if (with_kline_gap_as_xd && xd_gap_result != NO_TOPBOT) {
        return std::make_tuple(xd_gap_result, with_current_gap, with_kline_gap_as_xd);
    }
    
    // 检查标准的线段顶底分型
    auto result = checkXDTopBot(first, second, third, fourth, fifth, sixth);
    TopBotType xd_result = result.first;
    with_current_gap = result.second;
    
    // 检查方向是否匹配
    if ((xd_result == TOP && direction == BOT2TOP) || (xd_result == BOT && direction == TOP2BOT)) {
        if (with_current_gap) {
            // 创建working_df的副本用于检查
            std::vector<StandardKLine> working_df_copy = working_df;
            with_current_gap = checkPreviousElemToAvoidXdGap(with_current_gap, next_valid_elems, working_df_copy);
        }
        return std::make_tuple(xd_result, with_current_gap, with_kline_gap_as_xd);
    }
    
    return std::make_tuple(NO_TOPBOT, with_current_gap, with_kline_gap_as_xd);
}

// 线段候选位置检查
int ChanAnalyzer::xdTopbotCandidate(const std::vector<int>& next_valid_elems, TopBotType current_direction, std::vector<StandardKLine>& working_df, bool with_current_gap) {
    if (next_valid_elems.size() != 3) {
        if (is_debug) {
            // 调试输出
        }
        return -1;
    }
    
    // 获取价格列表
    std::vector<double> chan_price_list;
    for (int idx : next_valid_elems) {
        chan_price_list.push_back(working_df[idx].chan_price);
    }
    
    // 简单检查：根据方向找到极值位置
    if (current_direction == TOP2BOT) {
        auto min_it = std::min_element(chan_price_list.begin(), chan_price_list.end());
        int min_index = std::distance(chan_price_list.begin(), min_it);
        
        if (min_index > 1) { // min_index == 2
            return next_valid_elems[min_index - 1]; // 导航到当前底分型的起始位置
        }
    } else if (current_direction == BOT2TOP) {
        auto max_it = std::max_element(chan_price_list.begin(), chan_price_list.end());
        int max_index = std::distance(chan_price_list.begin(), max_it);
        
        if (max_index > 1) { // max_index == 2
            return next_valid_elems[max_index - 1]; // 导航到当前顶分型的起始位置
        }
    }
    
    // 基于包含关系的检查
    std::vector<int> new_valid_elems;
    if (with_current_gap) {
        new_valid_elems = checkInclusionByDirection(next_valid_elems[1], working_df, current_direction, 4);
    } else {
        new_valid_elems = checkInclusionByDirection(next_valid_elems[1], working_df, current_direction, 6);
    }
    
    if (new_valid_elems.size() >= 4) {
        int end_loc = new_valid_elems[3] + 1;
        if (end_loc > static_cast<int>(working_df.size())) {
            end_loc = static_cast<int>(working_df.size());
        }
        
        // 获取受影响的价格范围
        double min_price = std::numeric_limits<double>::max();
        double max_price = -std::numeric_limits<double>::max();
        
        for (int i = new_valid_elems[0]; i < end_loc; i++) {
            double price = working_df[i].chan_price;
            if (price < min_price) min_price = price;
            if (price > max_price) max_price = price;
        }
        
        if (current_direction == TOP2BOT) {
            if (float_less(min_price, working_df[next_valid_elems[1]].chan_price)) {
                // 恢复数据
                restoreTbData(working_df, next_valid_elems[1], new_valid_elems.back());
                return next_valid_elems[1]; // 下一个候选位置
            }
        } else {
            if (float_more(max_price, working_df[next_valid_elems[1]].chan_price)) {
                // 恢复数据
                restoreTbData(working_df, next_valid_elems[1], new_valid_elems.back());
                return next_valid_elems[1]; // 下一个候选位置
            }
        }
    }
    
    return -1; // 没有找到候选位置
}

// 实现缺失的函数：缺口区域识别
std::vector<std::pair<double, double>> ChanAnalyzer::gapRegion(double start_date, double end_date, TopBotType gap_direction) {
    std::vector<std::pair<double, double>> regions;
    
    // 简化实现：在指定日期范围内查找缺口
    for (const auto& kline : original_data) {
        if (kline.date >= start_date && kline.date <= end_date && kline.gap != 0) {
            double start_price = kline.gap_start;
            double end_price = kline.gap_end;
            
            // 根据缺口方向调整顺序
            if (gap_direction == BOT2TOP) {
                // 上升缺口
                if (start_price < end_price) {
                    regions.push_back(std::make_pair(start_price, end_price));
                }
            } else if (gap_direction == TOP2BOT) {
                // 下降缺口
                if (start_price > end_price) {
                    regions.push_back(std::make_pair(end_price, start_price));
                }
            }
        }
    }
    
    return regions;
}

// 合并缺口区域
std::vector<std::pair<double, double>> ChanAnalyzer::combineGaps(const std::vector<std::pair<double, double>>& gap_regions) {
    std::vector<std::pair<double, double>> combined;
    
    if (gap_regions.empty()) {
        return combined;
    }
    
    combined.push_back(gap_regions[0]);
    
    for (size_t i = 1; i < gap_regions.size(); i++) {
        const auto& current = gap_regions[i];
        auto& last = combined.back();
        
        // 检查是否可以合并重叠或相邻的缺口
        if (current.first <= last.second + MIN_PRICE_UNIT * 2) {
            // 合并缺口区域
            last.second = std::max(last.second, current.second);
        } else {
            combined.push_back(current);
        }
    }
    
    return combined;
}

// K线缺口作为线段检查
bool ChanAnalyzer::kbarGapAsXd(const std::vector<StandardKLine>& working_df, int first_idx, int second_idx, int compare_idx) {
    if (first_idx < 0 || second_idx < 0 || compare_idx < 0 || 
        first_idx >= static_cast<int>(working_df.size()) || 
        second_idx >= static_cast<int>(working_df.size()) || 
        compare_idx >= static_cast<int>(working_df.size())) {
        return false;
    }
    
    const StandardKLine& first = working_df[first_idx];
    const StandardKLine& second = working_df[second_idx];
    const StandardKLine& compare = working_df[compare_idx];
    
    // 检查是否有明显的价格跳空
    if (float_more(first.high, compare.low + MIN_PRICE_UNIT * 5) ||
        float_less(first.low, compare.high - MIN_PRICE_UNIT * 5)) {
        return true;
    }
    
    // 检查第二个元素是否增强了缺口效应
    if (float_more(second.high, compare.low + MIN_PRICE_UNIT * 3) ||
        float_less(second.low, compare.high - MIN_PRICE_UNIT * 3)) {
        return true;
    }
    
    return false;
}

// 线段包含关系处理
bool ChanAnalyzer::xdInclusion(const StandardKLine& first, const StandardKLine& second, const StandardKLine& third, const StandardKLine& forth) {
    // 检查线段级别的包含关系
    // 简化的线段包含逻辑：检查四个分型是否形成包含关系
    
    // 获取价格范围
    double min_price1 = std::min(first.chan_price, second.chan_price);
    double max_price1 = std::max(first.chan_price, second.chan_price);
    double min_price2 = std::min(third.chan_price, forth.chan_price);
    double max_price2 = std::max(third.chan_price, forth.chan_price);
    
    // 检查包含关系
    if (float_less_equal(min_price1, min_price2) && float_more_equal(max_price1, max_price2)) {
        return true; // 第一个线段包含第二个线段
    } else if (float_less_equal(min_price2, min_price1) && float_more_equal(max_price2, max_price1)) {
        return true; // 第二个线段包含第一个线段
    }
    
    return false;
}

// 检查线段包含关系是否自由
std::pair<bool, bool> ChanAnalyzer::isXDInclusionFree(TopBotType direction, const std::vector<int>& next_valid_elems, std::vector<StandardKLine>& working_df) {
    if (next_valid_elems.size() < 4) {
        return std::make_pair(false, false);
    }
    
    bool has_inclusion = false;
    bool is_free = true;
    
    for (size_t i = 0; i < next_valid_elems.size() - 3; i += 2) {
        int idx1 = next_valid_elems[i];
        int idx2 = next_valid_elems[i+1];
        int idx3 = next_valid_elems[i+2];
        int idx4 = next_valid_elems[i+3];
        
        if (idx1 < static_cast<int>(working_df.size()) && idx2 < static_cast<int>(working_df.size()) &&
            idx3 < static_cast<int>(working_df.size()) && idx4 < static_cast<int>(working_df.size())) {
            
            const StandardKLine& first = working_df[idx1];
            const StandardKLine& second = working_df[idx2];
            const StandardKLine& third = working_df[idx3];
            const StandardKLine& fourth = working_df[idx4];
            
            if (xdInclusion(first, second, third, fourth)) {
                has_inclusion = true;
                
                // 检查包含关系是否影响当前方向
                if ((direction == BOT2TOP && first.tb == BOT) ||
                    (direction == TOP2BOT && first.tb == TOP)) {
                    is_free = false;
                }
            }
        }
    }
    
    return std::make_pair(has_inclusion, is_free);
}

// 弹出缺口
std::pair<int, TopBotType> ChanAnalyzer::popGap(std::vector<StandardKLine>& working_df, const std::vector<int>& next_valid_elems, TopBotType current_direction) {
    if (next_valid_elems.size() < 2) {
        return std::make_pair(-1, NO_TOPBOT);
    }
    
    // 查找第一个有意义的缺口
    for (size_t i = 0; i < next_valid_elems.size() - 1; i++) {
        int idx1 = next_valid_elems[i];
        int idx2 = next_valid_elems[i+1];
        
        if (idx1 < static_cast<int>(working_df.size()) && idx2 < static_cast<int>(working_df.size())) {
            const StandardKLine& first = working_df[idx1];
            const StandardKLine& second = working_df[idx2];
            
            // 检查是否有价格跳空
            if ((current_direction == BOT2TOP && float_more(second.low, first.high + MIN_PRICE_UNIT * 3)) ||
                (current_direction == TOP2BOT && float_less(second.high, first.low - MIN_PRICE_UNIT * 3))) {
                
                // 返回缺口位置和方向
                return std::make_pair(idx1, current_direction);
            }
        }
    }
    
    return std::make_pair(-1, NO_TOPBOT);
}

// 查找线段
std::vector<StandardKLine> ChanAnalyzer::findXD(int initial_i, TopBotType initial_direction, std::vector<StandardKLine>& working_df) {
    std::vector<StandardKLine> result;
    
    if (initial_i < 0 || initial_i >= static_cast<int>(working_df.size())) {
        return result;
    }
    
    int current_idx = initial_i;
    TopBotType current_direction = initial_direction;
    bool found_xd = false;
    
    // 查找后续的分型
    std::vector<int> next_elems = getNextNElem(current_idx, working_df, 6, NO_TOPBOT, false);
    
    while (!next_elems.empty() && !found_xd) {
        // 检查是否构成线段
        auto xd_result = checkXDTopBotDirected(next_elems, current_direction, working_df);
        TopBotType xd_type = std::get<0>(xd_result);
        bool with_current_gap = std::get<1>(xd_result);
        bool with_kline_gap_as_xd = std::get<2>(xd_result);
        
        if (xd_type != NO_TOPBOT) {
            // 找到线段
            found_xd = true;
            
            // 将找到的线段分型添加到结果中
            for (int idx : next_elems) {
                if (idx >= 0 && idx < static_cast<int>(working_df.size())) {
                    StandardKLine kline = working_df[idx];
                    kline.xd_tb = (idx == next_elems[2] || idx == next_elems[5]) ? xd_type : NO_TOPBOT;
                    result.push_back(kline);
                }
            }
        } else if (with_current_gap || with_kline_gap_as_xd) {
            // 处理缺口情况
            auto gap_info = popGap(working_df, next_elems, current_direction);
            int gap_idx = gap_info.first;
            
            if (gap_idx != -1) {
                // 跳过缺口，继续查找
                current_idx = gap_idx + 1;
                next_elems = getNextNElem(current_idx, working_df, 6, NO_TOPBOT, false);
                continue;
            }
        }
        
        // 移动到下一个位置
        if (!next_elems.empty()) {
            current_idx = next_elems[0] + 1;
        } else {
            current_idx++;
        }
        next_elems = getNextNElem(current_idx, working_df, 6, NO_TOPBOT, false);
    }
    
    // 如果没有找到完整的线段，但至少有一些分型，返回部分结果
    if (result.empty() && !next_elems.empty()) {
        for (int idx : next_elems) {
            if (idx >= 0 && idx < static_cast<int>(working_df.size())) {
                result.push_back(working_df[idx]);
            }
        }
    }
    
    return result;
}

// 增强的线段定义函数
void ChanAnalyzer::defineXDEnhanced(int initial_state) {
    if (marked_bi.empty()) return;
    
    // 使用标记的笔作为起点
    std::vector<StandardKLine> working_df = marked_bi;
    std::vector<StandardKLine> xd_result;
    
    // 确定初始方向
    TopBotType current_direction = findInitialDirection(working_df, static_cast<TopBotType>(initial_state));
    
    // 从头开始查找线段
    int current_idx = 0;
    while (current_idx < static_cast<int>(working_df.size())) {
        std::vector<StandardKLine> found_xd = findXD(current_idx, current_direction, working_df);
        
        if (!found_xd.empty()) {
            // 将找到的线段添加到结果中
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
            current_direction = (current_direction == BOT2TOP) ? TOP2BOT : BOT2TOP;
        } else {
            current_idx++;
        }
    }
    
    marked_xd = xd_result;
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
    
    // 检查在指定范围内是否存在缺口
    if (next_index < 0 || next_index >= static_cast<int>(working_df.size()) ||
        current_index < 0 || current_index >= static_cast<int>(working_df.size())) {
        return false;
    }
    
    // 检查缺口是否存在于当前分型和下一个分型之间
    if (gapExistsInRange(working_df[current_index].date, working_df[next_index].date)) {
        // 确定缺口方向
        TopBotType gap_direction = NO_TOPBOT;
        if (working_df[next_index].tb == TOP) {
            gap_direction = BOT2TOP;
        } else if (working_df[next_index].tb == BOT) {
            gap_direction = TOP2BOT;
        }
        
        if (gap_direction == NO_TOPBOT) {
            return false;
        }
        
        // 获取缺口区域
        auto gap_ranges = gapRegion(working_df[current_index].date, 
                                   working_df[next_index].date, 
                                   gap_direction);
        gap_ranges = combineGaps(gap_ranges);
        
        // 检查每个缺口是否满足条件
        for (const auto& gap : gap_ranges) {
            if (previous_index < 0) {
                return true;
            }
            
            if (working_df[previous_index].tb == TOP) {
                // 对于顶分型：缺口高于前一个顶分型的低点
                bool qualify = float_less(gap.first, working_df[previous_index].low) &&
                              float_less_equal(working_df[previous_index].low, working_df[previous_index].high) &&
                              float_less(working_df[previous_index].high, gap.second);
                if (qualify) {
                    return true;
                }
            } else if (working_df[previous_index].tb == BOT) {
                // 对于底分型：缺口低于前一个底分型的高点
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
    // 回溯查找前一个有效分型
    for (int i = current_index - 1; i >= 0; i--) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            return i;
        }
    }
    return -1;
}

// 实现缺失的函数：get_next_tb
int ChanAnalyzer::get_next_tb(int current_index, const std::vector<StandardKLine>& working_df) {
    // 查找下一个有效分型
    for (int i = current_index + 1; i < static_cast<int>(working_df.size()); i++) {
        if (working_df[i].tb == TOP || working_df[i].tb == BOT) {
            return i;
        }
    }
    return static_cast<int>(working_df.size()); // 返回末尾索引
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
            xd.start_index = start.new_index;
            xd.end_index = end.new_index;
            
            result.push_back(xd);
        }
    }
    
    return result;
}