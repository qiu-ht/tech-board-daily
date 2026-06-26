#!/usr/bin/env python3
"""
科技板块涨跌自动查询脚本
- 数据源: 东方财富网公开API (push2.eastmoney.com)
- 覆盖: 概念板块 + 行业板块 中所有科技相关板块
- 输出: 控制台表格 + HTML报告 + JSON数据文件

502问题说明:
  push2.eastmoney.com 是东方财富的高频行情推送节点，非交易时段偶尔502是正常现象。
  脚本已内置多重保障：Session复用、递增重试、Header轮换、缓存兜底。

本地运行:
  pip install -r requirements.txt
  python tech_board_daily.py

离线安装:
  pip install --no-index --find-links=vendor -r requirements.txt
"""

import json
import time
import datetime
import os
import sys
import random

# ── HTTP库检测 ──
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

if not HAS_REQUESTS and not HAS_CURL_CFFI:
    print("[ERROR] 需要安装 requests 或 curl_cffi")
    print("  pip install requests")
    print("  pip install curl_cffi")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────────

# 科技相关关键词
TECH_KEYWORDS = [
    "CPO", "半导体", "芯片", "AI", "人工智能", "光模块", "算力", "GPU",
    "存储", "数据中心", "机器人", "5G", "通信", "华为", "苹果", "消费电子",
    "量子", "脑机", "低空", "固态电池", "新能源", "光伏", "储能", "汽车电子",
    "无人驾驶", "软件", "网络安全", "光刻", "服务器", "PCB", "英伟达",
    "AIGC", "智谱", "大模型", "边缘计算", "液冷", "铜缆", "高速连接",
    "芯片设计", "封装", "EDA", "传感", "汽车芯片", "车联网", "智能驾驶",
    "自动驾驶", "Sora", "短剧", "F5G", "光通信", "人形", "AI眼镜",
    "AI手机", "AIPC", "多模态", "AI智能体", "AI语料", "AI应用", "AI制药",
    "昇腾", "海思", "欧拉", "执行器", "第四代半导体", "先进封装",
    "第三代半导体", "国产芯片", "中芯", "纳米银", "3D玻璃",
    "模拟芯片", "数字芯片",
]

API_URL = "https://push2.eastmoney.com/api/qt/clist/get"
FIELDS = "f12,f14,f2,f3,f4,f104,f105,f62"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(SCRIPT_DIR, "output"))
CACHE_FILE = os.path.join(OUTPUT_DIR, ".last_cache.json")

# 多组User-Agent和Referer轮换，降低被限概率
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]
REFERERS = [
    "https://quote.eastmoney.com/center/boardlist.html",
    "https://data.eastmoney.com/bkzj/hy.html",
    "https://quote.eastmoney.com/",
]

# ── HTTP请求层 ──────────────────────────────────────────────────


def _create_session():
    """创建带连接池的Session"""
    s = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=5,
        pool_maxsize=10,
        max_retries=requests.adapters.Retry(total=2, backoff_factor=0.5),
    )
    s.mount("https://", adapter)
    return s


SESSION = _create_session() if HAS_REQUESTS else None


def _random_headers():
    """随机选一组headers，降低被识别概率"""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": random.choice(REFERERS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }


def _http_get(url, params, timeout=15, max_retries=4):
    """HTTP GET，502自动重试，重试时换Headers"""
    last_error = None
    for attempt in range(max_retries):
        headers = _random_headers()

        # 优先curl_cffi（Linux下TLS指纹更自然）
        if HAS_CURL_CFFI:
            try:
                resp = cffi_requests.get(
                    url, params=params, headers=headers,
                    impersonate="chrome", timeout=timeout
                )
                if resp.status_code in (502, 503, 504):
                    if attempt < max_retries - 1:
                        wait = 2 ** attempt + random.uniform(1, 3)
                        time.sleep(wait)
                        continue
                if resp.status_code != 200 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt + random.uniform(0, 2))
                    continue
                return resp
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt + random.uniform(1, 2))

        # 标准requests
        if HAS_REQUESTS:
            try:
                resp = SESSION.get(
                    url, params=params, headers=headers,
                    timeout=timeout
                )
                if resp.status_code in (502, 503, 504):
                    if attempt < max_retries - 1:
                        wait = 2 ** attempt + random.uniform(1, 3)
                        print(f"  [RETRY] HTTP {resp.status_code}，{wait:.1f}秒后重试...")
                        time.sleep(wait)
                        continue
                if resp.status_code != 200:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt + random.uniform(0, 2))
                    continue
                return resp
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt + random.uniform(1, 2)
                    print(f"  [RETRY] {type(e).__name__}，{wait:.1f}秒后重试...")
                    time.sleep(wait)

    raise last_error or RuntimeError(f"HTTP请求失败（重试{max_retries}次）")


