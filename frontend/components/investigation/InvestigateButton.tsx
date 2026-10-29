"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Play } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "../ui";

export function useStartInvestigation() {
  const router = useRouter();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ anomalyId, useLlm = true }: { anomalyId: string; useLlm?: boolean }) =>
      api.startInvestigation(anomalyId, useLlm),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["anomalies"] });
      qc.invalidateQueries({ queryKey: ["investigations"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      router.push(`/investigations/${r.investigation_id}`);
    },
    onError: (e: Error) => toast.error(`Could not start investigation: ${e.message}`),
  });
}

export function InvestigateButton({
  anomalyId,
  investigationId,
  size = "xs",
}: {
  anomalyId: string;
  investigationId?: string | null;
  size?: "xs" | "sm";
}) {
  const start = useStartInvestigation();
  if (investigationId)
    return (
      <Link href={`/investigations/${investigationId}`}>
        <Button size={size} variant="default">
          Open <ArrowUpRight className="h-3 w-3" />
        </Button>
      </Link>
    );
  return (
    <Button
      size={size}
      variant="primary"
      loading={start.isPending && start.variables?.anomalyId === anomalyId}
      onClick={(e) => {
        e.stopPropagation();
        start.mutate({ anomalyId });
      }}
    >
      {!start.isPending && <Play className="h-3 w-3" />} Investigate
    </Button>
  );
}
