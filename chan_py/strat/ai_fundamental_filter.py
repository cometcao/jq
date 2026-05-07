import os
import time
import json
import re
import requests
from typing import List, Tuple, Optional
from bs4 import BeautifulSoup
from dashscope import Generation
from zai import ZhipuAiClient

# -------------------- 环境变量 --------------------
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "").strip()
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "").strip()
CONFIG_FILE = "ai_filter_config.json"

if not DASHSCOPE_API_KEY:
    raise ValueError("请设置环境变量 DASHSCOPE_API_KEY")
if not ZHIPU_API_KEY:
    raise ValueError("请设置环境变量 ZHIPU_API_KEY")

QWEN_MODEL_LIST = ["qwen3-max", "qwen3-plus", "qwen-turbo"]
zhipu_client = ZhipuAiClient(api_key=ZHIPU_API_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

RISK_FLAGS = ["留置", "立案调查", "立案", "纪律审查", "监察调查",
              "无法表示意见", "否定意见", "财务造假", "ST", "*ST"]

# 重试配置
MAX_RETRIES = 2
RETRY_BACKOFF = 1.5  # 秒

# -------------------- 加载外部配置 --------------------
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

# -------------------- 提示词 --------------------
SYSTEM_PROMPT = """你是一名中国证券市场合规分析专家。请严格按照以下规则判断上市公司是否合规。

【黄金原则】  
- 只有获取到明确、可信的证据（财报、公告、监管通报）证明触犯以下某条标准，才能判定“不合规”。  
- 信息缺失、不确定或未找到违规证据，必须判“合规”。  
- 严禁将“不合规”作为默认答案或列出全部规则。

【⚠️ 最高优先级规则 —— 规则6】
规则6是最高优先级。只要通过联网搜索确认以下任意一种情形，立即判定为不合规：
- 公司或董监高、实控人被纪委监委“留置”  
- 被证监会、交易所“立案调查”  
- 关键词：“留置”、“立案调查”、“纪律审查”、“监察调查”  
即使公告标题或新闻摘要未直接写“违规”，只要出现上述关键词且涉及公司相关人员，就必须判定为不合规（violated_rules包含"6"）。

【判定细则】  
满足以下任意一条且证据确凿，即为不合规（is_qualified = false），列出规则编号：
1. 被实施ST或*ST风险警示  
2. 最近一会计年度经审计净资产为负值  
3. 最近一会计年度净利润为负且营业收入低于3亿元(主板)/1亿元(科创、创业板)  
4. 最近三个会计年度净利为正，但累计现金分红低于年均净利30%且低于5000万元  
5. 内控审计报告被出具否定意见或无法表示意见  
6. 公司或其董监高、实控人因涉嫌财务报告、信息披露、证券交易等相关违法违规，被有权机关立案调查或留置，尚未结案  
7. 最近三个会计年度归母净利润合计亏损超2亿元，且最近一年亏损额占前两年平均亏损额比例≥80%  
8. 证监会或其派出机构正式处罚或公告认定的重大财务造假  
9. 公司主动发布会计差错更正公告，更正对最近一已披露会计年度净利润影响金额超原披露净利润的20%  
10. 存在尚未结案、涉案金额超最近一期经审计净资产10%的重大诉讼

【输出格式】  
- 只输出一个JSON对象，无其他文字。  
- 格式：  
  {"code": "股票代码", "name": "股票简称", "is_qualified": true/false, "reason": "判断理由", "violated_rules": ["规则编号"]}
"""

# -------------------- URL动态维护（只用AI模型） --------------------
def _check_url(url: str) -> bool:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        return r.status_code == 200
    except:
        return False

def _ai_search_url_qwen(model: str, source_name: str) -> Optional[str]:
    prompt = (
        f"请帮我查找“{source_name}”当前可用的**上市公司公告查询网页入口**。\n"
        "要求：可在浏览器中直接打开的公开页面，能输入股票代码查询公告列表。\n"
        "只返回一个JSON对象：{\"url\": \"完整URL\"}，URL中如需股票代码用{code}占位。"
    )
    try:
        resp = Generation.call(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            result_format='message',
            enable_search=True,
            response_format={"type": "json_object"},
        )
        if resp.status_code != 200:
            return None
        content = resp.output.choices[0].message.content.strip()
        data = json.loads(content)
        url = data.get("url", "")
        if url and "{code}" not in url:
            url = url + ("&code={code}" if "?" in url else "?code={code}")
        return url if url else None
    except:
        return None

def _ai_search_url_zhipu(source_name: str) -> Optional[str]:
    prompt = (
        f"请帮我查找“{source_name}”当前可用的**上市公司公告查询网页入口**。\n"
        "要求：可在浏览器中直接打开的公开页面，能输入股票代码查询公告列表。\n"
        "只返回一个JSON对象：{\"url\": \"完整URL\"}，URL中如需股票代码用{code}占位。"
    )
    try:
        resp = zhipu_client.chat.completions.create(
            model="glm-4.7-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            tools=[{"type": "web_search", "web_search": {"enable": True, "search_result": True}}],
            tool_choice="auto",
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content.strip()
        data = json.loads(content)
        url = data.get("url", "")
        if url and "{code}" not in url:
            url = url + ("&code={code}" if "?" in url else "?code={code}")
        return url if url else None
    except:
        return None

def _ai_search_url_fallback(source_name: str, debug: bool = False) -> Optional[str]:
    for model in QWEN_MODEL_LIST:
        if debug:
            print(f"    -> 尝试 {model}...")
        url = _ai_search_url_qwen(model, source_name)
        if url:
            return url
    if debug:
        print("    -> 千问均失败，尝试智谱...")
    return _ai_search_url_zhipu(source_name)

def maintain_sources(debug: bool = False):
    global config
    updated = False
    for key, src in config["sources"].items():
        test_url = src["url"].format(code="000001")
        if _check_url(test_url):
            if debug:
                print(f"  [健康] {src['name']} OK")
        else:
            if debug:
                print(f"  [警告] {src['name']} 失效，AI搜索新URL...")
            new_url = _ai_search_url_fallback(src["name"], debug)
            if new_url:
                # 先测试新URL是否真的可用
                test_new_url = new_url.format(code="000001")
                if _check_url(test_new_url):
                    src["url"] = new_url
                    updated = True
                    if debug:
                        print(f"  [修复] {src['name']} -> {new_url}")
                else:
                    if debug:
                        print(f"  [放弃] 新URL不可用，保留原URL")
            else:
                if debug:
                    print(f"  [失败] {src['name']} 无法修复，保留原URL")
    if updated:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

# -------------------- 数据抓取（带重试） --------------------
def _fetch_from_url(code: str, source_key: str, source_config: dict, debug: bool = False) -> str:
    name = source_config["name"]
    code_short = code.split('.')[0]
    url = source_config["url"].format(code=code_short)

    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                # 尝试JSON
                try:
                    data = resp.json()
                    items = []
                    if source_key == "cninfo":
                        items = data.get("announcements", [])[:10]
                    elif source_key == "sse":
                        items = data.get("result", [])[:10]
                    elif source_key == "szse":
                        items = data.get("data", [])[:10]
                    if items:
                        lines = [f"【{name}】"]
                        for it in items:
                            title = it.get("title") or it.get("announcementTitle", "")
                            date = str(it.get("publishDate") or it.get("announcementDate", ""))[:10]
                            lines.append(f"  {date} {title}")
                        return "\n".join(lines)
                    else:
                        if debug:
                            print(f"  [{name}] JSON无数据")
                        return ""
                except:
                    pass

                # HTML解析（东方财富等）
                soup = BeautifulSoup(resp.text, "html.parser")
                if source_key == "eastmoney":
                    items = soup.select(".news-item")[:10]
                    lines = [f"【{name}】"]
                    for item in items:
                        title_el = item.select_one("h3 a")
                        if title_el:
                            title = title_el.get_text(strip=True)
                            desc_el = item.select_one(".news-desc")
                            desc = " —— " + desc_el.get_text(strip=True) if desc_el else ""
                            lines.append(f"  {title}{desc}")
                    if len(lines) > 1:
                        return "\n".join(lines)

                # 深交所网页备用
                if source_key == "szse":
                    text = soup.get_text()[:2000]
                    if "公告" in text:
                        if debug:
                            print(f"  [{name}] 网页文本提取")
                        return f"【{name}】\n（网页文本摘要）\n{text}"
                return ""
            else:
                if debug:
                    print(f"  [{name}] 状态码 {resp.status_code}")
        except Exception as e:
            if debug:
                print(f"  [{name}] 请求异常: {e}")

        # 重试前等待
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * (attempt + 1))
            if debug:
                print(f"  [{name}] 重试 {attempt+1}/{MAX_RETRIES}...")

    return ""

def collect_external_info(code: str, debug: bool = False) -> str:
    parts = []
    # 巨潮
    cninfo = _fetch_from_url(code, "cninfo", config["sources"]["cninfo"], debug)
    if cninfo:
        parts.append(cninfo)
    # 东方财富
    em = _fetch_from_url(code, "eastmoney", config["sources"]["eastmoney"], debug)
    if em:
        parts.append(em)
    # 交易所
    suffix = code.split('.')[1].lower() if '.' in code else ''
    if suffix in ('sh', 'sha'):
        sse = _fetch_from_url(code, "sse", config["sources"]["sse"], debug)
        if sse:
            parts.append(sse)
    elif suffix in ('sz', 'szs', 'sze'):
        szse = _fetch_from_url(code, "szse", config["sources"]["szse"], debug)
        if szse:
            parts.append(szse)
    else:
        sse = _fetch_from_url(code, "sse", config["sources"]["sse"], debug)
        if sse:
            parts.append(sse)
        szse = _fetch_from_url(code, "szse", config["sources"]["szse"], debug)
        if szse:
            parts.append(szse)

    if parts:
        combined = "\n\n".join(parts)
        risk_found = [kw for kw in RISK_FLAGS if kw in combined]
        header = "以下为近期公开公告/新闻标题，请仔细审查。"
        if risk_found:
            header += f" ⚠️ 检测到高危信号：{', '.join(risk_found)}，请务必联网核实！"
        header += "\n\n"
        return header + combined
    return ""

# -------------------- 模型输出解析 --------------------
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
            except:
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

# -------------------- 模型调用（强制留置搜索） --------------------
def _call_qwen(model: str, code: str, external_info: str, debug: bool = False):
    search_instruction = (
        f"请立即使用联网搜索以下关键词：\"{code} 留置\"、\"{code} 立案调查\"、"
        f"\"{code} 纪律审查\"，并仔细查看搜索结果。"
        "如果发现公司董事、监事、高管或实际控制人被留置、立案调查，必须判定为不合规（规则6）。"
    )
    user_prompt = (
        f"请判断股票{code}目前的合规状况。\n"
        f"{external_info}\n"
        f"{search_instruction}\n"
        "输出JSON。"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        resp = Generation.call(
            model=model,
            messages=messages,
            temperature=0.1,
            result_format='message',
            enable_search=True,
            response_format={"type": "json_object"},
        )
        if resp.status_code != 200:
            if debug:
                print(f"  ⚠️ {model} 状态码 {resp.status_code}")
            return None, None, None
        content = resp.output.choices[0].message.content.strip()
        if debug:
            short = content[:100] + ('...' if len(content) > 100 else '')
            print(f"  [{model}] {short}")
        return _parse_response(content)
    except Exception as e:
        if debug:
            print(f"  ❌ {model} 异常: {e}")
        return None, None, None

def _call_zhipu(code: str, external_info: str, debug: bool = False) -> Tuple[bool, str, List[str]]:
    search_instruction = (
        f"请立即使用联网搜索以下关键词：\"{code} 留置\"、\"{code} 立案调查\"、"
        f"\"{code} 纪律审查\"，并仔细查看搜索结果。"
        "如果发现公司董事、监事、高管或实际控制人被留置、立案调查，必须判定为不合规（规则6）。"
    )
    user_prompt = (
        f"请判断股票{code}目前的合规状况。\n"
        f"{external_info}\n"
        f"{search_instruction}\n"
        "输出JSON。"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        resp = zhipu_client.chat.completions.create(
            model="glm-4.7-flash",
            messages=messages,
            temperature=0.1,
            tools=[{"type": "web_search", "web_search": {"enable": True, "search_result": True}}],
            tool_choice="auto",
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content.strip() if resp.choices[0].message.content else ""
        if debug:
            short = content[:100] + ('...' if len(content) > 100 else '')
            print(f"  [智谱] {short}")
        return _parse_response(content)
    except Exception as e:
        print(f"  ❌ 智谱调用失败: {e}")
        return True, f"智谱异常，默认合规: {e}", []

def _call_with_fallback(code: str, external_info: str, debug: bool = False) -> Tuple[bool, str, List[str]]:
    for model in QWEN_MODEL_LIST:
        is_q, reason, viol = _call_qwen(model, code, external_info, debug)
        if is_q is not None:
            return is_q, reason, viol
    if debug:
        print("  ⚠️ 千问模型均失败，切换至智谱...")
    return _call_zhipu(code, external_info, debug)

# -------------------- 主函数 --------------------
def filter_stocks(stock_list: List[str], delay: float = 2.0, debug: bool = False) -> List[str]:
    def norm(code: str) -> str:
        return code.split('.')[0] if '.' in code else code
    original_map = {norm(raw): raw for raw in stock_list}
    normalized = list(original_map.keys())
    qualified = []

    maintain_sources(debug)

    print(f"\n筛选 {len(normalized)} 只股票（模型联网校验 + 动态URL维护）")
    if debug:
        print("DEBUG模式")
    print("-" * 60)

    for idx, code in enumerate(normalized, 1):
        print(f"[{idx}/{len(normalized)}] {code}")
        external_info = collect_external_info(code, debug=debug)
        if external_info and not debug:
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