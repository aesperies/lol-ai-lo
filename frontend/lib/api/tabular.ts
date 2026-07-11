"use client";

/* ------------------------------------------------------------------ */
/* Tabular Review (010_tabular_reviews.sql) — gestora-siloed grid        */
/* ------------------------------------------------------------------ */

import { docTypeLabel } from "@/lib/catalog";
import { isStubMode } from "@/lib/supabase/client";
import type {
  TabularColumnInput,
  TabularDocumentOption,
  TabularReview,
  TabularReviewDetail,
  TabularReviewStatusInfo,
} from "@/lib/types";
import {
  ApiError,
  STUB_LATENCY,
  apiFetch,
  apiPaths,
  fetchBlob,
  stubCall,
} from "./http";

interface TabularColumnWire {
  id: string;
  review_id: string;
  position: number;
  name: string;
  question: string;
  col_type: TabularReviewDetail["columns"][number]["colType"];
  options?: string[] | null;
}

interface TabularDocumentWire {
  id: string;
  review_id: string;
  position: number;
  source_kind: TabularDocumentOption["sourceKind"];
  source_id: string;
  label?: string | null;
}

interface TabularCellWire {
  id: string;
  document_id: string;
  column_id: string;
  value?: string | null;
  reasoning?: string | null;
  citation?: { page: number | string | null; quote: string | null } | null;
  status: TabularReviewDetail["cells"][number]["status"];
  error?: string | null;
}

interface TabularReviewWire {
  id: string;
  gestora_id: string;
  fund_id?: string | null;
  created_by?: string | null;
  title: string;
  status: TabularReview["status"];
  // Collaboration (012_collaboration.sql): per-caller ownership/sharing flags.
  is_owner?: boolean | null;
  shared_with_me?: boolean | null;
  shared_by_email?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface TabularReviewDetailWire extends TabularReviewWire {
  columns: TabularColumnWire[];
  documents: TabularDocumentWire[];
  cells: TabularCellWire[];
}

function mapTabularReview(wire: TabularReviewWire): TabularReview {
  return {
    id: wire.id,
    gestoraId: wire.gestora_id,
    fundId: wire.fund_id ?? null,
    createdBy: wire.created_by ?? null,
    title: wire.title,
    status: wire.status,
    isOwner: wire.is_owner ?? null,
    sharedWithMe: wire.shared_with_me ?? null,
    sharedByEmail: wire.shared_by_email ?? null,
    createdAt: wire.created_at ?? null,
    updatedAt: wire.updated_at ?? null,
  };
}

function mapTabularDetail(wire: TabularReviewDetailWire): TabularReviewDetail {
  return {
    ...mapTabularReview(wire),
    columns: wire.columns.map((c) => ({
      id: c.id,
      reviewId: c.review_id,
      position: c.position,
      name: c.name,
      question: c.question,
      colType: c.col_type,
      options: c.options ?? null,
    })),
    documents: wire.documents.map((d) => ({
      id: d.id,
      reviewId: d.review_id,
      position: d.position,
      sourceKind: d.source_kind,
      sourceId: d.source_id,
      label: d.label ?? null,
    })),
    cells: wire.cells.map((c) => ({
      id: c.id,
      documentId: c.document_id,
      columnId: c.column_id,
      value: c.value ?? null,
      reasoning: c.reasoning ?? null,
      citation: c.citation ?? null,
      status: c.status,
      error: c.error ?? null,
    })),
  };
}

export async function getTabularReviews(): Promise<TabularReview[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubTabularReviews();
    });
  }
  const rows = await apiFetch<TabularReviewWire[]>(apiPaths.tabularReviews);
  return rows.map(mapTabularReview);
}

export async function getTabularReview(
  id: string,
): Promise<TabularReviewDetail> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const review = stub.stubTabularReview(id);
      if (!review) throw new ApiError(404, "Tabular review not found");
      return review;
    });
  }
  const wire = await apiFetch<TabularReviewDetailWire>(apiPaths.tabularReview(id));
  return mapTabularDetail(wire);
}

