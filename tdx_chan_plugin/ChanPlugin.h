// ChanPlugin.h - Tongdaxin Chan Theory Plugin Header File
// Plugin supports any period, real-time updates, draws pen and line segments on main K chart

// Prevent conflicts between min/max macros in windows.h and std::min/std::max
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#pragma once

#ifdef _WIN32
    #include <windows.h>
#else
    // Non-Windows platform simulation
    typedef void* HDC;
    typedef struct { int left; int top; int right; int bottom; } RECT;
    #define __declspec(dllexport)
    #define __stdcall
#endif

#include <vector>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <string>
#include <sstream>
#include <tuple>
#include <utility>

// Chan theory constant definitions
const double MIN_PRICE_UNIT = 0.01;  // Minimum price unit
const double FLOAT_CMP_EPSILON = 1e-10; // 显式 epsilon 下限
const double FLOAT_CMP_RTOL = 1e-5;     // 对应 np.isclose 默认 rtol
const double FLOAT_CMP_ATOL = 1e-8;     // 对应 np.isclose 默认 atol
const double GOLDEN_RATIO = 0.618;   // Golden ratio

// Top/bottom pattern type enumeration
enum TopBotType {
    NO_TOPBOT = 0,   // No pattern
    TOP = 1,         // Top pattern
    BOT = 2,         // Bottom pattern
    TOP2BOT = 3,     // Top to bottom
    BOT2TOP = 4      // Bottom to top
};

// Inclusion relation type
enum InclusionType {
    NO_INCLUSION = 0,    // No inclusion
    FIRST_CSECOND = 1,   // First includes second
    SECOND_CFIRST = 2    // Second includes first
};

// K-line data structure
struct KLine {
    int date;           // Date/time
    double open;        // Open price
    double high;        // High price
    double low;         // Low price
    double close;       // Close price
    double volume;      // Volume
    int gap;            // Gap: 0=none, 1=up gap, -1=down gap
    double gap_start;   // Gap start price
    double gap_end;     // Gap end price
};

// Standardized K-line data structure
struct StandardKLine {
    int date;           // Date/time
    double close;       // Close price
    double high;        // High price (after standardization)
    double low;         // Low price (after standardization)
    int real_loc;       // Original position index
    int new_index;      // New index
    int tb;             // Top/bottom pattern type
    double chan_price;  // Chan price (high for top pattern, low for bottom pattern)
    int original_tb;    // Original pattern type
    int xd_tb;          // Line segment top/bottom pattern type
    // 已被包含处理合并掉的元素标记。
    // 注意: 不能用 high/low 置 0 当标记 —— Python 原版里被合并元素保留原始 high/low
    // (合并结果放在 new_high/new_low), 而 isBullType(past, first) 依赖 past 的原始 high;
    // 置 0 会让方向判断恒为 BOT2TOP, 合并取 max/min 取错, 分型数量与位置随之全偏。
    bool merged_away = false;
};

// Feature sequence element for XD line segment detection
struct FeatureSeqElement {
    TopBotType tb;              // TOP or BOT
    double price;               // Price for inclusion check (direction-merged: max for up, min for down)
    double orig_price;          // Price for XD endpoint detection (true market extreme)
    int orig_market_idx;        // Index of corresponding StandardKLine in working_df
    bool is_merged;             // Whether this element results from merging
    std::vector<int> sources;   // Indices of original elements merged into this one (for debugging)
};

// Result returned by findXDOnFeatureSeq (one XD endpoint per call)
struct XDFindResult {
    bool found;                 // Whether an XD endpoint was found
    int xd_market_idx;          // Market index of the XD endpoint in working_df
    TopBotType xd_type;         // TOP or BOT
    bool with_gap;              // Whether gap was involved
    int next_market_start;      // Market index for next segment's tail_start in working_df
    TopBotType new_direction;   // Direction for next segment
    bool is_rollback;           // True for popGap / prev_xd invalidation
    int rollback_start;         // Market index to rollback tail_start to
    bool is_kg2_backstep;       // True when new_i == i+1 (gap-based XD overlapping)
};

