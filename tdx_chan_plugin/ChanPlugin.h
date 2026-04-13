// ChanPlugin.h - 通达信缠论插件头文件
// 插件支持任何周期，实时更新，在主K线图上绘制笔和线段

// 防止windows.h中的min/max宏与std::min/std::max冲突
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
    // 非Windows平台模拟
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

// 缠论常量定义
const double MIN_PRICE_UNIT = 0.01;  // 最小价格单位
const double GOLDEN_RATIO = 0.618;   // 黄金分割比例

// 顶底分型类型枚举
enum TopBotType {
    NO_TOPBOT = 0,   // 无分型
    TOP = 1,         // 顶分型
    BOT = 2,         // 底分型
    TOP2BOT = 3,     // 顶到底
    BOT2TOP = 4      // 底到顶
};

// 包含关系类型
enum InclusionType {
    NO_INCLUSION = 0,    // 无包含
    FIRST_CSECOND = 1,   // 第一包含第二
    SECOND_CFIRST = 2    // 第二包含第一
};

// K线数据结构
struct KLine {
    int date;           // 日期/时间
    double open;        // 开盘价
    double high;        // 最高价
    double low;         // 最低价
    double close;       // 收盘价
    double volume;      // 成交量
    int gap;            // 跳空缺口: 0=无, 1=向上缺口, -1=向下缺口
    double gap_start;   // 缺口开始价格
    double gap_end;     // 缺口结束价格
};

// 标准化K线数据结构
struct StandardKLine {
    int date;           // 日期/时间
    double close;       // 收盘价
    double high;        // 最高价（标准化后）
    double low;         // 最低价（标准化后）
    int real_loc;       // 原始位置索引
    int new_index;      // 新索引
    int tb;             // 顶底分型类型
    double chan_price;  // 缠论价格（顶分型取high，底分型取low）
    int original_tb;    // 原始分型类型
    int xd_tb;          // 线段顶底分型类型
};

// 笔结构
struct Bi {
    int start_date;     // 起始日期
    int end_date;       // 结束日期
    double start_price; // 起始价格
    double end_price;   // 结束价格
    int type;           // 类型: TOP=顶分型, BOT=底分型
    int start_index;    // 起始索引
    int end_index;      // 结束索引
};

// 线段结构
struct XianDuan {
    int start_date;     // 起始日期
    int end_date;       // 结束日期
    double start_price; // 起始价格
    double end_price;   // 结束价格
    int type;           // 类型: TOP=顶分型, BOT=底分型
    int start_index;    // 起始索引
    int end_index;      // 结束索引
};

// 浮点数比较函数（考虑精度）
inline bool float_less(double a, double b) {
    return a <= b - MIN_PRICE_UNIT;
}

inline bool float_more(double a, double b) {
    return (a - b) > (MIN_PRICE_UNIT * 0.9999);
}

inline bool float_less_equal(double a, double b) {
    return a <= b + MIN_PRICE_UNIT;
}

inline bool float_more_equal(double a, double b) {
    return a >= b - MIN_PRICE_UNIT;
}

// 缠论分析器主类
class ChanAnalyzer {
private:
    std::vector<KLine> original_data;          // 原始K线数据
    std::vector<StandardKLine> standardized;   // 标准化K线
    std::vector<StandardKLine> marked_bi;      // 标记的笔
    std::vector<StandardKLine> marked_xd;      // 标记的线段
    std::vector<int> gap_XD;                   // 线段缺口索引
    std::vector<int> previous_skipped_idx;     // 之前跳过的索引
    bool previous_with_xd_gap;                 // 之前有线段缺口
    bool is_debug;                             // 调试模式

public:
    ChanAnalyzer(bool debug = false);
    
    // 设置K线数据
    void setData(const std::vector<KLine>& data);
    
    // 执行完整分析
    void analyze();
    
    // 获取笔
    std::vector<Bi> getBi() const;
    
    // 获取线段
    std::vector<XianDuan> getXianDuan() const;
    
