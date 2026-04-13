// TDXPlugin.cpp - 通达信缠论DLL指标插件
// 最小化实现，仅保留通达信标准接口

#include "ChanPlugin.h"
#include <vector>

// 全局分析器实例
static ChanAnalyzer g_analyzer;
static std::vector<KLine> g_klines;

// ============================================================================
// 通达信DLL标准接口
// ============================================================================

// 通达信DLL标准计算函数
// DataLen: K线数量
// pfOUT: 输出数组
// nParamCount: 参数数量
// pfPARAM: 参数值
// pfReserve: 保留参数
extern "C" __declspec(dllexport) int __stdcall Plugin2(
    int DataLen,
    float *pfOUT,
    int nParamCount,
    float *pfPARAM)
{
    // 初始化输出
    for (int i = 0; i < DataLen; i++) {
        pfOUT[i] = -1e10f;
    }
    
    return 1;
}

// CalcN - 通达信标准计算函数
// DataLen: K线数量
// pfOUT: 输出数组 (长度=DataLen)
// pfIN: 输入数据 (OPEN,HIGH,LOW,CLOSE,VOL,AMOUNT,DATE)
// nParamCount: 参数数量
// pfPARAM: 参数值
// nReserved: 保留参数
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
    
    // 初始化输出
    for (int i = 0; i < DataLen; i++) {
        pfOUT[i] = -1e10f;
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
    
    std::vector<Bi> bi_list = g_analyzer.getBi();
    
    // 写入笔数据到输出
    for (const auto& bi : bi_list) {
        for (int i = 0; i < DataLen; i++) {
            if (g_klines[i].date == bi.start_date) {
                pfOUT[i] = static_cast<float>(bi.start_price);
            }
            if (g_klines[i].date == bi.end_date) {
                pfOUT[i] = static_cast<float>(bi.end_price);
            }
        }
    }
    
    return 1;
}

// 通达信DLL入口点
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    (void)hModule;
    (void)lpReserved;
    switch (ul_reason_for_call) {
        case DLL_PROCESS_ATTACH:
        case DLL_PROCESS_DETACH:
        case DLL_THREAD_ATTACH:
        case DLL_THREAD_DETACH:
            break;
    }
    return TRUE;
}