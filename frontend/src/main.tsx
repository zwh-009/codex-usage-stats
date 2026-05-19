import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { motion } from "framer-motion";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Maximize2,
  MonitorDot,
  Palette,
  RefreshCcw,
  Settings,
  Sparkles,
  Zap
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import "./styles.css";

type UsageRecord = {
  timestamp: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached: boolean;
  cached_tokens: number;
  cost_usd: number;
};

type ApiPayload = {
  source: {
    path: string | null;
    name: string | null;
    note: string;
    refreshing?: boolean;
    refreshed_at?: string | null;
  };
  records: UsageRecord[];
};

type Period = "today" | "7d" | "30d" | "all" | "date";
type PriceConfig = Record<string, { input: number; cached: number; output: number }>;
type PriceDraft = Record<string, { input: string; cached: string; output: string }>;
type ExportNotice = { type: "success" | "error"; text: string };
type WidgetTheme = "glass" | "frosted" | "light" | "dark";
type WidgetSettings = {
  mode: "main" | "widget";
  widget_period: Period;
  widget_opacity: number;
  widget_theme: WidgetTheme;
  widget_compact: boolean;
  widget_show_items: {
    tokens: boolean;
    requests: boolean;
    cost: boolean;
    cache_rate: boolean;
    token_split: boolean;
  };
};
type UsageCache = { payload: ApiPayload; updated_at: string };
type DesktopBridge = {
  moveBy: (dx: number, dy: number) => void;
  resizeBy: (edge: string, dx: number, dy: number) => void;
  setContentHeight: (height: number) => void;
  finishDrag: () => void;
};
type WidgetDragState = { mode: "move"; x: number; y: number } | { mode: "resize"; edge: string; x: number; y: number };

declare global {
  interface Window {
    qt?: { webChannelTransport: unknown };
    QWebChannel?: new (
      transport: unknown,
      callback: (channel: { objects: { desktopBridge?: DesktopBridge } }) => void
    ) => void;
    desktopBridge?: DesktopBridge;
    __CODEX_WINDOW_SETTINGS__?: Partial<WidgetSettings>;
  }
}

const periods: Array<{ value: Period; label: string }> = [
  { value: "today", label: "今天" },
  { value: "7d", label: "7 天" },
  { value: "30d", label: "30 天" },
  { value: "all", label: "全部" }
];

const pieColors = ["#1683f8", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444"];
const requestPageSize = 10;
const usageCacheKey = "codex-usage-cache";
const widgetSettingsCacheKey = "codex-widget-settings-cache";
const defaultWidgetSettings: WidgetSettings = {
  mode: "main",
  widget_period: "today",
  widget_opacity: 0.86,
  widget_theme: "glass",
  widget_compact: false,
  widget_show_items: {
    tokens: true,
    requests: true,
    cost: true,
    cache_rate: true,
    token_split: true
  }
};

function useSmoothWheel(ref: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    let targetTop = element.scrollTop;
    let frame = 0;

    const animate = () => {
      const delta = targetTop - element.scrollTop;
      if (Math.abs(delta) < 0.6) {
        element.scrollTop = targetTop;
        frame = 0;
        return;
      }
      element.scrollTop += delta * 0.18;
      frame = window.requestAnimationFrame(animate);
    };

    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      const maxTop = element.scrollHeight - element.clientHeight;
      if (maxTop <= 0) return;

      targetTop = Math.max(0, Math.min(maxTop, targetTop + event.deltaY));
      const atTop = element.scrollTop <= 0 && event.deltaY < 0;
      const atBottom = element.scrollTop >= maxTop - 1 && event.deltaY > 0;
      if (atTop || atBottom) return;

      event.preventDefault();
      if (!frame) frame = window.requestAnimationFrame(animate);
    };

    element.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      element.removeEventListener("wheel", onWheel);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [ref]);
}

function useSmoothPageWheel() {
  useEffect(() => {
    let targetTop = window.scrollY;
    let frame = 0;

    const animate = () => {
      const delta = targetTop - window.scrollY;
      if (Math.abs(delta) < 0.8) {
        window.scrollTo(0, targetTop);
        frame = 0;
        return;
      }
      window.scrollTo(0, window.scrollY + delta * 0.16);
      frame = window.requestAnimationFrame(animate);
    };

    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      if ((event.target as Element | null)?.closest?.(".table-wrap")) return;

      const documentElement = document.documentElement;
      const maxTop = documentElement.scrollHeight - window.innerHeight;
      if (maxTop <= 0) return;

      targetTop = Math.max(0, Math.min(maxTop, targetTop + event.deltaY));
      const atTop = window.scrollY <= 0 && event.deltaY < 0;
      const atBottom = window.scrollY >= maxTop - 1 && event.deltaY > 0;
      if (atTop || atBottom) return;

      event.preventDefault();
      if (!frame) frame = window.requestAnimationFrame(animate);
    };

    window.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      window.removeEventListener("wheel", onWheel);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);
}

function useDesktopBridge() {
  useEffect(() => {
    if (window.desktopBridge) return;
    if (!window.qt?.webChannelTransport) return;

    const setup = () => {
      if (!window.QWebChannel || !window.qt?.webChannelTransport) return;
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        window.desktopBridge = channel.objects.desktopBridge;
      });
    };

    if (window.QWebChannel) {
      setup();
      return;
    }

    const script = document.createElement("script");
    script.src = "qrc:///qtwebchannel/qwebchannel.js";
    script.onload = setup;
    document.head.appendChild(script);
  }, []);
}

