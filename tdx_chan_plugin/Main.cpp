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
// 性能配置：只处理最近 N 根K线，防止历史K线过多导致卡死
//=============================================================================
static const int MAX_PROCESS_COUNT = 4000; // 最大处理K线数量，超过则截断

//=============================================================================
// 辅助结构体：数据窗口
//=============================================================================
struct DataWindow {
    std::vector<KLine> klines;  // 截断后的K线数据
    int startIdx;               // 在原数组中的起始位置
    int processCount;           // 实际处理的数量
};

//=============================================================================
// 通用数据准备函数：截断数据到最近 MAX_PROCESS_COUNT 根K线
//=============================================================================
static DataWindow prepareDataWindow(int nCount, float* pHigh, float* pLow,
                                    float* pOpen = nullptr, float* pClose = nullptr,
                                    float* pVolume = nullptr, int* pDate = nullptr)
{
    DataWindow dw;
    dw.processCount = (nCount < MAX_PROCESS_COUNT) ? nCount : MAX_PROCESS_COUNT;
    dw.startIdx = (nCount > MAX_PROCESS_COUNT) ? (nCount - MAX_PROCESS_COUNT) : 0;
    dw.klines.reserve(dw.processCount);

    for (int i = 0; i < dw.processCount; i++) {
        int idx = dw.startIdx + i;
        KLine k;
        k.date = (pDate != nullptr) ? pDate[idx] : idx;
        k.open = (pOpen != nullptr) ? pOpen[idx] : 0.0f;
        k.high = pHigh[idx];
        k.low = pLow[idx];
        k.close = (pClose != nullptr) ? pClose[idx] : 0.0f;
        k.volume = (pVolume != nullptr) ? pVolume[idx] : 0.0f;
        k.gap = 0;
        k.gap_start = 0.0;
        k.gap_end = 0.0;
        dw.klines.push_back(k);
    }
    return dw;
}

//=============================================================================
// 辅助函数：将ChanAnalyzer的笔数据转换为输出数组（支持索引偏移映射）
// bi_list 中的 start_index/end_index 是截断数据内的原始索引（real_loc），
// 需要加上 startOffset 才能映射到通达信原始数组位置
//=============================================================================
static void convertBiToOutputWithOffset(const std::vector<Bi>& bi_list, float* pOut, int nCount, int startOffset)
{
    memset(pOut, 0, nCount * sizeof(float));
    for (const auto& bi : bi_list) {
        int origStart = startOffset + bi.start_index;
        int origEnd = startOffset + bi.end_index;
        if (origStart >= 0 && origStart < nCount) {
            pOut[origStart] = (bi.type == TOP) ? 1.0f : -1.0f;
        }
        if (origEnd >= 0 && origEnd < nCount) {
            pOut[origEnd] = (bi.type == TOP) ? 1.0f : -1.0f;
        }
    }
}

//=============================================================================
// 辅助函数：将ChanAnalyzer的线段数据转换为输出数组（支持索引偏移映射）
// 输出值为 ±1，与通达信公式 DRAWLINE 兼容
//=============================================================================
static void convertXianDuanToOutputWithOffset(const std::vector<XianDuan>& xd_list, float* pOut, int nCount, int startOffset)
{
    memset(pOut, 0, nCount * sizeof(float));
    for (const auto& xd : xd_list) {
        int origStart = startOffset + xd.start_index;
        int origEnd = startOffset + xd.end_index;
        if (origStart >= 0 && origStart < nCount) {
            pOut[origStart] = (xd.type == TOP) ? 1.0f : -1.0f;
        }
        if (origEnd >= 0 && origEnd < nCount) {
            pOut[origEnd] = (xd.type == TOP) ? 1.0f : -1.0f;
        }
    }
}

//=============================================================================
// 输出函数1号：标准笔顶底端点（使用ChanAnalyzer + 数据截断）
// 输出值：顶分型=+1.0，底分型=-1.0
//=============================================================================
void Func1(int nCount, float *pOut, float *pHigh, float *pLow, float *pIgnore)
{
    if (nCount <= 0 || pOut == nullptr || pHigh == nullptr || pLow == nullptr) {
        return;
    }

    // 1. 准备截断后的数据窗口
    DataWindow dw = prepareDataWindow(nCount, pHigh, pLow);

    // 2. 创建分析器并分析
    ChanAnalyzer analyzer(false);
    analyzer.setData(dw.klines);
    analyzer.analyze();

    // 3. 获取笔结果并映射回原数组位置
    std::vector<Bi> bi_list = analyzer.getBi();
    convertBiToOutputWithOffset(bi_list, pOut, nCount, dw.startIdx);
}

//=============================================================================
// 输出函数2号：线段端点（使用ChanAnalyzer真正线段算法 + 数据截断）
// 输出值：线段顶=+1.0，线段底=-1.0
//=============================================================================
void Func2(int nCount, float *pOut, float *pIn, float *pHigh, float *pLow)
{
    if (nCount <= 0 || pOut == nullptr || pHigh == nullptr || pLow == nullptr) {
        return;
    }

    // 1. 准备截断后的数据窗口
    DataWindow dw = prepareDataWindow(nCount, pHigh, pLow);

    // 2. 创建分析器并分析（获取真正线段）
    ChanAnalyzer analyzer(false);
    analyzer.setData(dw.klines);
    analyzer.analyze();

    // 3. 获取线段结果并映射回原数组位置
    std::vector<XianDuan> xd_list = analyzer.getXianDuan();
    convertXianDuanToOutputWithOffset(xd_list, pOut, nCount, dw.startIdx);
}

//=============================================================================
// 函数注册表 - 只注册笔和线段两个核心函数
//=============================================================================
static PluginTCalcFuncInfo Info[] =
    {
        {1, &Func1},  // 标准笔端点（顶=+1，底=-1）
        {2, &Func2},  // 线段端点（顶=+1，底=-1）
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
    return "TDX Chan Theory Plugin v2.0 - Bi and XianDuan Analysis";
}

//=============================================================================
// 通达信插件初始化函数
//=============================================================================
extern "C" __declspec(dllexport) int __stdcall TDXPlugin_Init()
{
    return 0; // 成功
}

//=============================================================================
// 通达信内存释放函数
//=============================================================================
extern "C" __declspec(dllexport) void __stdcall TDXPlugin_FreeMemory(float* pData)
{
    if (pData != nullptr) {
        delete[] pData;
    }
}

//=============================================================================
// 通达信主计算函数 - 统一使用 MAX_PROCESS_COUNT 截断
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

    // 使用统一的数据窗口准备（截断保护）
    DataWindow dw = prepareDataWindow(nCount, pHigh, pLow, pOpen, pClose, pVolume, pDate);

    // 创建分析器并分析
    ChanAnalyzer analyzer(false);
    analyzer.setData(dw.klines);
    analyzer.analyze();

    // 获取笔和线段数据
    std::vector<Bi> bi_list = analyzer.getBi();
    std::vector<XianDuan> xd_list = analyzer.getXianDuan();

    // 分配输出缓冲区 - 分配完整nCount大小
    if (ppOutData1 != nullptr) {
        *ppOutData1 = new float[nCount];
        memset(*ppOutData1, 0, nCount * sizeof(float));
        convertBiToOutputWithOffset(bi_list, *ppOutData1, nCount, dw.startIdx);
    }

    if (ppOutData2 != nullptr) {
        *ppOutData2 = new float[nCount];
        memset(*ppOutData2, 0, nCount * sizeof(float));
        convertXianDuanToOutputWithOffset(xd_list, *ppOutData2, nCount, dw.startIdx);
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
