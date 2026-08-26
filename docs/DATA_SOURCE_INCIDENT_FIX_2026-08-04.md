# 数据源故障根因分析与修复记录 (2026-08-04)

> 背景: 前台任务中出现 `financial_data / deep_scrape / ths_quote` 接口故障与
> `web_search` 返回无关结果; 报告仅能引用可追溯数据源, 2025 年报财务数值与
> 铜价最新报价均无法获取。
> 本文档记录根因定位过程与修复内容, 与 2026-07-08 的优化方案文档配套。

## 1. 根因定位 (诊断脚本: `python_service/scratch/diag_data_sources.py`)

| 故障 | 根因 | 证据 |
|------|------|------|
| `ths_quote` (HK/US) | thsdk 游客账户 (`thsguest_*`) 仅支持 A 股行情, HK/US 查询返回 `QueryData错误:not data`; A 股正常 | thsdk 连接成功但 `UHKG01888`/`UNQNAAPL` 均 0 行 |
| `financial_data` (HK/US) | yfinance 被 Yahoo 全局限流: `YFRateLimitError: Too Many Requests` (600519.SS 与 AAPL 均触发); HK/US 的 provider 链只有 yfinance → 全部失败 | 诊断实测 AAPL/1888.HK 均 YFRateLimitError |
| `deep_scrape` | `crawl4ai` 未安装 (venv 无 pip 模块, site-packages 亦无 crawl4ai) | `ModuleNotFoundError: No module named 'crawl4ai'` |
| `web_search` 无关结果 | ① `IWENCAI_API_KEY` 仅存在于 shell 会话环境变量, 未持久化到任何 `.env.runtime` → 会话外 Iwencai 失效, 中文查询掉到 SearXNG(bing) 返回教育考试院等无关结果; ② 英文/商品查询 (铜价) 无可靠来源: FAOS (Tavily/Serper/Jina) 默认 disabled 且其硬编码 key 已全部失效 (HTTP 432/400/超时); SearXNG bing 对英文金融查询 0 结果 | 诊断 [5][6][7] |
| OpenBB enrichment | `run_in_executor` worker 线程中 OpenBB 首次 build 调用 `signal.signal(SIGTERM)` → `ValueError: signal only works in main thread` | 每次调用打印 `⚠ Income statement failed: signal only works...` |

补充事实 (修复可行性验证):
- 东方财富 datacenter `RPT_HKF10_FN_MAININDICATOR` 直接可用, 返回建滔积层板
  2025 年报: 营收 184.26 亿 (+10.03%), 归母净利 22.06 亿 (+84.16%), EPS 0.7063,
  ROE 15.42% — 正是前台任务缺失的数据。
- 腾讯行情 `qt.gtimg.cn` 支持 A/港/美 (`sh600519`/`hk01888`/`usNVDA`, 美股**不带**
  `.OQ/.N` 后缀)。
- 新浪期货 `hq.sinajs.cn` (`nf_CU0` 沪铜主力 / `hf_CAD` 伦铜) keyless 可用。
- Iwencai OpenAPI key 在会话环境变量中有效 (status=0, 30 条/查询)。

## 2. 修复内容

