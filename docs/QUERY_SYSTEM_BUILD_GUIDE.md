# 查询系统从 0→1 搭建参考指南

> 目标：搭建一套"类似"的金融数据查询系统（多市场 × 多维度，统一口径，CLI/API/AI-Agent 多形态消费）。
> 借鉴来源：本仓库 ALSA 数据层（`python_service/app/services/data_providers/`、`app/lake/`）+ westock-data skill（分发形态与治理文档）+ 业内开源项目。

---

## 一、现有系统里最值得抄的 4 个设计（直接复用）

### 1. Provider 抽象 + 路由降级（ALSA `data_providers/`）

这是整套系统里最有价值的架构模式，5 个文件配合：

| 文件 | 职责 | 要点 |
|------|------|------|
| `base.py` | Provider 抽象基类 + 统一 schema | `DataProvider` ABC；`QuoteData` dataclass；`normalize_ohlcv()` 把各源列名归一为标准 OHLCV |
| `router.py` | 策略模式路由器 | 按 ticker 检测市场 → 选主源 → 失败按序降级；`contextvars` 传播路由元数据；`runtime_stats` 统计成功率 |
| `provider_policies.yaml` | 配置化策略（支持热更新） | 每市场的主备顺序、质量阈值（quote 0.6 / financial 0.35 等）、按数据类型的 TTL（quote 3s / 1d K线 900s） |
| 质量评分函数 | `score_quote_quality` 等 | 字段覆盖率评分 → 低于阈值自动降级到备用源 |
| 缓存 | 内存 TTL + Redis | 按 market+data_type 分档 TTL，避免高频打源 |

**新系统照抄的关键点**：统一 schema 先行、路由顺序与阈值全部外置到 YAML（换源/调参不改代码）、每个 provider 无状态可懒加载。

### 2. 能力矩阵 + 三层路由文档（westock-data skill）

westock-data 最值得抄的不是代码而是**文档治理体系**：

- **三层文档分工**：`commands.md`（命令语法/参数）→ `routing-guide.md`（用户意图 → 精确命令映射表）→ `scenarios-guide.md`（分析场景模板）
- **能力矩阵**（routing-guide §六）：标的（A股/港股/美股/ETF/指数/板块/期货/外汇/可转债）× 维度（K线/财务/研报/资金流/宏观…）的差异速查表——**不同标的不支持的维度必须显式列出**（如"美股无资金流向"）
- **批量优先 API 设计**：多标的用逗号拼在一次调用（`kline sh600519,sz000651`），例外清单明确列出（`search` 不支持批量）
- **AI 消费治理铁律**：单一权威入口、禁止 HTTP 直连/web_search 替代、失败如实转述禁止编造、search 默认只搜股票必须显式 `--type` 防 fan-out 浪费

### 3. 数据湖（ALSA `lake/`）

- DuckDB in-memory 实例 + Hive 分区 Parquet：`ohlc/market={market}/year={year}/symbol={symbol}/`
- 查询级 TTL 缓存（30s）+ glob 路径白名单校验（防注入）
- 结论：**新系统第一版不需要湖**，内存缓存 + 按需拉取即可；湖是二期做"历史数据沉淀 + 复权计算"时再加

### 4. 分发形态（westock-data 的 npx 模型）

- npm 发布 + `npx -y <pkg>@<钉死版本>` 零安装执行 → AI Agent 环境里分发成本最低
- `help` 子命令实时输出命令清单（避免文档漂移）
- Node ≥ 18 即可跑，无额外依赖

---

## 二、框架选型清单（按层）

### 语言分工（参考 ALSA 混合架构）

- **数据采集/计算层：Python 3.11+** — 金融开源库生态全在 Python（AkShare 等接口逆向参考）
- **CLI 壳/分发层：Node 或 Python 二选一** — 若走 npx 分发用 Node；若走 `uv tool`/`pipx` 用 Python（uv 现在分发体验已接近 npx）

### CLI 层

| 框架 | 选择理由 |
|------|----------|
| **Click 8.x / Typer**（Python） | Typer = FastAPI 同作者，类型注解即 CLI，自动生成 help；子命令结构天然匹配"查询系统"的多命令形态 |
| **commander / oclif**（Node） | oclif 适合插件化多命令；westock-data 这类简单 CLI 用 commander 就够 |
| **rich / Ink** | 表格、颜色输出；要做交互式 TUI 用 Ink |

