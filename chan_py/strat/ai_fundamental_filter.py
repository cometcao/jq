# -*- coding: utf-8 -*-
import os
import time
import json
import re
from typing import List, Tuple
from dashscope import Generation
from zai import ZhipuAiClient

# ==================== 配置 ====================
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "").strip()
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "").strip()

if not DASHSCOPE_API_KEY:
    raise ValueError("请在环境变量中设置 DASHSCOPE_API_KEY")
if not ZHIPU_API_KEY:
    raise ValueError("请在环境变量中设置 ZHIPU_API_KEY")

# 阿里百炼模型优先级列表（免费额度充足）
QWEN_MODEL_LIST = [
    "qwen3-max",
    "qwen3-32b",
    "qwen3-plus",
    "qwen-turbo",
]
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
6. **公司或其董事、监事、高级管理人员、实际控制人**因涉嫌与上市公司**财务报告、信息披露、证券交易**相关的违法违规行为，被**证监会、证券交易所、纪委监委、公安机关等有权机关**正式**立案调查或采取留置措施**，且尚未结案。  
7. 最近三个会计年度归母净利润合计亏损超过2亿元，且最近一年度亏损额占前两年平均亏损额的比例 ≥ 80%  
8. 经证监会或其派出机构正式处罚或公告认定的重大财务造假  
9. 公司主动发布会计差错更正公告，且更正对最近一个已披露会计年度的净利润影响金额超过原披露净利润的20%  
10. 公司存在尚未结案的、涉案金额超过最近一期经审计净资产10%的重大诉讼

【输出格式】  
- 必须输出一个JSON对象，不得包含任何其他解释性文字。  
- JSON格式：  
  {"code": "股票代码", "name": "股票简称", "is_qualified": true/false, "reason": "判断理由", "violated_rules": ["规则编号"]}
"""

def _call_qwen(model: str, code: str, name: str, debug: bool = False):
    """调用单个阿里百炼模型，成功返回 (is_qualified, reason, violated)，失败返回 (None, None, None)"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请判断股票{code}({name})目前的合规状况。请务必开启联网搜索获取最新信息，特别是检查是否有高管被留置或立案调查。输出JSON。"}
    ]
    try:
        response = Generation.call(
            model=model,
            messages=messages,
            temperature=0.1,
            result_format='message',
            enable_search=True,
            response_format={"type": "json_object"},
        )
        if response.status_code != 200:
            if debug:
                print(f"  ⚠️ {model} 返回错误码 {response.status_code}")
            return None, None, None

        content = response.output.choices[0].message.content.strip()
        if debug:
            short = content[:100] + ('...' if len(content) > 100 else '')
            print(f"  [{model}] {short}")

        if not content:
            return None, None, None

        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            return None, None, None

        result = json.loads(match.group())
        is_qualified = result.get("is_qualified", False)
        reason = result.get("reason", "")
        violated = result.get("violated_rules", [])

        # 防御：不合规但无具体规则 → 强制合规
        if not is_qualified and len(violated) == 0:
            return True, reason + "（模型未提供具体规则，按合规处理）", []
        all_rules = {"1","2","3","4","5","6","7","8","9","10"}
        if not is_qualified and set(violated) == all_rules:
            return True, "模型输出异常（列出全部规则），按信息不足处理", []
        return is_qualified, reason, violated

    except Exception as e:
        if debug:
            print(f"  ❌ {model} 调用异常: {e}")
        return None, None, None

def _call_zhipu(code: str, name: str, debug: bool = False) -> Tuple[bool, str, List[str]]:
    """使用 zai-sdk 调用智谱 GLM-4.7-Flash 模型作为备选"""
    client = ZhipuAiClient(api_key=ZHIPU_API_KEY)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请判断股票{code}({name})目前的合规状况。请务必开启联网搜索获取最新信息，特别是检查是否有高管被留置或立案调查。输出JSON。"}
    ]
    try:
        response = client.chat.completions.create(
            model="glm-4.7-flash",
            messages=messages,
            temperature=0.1,
            tools=[{
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_result": True
                }
            }],
            tool_choice="auto",
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            return True, "模型返回空内容，按合规处理", []
        content = content.strip()
        if debug:
            short = content[:100] + ('...' if len(content) > 100 else '')
            print(f"  [智谱GLM] {short}")

        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            return True, "未找到JSON，按合规处理", []

        result = json.loads(match.group())
        is_qualified = result.get("is_qualified", False)
        reason = result.get("reason", "")
        violated = result.get("violated_rules", [])

        if not is_qualified and len(violated) == 0:
            return True, reason + "（模型未提供具体规则，按合规处理）", []
        all_rules = {"1","2","3","4","5","6","7","8","9","10"}
        if not is_qualified and set(violated) == all_rules:
            return True, "模型输出异常（列出全部规则），按信息不足处理", []
        return is_qualified, reason, violated

    except Exception as e:
        print(f"  ❌ 智谱API调用失败: {e}")
        return True, f"调用异常，默认合规: {e}", []

def _call_with_fallback(code: str, name: str, debug: bool = False) -> Tuple[bool, str, List[str]]:
    """依次尝试阿里百炼模型列表，全部失败后使用智谱 GLM 作为最终备选"""
    for model in QWEN_MODEL_LIST:
        is_qualified, reason, violated = _call_qwen(model, code, name, debug)
        if is_qualified is not None:
            return is_qualified, reason, violated
    if debug:
        print(f"  ⚠️ 阿里百炼模型均失败，切换至智谱 GLM...")
    return _call_zhipu(code, name, debug)

def filter_stocks(stock_list: List[str], delay: float = 1.0, debug: bool = False) -> List[str]:
    def norm(code: str) -> str:
        return code.split('.')[0] if '.' in code else code

    original_map = {norm(raw): raw for raw in stock_list}
    normalized = list(original_map.keys())
    qualified = []

    print(f"\n筛选 {len(normalized)} 只股票（阿里百炼多模型 + 智谱 GLM 备选）")
    if debug:
        print("DEBUG模式（简洁）")
    print("-" * 60)

    for idx, code in enumerate(normalized, 1):
        print(f"[{idx}/{len(normalized)}] {code}")
        is_qualified, reason, rules = _call_with_fallback(code, "待查", debug=debug)
        if is_qualified:
            print(f"  ✅ 保留")
            qualified.append(code)
        else:
            print(f"  ❌ 剔除 | 规则 {', '.join(rules) if rules else '无'} | {reason[:60]}")
        if idx < len(normalized):
            time.sleep(delay)

    print("-" * 60)
    print(f"完成，{len(qualified)}/{len(normalized)} 合规")
    return [original_map[code] for code in qualified]

if __name__ == "__main__":
    test = ["000001.sz", "000858.sz", "600519.sh", "000639.sz"]
    result = filter_stocks(test, delay=1.0, debug=True)
    print(f"\n最终合规股票池: {result}")