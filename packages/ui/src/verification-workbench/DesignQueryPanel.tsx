import { useEffect, useRef, useState } from "react";
import { usePlatform } from "@/hooks/usePlatform.js";
import { Button } from "@/components/ui/button.js";
import { useZCodeIntl } from "@/i18n/IntlProvider.js";
import type { DesignQueryJob, DesignQueryRequest, VerificationFrameProps } from "./contract.js";
import { DesignQueryResults } from "./DesignQueryResults.js";
import { useDesignQueryService } from "./useVerificationService.js";

const field = "min-w-0 rounded-md border border-border bg-input px-2 py-1 text-ui-sm text-foreground";
const label = "flex min-w-0 flex-col gap-1 text-ui-xs text-foreground-muted";

export function DesignQueryPanel({ workspace }: VerificationFrameProps) {
  const service = useDesignQueryService();
  const platform = usePlatform();
  const filePicker = useRef<HTMLInputElement>(null);
  const zh = useZCodeIntl().locale.startsWith("zh");
  const [operation, setOperation] = useState<DesignQueryRequest["operation"]>("instances");
  const [kdb, setKdb] = useState("");
  const [pattern, setPattern] = useState("");
  const [instance, setInstance] = useState("");
  const [scope, setScope] = useState("");
  const [signal, setSignal] = useState("");
  const [direction, setDirection] = useState<NonNullable<DesignQueryRequest["direction"]>>("both");
  const [lookup, setLookup] = useState("");
  const [job, setJob] = useState<DesignQueryJob>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const pendingId = job?.status === "queued" || job?.status === "running" ? job.id : undefined;

  useEffect(() => () => { generation.current++; }, []);
  useEffect(() => {
    if (!service || !pendingId || busy) return;
    const read = () => service.get(workspace, pendingId);
    const version = generation.current;
    let closed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await read();
        if (closed || version !== generation.current) return;
        setJob(next);
        if (next.status === "queued" || next.status === "running") timer = setTimeout(poll, 800);
      } catch (err) {
        if (!closed && version === generation.current) setError(String(err));
      }
    }
    timer = setTimeout(poll, 250);
    return () => { closed = true; clearTimeout(timer); };
  }, [busy, pendingId, service, workspace]);

  function restoreInputs(query: DesignQueryJob["query"]) {
    const relative = (path = "") => path.startsWith(workspace + "/") ? path.slice(workspace.length + 1) : path;
    setOperation(query.operation);
    setKdb(relative(query.kdb));
    setPattern(query.definition === "*" ? "" : query.definition || "");
    setInstance(query.instance === "*" ? "" : query.instance || "");
    setScope(query.scope || "");
    setSignal(query.signal || "");
    setDirection(query.direction || "both");
  }

  async function select(load: () => Promise<DesignQueryJob>, restore = false) {
    const version = ++generation.current;
    setBusy(true);
    setError("");
    setJob(undefined);
    try {
      const next = await load();
      if (version === generation.current) {
        setJob(next);
        setLookup(next.id);
        if (restore) restoreInputs(next.query);
      }
    } catch (err) {
      if (version === generation.current) setError(String(err));
    } finally {
      if (version === generation.current) setBusy(false);
    }
  }

  function start() {
    if (!service || !kdb.trim()) return;
    const query = operation === "signal" ? { signal, direction } : { definition: pattern || "*", instance: instance || "*", scope };
    void select(() => service.start(workspace, { operation, kdb: kdb.trim(), ...query }));
  }
  return (
    <main className="flex h-full min-h-0 flex-col overflow-y-auto bg-background text-foreground" data-testid="design-query-panel">
      <header className="border-b border-border px-5 py-4">
        <h1 className="text-ui-xl font-semibold">{zh ? "RTL 查询" : "RTL query"}</h1>
        <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); start(); }}>
          <label className={label}>{zh ? "已编译的 KDB 路径" : "Compiled KDB path"}
            <input required className={field + " w-72 max-w-full"} value={kdb} data-testid="design-query-kdb"
              placeholder="build/simv.daidir/simv.kdb" onChange={(event) => setKdb(event.target.value)} />
          </label>
          {platform.getPathForFile && (<>
            <input type="file" ref={filePicker} accept=".kdb" className="hidden" onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              event.currentTarget.value = "";
              if (!file) return;
              const path = platform.getPathForFile?.(file);
              if (path) { setKdb(path); setError(""); }
              else setError(zh ? "请填写 KDB 在虚拟机中的路径。" : "Enter the KDB path on the VM.");
            }} />
            <Button type="button" size="sm" variant="outline" data-testid="design-query-browse" onClick={() => filePicker.current?.click()}>
              {zh ? "选择 KDB 文件" : "Choose KDB file"}
            </Button>
          </>)}
          <label className={label}>{zh ? "查询类型" : "Query type"}
            <select className={field} value={operation} data-testid="design-query-operation" onChange={(e) => setOperation(e.target.value as DesignQueryRequest["operation"])}>
              <option value="instances">{zh ? "Module 实例" : "Module instances"}</option><option value="signal">{zh ? "信号连接" : "Signal connectivity"}</option>
            </select>
          </label>
          {operation === "instances" ? (<>
            <label className={label}>{zh ? "模块定义" : "Module definition"}<input className={field} data-testid="design-query-pattern" value={pattern} placeholder="*" onChange={(e) => setPattern(e.target.value)} /></label>
            <label className={label}>{zh ? "实例路径模式" : "Instance path pattern"}<input className={field} value={instance} placeholder="*" onChange={(e) => setInstance(e.target.value)} /></label>
            <label className={label}>{zh ? "限定层次" : "Within hierarchy"}<input className={field} value={scope} onChange={(e) => setScope(e.target.value)} /></label>
          </>) : (<>
            <label className={label}>{zh ? "信号层次路径" : "Hierarchical signal"}<input required className={field + " w-72 max-w-full"} data-testid="design-query-signal" value={signal} placeholder="top.u_tx.port.valid" onChange={(e) => setSignal(e.target.value)} /></label>
            <label className={label}>{zh ? "方向" : "Direction"}<select className={field} value={direction} onChange={(e) => setDirection(e.target.value as typeof direction)}>
              <option value="both">Driver + Load</option><option value="driver">Driver</option><option value="load">Load</option>
            </select></label>
          </>)}
          <Button size="sm" type="submit" data-testid="design-query-start" disabled={!service || busy || !kdb.trim()}>{zh ? "查询" : "Run query"}</Button>
        </form>
      </header>
      <section className="space-y-4 px-5 py-4">
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (service) void select(() => service.get(workspace, lookup.trim()), true); }}>
          <label className={label}>{zh ? "按查询 ID 打开" : "Open query by ID"}<input className={field + " w-72 max-w-full font-mono"} value={lookup} onChange={(e) => setLookup(e.target.value)} /></label>
          <Button size="sm" type="submit" variant="outline" disabled={!service || busy || !lookup.trim()}>{zh ? "打开" : "Open"}</Button>
        </form>
        {error && <p role="alert" className="break-words text-ui-sm">{error}</p>}
        {job && <DesignQueryResults job={job} zh={zh} />}
      </section>
    </main>
  );
}