# ── 数据获取层 ──────────────────────────────────────────────────


def fetch_board_page(fs_code: str, page: int) -> tuple:
    """获取单页板块数据，返回 (boards, total)"""
    params = {
        "pn": str(page),
        "pz": "100",
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": fs_code,
        "fields": FIELDS,
        "_": str(int(time.time() * 1000)),
    }
    resp = _http_get(API_URL, params=params, timeout=15)
    data = resp.json()
    if not data.get("data") or not data["data"].get("diff"):
        return [], 0
    return data["data"]["diff"], data["data"]["total"]


def fetch_board_list(fs_code: str, max_pages: int = 10) -> list:
    """分页获取板块列表"""
    all_boards = []
    total = None

    # 先获取第一页拿total
    try:
        boards, total = fetch_board_page(fs_code, 1)
        all_boards.extend(boards)
        if total is None or total <= 100:
            return all_boards
    except Exception as e:
        print(f"[WARN] 第1页失败: {e}")

    if not all_boards:
        return all_boards

    # 获取剩余页
    total_pages = min(max_pages, (total // 100) + 1)
    for pn in range(2, total_pages + 1):
        try:
            boards, _ = fetch_board_page(fs_code, pn)
            all_boards.extend(boards)
        except Exception as e:
            print(f"[WARN] 第{pn}页失败: {e}")
        time.sleep(0.8 + random.uniform(0, 0.5))  # 随机间隔
    return all_boards


def filter_tech_boards(boards: list) -> list:
    """筛选科技相关板块"""
    found = []
    for b in boards:
        name = b.get("f14", "")
        for kw in TECH_KEYWORDS:
            if kw in name:
                found.append({
                    "code": b.get("f12"),
                    "name": name,
                    "price": b.get("f2", "-"),
                    "change_pct": b.get("f3", "-"),
                    "change_amt": b.get("f4", "-"),
                    "up_count": b.get("f104", "-"),
                    "down_count": b.get("f105", "-"),
                    "main_net_inflow": b.get("f62", "-"),
                })
                break
    return found


# ── 缓存机制（API全挂时用上次数据兜底）──────────────────────────


def load_cache():
    """加载上次缓存的板块数据"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
                return cache.get("boards", [])
        except Exception:
            pass
    return []


def save_cache(tech_boards: list):
    """保存板块数据到缓存"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "boards": tech_boards,
        }, f, ensure_ascii=False)
    os.chmod(CACHE_FILE, 0o600)  # 只让当前用户可读写


# ── 交易时段判断 ──────────────────────────────────────────────────


def is_trading_time(now=None):
    """判断当前是否为A股交易时段"""
    if now is None:
        now = datetime.datetime.now()
    # 周末不交易
    if now.weekday() >= 5:
        return False, "周末休市"
    t = now.time()
    morning_start = datetime.time(9, 15)
    morning_end = datetime.time(11, 30)
    afternoon_start = datetime.time(13, 0)
    afternoon_end = datetime.time(15, 0)
    if morning_start <= t <= morning_end:
        return True, "早盘交易中"
    if afternoon_start <= t <= afternoon_end:
        return True, "午盘交易中"
    if t < morning_start:
        return False, "尚未开盘（9:15开盘）"
    if morning_end < t < afternoon_start:
        return False, "午间休市"
    return False, "已收盘"


# ── 输出格式化 ──────────────────────────────────────────────────