// Pen structure
struct Bi {
    int start_date;     // Start date
    int end_date;       // End date
    double start_price; // Start price
    double end_price;   // End price
    int type;           // Type: TOP=top pattern, BOT=bottom pattern
    int start_index;    // Start index
    int end_index;      // End index
};

// Line segment structure
struct XianDuan {
    int start_date;     // Start date
    int end_date;       // End date
    double start_price; // Start price
    double end_price;   // End price
    int type;           // Type: TOP=top pattern, BOT=bottom pattern
    int start_index;    // Start index
    int end_index;      // End index
};

// 浮点比较 (与 Python chan_common_include.float_* 保持一致)
// Python: float_less(a,b) = a < b and not np.isclose(a,b)
//         np.isclose 默认 rtol=1e-5, atol=1e-8 -> 容差 = atol + rtol*|b|
// 原实现用固定绝对容差 1e-10, 对大价格标的 (如千元股) 会与 Python 判定不同:
// Python 认为 0.015 元以内的差算"相等", 原实现只有 1e-10 以内才算相等, 于是
// 包含关系与分型判定发生分歧。
inline bool float_isclose(double a, double b, double epsilon = FLOAT_CMP_EPSILON) {
    double tol = FLOAT_CMP_ATOL + FLOAT_CMP_RTOL * std::abs(b);
    if (tol < epsilon) tol = epsilon;   // 显式传入的 epsilon 仍作为下限生效
    return std::abs(a - b) <= tol;
}

inline bool float_less(double a, double b, double epsilon = FLOAT_CMP_EPSILON) {
    return a < b && !float_isclose(a, b, epsilon);
}

inline bool float_more(double a, double b, double epsilon = FLOAT_CMP_EPSILON) {
    return a > b && !float_isclose(a, b, epsilon);
}

inline bool float_less_equal(double a, double b, double epsilon = FLOAT_CMP_EPSILON) {
    return a < b || float_isclose(a, b, epsilon);
}

inline bool float_more_equal(double a, double b, double epsilon = FLOAT_CMP_EPSILON) {
    return a > b || float_isclose(a, b, epsilon);
}

inline bool float_equal(double a, double b, double epsilon = FLOAT_CMP_EPSILON) {
    return float_isclose(a, b, epsilon);
}

// Chan Analyzer main class
class ChanAnalyzer {
private:
    std::vector<KLine> original_data;          // Original K-line data
    std::vector<StandardKLine> standardized;   // Standardized K-lines
    std::vector<StandardKLine> marked_bi;      // Marked pen
    std::vector<StandardKLine> marked_xd;      // Marked line segment
    std::vector<int> gap_XD;                   // Line segment gap indices
    std::vector<int> previous_skipped_idx;     // Previously skipped indices
    bool previous_with_xd_gap;                 // Previously had line segment gap
    bool is_debug;                             // Debug mode

public:
    ChanAnalyzer(bool debug = false);
    
    // Set K-line data
    void setData(const std::vector<KLine>& data);
    
    // Execute complete analysis
    void analyze();
    
    // Get pen
    std::vector<Bi> getBi() const;
    
    // Get line segment
    std::vector<XianDuan> getXianDuan() const;
    
    // Get standardized K-lines (for debugging)
    std::vector<StandardKLine> getStandardized() const { return standardized; }

    // Get pen fractal points / segment endpoints (for debugging and diagnostics)
    std::vector<StandardKLine> getMarkedBi() const { return marked_bi; }
    std::vector<StandardKLine> getMarkedXd() const { return marked_xd; }
    
private:
    // Core algorithm methods
    void standardize(int initial_state = NO_TOPBOT);
    void markTopBot(int initial_state = NO_TOPBOT, bool mark_last_kbar = true);
    void defineBi();
    void defineXD(int initial_state = NO_TOPBOT);
    
    // Helper methods
    InclusionType checkInclusion(const StandardKLine& first, const StandardKLine& second);
    TopBotType isBullType(const StandardKLine& first, const StandardKLine& second);
    TopBotType checkTopBot(const StandardKLine& current, 
                          const StandardKLine& first, 
                          const StandardKLine& second);
    
