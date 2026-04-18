export const TEMPORAL_ALIGNMENT_EN = `
**TEMPORAL ALIGNMENT PROTOCOL (MANDATORY)**:
1. **Strict Timeliness**: All core variables you retrieve must be aligned to the **current date** provided dynamically below or the latest closing price within the last 3 trading days.
2. **Reject Stale Memory**: Using historical training data values is strictly prohibited. Use search to find today's data.
3. **Evidence Adoption**: Data more than 15 days old is considered "expired" for high-beta variables.
`;

export const TEMPORAL_ALIGNMENT_ZH = `
**时间戳强制对齐协议 (TEMPORAL ALIGNMENT PROTOCOL)**:
1. **严格实时性**: 你获取的所有核心变量必须对齐至**当前日期**（参见下方）或其前 3 个交易日内的最新成交价。
2. **拒绝陈旧记忆**: 严禁使用模型历史训练数据中的数值。必须使用搜索获取当下的数据。
3. **搜证时效**: 对于高频变量，发布日期早于当前 15 天的数据被视为失效。
`;
