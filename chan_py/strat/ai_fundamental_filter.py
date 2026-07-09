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
import baostock as bs

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
    "qwen3.7-max",
    "qwen3.7-plus",
    "qwen3.6-flash",
    "qwen3-max",
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

# -------------------- baostock 金融数据工具 --------------------
def _bs_code(raw_code: str) -> str:
    code = raw_code.split('.')[0]
    suffix = raw_code.split('.')[1].lower() if '.' in raw_code else ''
    prefix = 'sh' if suffix in ('sh', 'sha', 'xshg') else 'sz'
    return f"{prefix}.{code}"

def _get_board(raw_code: str) -> str:
    code = raw_code.split('.')[0]
    if code.startswith('688'):
        return '科创板'
    if code.startswith(('300', '301')):
        return '创业板'
    return '主板'

_bs_logged_in = False

def _bs_login():
    global _bs_logged_in
    if _bs_logged_in:
        return True
    lg = bs.login()
    _bs_logged_in = (lg.error_code == '0')
    if not _bs_logged_in:
        print(f"  [!] baostock 登录失败: {lg.error_msg}")
    return _bs_logged_in

def _bs_logout():
    global _bs_logged_in
    if _bs_logged_in:
        try:
            bs.logout()
        except:
            pass
        _bs_logged_in = False

def _check_financial_rules(code: str, raw_code: str, debug: bool = False) -> Tuple[List[dict], List[str]]:
    """
    用 baostock 确定性数据核验规则 ①③④⑫。
    返回 (violations, summary_lines)。
    violations 非空时 summary_lines 仅含违规描述。
    """
    code_bs = _bs_code(raw_code)
    board = _get_board(raw_code)
    violations = []
    summary = []
    current_year = datetime.datetime.now().year
    report_year = current_year - 1

    # ---- 日K线 ----
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime('%Y-%m-%d')
    daily_rows = []
    try:
        rs = bs.query_history_k_data_plus(code_bs, "date,close,isST",
                                           start_date=start_date, end_date=end_date,
                                           frequency="d", adjustflag="3")
        while (rs.error_code == '0') & rs.next():
            daily_rows.append(rs.get_row_data())
    except Exception as e:
        if debug:
            print(f"  [!] baostock k线查询失败: {e}")

    close = None
    is_st = None
    max_below_1 = 0
    if daily_rows:
        try:
            close_val = daily_rows[-1][1]
            close = float(close_val) if close_val else None
        except (ValueError, TypeError):
            pass
        try:
            is_st = daily_rows[-1][2] if len(daily_rows[-1]) > 2 else None
        except:
            pass
        below = 0
        for row in daily_rows:
            try:
                val = row[1]
                if val and float(val) < 1.0:
                    below += 1
                    max_below_1 = max(max_below_1, below)
                else:
                    below = 0
            except:
                pass

    # Rule ①
    if max_below_1 >= 20:
        violations.append({"rule": "1", "severity": "high",
                           "year": current_year,
                           "description": f"连续{max_below_1}日收盘价<1元"})
    elif close is not None:
        summary.append(f"- 最新收盘价: {close:.2f}元，连续<1元: {max_below_1}日（规则①通过）")
    else:
        summary.append(f"- 收盘价数据获取失败，规则①无法核验")

    # Rule ④
    if is_st == '1':
        violations.append({"rule": "4", "severity": "high",
                           "year": current_year,
                           "description": "已被交易所实施ST/*ST"})
    elif is_st == '0':
        summary.append(f"- ST状态: 正常（规则④通过）")
    else:
        summary.append(f"- ST状态: 未获取，规则④无法核验")

    # ---- 年报利润表 ----
    net_profit = None
    revenue = None
    total_share = None
    try:
        rs = bs.query_profit_data(code=code_bs, year=report_year, quarter=4)
        while (rs.error_code == '0') & rs.next():
            r = rs.get_row_data()
            try:
                net_profit = float(r[6]) if r[6] else None
            except (ValueError, TypeError, IndexError):
                pass
            try:
                revenue = float(r[8]) if r[8] else None
            except (ValueError, TypeError, IndexError):
                pass
            try:
                total_share = float(r[9]) if r[9] else None
            except (ValueError, TypeError, IndexError):
                pass
            break
    except Exception as e:
        if debug:
            print(f"  [!] baostock 利润表查询失败: {e}")

    if net_profit is not None:
        summary.append(f"- {report_year}年归母净利润: {net_profit/1e8:.2f}亿元")
    if revenue is not None:
        summary.append(f"- {report_year}年营业收入: {revenue/1e8:.2f}亿元")
    if total_share is not None:
        summary.append(f"- 总股本: {total_share/1e8:.2f}亿股")

    # Rule ③
    rev_threshold = 1e8 if board in ('科创板', '创业板') else 3e8
    if net_profit is not None and revenue is not None:
        if net_profit < 0 and revenue < rev_threshold:
            violations.append({"rule": "3", "severity": "high", "year": report_year,
                               "description": f"净利润{net_profit/1e8:.2f}亿<0且营收{revenue/1e8:.2f}亿<{rev_threshold/1e8:.0f}亿"})
        else:
            profit_s = "负" if net_profit < 0 else "正"
            summary.append(f"- 净利润{profit_s}, 营收{'<=' if revenue < rev_threshold else '>'}阈值（{board} {rev_threshold/1e8:.0f}亿），规则③通过")
    else:
        summary.append(f"- 利润数据缺失，规则③无法核验")

    # Rule ⑫
    if board == '主板' and close is not None and total_share is not None:
        market_cap = close * total_share
        summary.append(f"- 总市值: {market_cap/1e8:.2f}亿元")
        if market_cap < 5e8:
            max_below_5b = 0
            mc_below = 0
            for row in daily_rows:
                try:
                    if row[1]:
                        cap = float(row[1]) * total_share
                        if cap < 5e8:
                            mc_below += 1
                            max_below_5b = max(max_below_5b, mc_below)
                        else:
                            mc_below = 0
                except:
                    pass
            if max_below_5b >= 20:
                violations.append({"rule": "12", "severity": "high", "year": current_year,
                                   "description": f"连续{max_below_5b}日市值<5亿"})
            elif max_below_5b > 0:
                summary.append(f"- 市值<5亿天数: {max_below_5b}日（未达20日阈值，规则⑫通过）")
            else:
                summary.append(f"- 市值>5亿，规则⑫通过")
        else:
            summary.append(f"- 市值>5亿，规则⑫通过")
    elif board != '主板':
        summary.append(f"- 市值退市仅主板适用（{board}，规则⑫不适用）")
    elif close is not None and total_share is not None:
        summary.append(f"- 总市值: {close*total_share/1e8:.2f}亿元")
    else:
        summary.append(f"- 市值数据缺失，规则⑫无法核验")

    return violations, summary

