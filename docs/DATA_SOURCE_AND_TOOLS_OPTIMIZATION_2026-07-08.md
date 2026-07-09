# ALSA 数据源与 Tools 治理优化方案

> 日期: 2026-07-08
> 范围: 数据源统一管理、稳定性、分市场能力、Tools 层一致治理
> 目标: 在不打断现有功能的前提下，建立统一控制面、提升跨市场稳定性、形成可量化SLA

## 实施状态 (2026-07-08 当日)

- 已完成: P0-1 HK 路由优先序修正
- 已完成: P0-2 Router/API 元数据透传 (quote/history)
- 已完成: P0-3 Node 侧市场维 SLA 聚合 + 健康接口聚合 Python 状态
- 已完成: P1-1 缓存分层精细化 (quote 市场TTL / history interval TTL / financial TTL)
- 已完成: P1-2 全量能力 (tools 输出统一注入 market_context)
- 已完成: P1-3 关键能力 (Incident Console 市场过滤与市场展示)
- 已完成: P2-1 核心能力 (Provider 策略中心 + 热加载)
- 已完成: P2-2 核心能力 (质量评分 + 阈值自动降级)

---

## 1. 执行摘要

当前系统已经具备较强的数据能力，但属于"分层统一"而非"单控制面统一"：

- Python 侧以 DataRouter 作为数据聚合与回退核心。
- Node 侧以 DataSourceMonitor 进行网关健康治理。
- Tools 侧有独立注册和开关体系，但缺少与数据路由相同口径的市场级SLA观测。

结论:

1. 可用性整体良好，但存在尾延迟和个别标的脆弱点。
2. A 股链路明显更强，HK/US 仍有治理优化空间。
3. 需要优先做"统一可观测 + HK路由修正 + 工具层SLA对齐"三件事。

---

## 2. 现状与问题定位

## 2.1 当前优势

- 数据统一入口已存在:
  - python_service/app/services/data_providers/router.py
  - python_service/app/services/data_providers/base.py
- 已有并发回退、缓存、超时、熔断机制:
  - python_service/app/services/data_providers/router.py
  - python_service/app/services/market_data_service.py
- THS 能力覆盖到更细粒度市场和数据类型:
  - python_service/app/api/ths.py
  - python_service/app/services/data_providers/ths_provider.py
- Tools 已有注册中心和热更新开关:
  - python_service/app/services/tools/registry.py
  - python_service/app/services/tools_config.py

## 2.2 关键问题

1. 控制面分裂
- Node 健康监控与 Python Router 指标分离，缺少统一 SLA 面板。
- 相关文件:
  - server/dataSourceHealth.ts
  - server.ts

2. HK 路由优先级潜在不合理
- HK 分支当前 provider 顺序包含 A 股优先 provider，可能引入市场不匹配尝试成本。
- 相关文件:
  - python_service/app/services/data_providers/router.py

3. 尾延迟较高
- 网关报价请求有明显长尾，影响高频/盘中体验。
- 相关日志:
  - logs/api.log
  - logs/py_api.log

4. Tools 与 Router 缺少统一市场上下文
- Tools 可以分市场调用，但没有统一的 market_detected/provider_used/fallback_depth 指标链路。
- 相关文件:
  - python_service/app/services/expert_tools.py
  - python_service/app/services/tools/ths_tools.py
  - python_service/app/services/token_guard.py

---

## 3. 优先级与实施路线

## 3.1 P0 (本周必须落地)

### P0-1 修正 HK 路由优先序

目标:
- 降低 HK 请求在错误 provider 上的尝试成本，缩短平均响应时间和失败恢复时间。

建议改造:
- 在 DataRouter 的 HK 分支中，将 HK 专用/通用全球源放前，A 股专用源后置或移除。
- 为不同市场定义独立 provider profile，避免跨市场误尝试。

代码范围:
- python_service/app/services/data_providers/router.py
- python_service/app/services/data_providers/yfinance_provider.py
- python_service/app/services/data_providers/a_stock_direct.py

验收指标:
- HK 报价请求失败率下降 >= 30%
- HK 报价 p95 降低 >= 20%
- All providers failed 在 HK 样本中显著下降

---

### P0-2 建立统一响应元数据 (Router + API)

目标:
- 让每一条报价/历史/财务结果可追踪"来自哪里、经历几级回退、是否命中缓存"。

建议改造:
- 在 Router 输出附加:
  - market_detected
  - provider_used
  - fallback_depth
  - latency_ms
  - cache_hit
- 在 market API 透传元数据到响应。

代码范围:
- python_service/app/services/data_providers/router.py
- python_service/app/services/market_data_service.py
- python_service/app/api/market.py

验收指标:
- 95% 以上响应包含完整 metadata
- 线上排障时可在单次请求内定位 provider 决策路径

---

### P0-3 市场级 SLA 看板最小闭环

目标:
- 同一面板看到 A/HK/US 在 quote/history/financial 维度的成功率和延迟分位数。

建议改造:
- Node DataSourceMonitor 增加市场和数据类型标签维度。
- Python Router 上报统一指标到同一聚合层。
- 增加 /api/health/data-sources 扩展字段，包含按市场聚合统计。

代码范围:
- server/dataSourceHealth.ts
- server.ts
- python_service/app/services/data_providers/router.py

验收指标:
- 可输出 market x data_type x provider 的 success_rate, p50, p95, p99
- 故障出现 5 分钟内可定位是"市场问题"还是"provider问题"

