# -*- coding: utf-8 -*-
import os
import time
import json
import re
import requests
from typing import List, Tuple
from bs4 import BeautifulSoup
from dashscope import Generation
from zai import ZhipuAiClient

# ==================== 配置 ====================
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "").strip()
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "").strip()

if not DASHSCOPE_API_KEY:
    raise ValueError("请在环境变量中设置 DASHSCOPE_API_KEY")
if not ZHIPU_API_KEY:
    raise ValueError("请在环境变量中设置 ZHIPU_API_KEY")

QWEN_MODEL_LIST = [
    "qwen3-max",
    "qwen3-plus",
    "qwen-turbo",
]

zhipu_client = ZhipuAiClient(api_key=ZHIPU_API_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
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

【工作流程】  
- 我会提供该股票近期的公告和新闻标题（及部分摘要）。  
- 你必须仔细阅读这些线索，对其中可能涉及违规的条目（如留置、立案调查、ST、处罚、否定意见等） **立即使用联网搜索** 核实该公告的详细内容。  
- 只有在官方公告或权威媒体报道中确认了违规事实，才能判定为不合规。

【输出格式】  
- 必须输出一个JSON对象，不得包含任何其他解释性文字。  
- JSON格式：  
  {"code": "股票代码", "name": "股票简称", "is_qualified": true/false, "reason": "判断理由", "violated_rules": ["规则编号"]}
"""


def _fetch_cninfo(code: str, debug: bool) -> str:
    """巨潮资讯网：返回前10条公告标题"""
    try:
        short = code.split('.')[0]
        url = f"http://www.cninfo.com.cn/new/fulltextSearch/full?searchkey={short}&sdate=2025-01-01&edate=2026-12-31&isfulltext=false&sortName=pubdate&sortType=desc&pageNum=1&pageSize=10"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        data = resp.json()
        items = data.get("announcements", [])[:10]
        if items:
            lines = ["【巨潮公告（法定信息披露）】"]
            for ann in items:
                title = ann.get("announcementTitle", "")
                date = ann.get("announcementDate", "")[:10]
                lines.append(f"  {date} {title}")
            if debug:
                print(f"  [巨潮] 获取{len(items)}条")
            return "\n".join(lines)
    except Exception as e:
        if debug:
            print(f"  [巨潮] 异常: {e}")
    return ""


def _fetch_eastmoney_news(code: str, debug: bool) -> str:
    """东方财富个股新闻：返回前10条，并提取标题+摘要"""
    try:
        short = code.split('.')[0]
        url = f"https://so.eastmoney.com/news/s?keyword={short}&pageindex=1&searchrange=8192&channelid=1"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(".news-item")[:10]
        lines = []
        for item in items:
            title_el = item.select_one("h3 a")
            desc_el = item.select_one(".news-desc")  # 东方财富列表的摘要 class
            if title_el:
                title = title_el.get_text(strip=True)
                desc = desc_el.get_text(strip=True) if desc_el else ""
                line = f"  {title}"
                if desc:
                    line += f" —— {desc}"
                lines.append(line)
        if lines:
            if debug:
                print(f"  [东方财富] 获取{len(lines)}条")
            return "【东方财富新闻】\n" + "\n".join(lines)
    except Exception as e:
        if debug:
            print(f"  [东方财富] 异常: {e}")
    return ""


def _fetch_exchange_announce(code: str, debug: bool) -> str:
    """上交所/深交所公告：返回前10条标题"""
    try:
        short = code.split('.')[0]
        suffix = code.split('.')[1].lower() if '.' in code else ''
        items = []
        if suffix in ('sh', 'sha'):
            url = f"http://query.sse.com.cn/security/stock/queryCompanyBulletin.do?stockCode={short}&page=1&pageSize=10"
            headers = {**HEADERS, "Referer": "http://www.sse.com.cn/"}
            resp = requests.get(url, headers=headers, timeout=8)
            data = resp.json()
            items = data.get("result", [])[:10]
        elif suffix in ('sz', 'szs', 'sze'):
            url = f"http://www.szse.cn/api/disc/announcement/annList?stockCode={short}&pageSize=10"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            data = resp.json()
            items = data.get("data", [])[:10]

        if items:
            lines = ["【交易所公告】"]
            for it in items:
                title = it.get("title", "")
                date = it.get("publishDate", "")[:10] if suffix in ('sh', 'sha') else it.get("pubDate", "")[:10]
                lines.append(f"  {date} {title}")
            if debug:
                print(f"  [交易所] 获取{len(items)}条")
            return "\n".join(lines)
    except Exception as e:
        if debug:
            print(f"  [交易所] 异常: {e}")
    return ""


def collect_external_info(code: str, debug: bool = False) -> str:
    """汇总所有外部信源，返回格式化公告/新闻列表（供模型参考）"""
    parts = []
    cninfo = _fetch_cninfo(code, debug)
    if cninfo:
        parts.append(cninfo)
    em = _fetch_eastmoney_news(code, debug)
    if em:
        parts.append(em)
    exch = _fetch_exchange_announce(code, debug)
    if exch:
        parts.append(exch)

    if parts:
        return "以下是该股票近期的公开公告及新闻标题，请仔细审阅，对其中任何涉嫌违规的条目立即进行联网检索核实：\n\n" + "\n\n".join(parts)
    return ""


def _parse_response(content: str) -> Tuple[bool, str, List[str]]:
    if not content:
        return True, "模型返回空内容，按合规处理", []

    result = None
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{(?:[^{}]|\{[^{}]*\})*\}', content, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if result is None:
        return True, "未找到有效JSON，按合规处理", []

    is_qualified = result.get("is_qualified", False)
    reason = result.get("reason", "")
    violated = result.get("violated_rules", [])

    if not is_qualified and len(violated) == 0:
        return True, reason + "（模型未提供具体规则，按合规处理）", []
    if not is_qualified and set(violated) == set(str(i) for i in range(1, 11)):
        return True, "模型输出异常（列出全部规则），按信息不足处理", []

    return is_qualified, reason, violated


def _call_qwen(model: str, code: str, external_info: str, debug: bool = False):
    user_prompt = f"请判断股票{code}目前的合规状况。\n{external_info}\n请务必开启联网搜索获取最新信息。输出JSON。"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
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

        return _parse_response(content)

    except Exception as e:
        if debug:
            print(f"  ❌ {model} 调用异常: {e}")
        return None, None, None


def _call_zhipu(code: str, external_info: str, debug: bool = False) -> Tuple[bool, str, List[str]]:
    user_prompt = f"请判断股票{code}目前的合规状况。\n{external_info}\n请务必开启联网搜索获取最新信息。输出JSON。"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        response = zhipu_client.chat.completions.create(
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
        content = content.strip() if content else ""
        if debug:
            short = content[:100] + ('...' if len(content) > 100 else '')
            print(f"  [智谱GLM] {short}")
        return _parse_response(content)
    except Exception as e:
        print(f"  ❌ 智谱API调用失败: {e}")
        return True, f"调用异常，默认合规: {e}", []


def _call_with_fallback(code: str, external_info: str, debug: bool = False) -> Tuple[bool, str, List[str]]:
    for model in QWEN_MODEL_LIST:
        is_qualified, reason, violated = _call_qwen(model, code, external_info, debug)
        if is_qualified is not None:
            return is_qualified, reason, violated
    if debug:
        print(f"  ⚠️ 阿里百炼模型均失败，切换至智谱 GLM...")
    return _call_zhipu(code, external_info, debug)


def filter_stocks(stock_list: List[str], delay: float = 2.0, debug: bool = False) -> List[str]:
    def norm(code: str) -> str:
        return code.split('.')[0] if '.' in code else code

    original_map = {norm(raw): raw for raw in stock_list}
    normalized = list(original_map.keys())
    qualified = []

    print(f"\n筛选 {len(normalized)} 只股票（外部信源 + 多模型联网）")
    if debug:
        print("DEBUG模式")
    print("-" * 60)

    for idx, code in enumerate(normalized, 1):
        print(f"[{idx}/{len(normalized)}] {code}")
        external_info = collect_external_info(code, debug=debug)
        if external_info and not debug:
            # 仅显示外部信息长度
            print(f"  📄 外部信息加载完成 ({len(external_info)}字符)")

        is_qualified, reason, rules = _call_with_fallback(code, external_info, debug=debug)
        if is_qualified:
            print(f"  ✅ 保留")
            qualified.append(code)
        else:
            print(f"  ❌ 剔除 | 触发规则: {', '.join(rules) if rules else '无'} | {reason[:80]}")
        if idx < len(normalized):
            time.sleep(delay)

    print("-" * 60)
    print(f"完成，{len(qualified)}/{len(normalized)} 合规")
    return [original_map[code] for code in qualified]


if __name__ == "__main__":
    test = ["000001.sz", "000858.sz", "600519.sh", "000639.sz"]
    result = filter_stocks(test, delay=2.0, debug=True)
    print(f"\n最终合规股票池: {result}")