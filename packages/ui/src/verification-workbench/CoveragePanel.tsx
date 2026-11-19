import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button.js";
import { useZCodeIntl } from "@/i18n/IntlProvider.js";
import type { CoverageFilter, CoverageJob, CoveragePage } from "./contract.js";
import { useDesignQueryService } from "./useVerificationService.js";

const field =
  "min-w-0 rounded-md border border-border bg-input px-2 py-1 text-ui-sm text-foreground";
const label = "grid gap-1 text-ui-caption text-foreground-subtle";
const zhMetric: Record<string, string> = {
  hierarchy: "实例层次",
  line: "行",
  condition: "条件",
  branch: "分支",
  toggle: "翻转",
  fsm: "FSM",
  assertion: "断言",
  functional: "功能",
  power: "低功耗",
};
const zhState: Record<string, string> = {
  covered: "已覆盖",
  missed: "未命中",
  partial: "部分覆盖",
  excluded: "已排除",
  partially_excluded: "部分排除",
  unreachable: "不可达",
  illegal: "非法",
  count_only: "仅计数",
  unmeasured: "无覆盖分母",
};
const describe = (e: unknown) => (e instanceof Error ? e.message : String(e));

function CoverageData({
  workspace,
  jobId,
  result,
  zh,
}: {
  workspace: string;
  jobId: string;
  result: NonNullable<CoverageJob["result"]>;
  zh: boolean;
}) {
  const service = useDesignQueryService();
  const firstView =
    result.views.find((v) => v.id === "merged")?.id ??
    result.views[0]?.id ??
    "";
  const [draft, setDraft] = useState({
    view: firstView,
    metric: "",
    state: "",
    search: "",
  });
  const [filter, setFilter] = useState<CoverageFilter>({ view: firstView });
  const [cursors, setCursors] = useState([0]);
  const [page, setPage] = useState<CoveragePage>();
  const [expanded, setExpanded] = useState<number>();
  const [error, setError] = useState("");
  const after = cursors[cursors.length - 1];
  const view = result.views.find((v) => v.id === draft.view);
  useEffect(() => {
    if (!service) return;
    let stale = false;
    setPage(undefined);
    setExpanded(undefined);
    setError("");
    void service
      .coverageRows(workspace, jobId, { ...filter, after, limit: 50 })
      .then((value) => {
        if (!stale) setPage(value);
      })
      .catch((e) => {
        if (!stale) setError(describe(e));
      });
    return () => {
      stale = true;
    };
  }, [service, workspace, jobId, filter, after]);
  const activeRow = page?.rows.find((row) => row.id === expanded);
  return (
    <section data-testid="coverage-ready" className="min-w-0 space-y-3">
      <p className="text-ui-sm">
        {zh ? "覆盖率记录" : "Coverage records"}{" "}
        <strong>{result.rowCount.toLocaleString()}</strong> ·{" "}
        {zh ? "源文件" : "Source files"} {result.sourceFiles}
      </p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setCursors([0]);
          setFilter({ ...draft });
        }}
      >
        <label className={label}>
          {zh ? "测试视图" : "Test view"}
          <select
            className={field}
            data-testid="coverage-view"
            value={draft.view}
            onChange={(e) =>
              setDraft({ ...draft, view: e.currentTarget.value })
            }
          >
            {result.views.map((v) => (
              <option key={v.id} value={v.id}>
                {v.id === "merged" && zh
                  ? "合并结果"
                  : v.name.split("/").at(-1) || v.id}
              </option>
            ))}
          </select>
        </label>
        <label className={label}>
          {zh ? "指标" : "Metric"}
          <select
            className={field}
            data-testid="coverage-metric"
            value={draft.metric}
            onChange={(e) =>
              setDraft({ ...draft, metric: e.currentTarget.value })
            }
          >
            <option value="">{zh ? "全部指标" : "All metrics"}</option>
            {Object.entries(zhMetric).map(([key, name]) => (
              <option key={key} value={key}>
                {zh ? name : key}
                {view?.metrics[key]
                  ? " · " + view.metrics[key].dataRecords
                  : ""}
              </option>
            ))}
          </select>
        </label>
        <label className={label}>
          {zh ? "覆盖状态" : "Coverage state"}
          <select
            className={field}
            value={draft.state}
            onChange={(e) =>
              setDraft({ ...draft, state: e.currentTarget.value })
            }
          >
            <option value="">{zh ? "全部状态" : "All states"}</option>
            {Object.entries(zhState).map(([k, v]) => (
              <option key={k} value={k}>
                {zh ? v : k.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label className={label}>
          {zh ? "层次或名称" : "Hierarchy or name"}
          <input
            className={field}
            data-testid="coverage-search"
            value={draft.search}
            onChange={(e) =>
              setDraft({ ...draft, search: e.currentTarget.value })
            }
          />
        </label>
        <Button
          type="submit"
          variant="outline"
          size="sm"
          data-testid="coverage-apply"
        >
          {zh ? "筛选" : "Filter"}
        </Button>
      </form>
      {error ? <p role="alert">{error}</p> : null}
      {page ? (
        <div className="overflow-x-auto rounded border border-border">
          <table className="w-full text-left text-ui-sm">
            <thead className="bg-surface text-foreground-subtle">
              <tr>
                {(zh
                  ? ["对象路径", "类型", "已覆盖 / 可覆盖", "命中次数", "状态"]
                  : [
                      "Object path",
                      "Kind",
                      "Covered / coverable",
                      "Hit count",
                      "State",
                    ]
                ).map((h) => (
                  <th className="p-2" key={h}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {page.rows.map((r) => (
                <tr
                  key={r.id}
                  data-testid="coverage-row"
                  className="border-t border-border hover:bg-surface"
                >
                  <td className="max-w-sm break-words p-2">
                    <button
                      type="button"
                      title={r.scope}
                      className="cursor-pointer text-left font-mono hover:underline"
                      onClick={() =>
                        setExpanded(r.id === expanded ? undefined : r.id)
                      }
                    >
                      {r.scope}
                    </button>
                  </td>
                  <td className="p-2">{r.kind}</td>
                  <td className="p-2">
                    {r.covered ?? "—"} / {r.coverable ?? "—"}
                  </td>
                  <td className="p-2">{r.count ?? "—"}</td>
                  <td className="p-2">
                    {zh
                      ? (zhState[r.state] ?? r.state)
                      : r.state.replaceAll("_", " ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!page.rows.length ? (
            <p className="p-3 text-ui-sm">
              {zh ? "没有符合条件的记录" : "No matching records"}
            </p>
          ) : null}
        </div>
      ) : !error ? (
        <p className="text-ui-sm">
          {zh ? "正在读取记录…" : "Reading records…"}
        </p>
      ) : null}
      {activeRow ? (
        <pre className="max-h-64 overflow-auto rounded border border-border p-3 text-ui-sm">
          {JSON.stringify(activeRow, null, 2)}
        </pre>
      ) : null}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={cursors.length <= 1}
          onClick={() => setCursors((c) => c.slice(0, -1))}
        >
          {zh ? "上一页" : "Previous"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={page?.nextAfter == null}
          onClick={() => {
            if (page?.nextAfter != null)
              setCursors([...cursors, page.nextAfter]);
          }}
        >
          {zh ? "下一页" : "Next"}
        </Button>
        <span className="text-ui-caption">{cursors.length}</span>
      </div>
      <details className="text-ui-sm">
        <summary className="cursor-pointer">
          {zh ? "完整导出文件" : "Full exports"}
        </summary>
        <dl className="mt-2 grid gap-1">
          {[
            [zh ? "覆盖记录 JSONL" : "Coverage JSONL", result.jsonlPath],
            ["SQLite", result.sqlitePath],
            ["VDB XML", result.xmlPath],
            [zh ? "源文件清单" : "Source manifest", result.manifestPath],
            [
              zh ? "原始 VDB 归档" : "Original VDB archive",
              result.sourceArchive,
            ],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-foreground-subtle">{k}</dt>
              <dd className="select-all break-all font-mono">{v}</dd>
            </div>
          ))}
        </dl>
        {result.xmlErrors ? (
          <p>
            {zh ? "未解析的 XML 文件数" : "Unparsed XML members"}{" "}
            {result.xmlErrors}
          </p>
        ) : null}
      </details>
    </section>
  );
}

export function CoveragePanel({
  workspace,
  runId,
  returnToTools,
  onClose,
}: {
  workspace: string;
  runId?: string;
  returnToTools?: boolean;
  onClose: () => void;
}) {
  const service = useDesignQueryService();
  const zh = useZCodeIntl().locale.startsWith("zh");
  const [path, setPath] = useState("simv.vdb");
  const [exclude, setExclude] = useState("");
  const [id, setId] = useState("");
  const [job, setJob] = useState<CoverageJob>();
  const [error, setError] = useState("");
  const sequence = useRef(0);
  useEffect(
    () => () => {
      sequence.current++;
    },
    [],
  );
  async function load(action: () => Promise<CoverageJob>) {
    if (!service) return;
    const token = ++sequence.current;
    setError("");
    setJob(undefined);
    try {
      let next = await action();
      while (token === sequence.current) {
        setJob(next);
        if (next.status !== "queued" && next.status !== "running") break;
        await new Promise((resolve) => setTimeout(resolve, 650));
        if (token !== sequence.current) return;
        next = await service.getCoverage(workspace, next.id);
      }
    } catch (e) {
      if (token === sequence.current) setError(describe(e));
    }
  }
  return (
    <main className="h-full min-h-0 space-y-4 overflow-auto bg-background p-5 text-foreground">
      <header className="flex items-center gap-3">
        <Button size="sm" variant="outline" onClick={onClose}>
          {returnToTools ? (zh ? "返回工具" : "Back to tools") : (zh ? "返回验证" : "Back to verification")}
        </Button>
        <h1 className="text-ui-xl font-semibold">
          {zh ? "覆盖率数据" : "Coverage data"}
        </h1>
      </header>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (service)
            void load(() =>
              service.startCoverage(workspace, {
                path: path.trim(),
                excludeFile: exclude.trim() || undefined,
              }),
            );
        }}
      >
        <label className={label + " min-w-56 flex-1"}>
          {zh ? "VCS 覆盖率库 (.vdb)" : "VCS coverage database (.vdb)"}
          <input
            className={field}
            data-testid="coverage-input"
            value={path}
            onChange={(e) => setPath(e.currentTarget.value)}
          />
        </label>
        <label className={label}>
          {zh ? "排除文件 (.el，可选)" : "Exclusion file (.el, optional)"}
          <input
            className={field}
            value={exclude}
            onChange={(e) => setExclude(e.currentTarget.value)}
          />
        </label>
        <Button
          size="sm"
          type="submit"
          disabled={!path.trim()}
          data-testid="coverage-extract"
        >
          {zh ? "提取全部数据" : "Extract all data"}
        </Button>
        {runId && service ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            data-testid="coverage-from-run"
            onClick={() =>
              void load(() =>
                service.startCoverage(workspace, {
                  runId,
                  excludeFile: exclude.trim() || undefined,
                }),
              )
            }
          >
            {zh ? "从所选作业提取" : "Extract selected run"}
          </Button>
        ) : null}
      </form>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (service)
            void load(() => service.getCoverage(workspace, id.trim()));
        }}
      >
        <label className={label}>
          {zh ? "已有查询 ID" : "Saved query ID"}
          <input
            className={field + " w-72"}
            data-testid="coverage-job-input"
            value={id}
            onChange={(e) => setId(e.currentTarget.value)}
          />
        </label>
        <Button
          size="sm"
          variant="outline"
          type="submit"
          data-testid="coverage-reopen"
          disabled={!id.trim()}
        >
          {zh ? "打开结果" : "Open results"}
        </Button>
      </form>
      {error ? (
        <p role="alert" className="text-ui-sm">
          {error}
        </p>
      ) : null}
      {job ? (
        <div className="space-y-1 border-t border-border pt-3 text-ui-caption">
          <span data-testid="coverage-id" className="select-all font-mono">
            {job.id}
          </span>{" "}
          · {job.status}
          <div className="break-all text-foreground-subtle">
            {job.query.database}
          </div>
          {job.message ? (
            <pre
              role="alert"
              className="max-h-48 overflow-auto whitespace-pre-wrap"
            >
              {job.message}
            </pre>
          ) : null}
        </div>
      ) : null}
      {job?.status === "complete" && job.result ? (
        <CoverageData
          key={job.id}
          workspace={workspace}
          jobId={job.id}
          result={job.result}
          zh={zh}
        />
      ) : null}
    </main>
  );
}