---

## 3.2 P1 (2-4周)

### P1-1 历史数据与报价缓存策略分层

目标:
- 让实时链路更快、历史链路更稳，避免缓存策略互相干扰。

建议改造:
- quote: 保持短 TTL，但增加市场差异化 TTL
- history: 按 interval 分层缓存 (1m/5m/day)
- financial: 增加刷新窗口与主动预热

代码范围:
- python_service/app/services/data_providers/router.py
- python_service/app/services/market_data_service.py

验收指标:
- quote p95 再降 15%
- history 缓存命中率 >= 70%

---

### P1-2 Tools 市场上下文统一注入

目标:
- Tools 与 Router 使用同一套市场判定和观测口径，减少跨工具口径不一致。

建议改造:
- expert_tools 在执行前统一解析 market_context:
  - symbol
  - market_detected
  - preferred_provider_profile
- ths_tools / financial_data / news_search 统一记录 tool_market_tag。

代码范围:
- python_service/app/services/expert_tools.py
- python_service/app/services/tools/ths_tools.py
- python_service/app/services/tools/search.py

验收指标:
- 工具调用日志中 market 标签覆盖率 >= 95%
- 跨市场分析任务中，工具调用错误率下降 >= 20%

---

### P1-3 Incident Console 增加市场维诊断能力

目标:
- 运维人员按 market 快速定位故障聚类。

建议改造:
- 在管理台增加 market 过滤和分组。
- 增加 provider_used/fallback_depth 显示列。

代码范围:
- src/components/admin/IncidentConsole.tsx
- python_service/app/api/admin.py

验收指标:
- 可在 2 次点击内完成"市场 -> provider"故障定位

---

## 3.3 P2 (4-8周)

### P2-1 建立市场能力矩阵与路由策略中心

目标:
- 把"哪个市场能用哪些 provider、哪些数据类型"从代码硬编码迁移到策略配置。

建议改造:
- 新增 provider_capability_matrix 配置文件。
- Router 读取配置动态路由。
- 支持灰度启用/禁用 provider。

代码范围:
- python_service/app/services/data_providers/router.py
- python_service/app/services/tools_config.yaml (可扩展)
- 新增配置文件: python_service/app/services/data_providers/provider_policies.yaml

验收指标:
- 新 provider 接入代码改动减少 >= 40%
- 灰度开关可在不重启情况下生效

---

### P2-2 数据质量评分与自动降级

目标:
- 当数据完整性/新鲜度下降时自动切换次优路径，避免把问题数据直接给上游。

建议改造:
- 为 quote/history/financial 定义 quality_score。
- 在 Router 决策加入质量阈值。
- 对低质量结果打标并触发告警。

代码范围:
- python_service/app/services/data_providers/base.py
- python_service/app/services/data_providers/router.py
- server/dataSourceHealth.ts

验收指标:
- 低质量数据误用率下降 >= 50%

---

## 4. 技术设计建议 (面向当前代码库)

## 4.1 统一事件模型 (建议)

建议新增统一事件结构，用于 Router、API、Tools、Admin：

- request_id
- symbol
- market_detected
- data_type (quote/history/financial/news/tool)
- provider_used
- fallback_depth
- cache_hit
- latency_ms
- quality_score
- error_code
- timestamp

建议落点:
- Python: 在 data_router 与 expert_tools 执行器打点
- Node: 在 dataSourceHealth 收敛展示

---

## 4.2 优先保留的现有设计

以下设计应保留并增强，不建议推倒重来:

1. DataRouter 并发竞速 + 优先级回退
2. Router 的 Redis + DB 双缓存思路
3. Tools 热更新开关机制
4. TokenGuard 的输出预算控制

---

## 5. 里程碑计划

## Week 1

1. P0-1 HK 路由修正
2. P0-2 Router 元数据透传
3. 指标埋点联调

交付:
- 可发布的路由修复版本
- 初版 market SLA JSON 接口

## Week 2

1. P0-3 SLA 看板接入
2. P1-3 Incident Console 市场诊断字段上线
3. 回归测试和压测

交付:
- 运维可用的市场级诊断能力
- 变更后性能对比报告

## Week 3-4

1. P1 系列完成 (缓存分层 + tools 市场上下文)
2. 输出稳定性周报模板

交付:
- Tools 与数据链路统一观测口径
- 跨市场稳定性提升报告

---

## 6. 验收清单

上线前必须满足:

1. market API 响应可追踪 provider/fallback/cache
2. HK/US/A 在 24h 内都有可观测样本
3. "All providers failed" 有错误码和市场标签
4. Incident Console 能按 market 过滤
5. Tools 调用日志包含 market 标签
6. p95 延迟与失败率有前后对比数据

---

## 7. 风险与回滚

主要风险:

1. 路由优先级调整导致局部市场回归
2. 元数据扩展影响旧前端字段解析
3. 指标打点增加少量开销

回滚策略:

1. provider profile 支持 env 开关回退
2. metadata 字段采用向后兼容追加，不替换旧字段
3. 监控异常时可快速切回旧路由顺序

---

## 8. 建议下一步

按当前代码状态，建议立即执行:

1. 先做 P0-1 与 P0-2，投入小、收益快。
2. 并行准备 P0-3 的统一指标模型，避免后续重复埋点。
3. 在当前管理台基础上追加 market 与 provider 诊断字段，形成排障闭环。
