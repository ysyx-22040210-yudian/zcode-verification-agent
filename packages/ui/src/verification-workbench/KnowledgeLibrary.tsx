import { useEffect, useRef, useState } from "react";
import { usePlatform } from "@/hooks/usePlatform.js";
import { Button } from "@/components/ui/button.js";
import { useZCodeIntl } from "@/i18n/IntlProvider.js";
import type { KnowledgeLibraryProps, KnowledgeReadResult, KnowledgeSearchResult, KnowledgeSource } from "./contract.js";
import { KnowledgeArchivePanel } from "./KnowledgeArchivePanel.js";
import { KnowledgePdfPreview } from "./KnowledgePdfPreview.js";
import { useKnowledgeFilingService, useVerificationService } from "./useVerificationService.js";

const inputClass = "rounded-md border border-border bg-input px-3 py-2 text-ui-base text-foreground";
const rowClass = "w-full rounded-md border border-border px-3 py-2 text-left text-ui-sm hover:bg-surface-hover aria-pressed:bg-card-selected";

export function KnowledgeLibrary({ startArchive }: KnowledgeLibraryProps) {
  const service = useVerificationService();
  const filing = useKnowledgeFilingService();
  const platform = usePlatform();
  const picker = useRef<HTMLInputElement>(null);
  const launching = useRef(false);
  const mounted = useRef(true);
  const [busy, setBusy] = useState(false);
  const [operation, setOperation] = useState("");
  const [archiveError, setArchiveError] = useState("");
  const { locale } = useZCodeIntl();
  const zh = locale.startsWith("zh");
  const [sources, setSources] = useState<readonly KnowledgeSource[]>([]);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [revision, setRevision] = useState(0);
  const [sourceId, setSourceId] = useState("");
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [search, setSearch] = useState<KnowledgeSearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [read, setRead] = useState<KnowledgeReadResult | null>(null);
  const [notice, setNotice] = useState<string>();
  const [pdfVisible, setPdfVisible] = useState(false);
  const source = sources.find((item) => item.id === sourceId) ?? sources[0];
  const shownPage = read?.source.sha256 === source?.sha256 && read?.pages[0]?.page === page
    ? read.pages[0] : undefined;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    if (!service) return;
    let stale = false;
    setCatalogLoaded(false);
    setNotice(undefined);
    void service.listKnowledge().then((result) => {
      if (!stale) setSources(result);
    }).catch((error: unknown) => {
      if (!stale) setNotice(error instanceof Error ? error.message : String(error));
    }).finally(() => {
      if (!stale) setCatalogLoaded(true);
    });
    return () => { stale = true; };
  }, [revision, service]);

  useEffect(() => {
    if (!source || !service) return;
    let stale = false;
    setRead(null);
    setNotice(undefined);
    void service.readKnowledge({ sourceId: source.id, sha256: source.sha256, page }).then((result) => {
      if (!stale) setRead(result);
    }).catch((error: unknown) => {
      if (!stale) setNotice(error instanceof Error ? error.message : String(error));
    });
    return () => { stale = true; };
  }, [page, service, source]);

  useEffect(() => {
    setSearch(null);
    if (!source || !service || !submittedQuery) {
      setSearching(false);
      return;
    }
    let stale = false;
    setSearching(true);
    setNotice(undefined);
    void service.searchKnowledge({
      sourceId: source.id, sha256: source.sha256, query: submittedQuery, limit: 30,
    }).then((result) => {
      if (!stale) setSearch(result);
    }).catch((error: unknown) => {
      if (!stale) setNotice(error instanceof Error ? error.message : String(error));
    }).finally(() => {
      if (!stale) setSearching(false);
    });
    return () => { stale = true; };
  }, [service, source, submittedQuery]);

  function openPage(number: number) {
    if (!source || !Number.isInteger(number) || number < 1 || number > source.pageCount) return;
    setPage(number);
    setPageInput(String(number));
  }

  async function launch(selection: { path: string } | { sourceId: string; sha256: string }) {
    if (launching.current) return;
    launching.current = true;
    setBusy(true);
    setArchiveError("");
    setNotice(undefined);
    try {
      if ("path" in selection) {
        if (!filing) throw new Error(zh ? "知识库服务不可用" : "Knowledge service unavailable");
        setOperation(zh ? "正在保留原件并建立索引…" : "Retaining PDF and indexing pages…");
        let receipt = await filing.importKnowledge(selection.path);
        while (receipt.status === "indexing" && mounted.current) {
          receipt = await filing.knowledgeImportStatus(receipt.jobId);
        }
        if (!mounted.current || receipt.status === "indexing") return;
        if (receipt.status === "failed") throw new Error(receipt.error);
        selection = { sourceId: receipt.sourceId, sha256: receipt.sha256 };
        setSourceId(receipt.sourceId);
        setPage(1);
        setPageInput("1");
        setSubmittedQuery("");
        setQuery("");
        setPdfVisible(false);
        setRevision((value) => value + 1);
      }
      setOperation(zh ? "正在启动模型归档…" : "Starting model filing…");
      const subject = JSON.stringify(selection);
      const message = zh
        ? `请把选定的 PDF 加入本机验证知识库并完成模型归档。文件或已有来源为 ${subject}。使用 verification-knowledge 流程。新文件先 knowledge_import，已有来源从检查点继续。逐批读取证据，保存带页码的主题、摘要和中英文关键词，必要时查原始 PDF。处理待复核页后报告实际进度。`
        : `File the selected PDF in the local verification knowledge base. Selection: ${subject}. Follow the verification-knowledge workflow. Import a new file with knowledge_import or resume the existing source. Read each evidence batch, save cited topics, summaries and search aliases, inspect original pages as needed, and report progress and unresolved pages.`;
      await startArchive(message);
    } catch (error) {
      setArchiveError(error instanceof Error ? error.message : String(error));
    } finally {
      launching.current = false;
      setBusy(false);
      setOperation("");
    }
  }

  return (
    <main className="@container flex h-full min-h-0 flex-col overflow-y-auto bg-background" data-testid="knowledge-library">
      <header className="shrink-0 space-y-3 border-b border-border px-5 py-4">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-ui-xl font-semibold">{zh ? "知识库" : "Knowledge base"}</h1>
          <div className="flex flex-wrap gap-2">
            <input type="file" ref={picker} accept=".pdf,application/pdf" className="hidden" data-testid="knowledge-import-file"
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                event.currentTarget.value = "";
                if (!file) return;
                const path = platform?.getPathForFile?.(file);
                if (!path || !/\.pdf$/i.test(file.name)) {
                  setNotice(zh ? "请选择本机的 PDF 文件。" : "Choose a local PDF file.");
                  return;
                }
                void launch({ path });
              }} />
            <Button size="sm" disabled={busy} data-testid="knowledge-import" onClick={() => picker.current?.click()}>
              {zh ? "添加 PDF 并归档" : "Add PDF and file with Agent"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setRevision((value) => value + 1)}>
              {zh ? "刷新" : "Refresh"}
            </Button>
          </div>
        </div>
        <form className="flex flex-wrap gap-2" onSubmit={(event) => {
          event.preventDefault();
          setSubmittedQuery(query.trim());
        }}>
          <select className={inputClass + " max-w-full"} aria-label={zh ? "选择手册" : "Select manual"}
            data-testid="knowledge-source" value={source?.id ?? ""} disabled={!sources.length}
            onChange={(event) => {
              setSourceId(event.currentTarget.value);
              setPage(1);
              setPageInput("1");
              setPdfVisible(false);
            }}>
            {sources.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
          <input className={inputClass + " min-w-40 flex-1"} data-testid="knowledge-query"
            aria-label={zh ? "检索手册" : "Search manual"} value={query} maxLength={300}
            placeholder={zh ? "搜索 API 名称、关键词或归档主题" : "Search API names, keywords or filed topics"}
            onChange={(event) => setQuery(event.currentTarget.value)} />
          <Button type="submit" disabled={!source || !query.trim() || searching} data-testid="knowledge-search">
            {searching ? (zh ? "检索中…" : "Searching…") : (zh ? "搜索" : "Search")}
          </Button>
        </form>
        {operation ? <p role="status" className="text-ui-sm text-foreground-subtle">{operation}</p> : null}
        {archiveError ? <p role="alert" className="text-ui-sm text-destructive">{archiveError}</p> : null}
        {notice ? <p role="alert" className="text-ui-sm text-destructive">{notice}</p> : null}
      </header>

      {!catalogLoaded ? <p className="p-5 text-ui-base text-foreground-subtle">{zh ? "加载知识库…" : "Loading library…"}</p> : null}
      {catalogLoaded && !sources.length && !notice ? (
        <p className="p-5 text-ui-base text-foreground-subtle">{zh ? "知识库中还没有手册。" : "No manuals have been imported."}</p>
      ) : null}
      {source ? (
        <div className="grid min-w-0 gap-4 p-5 @3xl:min-h-0 @3xl:flex-1 @3xl:grid-cols-[minmax(16rem,1fr)_minmax(0,2fr)] @3xl:grid-rows-[minmax(0,1fr)]">
          <aside className="flex min-w-0 flex-col gap-4 @3xl:min-h-0">
            <section className="shrink-0 space-y-1" data-testid="knowledge-source-metadata">
              <h2 className="text-ui-base font-semibold">{source.title}</h2>
              <p className="text-ui-sm text-foreground-subtle">{source.version} · {source.pageCount.toLocaleString(locale)} {zh ? "页" : "pages"}</p>
              <p className="text-ui-xs text-foreground-subtle">{source.filename}</p>
              <KnowledgeArchivePanel key={source.sha256} source={source} zh={zh} busy={busy}
                openPage={openPage} onResume={() => void launch({ sourceId: source.id, sha256: source.sha256 })} />
            </section>
            <nav className="min-h-0 space-y-2 @3xl:flex-1 @3xl:overflow-y-auto" aria-label={zh ? "章节和检索结果" : "Chapters and search results"}>
              {submittedQuery ? (
                <>
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="text-ui-base font-semibold">{zh ? "搜索结果" : "Search results"}{search ? ` · ${search.total}` : ""}</h2>
                    <Button size="sm" variant="ghost" onClick={() => { setQuery(""); setSubmittedQuery(""); }}>
                      {zh ? "查看目录" : "Chapters"}
                    </Button>
                  </div>
                  {search?.total === 0 ? <p className="text-ui-sm text-foreground-subtle">{zh ? "未找到相关内容，试试 API 名称或更短的关键词。" : "No matches. Try an API name or fewer keywords."}</p> : null}
                  {search?.results.map((hit) => (
                    <button type="button" className={rowClass + " space-y-1"} key={hit.page}
                      aria-pressed={page === hit.page} data-testid="knowledge-result" data-page={hit.page}
                      onClick={() => openPage(hit.page)}>
                      <span className="block text-ui-xs text-foreground-subtle">PDF {zh ? "第 " : "page "}{hit.page}{zh ? " 页" : ""}
                        {hit.origin === "model_guide" ? (zh ? " · 模型归档" : " · Model guide") : ""}</span>
                      <span className="block break-words font-medium">{hit.section || source.title}</span>
                      <span className="line-clamp-3 block break-words text-foreground-subtle">{hit.excerpt}</span>
                    </button>
                  ))}
                </>
              ) : (
                <>
                  <h2 className="text-ui-base font-semibold">{zh ? "章节目录" : "Chapters"}</h2>
                  {source.chapters.map((chapter, index) => (
                    <button type="button" className={rowClass + " flex items-start justify-between gap-3"}
                      key={`${chapter.page}-${index}`} data-testid="knowledge-chapter" onClick={() => openPage(chapter.page)}>
                      <span>{chapter.title}</span><span className="shrink-0 text-foreground-subtle">{chapter.page}</span>
                    </button>
                  ))}
                </>
              )}
            </nav>
          </aside>
          <section className="flex min-h-[28rem] min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-card @3xl:min-h-0"
            data-testid="knowledge-reader">
            <header className="shrink-0 space-y-3 border-b border-border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-ui-sm" data-testid="knowledge-citation">{source.title} · {source.version} · PDF {zh ? "第 " : "page "}{page}{zh ? " 页" : ""}</p>
                <Button size="sm" variant="outline" data-testid="knowledge-pdf-toggle" aria-pressed={pdfVisible}
                  onClick={() => setPdfVisible((value) => !value)}>
                  {pdfVisible ? (zh ? "查看文本" : "Text") : (zh ? "原始 PDF" : "Original PDF")}
                </Button>
              </div>
              <form className="flex flex-wrap items-center gap-2" onSubmit={(event) => { event.preventDefault(); openPage(Number(pageInput)); }}>
                <Button size="sm" variant="ghost" type="button" disabled={page <= 1} onClick={() => openPage(page - 1)}>
                  {zh ? "上一页" : "Previous"}
                </Button>
                <input className={inputClass + " w-20"} type="number" min={1} max={source.pageCount} value={pageInput}
                  aria-label={zh ? "PDF 页码" : "PDF page"} data-testid="knowledge-page-input"
                  onChange={(event) => setPageInput(event.currentTarget.value)} />
                <span className="text-ui-sm text-foreground-subtle">/ {source.pageCount}</span>
                <Button size="sm" type="submit" variant="outline">{zh ? "跳转" : "Go"}</Button>
                <Button size="sm" variant="ghost" type="button" disabled={page >= source.pageCount} onClick={() => openPage(page + 1)}>
                  {zh ? "下一页" : "Next"}
                </Button>
              </form>
            </header>
            {pdfVisible ? (
              <div className="min-h-0 flex-1" data-testid="knowledge-pdf">
                <KnowledgePdfPreview key={source.sha256} source={source} page={page} onPageChange={openPage} />
              </div>
            ) : (
              <div className="min-h-0 flex-1 overflow-auto p-4" data-testid="knowledge-text">
                {shownPage ? (
                  <>
                    <h2 className="mb-4 text-ui-base font-semibold">{shownPage.section || source.title}</h2>
                    <pre className="whitespace-pre-wrap break-words font-mono text-ui-sm leading-relaxed">{shownPage.text || (zh ? "本页没有可提取文本，请查看原始 PDF。" : "This page has no extractable text. Open the original PDF.")}</pre>
                  </>
                ) : <p className="text-ui-sm text-foreground-subtle">{notice ? "" : (zh ? "加载页面…" : "Loading page…")}</p>}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </main>
  );
}
