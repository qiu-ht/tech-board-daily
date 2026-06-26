# 科技板块涨跌日报

每天自动查询 A 股科技相关板块（CPO、半导体、AI、算力等）的涨跌情况，生成控制台报告 + HTML可视化报告 + JSON数据文件。

## 数据源

使用 **东方财富网公开 API**（完全免费，无需注册）：

```
https://push2.eastmoney.com/api/qt/clist/get
```

### 为什么偶尔 502？

`push2` 是东方财富的**高频行情推送节点**，非交易时段（夜间/周末/午休）服务器降级维护时会偶发 502。脚本已内置多重保障：

| 策略 | 说明 |
|------|------|
| Session 连接池 | 复用 TCP 连接，减少握手失败 |
| 指数退避重试 | 502 后 2→4→8→16 秒递增等待，最多重试 4 次 |
| Header 轮换 | 每次请求随机换 User-Agent 和 Referer |
| 3 轮整体重试 | 一次运行最多 3 轮整体重试，轮间等 10→20→30 秒 |
| 缓存兜底 | API 全挂时自动加载上次成功数据，标注「缓存」 |
| 交易时段识别 | 自动判断当前是否交易时段，给出友好提示 |

## 本地运行

**方式一：联网安装**
```bash
pip install -r requirements.txt
python tech_board_daily.py
```

**方式二：离线安装**

`vendor/` 目录已包含所有依赖的 wheel 包（Windows x64 + Python 3.14）：
```bash
pip install --no-index --find-links=vendor -r requirements.txt
python tech_board_daily.py
```

输出文件保存在脚本所在目录的 `output/` 子目录下：
- `tech_board_YYYYMMDD.html` — 可视化报告（深色主题）
- `tech_board_YYYYMMDD.json` — JSON原始数据
- `tech_board_YYYYMMDD.txt`  — 控制台文本报告

## Windows 定时运行

用任务计划程序，A 股收盘后运行（15:05）数据最准：

```powershell
schtasks /create /tn "TechBoardDaily" /tr "python C:\path\to\tech_board_daily.py" /sc daily /st 15:05
```

## 依赖

- `requests` — 标准HTTP库，Windows/Linux通用
- `curl_cffi` — 可选，Linux下模拟浏览器TLS指纹

## 自定义监控板块

编辑脚本中的 `TECH_KEYWORDS` 列表即可增减关键词，脚本会从东方财富全部板块中自动匹配。