def format_console(tech_boards: list, date_str: str, source_label: str) -> str:
    lines = []
    lines.append(f"\n{'='*62}")
    lines.append(f"  📊 科技板块涨跌日报 - {date_str}")
    lines.append(f"{'='*62}")
    lines.append(f"  数据源: {source_label}")
    lines.append(f"  共监控 {len(tech_boards)} 个科技相关板块")
    lines.append(f"{'='*62}\n")

    up_boards = [b for b in tech_boards if isinstance(b["change_pct"], (int, float)) and b["change_pct"] > 0]
    up_boards.sort(key=lambda x: x["change_pct"], reverse=True)
    if up_boards:
        lines.append("🟢 涨幅榜 TOP10:")
        for i, b in enumerate(up_boards[:10], 1):
            lines.append(f"  {i:>2}. {b['name']:<16} {b['change_pct']:>+.2f}%  指数:{b['price']}")

    down_boards = [b for b in tech_boards if isinstance(b["change_pct"], (int, float)) and b["change_pct"] < 0]
    down_boards.sort(key=lambda x: x["change_pct"])
    if down_boards:
        lines.append("\n🔴 跌幅榜 TOP10:")
        for i, b in enumerate(down_boards[:10], 1):
            lines.append(f"  {i:>2}. {b['name']:<16} {b['change_pct']:>+.2f}%  指数:{b['price']}")

    all_sorted = sorted(tech_boards, key=lambda x: x["change_pct"] if isinstance(x["change_pct"], (int, float)) else 0, reverse=True)
    lines.append(f"\n📋 全部科技板块 ({len(all_sorted)}个):")
    lines.append(f"  {'板块':<16} {'涨跌幅':>8} {'指数':>10} {'涨':>4} {'跌':>4} {'主力净流入(万)':>14}")
    lines.append(f"  {'-'*62}")
    for b in all_sorted:
        pct = b["change_pct"]
        pct_str = f"{pct:>+.2f}%" if isinstance(pct, (int, float)) else str(pct)
        inflow = b["main_net_inflow"]
        inflow_str = f"{inflow:>+.0f}" if isinstance(inflow, (int, float)) else str(inflow)
        lines.append(f"  {b['name']:<16} {pct_str:>8} {str(b['price']):>10} {str(b['up_count']):>4} {str(b['down_count']):>4} {inflow_str:>14}")

    lines.append(f"\n{'='*62}")
    return "\n".join(lines)


def format_html(tech_boards: list, date_str: str, source_label: str) -> str:
    all_sorted = sorted(tech_boards,
        key=lambda x: x["change_pct"] if isinstance(x["change_pct"], (int, float)) else 0,
        reverse=True)
    up_count = len([b for b in tech_boards if isinstance(b["change_pct"], (int, float)) and b["change_pct"] > 0])
    down_count = len([b for b in tech_boards if isinstance(b["change_pct"], (int, float)) and b["change_pct"] < 0])
    flat_count = len(tech_boards) - up_count - down_count

    rows_html = ""
    for b in all_sorted:
        pct = b["change_pct"]
        pct_val = pct if isinstance(pct, (int, float)) else 0
        color = "#e74c3c" if pct_val < 0 else ("#27ae60" if pct_val > 0 else "#999")
        pct_str = f"{pct:>+.2f}%" if isinstance(pct, (int, float)) else str(pct)
        inflow = b["main_net_inflow"]
        inflow_str = f"{inflow:>+.0f}" if isinstance(inflow, (int, float)) else str(inflow)
        inflow_color = "#e74c3c" if isinstance(inflow, (int, float)) and inflow < 0 else ("#27ae60" if isinstance(inflow, (int, float)) and inflow > 0 else "#999")
        rows_html += f"""
        <tr>
            <td>{b['name']}</td>
            <td style="color:{color};font-weight:bold">{pct_str}</td>
            <td>{b['price']}</td>
            <td>{b['change_amt']}</td>
            <td>{b['up_count']}</td>
            <td>{b['down_count']}</td>
            <td style="color:{inflow_color}">{inflow_str}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>科技板块涨跌日报 - {date_str}</title>
<style>
    body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }}
    h1 {{ text-align: center; color: #e0e0e0; }}
    .meta {{ text-align: center; color: #aaa; margin: 10px 0; }}
    .stats {{ text-align: center; margin: 20px 0; }}
    .stat-card {{ display: inline-block; padding: 10px 20px; margin: 5px; border-radius: 8px; }}
    .stat-up {{ background: #27ae60; }}
    .stat-down {{ background: #e74c3c; }}
    .stat-flat {{ background: #555; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
    th {{ background: #16213e; padding: 12px; text-align: center; }}
    td {{ padding: 10px; text-align: center; border-bottom: 1px solid #333; }}
    tr:nth-child(even) {{ background: #16213e; }}
    .footer {{ text-align: center; color: #777; margin-top: 30px; font-size: 12px; }}
</style>
</head>
<body>
<h1>📊 科技板块涨跌日报</h1>
<p class="meta">{date_str} | {source_label}</p>
<div class="stats">
    <span class="stat-card stat-up">🟢 上涨 {up_count} 个</span>
    <span class="stat-card stat-down">🔴 下跌 {down_count} 个</span>
    <span class="stat-card stat-flat">⚪ 平盘 {flat_count} 个</span>
</div>
<table>
<thead><tr>
    <th>板块名称</th><th>涨跌幅</th><th>指数点位</th><th>涨跌额</th><th>上涨家数</th><th>下跌家数</th><th>主力净流入(万)</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
<div class="footer">
    <p>数据源: 东方财富 push2.eastmoney.com | 完全免费 无需注册</p>
</div>
</body>
</html>"""


