# Codex Windows Usage Tool

本项目是一个本地 Windows 用量统计工具，用于自动读取 Codex 本地日志、计算 token 与估算花费、写入本地 SQLite，并通过 React Web UI 展示趋势、模型占比和请求明细。

## 普通用户下载

普通用户不要下载 GitHub 右上角 `Code -> Download ZIP` 的源码包。

请到 GitHub Releases 下载：

```text
直接解压本压缩包即可使用-无脑使用版.zip
```

使用方式：

```text
解压 zip -> 双击 CodexUsageTool.exe
```

源码包面向开发者，里面不会包含打包后的 exe。发布版 zip 作为 GitHub Release 附件提供，这样仓库不会被 200MB+ 的二进制文件拖慢，也不会触发 GitHub 单文件大小限制。

## 功能

- 自动读取：`%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl`
- 回退读取：`%USERPROFILE%\.codex\logs_2.sqlite` 和 `%USERPROFILE%\.codex\logs\*.jsonl`
- 支持手动更换 SQLite/JSONL 数据来源
- 统计总请求数、总 tokens、缓存 token 数、估算花费
- 统计缓存 token 数和缓存命中率
- 展示每日 token 趋势、模型占比、请求明细表
- React 前端支持时间筛选、模型筛选、搜索、动效统计卡片
- 启动后每 30 秒自动刷新
- 本地保存 SQLite：源码运行时为 `data/codex_usage.sqlite3`，打包版为 `%LOCALAPPDATA%\CodexUsageTool\codex_usage.sqlite3`
- 支持导出 XLSX

## 不做的事

- 不读取 `.codex\auth.json`
- 不上传日志或统计数据
- 不把本地 SQLite、CSV、原始日志提交进仓库

## 开源前检查

仓库已默认忽略本地数据、日志、数据库、虚拟环境、Node 依赖和发布包：

```text
data/
.venv/
node_modules/
frontend/node_modules/
frontend/dist/
release/
*.sqlite*
*.db
*.csv
*.xlsx
*.log
```

发布源码前建议再执行一次敏感信息扫描，确认没有个人路径、日志内容或密钥进入提交。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\open_source_check.ps1
```

## 许可证

本项目使用 MIT License，详见 `LICENSE`。

## 安装

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
```

## 运行

```powershell
python -m codex_usage_tool
```

Windows 文件管理器里可以直接双击，首次运行会自动创建本地 `.venv` 并安装依赖：

```text
run_app.bat
```

随后会打开一个本地工具窗口，React UI 会嵌在窗口内部显示，不会弹出外部浏览器。

如果不想每次进入项目文件夹，双击一次：

```text
install_desktop_shortcut.bat
```

它会在桌面创建 `Codex 用量统计` 快捷方式，快捷方式使用隐藏启动器启动，不会保留命令窗口。

主窗口最小化或关闭后会进入系统托盘；右键托盘图标可以打开主窗口、显示/隐藏组件或退出程序。

如果窗口没有打开，双击 `debug_app.bat` 查看错误输出。

## 下载版使用

发布包面向普通用户：

```text
下载 zip -> 解压 -> 双击 CodexUsageTool.exe
```

程序会读取当前 Windows 用户自己的 Codex 日志，不绑定固定用户名；本地缓存、价格配置、窗口设置和启动日志写入：

```text
%LOCALAPPDATA%\CodexUsageTool
```

## 构建 Windows 便携版

构建脚本会使用项目内 `.venv`，不会安装全局 Python 依赖：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

输出位置：

```text
release/CodexUsageTool_<时间戳>/
release/直接解压本压缩包即可使用-无脑使用版.zip
```

构建脚本会保留最近 2 个时间戳构建目录，并自动清理更早的旧构建目录；固定名称的“无脑使用版”zip 会覆盖为最新版。

发布 GitHub Release 时，上传固定名称的“无脑使用版”zip。更详细的发布步骤见 `docs/release_guide.md`。

## 验证

```powershell
python -m unittest discover -s tests
python -m compileall src tests
```

## 本地数据位置

日志读取路径使用当前系统用户目录，不绑定固定用户名：

```text
%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl
%USERPROFILE%\.codex\logs_2.sqlite
%USERPROFILE%\.codex\logs\*.jsonl
```

程序自身缓存、价格配置和窗口设置：

```text
源码运行：项目 data 目录
打包运行：%LOCALAPPDATA%\CodexUsageTool
```

## 日志字段兼容

解析器优先读取 Codex session rollout 里的 `token_count` 事件，并兼容 Codex Desktop SQLite 的 `response.completed` usage 事件和以下 JSONL 结构：

```json
{"timestamp":"2026-05-18T14:22:33","model":"codex-davinci-002","prompt_tokens":45,"completion_tokens":120,"cached":false}
```

```json
{"timestamp":"2026-05-18T14:22:33Z","model":"gpt-example","usage":{"input_tokens":45,"output_tokens":120,"input_tokens_details":{"cached_tokens":20}}}
```
