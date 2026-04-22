#include "ChanPlugin.h"
#include <vector>
#include <algorithm>
#include <cstring>
#include <memory>

// 定义DLL程序的入口函数
BOOL APIENTRY DllMain(HANDLE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    switch (ul_reason_for_call)
    {
    case DLL_PROCESS_ATTACH:
    case DLL_THREAD_ATTACH:
    case DLL_THREAD_DETACH:
    case DLL_PROCESS_DETACH:
        break;
    }
    return TRUE;
}

// 通达信函数指针类型和注册结构体（必须与ChanlunX完全一致）
typedef void (*pPluginFUNC)(int nCount, float *pOut, float *a, float *b, float *c);

#pragma pack(push, 1)
typedef struct tagPluginTCalcFuncInfo
{
    unsigned short nFuncMark; // 函数编号
    pPluginFUNC pCallFunc;    // 函数地址
} PluginTCalcFuncInfo;
#pragma pack(pop)

//=============================================================================
// 辅助函数：将ChanAnalyzer的笔数据转换为输出数组
//=============================================================================
static void convertBiToOutput(const std::vector<Bi>& bi_list, float* pOut, int nCount)
{
    // 初始化输出为0
    memset(pOut, 0, nCount * sizeof(float));
    
    // 将笔端点标记到输出数组
    for (const auto& bi : bi_list) {
        int start_idx = bi.start_index;
        int end_idx = bi.end_index;
        
        if (start_idx >= 0 && start_idx < nCount) {
            // 笔起点：顶分型标记为1.0，底分型标记为-1.0
            pOut[start_idx] = (bi.type == TOP) ? 1.0f : -1.0f;
        }
        
        if (end_idx >= 0 && end_idx < nCount) {
            // 笔终点：顶分型标记为1.0，底分型标记为-1.0
            pOut[end_idx] = (bi.type == TOP) ? 1.0f : -1.0f;
        }
    }
}

//=============================================================================
// 辅助函数：将ChanAnalyzer的线段数据转换为输出数组
//=============================================================================
static void convertXianDuanToOutput(const std::vector<XianDuan>& xd_list, float* pOut, int nCount)
{
    // 初始化输出为0
    memset(pOut, 0, nCount * sizeof(float));
    
    // 将线段端点标记到输出数组
    for (const auto& xd : xd_list) {
        int start_idx = xd.start_index;
        int end_idx = xd.end_index;
        
        if (start_idx >= 0 && start_idx < nCount) {
            // 线段起点：顶分型标记为2.0，底分型标记为-2.0
            pOut[start_idx] = (xd.type == TOP) ? 2.0f : -2.0f;
        }
        
        if (end_idx >= 0 && end_idx < nCount) {
            // 线段终点：顶分型标记为2.0，底分型标记为-2.0
            pOut[end_idx] = (xd.type == TOP) ? 2.0f : -2.0f;
        }
    }
}

//=============================================================================
// 输出函数1号：输出简笔顶底端点
//=============================================================================
void Func1(int nCount, float *pOut, float *pHigh, float *pLow, float *pIgnore)
{
    if (nCount <= 0 || pOut == nullptr) return;
    
    // 初始化输出为0
    for (int i = 0; i < nCount; i++) {
        pOut[i] = 0.0f;
    }
    
    // 简化实现：当高价创3周期新高时标记为1，低价创3周期新低时标记为-1
    if (pHigh != nullptr && pLow != nullptr && nCount >= 3) {
        for (int i = 2; i < nCount; i++) {
            if (pHigh[i] > pHigh[i-1] && pHigh[i] > pHigh[i-2]) {
                pOut[i] = 1.0f;  // 顶分型
            } else if (pLow[i] < pLow[i-1] && pLow[i] < pLow[i-2]) {
                pOut[i] = -1.0f; // 底分型
            }
        }
    }
}

//=============================================================================
// 输出函数2号：输出标准笔顶底端点（使用ChanAnalyzer）
//=============================================================================
void Func2(int nCount, float *pOut, float *pHigh, float *pLow, float *pIgnore)
{
    if (nCount <= 0 || pOut == nullptr || pHigh == nullptr || pLow == nullptr) {
        return;
    }
    
    // 创建K线数据
    std::vector<KLine> klines;
    for (int i = 0; i < nCount; i++) {
        KLine kline;
        kline.date = i;  // 使用索引作为日期
        kline.open = 0.0;
        kline.high = pHigh[i];
        kline.low = pLow[i];
        kline.close = 0.0;
        kline.volume = 0.0;
        kline.gap = 0;
        kline.gap_start = 0.0;
        kline.gap_end = 0.0;
        klines.push_back(kline);
    }
    
    // 创建分析器并分析
    ChanAnalyzer analyzer(false);
    analyzer.setData(klines);
    analyzer.analyze();
    
    // 获取笔数据并转换
    std::vector<Bi> bi_list = analyzer.getBi();
    convertBiToOutput(bi_list, pOut, nCount);
}

//=============================================================================
// 输出函数3号：段端点（标准画法）
//=============================================================================
void Func3(int nCount, float *pOut, float *pIn, float *pHigh, float *pLow)
{
    if (nCount <= 0 || pOut == nullptr) return;
    
    // 初始化输出为0
    for (int i = 0; i < nCount; i++) {
        pOut[i] = 0.0f;
    }
    
    // 简化实现：基于笔端点识别线段端点
    // 实际算法应基于缠论线段定义
    if (pIn != nullptr && nCount >= 5) {
        for (int i = 4; i < nCount; i++) {
            // 简化逻辑：当连续3个同向笔端点时标记为线段端点
            if (pIn[i] == 2.0f && pIn[i-2] == 2.0f && pIn[i-4] == 2.0f) {
                pOut[i] = 3.0f;  // 线段顶
            } else if (pIn[i] == -2.0f && pIn[i-2] == -2.0f && pIn[i-4] == -2.0f) {
                pOut[i] = -3.0f; // 线段底
            }
        }
    }
}