# 各规则在 external_info 中需要的关键词证据（LLM 声称违规时用于交叉验证）
RULE_EVIDENCE_KEYWORDS = {
    "1": ["面值", "低于1元"],
    "2": ["留置", "立案", "监管", "处罚", "警示函", "责令改正", "通报批评", "公开谴责", "纪律审查", "监察调查"],
    "3": ["净利润", "营收", "亏损", "营业收入"],
    "4": ["ST", "*ST", "风险警示"],
    "5": ["否定意见", "无法表示意见", "内控审计"],
    "6": ["诉讼", "仲裁", "起诉", "涉案"],
    "7": ["会计差错更正"],
    "8": ["资金占用", "违规担保"],
    "9": ["分红", "利润分配"],
    "10": ["净资产", "资不抵债"],
    "11": ["财务造假"],
    "12": ["市值", "退市"],
}

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
规则已按触发频率从高到低排列。你必须按①→⑫顺序逐一检查，一旦确认任一违规立即停止（输出当前违规结果，不检查后续规则）。所有判断基于提供的金融数据核验结果和公告标题进行，无需联网搜索。

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
        f"请判断股票{code}目前的合规状况。\n\n"
        f"{external_info}\n"
        "请基于以上提供的金融数据核验结果和公告标题进行判断。\n"
        "规则①③④⑫已由系统预检（若数据中标记\"通过\"则无需再判）。\n"
        "规则②⑤⑦⑪已由系统预检公告标题。\n"
        "仅需关注规则⑥（重大诉讼）、⑧（资金占用/违规担保）、⑨（分红不达标）、⑩（净资产为负）是否从公告标题中触发。\n"
        "若公告标题未明确提及相关违规信息，应判定合规（信息不足）。\n"
        "请注意：所有判断必须严格限定在上市公司主体层面。除非明确说明，子公司的财务数据、经营亏损、法律诉讼、被罚款/处罚、会计差错等，不应直接视为上市公司本体的违规。\n"
        "区分上市公司自身被ST与因其子公司、主要投资标的或参股公司出现问题带来的股价波动。\n"
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
        f"请判断股票{code}目前的合规状况。\n\n"
        f"{external_info}\n"
        "请基于以上提供的金融数据核验结果和公告标题进行判断。\n"
        "规则①③④⑫已由系统预检（若数据中标记\"通过\"则无需再判）。\n"
        "规则②⑤⑦⑪已由系统预检公告标题。\n"
        "仅需关注规则⑥（重大诉讼）、⑧（资金占用/违规担保）、⑨（分红不达标）、⑩（净资产为负）是否从公告标题中触发。\n"
        "若公告标题未明确提及相关违规信息，应判定合规（信息不足）。\n"
        "请注意：所有判断必须严格限定在上市公司主体层面。除非明确说明，子公司的财务数据、经营亏损、法律诉讼、被罚款/处罚、会计差错等，不应直接视为上市公司本体的违规。\n"
        "区分上市公司自身被ST与因其子公司、主要投资标的或参股公司出现问题带来的股价波动。\n"
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
    """从违规描述中提取最近提及的4位年份（不超过当前年）"""
    if not text:
        return None
    current_year = datetime.datetime.now().year
    matches = re.findall(r'(20\d{2})', text)
    if matches:
        years = [int(y) for y in matches if int(y) <= current_year]
        if years:
            return max(years)
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

