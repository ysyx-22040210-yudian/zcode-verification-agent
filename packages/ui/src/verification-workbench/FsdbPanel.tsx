import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button.js";
import { usePlatform } from "@/hooks/usePlatform.js";
import { useZCodeIntl } from "@/i18n/IntlProvider.js";
import type { FsdbFileList, FsdbJob, FsdbRequest, VerificationFrameProps } from "./contract.js";
import { useDesignQueryService } from "./useVerificationService.js";

const field = "min-w-0 rounded-md border border-border bg-input px-2 py-1.5 text-ui-sm text-foreground";
const label = "flex min-w-0 flex-col gap-1 text-ui-xs text-foreground-muted";
type Trigger = NonNullable<FsdbRequest["trigger"]>;

export function FsdbPanel({ workspace, initialPath }: VerificationFrameProps & { initialPath?: string }) {
  const service = useDesignQueryService();
  const platform = usePlatform();
  const zh = useZCodeIntl().locale.startsWith("zh");
  const picker = useRef<HTMLInputElement>(null);
  const generation = useRef({ id: 0 });
  const [files, setFiles] = useState<FsdbFileList>();
  const [file, setFile] = useState(initialPath ?? "");
  const [pattern, setPattern] = useState("");
  const [catalog, setCatalog] = useState<FsdbJob>();
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<"range" | "trigger">("range");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [signal, setSignal] = useState("");
  const [edge, setEdge] = useState<Trigger["edge"]>("rising");
  const [from, setFrom] = useState("0");
  const [before, setBefore] = useState("10");
  const [after, setAfter] = useState("10");
  const [receipt, setReceipt] = useState<FsdbJob>();
  const [view, setView] = useState<{ id: string; html: string }>();
  const [id, setId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const t = (cn: string, en: string) => zh ? cn : en;

  useEffect(() => {
    const requests = generation.current;
    let mounted = true;
    if (service) void service.listFsdb(workspace).then((list) => {
      if (!mounted) return;
      setFiles(list);
      if (!initialPath && list.files.length === 1) setFile((value) => value || list.files[0]!.path);
    }).catch((err: unknown) => { if (mounted) setError(String(err)); });
    return () => { mounted = false; requests.id++; };
  }, [service, workspace, initialPath]);

  function chooseFile(path: string) {
    generation.current.id++;
    setBusy(false); setError(""); setFile(path); setCatalog(undefined); setView(undefined); setReceipt(undefined);
    setSelected([]); setSignal(""); setId(""); setStart(""); setEnd("");
  }
  function pick(name: string) {
    setSelected((current) => current.includes(name) ? current.filter((n) => n !== name) : [...current, name]);
  }
  function restore(query: FsdbRequest) {
    setFile(query.file); setPattern(query.pattern ?? "");
    if (query.operation !== "wave") return;
    setSelected([...(query.signals ?? [])]); setStart(query.start ?? ""); setEnd(query.end ?? "");
    setMode(query.trigger ? "trigger" : "range"); setSignal(query.trigger?.signal ?? "");
    setEdge(query.trigger?.edge ?? "rising"); setFrom(query.trigger?.from ?? "0");
    setBefore(query.trigger?.before ?? "10"); setAfter(query.trigger?.after ?? "10");
  }
  async function run(action: () => Promise<FsdbJob>, reopen = false) {
    if (!service) return;
    const version = ++generation.current.id;
    setBusy(true); setError(""); setView(undefined); setReceipt(undefined);
    try {
      let job = await action();
      if (version !== generation.current.id) return;
      if (reopen) {
        if (catalog?.query.fingerprint !== job.query.fingerprint) { setCatalog(undefined); setSelected([]); setSignal(""); }
        restore(job.query);
      }
      setReceipt(job); setId(job.id);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 450));
        if (version !== generation.current.id) return;
        job = await service.getFsdb(workspace, job.id);
        if (version !== generation.current.id) return;
        setReceipt(job);
      }
      if (job.status !== "complete") throw new Error(job.message || job.status);
      if (job.query.operation === "signals") {
        if (catalog && catalog.query.fingerprint !== job.query.fingerprint) setSelected([]);
        setCatalog(job);
      } else if (job.result?.outcome === "ok") {
        const document = await service.fsdbViewer(workspace, job.id);
        if (version === generation.current.id) setView({ id: job.id, html: document.html });
      }
    } catch (err) {
      if (version === generation.current.id) setError(String(err));
    } finally {
      if (version === generation.current.id) setBusy(false);
    }
  }
  function search() {
    if (service) void run(() => service.startFsdb(workspace, { operation: "signals", file, pattern: pattern.trim() || "*" }));
  }
  function extract() {
    if (!service) return;
    const source = { file, signals: selected, fingerprint: catalog?.query.fingerprint };
    const interval = mode === "range" ? { start: start || undefined, end: end || undefined } :
      { trigger: { signal: signal || selected[0] || "", edge, from: from || "0", before: before || "0", after: after || "0" } };
    void run(() => service.startFsdb(workspace, { operation: "wave", ...source, ...interval }));
  }
  const matches = catalog?.result?.signals ?? [];
  const meta = catalog?.result ?? receipt?.result;
  const outcome = receipt?.result?.outcome;
  const message = outcome === "no_trigger" ? t("指定条件在记录中没有触发。", "No matching recorded transition.") :
    outcome === "trigger_limit" ? t("已到达搜索上限，可从后续时间继续。", "Trigger scan limit reached.") + " " + (receipt?.result?.searchedThrough ?? "") :
    outcome === "outside_range" ? t("所选区间在文件记录范围以外。", "Interval outside the recorded range.") : "";
  return <main className="flex h-full min-h-0 flex-col overflow-auto bg-background text-foreground" data-testid="fsdb-panel">
    <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border px-4 py-3">
      <div><h1 className="text-ui-xl font-semibold">{t("FSDB 波形", "FSDB waveforms")}</h1>
        {meta && <div className="mt-1 font-mono text-ui-xs text-foreground-muted">{meta.minTime} – {meta.maxTime} ticks · 1 tick = {meta.scale}</div>}
      </div>
      <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (service) void run(() => service.getFsdb(workspace, id.trim()), true); }}>
        <label className={label}>{t("按查询 ID 打开", "Open query by ID")}<input className={field + " w-64 max-w-full font-mono"} data-testid="fsdb-job-input" value={id} onChange={(e) => setId(e.target.value)} /></label>
        <Button size="sm" type="submit" variant="outline" disabled={!service || !id.trim() || busy} data-testid="fsdb-reopen">{t("打开", "Open")}</Button>
      </form>
    </header>
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(15rem,21rem)_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col gap-3 overflow-auto border-b border-border p-4 lg:border-b-0 lg:border-r">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); search(); }}>
          <label className={label}>{t("FSDB 文件", "FSDB file")}<input required data-testid="fsdb-path" className={field} list="fsdb-file-options" value={file} placeholder="demo.fsdb" onChange={(e) => chooseFile(e.target.value)} /></label>
          <datalist id="fsdb-file-options">{files?.files.map((item) => <option key={item.path} value={item.path}>{item.label}</option>)}</datalist>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => picker.current?.click()}>{t("选择文件…", "Choose file…")}</Button>
            <input ref={picker} type="file" accept=".fsdb" className="hidden" onChange={(e) => {
              const chosen = e.target.files?.[0]; e.target.value = "";
              if (!chosen) return;
              const path = platform?.getPathForFile?.(chosen);
              if (path) chooseFile(path); else setError(t("请填写 VM 上的文件路径。", "Enter the path on the VM."));
            }} />
            {files?.truncated && <span className="text-ui-xs text-foreground-muted">{t("文件列表不完整", "File list incomplete")}</span>}
          </div>
          <label className={label}>{t("信号名或层次匹配", "Signal name or hierarchy pattern")}<input className={field} value={pattern} placeholder="*valid*" onChange={(e) => setPattern(e.target.value)} /></label>
          <Button type="submit" size="sm" disabled={!service || !file.trim() || busy} data-testid="fsdb-search">{t("查找信号", "Find signals")}</Button>
        </form>
        {catalog && <section className="min-h-0 space-y-1">
          <h2 className="text-ui-base font-semibold">{t("已记录信号", "Recorded signals")} ({matches.length}{catalog.result?.truncated ? "+" : ""})</h2>
          {catalog.result?.truncated && <p className="text-ui-xs text-foreground-muted">{t("缩小匹配范围可以查看更多信号。", "Narrow the pattern to see more signals.")}</p>}
          {!matches.length && <p className="text-ui-sm">{t("没有匹配的信号", "No matching signals")}</p>}
          {matches.map((item) => <label key={item.name} className="flex items-center gap-2 py-1 text-ui-sm">
            <input type="checkbox" aria-label={item.name} checked={selected.includes(item.name)}
              disabled={!selected.includes(item.name) && selected.length >= 16} onChange={() => pick(item.name)} />
            <span className="break-all font-mono">{item.name}</span><span className="ml-auto text-ui-xs text-foreground-muted">{item.width}b</span>
          </label>)}
        </section>}
      </aside>
      <section className="flex min-h-0 min-w-0 flex-col gap-3 overflow-auto p-4">
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); extract(); }}>
          <label className={label}>{t("时间窗口", "Time window")}<select className={field} value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
            <option value="range">{t("时间区间", "Time interval")}</option><option value="trigger">{t("触发前后", "Around a trigger")}</option></select></label>
          {mode === "range" ? (<>
            <label className={label}>{t("起点", "Start")}<input className={field + " w-28"} inputMode="numeric" pattern="[0-9]*" value={start} placeholder={meta?.minTime ?? "0"} onChange={(e) => setStart(e.target.value)} /></label>
            <label className={label}>{t("终点", "End")}<input className={field + " w-28"} inputMode="numeric" pattern="[0-9]*" value={end} placeholder={meta?.maxTime ?? t("文件末尾", "File end")} onChange={(e) => setEnd(e.target.value)} /></label>
          </>) : (<>
            <label className={label}>{t("触发信号", "Trigger signal")}<input className={field} value={signal} placeholder={selected[0]} list="fsdb-selected" onChange={(e) => setSignal(e.target.value)} /></label>
            <datalist id="fsdb-selected">{[...new Set([...selected,...matches.map((item) => item.name)])].map((name) => <option key={name} value={name} />)}</datalist>
            <label className={label}>{t("条件", "Edge")}<select className={field} value={edge} onChange={(e) => setEdge(e.target.value as Trigger["edge"])}>
              <option value="rising">{t("上升沿", "Rising")}</option><option value="falling">{t("下降沿", "Falling")}</option><option value="change">{t("任意变化", "Any change")}</option>
            </select></label>
            {[[t("搜索起点", "Search from"), from, setFrom],[t("提前 ticks", "Ticks before"), before, setBefore],[t("延后 ticks", "Ticks after"), after, setAfter]].map((entry) => {
              const [caption, value, setter] = entry as [string, string, (value: string) => void];
              return <label className={label} key={caption}>{caption}<input className={field + " w-24"} inputMode="numeric" pattern="[0-9]*" value={value} onChange={(e) => setter(e.target.value)} /></label>;
            })}
          </>)}
          <Button type="submit" size="sm" data-testid="fsdb-read" disabled={!service || !file || !selected.length || busy}>{t("提取波形", "Extract wave")} ({selected.length})</Button>
        </form>
        {selected.length > 0 && <div className="flex flex-wrap gap-1">{selected.map((name) => <button type="button" key={name} title={t("移除信号", "Remove signal")}
          className="rounded border border-border px-2 py-0.5 font-mono text-ui-xs" onClick={() => pick(name)}>{name} ×</button>)}</div>}
        {error && <pre role="alert" className="whitespace-pre-wrap break-all text-ui-sm">{error}</pre>}
        {message && <p role="status" className="text-ui-sm">{message}</p>}
        {receipt && <div className="flex flex-wrap items-center gap-2 text-ui-xs text-foreground-muted">
          <code data-testid="fsdb-job-id">{receipt.id}</code>{busy && <span>{t("正在读取…", "Reading…")}</span>}
          {view && platform?.openFsdbWaveform && <Button type="button" size="sm" variant="outline" data-testid="fsdb-detach" onClick={() => {
            void platform.openFsdbWaveform?.(workspace, view.id).catch((err: unknown) => setError(String(err)));
          }}>{t("独立波形窗口", "Open separate window")}</Button>}
        </div>}
        {view && <iframe key={view.id} data-testid="fsdb-plot" title={t("FSDB 波形窗口", "FSDB waveform window")} sandbox="allow-scripts"
          srcDoc={view.html} className="min-h-96 w-full flex-1 rounded-md border border-border" />}
      </section>
    </div>
  </main>;
}

