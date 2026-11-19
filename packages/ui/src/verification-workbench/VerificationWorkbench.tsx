import { useEffect, useRef, useState } from "react";
import { Wrench } from "lucide-react";
import { Button } from "@/components/ui/button.js";
import { useZCodeIntl } from "@/i18n/IntlProvider.js";
import type { VerificationEntryProps, VerificationFrameProps, VerificationRun, VerificationSnapshot, VerificationVariant } from "./contract.js";
import { useDesignQueryService, useVerificationService } from "./useVerificationService.js";
import { CoveragePanel } from "./CoveragePanel.js";
import { Waveform } from "./Waveform.js";

const selectClass = "rounded-md border border-border bg-input px-2 py-1 text-ui-sm text-foreground";
const statusClass = "rounded border border-border bg-surface px-1.5 py-0.5 text-ui-xs";
const isActive = (run: VerificationRun) => run.status === "queued" || run.status === "running";

export function VerificationEntry({ active, onToggle, toolsActive, onToolsToggle, knowledgeActive, onKnowledgeToggle, designActive, onDesignToggle, fsdbActive, onFsdbToggle }: VerificationEntryProps) {
  const service = useVerificationService();
  const { locale } = useZCodeIntl();
  const [available, setAvailable] = useState(false);
  const label = locale.startsWith("zh") ? "验证" : "Verification";

  useEffect(() => {
    if (!service) return;
    let stale = false;
    void service.available().then((value) => {
      if (!stale) setAvailable(value);
    }).catch(() => {
      if (!stale) setAvailable(false);
    });
    return () => { stale = true; };
  }, [service]);

  if (!available) return null;
  return (
    <div className="flex shrink-0 flex-wrap justify-end border-b border-border bg-background px-3 py-1">
      <Button type="button" size="sm" variant={toolsActive ? "secondary" : "ghost"} aria-pressed={toolsActive}
        data-testid="verification-tools-entry" onClick={onToolsToggle}>
        <Wrench className="size-3.5" aria-hidden="true" />{locale.startsWith("zh") ? "工具" : "Tools"}
      </Button>
      <Button type="button" size="sm" variant={fsdbActive ? "secondary" : "ghost"} aria-pressed={fsdbActive}
        data-testid="fsdb-entry" onClick={onFsdbToggle}>{locale.startsWith("zh") ? "FSDB 波形" : "FSDB waves"}</Button>
      <Button type="button" size="sm" variant={designActive ? "secondary" : "ghost"}
        aria-pressed={designActive} data-testid="design-query-entry" onClick={onDesignToggle}>
        {locale.startsWith("zh") ? "RTL 查询" : "RTL query"}
      </Button>
      <Button type="button" size="sm" variant={knowledgeActive ? "secondary" : "ghost"}
        aria-pressed={knowledgeActive} data-testid="knowledge-entry" onClick={onKnowledgeToggle}>
        {locale.startsWith("zh") ? "知识库" : "Knowledge base"}
      </Button>
      <Button type="button" size="sm" variant={active ? "secondary" : "ghost"} aria-pressed={active}
        data-testid="verification-entry" onClick={onToggle}>
        {label}
      </Button>
    </div>
  );
}

