import type { DesignQueryJob } from "./contract.js";

type Result = NonNullable<DesignQueryJob["result"]>;
const mono = "break-all font-mono text-ui-sm";
const styles = "rounded-lg border border-border bg-surface px-3 py-2";
const source = (file: string, line: number) => file ? file + (line ? ":" + line : "") : "—";

function Endpoints({ title, side, result }: { title: string; side: "drivers" | "loads"; result: Result }) {
  return <section className={styles} data-testid={"design-query-" + side}>
    <h3 className="text-ui-base font-semibold">{title} ({result.totals[side]})</h3>
    <ul className="divide-y divide-border">{result[side].map((row, i) => (
      <li key={i} className="space-y-1 py-2">
        <p className={mono}>{row.scope}</p>
        <p className="break-all text-ui-xs text-foreground-muted">{row.kind} · {source(row.file, row.line)}</p>
        {row.related.length > 0 && <p className={mono}>{row.related.join(", ")}</p>}
      </li>
    ))}</ul>
  </section>;
}

export function DesignQueryResults({ job, zh }: { job: DesignQueryJob; zh: boolean }) {
  const result = job.result;
  const outcomes = { ok: zh ? "查询完成" : "Complete", partial: zh ? "部分结果" : "Partial results",
    no_matches: zh ? "没有匹配的实例" : "No matching instances", not_found: zh ? "找不到该信号" : "Signal not found",
    unsupported: zh ? "此对象不支持静态查询" : "Unsupported static object" };
  const status = { queued: zh ? "排队中" : "Queued", running: zh ? "查询中" : "Running",
    complete: zh ? "已完成" : "Complete", tool_error: zh ? "工具错误" : "Tool error",
    license_error: zh ? "许可证错误" : "License error", timeout: zh ? "超时" : "Timed out",
    interrupted: zh ? "已中断" : "Interrupted" };
  return <article className="space-y-3" data-testid="design-query-result">
    <div className="flex flex-wrap items-baseline gap-3">
      <h2 className="text-ui-lg font-semibold">{result ? outcomes[result.outcome] : status[job.status]}</h2>
      <code className="break-all text-ui-xs text-foreground-muted" data-testid="design-query-job-id">{job.id}</code>
    </div>
    <p className="break-all text-ui-xs text-foreground-muted" data-testid="design-query-source">
      {job.query.kdb ? <>KDB · <code>{job.query.kdb}</code></> : (zh ? "历史查询来源：源码展开" : "Historical query from source elaboration")}
    </p>
    {job.message && <pre className="whitespace-pre-wrap break-all text-ui-sm">{job.message}</pre>}
    {result && (<>
      {result.truncated && <p className="text-ui-sm">{zh ? "结果已截断。可缩小查询范围，或在 Agent 中调高 limit。" : "Results truncated. Narrow the query or increase the Agent limit."}</p>}
      {result.warnings.map((warning) => <p className="break-all text-ui-sm" key={warning}>{warning}</p>)}
      {job.query.operation === "instances" && result.instances.length > 0 && <section className={styles}>
        <h3 className="text-ui-base font-semibold">{zh ? "实例" : "Instances"} ({result.totals.instances})</h3>
        <ul className="divide-y divide-border">{result.instances.map((row) => <li key={row.path} className="py-2">
          <p className={mono}>{row.path}</p>
          <p className="break-all text-ui-xs text-foreground-muted">{row.definition} · {source(row.file, row.line)}</p>
          {row.definitionFile && <p className="break-all text-ui-xs text-foreground-muted">{zh ? "定义" : "Definition"} · {source(row.definitionFile, row.definitionLine)}</p>}
        </li>)}</ul>
      </section>}
      {result.signal && (<>
        <p className={mono}>{result.signal.canonical} <span className="text-ui-xs text-foreground-muted">{result.signal.kind}</span></p>
        <div className="grid gap-3 lg:grid-cols-2">
          {job.query.direction !== "load" && <Endpoints title={zh ? "驱动端 · Driver" : "Drivers"} side="drivers" result={result} />}
          {job.query.direction !== "driver" && <Endpoints title={zh ? "负载端 · Load" : "Loads"} side="loads" result={result} />}
        </div>
        {result.bindings.length > 0 && <section className={styles}>
          <h3 className="text-ui-base font-semibold">{zh ? "Interface 端口绑定" : "Interface port bindings"} ({result.totals.bindings})</h3>
          <ul>{result.bindings.map((row) => <li key={row.scope + "." + row.port} className="flex flex-wrap gap-2 py-1">
            <span className={mono}>{row.scope}.{row.port}</span>
            <span className="text-ui-sm text-foreground-muted">{row.modport || (zh ? "完整 interface" : "Full interface")} · {row.direction}</span>
          </li>)}</ul>
        </section>}
      </>)}
    </>)}
    <p className="break-all text-ui-xs text-foreground-muted">{zh ? "原始记录" : "Evidence"} · {job.evidenceDirectory}</p>
  </article>;
}

