import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button.js";
import type { KnowledgeGuideResult, KnowledgeSource } from "./contract.js";
import { useKnowledgeFilingService } from "./useVerificationService.js";

export function KnowledgeArchivePanel({ source, zh, busy, onResume, openPage }: {
  readonly source: KnowledgeSource; readonly zh: boolean; readonly busy: boolean;
  readonly onResume: () => void; readonly openPage: (page: number) => void;
}) {
  const service = useKnowledgeFilingService();
  const [expanded, setExpanded] = useState(false);
  const [offset, setOffset] = useState(0);
  const [guide, setGuide] = useState<KnowledgeGuideResult>();
  const [error, setError] = useState("");
  const { id, sha256, archive } = source;
  const filed = archive?.filedPages ?? 0;
  const reviews = archive?.reviewCount ?? 0;
  useEffect(() => {
    if (!expanded || !service) return;
    let stale = false;
    setGuide(undefined);
    setError("");
    void service.getKnowledgeGuide({ sourceId: id, sha256, offset }).then((value) => {
      if (!stale) setGuide(value);
    }).catch((reason: unknown) => {
      if (!stale) setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => { stale = true; };
  }, [expanded, filed, id, offset, reviews, service, sha256]);

  return <section className="space-y-1">
    <p data-testid="knowledge-archive-status" className="text-ui-sm text-foreground-subtle">
      {zh ? "模型已整理" : "Filed by model"} {filed} / {source.pageCount} {zh ? "页" : "pages"}
      {reviews > 0 ? (zh ? ` · ${reviews} 页待复核` : ` · ${reviews} pages to review`) : ""}
    </p>
    <div className="flex flex-wrap gap-2">
      {(archive?.topicCount || reviews) ? <Button size="sm" variant="outline" aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}>{zh ? "归档主题" : "Filed topics"} · {archive?.topicCount ?? 0}</Button> : null}
      {filed < source.pageCount || reviews > 0 ? <Button size="sm" variant="ghost" disabled={busy} onClick={onResume}>
        {filed < source.pageCount ? (zh ? "继续模型归档" : "File with Agent") : (zh ? "复核原页" : "Review original pages")}
      </Button> : null}
    </div>
    {expanded ? <div className="max-h-56 space-y-2 overflow-y-auto" data-testid="knowledge-guide">
      {error ? <p role="alert" className="text-ui-sm text-destructive">{error}</p> : null}
      {guide?.topics.map((topic, index) => <button type="button" key={offset + index}
        className="block w-full rounded-md border border-border p-2 text-left text-ui-sm hover:bg-surface-hover"
        onClick={() => openPage(topic.page)}>
        <span className="block font-semibold">{topic.title} · PDF {topic.page}</span>
        <span className="block">{topic.summary}</span>
        {topic.quote ? <q className="block text-foreground-subtle">{topic.quote}</q> : null}
      </button>)}
      {guide?.reviewPages.map((number) => <Button key={number} variant="ghost" size="sm" onClick={() => openPage(number)}>
        {zh ? "待复核" : "To review"} · PDF {number}
      </Button>)}
      {offset > 0 ? <Button variant="ghost" size="sm" onClick={() => setOffset(Math.max(0, offset - 32))}>
        {zh ? "上一组主题" : "Previous topics"}</Button> : null}
      {guide?.nextOffset != null ? <Button variant="ghost" size="sm" onClick={() => setOffset(guide.nextOffset ?? 0)}>
        {zh ? "下一组主题" : "More topics"}</Button> : null}
    </div> : null}
  </section>;
}

