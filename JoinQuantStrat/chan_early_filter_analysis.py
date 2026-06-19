# -*- coding: utf-8 -*-
"""
聚宽研究环境调用缠论早期过滤器

============================================================
使用前必须上传以下 4 个文件到聚宽研究环境:
  1. chan_early_filter.py   (Utility\chan_early_filter.py)
  2. chan_kbar_filter.py    (Utility\chan_kbar_filter.py)
  3. biaoLiStatus.py        (Utility\biaoLiStatus.py)
  4. chan_common_include.py (Utility\chan_common_include.py)

还需上传:
  5. tomorrow_candiate_list.txt (每行一只股票代码, #开头为注释)
============================================================
"""

from chan_early_filter import filter_chan_early

# ==================== 检查级别配置 (可自行调整) ====================
CHECK_LEVEL_UP = ["1m", "5m", "30m", "60m", "1d"]
CHECK_LEVEL_DOWN = ["1d"]

# ==================== 1. 读取候选股票列表 ====================
filename = 'tomorrow_candidate_list.txt'
try:
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # 清洗: 去掉空白、空行、注释行
    candidate_list = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            candidate_list.append(line)
    print("从 {0} 读取到 {1} 只候选股票".format(filename, len(candidate_list)))
    print("候选股票: {0}".format(candidate_list))
except Exception as e:
    print("读取文件失败: {0}".format(e))
    # fallback 测试数据
    candidate_list = ['000001.XSHE', '000002.XSHE', '600000.XSHG']
    print("使用默认测试列表: {0}".format(candidate_list))

print()

# ==================== 2. 执行缠论早期过滤 ====================
filtered = filter_chan_early(candidate_list,
                             check_level_up=CHECK_LEVEL_UP,
                             check_level_down=CHECK_LEVEL_DOWN)

# ==================== 3. 输出结果 ====================
print()
print("=" * 40)
print("最终结果: {0} 只股票通过过滤".format(len(filtered)))
print("=" * 40)
for stock in filtered:
    print(stock)

# 可选: 保存结果到文件
output_filename = 'chan_filtered_result.txt'
try:
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(filtered))
    print("\n结果已保存到: {0}".format(output_filename))
except Exception as e:
    print("\n保存结果失败: {0}".format(e))
