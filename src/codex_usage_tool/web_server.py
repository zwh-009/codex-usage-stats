from __future__ import annotations

import argparse
import csv
import json
import os
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from codex_usage_tool.app_paths import app_data_dir, frontend_dist_dir
from codex_usage_tool.core.parser import DEFAULT_SESSIONS_PATH, DEFAULT_SQLITE_LOG_PATH, auto_load_records, default_log_path
from codex_usage_tool.core.statistics import build_summary
from codex_usage_tool.core.storage import DEFAULT_DB_PATH, load_records, save_records
from codex_usage_tool.window_settings import read_window_settings, update_window_settings


ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = frontend_dist_dir()
PRICE_CONFIG_PATH = app_data_dir() / "model_prices.json"
USAGE_REFRESH_MIN_INTERVAL_SECONDS = 90
_USAGE_REFRESH_LOCK = threading.Lock()
_USAGE_REFRESHING = False
_USAGE_LAST_REFRESH_AT: datetime | None = None
_USAGE_LAST_SOURCE_PATH: Path | None = None
_USAGE_LAST_SOURCE_NOTE = "读取本地缓存"
_USAGE_LAST_FINGERPRINT: tuple[Any, ...] | None = None


def create_app(window_command: Any | None = None) -> FastAPI:
    app = FastAPI(title="Codex Usage Tool", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/usage")
    def usage() -> dict[str, Any]:
        return _usage_payload()

    @app.get("/api/prices")
    def prices() -> dict[str, Any]:
        return {"prices": _read_price_config()}

    @app.post("/api/prices")
    async def save_prices(request: Request) -> dict[str, Any]:
        payload = await request.json()
        prices = payload.get("prices") if isinstance(payload, dict) else {}
        if not isinstance(prices, dict):
            prices = {}
        sanitized = _sanitize_price_config(prices)
        _write_price_config(sanitized)
        return {"prices": sanitized}

    @app.get("/api/window-settings")
    def window_settings() -> dict[str, Any]:
        return {"settings": read_window_settings()}

    @app.post("/api/window-settings")
    async def save_window_settings(request: Request) -> dict[str, Any]:
        payload = await request.json()
        settings = payload.get("settings") if isinstance(payload, dict) else {}
        if not isinstance(settings, dict):
            settings = {}
        saved = update_window_settings(settings)
        if window_command:
            window_command("settings", saved)
        return {"settings": saved}

    @app.post("/api/window-mode")
    async def window_mode(request: Request) -> dict[str, Any]:
        payload = await request.json()
        mode = payload.get("mode") if isinstance(payload, dict) else None
        if mode not in {"main", "widget"}:
            mode = "main"
        saved = update_window_settings({"mode": mode})
        if window_command:
            window_command("mode", saved)
        return {"settings": saved}

    @app.post("/api/window-action")
    async def window_action(request: Request) -> dict[str, Any]:
        payload = await request.json()
        action = payload.get("action") if isinstance(payload, dict) else None
        if action == "reset-widget-position":
            saved = update_window_settings({"widget_geometry": None})
            if window_command:
                window_command("reset-widget-position", saved)
            return {"settings": saved}
        return {"settings": read_window_settings()}

    @app.get("/api/export.csv")
    def export_csv(
        period: str = "today",
        model: str = "all",
        query: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> Response:
        records = _cached_records_with_refresh()
        prices = _read_price_config()
        filtered_records = _filter_records(records, period, model, query, start_date, end_date)
        csv_text = _records_to_csv(filtered_records, prices)
        filename = f"codex_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            content=f"\ufeff{csv_text}",
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/export")
    def export_file(
        period: str = "today",
        model: str = "all",
        query: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> dict[str, Any]:
        records = _cached_records_with_refresh()
        prices = _read_price_config()
        filtered_records = _filter_records(records, period, model, query, start_date, end_date)
        filename = f"codex_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path = _desktop_dir() / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_records_to_xlsx_bytes(filtered_records, prices))
        return {"path": str(path), "filename": filename, "rows": len(filtered_records)}

    if FRONTEND_DIST.exists():
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{path:path}", response_model=None)
        def index(path: str = ""):
            candidate = FRONTEND_DIST / path
            if candidate.is_file():
                return FileResponse(candidate)
            if path == "widget" or path.startswith("widget/"):
                return HTMLResponse(_widget_index_html())
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


def _widget_index_html() -> str:
    html = (FRONTEND_DIST / "index.html").read_text(encoding="utf-8")
    settings_json = json.dumps(read_window_settings(), ensure_ascii=False)
    preload = (
        "<script>"
        f"window.__CODEX_WINDOW_SETTINGS__={settings_json};"
        "try{localStorage.setItem('codex-widget-settings-cache',JSON.stringify(window.__CODEX_WINDOW_SETTINGS__));}catch(e){}"
        "</script>"
    )
    return html.replace("<head>", f"<head>{preload}", 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


def _summary_to_dict(summary: Any) -> dict[str, Any]:
    payload = asdict(summary)
    payload["daily_stats"] = [asdict(stat) for stat in summary.daily_stats]
    return payload


def _usage_payload() -> dict[str, Any]:
    records = _cached_records_with_refresh()
    summary = build_summary(records)
    source_path, source_note, refreshing, refreshed_at = _usage_source_state()
    if not records and refreshing:
        source_note = "首次建立本地缓存，后台读取 Codex 日志中"

    return {
        "source": {
            "path": str(source_path) if source_path else None,
            "name": source_path.name if source_path else None,
            "note": source_note,
            "refreshing": refreshing,
            "refreshed_at": refreshed_at.isoformat() if refreshed_at else None,
        },
        "summary": _summary_to_dict(summary),
        "records": [_record_to_dict(record) for record in records],
    }


def _cached_records_with_refresh() -> list[Any]:
    records = load_records(DEFAULT_DB_PATH)
    _start_usage_refresh()
    return records


def _usage_source_state() -> tuple[Path | None, str, bool, datetime | None]:
    with _USAGE_REFRESH_LOCK:
        return _USAGE_LAST_SOURCE_PATH, _USAGE_LAST_SOURCE_NOTE, _USAGE_REFRESHING, _USAGE_LAST_REFRESH_AT


def _start_usage_refresh() -> None:
    global _USAGE_LAST_SOURCE_NOTE, _USAGE_REFRESHING
    fingerprint = _usage_source_fingerprint()
    now = datetime.now().astimezone()
    with _USAGE_REFRESH_LOCK:
        if _USAGE_REFRESHING:
            return
        if (
            _USAGE_LAST_REFRESH_AT
            and (now - _USAGE_LAST_REFRESH_AT).total_seconds() < USAGE_REFRESH_MIN_INTERVAL_SECONDS
        ):
            _USAGE_LAST_SOURCE_NOTE = "读取本地缓存，后台刷新间隔保护中"
            return
        if _USAGE_LAST_REFRESH_AT and _USAGE_LAST_FINGERPRINT == fingerprint:
            _USAGE_LAST_SOURCE_NOTE = "读取本地缓存，日志未变化"
            return
        _USAGE_REFRESHING = True
    thread = threading.Thread(target=_refresh_usage_cache, args=(fingerprint,), daemon=True)
    thread.start()


def _refresh_usage_cache(fingerprint: tuple[Any, ...]) -> None:
    global _USAGE_LAST_FINGERPRINT, _USAGE_LAST_REFRESH_AT, _USAGE_LAST_SOURCE_NOTE, _USAGE_LAST_SOURCE_PATH, _USAGE_REFRESHING
    try:
        start = time.perf_counter()
        records, source_path, source_note = auto_load_records()
        save_records(records, DEFAULT_DB_PATH, replace=True)
        duration = time.perf_counter() - start
        with _USAGE_REFRESH_LOCK:
            _USAGE_LAST_REFRESH_AT = datetime.now().astimezone()
            _USAGE_LAST_SOURCE_PATH = source_path
            _USAGE_LAST_SOURCE_NOTE = f"{source_note}，后台刷新 {duration:.1f}s"
            _USAGE_LAST_FINGERPRINT = fingerprint
    except Exception as error:
        with _USAGE_REFRESH_LOCK:
            _USAGE_LAST_SOURCE_NOTE = f"后台刷新失败：{error}"
    finally:
        with _USAGE_REFRESH_LOCK:
            _USAGE_REFRESHING = False


def _usage_source_fingerprint() -> tuple[Any, ...]:
    env_path = default_log_path()
    if os.environ.get("CODEX_USAGE_LOG_PATH") and env_path.exists():
        return _path_fingerprint("env", env_path)

    if DEFAULT_SESSIONS_PATH.exists():
        count = 0
        total_size = 0
        latest_mtime = 0
        for path in DEFAULT_SESSIONS_PATH.rglob("rollout-*.jsonl"):
            try:
                stat = path.stat()
            except OSError:
                continue
            count += 1
            total_size += stat.st_size
            latest_mtime = max(latest_mtime, stat.st_mtime_ns)
        return ("sessions", str(DEFAULT_SESSIONS_PATH), count, total_size, latest_mtime)

    if DEFAULT_SQLITE_LOG_PATH.exists():
        return _path_fingerprint("sqlite", DEFAULT_SQLITE_LOG_PATH)

    codex_dir = Path.home() / ".codex"
    count = 0
    total_size = 0
    latest_mtime = 0
    for path in codex_dir.glob("logs/**/*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        count += 1
        total_size += stat.st_size
        latest_mtime = max(latest_mtime, stat.st_mtime_ns)
    return ("jsonl", str(codex_dir), count, total_size, latest_mtime)


def _path_fingerprint(kind: str, path: Path) -> tuple[Any, ...]:
    try:
        stat = path.stat()
    except OSError:
        return (kind, str(path), None)
    return (kind, str(path), stat.st_size, stat.st_mtime_ns)


def _record_to_dict(record: Any) -> dict[str, Any]:
    return {
        "timestamp": record.timestamp.isoformat(),
        "model": record.model,
        "prompt_tokens": record.prompt_tokens,
        "completion_tokens": record.completion_tokens,
        "total_tokens": record.total_tokens,
        "cached": record.cached,
        "cached_tokens": record.cached_tokens,
        "cost_usd": record.cost_usd,
    }


def _filter_records(
    records: list[Any],
    period: str,
    model: str,
    query: str,
    start_date: str,
    end_date: str,
) -> list[Any]:
    now = datetime.now().astimezone()
    start: datetime | None = None
    end: datetime | None = None

    if period == "date":
        start = _parse_local_date(start_date)
        end_start = _parse_local_date(end_date)
        if start and end_start and start > end_start:
            start, end_start = end_start, start
        if end_start:
            end = end_start + timedelta(days=1)
    elif period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)

    query_text = query.strip().lower()
    filtered: list[Any] = []
    for record in records:
        timestamp = _as_local(record.timestamp)
        if start and timestamp < start:
            continue
        if end and timestamp >= end:
            continue
        if model != "all" and record.model != model:
            continue
        if query_text and query_text not in f"{record.model} {timestamp.strftime('%Y/%m/%d %H:%M:%S')}".lower():
            continue
        filtered.append(record)
    return sorted(filtered, key=lambda item: item.timestamp, reverse=True)


def _records_to_csv(records: list[Any], prices: dict[str, dict[str, float]]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["时间", "模型", "输入", "输出", "总量", "缓存 Tokens", "花费 USD"])
    for record in records:
        writer.writerow(
            [
                _as_local(record.timestamp).strftime("%Y/%m/%d %H:%M:%S"),
                record.model,
                record.prompt_tokens,
                record.completion_tokens,
                record.total_tokens,
                record.cached_tokens,
                f"{_record_cost(record, prices):.6f}",
            ]
        )
    return buffer.getvalue()


def _downloads_dir() -> Path:
    path = Path.home() / "Downloads"
    if path.exists():
        return path
    return app_data_dir() / "exports"


def _desktop_dir() -> Path:
    path = Path.home() / "Desktop"
    if path.exists():
        return path
    return app_data_dir() / "exports"


def _records_to_xlsx_bytes(records: list[Any], prices: dict[str, dict[str, float]]) -> bytes:
    rows: list[list[str | int | float]] = [["时间", "模型", "输入", "输出", "总量", "缓存 Tokens", "花费 USD"]]
    for record in records:
        rows.append(
            [
                _as_local(record.timestamp).strftime("%Y/%m/%d %H:%M:%S"),
                record.model,
                record.prompt_tokens,
                record.completion_tokens,
                record.total_tokens,
                record.cached_tokens,
                round(_record_cost(record, prices), 6),
            ]
        )

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", _xlsx_content_types())
        workbook.writestr("_rels/.rels", _xlsx_root_rels())
        workbook.writestr("docProps/app.xml", _xlsx_app_props())
        workbook.writestr("docProps/core.xml", _xlsx_core_props())
        workbook.writestr("xl/workbook.xml", _xlsx_workbook())
        workbook.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels())
        workbook.writestr("xl/styles.xml", _xlsx_styles())
        workbook.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(rows))
    return output.getvalue()


def _xlsx_sheet(rows: list[list[str | int | float]]) -> str:
    sheet_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_xlsx_column_name(column_index)}{row_index}"
            style = ' s="1"' if row_index == 1 else ""
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{escape(str(value))}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cols>
    <col min="1" max="1" width="22" customWidth="1"/>
    <col min="2" max="2" width="16" customWidth="1"/>
    <col min="3" max="6" width="16" customWidth="1"/>
    <col min="7" max="7" width="14" customWidth="1"/>
  </cols>
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetData>{''.join(sheet_rows)}</sheetData>
  <autoFilter ref="A1:G{max(len(rows), 1)}"/>
</worksheet>'''


def _xlsx_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_content_types() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''


def _xlsx_root_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def _xlsx_workbook() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="用量明细" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''


def _xlsx_workbook_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''


def _xlsx_styles() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _xlsx_app_props() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex 用量统计</Application>
</Properties>'''


def _xlsx_core_props() -> str:
    created = datetime.now().astimezone().isoformat()
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Codex 用量统计</dc:title>
  <dc:creator>Codex 用量统计</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
</cp:coreProperties>'''


def _record_cost(record: Any, prices: dict[str, dict[str, float]]) -> float:
    price = prices.get(record.model)
    if not price:
        return 0.0
    cached = min(record.cached_tokens, record.prompt_tokens)
    uncached_input = max(record.prompt_tokens - cached, 0)
    return (
        uncached_input * price["input"]
        + cached * price["cached"]
        + record.completion_tokens * price["output"]
    ) / 1_000_000


def _parse_local_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        year, month, day = [int(part) for part in value.split("-")]
    except ValueError:
        return None
    return datetime(year, month, day, tzinfo=datetime.now().astimezone().tzinfo)


def _as_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return value.astimezone()


def _read_price_config() -> dict[str, dict[str, float]]:
    try:
        payload = json.loads(PRICE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return _sanitize_price_config(payload)


def _sanitize_price_config(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    sanitized: dict[str, dict[str, float]] = {}
    for model, price in payload.items():
        if not isinstance(model, str) or not isinstance(price, dict):
            continue
        sanitized[model] = {
            "input": _non_negative_float(price.get("input")),
            "cached": _non_negative_float(price.get("cached")),
            "output": _non_negative_float(price.get("output")),
        }
    return {
        model: price
        for model, price in sanitized.items()
        if price["input"] > 0 or price["cached"] > 0 or price["output"] > 0
    }


def _write_price_config(prices: dict[str, dict[str, float]]) -> None:
    PRICE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRICE_CONFIG_PATH.write_text(
        json.dumps(prices, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _non_negative_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed > 0 else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
