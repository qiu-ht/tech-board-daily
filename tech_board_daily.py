#!/usr/bin/env python3
"""
科技板块涨跌自动查询脚本
- 数据源: 东方财富网公开API (push2.eastmoney.com)
- 覆盖: 概念板块 + 行业板块 中所有科技相关板块
- 输出: 控制台表格 + HTML报告 + JSON数据文件

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

# 使用标准 requests（Windows/Linux通用，无TLS指纹问题）
# curl_cffi 可选安装，仅在Linux下用于模拟浏览器指纹
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

# ============================================================
# 配置区域
# ============================================================

# 科技相关关键词（会自动从全部板块中匹配名称包含这些词的板块）
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

# API地址
API_URL = "https://push2.eastmoney.com/api/qt/clist/get"

# 输出目录（默认在脚本所在目录下的 output 子目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(SCRIPT_DIR, "output"))

# ============================================================
# 数据获取
# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}

# 字段说明:
# f2  = 最新价(板块指数)
# f3  = 涨跌幅(%)
# f4  = 涨跌额
# f12 = 板块代码
# f14 = 板块名称
# f104 = 上涨家数
# f105 = 下跌家数
# f62 = 主力净流入(万元)
FIELDS = "f12,f14,f2,f3,f4,f104,f105,f62"


def _http_get(url, params, headers, timeout=15, max_retries=3):
    """统一HTTP GET请求，自动选择最佳可用库，含502/503重试"""
    for attempt in range(max_retries):
        # 优先用 curl_cffi（Linux环境下更稳定），回退到标准 requests
        if HAS_CURL_CFFI:
            try:
                resp = cffi_requests.get(
                    url, params=params, headers=headers,
                    impersonate="chrome", timeout=timeout
                )
                if resp.status_code in (502, 503):
                    if attempt < max_retries - 1:
                        time.sleep(3 + attempt * 2)  # 递增等待
                        continue
                return resp
            except Exception:
                pass  # curl_cffi失败则回退到requests

        if HAS_REQUESTS:
            try:
                resp = requests.get(
                    url, params=params, headers=headers,
                    timeout=timeout
                )
                if resp.status_code in (502, 503):
                    if attempt < max_retries - 1:
                        time.sleep(3 + attempt * 2)  # 递增等待
                        continue
                return resp
            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    time.sleep(3 + attempt * 2)
                    continue
                raise

    raise RuntimeError("所有重试均失败")


def fetch_board_list(fs_code: str, max_pages: int = 10) -> list:
    """分页获取板块列表，包含502自动重试"""
    all_boards = []
    for pn in range(1, max_pages + 1):
        params = {
            "pn": str(pn),
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
        for attempt in range(5):  # 每页最多重试5次（应对502）
            try:
                resp = _http_get(API_URL, params=params, headers=HEADERS, timeout=15)
                # 检查HTTP状态码
                if resp.status_code in (502, 503):
                    print(f"[WARN] 第{pn}页返回{resp.status_code}，等待重试...")
                    time.sleep(3 + attempt * 3)  # 递增等待3/6/9/12/15秒
                    continue
                if resp.status_code != 200:
                    print(f"[WARN] 第{pn}页返回HTTP {resp.status_code}")
                    break

                data = resp.json()
                if not data.get("data") or not data["data"].get("diff"):
                    return all_boards
                boards = data["data"]["diff"]
                total = data["data"]["total"]
                all_boards.extend(boards)
                if pn * 100 >= total:
                    return all_boards
                break  # 成功则跳出重试
            except Exception as e:
                if attempt < 4:
                    print(f"[WARN] 第{pn}页请求异常({type(e).__name__}): {str(e)[:60]}")
                    time.sleep(3 + attempt * 2)
                else:
                    print(f"[WARN] 第{pn}页5次重试均失败，跳过")
        time.sleep(1.5)  # 页间间隔稍长，避免触发限流
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


# ============================================================
# 输出格式化
# ============================================================

def format_console(tech_boards: list, date_str: str) -> str:
    """格式化控制台输出"""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"  📊 科技板块涨跌日报 - {date_str}")
    lines.append(f"{'='*60}")
    lines.append(f"  数据来源: 东方财富网 push2.eastmoney.com API")
    lines.append(f"  共监控 {len(tech_boards)} 个科技相关板块")
    lines.append(f"{'='*60}\n")

    up_boards = [b for b in tech_boards if isinstance(b["change_pct"], (int, float)) and b["change_pct"] > 0]
    up_boards.sort(key=lambda x: x["change_pct"], reverse=True)
    if up_boards:
        lines.append("🟢 涨幅榜 TOP10:")
        for i, b in enumerate(up_boards[:10], 1):
            lines.append(f"  {i:>2}. {b['name']:<16} 涨跌幅:{b['change_pct']:>+.2f}%  指数:{b['price']}  上涨:{b['up_count']} 下跌:{b['down_count']}")

    down_boards = [b for b in tech_boards if isinstance(b["change_pct"], (int, float)) and b["change_pct"] < 0]
    down_boards.sort(key=lambda x: x["change_pct"])
    if down_boards:
        lines.append("\n🔴 跌幅榜 TOP10:")
        for i, b in enumerate(down_boards[:10], 1):
            lines.append(f"  {i:>2}. {b['name']:<16} 涨跌幅:{b['change_pct']:>+.2f}%  指数:{b['price']}  上涨:{b['up_count']} 下跌:{b['down_count']}")

    all_sorted = sorted(tech_boards, key=lambda x: x["change_pct"] if isinstance(x["change_pct"], (int, float)) else 0, reverse=True)
    lines.append(f"\n📋 全部科技板块一览 (共{len(all_sorted)}个):")
    lines.append(f"  {'板块名称':<16} {'涨跌幅':>8} {'指数':>10} {'上涨':>4} {'下跌':>4} {'主力净流入(万)':>14}")
    lines.append(f"  {'-'*60}")
    for b in all_sorted:
        pct = b["change_pct"]
        pct_str = f"{pct:>+.2f}%" if isinstance(pct, (int, float)) else str(pct)
        inflow = b["main_net_inflow"]
        inflow_str = f"{inflow:>+.0f}" if isinstance(inflow, (int, float)) else str(inflow)
        lines.append(f"  {b['name']:<16} {pct_str:>8} {str(b['price']):>10} {str(b['up_count']):>4} {str(b['down_count']):>4} {inflow_str:>14}")

    lines.append(f"\n{'='*60}")
    return "\n".join(lines)


def format_html(tech_boards: list, date_str: str) -> str:
    """生成HTML报告"""
    all_sorted = sorted(tech_boards, key=lambda x: x["change_pct"] if isinstance(x["change_pct"], (int, float)) else 0, reverse=True)

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

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>科技板块涨跌日报 - {date_str}</title>
<style>
    body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }}
    h1 {{ text-align: center; color: #e0e0e0; }}
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
<p style="text-align:center;color:#aaa;">{date_str} | 数据来源: 东方财富网 API</p>

<div class="stats">
    <span class="stat-card stat-up">🟢 上涨 {up_count} 个板块</span>
    <span class="stat-card stat-down">🔴 下跌 {down_count} 个板块</span>
    <span class="stat-card stat-flat">⚪ 平盘 {flat_count} 个板块</span>
</div>

<table>
<thead>
<tr>
    <th>板块名称</th>
    <th>涨跌幅</th>
    <th>指数点位</th>
    <th>涨跌额</th>
    <th>上涨家数</th>
    <th>下跌家数</th>
    <th>主力净流入(万)</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>

<div class="footer">
    <p>API: 东方财富 push2.eastmoney.com | fs=m:90+t:3(概念板块) / fs=m:90+t:2(行业板块)</p>
    <p>字段: f2=最新价 f3=涨跌幅 f4=涨跌额 f12=板块代码 f14=板块名称 f104=上涨家数 f105=下跌家数 f62=主力净流入</p>
</div>
</body>
</html>"""
    return html