| 文件 | 修复 |
|------|------|
| `data_providers/a_stock_direct.py` | 新增 `fetch_hk_financials()` (东财 HK F10 主要指标) 与 `fetch_tencent_quote()` (A/港/美行情); `get_financial_summary()` 增加 HK/US 快速路径 (腾讯行情 + 东财港股财报, 不依赖 yfinance) |
| `data_providers/provider_policies.yaml` | US-Share 增加 `a-stock-direct` 兜底; US-Share financial 质量阈值 0.35→0.2 (腾讯行情仅 PE/市值, 2/8=0.25 分, 允许降级数据通过) |
| `tools/ths_tools.py` | `ths_quote` HK/US 空结果时自动 fallback 腾讯行情, 返回标注 `(腾讯行情 fallback — thsdk 无此市场数据)` |
| `services/expert_tools.py` | `financial_data` HK/US 分支预取东财港股财报 + 腾讯行情, 各数据段 (valuation/financials/balance/cashflow/income) yfinance 失败时逐段降级 |
| `services/search_service.py` | ① 新增 `_futures_search()` 新浪期货 fallback (铜/金/银/铝/锌/镍/原油/螺纹钢/铁矿/大豆, 中英文关键词), 插入 FAOS 之后 SearXNG 之前; ② 移除已失效的 FAOS 硬编码 key (留 env 覆盖位) |
| `services/openbb_service.py` | 新增 `_run_obb_thread()`: worker 线程内临时中和 `signal.signal`, 修复 OpenBB build 的 signal 异常 |
| `.env.runtime` (根) | 持久化 `IWENCAI_API_KEY` / `IWENCAI_BASE_URL` (生产启动脚本 source 此文件) |
| 环境 | venv 补装 pip (ensurepip) + `crawl4ai 0.9.2` + playwright chromium/headless-shell (经 npmmirror 镜像手动安装, 直连 CDN 仅 ~500B/s) |

## 3. 修复后验证

```
[1] financial_data 1888.HK → ## Financials (EastMoney HK) 2025-12-31 2025年年报:
    营收:18.43B | 营收同比:10.03% | 归母净利:2.21B | 净利同比:84.16% | 毛利率:19.56%
[2] ths_quote UHKG01888 → 腾讯行情 fallback: 建滔积层板 31.18 +3.93% PE 40.24
[3] web_search "LME copper price" → Iwencai: LME三个月期铜 13870 美元/吨 (+79)
[4] web_search "铜价 最新报价" → Iwencai: 1#铜 106230 元/吨 (+80)
[5] data_router financial_summary: 00700/01888.HK/NVDA/AAPL/MSFT/600519 全部可用
    (US 经腾讯行情, HK 经东财财报, A 股原有链路不变)
[6] deep_scrape (crawl4ai) → 格隆汇新闻页 13K 字符 markdown 抓取成功
[7] OpenBB → 不再报 signal 错误 (yfinance 限流时返回正常失败信息)
```

测试: `test_serenity_data_fix.py` (7 passed, 含此前失败的
`test_fetch_sector_stocks_hk_and_us`), `test_tool_calls.py` +
`test_phase1_tool_governance.py` + `test_audit_phase1_fixes.py` (68 passed),
`test_tool_registry.py` + `test_data_quality_pipeline.py` (22 passed)。

## 4. 遗留与注意事项

1. **yfinance 限流未解除** — 这是 Yahoo 对数据中心 IP 的反爬策略, 代码侧无法
   根治; 已通过东财/腾讯/新浪 keyless fallback 绕过。若后续拿到可用的
   Tavily/Serper/Jina key, 可恢复 FAOS 英文搜索通道 (`TAVILY_ENABLED=true` +
   `TAVILY_API_KEY=...` 写入 `.env.runtime`)。
2. **thsdk 游客账户** — 仅 A 股可用且"随时可能失效", 正式账户凭据到位前
   HK/US 行情依赖腾讯 fallback。
3. **美股财务数据** — 腾讯行情仅提供 PE/市值/换手率, 无财务报表; 美股财务
   仍需 yfinance (限流时降级为仅估值数据)。
4. **crawl4ai 浏览器** — 手动安装于 `~/.cache/ms-playwright/`, 新机器部署时
   需执行 `python -m playwright install chromium` (直连 CDN 慢, 建议
   `PLAYWRIGHT_DOWNLOAD_HOST` 指向 npmmirror)。
5. **httpx 升级** — crawl4ai 安装将 httpx 升至 0.28.1, mootdx (未使用) 声明
   兼容 <0.26; 若后续启用 mootdx 需评估。