### API 层

- **FastAPI + Pydantic v2**：自动 OpenAPI、类型校验、async 原生——数据查询 API 首选
- **GraphQL（Strawberry）**：仅当"维度 × 标的"组合爆炸、客户端要按需取字段时才值得；否则 REST 够用
- **MCP server（modelcontextprotocol python-sdk）**：**新系统必做项**——把查询能力同时暴露成 MCP 工具，AI Agent 就能直接消费，这是当前分发最高效的形态（本仓库 `config/mcporter.json` 已在用 MCP）

### 数据接入层

| 组件 | 用途 |
|------|------|
| `httpx`（async） | 并发打多源接口 |
| `tenacity` | 重试 + 指数退避（金融接口限流严重） |
| `curl_cffi` | TLS 指纹伪装，绕过部分站点防护 |
| 自实现令牌桶 | 每源每 QPS 限流（EastMoney 等限流极狠） |
| `hashlib/hmac` | EastMoney 等接口的签名参数构造 |

### 处理/存储/缓存

- **Polars**（计算）或 pandas（兼容）——ALSA 两者都在用
- **Redis**（TTL 热缓存，按 market×data_type 分档）+ 内存进程级缓存（quote 秒级数据）
- **DuckDB**（二期数据湖查询）/ SQLite（元数据、code→name 映射表）
- **Parquet**（历史数据沉淀，Hive 分区）

### 调度/可观测

- Celery + Redis（Python）或 BullMQ（Node）——只有"定时拉全市场数据"才需要
- `structlog`（Python）/ `pino`（Node）+ prometheus-client + Grafana
- **必做**：每个 provider 的 success/failure/latency 计数（照抄 ALSA `runtime_stats`）

---

## 三、开源系统借鉴清单

### A. 数据源聚合类（架构最值得抄）

| 项目 | 借鉴点 |
|------|--------|
| **OpenBB Platform** | **多源统一抽象的最佳范本**：Provider 注册 + Router + Standard Models（Obbject）三层设计，直接对标本文档第一节的设计 |
| **AkShare** | A股/宏观/期货数据最全的开源库；其 eastmoney/sina/ths 模块是**接口逆向的源码级教材**（URL、参数构造、字段解析） |
| **vnpy** | 行情网关抽象：`BaseGateway` 接口 + 多源适配器，长期维护的多源接驳范式 |
| **qlib**（微软） | 数据层 bin 格式 + 表达式引擎，适合二期做"存储优化"参考 |
| **yfinance** | 港美股数据源 |
| **efinance / a-stock-data**（simonlin1212） | 轻量 A 股接口逆向参考（ALSA 的 a_stock_direct.py 即源自后者） |

### B. 接口逆向的直接数据源（新系统首要选择）

- 腾讯行情 `qt.gtimg.cn`（免费、无鉴权、覆盖 A/HK/US、批量）—— westock-data 的数据底座
- EastMoney `datacenter-web.eastmoney.com/api/data/v1/get`（财务/分红/股东）+ `push2`（K线）
- 新浪财经（三大报表）、同花顺 `basic.10jqka.com.cn`（财务摘要）
- 注意：这些接口**无 SLA、随时可能改**——所以必须有主备降级链（第一节点）

### C. Agent 分发生态

- **MCP 官方 SDK + 现有金融 MCP server**（搜 GitHub "mcp finance"）——查询系统暴露给 AI 的标准方式
- **SkillHub / Claude Code skills 格式**——westock-data 的"SKILL.md + references 三层文档 + npx 调用"就是一种成熟模板
- **SkillHub 平台的 skill 打包规范**（`npx -y <pkg>@<version>` 分发）

### D. 基础设施（按需选）

| 需求 | 选择 |
|------|------|
| API 网关（多服务聚合/限流/熔断） | APISIX 或 Kong；单服务则不需要 |
| 全文搜索（代码/名称模糊搜索） | Meilisearch（轻量）或 Elasticsearch |
| 大规模数据湖 | DuckDB + delta-rs；再大规模才上 Iceberg/Trino |

---

## 四、从 0 → 1 路线图（7 个阶段，每阶段有验收标准）

