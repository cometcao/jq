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

// Floating point comparison functions (implementation matches KBar_Chan.py)
inline bool float_less(double a, double b, double epsilon = MIN_PRICE_UNIT) {
    return a < b - epsilon;
}

inline bool float_more(double a, double b, double epsilon = MIN_PRICE_UNIT) {
    return a > b + epsilon;
}

inline bool float_less_equal(double a, double b, double epsilon = MIN_PRICE_UNIT) {
    return a < b + epsilon;
}

inline bool float_more_equal(double a, double b, double epsilon = MIN_PRICE_UNIT) {
    return a > b - epsilon;
}

inline bool float_equal(double a, double b, double epsilon = MIN_PRICE_UNIT) {
    return std::abs(a - b) < epsilon;
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
    
    // Core helper functions
    std::vector<int> getNextNElem(int loc, const std::vector<StandardKLine>& working_df, int N = 4, TopBotType start_tb = NO_TOPBOT, bool single_direction = false);
    std::vector<int> getPreviousNElem(int loc, const std::vector<StandardKLine>& working_df, int N = 0, TopBotType end_tb = NO_TOPBOT, bool single_direction = true);
    bool directionAssert(const StandardKLine& elem, TopBotType direction);
    
    // Line segment (XD) Full implementations
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
    bool checkPreviousElemToAvoidXdGap(bool with_gap, const std::vector<int>& next_valid_elems, std::vector<StandardKLine>& working_df);
    
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