    // 获取标准化K线（用于调试）
    std::vector<StandardKLine> getStandardized() const { return standardized; }
    
private:
    // 核心算法方法
    void standardize(int initial_state = NO_TOPBOT);
    void markTopBot(int initial_state = NO_TOPBOT, bool mark_last_kbar = true);
    void defineBi();
    void defineXD(int initial_state = NO_TOPBOT);
    
    // 辅助方法
    InclusionType checkInclusion(const StandardKLine& first, const StandardKLine& second);
    TopBotType isBullType(const StandardKLine& first, const StandardKLine& second);
    TopBotType checkTopBot(const StandardKLine& current, 
                          const StandardKLine& first, 
                          const StandardKLine& second);
    
    // 缺口处理
    void detectGaps();
    bool gapExistsInRange(int start_idx, int end_idx);
    
    // 索引查找
    int getNextLoc(int loc, const std::vector<StandardKLine>& working_df);
    int getPreviousLoc(int loc, const std::vector<StandardKLine>& working_df);
    
    // 清理前两个分型
    std::vector<StandardKLine> cleanFirstTwoTB(const std::vector<StandardKLine>& working_df);
    
    // 缺口处理高级函数
    std::vector<std::pair<double, double>> gapRegion(double start_date, double end_date, TopBotType gap_direction);
    std::vector<std::pair<double, double>> combineGaps(const std::vector<std::pair<double, double>>& gap_regions);
    bool kbarGapAsXd(const std::vector<StandardKLine>& working_df, int first_idx, int second_idx, int compare_idx);
    
    // 线段包含关系处理
    bool xdInclusion(const StandardKLine& first, const StandardKLine& second, const StandardKLine& third, const StandardKLine& forth);
    std::pair<bool, bool> isXDInclusionFree(TopBotType direction, const std::vector<int>& next_valid_elems, std::vector<StandardKLine>& working_df);
    
    // 高级线段识别
    std::vector<int> checkInclusionByDirection(int current_loc, std::vector<StandardKLine>& working_df, TopBotType direction, int count_num = 6);
    std::pair<TopBotType, bool> checkXDTopBot(const StandardKLine& first, const StandardKLine& second, const StandardKLine& third, 
                                              const StandardKLine& forth, const StandardKLine& fifth, const StandardKLine& sixth);
    std::tuple<TopBotType, bool, bool> checkKlineGapAsXd(const std::vector<int>& next_valid_elems, const std::vector<StandardKLine>& working_df, TopBotType direction);
    std::tuple<TopBotType, bool, bool> checkXDTopBotDirected(const std::vector<int>& next_valid_elems, TopBotType direction, const std::vector<StandardKLine>& working_df);
    
    // 辅助函数
    std::vector<int> getNextNElem(int loc, const std::vector<StandardKLine>& working_df, int N = 4, TopBotType start_tb = NO_TOPBOT, bool single_direction = false);
    std::vector<int> getPreviousNElem(int loc, const std::vector<StandardKLine>& working_df, int N = 0, TopBotType end_tb = NO_TOPBOT, bool single_direction = true);
    bool directionAssert(const StandardKLine& elem, TopBotType direction);
    TopBotType findInitialDirection(const std::vector<StandardKLine>& working_df, TopBotType initial_status);
    void restoreTbData(std::vector<StandardKLine>& working_df, int from_idx, int to_idx);
    int xdTopbotCandidate(const std::vector<int>& next_valid_elems, TopBotType current_direction, std::vector<StandardKLine>& working_df, bool with_current_gap);
    std::pair<int, TopBotType> popGap(std::vector<StandardKLine>& working_df, const std::vector<int>& next_valid_elems, TopBotType current_direction);
    std::vector<StandardKLine> findXD(int initial_i, TopBotType initial_direction, std::vector<StandardKLine>& working_df);
    
