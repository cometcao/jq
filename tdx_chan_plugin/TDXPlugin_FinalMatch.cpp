// TDXPlugin_FinalMatch.cpp - 完全匹配TDXChanPlugin_Final.dll的导出顺序和结构
// 关键：函数定义的顺序必须与可绑定DLL完全一致

#include "ChanPlugin.h"
#include <vector>
#include <algorithm>
#include <windows.h>
#include <string.h>

// 全局分析器实例
static ChanAnalyzer g_analyzer;
static std::vector<KLine> g_klines;

// ============================================================================
// 通达信DLL标准接口 - 完全匹配Final版本
// ============================================================================

// ChanlunX兼容的函数指针类型
typedef void (*pPluginFUNC)(int nCount, float *pOut, float *a, float *b, float *c);

typedef struct tagPluginTCalcFuncInfo
{
    unsigned short nFuncMark; // 函数编号
    pPluginFUNC pCallFunc;    // 函数地址
} PluginTCalcFuncInfo;

// ============================================================================
// 函数定义顺序必须完全匹配TDXChanPlugin_Final.dll
// 导出顺序：0: Plugin2, 1: CalcN, 2: RegisterTdxFunc, 3: Func1, 4: Func2, ...
// ============================================================================

// 函数声明（需要在RegisterTdxFunc之前声明）
extern "C" __declspec(dllexport) void Func1(int nCount, float *pOut, float *pHigh, float *pLow, float *pIgnore);
extern "C" __declspec(dllexport) void Func2(int nCount, float *pOut, float *pIn, float *pHigh, float *pLow);
extern "C" __declspec(dllexport) void Func3(int nCount, float *pOut, float *pHigh, float *pLow, float *pIgnore);
extern "C" __declspec(dllexport) void Func4(int nCount, float *pOut, float *pIn, float *pHigh, float *pLow);
extern "C" __declspec(dllexport) void Func5(int nCount, float *pOut, float *a, float *b, float *c);
extern "C" __declspec(dllexport) void Func6(int nCount, float *pOut, float *a, float *b, float *c);
extern "C" __declspec(dllexport) void Func7(int nCount, float *pOut, float *a, float *b, float *c);
extern "C" __declspec(dllexport) void Func8(int nCount, float *pOut, float *a, float *b, float *c);
extern "C" __declspec(dllexport) void Func9(int nCount, float *pOut, float *a, float *b, float *c);

// ============================================================================
// 函数0：Plugin2 - 必须是第0个导出函数（索引0）
// ============================================================================
extern "C" __declspec(dllexport) int __stdcall Plugin2(
    int DataLen,
    float *pfOUT,
    int nParamCount,
    float *pfPARAM)
{
    if (DataLen <= 0 || pfOUT == nullptr || pfPARAM == nullptr || nParamCount < 1) {
        return 0;
    }
    
    int func_no = static_cast<int>(pfPARAM[0]);
    
    // 初始化输出
    for (int i = 0; i < DataLen; i++) {
        pfOUT[i] = 0.0f;
    }
    
    if (func_no == 1) {
        // 输出笔端点
        std::vector<Bi> bi_list = g_analyzer.getBi();
        for (const auto& bi : bi_list) {
            for (int i = 0; i < DataLen; i++) {
                if (g_klines[i].date == bi.start_date) {
                    pfOUT[i] = static_cast<float>(bi.type == TOP ? 1.0f : -1.0f);
                }
                if (g_klines[i].date == bi.end_date) {
                    pfOUT[i] = static_cast<float>(bi.type == TOP ? 1.0f : -1.0f);
                }
            }
        }
    } 
    else if (func_no == 2) {
        // 输出线段端点
        std::vector<XianDuan> xd_list = g_analyzer.getXianDuan();
        for (const auto& xd : xd_list) {
            for (int i = 0; i < DataLen; i++) {
                if (g_klines[i].date == xd.start_date) {
                    pfOUT[i] = static_cast<float>(xd.type == TOP ? 1.0f : -1.0f);
                }
                if (g_klines[i].date == xd.end_date) {
                    pfOUT[i] = static_cast<float>(xd.type == TOP ? 1.0f : -1.0f);
                }
            }
        }
    }
    
    return 1;
}

