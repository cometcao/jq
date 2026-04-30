import os
import time
import json
from typing import List, Tuple
import requests

# ==================== 配置 ====================
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY")
if not ZHIPU_API_KEY:
    raise ValueError("请在环境变量中设置 ZHIPU_API_KEY")

ZHIPU_MODEL = "glm-4-flash"
# ============================================

SYSTEM_PROMPT = """你是一名中国证券市场合规分析专家。请严格按照以下规则判断上市公司是否合规。

【黄金原则】  
- 只有当你获取到明确、可信的证据（例如财报、公告、监管通报）证明该股票触犯以下某条标准时，才能判定为“不合规”。  
- 如果信息缺失、不确定或未找到任何违规证据，必须判定为“合规”。  
- 严禁在无法确认具体标准时，将“不合规”作为默认答案或列出全部规则。

【判定细则】  
只要满足以下**任意一条**且证据确凿，即为“不合规”（is_qualified = false），并在 violated_rules 中列出对应的规则编号。  
若所有标准均不满足或信息不足，则判定为“合规”（is_qualified = true）。

1. 被实施ST或*ST风险警示  
2. 最近一会计年度经审计净资产为负值  
3. 最近一会计年度净利润为负值且营业收入低于3亿元（主板）/1亿元（科创板、创业板）  
4. 最近三个会计年度净利润均为正，但累计现金分红低于年均净利润30%且低于5000万元  
5. 内控审计报告被出具否定意见或无法表示意见  
6. 公司或实际控制人因信息披露违法违规被证监会立案调查（尚未结案阶段）  
7. 最近三个会计年度连续亏损超过2亿元且无明显改善迹象  
8. 经查实存在重大财务造假：一年造假金额≥2亿元且占当期披露利润比例≥30%，或连续两年造假金额合计≥3亿元且比例≥20%

【输出格式】  
- 必须输出一个JSON对象，不得包含任何其他解释性文字。  
- JSON格式：  
  {"code": "股票代码", "name": "股票简称", "is_qualified": true/false, "reason": "判断理由", "violated_rules": ["规则编号"]}  
- 当 is_qualified = false 时，violated_rules 必须为非空数组，reason 需明确指出触犯了哪条标准及证据来源。  
- 当 is_qualified = true 时，violated_rules 为空数组，reason 可简述为“信息不足，未发现违规证据”或“各项指标正常”。
"""

def _call_zhipu(code: str, name: str, debug: bool = False) -> Tuple[bool, str, List[str]]:
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ZHIPU_API_KEY}"
    }
    payload = {
        "model": ZHIPU_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请判断股票{code}({name})目前的合规状况。请务必开启联网搜索获取最新信息。"}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
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
            print(f"  API错误 {resp.status_code}: {resp.text[:200]}")
            return False, f"HTTP {resp.status_code}", []

        data = resp.json()
        if debug:
            # 只打印核心内容，避免日志过长
            print(f"  [DEBUG] 模型输出: {data['choices'][0]['message']['content'][:200]}")

        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        result = json.loads(content)
        is_qualified = result.get("is_qualified", False)
        reason = result.get("reason", "无理由")
        violated = result.get("violated_rules", [])

        # 防御：不合规但无具体规则 → 强制合规
        if not is_qualified and len(violated) == 0:
            return True, reason + "（模型未提供违规规则，按合规处理）", []

        # 防御：不合规且规则包含全部8条 → 视为模型异常，改为合规
        if not is_qualified and set(violated) == {"1","2","3","4","5","6","7","8"}:
            return True, "模型输出异常（列出全部规则），按信息不足处理", []

        return is_qualified, reason, violated

    except Exception as e:
        print(f"  ❌ API调用失败: {e}")
        return False, f"调用异常: {e}", []


def filter_stocks(stock_list: List[str], delay: float = 0.8, debug: bool = False) -> List[str]:
    """
    筛选合规股票，保持原顺序。
    stock_list: 支持 ["000001"] 或 ["000001.sz"] 格式
    delay: 两次调用间隔（秒），避免限流
    debug: 是否打印API原始返回摘要
    """
    def norm(code: str) -> str:
        return code.split('.')[0] if '.' in code else code

    original_map = {norm(raw): raw for raw in stock_list}
    normalized = list(original_map.keys())
    qualified = []

    print(f"\n筛选 {len(normalized)} 只股票，模型: {ZHIPU_MODEL}（联网搜索已启用）")
    if debug:
        print("DEBUG模式已开启")
    print("-" * 60)

    for idx, code in enumerate(normalized, 1):
        print(f"[{idx}/{len(normalized)}] 分析 {code}...")
        is_qualified, reason, rules = _call_zhipu(code, "待查", debug=debug)

        if is_qualified:
            print(f"  ✅ 保留: {reason[:80]}")
            qualified.append(code)
        else:
            print(f"  ❌ 剔除: {reason[:80]} | 违反规则: {rules}")
        if idx < len(normalized):
            time.sleep(delay)

    print("-" * 60)
    print(f"筛选完成，{len(qualified)}/{len(normalized)} 只股票合规。")
    return [original_map[code] for code in qualified]


if __name__ == "__main__":
    test = ["000001.sz", "000858.sz", "600519.sh", "000639.sz"]
    # 日常使用 debug=False，调试时改为 True
    result = filter_stocks(test, delay=0.8, debug=False)
    print(f"\n最终合规股票池（保持原顺序）: {result}")