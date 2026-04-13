// test_main.cpp - 缠论算法测试程序
// 用于测试ChanAnalyzer的核心算法

#include "ChanPlugin.h"
#include <iostream>
#include <vector>
#include <random>

// 生成随机K线数据用于测试
std::vector<KLine> generateTestData(int count) {
    std::vector<KLine> data;
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_real_distribution<> price_dist(100.0, 200.0);
    std::uniform_real_distribution<> range_dist(0.5, 2.0);
    
    double current_price = 150.0;
    
    for (int i = 0; i < count; i++) {
        KLine kline;
        kline.date = 20240101 + i;
        kline.open = current_price;
        
        // 随机生成高低点
        double range = range_dist(gen);
        kline.high = current_price + range;
        kline.low = current_price - range;
        
        // 随机决定收盘价
        std::uniform_real_distribution<> close_dist(kline.low, kline.high);
        kline.close = close_dist(gen);
        
        kline.volume = 1000000.0;
        kline.gap = 0;
        kline.gap_start = 0;
        kline.gap_end = 0;
        
        data.push_back(kline);
        
        // 更新当前价格
        current_price = kline.close;
    }
    
    return data;
}

// 测试标准化函数
void testStandardize() {
    std::cout << "=== 测试标准化函数 ===" << std::endl;
    
    ChanAnalyzer analyzer(true); // 启用调试模式
    
    // 生成测试数据
    std::vector<KLine> testData = generateTestData(20);
    analyzer.setData(testData);
    
    // 调用分析
    analyzer.analyze();
    
    // 获取标准化数据
    auto standardized = analyzer.getStandardized();
    
    std::cout << "原始数据数量: " << testData.size() << std::endl;
    std::cout << "标准化后数量: " << standardized.size() << std::endl;
    
    if (!standardized.empty()) {
        std::cout << "前5个标准化K线:" << std::endl;
        for (int i = 0; i < std::min(5, (int)standardized.size()); i++) {
            const auto& kline = standardized[i];
            std::cout << "  日期: " << kline.date 
                      << ", 高: " << kline.high 
                      << ", 低: " << kline.low
                      << ", 分型: " << kline.tb << std::endl;
        }
    }
    
    std::cout << std::endl;
}

// 测试笔识别
void testBiRecognition() {
    std::cout << "=== 测试笔识别 ===" << std::endl;
    
    ChanAnalyzer analyzer(true);
    
    // 生成有趋势的测试数据（上升趋势）
    std::vector<KLine> trendData;
    double price = 100.0;
    
    for (int i = 0; i < 30; i++) {
        KLine kline;
        kline.date = 20240101 + i;
        
        // 创建上升趋势
        price += (i % 5 == 0 ? -2.0 : 3.0); // 每5根回调一次
        
        kline.open = price;
        kline.high = price + 1.5;
        kline.low = price - 1.0;
        kline.close = price + 0.5;
        kline.volume = 1000000.0;
        kline.gap = 0;
        kline.gap_start = 0;
        kline.gap_end = 0;
        
        trendData.push_back(kline);
    }
    
    analyzer.setData(trendData);
    analyzer.analyze();
    
    auto bi_list = analyzer.getBi();
    
    std::cout << "识别到的笔数量: " << bi_list.size() << std::endl;
    
    for (size_t i = 0; i < bi_list.size(); i++) {
        const auto& bi = bi_list[i];
        std::cout << "笔 " << i + 1 << ":" << std::endl;
        std::cout << "  类型: " << (bi.type == TOP ? "顶分型" : "底分型") << std::endl;
        std::cout << "  起始日期: " << bi.start_date 
                  << ", 价格: " << bi.start_price << std::endl;
        std::cout << "  结束日期: " << bi.end_date
                  << ", 价格: " << bi.end_price << std::endl;
        std::cout << "  幅度: " << (bi.end_price - bi.start_price) << std::endl;
    }
    
    std::cout << std::endl;
}

// 测试缺口检测
void testGapDetection() {
    std::cout << "=== 测试缺口检测 ===" << std::endl;
    
    std::vector<KLine> gapData;
    
    // 创建有缺口的数据
    for (int i = 0; i < 10; i++) {
        KLine kline;
        kline.date = 20240101 + i;
        
        if (i == 5) {
            // 在第6根K线创建向上缺口
            kline.open = 120.0;
            kline.low = 119.5;
            kline.high = 122.0;
            kline.close = 121.5;
        } else {
            double base = 100.0 + i * 2.0;
            kline.open = base;
            kline.low = base - 1.0;
            kline.high = base + 1.0;
            kline.close = base + 0.5;
        }
        
        kline.volume = 1000000.0;
        kline.gap = 0;
        kline.gap_start = 0;
        kline.gap_end = 0;
        
        gapData.push_back(kline);
    }
    
    ChanAnalyzer analyzer(true);
    analyzer.setData(gapData);
    
    // 注意：当前的C++版本可能还没有完全实现缺口检测
    // 这里主要是为了测试接口
    
    std::cout << "创建了" << gapData.size() << "根K线，其中第6根有向上缺口" << std::endl;
    
    // 我们可以手动检查缺口
    if (gapData.size() > 5) {
        const KLine& prev = gapData[4];  // 第5根
        const KLine& current = gapData[5]; // 第6根
        
        if (float_less(prev.high, current.low - MIN_PRICE_UNIT)) {
            std::cout << "检测到向上缺口: " << prev.high << " -> " << current.low << std::endl;
        }
    }
    
    std::cout << std::endl;
}

// 测试浮点数比较函数
void testFloatComparison() {
    std::cout << "=== 测试浮点数比较 ===" << std::endl;
    
    double a = 100.0;
    double b = 100.01;
    double c = 100.02;
    
    std::cout << "a = " << a << ", b = " << b << ", c = " << c << std::endl;
    std::cout << "float_less(a, b): " << float_less(a, b) << " (期望: 1)" << std::endl;
    std::cout << "float_less(b, a): " << float_less(b, a) << " (期望: 0)" << std::endl;
    std::cout << "float_more(c, b): " << float_more(c, b) << " (期望: 1)" << std::endl;
    std::cout << "float_less_equal(a, b): " << float_less_equal(a, b) << " (期望: 1)" << std::endl;
    std::cout << "float_more_equal(b, a): " << float_more_equal(b, a) << " (期望: 1)" << std::endl;
    
    // 测试精度边界
    double d = 100.005;
    double e = 100.015;
    std::cout << "\nd = " << d << ", e = " << e << " (相差0.01)" << std::endl;
    std::cout << "float_less(d, e): " << float_less(d, e) << std::endl;
    std::cout << "float_more(e, d): " << float_more(e, d) << std::endl;
    
    std::cout << std::endl;
}

int main() {
    std::cout << "缠论算法测试程序" << std::endl;
    std::cout << "=================" << std::endl << std::endl;
    
    testFloatComparison();
    testStandardize();
    testBiRecognition();
    testGapDetection();
    
    std::cout << "测试完成!" << std::endl;
    
    return 0;
}