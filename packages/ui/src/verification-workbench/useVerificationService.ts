import { useServices } from "@/hooks/useServices.js";

export function useVerificationService() {
  return useServices().verificationService;
}

export function useDesignQueryService() {
  return useServices().designQueryService;
}

export function useKnowledgeFilingService() {
  return useServices().knowledgeFilingService;
}