interface EvidenceView {
  runId: string;
  name: string;
  text: string;
  nextOffset: number | null;
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function VerificationWorkbench({ workspace, onOpenFsdb }: VerificationFrameProps & { onOpenFsdb: (path: string) => void }) {
  const designService = useDesignQueryService();
  const service = useVerificationService();
  const { locale } = useZCodeIntl();
  const zh = locale.startsWith("zh");
  const [coverageOpen, setCoverageOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<VerificationSnapshot | null>(null);
  const [notice, setNotice] = useState<string>();
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState("");
  const [variant, setVariant] = useState<VerificationVariant>("normal");
  const [seed, setSeed] = useState("42");
  const [selectedRun, setSelectedRun] = useState<string>();
  const [evidence, setEvidence] = useState<EvidenceView>();
  const evidenceRequest = useRef(0);

  useEffect(() => {
    if (!service) return;
    let stale = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await service?.inspect(workspace);
        if (!stale && next) {
          setSnapshot(next);
          timer = setTimeout(() => { void refresh(); }, 1600);
        }
      } catch (error) {
        if (!stale) setNotice(describe(error));
      }
    }
    void refresh();
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [revision, service, workspace]);

  // 提交的运行可能尚未进入下一次列表快照，先等待该 ID，避免短暂显示别的作业。
  const run = selectedRun
    ? snapshot?.runs.find((item) => item.id === selectedRun)
    : snapshot?.runs[0];
  const activeProfile = snapshot?.profiles[profile] ? profile : Object.keys(snapshot?.profiles ?? {})[0];
  const canMutate = activeProfile ? snapshot?.profiles[activeProfile]?.mutant === true : false;
  const parsedSeed = Number(seed);
  const validSeed = Number.isInteger(parsedSeed) && parsedSeed >= 1 && parsedSeed <= 2147483647;
  const shownEvidence = evidence?.runId === run?.id ? evidence : undefined;
  const nextStage = snapshot?.stages.find((item) => !item.completed);

  async function update(action: () => Promise<VerificationRun | VerificationSnapshot>) {
    setBusy(true);
    setNotice(undefined);
    try {
      const result = await action();
      if ("id" in result) {
        setSelectedRun(result.id);
      } else {
        setSnapshot(result);
      }
      setRevision((value) => value + 1);
    } catch (error) {
      setNotice(describe(error));
    } finally {
      setBusy(false);
    }
  }

  async function openEvidence(target: VerificationRun, name: string, previous?: EvidenceView) {
    if (!service) return;
    const request = ++evidenceRequest.current;
    try {
      if (name.toLowerCase().endsWith(".fsdb") && designService) {
        const artifact = await designService.fsdbArtifact(workspace, target.id, name);
        if (evidenceRequest.current === request) onOpenFsdb(artifact.path);
        return;
      }
      const page = await service.readArtifact(workspace, target.id, name, previous?.nextOffset ?? 0);
      if (evidenceRequest.current !== request) return;
      setEvidence({ runId: target.id, name, text: (previous?.text ?? "") + page.text, nextOffset: page.nextOffset });
    } catch (error) {
      if (request === evidenceRequest.current) setNotice(describe(error));
    }
  }

  if (!service) return null;
  if (coverageOpen) return <CoveragePanel key={workspace} workspace={workspace} runId={run?.coverage ? run.id : undefined} onClose={() => setCoverageOpen(false)} />;
  return (
    <main
      data-testid="verification-workbench"
      className="@container flex h-full min-h-0 flex-col overflow-y-auto bg-background"
    >
      <div className="shrink-0 space-y-3 border-b border-border px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-ui-xl font-semibold">{zh ? "验证工作台" : "Verification"}</h1>
          <Button type="button" variant="outline" size="sm" data-testid="coverage-entry" onClick={() => setCoverageOpen(true)}>
            {zh ? "覆盖率数据" : "Coverage data"}
          </Button>
          {snapshot ? <span className="text-ui-caption text-foreground-subtle">{snapshot.name} · {snapshot.spec}</span> : null}
        </div>
        {notice ? <p role="alert" className="text-ui-sm text-foreground-subtle">{notice}</p> : null}
        {snapshot && activeProfile ? (
          <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => {
            event.preventDefault();
            void update(() => service.submit(workspace, {
              profile: activeProfile, seed: parsedSeed, variant: canMutate ? variant : "normal",
            }));
          }}>
            <label className="grid gap-1 text-ui-xs text-foreground-subtle">
              {zh ? "验证配置" : "Profile"}
              <select className={selectClass} data-testid="verification-profile" value={activeProfile}
                onChange={(event) => setProfile(event.currentTarget.value)}>
                {Object.entries(snapshot.profiles).map(([id, item]) => (
                  <option key={id} value={id}>{id} · {item.backend === "yosys" ? "Yosys + Z3" : (item.backend ?? item.mode).toUpperCase()}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-ui-xs text-foreground-subtle">
              Seed
              <input type="number" min={1} max={2147483647} className={selectClass + " w-20"} value={seed}
                onChange={(event) => setSeed(event.currentTarget.value)} />
            </label>
            {canMutate ? (
              <label className="grid gap-1 text-ui-xs text-foreground-subtle">
                {zh ? "设计版本" : "Design"}
                <select className={selectClass} data-testid="verification-variant" value={variant}
                  onChange={(event) => setVariant(event.currentTarget.value === "mutant" ? "mutant" : "normal")}>
                  <option value="normal">{zh ? "正常" : "Normal"}</option>
                  <option value="mutant">{zh ? "故障用例" : "Mutant"}</option>
                </select>
              </label>
            ) : null}
            <Button type="submit" size="sm" disabled={busy || !validSeed} data-testid="verification-submit">
              {zh ? "运行" : "Run"}
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={busy || !nextStage || nextStage.missingProfiles.length > 0}
              onClick={() => { void update(() => service.advance(workspace)); }}>
              {zh ? "验收阶段" : "Complete stage"}
            </Button>
          </form>
        ) : null}
      </div>

      {snapshot ? (
        // 双栏占满工作台的剩余高度，窄窗中的两栏内容随页面滚动。
        <div className="grid min-w-0 gap-4 px-5 py-4 @3xl:min-h-0 @3xl:flex-1 @3xl:grid-cols-[minmax(13rem,1fr)_minmax(0,2.3fr)] @3xl:grid-rows-[minmax(0,1fr)]">
          <aside className="flex min-w-0 flex-col gap-4 @3xl:min-h-0">
            <section className="shrink-0 space-y-2 @3xl:max-h-[50%] @3xl:overflow-y-auto">
              <h2 className="text-ui-base font-semibold">{zh ? "阶段和验证点" : "Stages and checks"}</h2>
              <div className="flex flex-wrap gap-1">
                {snapshot.stages.map((stage) => (
                  <span className={statusClass} key={stage.id} title={stage.missingProfiles.join(", ")}>
                    {stage.completed ? "✓ " : ""}{stage.id}
                  </span>
                ))}
              </div>
              <ul className="space-y-1 text-ui-sm">
                {snapshot.checks.map((check) => (
                  <li key={check.id}>
                    <span className="font-mono text-ui-xs text-foreground-subtle">{check.id} </span>
                    {check.title}
                  </li>
                ))}
              </ul>
            </section>
            <section className="flex min-h-0 flex-col gap-2 @3xl:flex-1">
              <h2 className="shrink-0 text-ui-base font-semibold">{zh ? "运行历史" : "Runs"}</h2>
              <ul className="min-h-0 max-h-[40dvh] space-y-1 overflow-y-auto @3xl:max-h-none @3xl:flex-1">
                {snapshot.runs.map((item) => (
                  <li key={item.id}>
                    <button type="button" onClick={() => setSelectedRun(item.id)} data-testid="verification-run-row"
                      data-run-id={item.id} aria-pressed={run?.id === item.id}
                      className="flex w-full items-center justify-between gap-2 rounded-md border border-border px-2 py-1.5 text-left text-ui-sm hover:bg-surface-hover aria-pressed:bg-card-selected">
                      <span className="min-w-0 truncate">
                        {item.profileId} · {item.variant} <span className="font-mono text-ui-xs text-foreground-subtle">{item.id.slice(0, 8)}</span>
                      </span>
                      <span className={statusClass}>{item.status}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </aside>

          {run ? (
            <section
              className="flex min-w-0 flex-col gap-3 rounded-md border border-border bg-card p-3 @3xl:min-h-0 @3xl:overflow-y-auto"
              data-testid="verification-run-detail"
            >
              <div className="shrink-0 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-ui-base font-semibold">{run.engine} · {run.profileId}</h2>
                  <span data-testid="verification-run-status" className={statusClass}>{run.status}</span>
                  <span className="grow text-ui-caption text-foreground-subtle">seed {run.seed}</span>
                  <Button size="sm" variant="outline" disabled={busy || !isActive(run)}
                    onClick={() => { void update(() => service.cancel(workspace, run.id)); }}>
                    {zh ? "取消" : "Cancel"}
                  </Button>
                  <Button size="sm" variant="outline" disabled={busy || isActive(run)} data-testid="verification-rerun"
                    onClick={() => { void update(() => service.rerun(workspace, run.id)); }}>
                    {zh ? "重跑" : "Rerun"}
                  </Button>
                </div>
                <p className="break-all font-mono text-ui-xs text-foreground-subtle" data-testid="verification-run-id">{run.id}</p>
                <p className="text-ui-sm">{run.message}</p>
                {typeof run.checksExecuted === "number" ? (
                  <p className="text-ui-sm">{zh ? "已执行检查" : "Checks executed"} {run.checksExecuted}</p>
                ) : null}
                {run.coverage ? (
                  <dl className="flex flex-wrap gap-3 text-ui-sm" data-testid="verification-coverage">
                    <div>{zh ? "功能" : "Functional"} {run.coverage.functionalPercent ?? "—"}%</div>
                    <div>{zh ? "行" : "Line"} {run.coverage.linePercent ?? "—"}%</div>
                    <div>{zh ? "条件" : "Condition"} {run.coverage.conditionPercent ?? "—"}%</div>
                    <div>{zh ? "翻转" : "Toggle"} {run.coverage.togglePercent ?? "—"}%</div>
                  </dl>
                ) : null}
                {run.properties ? (
                  <ul className="space-y-1 text-ui-sm" data-testid="verification-properties">
                    {run.properties.map((property) => (
                      <li key={property.name} className="flex flex-wrap items-center gap-2">
                        <code className="text-ui-xs">{property.name}</code>
                        <span className={statusClass}>{property.status}</span>
                        {property.depth === undefined ? null : <span>{zh ? "深度" : "Depth"} {property.depth}</span>}
                        {property.trace ? (
                          <Button type="button" size="sm" variant="ghost"
                            onClick={() => { if (property.trace) void openEvidence(run, property.trace); }}>
                            {property.status === "counterexample" ? (zh ? "查看反例" : "View counterexample") : (zh ? "查看波形" : "View trace")}
                          </Button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}

                <div className="flex flex-wrap gap-1.5">
                  {run.artifacts.map((asset) => (
                    <Button key={asset.name} type="button" size="sm" variant="ghost"
                      data-testid={asset.kind === "waveform" ? "verification-waveform" : "verification-artifact"}
                      onClick={() => { void openEvidence(run, asset.name); }}>
                      {asset.name}
                    </Button>
                  ))}
                </div>
              </div>
              {shownEvidence ? (
                <div className="flex h-[50dvh] min-h-48 flex-col gap-2 @3xl:h-auto @3xl:flex-1">
                  <div
                    aria-label={shownEvidence.name}
                    className="min-h-0 flex-1 overflow-auto rounded-md border border-border bg-background"
                    data-testid="verification-evidence"
                    role="region"
                    tabIndex={0}
                  >
                    {shownEvidence.name.endsWith(".vcd") ? (
                      <div className="px-2 pt-2">
                        <Waveform text={shownEvidence.text} label={zh ? "作业波形" : "Run waveform"} />
                      </div>
                    ) : null}
                    <pre className="p-2 font-mono text-ui-xs">{shownEvidence.text}</pre>
                  </div>
                  {shownEvidence.nextOffset !== null ? (
                    <Button
                      className="shrink-0 self-start"
                      size="sm"
                      variant="outline"
                      onClick={() => { void openEvidence(run, shownEvidence.name, shownEvidence); }}
                    >
                      {zh ? "读取更多" : "Read more"}
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