    // 完整线段定义辅助函数 (Full implementation matching Python)
    bool xdInclusionFull(const StandardKLine& firstElem, const StandardKLine& secondElem,
                         const StandardKLine& thirdElem, const StandardKLine& forthElem);
    bool checkCurrentGap(const std::vector<StandardKLine>& working_df, int idx0, int idx1, int idx2, int idx3);
    bool kbarGapAsXdFull(const std::vector<StandardKLine>& working_df, int first_idx, int second_idx, int compare_idx);
    std::pair<bool, bool> isXDInclusionFreeFull(TopBotType direction, const std::vector<int>& next_valid_elems, std::vector<StandardKLine>& working_df);
    std::vector<int> checkInclusionByDirectionFull(int current_loc, std::vector<StandardKLine>& working_df, TopBotType direction, int count_num);
    std::tuple<TopBotType, bool, bool> checkKlineGapAsXdFull(const std::vector<int>& next_valid_elems, TopBotType direction, std::vector<StandardKLine>& working_df);
    std::pair<TopBotType, bool> checkXDTopBotFull(const StandardKLine& first, const StandardKLine& second,
                                                   const StandardKLine& third, const StandardKLine& forth,
                                                   const StandardKLine& fifth, const StandardKLine& sixth);
    std::tuple<TopBotType, bool, bool> checkXDTopBotDirectedFull(const std::vector<int>& next_valid_elems, TopBotType direction, std::vector<StandardKLine>& working_df);
    int xdTopbotCandidateFull(const std::vector<int>& next_valid_elems, TopBotType current_direction, std::vector<StandardKLine>& working_df, bool with_current_gap);
    std::pair<int, TopBotType> popGapFull(std::vector<StandardKLine>& working_df, const std::vector<int>& next_valid_elems, TopBotType current_direction);
    std::vector<StandardKLine> findXDFull(int initial_i, TopBotType initial_direction, std::vector<StandardKLine>& working_df);
    std::pair<int, TopBotType> findInitialDirectionFull(std::vector<StandardKLine>& working_df, TopBotType initial_status);
    
    // 检查前一个元素以避免线段缺口
    bool checkPreviousElemToAvoidXdGap(bool with_gap, const std::vector<int>& next_valid_elems, std::vector<StandardKLine>& working_df);
    
    // 增强的线段定义函数
    void defineXDEnhanced(int initial_state = NO_TOPBOT);
    
    // 缺失的函数声明
    std::tuple<int, int, int> same_tb_remove_previous(std::vector<StandardKLine>& working_df, int previous_index, int current_index, int next_index);
    std::tuple<int, int, int> same_tb_remove_current(std::vector<StandardKLine>& working_df, int previous_index, int current_index, int next_index);
    std::tuple<int, int, int> same_tb_remove_next(std::vector<StandardKLine>& working_df, int previous_index, int current_index, int next_index);
    int trace_back_index(const std::vector<StandardKLine>& working_df, int current_index);
    int get_next_tb(int current_index, const std::vector<StandardKLine>& working_df);
    bool check_gap_qualify(const std::vector<StandardKLine>& working_df, int previous_index, int current_index, int next_index);
};


// 通达信插件接口函数
#ifdef __cplusplus
extern "C" {
#endif

// 插件信息
__declspec(dllexport) const char* __stdcall TDXPlugin_GetInfo();
__declspec(dllexport) int __stdcall TDXPlugin_Init();

// 主计算函数
__declspec(dllexport) int __stdcall TDXPlugin_Calculate(
    int nCount,                     // K线数量
    float* pOpen,                   // 开盘价数组
    float* pHigh,                   // 最高价数组
    float* pLow,                    // 最低价数组
    float* pClose,                  // 收盘价数组
    float* pVolume,                 // 成交量数组
    int* pDate,                     // 日期数组
    int nPeriod,                    // 周期类型
    int* pOutCount,                 // 输出数量
    float** ppOutData1,             // 输出数据1（笔）
    float** ppOutData2,             // 输出数据2（线段）
    char*** ppOutText               // 输出文本
);

// 绘图函数
__declspec(dllexport) int __stdcall TDXPlugin_Draw(
    HDC hDC,                        // 设备上下文
    RECT* pRect,                    // 绘图区域
    int nCount,                     // K线数量
    float* pOpen,                   // 开盘价数组
    float* pHigh,                   // 最高价数组
    float* pLow,                    // 最低价数组
    float* pClose,                  // 收盘价数组
    int* pDate,                     // 日期数组
    int nPeriod                     // 周期类型
);

#ifdef __cplusplus
}
#endif