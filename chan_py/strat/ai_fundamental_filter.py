import os
import time
import json
import re
import requests
from typing import List, Tuple, Optional
import datetime
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

# 所有免费联网千问模型（从最强到最弱），智谱作为最终备选
QWEN_MODEL_LIST = [
    "qwen3-max",
    "qwen3-plus",
    "qwen3-turbo",
    "qwen-plus",
    "qwen-turbo",
    "qwen-flash",
]
zhipu_client = ZhipuAiClient(api_key=ZHIPU_API_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
SSE_HEADERS = {
    **HEADERS,
    "Referer": "https://www.sse.com.cn/"
}

# 高风险关键词（仅用于在前端提示中醒目显示，不作为过滤依据）
RISK_FLAGS = [
    "留置", "立案调查", "立案", "纪律审查", "监察调查",
    "责令改正", "监管警示", "出具警示函", "通报批评", "公开谴责",
    "无法表示意见", "否定意见", "财务造假", "ST", "*ST"
]

# 网络重试
MAX_RETRIES = 2
RETRY_BACKOFF = 1.5  # 秒

# -------------------- 加载外部配置 --------------------
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

# Debug log file (每次运行覆盖写入)
DEBUG_LOG = "debug_search.log"

# -------------------- 系统提示词（12条规则，按触发频率排序，国九条框架） --------------------
SYSTEM_PROMPT = """你是一名中国证券市场合规分析专家。请严格按照以下规则判断上市公司是否合规。

【黄金原则】  
- 只有获取到明确、可信的证据（财报、公告、监管通报）证明触犯以下某条标准，才能判定"不合规"。  
- 信息缺失、不确定或未找到违规证据，必须判"合规"。  
- 严禁将"不合规"作为默认答案或列出全部规则。

【判定细则】  
以下规则按触发频率从高到低排列，满足任意一条且证据确凿即为不合规（is_qualified = false），列出规则编号：

[直接条款] ① 交易类：面值退市  
  连续20个交易日（无需连贯）收盘价均＜1元人民币。

[关联信号] ② 监管处罚/立案  
  公司本身或其董事、监事、高级管理人员、实际控制人因涉嫌与上市公司**财务报告、信息披露、证券交易**等相关的违法违规行为，被**证监会及其派出机构、交易所、纪委监委、公安机关等有权机关**采取正式立案调查，或**任何已公开的、指向上市公司自身**的行政监管措施、纪律处分，且相关程序尚未结案或整改完成。  
  **豁免**：仅涉及分支机构且与财务报告/信息披露/证券交易无关的常规业务罚款（如贷款操作瑕疵、环保罚款），不触发本条。  
  **工作要求**：判定违反时，reason 必须引用具体公告编号或新闻来源、涉事人员姓名及职位；判定不违反时，reason 必须逐一排除经搜索确认的潜在风险点，严禁使用"经核查，未发现触发规则"等笼统表述。  
  **严重程度分级（本规则专用）**：判定违反后，须根据违规措施性质分级——  
  - **高（high）**：立案调查、行政处罚决定书、公开谴责、留置、纪律审查/监察调查  
  - **中（medium）**：通报批评、责令改正/责令整改（涉及财务报告或信息披露）  
  - **低（low）**：监管警示函、出具警示函、监管关注函（仅涉及信披程序性瑕疵，未衍生出实质性后果）  
  分级信息须填入 violation_details。你必须主动搜索相关监管信息，注意公告或新闻中出现的"责令改正""监管警示""出具警示函""通报批评""公开谴责""留置""立案调查"等词汇，但不限于这些。只要是监管机构正式发出的、与财务或信披相关的负面的、公开的措施，即应判定为违反本规则。

[直接条款] ③ 财务类：净利润负且营收低  
  最近一会计年度净利润为负且营业收入低于3亿元（主板）/1亿元（科创、创业板）。

[结果指标] ④ ST/*ST 风险警示  
  已被交易所实施ST或*ST风险警示。

[直接条款] ⑤ 规范类：内控审计否定/无法表示意见  
  最近一会计年度内控审计报告被出具否定意见或无法表示意见；连续两年非标即面临*ST。

[关联信号] ⑥ 重大诉讼  
  存在尚未结案的诉讼/仲裁，涉案金额超过最近一期经审计净资产的10%。

[直接条款] ⑦ 规范类：会计差错更正  
  公司主动发布会计差错更正公告，更正对最近一已披露会计年度净利润影响金额超过原披露净利润的20%。

[直接条款] ⑧ 规范类：资金占用/违规担保  
  存在关联方非经营性资金占用或违规对外担保，且未在规定期限内完成整改。

[直接条款] ⑨ 财务类：分红不达标  
  主板公司最近三个会计年度累计现金分红总额低于最近三个会计年度年均净利润的30%，且累计分红金额低于5000万元（科创、创业板、北交所不适用此条）。

[直接条款] ⑩ 财务类：净资产为负  
  最近一会计年度经审计归属于母公司股东的净资产为负值。

[直接条款] ⑪ 重大违法类：财务造假  
  经证监会或其派出机构正式认定或公告的财务造假行为：一年虚增收入≥2亿元且占比≥30%，或连续两年虚增收入≥3亿元且占比≥20%等情形。

[直接条款] ⑫ 交易类：市值退市  
  连续20个交易日（无需连贯）总市值均＜5亿元（仅主板适用）。

【工作流程】  
规则已按触发频率从高到低排列。你必须按①→⑫顺序逐一检查，一旦确认任一违规立即停止（输出当前违规结果，不检查后续规则）。对可疑条目须联网搜索完整公告或权威报道核实后方可判定。

【输出格式】  
- 只输出一个JSON对象，无其他文字。  
- 格式：  
  {"code": "股票代码", "name": "股票简称", "is_qualified": true/false, "reason": "判断理由（须含违规年份）", "violated_rules": ["规则编号"], "violation_details": [{"rule": "规则编号", "severity": "high/medium/low", "year": 年份整数, "description": "简述（≤30字）"}]}
- **注意**：violation_details 在 is_qualified=false 时必须提供；is_qualified=true 时可为空数组 []。对规则②（监管处罚/立案）的每条违规必须包含 severity 和 year。

【关键判断原则】
- 在应用规则③、⑧、⑨、⑩、⑪时，应以"上市公司自身"（即上市公司合并报表主体）为判断基准。其下属子公司、分支机构或参股公司的独立情况（如：单独的财务亏损、经营不善、诉讼纠纷、被处罚等），一般不直接等同于上市公司主体的违规。
- 规则④中的"ST"指根据交易所上市规则，因财务状况、内控等原因被实施的风险警示，不包括因其他原因（如重大信息披露违法后被行政处罚）而被叠加实施的ST或*ST。请务必仔细甄别。
- 规则⑦中"会计差错更正"的范围，应是指上市公司自身在定期报告中出现的重大错报，不包括子公司或分支机构独立的、金额未达到重要性水平的调整。
- 对规则⑥"重大诉讼"的判断，应以公司整体经审计报表为准，并对"重大"作审慎判断。仅当其确实可能对公司经营产生重大影响时，方可认定为触发。
- 规则②中"董监高、实际控制人"指上市公司年报/公告中明确披露的人员。非上市公司的关联方高管（如控股股东董事长）其个人行为原则上不构成上市公司的规则②违规，除非该人员同时担任上市公司董监高。
"""

# -------------------- URL动态维护（不变） --------------------
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
        # SSE 用沪市代码检测，SZSE 用深市代码，其它通用源用 000001
        if key == "sse":
            test_code = "600000"
        elif key == "szse":
            test_code = "000001"
        else:
            test_code = "000001"
        test_url = src["url"].format(code=test_code, type="SHA" if test_code.startswith("6") else "SZA")
        if _check_url(test_url):
            if debug:
                print(f"  [健康] {src['name']} OK")
        else:
            if debug:
                print(f"  [警告] {src['name']} 失效，AI搜索新URL...")
            new_url = _ai_search_url_fallback(src["name"], debug)
            if new_url:
                test_new_url = new_url.format(code=test_code, type="SHA" if test_code.startswith("6") else "SZA")
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

# -------------------- 数据抓取（不变） --------------------
def _fetch_from_url(code: str, source_key: str, source_config: dict, debug: bool = False, log_file=None) -> str:
    name = source_config["name"]
    code_short = code.split('.')[0]
    suffix = code.split('.')[1].lower() if '.' in code else ''
    ann_type = "SHA" if suffix in ('sh', 'sha', 'xshg') else "SZA"
    url = source_config["url"].format(code=code_short, type=ann_type)
    headers = SSE_HEADERS if source_key == "sse" else HEADERS
    def _diag(msg):
        if log_file:
            log_file.write(msg + "\n")
        elif debug:
            print(msg)
    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            _diag(f"  [{name}] status={resp.status_code} ct={resp.headers.get('Content-Type','?')[:80]}")
            if resp.status_code == 200:
                try:
                    raw_text = resp.text.strip()
                    if source_key == "sse" and raw_text.endswith(")"):
                        idx = raw_text.find("(")
                        if idx > 0:
                            raw_text = raw_text[idx+1:-1]
                    data = json.loads(raw_text)
                    items = []
                    if source_key == "cninfo":
                        items = data.get("announcements", [])
                    elif source_key == "sse":
                        items = data.get("result", [])
                        if not items:
                            page_help = data.get("pageHelp", {})
                            items = page_help.get("data", [])
                    elif source_key == "eastmoney":
                        ann_data = data.get("data", {})
                        items = ann_data.get("list", [])
                    elif source_key == "szse":
                        items = data.get("data", [])
                    if items:
                        lines = [f"【{name}】"]
                        for it in items:
                            title = it.get("title") or it.get("announcementTitle") or it.get("TITLE", "")
                            date = str(it.get("notice_date") or it.get("publishDate") or it.get("announcementDate") or it.get("SSEDATE", ""))[:10]
                            lines.append(f"  {date} {title}")
                        return "\n".join(lines)
                    else:
                        keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
                        _diag(f"  [{name}] JSON OK but items=[] (keys={keys})")
                        return ""
                except Exception as e:
                    _diag(f"  [{name}] JSON error: {type(e).__name__} {e}")
                    if debug or log_file:
                        try:
                            _diag(f"  [{name}] resp[:500]={resp.text[:500]}")
                        except:
                            pass
                    pass
                soup = BeautifulSoup(resp.text, "html.parser")
                if source_key == "eastmoney":
                    items = soup.select(".news-item")[:10]
                    if not items:
                        _diag(f"  [{name}] .news-item=0 (HTML fallback)")
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
                if source_key == "szse":
                    text = soup.get_text()[:2000]
                    if "公告" in text:
                        return f"【{name}】\n（网页文本摘要）\n{text}"
                _diag(f"  [{name}] 返回空 (HTML无匹配)")
                return ""
            else:
                _diag(f"  [{name}] HTTP {resp.status_code}")
        except Exception as e:
            _diag(f"  [{name}] 请求异常: {type(e).__name__}: {e}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * (attempt + 1))
    return ""

def collect_external_info(code: str, debug: bool = False, log_file=None):
    code_short = code.split('.')[0]
    parts = []
    cninfo = _fetch_from_url(code, "cninfo", config["sources"]["cninfo"], debug, log_file)
    if cninfo:
        parts.append(cninfo)
        if debug:
            lines = cninfo.strip().split("\n")
            first = lines[1].strip()[:60] if len(lines) > 1 else "?"
            print(f"  [巨潮资讯网] OK: {len(lines) - 1} 条 | {first}")
    elif debug:
        print(f"  [巨潮资讯网] EMPTY")
    em = _fetch_from_url(code, "eastmoney", config["sources"]["eastmoney"], debug, log_file)
    if em:
        parts.append(em)
        if debug:
            lines = em.strip().split("\n")
            first = lines[1].strip()[:60] if len(lines) > 1 else "?"
            print(f"  [东方财富] OK: {len(lines) - 1} 条 | {first}")
    elif debug:
        print(f"  [东方财富] EMPTY")
    suffix = code.split('.')[1].lower() if '.' in code else ''
    if suffix in ('sh', 'sha'):
        sse = _fetch_from_url(code, "sse", config["sources"]["sse"], debug, log_file)
        if sse:
            parts.append(sse)
            if debug:
                lines = sse.strip().split("\n")
                first = lines[1].strip()[:60] if len(lines) > 1 else "?"
                print(f"  [上交所] OK: {len(lines) - 1} 条 | {first}")
        elif debug:
            print(f"  [上交所] EMPTY")
    elif suffix in ('sz', 'szs', 'sze'):
        szse = _fetch_from_url(code, "szse", config["sources"]["szse"], debug, log_file)
        if szse:
            parts.append(szse)
            if debug:
                lines = szse.strip().split("\n")
                first = lines[1].strip()[:60] if len(lines) > 1 else "?"
                print(f"  [深交所] OK: {len(lines) - 1} 条 | {first}")
        elif debug:
            print(f"  [深交所] EMPTY")
    else:
        sse = _fetch_from_url(code, "sse", config["sources"]["sse"], debug, log_file)
        if sse:
            parts.append(sse)
            if debug:
                lines = sse.strip().split("\n")
                first = lines[1].strip()[:60] if len(lines) > 1 else "?"
                print(f"  [上交所] OK: {len(lines) - 1} 条 | {first}")
        elif debug:
            print(f"  [上交所] EMPTY")
        szse = _fetch_from_url(code, "szse", config["sources"]["szse"], debug, log_file)
        if szse:
            parts.append(szse)
            if debug:
                lines = szse.strip().split("\n")
                first = lines[1].strip()[:60] if len(lines) > 1 else "?"
                print(f"  [深交所] OK: {len(lines) - 1} 条 | {first}")
        elif debug:
            print(f"  [深交所] EMPTY")

    # 写入日志：原始源数据
    if log_file and parts:
        log_file.write("  ── 原始数据源 ──\n")
        for part in parts:
            for line in part.strip().split("\n"):
                log_file.write(f"  {line}\n")
        log_file.write("\n")

    if parts:
        # 提取含高风险关键词的公告行，提到最前面强制模型关注
        flagged_lines = []
        clean_parts = []
        for part in parts:
            lines = part.split("\n")
            header_line = lines[0]  # 【巨潮资讯网】等
            kept = [header_line]
            for line in lines[1:]:
                stripped = line.strip()
                if stripped and any(kw in line for kw in RISK_FLAGS):
                    flagged_lines.append(stripped)
                else:
                    kept.append(line)
            if len(kept) > 1:
                clean_parts.append("\n".join(kept))

        header = "以下为近期公开公告/新闻标题，请仔细审查，逐条判断是否可能触发规则1-10。"
        if flagged_lines:
            header += f"\n\n[!] 以下{len(flagged_lines)}条公告/新闻含高风险关键词，须逐一联网核实："
            header += "\n" + "\n".join(flagged_lines)
        if clean_parts:
            header += "\n\n以下为其他公告/新闻标题："
            header += "\n\n" + "\n\n".join(clean_parts)
        return header, flagged_lines
    return "", []

# -------------------- 模型回复解析 --------------------
def _parse_response(content: str) -> Tuple[bool, str, List[str], List[dict]]:
    if not content:
        return True, "模型返回空内容，按合规处理", [], []
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
        return True, "未找到有效JSON，按合规处理", [], []
    is_qualified = result.get("is_qualified", False)
    reason = result.get("reason", "")
    violated = result.get("violated_rules", [])
    violation_details = result.get("violation_details", [])
    if not isinstance(violation_details, list):
        violation_details = []
    if not is_qualified and len(violated) == 0:
        return True, reason + "（模型未提供具体规则，按合规处理）", [], []
    if not is_qualified and len(violated) >= 5:
        return True, f"模型输出异常（列出{len(violated)}条规则），按信息不足处理", [], []
    return is_qualified, reason, violated, violation_details

# -------------------- 模型调用 --------------------
def _call_qwen(model: str, code: str, external_info: str, debug: bool = False):
    user_prompt = (
        f"请判断股票{code}目前的合规状况。\n"
        f"{external_info}\n"
        f"请主动联网搜索\"{code} 监管\" \"{code} 处罚\" \"{code} 纪律\"等，确认是否存在任何正式的行政监管措施或纪律处分。\n"
        "请注意：所有判断必须严格限定在上市公司主体层面。除非明确说明，子公司的财务数据、经营亏损、法律诉讼、被罚款/处罚、会计差错等，不应直接视为上市公司本体的违规。\n"
        "区分上市公司自身被ST与因其子公司、主要投资标的或参股公司出现问题带来的股价波动。\n"
        "逐条审查所有标题，并在输出前完成所有必要的搜索与核实，确保没有遗漏。\n"
        "本次审查结果将用于投资决策，宁可误判违规也不遗漏真实违规（优先减少假阴性）。\n"
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
            temperature=0,
            result_format='message',
            enable_search=True,
            response_format={"type": "json_object"},
        )
        if resp.status_code != 200:
            if debug:
                print(f"  [!] {model} 状态码 {resp.status_code}")
            return None, None, None, []
        content = resp.output.choices[0].message.content.strip()
        if debug:
            short = content[:100] + ('...' if len(content) > 100 else '')
            print(f"  [{model}] {short}")
        return _parse_response(content)
    except Exception as e:
        if debug:
            print(f"  [FAIL] {model} 异常: {e}")
        return None, None, None, []

def _call_zhipu(code: str, external_info: str, debug: bool = False) -> Tuple[bool, str, List[str], List[dict]]:
    user_prompt = (
        f"请判断股票{code}目前的合规状况。\n"
        f"{external_info}\n"
        f"请主动联网搜索\"{code} 监管\" \"{code} 处罚\" \"{code} 纪律\"等，确认是否存在任何正式的行政监管措施或纪律处分。\n"
        "请注意：所有判断必须严格限定在上市公司主体层面。除非明确说明，子公司的财务数据、经营亏损、法律诉讼、被罚款/处罚、会计差错等，不应直接视为上市公司本体的违规。\n"
        "区分上市公司自身被ST与因其子公司、主要投资标的或参股公司出现问题带来的股价波动。\n"
        "逐条审查所有标题，并在输出前完成所有必要的搜索与核实，确保没有遗漏。\n"
        "本次审查结果将用于投资决策，宁可误判违规也不遗漏真实违规（优先减少假阴性）。\n"
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
            temperature=0,
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
        print(f"  [FAIL] 智谱调用失败: {e}")
        return True, f"智谱异常，默认合规: {e}", [], []

_RULE_CIRCLED = str.maketrans("①②③④⑤⑥⑦⑧⑨⑩⑪⑫", "123456789012")

def _normalize_rules(rules: List[str]) -> List[str]:
    return [r.translate(_RULE_CIRCLED) for r in rules]

def _call_with_fallback(code: str, external_info: str, debug: bool = False) -> Tuple[bool, str, List[str], List[dict], str]:
    for model in QWEN_MODEL_LIST:
        is_q, reason, viol, vd = _call_qwen(model, code, external_info, debug)
        if is_q is not None:
            return is_q, reason, viol, vd, model
    if debug:
        print("  [!] 千问模型均失败，切换至智谱...")
    is_q, reason, viol, vd = _call_zhipu(code, external_info, debug)
    return is_q, reason, viol, vd, "glm-4.7-flash"

# -------------------- 分级时效过滤 --------------------
def _extract_year_from_reason(text: str) -> Optional[int]:
    """从违规描述中提取最近提及的4位年份"""
    if not text:
        return None
    matches = re.findall(r'(20\d{2})', text)
    if matches:
        years = [int(y) for y in matches]
        return max(years)  # 取最近年份
    return None

def _classify_violation(vtype: str) -> str:
    """根据违规类型关键词归类为 high/medium/low"""
    tier_rules = config.get("violation_tier_rules", {})
    for severity in ["high", "medium", "low"]:
        types = tier_rules.get(severity, {}).get("types", [])
        for keyword in types:
            if keyword in vtype:
                return severity
    return "high"  # 无法归类时按最高等级处理，宁严勿松

# -------------------- 规则②本地扫描（一审） --------------------
def _local_rule2_scan(flagged_lines: List[str]) -> List[dict]:
    """扫描外部公告标题，纯代码判定规则②（监管处罚/立案）违规，命中即结论不调API"""
    if not flagged_lines:
        return []

    tier_rules = config.get("violation_tier_rules", {})
    current_year = datetime.datetime.now().year

    # 构建配置中的Rule②关键词→severity映射（只用config关键词，不用全部RISK_FLAGS）
    rule2_kw_map = {}
    for severity in ["high", "medium", "low"]:
        for kw in tier_rules.get(severity, {}).get("types", []):
            rule2_kw_map[kw] = severity

    violations = []
    for line in flagged_lines:
        matched_severity = None
        matched_keyword = None
        for kw, severity in rule2_kw_map.items():
            if kw in line:
                matched_severity = severity
                matched_keyword = kw
                break
        if not matched_keyword:
            continue

        year_val = _extract_year_from_reason(line)
        if year_val is None:
            year_val = current_year

        lookback = tier_rules.get(matched_severity, {}).get("lookback_years", 3)
        if current_year - year_val <= lookback:
            violations.append({
                "rule": "2",
                "severity": matched_severity,
                "year": year_val,
                "description": line[:30]
            })

    return violations

def _apply_tiered_filter(is_qualified: bool, reason: str,
                         violated_rules: List[str],
                         violation_details: List[dict],
                         external_info: str = "") -> Tuple[bool, str, List[str]]:
    """对规则②（监管处罚/立案）违规应用分级×时效过滤，超时效窗口的违规予以豁免"""
    if is_qualified:
        return True, reason, violated_rules

    violated_rules = _normalize_rules(violated_rules)
    if violation_details:
        for vd in violation_details:
            if isinstance(vd.get("rule"), str):
                vd["rule"] = vd["rule"].translate(_RULE_CIRCLED)

    if "2" not in violated_rules:
        return False, reason, violated_rules

    # 规则②本地证据校验：固定源公告标题无任何风险关键词 → 模型判断可能来自搜索引擎噪声
    if external_info and not any(kw in external_info for kw in RISK_FLAGS):
        remaining = [r for r in violated_rules if r != "2"]
        if not remaining:
            print(f"  [!] 规则②违规缺乏固定源公告证据，按合规处理")
            return True, reason + "（缺乏固定源证据，规则②不予采信）", remaining
        # 除规则②外还有其他规则，继续检查
        return False, reason, remaining

    tier_rules = config.get("violation_tier_rules", {})
    current_year = datetime.datetime.now().year

    # 优先用模型提供的 violation_details；缺失时从 reason 回退提取
    violations = [vd for vd in (violation_details or []) if str(vd.get("rule", "")) == "2"]

    if violations:
        rule2_valid = False
        for vd in violations:
            severity = vd.get("severity", "")
            if not severity:
                severity = _classify_violation(vd.get("description", "") or reason)
            vyear = vd.get("year")
            if vyear is None or not isinstance(vyear, int):
                vyear = _extract_year_from_reason(vd.get("description", "") or reason)
            if vyear is None:
                vyear = current_year - 10
                print(f"  [!] 规则②违规年份无法提取，默认按10年前处理（{current_year - 10}）")

            lookback = tier_rules.get(severity, {}).get("lookback_years", 3)
            if current_year - vyear <= lookback:
                rule2_valid = True
                break  # 至少一条规则②仍在时效内
    else:
        # 回退：从 reason 文本中提取年份和类型
        severity = _classify_violation(reason)
        vyear = _extract_year_from_reason(reason)
        lookback = tier_rules.get(severity, {}).get("lookback_years", 3)
        rule2_valid = bool(vyear and current_year - vyear <= lookback)

    if not rule2_valid:
        remaining = [r for r in violated_rules if r != "2"]
        if not remaining:
            return True, reason + "（违规已超过时效窗口，豁免）", remaining
        # 除规则②外还有其他规则未豁免，继续返回不合规
        return False, reason, remaining

    return False, reason, violated_rules

# -------------------- 主筛选函数 --------------------
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

    with open(DEBUG_LOG, "w", encoding="utf-8") as log_file:
        log_file.write(f"=== RUN: {datetime.datetime.now().isoformat()} ===\n")

        for idx, code in enumerate(normalized, 1):
            raw_code = original_map[code]  # 保留原始后缀（.sz/.sh/.XSHE/.XSHG）
            print(f"[{idx}/{len(normalized)}] {code}")
            log_file.write(f"\n{'='*60}\n")
            log_file.write(f"[{idx}/{len(normalized)}] {code}\n\n")

            external_info, flagged_lines = collect_external_info(raw_code, debug=debug, log_file=log_file)

            log_file.write(f"  ── 提取的 flagged_lines (RISK_FLAGS) ──\n")
            if flagged_lines:
                for fl in flagged_lines:
                    log_file.write(f"  {fl}\n")
            else:
                log_file.write(f"  (空)\n")

            log_file.write(f"\n  ── 发送给模型的 external_info ──\n")
            log_file.write(f"{external_info}\n" if external_info else "(空)\n")

            if external_info and not debug:
                print(f"  [INFO] 外部信息加载完成 ({len(external_info)}字符)")

            if not external_info.strip():
                print(f"  [!] 外部公告数据为空，模型仅依赖联网搜索，误判风险升高")

            # --- 规则②本地扫描（一审）：命中直接剔除，跳过API ---
            if flagged_lines:
                rule2_violations = _local_rule2_scan(flagged_lines)
                if rule2_violations:
                    vd = rule2_violations[0]
                    print(f"  [SCAN] 本地扫描命中规则② | severity={vd['severity']} year={vd['year']}")
                    print(f"  [FAIL] 剔除 | 触发规则: 2 | {vd['description']}")
                    log_file.write(f"\n  ── 规则②本地扫描 ──\n")
                    log_file.write(f"  命中: severity={vd['severity']}, year={vd['year']}\n")
                    log_file.write(f"  description: {vd['description']}\n")
                    log_file.write(f"  结果: 跳过API，直接剔除\n")
                    continue
                if debug:
                    print(f"  [!] 存在{len(flagged_lines)}条风险信号但本地扫描未命中，移交API复查")

            model_qualified, reason, rules, violation_details, model_used = _call_with_fallback(code, external_info, debug=debug)
            log_file.write(f"\n  ── 模型返回 ──\n")
            log_file.write(f"  model: {model_used}\n")
            log_file.write(f"  is_qualified: {model_qualified}\n")
            log_file.write(f"  reason: {reason}\n")
            log_file.write(f"  violated_rules: {rules}\n")
            log_file.write(f"  violation_details: {violation_details}\n")

            is_qualified, reason, rules = _apply_tiered_filter(model_qualified, reason, rules, violation_details, external_info)
            if is_qualified:
                if not model_qualified:
                    print(f"  [OK] 保留（时效豁免）")
                    log_file.write(f"  最终: [OK] 保留（时效豁免）\n")
                else:
                    print(f"  [OK] 保留")
                    log_file.write(f"  最终: [OK] 保留\n")
                qualified.append(code)
            else:
                print(f"  [FAIL] 剔除 | 触发规则: {', '.join(rules) if rules else '无'} | {reason[:80]}")
                log_file.write(f"  最终: [FAIL] 剔除\n")
            if idx < len(normalized):
                time.sleep(delay)

    print("-" * 60)
    print(f"完成，{len(qualified)}/{len(normalized)} 合规")
    return [original_map[code] for code in qualified]

if __name__ == "__main__":
    # test = ["000001.sz", "000858.sz", "600519.sh", "000639.sz", "605177.sh", "002758.sz"]
    test = ["600638.XSHG", "002582.XSHE", "605177.XSHG", "002758.XSHE", "000498.XSHE", "002745.XSHE", "002614.XSHE", "000421.XSHE", "000906.XSHE", "600455.XSHG", "001218.XSHE", "600768.XSHG", "600717.XSHG", "002743.XSHE", "605189.XSHG", "601188.XSHG", "002054.XSHE"]
    result = filter_stocks(test, delay=2.0, debug=True)
    print(f"\n最终合规股票池: {result}")
