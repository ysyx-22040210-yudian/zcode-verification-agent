import { useServices } from "@/hooks/useServices.js";

export function useVerificationService() {
  return useServices().verificationService;
}
