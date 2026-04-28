# WebSocket 迁移设计规范 (2026-04-28)

## 架构
- 将 `/analysis/jobs/:analysisId/:jobId` 的 HTTP 轮询替换为 `socket.io` 推送。
- Node.js 作为 WebSocket 服务端，FastAPI 保持现有状态更新逻辑，Node 服务端接收 FastAPI 变更后推送。

## 实现细节
1. **服务端**：集成 `socket.io` 到 Express 服务。
2. **客户端**：新增 `useAnalysisStatus` hook，替代现有的 polling 实现。

## 测试
- 验证服务器端 socket emit 行为。
- 验证客户端 hook 在接收到状态变更时能否触发 UI 重渲染。