# ── 主流程 ──────────────────────────────────────────────────────


def main():
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M:%S")
    date_file = now.strftime("%Y%m%d")

    # 交易时段提示
    trading, trading_msg = is_trading_time(now)
    print(f"[INFO] 当前时间: {date_str} | {trading_msg}")

    # HTTP库信息
    lib_info = []
    if HAS_CURL_CFFI:
        lib_info.append("curl_cffi")
    if HAS_REQUESTS:
        lib_info.append("requests")
    print(f"[INFO] HTTP引擎: {', '.join(lib_info)} | 重试策略: 指数退避+随机抖动")

    # 获取数据（最多尝试3轮）
    tech_boards = []
    source_label = "东方财富 push2.eastmoney.com"
    for round_num in range(1, 4):
        try:
            print(f"\n[INFO] --- 第{round_num}轮尝试获取数据 ---")
            concept_boards = fetch_board_list("m:90+t:3", max_pages=10)
            print(f"[INFO] 概念板块: {len(concept_boards)}个")
            industry_boards = fetch_board_list("m:90+t:2", max_pages=3)
            print(f"[INFO] 行业板块: {len(industry_boards)}个")
            all_boards = concept_boards + industry_boards
            tech_boards = filter_tech_boards(all_boards)

            if tech_boards:
                print(f"[INFO] ✅ 匹配到 {len(tech_boards)} 个科技相关板块")
                break
            else:
                print(f"[WARN] 未匹配到板块，可能API返回空数据")

        except Exception as e:
            print(f"[WARN] 第{round_num}轮失败: {e}")
            if round_num < 3:
                wait = 10 * round_num
                print(f"[INFO] 等待{wait}秒后重试...")
                time.sleep(wait)

        if round_num == 3 and not tech_boards:
            print("\n[INFO] API三轮都失败，尝试从缓存加载上次数据...")
            tech_boards = load_cache()
            if tech_boards:
                source_label = "本地缓存 (API不可用时的兜底数据)"
                print(f"[WARN] 使用缓存数据（{len(tech_boards)}个板块），非实时数据！")

    if not tech_boards:
        print("[ERROR] 无法获取任何板块数据，请检查网络连接")
        if not trading:
            print("[提示] 当前非交易时段，服务器可能处于维护状态，交易时段重试即可")
        sys.exit(1)

    # 保存缓存
    save_cache(tech_boards)

    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 控制台输出
    console_output = format_console(tech_boards, date_str, source_label)
    print(console_output)

    # JSON
    json_file = os.path.join(OUTPUT_DIR, f"tech_board_{date_file}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({
            "date": date_str,
            "source": source_label,
            "trading_status": trading_msg,
            "tech_board_count": len(tech_boards),
            "boards": tech_boards,
        }, f, ensure_ascii=False, indent=2)
    print(f"[INFO] JSON: {json_file}")

    # HTML
    html_file = os.path.join(OUTPUT_DIR, f"tech_board_{date_file}.html")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(format_html(tech_boards, date_str, source_label))
    print(f"[INFO] HTML: {html_file}")

    # TXT
    txt_file = os.path.join(OUTPUT_DIR, f"tech_board_{date_file}.txt")
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(console_output)
    print(f"[INFO] TXT: {txt_file}")

    return tech_boards


if __name__ == "__main__":
    main()
