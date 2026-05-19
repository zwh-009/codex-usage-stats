# Implementation Notes

## Scope

当前版本实现本地日志解析、统计、SQLite/CSV、本地 FastAPI、React Web UI，并通过 PySide6 WebEngine 嵌入本地工具窗口。不实现凭据读取、远程 usage 接口或实时代理捕获。

## Cost Calculation

当前花费是估算值。只有 `codex-davinci-002` 配置了方案示例价格，未知模型按 `$0` 处理，避免展示不可靠价格。

## Persistence

SQLite 写入使用 `INSERT OR IGNORE` 和唯一索引去重，不清空历史数据。CSV 导出由用户在 UI 中选择目标路径。
