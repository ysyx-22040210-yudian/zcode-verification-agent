import { useEffect, useState } from "react";
import {
  Activity,
  Boxes,
  ChartColumn,
  ChevronRight,
  Search,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/button.js";
import { useZCodeIntl } from "@/i18n/IntlProvider.js";
import type { ToolCatalog, ToolStarter, VerificationTool } from "./contract.js";
import { useDesignQueryService } from "./useVerificationService.js";

type ToolId = VerificationTool["id"];
type Locale = "zh" | "en";
type Mode = "analyze" | "develop";
type Drafts = Record<Mode, string>;
const emptyDrafts: Drafts = { analyze: "", develop: "" };

interface Props {
  workspace: string;
  onOpen: (id: ToolId) => void;
  startAgent: (prompt: string) => Promise<void>;
}

const icons = { rtl: Boxes, fsdb: Activity, coverage: ChartColumn };

function describe(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function ToolDetail({
  tool,
  catalog,
  workspace,
  onOpen,
  startAgent,
  lang,
  drafts,
  onDraft,
}: Props & {
  drafts: Drafts;
  onDraft: (mode: Mode, value: string) => void;
  tool: VerificationTool;
  catalog: ToolCatalog;
  lang: Locale;
}) {
  const service = useDesignQueryService();
  const zh = lang === "zh";
  const [mode, setMode] = useState<Mode>("analyze");
  const [receipt, setReceipt] = useState<ToolStarter>();
  const [busy, setBusy] = useState<"agent" | "starter">();
  const [error, setError] = useState("");
  const developing = mode === "develop";
  const Icon = icons[tool.id];

  async function createStarter() {
    if (!service || busy) return;
    setBusy("starter");
    setError("");
    try {
      setReceipt(await service.scaffoldTool(workspace, tool.id));
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setBusy(undefined);
    }
  }

  async function submit() {
    const request = drafts[mode].trim();
    if (!request || busy) return;
    setBusy("agent");
    setError("");
    const task = developing
      ? zh
        ? "请基于这个工具在当前工程做二次开发。先调用 verification_tool_catalog 查看接口，然后用 verification_tool_scaffold 取得项目示例，阅读现有文件，按需求修改并运行验证，返回代码路径和实测结果。"
        : "Extend this tool in the current project. Inspect its interface with verification_tool_catalog and obtain the starter with verification_tool_scaffold. Read existing files, implement and run the requested change, and return the code path and observed results."
      : zh
        ? "请使用该工具处理当前工程中的需求，依据实际运行结果回答，并给出作业 ID。"
        : "Use this tool in the current project, answer from the observed results and include the job ID.";
    try {
      await startAgent(
        [
          task,
          tool.title[lang] + " (" + tool.id + ") · " + tool.methods.join(", "),
          request,
        ].join("\n\n"),
      );
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setBusy(undefined);
    }
  }

  return (
    <section
      className="min-w-0 space-y-5 rounded-lg border border-border bg-surface p-4 sm:p-5"
      aria-label={tool.title[lang]}
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-ui-lg font-semibold">
            <Icon className="size-5" aria-hidden="true" />
            {tool.title[lang]}
          </h2>
          <p className="mt-2 text-ui-sm text-foreground-subtle">
            {tool.summary[lang]}
          </p>
        </div>
        <Button
          size="sm"
          data-testid="tool-open"
          onClick={() => onOpen(tool.id)}
        >
          {zh ? "打开工具" : "Open tool"}
          <ChevronRight className="size-3.5" aria-hidden="true" />
        </Button>
      </header>
      <div className="border-t border-border pt-4">
        <h3 className="text-ui-sm font-medium">
          {zh ? "Agent 可调用的接口" : "Agent methods"}
        </h3>
        <ul className="mt-2 flex flex-wrap gap-2">
          {tool.methods.map((method) => (
            <li
              className="rounded border border-border bg-background px-2 py-1 font-mono text-ui-xs"
              key={method}
            >
              {method}
            </li>
          ))}
        </ul>
      </div>
      <div className="space-y-3 border-t border-border pt-4">
        <div
          className="flex flex-wrap gap-1"
          role="group"
          aria-label={zh ? "需求类型" : "Request type"}
        >
          <Button
            size="sm"
            variant={developing ? "ghost" : "secondary"}
            aria-pressed={!developing}
            onClick={() => {
              setMode("analyze");
              setError("");
            }}
          >
            {zh ? "调用工具" : "Use tool"}
          </Button>
          <Button
            size="sm"
            variant={developing ? "secondary" : "ghost"}
            aria-pressed={developing}
            data-testid="tool-mode-develop"
            onClick={() => {
              setMode("develop");
              setError("");
            }}
          >
            {zh ? "二次开发" : "Extend tool"}
          </Button>
        </div>
        {developing ? (
          <div className="space-y-2 rounded-md border border-border p-3 text-ui-sm">
            <p>{tool.starterPurpose[lang]}</p>
            <code className="block break-all text-ui-xs text-foreground-subtle">
              verification_extensions/{tool.starter}
            </code>
            <Button
              size="sm"
              variant="outline"
              disabled={Boolean(busy)}
              onClick={() => void createStarter()}
              data-testid="tool-scaffold"
            >
              {zh ? "创建项目示例" : "Create project starter"}
            </Button>
            {receipt ? (
              <p
                className="break-all text-ui-xs"
                role="status"
                data-testid="tool-starter-path"
              >
                {receipt.created
                  ? zh
                    ? "已创建"
                    : "Created"
                  : zh
                    ? "已有项目文件"
                    : "Existing project file"}{" "}
                · {receipt.path}
              </p>
            ) : null}
            <details className="text-ui-xs text-foreground-subtle">
              <summary className="cursor-pointer">
                {zh ? "运行示例与源码位置" : "Example command and source files"}
              </summary>
              <pre className="my-2 whitespace-pre-wrap break-all">
                python3 verification_extensions/{tool.usage}
              </pre>
              <ul className="space-y-1 font-mono">
                {[
                  catalog.guidePath,
                  catalog.sdkPath,
                  tool.cli,
                  ...tool.sources,
                ].map((path) => (
                  <li key={path} className="break-all">
                    {path}
                  </li>
                ))}
              </ul>
            </details>
          </div>
        ) : null}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
          className="space-y-3"
        >
          <label className="block space-y-1.5 text-ui-sm">
            <span>
              {developing
                ? zh
                  ? "希望新增什么功能？"
                  : "What should the extension do?"
                : zh
                  ? "希望查什么？"
                  : "What would you like to inspect?"}
            </span>
            <textarea
              className="block min-h-24 w-full rounded-md border border-border bg-background p-2.5 text-foreground"
              data-testid="tool-request"
              value={drafts[mode]}
              onChange={(event) => onDraft(mode, event.target.value)}
            />
          </label>
          <Button
            type="submit"
            size="sm"
            variant="outline"
            disabled={Boolean(busy) || !drafts[mode].trim()}
            data-testid="tool-ask-agent"
          >
            {busy === "agent"
              ? zh
                ? "正在提交…"
                : "Submitting…"
              : zh
                ? "交给 Agent"
                : "Send to Agent"}
          </Button>
        </form>
        {error ? (
          <p role="alert" className="text-ui-sm text-destructive">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}

export function VerificationToolCatalog({
  workspace,
  onOpen,
  startAgent,
}: Props) {
  const service = useDesignQueryService();
  const lang = useZCodeIntl().locale.startsWith("zh") ? "zh" : "en";
  const zh = lang === "zh";
  const [query, setQuery] = useState("");
  const [drafts, setDrafts] = useState<Partial<Record<ToolId, Drafts>>>({});
  const [selected, setSelected] = useState<ToolId>("rtl");
  const [response, setResponse] = useState<{
    query: string;
    catalog?: ToolCatalog;
    error?: string;
  }>();
  useEffect(() => {
    if (!service) return;
    let active = true;
    void service
      .listTools(workspace, query)
      .then((catalog) => {
        if (active) setResponse({ query, catalog });
      })
      .catch((cause: unknown) => {
        if (active) setResponse({ query, error: describe(cause) });
      });
    return () => {
      active = false;
    };
  }, [query, service, workspace]);
  const current = response?.query === query ? response : undefined;
  const catalog = current?.catalog;
  const tool =
    catalog?.tools.find((item) => item.id === selected) ?? catalog?.tools[0];
  return (
    <main className="h-full min-h-0 overflow-auto bg-background p-4 text-foreground sm:p-6">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-ui-xl font-semibold">
          <Wrench className="size-5" aria-hidden="true" />
          {zh ? "验证工具" : "Verification tools"}
        </h1>
        <label className="flex w-full max-w-sm items-center gap-2 rounded-md border border-border bg-input px-2.5 py-1.5">
          <Search
            className="size-4 shrink-0 text-foreground-subtle"
            aria-hidden="true"
          />
          <input
            type="search"
            maxLength={512}
            className="min-w-0 flex-1 bg-transparent text-ui-sm"
            data-testid="verification-tool-search"
            aria-label={zh ? "搜索验证工具" : "Search verification tools"}
            placeholder={
              zh ? "搜索工具、用途或接口名称" : "Search tools, tasks or methods"
            }
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </header>
      {!service || current?.error ? (
        <p role="alert" className="text-ui-sm text-destructive">
          {current?.error ||
            (zh ? "验证服务不可用" : "Verification service unavailable")}
        </p>
      ) : !catalog ? (
        <p role="status" className="text-ui-sm text-foreground-subtle">
          {zh ? "正在搜索…" : "Searching…"}
        </p>
      ) : !tool ? (
        <p
          role="status"
          data-testid="tool-no-results"
          className="text-ui-sm text-foreground-subtle"
        >
          {zh
            ? "未找到匹配工具，可尝试接口名或更短的关键词。"
            : "No tools found. Try a method name or a shorter search."}
        </p>
      ) : (
        <div className="grid items-start gap-4 md:grid-cols-[minmax(13rem,0.75fr)_minmax(0,2fr)]">
          <nav
            aria-label={zh ? "验证工具列表" : "Verification tool list"}
            className="space-y-2"
          >
            {catalog.tools.map((item) => {
              const Icon = icons[item.id];
              return (
                <button
                  type="button"
                  key={item.id}
                  data-testid={"tool-select-" + item.id}
                  onClick={() => setSelected(item.id)}
                  aria-pressed={tool.id === item.id}
                  className="flex w-full items-center gap-2.5 rounded-md border border-border p-3 text-left text-ui-sm hover:bg-surface aria-pressed:bg-surface aria-pressed:font-semibold"
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  <span>{item.title[lang]}</span>
                </button>
              );
            })}
          </nav>
          <ToolDetail
            key={tool.id}
            tool={tool}
            catalog={catalog}
            lang={lang}
            workspace={workspace}
            onOpen={onOpen}
            startAgent={startAgent}
            drafts={drafts[tool.id] ?? emptyDrafts}
            onDraft={(mode, value) =>
              setDrafts((previous) => ({
                ...previous,
                [tool.id]: {
                  ...(previous[tool.id] ?? emptyDrafts),
                  [mode]: value,
                },
              }))
            }
          />
        </div>
      )}
    </main>
  );
}