// ============================================================================
// 函数1：CalcN - 必须是第1个导出函数（索引1）
// ============================================================================
extern "C" __declspec(dllexport) int __stdcall CalcN(
    int DataLen,
    float *pfOUT,
    float *pfIN,
    int nParamCount,
    float *pfPARAM,
    int nReserved)
{
    if (DataLen <= 0 || pfOUT == nullptr || pfIN == nullptr) {
        return 0;
    }
    
    // 初始化输出（笔端点标记）
    for (int i = 0; i < DataLen; i++) {
        pfOUT[i] = 0.0f;
    }
    
    // 准备K线数据
    g_klines.resize(DataLen);
    const int FIELDS = 7;
    for (int i = 0; i < DataLen; i++) {
        g_klines[i].open = pfIN[i * FIELDS + 0];
        g_klines[i].high = pfIN[i * FIELDS + 1];
        g_klines[i].low  = pfIN[i * FIELDS + 2];
        g_klines[i].close = pfIN[i * FIELDS + 3];
        g_klines[i].volume = pfIN[i * FIELDS + 4];
        g_klines[i].date = (int)pfIN[i * FIELDS + 6];
        g_klines[i].gap = 0;
        g_klines[i].gap_start = 0;
        g_klines[i].gap_end = 0;
    }
    
    // 执行缠论分析
    g_analyzer.setData(g_klines);
    g_analyzer.analyze();
    
    // 输出笔端点（顶分型=1，底分型=-1）
    std::vector<Bi> bi_list = g_analyzer.getBi();
    for (const auto& bi : bi_list) {
        for (int i = 0; i < DataLen; i++) {
            if (g_klines[i].date == bi.start_date || g_klines[i].date == bi.end_date) {
                pfOUT[i] = static_cast<float>(bi.type == TOP ? 1.0f : -1.0f);
            }
        }
    }
    
    return 1;
}

// ============================================================================
// 函数2：RegisterTdxFunc - 必须是第2个导出函数（索引2）
// ============================================================================

// 函数注册表
static PluginTCalcFuncInfo Info[] =
{
    {1, &Func1},  // 函数编号1
    {2, &Func2},  // 函数编号2  
    {3, &Func3},  // 函数编号3
    {4, &Func4},  // 函数编号4
    {0, NULL}     // 结束标记
};

extern "C" __declspec(dllexport) BOOL RegisterTdxFunc(PluginTCalcFuncInfo **pInfo)
{
    if (*pInfo == NULL)
    {
        *pInfo = Info;
        return TRUE;
    }
    
    return FALSE;
}

// ============================================================================
// 函数3-11：Func1-9 - 必须是第3-11个导出函数
// ============================================================================

// 函数3：Func1
extern "C" __declspec(dllexport) void Func1(int nCount, float *pOut, float *pHigh, float *pLow, float *pIgnore)
{
    memset(pOut, 0, nCount * sizeof(float));
    if (nCount <= 0) return;
    
    std::vector<Bi> bi_list = g_analyzer.getBi();
    for (const auto& bi : bi_list) {
        for (int i = 0; i < nCount; i++) {
            if (i < static_cast<int>(g_klines.size()) && 
                g_klines[i].date == bi.start_date) {
                pOut[i] = static_cast<float>(bi.type == TOP ? 1.0f : -1.0f);
            }
        }
    }
}

// 函数4：Func2
extern "C" __declspec(dllexport) void Func2(int nCount, float *pOut, float *pIn, float *pHigh, float *pLow)
{
    memset(pOut, 0, nCount * sizeof(float));
    if (nCount <= 0) return;
    
    std::vector<XianDuan> xd_list = g_analyzer.getXianDuan();
    for (const auto& xd : xd_list) {
        for (int i = 0; i < nCount; i++) {
            if (i < static_cast<int>(g_klines.size()) && 
                g_klines[i].date == xd.start_date) {
                pOut[i] = static_cast<float>(xd.type == TOP ? 1.0f : -1.0f);
            }
        }
    }
}

// 函数5：Func3
extern "C" __declspec(dllexport) void Func3(int nCount, float *pOut, float *pHigh, float *pLow, float *pIgnore)
{
    Func1(nCount, pOut, pHigh, pLow, pIgnore);
}

// 函数6：Func4
extern "C" __declspec(dllexport) void Func4(int nCount, float *pOut, float *pIn, float *pHigh, float *pLow)
{
    memset(pOut, 0, nCount * sizeof(float));
}

// 函数7：Func5
extern "C" __declspec(dllexport) void Func5(int nCount, float *pOut, float *a, float *b, float *c) 
{
    memset(pOut, 0, nCount * sizeof(float));
}

// 函数8：Func6
extern "C" __declspec(dllexport) void Func6(int nCount, float *pOut, float *a, float *b, float *c) 
{
    memset(pOut, 0, nCount * sizeof(float));
}

// 函数9：Func7
extern "C" __declspec(dllexport) void Func7(int nCount, float *pOut, float *a, float *b, float *c) 
{
    memset(pOut, 0, nCount * sizeof(float));
}

// 函数10：Func8
extern "C" __declspec(dllexport) void Func8(int nCount, float *pOut, float *a, float *b, float *c) 
{
    memset(pOut, 0, nCount * sizeof(float));
}

// 函数11：Func9
extern "C" __declspec(dllexport) void Func9(int nCount, float *pOut, float *a, float *b, float *c) 
{
    memset(pOut, 0, nCount * sizeof(float));
}

// ============================================================================
// DLL入口点
// ============================================================================
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
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