# -------------------- 扩展本地扫描（规则②⑤⑦⑪） --------------------
def _local_scan_extended(flagged_lines: List[str], all_external_info: str) -> List[dict]:
    """
    扫描公告标题，纯代码判定规则 ②⑤⑦⑪。
    规则②沿用现有 _local_rule2_scan（含分级×时效）。
    规则⑤⑦⑪ 为简单关键词匹配，命中即结论。
    返回所有命中的违规列表。
    """
    violations = []
    current_year = datetime.datetime.now().year

    # 规则②：分级×时效扫描
    if flagged_lines:
        rule2_violations = _local_rule2_scan(flagged_lines)
        violations.extend(rule2_violations)

    full_text = all_external_info or ""

    # 规则⑤：内控审计否定意见/无法表示意见
    for kw in ["否定意见", "无法表示意见"]:
        if kw in full_text:
            year = _extract_year_from_reason(full_text) or current_year
            violations.append({
                "rule": "5", "severity": "high", "year": year,
                "description": f"内控审计报告被出具{kw}"
            })
            break

    # 规则⑦：会计差错更正
    if "会计差错更正" in full_text:
        year = _extract_year_from_reason(full_text) or current_year
        violations.append({
            "rule": "7", "severity": "high", "year": year,
            "description": "发布会计差错更正公告"
        })

    # 规则⑪：财务造假
    if "财务造假" in full_text:
        year = _extract_year_from_reason(full_text) or current_year
        violations.append({
            "rule": "11", "severity": "high", "year": year,
            "description": "涉及财务造假"
        })

    return violations

