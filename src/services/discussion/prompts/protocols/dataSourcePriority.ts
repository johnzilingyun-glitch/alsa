export const DATA_PRIORITY_EN = `
**DATA SOURCE PRIORITY PROTOCOL (CRITICAL)**:
1. **Hierarchy**: Authoritative Financial API > Google Search authoritative sources > Other sources.
2. **Conflict Resolution**: If API and search data conflict (>1%), default to API, use search results to explain the difference.
3. **Multi-Source**: Must compare data from at least two different sources. If deviation >1%, perform deep logic tracing.
`;

export const DATA_PRIORITY_ZH = `
**数据源优先级协议 (DATA SOURCE PRIORITY PROTOCOL)**:
1. **层级**: 权威金融 API > Google Search 权威来源 > 其他来源。
2. **冲突处理**: 若 API 与搜索数据冲突（>1%），默认以 API 为准，搜索结果用于解释差异。
3. **多源核验**: 必须对比至少两个不同来源的数据。若偏差 >1%，必须进行深度逻辑溯源。
`;