//=============================================================================
// 输出函数4号：段端点（1+1终结画法）
//=============================================================================
void Func4(int nCount, float *pOut, float *pIn, float *pHigh, float *pLow)
{
    if (nCount <= 0 || pOut == nullptr) return;
    
    // 初始化输出为0
    for (int i = 0; i < nCount; i++) {
        pOut[i] = 0.0f;
    }
    
    // 简化实现：1+1终结画法
    // 实际算法应基于缠论1+1终结模式
    if (pIn != nullptr && nCount >= 3) {
        for (int i = 2; i < nCount; i++) {
            // 简化逻辑：笔端点模式变化时标记
            if (pIn[i] == 2.0f && pIn[i-1] == -2.0f && pIn[i-2] == 2.0f) {
                pOut[i] = 4.0f;  // 1+1终结顶
            } else if (pIn[i] == -2.0f && pIn[i-1] == 2.0f && pIn[i-2] == -2.0f) {
                pOut[i] = -4.0f; // 1+1终结底
            }
        }
    }
}

//=============================================================================
// 输出函数5号：输出线段端点（使用ChanAnalyzer）
//=============================================================================
void Func5(int nCount, float *pOut, float *pHigh, float *pLow, float *pIgnore)
{
    if (nCount <= 0 || pOut == nullptr || pHigh == nullptr || pLow == nullptr) {
        return;
    }
    
    // 创建K线数据
    std::vector<KLine> klines;
    for (int i = 0; i < nCount; i++) {
        KLine kline;
        kline.date = i;  // 使用索引作为日期
        kline.open = 0.0;
        kline.high = pHigh[i];
        kline.low = pLow[i];
        kline.close = 0.0;
        kline.volume = 0.0;
        kline.gap = 0;
        kline.gap_start = 0.0;
        kline.gap_end = 0.0;
        klines.push_back(kline);
    }
    
    // 创建分析器并分析
    ChanAnalyzer analyzer(false);
    analyzer.setData(klines);
    analyzer.analyze();
    
    // 获取线段数据并转换
    std::vector<XianDuan> xd_list = analyzer.getXianDuan();
    convertXianDuanToOutput(xd_list, pOut, nCount);
}

//=============================================================================
// 函数注册表 - 包含笔和线段函数
//=============================================================================
static PluginTCalcFuncInfo Info[] =
    {
        {1, &Func1},  // 简笔端点
        {2, &Func2},  // 标准笔端点（使用ChanAnalyzer）
        {3, &Func3},  // 段端点（标准画法）
        {4, &Func4},  // 段端点（1+1终结画法）
        {5, &Func5},  // 线段端点（使用ChanAnalyzer）
        {0, NULL}     // 结束标记
    };

//=============================================================================
// 通达信插件注册函数 - 必须导出
//=============================================================================
extern "C" __declspec(dllexport) BOOL RegisterTdxFunc(PluginTCalcFuncInfo **pInfo)
{
    if (*pInfo == NULL)
    {
        *pInfo = Info;

        return TRUE;
    }

    return FALSE;
}

//=============================================================================
// 通达信插件信息函数
//=============================================================================
extern "C" __declspec(dllexport) const char* __stdcall TDXPlugin_GetInfo()
{
    return "TDX Chan Theory Plugin v1.0 - Pen and Line Segment Analysis";
}

//=============================================================================
// 通达信插件初始化函数
//=============================================================================
extern "C" __declspec(dllexport) int __stdcall TDXPlugin_Init()
{
    return 0; // 成功
}

//=============================================================================
// 通达信主计算函数
//=============================================================================
extern "C" __declspec(dllexport) int __stdcall TDXPlugin_Calculate(
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
)
{
    if (nCount <= 0 || pHigh == nullptr || pLow == nullptr) {
        return -1; // 参数错误
    }
    
    // 创建K线数据
    std::vector<KLine> klines;
    for (int i = 0; i < nCount; i++) {
        KLine kline;
        kline.date = (pDate != nullptr && i < nCount) ? pDate[i] : i;
        kline.open = (pOpen != nullptr && i < nCount) ? pOpen[i] : 0.0;
        kline.high = pHigh[i];
        kline.low = pLow[i];
        kline.close = (pClose != nullptr && i < nCount) ? pClose[i] : 0.0;
        kline.volume = (pVolume != nullptr && i < nCount) ? pVolume[i] : 0.0;
        kline.gap = 0;
        kline.gap_start = 0.0;
        kline.gap_end = 0.0;
        klines.push_back(kline);
    }
    
    // 创建分析器并分析
    ChanAnalyzer analyzer(false);
    analyzer.setData(klines);
    analyzer.analyze();
    
    // 获取笔和线段数据
    std::vector<Bi> bi_list = analyzer.getBi();
    std::vector<XianDuan> xd_list = analyzer.getXianDuan();
    
    // 分配输出缓冲区
    if (ppOutData1 != nullptr) {
        *ppOutData1 = new float[nCount];
        convertBiToOutput(bi_list, *ppOutData1, nCount);
    }
    
    if (ppOutData2 != nullptr) {
        *ppOutData2 = new float[nCount];
        convertXianDuanToOutput(xd_list, *ppOutData2, nCount);
    }
    
    if (pOutCount != nullptr) {
        *pOutCount = nCount;
    }
    
    // 文本输出（可选）
    if (ppOutText != nullptr) {
        *ppOutText = nullptr; // 暂不提供文本输出
    }
    
    return 0; // 成功
}