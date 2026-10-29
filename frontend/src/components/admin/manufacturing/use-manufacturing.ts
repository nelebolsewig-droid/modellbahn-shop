"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  getBillOfMaterials,
  getGetBillOfMaterialsQueryKey,
  getGetPrinterHallQueryKey,
  getGetPrinterQueryKey,
  getListMaterialsQueryKey,
  getListPartsQueryKey,
  getListPrintJobsQueryKey,
  getPrinter,
  getPrinterHall,
  listMaterials,
  listParts,
  listPrintJobs,
} from "@/lib/api/generated/admin-manufacturing/admin-manufacturing";
import type {
  BomOut,
  HallOut,
  ListPartsParams,
  ListPrintJobsParams,
  MaterialOut,
  PartOut,
  PrinterRecordOut,
  PrintJobOut,
} from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";

const MANUFACTURING_PREFIX = "/api/v1/admin/manufacturing/";

/** After any change in the workshop: every manufacturing view loads again. */
export function useManufacturingRefresh() {
  const queryClient = useQueryClient();
  return () =>
    void queryClient.invalidateQueries({
      predicate: (query) => String(query.queryKey[0]).startsWith(MANUFACTURING_PREFIX),
    });
}

export function useHall() {
  return useQuery<HallOut, ApiProblem>({
    queryKey: getGetPrinterHallQueryKey(),
    queryFn: ({ signal }) => getPrinterHall({ signal }),
  });
}

export const RECENT_JOBS: ListPrintJobsParams = { status: ["done", "failed"], limit: 8 };

export function useJobs(params: ListPrintJobsParams) {
  return useQuery<PrintJobOut[], ApiProblem>({
    queryKey: getListPrintJobsQueryKey(params),
    queryFn: async ({ signal }) => (await listPrintJobs(params, { signal })).items,
  });
}

export function usePrinterRecord(printerId: string) {
  return useQuery<PrinterRecordOut, ApiProblem>({
    queryKey: getGetPrinterQueryKey(printerId),
    queryFn: ({ signal }) => getPrinter(printerId, { signal }),
  });
}

export function useMaterials() {
  return useQuery<MaterialOut[], ApiProblem>({
    queryKey: getListMaterialsQueryKey(),
    queryFn: async ({ signal }) => (await listMaterials({ signal })).items,
  });
}

export function useParts(params: ListPartsParams, enabled = true) {
  return useQuery<PartOut[], ApiProblem>({
    queryKey: getListPartsQueryKey(params),
    queryFn: async ({ signal }) => (await listParts(params, { signal })).items,
    enabled,
  });
}

export function useBom(productScaleId: string) {
  return useQuery<BomOut, ApiProblem>({
    queryKey: getGetBillOfMaterialsQueryKey(productScaleId),
    queryFn: ({ signal }) => getBillOfMaterials(productScaleId, { signal }),
  });
}

/** The current time, renewed every `intervalMs`: progress bars move without new data. */
export function useNow(intervalMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