# ============================================================
# 主流程
# ============================================================

def main():
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M:%S")
    date_file = now.strftime("%Y%m%d")

    # 显示当前使用的HTTP库
    if HAS_CURL_CFFI:
        print("[INFO] HTTP库: curl_cffi (模拟浏览器TLS指纹)")
    elif HAS_REQUESTS:
        print("[INFO] HTTP库: requests (标准库)")

    print(f"[INFO] 开始获取科技板块数据 - {date_str}")

    # 1. 获取概念板块 (fs=m:90+t:3)
    print("[INFO] 正在获取概念板块...")
    concept_boards = fetch_board_list("m:90+t:3", max_pages=10)
    print(f"[INFO] 获取到 {len(concept_boards)} 个概念板块")

    # 2. 获取行业板块 (fs=m:90+t:2)
    print("[INFO] 正在获取行业板块...")
    industry_boards = fetch_board_list("m:90+t:2", max_pages=3)
    print(f"[INFO] 获取到 {len(industry_boards)} 个行业板块")

    # 3. 合并并筛选科技相关板块
    all_boards = concept_boards + industry_boards
    tech_boards = filter_tech_boards(all_boards)
    print(f"[INFO] 匹配到 {len(tech_boards)} 个科技相关板块")

    if not tech_boards:
        print("[ERROR] 未获取到任何科技板块数据，可能API不可用")
        sys.exit(1)

    # 4. 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 5. 控制台输出
    console_output = format_console(tech_boards, date_str)
    print(console_output)

    # 6. 保存JSON数据
    json_file = os.path.join(OUTPUT_DIR, f"tech_board_{date_file}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({
            "date": date_str,
            "api_source": "东方财富 push2.eastmoney.com",
            "api_url": API_URL,
            "concept_board_count": len(concept_boards),
            "industry_board_count": len(industry_boards),
            "tech_board_count": len(tech_boards),
            "boards": tech_boards,
        }, f, ensure_ascii=False, indent=2)
    print(f"[INFO] JSON数据已保存: {json_file}")

    # 7. 保存HTML报告
    html_file = os.path.join(OUTPUT_DIR, f"tech_board_{date_file}.html")
    html_content = format_html(tech_boards, date_str)
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[INFO] HTML报告已保存: {html_file}")

    # 8. 保存控制台文本
    txt_file = os.path.join(OUTPUT_DIR, f"tech_board_{date_file}.txt")
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(console_output)
    print(f"[INFO] 文本报告已保存: {txt_file}")

    return tech_boards


if __name__ == "__main__":
    main()