def _apply_tiered_filter(is_qualified: bool, reason: str,
                         violated_rules: List[str],
                         violation_details: List[dict],
                         external_info: str = "",
                         fin_summary: str = "") -> Tuple[bool, str, List[str]]:
    """泛化证据交叉校验 + 规则②分级×时效过滤"""
    if is_qualified:
        return True, reason, violated_rules

    violated_rules = _normalize_rules(violated_rules)
    if violation_details:
        for vd in violation_details:
            if isinstance(vd.get("rule"), str):
                vd["rule"] = vd["rule"].translate(_RULE_CIRCLED)

    full_text = (fin_summary or "") + "\n" + (external_info or "")

    # ---- Step 1: 泛化证据交叉校验 ----
    # 模型声称的每条违规必须在 external_info（公告标题）中有对应关键词证据
    unverifiable_rules = []
    for rule in violated_rules:
        if rule == "2":
            continue  # 规则②有专门的分级×时效处理
        keywords = RULE_EVIDENCE_KEYWORDS.get(rule, [])
        if keywords and not any(kw in external_info for kw in keywords):
            unverifiable_rules.append(rule)

    if unverifiable_rules:
        remaining = [r for r in violated_rules if r not in unverifiable_rules]
        print(f"  [!] 规则{','.join(unverifiable_rules)}违规缺乏公告标题证据，不予采信")
        if not remaining:
            return True, reason + f"（违规缺乏固定源证据，不予采信）", remaining
        violated_rules = remaining

    # ---- Step 2: 规则②分级×时效过滤（沿用现有逻辑） ----
    if "2" not in violated_rules:
        return False, reason, violated_rules

    # 规则②本地证据校验：固定源公告标题无任何风险关键词 → 模型判断可能来自搜索引擎噪声
    if external_info and not any(kw in external_info for kw in RISK_FLAGS):
        remaining = [r for r in violated_rules if r != "2"]
        if not remaining:
            print(f"  [!] 规则②违规缺乏固定源公告证据，按合规处理")
            return True, reason + "（缺乏固定源证据，规则②不予采信）", remaining
        return False, reason, remaining

    tier_rules = config.get("violation_tier_rules", {})
    current_year = datetime.datetime.now().year

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
                break
    else:
        severity = _classify_violation(reason)
        vyear = _extract_year_from_reason(reason)
        lookback = tier_rules.get(severity, {}).get("lookback_years", 3)
        rule2_valid = bool(vyear and current_year - vyear <= lookback)

    if not rule2_valid:
        remaining = [r for r in violated_rules if r != "2"]
        if not remaining:
            return True, reason + "（违规已超过时效窗口，豁免）", remaining
        return False, reason, remaining

    return False, reason, violated_rules

# -------------------- Layer 4: 外部搜索收尾 --------------------
def _deterministic_search(query: str, debug: bool = False) -> str:
    """
    Layer 4: 确定性外部搜索。
    用 requests 直接调搜索引擎，取前 5 条结果标题+摘要。
    不依赖 LLM 内建搜索，不改变 enable_search=False 原则。
    """
    encoded = requests.utils.quote(query)
    results = []

    # Bing 搜索（中国大陆可访问，HTML 结构较稳定）
    # 排除股价/行情类页面噪声
    exclusion = "+-股价+-行情+-走势"
    try:
        url = f"https://www.bing.com/search?q={encoded}{requests.utils.quote(exclusion)}&setlang=zh-cn&count=5"
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("#b_results .b_algo")[:5]:
                title_el = item.select_one("h2 a")
                snippet_el = item.select_one(".b_caption p, .b_lineclamp2, .b_snippet, .b_paractl")
                title = title_el.get_text(strip=True) if title_el else ""
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                # 跳过纯股价页面（标题仅含股票名+价格）
                if title and not re.match(r'^[\u4e00-\u9fa5]+\s*\d{6}.*[（(].*股价.*[）)]', title):
                    results.append(f"- {title}\n  {snippet}" if snippet else f"- {title}")
    except Exception as e:
        if debug:
            print(f"  [!] Bing 搜索异常: {e}")

    if results:
        return "【外部搜索结果】\n" + "\n".join(results[:5])
    return ""


# Layer 4 高信号关键词：标题含这些才值得触发搜索
L4_HIGH_SIGNAL = [
    "涉案金额", "应诉通知书", "重大诉讼", "诉讼进展", "仲裁进展",
    "关联方资金占用", "违规担保",
]

def _should_trigger_layer4(external_info: str) -> bool:
    """Layer 3 判合规但标题含高信号关键词 → 搜索查漏补缺"""
    return any(kw in external_info for kw in L4_HIGH_SIGNAL)

