# Release Guide

本项目采用“源码仓库 + GitHub Release 附件”的分发方式。

## 面向普通用户

普通用户下载 GitHub Releases 里的发布包：

```text
直接解压本压缩包即可使用-无脑使用版.zip
```

使用方式：

```text
解压 zip -> 双击 CodexUsageTool.exe
```

不要让普通用户下载 GitHub 右上角 `Code -> Download ZIP` 的源码包。源码包不包含打包后的 exe。

## 面向开发者

开发者下载源码仓库后，可以使用源码运行：

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
python -m codex_usage_tool
```

构建 Windows 便携版：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

构建脚本会生成：

```text
release/CodexUsageTool_<时间戳>/
release/直接解压本压缩包即可使用-无脑使用版.zip
```

发布 GitHub Release 时，上传固定名称的“无脑使用版”zip 作为附件。

## 发布前检查

发布源码前执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\open_source_check.ps1
```

确认不要提交以下内容：

```text
data/
release/
.venv/
node_modules/
frontend/node_modules/
frontend/dist/
*.sqlite
*.sqlite3
*.db
*.csv
*.xlsx
*.log
*.zip
```

## GitHub Release 建议文案

标题：

```text
Codex 用量统计 v0.1.0
```

说明：

```text
普通用户请下载“直接解压本压缩包即可使用-无脑使用版.zip”。

使用方式：
1. 解压 zip
2. 双击 CodexUsageTool.exe

本工具只读取当前 Windows 用户本机的 Codex 日志，不上传日志、不读取 .codex\auth.json。
```
