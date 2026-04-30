import os
import time
import json
from typing import List, Tuple
import requests

# 环境变量读取API Key
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY")
if not ZHIPU_API_KEY:
    raise ValueError("请在环境变量中设置 ZHIPU_API_KEY")

ZHIPU_MODEL = "glm-4-flash"

# 优化后的合规判断提示词
SYSTEM_PROMPT = """你是一名中国证券市场合规分析专家，你需要根据以下标准判断上市公司是否合规。

判断标准(符合任意一条即为"不合规"):
1. 被实施ST或*ST风险警示
2. 最近一会计年度净资产为负值
3. 最近一会计年度净利润为负值且营业收入低于3亿元(主板)/1亿元(科创板创业板)
4. 最近三年净利润为正但累计分红低于年均净利润30%且低于5000万元
5. 内控审计报告被出具否定意见或无法表示意见
6. 公司或实控人被证监会立案调查(尚在阶段)
7. 最近三年连续亏损超过2亿元且无明显改善
8. 经查实一年财务造假≥2亿且比例≥30%，或两年造假≥3亿且比例≥20%

重要: 必须基于最新可验证的信息进行判断(如财报、公告).最终只需输出一个JSON，包含以下字段:
{"code": "股票代码", "name": "股票简称", "is_qualified": true/false, "reason": "判断理由", "violated_rules": ["规则编号"]}
"""

def _call_zhipu_enhanced(code: str, name: str) -> Tuple[bool, str, List[str]]:
    """使用官方推荐的JSON模式调用API,提高结构输出准确性"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ZHIPU_API_KEY}"
    }

    payload = {
        "model": ZHIPU_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请判断股票{code}({name})目前的合规状况."}
        ],
        "temperature": 0.1,  # 保持一致性
        "response_format": {"type": "json_object"},  # 强制输出JSON(关键参数)
        "tools": [{
            "type": "web_search",
            "web_search": {
                "enable": True,
                "search_result": True
            }
        }],
        "tool_choice": "auto"
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"API错误 {resp.status_code}: {resp.text[:200]}")
            return False, f"HTTP {resp.status_code}", []

        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        # 提取JSON (可能因response_format直接返回)
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]

        result = json.loads(content)
        return (
            result.get("is_qualified", False),
            result.get("reason", "无理由"),
            result.get("violated_rules", [])
        )
    except Exception as e:
        print(f"❌ API调用失败: {e}")
        return False, f"异常: {e}", []

def filter_stocks(stock_list: List[str], delay: float = 0.8) -> List[str]:
    """
    筛选合规股票,保持原顺序
    stock_list: 支持["000001"]或["000001.sz"]格式
    """
    # 标准化函数(split去除后缀)
    def norm(code: str) -> str:
        return code.split('.')[0] if '.' in code else code

    original_map = {norm(raw): raw for raw in stock_list}
    normalized = list(original_map.keys())
    qualified = []

    print(f"\n筛选 {len(normalized)} 只股票,使用模型: {ZHIPU_MODEL}")
    for idx, code in enumerate(normalized, 1):
        print(f"[{idx}/{len(normalized)}] 分析 {code}...")
        is_qualified, reason, rules = _call_zhipu_enhanced(code, "待查")
        if is_qualified:
            print(f"  ✅ 保留: {reason[:50]}")
            qualified.append(code)
        else:
            print(f"  ❌ 剔除: {reason[:50]} | 违反规则: {rules}")
        if idx < len(normalized):
            time.sleep(delay)

    return [original_map[code] for code in qualified]

if __name__ == "__main__":
    test = ["000001.sz", "000858.sz", "600519.sh", "000639.sz"]
    result = filter_stocks(test)
    print(f"最终合规: {result}")