    // Gap processing
    void detectGaps();
    bool gapExistsInRange(int start_idx, int end_idx);
    bool gapExistsInDateRange(double start_date, double end_date);
    
    // Index lookup
    int getNextLoc(int loc, const std::vector<StandardKLine>& working_df);
    
    // Clean first two top/bottom patterns (in-place)
    void cleanFirstTwoTB(std::vector<StandardKLine>& working_df);
    
    // Gap processing
    std::vector<std::pair<double, double>> gapRegion(double start_date, double end_date, TopBotType gap_direction);
    std::vector<std::pair<double, double>> combineGaps(const std::vector<std::pair<double, double>>& gap_regions);

    // ---- 缺口查询加速 (与"逐根全表日期过滤"完全等价, 输出逐字节相同) ----------
    // gap_prefix_[i]    = 前 i 根K线中"带缺口(gap != 0)"的根数
    // dates_monotonic_  = 日期数组是否"非递减"; 只有非递减才能把日期区间安全地换算成
    //                     K线下标区间。非递减(允许相等, 分钟线常见同日多根)即可;
    //                     一旦检测到倒退(d[i] < d[i-1])则所有加速路径自动回退到
    //                     原来的逐根扫描, 因此绝不影响结果。
    std::vector<int> gap_prefix_;
    bool dates_monotonic_ = false;
    std::pair<int, int> barIndexRangeByDate(double start_date, double end_date) const;
    // A2: defineXD 开头为每个笔端点元素预计算 "日期之后第一根K线的下标"
    // (日期非递减时可用, 查询从 O(log n) 降到 O(1); 与二分结果完全一致)
    std::vector<int> elem_after_date_;
    // 按下标区间收集缺口 (gapRegion 的 O(1) 边界版本)
    std::vector<std::pair<double, double>> gapRegionInBars(int b_from, int b_to_excl,
                                                           TopBotType gap_direction) const;
    
    // Core helper functions
    std::vector<int> getPreviousNElem(int loc, const std::vector<StandardKLine>& working_df, int N = 0, TopBotType end_tb = NO_TOPBOT, bool single_direction = true);
    bool directionAssert(const StandardKLine& elem, TopBotType direction);
    
    // Feature sequence element inclusion processing (Chan Theory compliant)
    std::vector<FeatureSeqElement> buildFeatureSeq(const std::vector<StandardKLine>& working_df, int start_loc);
    // 同 buildFeatureSeq, 但复用调用方提供的缓冲 (内容完全一致, 只为避免每轮重新分配)
    void buildFeatureSeqInto(const std::vector<StandardKLine>& working_df, int start_loc,
                             std::vector<FeatureSeqElement>& seq);
    // defineXD 主循环复用的特征序列缓冲
    std::vector<FeatureSeqElement> seq_buf_;

    // ---- A3: 特征序列缓存 ------------------------------------------------------
    // (tail_start, direction) -> buildFeatureSeq + processInclusions 的结果。
    // 二者只依赖 original_tb / high / low (笔阶段之后不再变化) 与方向, 因此同一对
    // 键必然得到同一序列, 可安全复用; 每次 defineXD 开始与 setData 时清空。
    // applied: 该序列对应的 chan_price 回写是否已执行过 (回写是幂等的, 重复执行无效果)。
    struct SeqCacheEntry {
        int tail_start = -1;
        int direction = 0;
        bool applied = false;
        long long tick = 0;
        std::vector<FeatureSeqElement> seq;
    };
    std::vector<SeqCacheEntry> seq_cache_;
    long long seq_cache_tick_ = 0;
    bool hasFeatureSeqInclusion(const FeatureSeqElement& e0, const FeatureSeqElement& e1,
                                const FeatureSeqElement& e2, const FeatureSeqElement& e3);
    std::pair<FeatureSeqElement, FeatureSeqElement> mergeFeatureSeqPair(
        const FeatureSeqElement& e0, const FeatureSeqElement& e1,
        const FeatureSeqElement& e2, const FeatureSeqElement& e3,
        bool merge_max);
    void processInclusions(std::vector<FeatureSeqElement>& seq, TopBotType direction);
    void applyCleanSequence(const std::vector<FeatureSeqElement>& feature_seq,
                            std::vector<StandardKLine>& working_df, int start_loc,
                            int end_loc = -1);

