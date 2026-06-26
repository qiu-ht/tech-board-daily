# 科技板块涨跌日报

每天自动查询 A 股科技相关板块（CPO、半导体、AI、算力等）的涨跌情况，生成控制台报告 + HTML可视化报告 + JSON数据文件。

## 数据源

使用 **东方财富网公开 API**：

```
https://push2.eastmoney.com/api/qt/clist/get
```

| 参数 | 说明 |
|------|------|
| `fs=m:90+t:3` | 概念板块列表 |
| `fs=m:90+t:2` | 行业板块列表 |
| `f3` | 涨跌幅(%) |
| `f2` | 板块指数点位 |
| `f62` | 主力净流入(万元) |

无需注册、无需 API Key，直接请求即可获取 JSON 数据。

## 本地运行

**方式一：联网安装（推荐）**
```bash
pip install -r requirements.txt
python tech_board_daily.py
```

**方式二：离线安装（无需联网）**

`vendor/` 目录已包含所有依赖的 wheel 包，直接离线安装：
```bash
pip install --no-index --find-links=vendor -r requirements.txt
python tech_board_daily.py
```

输出文件默认保存在脚本所在目录的 `output/` 子目录下：
- `tech_board_YYYYMMDD.json` — JSON原始数据
- `tech_board_YYYYMMDD.html` — HTML可视化报告（深色主题）
- `tech_board_YYYYMMDD.txt`  — 控制台文本报告

## 定时运行（crontab）

建议在 A 股收盘后运行（15:05），数据最准确：

```bash
crontab -e
# 添加：
5 15 * * 1-5  cd /path/to/tech_board_daily && python tech_board_daily.py
```

## 依赖说明

- `curl_cffi`：模拟浏览器 TLS 指纹，东方财富 API 对标准 requests 可能拒绝连接
- 如果不想安装 `curl_cffi`，脚本会自动回退到标准 `requests`，但成功率较低

## 自定义监控板块

编辑脚本中的 `TECH_KEYWORDS` 列表即可增减监控的科技板块关键词，脚本会从东方财富全部板块中自动匹配名称包含这些关键词的板块。