function App() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<Period>("today");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [model, setModel] = useState("all");
  const [logModel, setLogModel] = useState("all");
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [visibleRefreshing, setVisibleRefreshing] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportNotice, setExportNotice] = useState<ExportNotice | null>(null);
  const [priceOpen, setPriceOpen] = useState(false);
  const [priceConfig, setPriceConfig] = useState<PriceConfig>(() => loadPriceConfig());
  const [requestPage, setRequestPage] = useState(1);
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const visibleRefreshActive = useRef(false);
  const logTableRef = useRef<HTMLDivElement | null>(null);
  useSmoothPageWheel();
  useSmoothWheel(logTableRef);

  const load = async ({ showSpinner = false }: { showSpinner?: boolean } = {}) => {
    if (showSpinner) {
      visibleRefreshActive.current = true;
      setVisibleRefreshing(true);
    }
    setError("");
    let completedAt: Date | null = null;
    try {
      const response = await fetch("/api/usage");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const nextPayload = await response.json();
      completedAt = new Date();
      if (showSpinner) {
        visibleRefreshActive.current = false;
        setVisibleRefreshing(false);
        setLastUpdated(completedAt);
      }
      setPayload(nextPayload);
      writeUsageCache(nextPayload, completedAt);
      if (!showSpinner && !visibleRefreshActive.current) {
        setLastUpdated(completedAt);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
      if (showSpinner && !completedAt) {
        visibleRefreshActive.current = false;
        setVisibleRefreshing(false);
      }
    }
  };

  useEffect(() => {
    const cached = readUsageCache();
    if (cached) {
      setPayload(cached.payload);
      setLastUpdated(new Date(cached.updated_at));
      setLoading(false);
    }
    if (!cached || !isFreshUsageCache(cached)) {
      load({ showSpinner: true });
    } else {
      setVisibleRefreshing(false);
    }
    loadSavedPriceConfig().then((config) => setPriceConfig(config));
    const timer = window.setInterval(() => load(), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!payload?.source.refreshing) return;
    const timer = window.setTimeout(() => load(), 2500);
    return () => window.clearTimeout(timer);
  }, [payload?.source.refreshing]);

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const allRecords = payload?.records ?? [];
  const models = useMemo(() => [...new Set(allRecords.map((record) => record.model))].sort(), [allRecords]);

  const records = useMemo(() => {
    const now = new Date();
    const selectedStart = startDate ? localDateStart(startDate) : null;
    const selectedEndStart = endDate ? localDateStart(endDate) : null;
    const rangeStart =
      selectedStart && selectedEndStart && selectedStart > selectedEndStart ? selectedEndStart : selectedStart;
    const rangeEndStart =
      selectedStart && selectedEndStart && selectedStart > selectedEndStart ? selectedStart : selectedEndStart;
    const rangeEnd = rangeEndStart ? new Date(rangeEndStart.getTime() + 86400_000) : null;
    const start =
      period === "date"
        ? rangeStart
        : period === "today"
        ? new Date(now.getFullYear(), now.getMonth(), now.getDate())
        : period === "7d"
          ? new Date(now.getTime() - 7 * 86400_000)
          : period === "30d"
            ? new Date(now.getTime() - 30 * 86400_000)
            : null;

    return allRecords.filter((record) => {
      const time = new Date(record.timestamp);
      if (start && time < start) return false;
      if (period === "date" && rangeEnd && time >= rangeEnd) return false;
      if (model !== "all" && record.model !== model) return false;
      return true;
    });
  }, [allRecords, endDate, model, period, startDate]);

  const summary = useMemo(() => summarize(records, priceConfig), [records, priceConfig]);
  const hourlyTrend = isHourlyTrend(period, startDate, endDate);
  const trendData = useMemo(() => buildTrend(records, hourlyTrend), [hourlyTrend, records]);
  const modelShare = useMemo(() => buildModelShare(records), [records]);
  const cacheRate = summary.promptTokens ? summary.cachedTokens / summary.promptTokens : 0;
  const logModels = useMemo(() => [...new Set(records.map((record) => record.model))].sort(), [records]);
  const sortedRows = useMemo(
    () =>
      records
        .filter((record) => logModel === "all" || record.model === logModel)
        .sort((a, b) => +new Date(b.timestamp) - +new Date(a.timestamp)),
    [logModel, records]
  );
  const totalRequestPages = Math.max(1, Math.ceil(sortedRows.length / requestPageSize));
  const pageRows = useMemo(
    () => sortedRows.slice((requestPage - 1) * requestPageSize, requestPage * requestPageSize),
    [requestPage, sortedRows]
  );
  const pageItems = useMemo(
    () => buildPageItems(requestPage, totalRequestPages, viewportWidth <= 640),
    [requestPage, totalRequestPages, viewportWidth]
  );
  const visibleStart = sortedRows.length ? (requestPage - 1) * requestPageSize + 1 : 0;
  const visibleEnd = Math.min(requestPage * requestPageSize, sortedRows.length);

  useEffect(() => {
    setRequestPage(1);
  }, [endDate, logModel, model, period, startDate]);

  useEffect(() => {
    setRequestPage((page) => Math.min(page, totalRequestPages));
  }, [totalRequestPages]);

  useEffect(() => {
    if (logModel !== "all" && !logModels.includes(logModel)) {
      setLogModel("all");
    }
  }, [logModel, logModels]);

  const exportCsv = async () => {
    const params = new URLSearchParams({
      period,
      model,
      start_date: startDate,
      end_date: endDate
    });
    setExporting(true);
    setExportNotice(null);
    try {
      const response = await fetch(`/api/export?${params.toString()}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await response.json();
      setExportNotice({ type: "success", text: "已保存在桌面" });
      window.setTimeout(() => setExportNotice(null), 5000);
    } catch (err) {
      setExportNotice({ type: "error", text: err instanceof Error ? `导出失败：${err.message}` : "导出失败" });
      window.setTimeout(() => setExportNotice(null), 5000);
    } finally {
      setExporting(false);
    }
  };

  const switchToWidget = async () => {
    await setWindowMode("widget");
  };

  return (
    <main className="shell">
      <header className="topbar">
        <div className="title-row">
          <div>
            <h1>用量统计</h1>
            <p>查看 Codex 模型的本地用量和缓存情况</p>
          </div>
        </div>
        <div className="actions">
          <div className="refresh-state">
            <strong>
              {payload?.source.refreshing
                ? "后台更新中"
                : lastUpdated
                  ? `${formatClock(lastUpdated)} 刷新`
                  : "等待读取"}
            </strong>
          </div>
          <button className="ghost-button" onClick={() => load({ showSpinner: true })} disabled={visibleRefreshing}>
            <RefreshCcw size={17} className={visibleRefreshing ? "spinning" : ""} />
            刷新
          </button>
          <button className="ghost-button" onClick={exportCsv} disabled={exporting}>
            <Download size={17} />
            {exporting ? "导出中" : "导出"}
          </button>
          <button className="ghost-button" onClick={switchToWidget}>
            <MonitorDot size={17} />
            组件
          </button>
          <button className="ghost-button" onClick={() => setPriceOpen(true)}>
            <Settings size={17} />
            价格
          </button>
        </div>
      </header>

      <section className="toolbar panel">
        <div className="filter-zone">
          <div className="filter-group">
            {periods.map((item) => (
              <button
                key={item.value}
                className={`chip ${period === item.value ? "active" : ""}`}
                onClick={() => {
                  setPeriod(item.value);
                  setStartDate("");
                  setEndDate("");
                }}
              >
                {item.label}
              </button>
            ))}
            <input
              className="date-input"
              type="date"
              value={startDate}
              onChange={(event) => {
                setStartDate(event.target.value);
                if (event.target.value) setPeriod("date");
              }}
            />
            <span className="date-separator">至</span>
            <input
              className="date-input"
              type="date"
              value={endDate}
              onChange={(event) => {
                setEndDate(event.target.value);
                if (event.target.value) setPeriod("date");
              }}
            />
          </div>
        </div>
        <div className="model-selector">
          <div className="select-wrap">
            <select value={model} onChange={(event) => setModel(event.target.value)}>
              <option value="all">全部模型</option>
              {models.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {error ? <div className="error-panel">读取失败：{error}</div> : null}
      {exportNotice ? (
        <motion.div
          className={`export-toast ${exportNotice.type}`}
          role={exportNotice.type === "error" ? "alert" : "status"}
          initial={{ opacity: 0, y: -8, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -8, scale: 0.98 }}
        >
          {exportNotice.text}
        </motion.div>
      ) : null}
      {loading ? (
        <div className="loading-panel">
          <RefreshCcw size={17} className="spinning" />
          正在读取本地 Codex 用量...
        </div>
      ) : null}

      <motion.section className="hero-card" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
        <div className="hero-head">
          <div>
            <div className="eyebrow">
              <span className="icon-bubble"><Zap size={18} /></span>
              真实消耗 Tokens
            </div>
            <motion.div className="hero-number" initial={false} animate={{ opacity: 1 }}>
              {formatNumber(summary.totalTokens)}
            </motion.div>
            <div className="hero-sub">约 {formatCompact(summary.totalTokens)} tokens</div>
          </div>
          <div className="hero-side">
            <SmallStat label="总请求数" value={formatNumber(summary.requests)} />
            <SmallStat
              label="总成本"
              value={summary.hasPricing ? `$${summary.totalCost.toFixed(4)}` : "未配置"}
              accent={summary.hasPricing}
              onClick={!summary.hasPricing ? () => setPriceOpen(true) : undefined}
            />
          </div>
        </div>

        <div className="metric-grid">
          <MetricCard label="输入 Tokens" value={formatCompact(summary.promptTokens)} />
          <MetricCard label="输出 Tokens" value={formatCompact(summary.completionTokens)} />
          <MetricCard label="缓存 Tokens" value={formatCompact(summary.cachedTokens)} />
          <MetricCard label="平均每请求" value={formatCompact(summary.requests ? summary.totalTokens / summary.requests : 0)} />
        </div>

        <div className="cache-line">
          <div>
            <span>缓存命中率</span>
            <strong>{(cacheRate * 100).toFixed(1)}%</strong>
          </div>
          <div className="progress-track">
            <motion.div
              className="progress-fill"
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(cacheRate * 100, 100)}%` }}
              transition={{ duration: 0.55, ease: "easeOut" }}
            />
          </div>
        </div>
      </motion.section>

      <section className="chart-grid">
        <Panel title="使用趋势" right={<span>{periodLabel(period)}</span>}>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={trendData} margin={{ left: 6, right: 12, top: 16, bottom: 0 }}>
              <defs>
                <linearGradient id="tokenGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1683f8" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#1683f8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="#edf1f7" />
              <XAxis dataKey="date" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} tickFormatter={formatCompact} width={72} />
              <Tooltip formatter={(value) => formatNumber(Number(value))} />
              <Area type="monotone" dataKey="tokens" stroke="#1683f8" fill="url(#tokenGradient)" strokeWidth={3} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="模型占比">
          {modelShare.length === 0 ? (
            <EmptyState text="暂无模型数据" />
          ) : modelShare.length === 1 ? (
            <div className="single-model-donut">
              <div>
                <strong>100%</strong>
                <span>{modelShare[0].model}</span>
              </div>
            </div>
          ) : (
            <div className="pie-stage">
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={modelShare} dataKey="tokens" nameKey="model" innerRadius={62} outerRadius={94} paddingAngle={3} isAnimationActive={false}>
                    {modelShare.map((_, index) => <Cell key={index} fill={pieColors[index % pieColors.length]} />)}
                  </Pie>
                  <Tooltip formatter={(value) => formatNumber(Number(value))} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="legend">
              {modelShare.map((item, index) => (
                <div key={item.model}>
                <span style={{ background: pieColors[index % pieColors.length] }} />
                {item.model}
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <Panel
        title="使用日志"
        right={
          <div className="log-filter select-wrap">
            <select value={logModel} onChange={(event) => setLogModel(event.target.value)}>
              <option value="all">全部模型</option>
              {logModels.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>
        }
      >
        <div className="table-wrap" ref={logTableRef}>
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>模型</th>
                <th>输入</th>
                <th>输出</th>
                <th>总量</th>
                <th>缓存 Tokens</th>
                <th>花费</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((record, index) => (
                <motion.tr key={`${record.timestamp}-${index}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <td>{formatDate(record.timestamp)}</td>
                  <td><span className="model-pill">{record.model}</span></td>
                  <td>{formatNumber(record.prompt_tokens)}</td>
                  <td>{formatNumber(record.completion_tokens)}</td>
                  <td>{formatNumber(record.total_tokens)}</td>
                  <td>{formatNumber(record.cached_tokens)}</td>
                  <td>{summary.hasPricing ? `$${computeRecordCost(record, priceConfig).toFixed(6)}` : "未配置"}</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
          {!loading && sortedRows.length === 0 ? (
            <div className="empty">
              <Sparkles size={18} />
              当前筛选条件下没有记录
            </div>
          ) : null}
        </div>
        <div className="pagination">
          <span>显示第 {formatNumber(visibleStart)} 条 - 第 {formatNumber(visibleEnd)} 条，共 {formatNumber(sortedRows.length)} 条</span>
          <div className="page-controls">
            <span>总页数：{formatNumber(totalRequestPages)}</span>
            <button
              className="page-button"
              onClick={() => setRequestPage((page) => Math.max(1, page - 1))}
              disabled={requestPage <= 1}
              aria-label="上一页"
            >
              <ChevronLeft size={16} />
            </button>
            {pageItems.map((item, index) =>
              item === "ellipsis" ? (
                <span className="page-ellipsis" key={`ellipsis-${index}`}>...</span>
              ) : (
                <button
                  className={`page-number ${item === requestPage ? "active" : ""}`}
                  key={item}
                  onClick={() => setRequestPage(item)}
                >
                  {item}
                </button>
              )
            )}
            <button
              className="page-button"
              onClick={() => setRequestPage((page) => Math.min(totalRequestPages, page + 1))}
              disabled={requestPage >= totalRequestPages}
              aria-label="下一页"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </Panel>
      {priceOpen ? (
        <PriceModal
          models={models}
          value={priceConfig}
          onChange={(next) => {
            setPriceConfig(next);
            savePriceConfig(next);
          }}
          onClose={() => setPriceOpen(false)}
        />
      ) : null}
    </main>
  );
}

function WidgetApp() {
  const [payload, setPayload] = useState<ApiPayload | null>(null);
  const [priceConfig, setPriceConfig] = useState<PriceConfig>(() => loadPriceConfig());
  const [settings, setSettings] = useState<WidgetSettings>(() => readWidgetSettingsCache());
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const dragRef = useRef<WidgetDragState | null>(null);
  const cardRef = useRef<HTMLElement | null>(null);

  useDesktopBridge();

  useEffect(() => {
    document.body.classList.add("widget-body");
    document.documentElement.classList.add("widget-html");
    return () => {
      document.body.classList.remove("widget-body");
      document.documentElement.classList.remove("widget-html");
    };
  }, []);

  const load = async ({ visible = false }: { visible?: boolean } = {}) => {
    if (visible) setRefreshing(true);
    try {
      const [usageResponse, priceResponse] = await Promise.all([
        fetch("/api/usage"),
        fetch("/api/prices")
      ]);
      if (usageResponse.ok) {
        const nextPayload = await usageResponse.json();
        const updatedAt = new Date();
        setPayload(nextPayload);
        setLastUpdated(updatedAt);
        writeUsageCache(nextPayload, updatedAt);
      }
      if (priceResponse.ok) {
        const pricePayload = await priceResponse.json();
        if (pricePayload?.prices) {
          localStorage.setItem("codex-usage-prices", JSON.stringify(pricePayload.prices));
          setPriceConfig(pricePayload.prices);
        }
      }
    } finally {
      setLoading(false);
      if (visible) setRefreshing(false);
    }
  };

  const loadSettings = async () => {
    try {
      const response = await fetch("/api/window-settings");
      if (!response.ok) return;
      const payload = await response.json();
      const next = normalizeWidgetSettings(payload?.settings);
      setSettings(next);
      writeWidgetSettingsCache(next);
    } catch {
      // Keep the cached appearance so switching modes does not visibly reset.
    }
  };

  useEffect(() => {
    loadSettings();
    const cached = readUsageCache();
    if (cached) {
      setPayload(cached.payload);
      setLastUpdated(new Date(cached.updated_at));
      setLoading(false);
    }
    load();
    const timer = window.setInterval(() => load(), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!payload?.source.refreshing) return;
    const timer = window.setTimeout(() => load(), 2500);
    return () => window.clearTimeout(timer);
  }, [payload?.source.refreshing]);

  const records = useMemo(
    () => filterByPeriod(payload?.records ?? [], settings.widget_period),
    [payload, settings.widget_period]
  );
  const summary = useMemo(() => summarize(records, priceConfig), [records, priceConfig]);
  const cacheRate = summary.promptTokens ? summary.cachedTokens / summary.promptTokens : 0;
  const tokenSplit = useMemo(() => {
    const cached = summary.cachedTokens;
    const input = summary.promptTokens;
    const output = summary.completionTokens;
    const total = Math.max(input + output + cached, 1);
    return [
      { key: "input", label: "输入", value: input, percent: (input / total) * 100 },
      { key: "output", label: "输出", value: output, percent: (output / total) * 100 },
      { key: "cache", label: "缓存", value: cached, percent: (cached / total) * 100 }
    ];
  }, [summary.cachedTokens, summary.completionTokens, summary.promptTokens]);
  const statItems = useMemo(
    () =>
      [
        settings.widget_show_items.requests ? { label: "请求", value: formatNumber(summary.requests) } : null,
        settings.widget_show_items.cost
          ? { label: "成本", value: summary.hasPricing ? `$${summary.totalCost.toFixed(2)}` : "未配置" }
          : null,
        settings.widget_show_items.cache_rate ? { label: "缓存", value: `${(cacheRate * 100).toFixed(1)}%` } : null
      ].filter((item): item is { label: string; value: string } => Boolean(item)),
    [cacheRate, settings.widget_show_items.cache_rate, settings.widget_show_items.cost, settings.widget_show_items.requests, summary]
  );
  const widgetStyle = useMemo(
    () => {
      const opacity = settings.widget_opacity;
      return {
        "--surface-card": opacity.toFixed(2),
        "--surface-card-dark": (opacity * 0.94).toFixed(2),
        "--surface-strong": opacity.toFixed(2),
        "--surface-medium": (opacity * 0.92).toFixed(2),
        "--surface-soft": (opacity * 0.7).toFixed(2),
        "--surface-control": (opacity * 0.62).toFixed(2),
        "--surface-active": (opacity * 0.86).toFixed(2),
        "--surface-border": (opacity * 0.5).toFixed(2),
        "--surface-accent": (opacity * 0.22).toFixed(2),
        "--surface-track": (opacity * 0.18).toFixed(2),
        "--surface-dark-stat": (opacity * 0.34).toFixed(2)
      } as React.CSSProperties;
    },
    [settings.widget_opacity]
  );

  useEffect(() => {
    if (appearanceOpen) return;
    const timers: number[] = [];
    const frames: number[] = [];
    const fitHeight = () => {
      const card = cardRef.current;
      if (!card) return;
      const children = [...card.children].filter((child) => {
        const element = child as HTMLElement;
        return !element.classList.contains("widget-resize-handle")
          && !element.classList.contains("appearance-panel")
          && !element.classList.contains("widget-context-menu");
      }) as HTMLElement[];
      const contentBottom = children.reduce((bottom, child) => Math.max(bottom, child.offsetTop + child.offsetHeight), 0);
      const styles = getComputedStyle(card);
      const paddingBottom = Number.parseFloat(styles.paddingBottom) || 0;
      const border = Number.parseFloat(styles.borderBottomWidth) || 0;
      const desiredHeight = Math.ceil(contentBottom + paddingBottom + border);
      window.desktopBridge?.setContentHeight(desiredHeight);
    };

    const scheduleFit = (delay: number) => {
      timers.push(window.setTimeout(() => {
        frames.push(window.requestAnimationFrame(fitHeight));
      }, delay));
    };

    scheduleFit(0);
    scheduleFit(120);
    scheduleFit(420);
    scheduleFit(900);
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      frames.forEach((frame) => window.cancelAnimationFrame(frame));
    };
  }, [
    appearanceOpen,
    settings.widget_show_items.cache_rate,
    settings.widget_show_items.cost,
    settings.widget_show_items.requests,
    settings.widget_show_items.token_split,
    settings.widget_show_items.tokens,
    statItems.length,
    summary.totalTokens,
    summary.requests
  ]);

  useEffect(() => {
    const finishDrag = () => {
      if (!dragRef.current) return;
      dragRef.current = null;
      window.desktopBridge?.finishDrag();
    };

    const moveWindow = (event: MouseEvent) => {
      if (!dragRef.current) return;
      if (event.buttons !== 1) {
        finishDrag();
        return;
      }
      const dx = event.screenX - dragRef.current.x;
      const dy = event.screenY - dragRef.current.y;
      if (Math.abs(dx) + Math.abs(dy) < 1) return;
      const current = dragRef.current;
      if (current.mode === "resize") {
        window.desktopBridge?.resizeBy(current.edge, Math.round(dx), Math.round(dy));
        dragRef.current = { mode: "resize", edge: current.edge, x: event.screenX, y: event.screenY };
      } else {
        window.desktopBridge?.moveBy(Math.round(dx), Math.round(dy));
        dragRef.current = { mode: "move", x: event.screenX, y: event.screenY };
      }
    };

    window.addEventListener("mousemove", moveWindow);
    window.addEventListener("mouseup", finishDrag);
    window.addEventListener("blur", finishDrag);
    return () => {
      window.removeEventListener("mousemove", moveWindow);
      window.removeEventListener("mouseup", finishDrag);
      window.removeEventListener("blur", finishDrag);
    };
  }, []);

  const saveSettings = async (partial: Partial<WidgetSettings>) => {
    const next = normalizeWidgetSettings({ ...settings, mode: "widget", ...partial });
    setSettings(next);
    writeWidgetSettingsCache(next);
    await saveWindowSettings(next);
  };

  const changeShowItem = (key: keyof WidgetSettings["widget_show_items"], value: boolean) => {
    saveSettings({
      widget_show_items: {
        ...settings.widget_show_items,
        [key]: value
      }
    });
  };

  const startDrag = (event: React.MouseEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    const target = event.target as Element;
    if (target.closest("button,input,select,label,.appearance-panel,.widget-context-menu")) return;
    event.preventDefault();
    setContextMenu(null);
    setAppearanceOpen(false);
    dragRef.current = { mode: "move", x: event.screenX, y: event.screenY };
  };

  const startResize = (edge: string, event: React.MouseEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    setContextMenu(null);
    setAppearanceOpen(false);
    dragRef.current = { mode: "resize", edge, x: event.screenX, y: event.screenY };
  };

  const resetWidgetPosition = async () => {
    await fetch("/api/window-action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "reset-widget-position" })
    });
    setContextMenu(null);
  };

  return (
    <main
      className={`widget-shell theme-${settings.widget_theme}`}
      style={widgetStyle}
      onClick={() => {
        setContextMenu(null);
        setAppearanceOpen(false);
      }}
      onContextMenu={(event) => {
        event.preventDefault();
        setContextMenu({ x: event.clientX, y: event.clientY });
      }}
    >
      <section className="widget-card" ref={cardRef} onMouseDown={startDrag}>
        {["top", "right", "bottom", "left", "top-left", "top-right", "bottom-left", "bottom-right"].map((edge) => (
          <div
            key={edge}
            className={`widget-resize-handle ${edge}`}
            onMouseDown={(event) => startResize(edge, event)}
            aria-hidden="true"
          />
        ))}
        <header className="widget-top">
          <div>
            <div className="widget-title">Codex 用量</div>
            <div className="widget-time">{lastUpdated ? `${formatClock(lastUpdated)} 更新` : loading ? "读取中" : "待刷新"}</div>
          </div>
          <div className="widget-actions">
            <button className="widget-icon-button" onClick={() => load({ visible: true })} aria-label="刷新">
              <RefreshCcw size={15} className={refreshing ? "spinning" : ""} />
            </button>
            <button
              className="widget-icon-button"
              onClick={(event) => {
                event.stopPropagation();
                setAppearanceOpen((open) => !open);
              }}
              aria-label="外观"
            >
              <Palette size={15} />
            </button>
            <button className="widget-icon-button" onClick={() => setWindowMode("main")} aria-label="展开">
              <Maximize2 size={15} />
            </button>
          </div>
        </header>

        <div className="widget-periods">
          {periods.map((item) => (
            <button
              key={item.value}
              className={settings.widget_period === item.value ? "active" : ""}
              onClick={() => saveSettings({ widget_period: item.value })}
            >
              {item.label}
            </button>
          ))}
        </div>

        {settings.widget_show_items.tokens ? (
          <div className="widget-total">
            <span>真实消耗 Tokens</span>
            <strong>{formatCompact(summary.totalTokens)}</strong>
          </div>
        ) : null}

        {statItems.length > 0 ? (
          <div className="widget-stats">
            {statItems.map((item) => (
              <WidgetStat key={item.label} label={item.label} value={item.value} />
            ))}
          </div>
        ) : null}

        {settings.widget_show_items.token_split ? (
          <div className="widget-token-chart">
            <div className="widget-token-bar">
              {tokenSplit.map((item) => (
                <span key={item.key} className={`token-${item.key}`} style={{ width: `${item.percent}%` }} />
              ))}
            </div>
            <p>
              {tokenSplit.map((item) => (
                <span key={item.key}>
                  {item.label} <strong>{formatCompact(item.value)}</strong>
                </span>
              ))}
            </p>
          </div>
        ) : null}

        {appearanceOpen ? (
          <div className="appearance-panel" onClick={(event) => event.stopPropagation()}>
            <div className="appearance-row">
              <span>背景透明度</span>
              <strong>{Math.round(settings.widget_opacity * 100)}%</strong>
            </div>
            <input
              type="range"
              min="20"
              max="100"
              value={Math.round(settings.widget_opacity * 100)}
              onChange={(event) => saveSettings({ widget_opacity: Number(event.target.value) / 100 })}
            />
            <div className="appearance-row">
              <span>背景质感</span>
              <select value={settings.widget_theme} onChange={(event) => saveSettings({ widget_theme: event.target.value as WidgetTheme })}>
                <option value="glass">玻璃</option>
                <option value="frosted">磨砂</option>
                <option value="light">浅色</option>
                <option value="dark">深色</option>
              </select>
            </div>
            <div className="appearance-checks">
              <label><input type="checkbox" checked={settings.widget_show_items.tokens} onChange={(event) => changeShowItem("tokens", event.target.checked)} /> Tokens</label>
              <label><input type="checkbox" checked={settings.widget_show_items.requests} onChange={(event) => changeShowItem("requests", event.target.checked)} /> 请求数</label>
              <label><input type="checkbox" checked={settings.widget_show_items.cost} onChange={(event) => changeShowItem("cost", event.target.checked)} /> 成本</label>
              <label><input type="checkbox" checked={settings.widget_show_items.cache_rate} onChange={(event) => changeShowItem("cache_rate", event.target.checked)} /> 缓存率</label>
              <label><input type="checkbox" checked={settings.widget_show_items.token_split} onChange={(event) => changeShowItem("token_split", event.target.checked)} /> Token 分布</label>
            </div>
          </div>
        ) : null}
        {contextMenu ? (
          <div className="widget-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
            <button onClick={() => load({ visible: true })}>刷新</button>
            <button onClick={() => setWindowMode("main")}>展开主窗口</button>
            <button onClick={resetWidgetPosition}>位置恢复</button>
          </div>
        ) : null}
      </section>
    </main>
  );
}

function WidgetStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Panel({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <motion.section className="panel" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <div className="panel-head">
        <h2>{title}</h2>
        <div>{right}</div>
      </div>
      {children}
    </motion.section>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <motion.div className="metric-card" whileHover={{ y: -3 }}>
      <span>{label}</span>
      <strong>{value}</strong>
    </motion.div>
  );
}

function SmallStat({
  label,
  value,
  accent = false,
  onClick
}: {
  label: string;
  value: string;
  accent?: boolean;
  onClick?: () => void;
}) {
  return (
    <div className="small-stat">
      <span>{label}</span>
      {onClick ? (
        <button className="stat-link" onClick={onClick}>{value}</button>
      ) : (
        <strong className={accent ? "accent" : ""}>{value}</strong>
      )}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="empty chart-empty">
      <Sparkles size={18} />
      {text}
    </div>
  );
}

function PriceModal({
  models,
  value,
  onChange,
  onClose
}: {
  models: string[];
  value: PriceConfig;
  onChange: (value: PriceConfig) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<PriceDraft>(() => createPriceDraft(models, value));
  const changedRef = useRef(false);

  useEffect(() => {
    changedRef.current = false;
    setDraft(createPriceDraft(models, value));
  }, [models]);

  useEffect(() => {
    if (!changedRef.current) return;
    const timer = window.setTimeout(() => {
      onChange(priceConfigFromDraft(models, draft));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [draft, models]);

  const update = (model: string, key: "input" | "cached" | "output", raw: string) => {
    if (!isDecimalInput(raw)) return;
    changedRef.current = true;
    setDraft({
      ...draft,
      [model]: {
        input: draft[model]?.input ?? "",
        cached: draft[model]?.cached ?? "",
        output: draft[model]?.output ?? "",
        [key]: raw
      }
    });
  };

  const close = () => {
    onChange(priceConfigFromDraft(models, draft));
    onClose();
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <motion.div className="price-modal" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
        <div className="modal-head">
          <div>
            <h2>模型价格配置</h2>
            <p>单位为美元 / 100 万 tokens。缓存输入可单独设置折扣价。</p>
          </div>
          <button className="ghost-button" onClick={close}>完成</button>
        </div>
        <div className="price-grid">
          <div>模型</div>
          <div>输入</div>
          <div>缓存输入</div>
          <div>输出</div>
          {models.map((item) => (
            <React.Fragment key={item}>
              <strong>{item}</strong>
              <input inputMode="decimal" value={draft[item]?.input ?? ""} onChange={(event) => update(item, "input", event.target.value)} placeholder="请输入" />
              <input inputMode="decimal" value={draft[item]?.cached ?? ""} onChange={(event) => update(item, "cached", event.target.value)} placeholder="请输入" />
              <input inputMode="decimal" value={draft[item]?.output ?? ""} onChange={(event) => update(item, "output", event.target.value)} placeholder="请输入" />
            </React.Fragment>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

function priceConfigFromDraft(models: string[], draft: PriceDraft): PriceConfig {
  return Object.fromEntries(
    models.map((model) => [
      model,
      {
        input: parsePrice(draft[model]?.input ?? ""),
        cached: parsePrice(draft[model]?.cached ?? ""),
        output: parsePrice(draft[model]?.output ?? "")
      }
    ])
  );
}

function createPriceDraft(models: string[], value: PriceConfig): PriceDraft {
  return Object.fromEntries(
    models.map((model) => [
      model,
      {
        input: formatPriceInput(value[model]?.input),
        cached: formatPriceInput(value[model]?.cached),
        output: formatPriceInput(value[model]?.output)
      }
    ])
  );
}

function formatPriceInput(value: number | undefined) {
  return value === undefined || value === 0 ? "" : String(value);
}

function isDecimalInput(value: string) {
  return /^\d*(?:\.\d*)?$/.test(value);
}

function parsePrice(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function summarize(records: UsageRecord[], priceConfig: PriceConfig) {
  return records.reduce(
    (acc, record) => {
      acc.requests += 1;
      acc.promptTokens += record.prompt_tokens;
      acc.completionTokens += record.completion_tokens;
      acc.totalTokens += record.total_tokens;
      acc.cachedTokens += record.cached_tokens;
      acc.totalCost += computeRecordCost(record, priceConfig);
      acc.hasPricing = acc.hasPricing || hasModelPricing(record.model, priceConfig);
      return acc;
    },
    { requests: 0, promptTokens: 0, completionTokens: 0, totalTokens: 0, cachedTokens: 0, totalCost: 0, hasPricing: false }
  );
}

function buildTrend(records: UsageRecord[], hourly: boolean) {
  const map = new Map<string, number>();
  records.forEach((record) => {
    const time = new Date(record.timestamp);
    const key = hourly
      ? time.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).replace(/\d{2}$/, "00")
      : time.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
    map.set(key, (map.get(key) ?? 0) + record.total_tokens);
  });
  return [...map.entries()].map(([date, tokens]) => ({ date, tokens }));
}

function isHourlyTrend(period: Period, startDate: string, endDate: string) {
  if (period === "today") return true;
  if (period !== "date" || !startDate || !endDate) return false;
  return localDateStart(startDate).getTime() === localDateStart(endDate).getTime();
}

function buildModelShare(records: UsageRecord[]) {
  const map = new Map<string, number>();
  records.forEach((record) => map.set(record.model, (map.get(record.model) ?? 0) + record.total_tokens));
  return [...map.entries()].map(([model, tokens]) => ({ model, tokens }));
}

function formatNumber(value: number) {
  return Math.round(value).toLocaleString("en-US");
}

function formatCompact(value: number) {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(2)} 亿`;
  if (value >= 10_000) return `${(value / 10_000).toFixed(1)} 万`;
  return formatNumber(value);
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
}

function formatClock(value: Date) {
  return value.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
}

function periodLabel(value: Period) {
  if (value === "date") return "指定区间";
  return periods.find((period) => period.value === value)?.label ?? "全部";
}

function buildPageItems(current: number, total: number, compact = false): Array<number | "ellipsis"> {
  if (compact) {
    if (total <= 5) return Array.from({ length: total }, (_, index) => index + 1);
    if (current <= 2) return [1, 2, "ellipsis", total];
    if (current >= total - 1) return [1, "ellipsis", total - 1, total];
    return [1, "ellipsis", current, "ellipsis", total];
  }
  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1);
  }
  if (current <= 4) {
    return [1, 2, 3, 4, "ellipsis", total - 1, total];
  }
  if (current >= total - 3) {
    return [1, 2, "ellipsis", total - 3, total - 2, total - 1, total];
  }
  return [1, "ellipsis", current - 1, current, current + 1, "ellipsis", total];
}

function localDateStart(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function computeRecordCost(record: UsageRecord, priceConfig: PriceConfig) {
  const price = priceConfig[record.model];
  if (!price) return 0;
  const cached = Math.min(record.cached_tokens, record.prompt_tokens);
  const uncachedInput = Math.max(record.prompt_tokens - cached, 0);
  return (uncachedInput * price.input + cached * price.cached + record.completion_tokens * price.output) / 1_000_000;
}

function hasModelPricing(model: string, priceConfig: PriceConfig) {
  const price = priceConfig[model];
  return !!price && (price.input > 0 || price.cached > 0 || price.output > 0);
}

function loadPriceConfig(): PriceConfig {
  try {
    return JSON.parse(localStorage.getItem("codex-usage-prices") ?? "{}");
  } catch {
    return {};
  }
}

async function loadSavedPriceConfig(): Promise<PriceConfig> {
  try {
    const response = await fetch("/api/prices");
    if (!response.ok) return loadPriceConfig();
    const payload = await response.json();
    const prices = payload?.prices;
    if (prices && typeof prices === "object") {
      localStorage.setItem("codex-usage-prices", JSON.stringify(prices));
      return prices;
    }
  } catch {
    return loadPriceConfig();
  }
  return loadPriceConfig();
}

function readUsageCache(): UsageCache | null {
  try {
    const payload = JSON.parse(localStorage.getItem(usageCacheKey) ?? "null");
    if (!payload?.payload?.records || !payload?.updated_at) return null;
    return payload;
  } catch {
    return null;
  }
}

function writeUsageCache(payload: ApiPayload, updatedAt: Date) {
  try {
    localStorage.setItem(
      usageCacheKey,
      JSON.stringify({
        payload,
        updated_at: updatedAt.toISOString()
      })
    );
  } catch {
    // Local cache is only an optimization for smoother mode switching.
  }
}

function isFreshUsageCache(cache: UsageCache) {
  return Date.now() - new Date(cache.updated_at).getTime() < 30_000;
}

function readWidgetSettingsCache(): WidgetSettings {
  if (window.__CODEX_WINDOW_SETTINGS__) {
    return normalizeWidgetSettings(window.__CODEX_WINDOW_SETTINGS__);
  }
  try {
    return normalizeWidgetSettings(JSON.parse(localStorage.getItem(widgetSettingsCacheKey) ?? "null") ?? undefined);
  } catch {
    return defaultWidgetSettings;
  }
}

function writeWidgetSettingsCache(settings: WidgetSettings) {
  try {
    localStorage.setItem(widgetSettingsCacheKey, JSON.stringify(normalizeWidgetSettings(settings)));
  } catch {
    // Appearance cache only prevents a visible default-state flash.
  }
}

function savePriceConfig(value: PriceConfig) {
  const pruned = prunePriceConfig(value);
  localStorage.setItem("codex-usage-prices", JSON.stringify(pruned));
  fetch("/api/prices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prices: pruned })
  }).catch(() => undefined);
}

function prunePriceConfig(value: PriceConfig): PriceConfig {
  return Object.fromEntries(
    Object.entries(value).filter(([, price]) => price.input > 0 || price.cached > 0 || price.output > 0)
  );
}

function filterByPeriod(records: UsageRecord[], period: Period) {
  const now = new Date();
  const start =
    period === "today"
      ? new Date(now.getFullYear(), now.getMonth(), now.getDate())
      : period === "7d"
        ? new Date(now.getTime() - 7 * 86400_000)
        : period === "30d"
          ? new Date(now.getTime() - 30 * 86400_000)
          : null;
  return start ? records.filter((record) => new Date(record.timestamp) >= start) : records;
}

function normalizeWidgetSettings(value: Partial<WidgetSettings> | undefined): WidgetSettings {
  const source = value ?? {};
  return {
    mode: source.mode === "widget" ? "widget" : "main",
    widget_period: periods.some((period) => period.value === source.widget_period)
      ? (source.widget_period as Period)
      : defaultWidgetSettings.widget_period,
    widget_opacity: Math.min(Math.max(Number(source.widget_opacity ?? defaultWidgetSettings.widget_opacity), 0.2), 1),
    widget_theme: ["glass", "frosted", "light", "dark"].includes(String(source.widget_theme))
      ? (source.widget_theme as WidgetTheme)
      : defaultWidgetSettings.widget_theme,
    widget_compact: false,
    widget_show_items: {
      ...defaultWidgetSettings.widget_show_items,
      ...(source.widget_show_items ?? {})
    }
  };
}

async function saveWindowSettings(settings: WidgetSettings) {
  writeWidgetSettingsCache(settings);
  await fetch("/api/window-settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings })
  });
}

async function setWindowMode(mode: "main" | "widget") {
  await fetch("/api/window-mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode })
  });
}

createRoot(document.getElementById("root")!).render(
  window.location.pathname.startsWith("/widget") ? <WidgetApp /> : <App />
);