# -------------------- 主筛选函数 --------------------
def filter_stocks(stock_list: List[str], delay: float = 2.0, debug: bool = False) -> List[str]:
    def norm(code: str) -> str:
        return code.split('.')[0] if '.' in code else code
    original_map = {norm(raw): raw for raw in stock_list}
    normalized = list(original_map.keys())
    qualified = []

    maintain_sources(debug)

    print(f"\n筛选 {len(normalized)} 只股票（4层流水线）")
    if debug:
        print("DEBUG模式")
    print("-" * 60)

    # baostock 登录（整个筛选周期一次）
    bs_ok = _bs_login()
    if not bs_ok:
        print("  [!] baostock 不可用，Layer2 金融数据层将全部跳过")

    with open(DEBUG_LOG, "w", encoding="utf-8") as log_file:
        log_file.write(f"=== RUN: {datetime.datetime.now().isoformat()} ===\n")

        for idx, code in enumerate(normalized, 1):
            raw_code = original_map[code]
            print(f"[{idx}/{len(normalized)}] {code}")
            log_file.write(f"\n{'='*60}\n")
            log_file.write(f"[{idx}/{len(normalized)}] {code}\n\n")

            # ---- 收集公告标题（Title Layer） ----
            external_info, flagged_lines = collect_external_info(raw_code, debug=debug, log_file=log_file)
            log_file.write(f"  ── 提取的 flagged_lines (RISK_FLAGS) ──\n")
            if flagged_lines:
                for fl in flagged_lines:
                    log_file.write(f"  {fl}\n")
            else:
                log_file.write(f"  (空)\n")

            # ======== Layer 1: 扩展本地扫描（规则②⑤⑦⑪） ========
            local_violations = _local_scan_extended(flagged_lines, external_info)
            if local_violations:
                vd = local_violations[0]
                rules_hit = sorted(set(v["rule"] for v in local_violations))
                print(f"  [SCAN] 标题扫描命中规则{','.join(rules_hit)} | {vd['description'][:50]}")
                print(f"  [FAIL] 剔除（Layer 1）")
                log_file.write(f"\n  ── Layer 1 标题扫描 ──\n")
                for v in local_violations:
                    log_file.write(f"  命中: rule={v['rule']}, severity={v['severity']}, year={v['year']}\n")
                    log_file.write(f"  description: {v['description']}\n")
                log_file.write(f"  结果: 跳过后续层，直接剔除\n")
                continue

            # ======== Layer 2: 金融数据核验（规则①③④⑫） ========
            fin_violations = []
            fin_summary_lines = []
            if bs_ok:
                fin_violations, fin_summary_lines = _check_financial_rules(code, raw_code, debug=debug)
            else:
                fin_summary_lines = ["- baostock 不可用，金融数据层跳过"]

            log_file.write(f"\n  ── Layer 2 金融数据核验 ──\n")
            for line in fin_summary_lines:
                log_file.write(f"  {line}\n")

            if fin_violations:
                vd = fin_violations[0]
                rules_hit = sorted(set(v["rule"] for v in fin_violations))
                print(f"  [DATA] 金融数据命中规则{','.join(rules_hit)} | {vd['description'][:50]}")
                print(f"  [FAIL] 剔除（Layer 2）")
                for v in fin_violations:
                    log_file.write(f"  命中: rule={v['rule']}, severity={v['severity']}, year={v['year']}\n")
                    log_file.write(f"  description: {v['description']}\n")
                log_file.write(f"  结果: 跳过后续层，直接剔除\n")
                continue

            # ======== Layer 3: LLM 兜底判断（无联网搜索，输入确定） ========
            fin_block = ""
            if fin_summary_lines:
                fin_block = "【金融数据核验结果】\n" + "\n".join(fin_summary_lines) + "\n\n"

            augmented_info = fin_block + external_info if external_info else fin_block

            log_file.write(f"\n  ── 发送给模型的 augmented_info ──\n")
            log_file.write(f"{augmented_info[:3000]}\n" if augmented_info else "(空)\n")

            if not external_info.strip():
                print(f"  [!] 外部公告数据为空，仅依赖金融数据")
            elif not debug:
                print(f"  [INFO] 外部信息加载完成 ({len(external_info)}字符)")

            model_qualified, reason, rules, violation_details, model_used = _call_with_fallback(code, augmented_info, debug=debug)
            log_file.write(f"\n  ── 模型返回 ──\n")
            log_file.write(f"  model: {model_used}\n")
            log_file.write(f"  is_qualified: {model_qualified}\n")
            log_file.write(f"  reason: {reason}\n")
            log_file.write(f"  violated_rules: {rules}\n")
            log_file.write(f"  violation_details: {violation_details}\n")

            is_qualified, reason, rules = _apply_tiered_filter(
                model_qualified, reason, rules, violation_details,
                external_info=external_info, fin_summary=fin_block
            )

            # ======== Layer 4: 外部搜索查漏补缺 ========
            # 仅 Layer 3 判合规 + 标题含高信号关键词时触发（查漏杀）
            l4_triggered = False
            if is_qualified and _should_trigger_layer4(external_info):
                l4_triggered = True
                search_query = f"{code} 公告 重大诉讼 违规担保 关联方"
                if debug:
                    matched = [kw for kw in L4_HIGH_SIGNAL if kw in external_info]
                    print(f"  [L4] 合规但标题含高信号({','.join(matched)})→ 外部搜索")

                search_results = _deterministic_search(search_query, debug)
                log_file.write(f"\n  ── Layer 4 外部搜索（查漏补缺） ──\n")
                log_file.write(f"  matched_keywords: {[kw for kw in L4_HIGH_SIGNAL if kw in external_info]}\n")
                log_file.write(f"  query: {search_query}\n")
                log_file.write(f"  raw: {search_results[:500] if search_results else '(空)'}\n")

                if search_results:
                    l4_augmented = search_results + "\n\n" + fin_block + external_info
                    retry_q, retry_reason, retry_rules, retry_vd, retry_model = _call_with_fallback(
                        code, l4_augmented, debug=debug
                    )
                    log_file.write(f"\n  ── Layer 4 复审模型返回 ──\n")
                    log_file.write(f"  model: {retry_model}\n")
                    log_file.write(f"  is_qualified: {retry_q}\n")
                    log_file.write(f"  reason: {retry_reason}\n")
                    log_file.write(f"  violated_rules: {retry_rules}\n")

                    if retry_q is not None and not retry_q:
                        l4_is_q, l4_reason, l4_rules = _apply_tiered_filter(
                            retry_q, retry_reason, retry_rules, retry_vd,
                            external_info=external_info, fin_summary=fin_block
                        )
                        if not l4_is_q:
                            print(f"  [L4→FAIL] 外部搜索证实违规，覆写Layer 3结果")
                            is_qualified = False
                            reason = l4_reason
                            rules = l4_rules
                            model_qualified = retry_q
                    elif retry_q is not None:
                        if debug:
                            print(f"  [L4] 外部搜索后仍判定合规")
                elif debug:
                    print(f"  [L4] 外部搜索无结果，维持Layer 3合规判定")

            if is_qualified:
                if not model_qualified:
                    print(f"  [OK] 保留（时效豁免/证据不足豁免）")
                    log_file.write(f"  最终: [OK] 保留（豁免）\n")
                else:
                    print(f"  [OK] 保留")
                    log_file.write(f"  最终: [OK] 保留\n")
                qualified.append(code)
            else:
                print(f"  [FAIL] 剔除 | 触发规则: {', '.join(rules) if rules else '无'} | {reason[:80]}")
                log_file.write(f"  最终: [FAIL] 剔除\n")
            if idx < len(normalized):
                time.sleep(delay)

    _bs_logout()
    print("-" * 60)
    print(f"完成，{len(qualified)}/{len(normalized)} 合规")
    return [original_map[code] for code in qualified]

if __name__ == "__main__":
    # test = ["000001.sz", "000858.sz", "600519.sh", "000639.sz", "605177.sh", "002758.sz"]
    test = ["600638.XSHG", "002582.XSHE", "000498.XSHE", "000421.XSHE", "001218.XSHE", "000906.XSHE", "002614.XSHE", "600455.XSHG", "601188.XSHG", "605177.XSHG", "600768.XSHG", "002758.XSHE", "002054.XSHE", "002745.XSHE"]
    result = filter_stocks(test, delay=2.0, debug=True)
    print(f"\n最终合规股票池: {result}")