export interface CreateTabularReviewInput {
  title: string;
  fundId?: string | null;
  columns: TabularColumnInput[];
  documents: TabularDocumentOption[];
}

export async function createTabularReview(
  input: CreateTabularReviewInput,
): Promise<TabularReviewDetail> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      return stub.stubCreateTabularReview(input);
    });
  }
  const wire = await apiFetch<TabularReviewDetailWire>(apiPaths.tabularReviews, {
    method: "POST",
    body: {
      title: input.title,
      fund_id: input.fundId ?? null,
      columns: input.columns.map((c) => ({
        name: c.name,
        question: c.question,
        col_type: c.colType,
        options: c.options ?? null,
      })),
      documents: input.documents.map((d) => ({
        source_kind: d.sourceKind,
        source_id: d.sourceId,
        label: d.label,
      })),
    },
  });
  return mapTabularDetail(wire);
}

/** Enqueues extraction (202): poll getTabularReviewStatus while 'running'. */
export async function runTabularReview(id: string): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      stub.stubRunTabularReview(id);
    });
  }
  await apiFetch(apiPaths.tabularReviewRun(id), { method: "POST" });
}

export async function getTabularReviewStatus(
  id: string,
): Promise<TabularReviewStatusInfo> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 4);
      return stub.stubTabularReviewStatus(id);
    });
  }
  const res = await apiFetch<{
    id: string;
    status: TabularReviewStatusInfo["status"];
    cell_total: number;
    cell_done: number;
    cell_error: number;
  }>(apiPaths.tabularReviewStatus(id));
  return {
    id: res.id,
    status: res.status,
    cellTotal: res.cell_total,
    cellDone: res.cell_done,
    cellError: res.cell_error,
  };
}

export async function addTabularColumn(
  id: string,
  column: TabularColumnInput,
): Promise<TabularReviewDetail> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubAddTabularColumn(id, column);
    });
  }
  const wire = await apiFetch<TabularReviewDetailWire>(
    apiPaths.tabularReviewColumns(id),
    {
      method: "POST",
      body: {
        name: column.name,
        question: column.question,
        col_type: column.colType,
        options: column.options ?? null,
      },
    },
  );
  return mapTabularDetail(wire);
}

export async function deleteTabularColumn(
  id: string,
  columnId: string,
): Promise<TabularReviewDetail> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubDeleteTabularColumn(id, columnId);
    });
  }
  const wire = await apiFetch<TabularReviewDetailWire>(
    apiPaths.tabularReviewColumn(id, columnId),
    { method: "DELETE" },
  );
  return mapTabularDetail(wire);
}

/** CSV export of the grid (values only) as a Blob. */
export async function downloadTabularReviewCsv(id: string): Promise<Blob> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return new Blob([stub.stubTabularReviewCsv(id)], {
        type: "text/csv;charset=utf-8",
      });
    });
  }
  return fetchBlob(apiPaths.tabularReviewExport(id));
}

/** Documents the user can pick into a new review (precedents + generated). */
export async function getTabularDocumentOptions(): Promise<
  TabularDocumentOption[]
> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubTabularDocumentOptions();
    });
  }
  // Reuse the precedents list as the picker source; each active version is one
  // selectable document. Generated documents can be added later via the same
  // shape (source_kind=request_document).
  const precedents = await apiFetch<
    Array<{
      id: string;
      doc_type: string;
      versions?: Array<{ id: string; status: string; version_number: number }>;
    }>
  >(apiPaths.precedents);
  const options: TabularDocumentOption[] = [];
  for (const p of precedents) {
    for (const v of p.versions ?? []) {
      options.push({
        sourceKind: "precedent_version",
        sourceId: v.id,
        label: `${docTypeLabel(p.doc_type)} v${v.version_number}`,
      });
    }
  }
  return options;
}