    // FeatureSeqElement-based XD endpoint detection (replaces findXDFull)
    // Now processes ONE segment per call, returns result for iterative caller
    // (只读 feature_seq: 该函数从不修改序列, 便于 A3 缓存复用)
    XDFindResult findXDOnFeatureSeq(const std::vector<FeatureSeqElement>& feature_seq,
                                    std::vector<StandardKLine>& working_df,
                                    int seq_pos, TopBotType direction,
                                    int tail_start_market);

    // Line segment gap detection (retained)
    bool kbarGapAsXdFull(const std::vector<StandardKLine>& working_df, int first_idx, int second_idx, int compare_idx);

    // Segment endpoint extreme repair (Chan: a segment's endpoints must be the
    // extreme points of that segment)
    void repairXdExtremes(std::vector<StandardKLine>& working_df);
    void cleanXdMarks(std::vector<StandardKLine>& working_df);
    // Ported from Python check_previous_elem_to_avoid_xd_gap: narrows with_gap
    // when a previous same-type feature element already crosses element 4.
    // 原文第67课第二种情况: 反向特征序列出现反向分型才算确认
    bool secondFeatureSeqConfirms(const std::vector<StandardKLine>& working_df,
                                  int pivot_idx, TopBotType pivot_type);
    bool checkPreviousElemToAvoidXdGap(bool with_gap,
                                       const std::vector<FeatureSeqElement>& seq,
                                       int i,
                                       std::vector<StandardKLine>& working_df);
    
    // Initial direction
    std::pair<int, TopBotType> findInitialDirectionFull(std::vector<StandardKLine>& working_df, TopBotType initial_status);
    
    // Bi definition helpers
    void restoreTbData(std::vector<StandardKLine>& working_df, int from_idx, int to_idx);
    std::tuple<int, int, int> same_tb_remove_previous(std::vector<StandardKLine>& working_df, int previous_index, int current_index, int next_index);
    std::tuple<int, int, int> same_tb_remove_current(std::vector<StandardKLine>& working_df, int previous_index, int current_index, int next_index);
    std::tuple<int, int, int> same_tb_remove_next(std::vector<StandardKLine>& working_df, int previous_index, int current_index, int next_index);
    int trace_back_index(const std::vector<StandardKLine>& working_df, int current_index);
    int get_next_tb(int current_index, const std::vector<StandardKLine>& working_df);
    bool check_gap_qualify(const std::vector<StandardKLine>& working_df, int previous_index, int current_index, int next_index);
    std::tuple<int, int, int> work_on_end(std::vector<StandardKLine>& working_df, int pre_idx, int cur_idx, int nex_idx);
};


// Tongdaxin plugin interface functions
#ifdef __cplusplus
extern "C" {
#endif

// Plugin information
__declspec(dllexport) const char* __stdcall TDXPlugin_GetInfo();
__declspec(dllexport) int __stdcall TDXPlugin_Init();

// Main calculation function
__declspec(dllexport) int __stdcall TDXPlugin_Calculate(
    int nCount,                     // K-line count
    float* pOpen,                   // Open price array
    float* pHigh,                   // High price array
    float* pLow,                    // Low price array
    float* pClose,                  // Close price array
    float* pVolume,                 // Volume array
    int* pDate,                     // Date array
    int nPeriod,                    // Period type
    int* pOutCount,                 // Output count
    float** ppOutData1,             // Output data 1 (pen)
    float** ppOutData2,             // Output data 2 (line segment)
    char*** ppOutText               // Output text
);

// Drawing function
__declspec(dllexport) int __stdcall TDXPlugin_Draw(
    HDC hDC,                        // Device context
    RECT* pRect,                    // Drawing area
    int nCount,                     // K-line count
    float* pOpen,                   // Open price array
    float* pHigh,                   // High price array
    float* pLow,                    // Low price array
    float* pClose,                  // Close price array
    int* pDate,                     // Date array
    int nPeriod                     // Period type
);

#ifdef __cplusplus
}
#endif