### Phase 0 — 定范围（0.5 天）
**产出：能力矩阵草稿 + 路由文档草稿**
- 表格：标的（A股/港股/美股/ETF/指数/板块…）× 维度（行情/财务/K线/研报/公告/资金流/宏观…），标注"支持/不支持/延迟"
- 从 westock-data 的 routing-guide §六 抄结构，从自己能力范围砍维度
- **铁律：能力矩阵先行于代码**——它决定 API 形状

### Phase 1 — 单源打通（2-3 天）
**产出：1 个 provider + 统一 schema + 单元测试**
- 照抄 ALSA `base.py`：`DataProvider` ABC、`QuoteData` dataclass、`normalize_ohlcv()`
- 先接腾讯行情（免费无鉴权），跑通 quote + kline 两个命令
- 验收：`get_quote("sh600519")` 返回标准 schema，mock 测试覆盖解析逻辑

### Phase 2 — 多源路由 + 降级（3-5 天）
**产出：Router + policy YAML + 质量评分**
- 照抄 ALSA `router.py` + `provider_policies.yaml`（主备顺序/质量阈值/TTL 全部外置）
- 接第二源（EastMoney 或新浪），实现"主源超时 → 备源补上 → 质量评分低于阈值 → 再降级"
- 验收：杀掉主源（mock 异常），查询仍能返回且带 route_meta 说明走了哪个源

### Phase 3 — 缓存 + 限流（2-3 天）
- 内存 TTL 缓存（quote 3-5s）+ Redis 可选；每源令牌桶限流 + tenacity 重试
- 验收：同一查询连续 10 次，实际打源 ≤ 1 次

### Phase 4 — 暴露层：CLI + API + MCP（3-5 天）
- CLI（Typer/commander）：命令名 = 数据维度，批量用逗号分隔
- HTTP API（FastAPI）：同一套 service 逻辑，`{success, data, error}` 响应形状（本仓库约定）
- MCP server：把核心命令暴露为 MCP tools（AI Agent 消费入口）
- 验收：三端调用同一底层 service，无重复逻辑

### Phase 5 — 治理文档（2 天）
- `commands.md`（语法）+ `routing-guide.md`（意图→命令表）+ 能力矩阵 + AI 铁律（禁止绕过/如实转述）
- `help` 子命令从代码实时生成命令清单
- 验收：一个新手 Agent 只读文档 + help 就能正确完成 90% 查询

### Phase 6 — 分发（1-2 天）
- npx（npm 包钉版本）或 `uv tool` 发布；MCP server 配置文档
- 验收：干净环境一条命令安装并完成首次查询

### Phase 7 — 可观测 + 审计（2-3 天，持续）
- provider 维度 success/failure/latency 计数、降级事件日志、用量审计
- 验收：任何源故障 30 秒内可见

**总计：约 3-4 周到可用版本。**

---

## 五、避坑清单（来自本仓库 ALSA 的实战教训）

1. **模块 >250 LOC 必须拆分**——数据接入最容易被塞成巨型文件（本仓库 `stockRoutes.ts` 1261 行、`llm_gateway.py` 658 行的教训）
2. **禁止裸 `except:` 和 `print()`**——接口异常必须带上下文日志，否则线上数据源静默失败无法排查
3. **单一类型系统**——schema 定义只放一处（ALSA 的 `src/types.ts` vs `src/types/` 双轨是反面教材）
4. **路由所有权唯一**——同一查询不要被两层网关重复处理（ALSA 的 Express+FastAPI 重叠问题）
5. **接口无 SLA 是常态**——把"某源改版/挂掉"当成日常事件设计（降级链、审计、监控从 Day 1 就有）
6. **单测覆盖解析逻辑**——接口返回字段格式变化是最常见故障，每个 provider 的解析函数必须有用例（ALSA 62 个 pytest 文件是标准）
7. **时间戳/时区/货币单位**三件事从 schema 层定死（CST、港元/美元标注），否则 Agent 展示必然出错

---

## 六、一句话总结

> 架构抄 **OpenBB + ALSA data_providers**（Provider 抽象 + YAML 驱动降级），
> 数据源抄 **腾讯/EastMoney 逆向 + AkShare 源码**，
> 文档治理抄 **westock-data 三层路由文档 + 能力矩阵**，
> 分发抄 **npx skill + MCP server** 双通道，
> 从能力矩阵开始，从单源+统一 schema 起步，3-4 周可用。
