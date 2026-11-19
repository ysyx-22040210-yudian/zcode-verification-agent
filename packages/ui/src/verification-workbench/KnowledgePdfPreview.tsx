import { lazy, Suspense, useMemo } from "react";
import { usePdfViewerLabels } from "@/hooks/usePreviewViewerLabels.js";
import type { KnowledgeSource } from "./contract.js";
import { useVerificationService } from "./useVerificationService.js";

const PdfViewer = lazy(() => import("@/components/ui/pdf-viewer.js").then((module) => ({
  default: module.PdfViewer,
})));

export function KnowledgePdfPreview({ source, page, onPageChange }: Readonly<{
  source: KnowledgeSource;
  page: number;
  onPageChange: (page: number) => void;
}>) {
  const service = useVerificationService();
  const labels = usePdfViewerLabels();
  const pdf = useMemo(() => ({
    totalBytes: source.pdfBytes,
    async requestRange(offset: number, length: number) {
      if (!service) throw new Error("Knowledge service is unavailable");
      const { base64 } = await service.readKnowledgePdf({
        sourceId: source.id, sha256: source.sha256, offset, length,
      });
      const binary = atob(base64);
      return Uint8Array.from(binary, (character) => character.charCodeAt(0));
    },
  }), [service, source.id, source.pdfBytes, source.sha256]);

  return (
    <Suspense fallback={<p className="p-4 text-ui-base text-foreground-subtle">{labels.loading}</p>}>
      <PdfViewer source={pdf} initialPage={page} onPageChange={onPageChange} labels={labels} className="h-full" />
    </Suspense>
  );
}
