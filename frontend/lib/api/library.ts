"use client";

/* ------------------------------------------------------------------ */
/* Biblioteca del cliente (022)                                        */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type { LibraryItem, PrecedentVersionHtml } from "@/lib/types";
import {
  STUB_LATENCY,
  apiFetch,
  apiPaths,
  fetchMultipart,
  stubCall,
} from "./http";

interface LibraryItemWire {
  id: string;
  doc_type: string;
  language?: string | null;
  source?: string | null;
  fund_id?: string | null;
  fund_name?: string | null;
  document_date?: string | null;
  created_at?: string | null;
  version_id?: string | null;
  version_status?: string | null;
  version_number?: number | null;
  is_docx?: boolean | null;
}

function mapItem(wire: LibraryItemWire): LibraryItem {
  return {
    id: wire.id,
    docType: wire.doc_type,
    language: wire.language ?? "",
    source: wire.source ?? "",
    fundId: wire.fund_id ?? null,
    fundName: wire.fund_name ?? null,
    documentDate: wire.document_date ?? null,
    createdAt: wire.created_at ?? null,
    versionId: wire.version_id ?? null,
    versionStatus:
      (wire.version_status as LibraryItem["versionStatus"]) ?? null,
    versionNumber: wire.version_number ?? null,
    isDocx: wire.is_docx ?? false,
  };
}

/** Los documentos del silo de la gestora del usuario. */
export async function getMyLibrary(): Promise<LibraryItem[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubMyLibrary();
    });
  }
  const rows = await apiFetch<LibraryItemWire[]>(apiPaths.myLibrary);
  return rows.map(mapItem);
}

/** Sube un documento a la biblioteca propia (entra como borrador). */
export async function uploadLibraryDocument(input: {
  file: File;
  docType: string;
  language: string;
  fundId?: string | null;
  documentDate?: string | null;
}): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      stub.stubUploadLibraryDocument(input.file.name, input.docType, {
        fundId: input.fundId ?? null,
        documentDate: input.documentDate ?? null,
      });
    });
  }
  const form = new FormData();
  form.append("file", input.file);
  form.append("doc_type", input.docType);
  form.append("language", input.language);
  if (input.fundId) form.append("fund_id", input.fundId);
  if (input.documentDate) form.append("document_date", input.documentDate);
  await fetchMultipart(apiPaths.myLibraryUpload, form);
}

/** HTML seguro de una versión de precedente (citas clicables del chat). */
export async function getPrecedentVersionHtml(
  versionId: string,
): Promise<PrecedentVersionHtml> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubPrecedentVersionHtml(versionId);
    });
  }
  const data = await apiFetch<{ html: string; doc_type: string; version_id: string }>(
    apiPaths.precedentVersionHtml(versionId),
  );
  return { html: data.html, docType: data.doc_type, versionId: data.version_id };
}
