"use client";

/* ------------------------------------------------------------------ */
/* Review playbooks CRUD (admin) — gestora-siloed critic rules          */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type { Branch, DraftingLesson, ReviewPlaybook } from "@/lib/types";
import {
  STUB_LATENCY,
  apiFetch,
  apiPaths,
  fetchMultipart,
  fetchVoid,
  stubCall,
} from "./http";

interface ReviewPlaybookWire {
  id: string;
  gestora_id: string;
  branch?: string | null;
  doc_type?: string | null;
  title: string;
  content: string;
  file_path?: string | null;
  is_active: boolean;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

function mapPlaybook(wire: ReviewPlaybookWire): ReviewPlaybook {
  return {
    id: wire.id,
    gestoraId: wire.gestora_id,
    branch: (wire.branch ?? null) as ReviewPlaybook["branch"],
    docType: wire.doc_type ?? null,
    title: wire.title,
    content: wire.content,
    filePath: wire.file_path ?? null,
    isActive: wire.is_active,
    createdBy: wire.created_by ?? null,
    createdAt: wire.created_at ?? null,
    updatedAt: wire.updated_at ?? null,
  };
}

/** Lists review playbooks for a gestora (admin/counsel cross-gestora). */
export async function getPlaybooks(
  gestoraId: string,
): Promise<ReviewPlaybook[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubPlaybooks(gestoraId);
    });
  }
  const rows = await apiFetch<ReviewPlaybookWire[]>(apiPaths.playbooks(gestoraId));
  return rows.map(mapPlaybook);
}

/** Creates a playbook (multipart: text fields + optional file attachment). */
export async function createPlaybook(input: {
  gestoraId: string;
  title: string;
  content: string;
  branch?: string | null;
  docType?: string | null;
  file?: File | null;
}): Promise<ReviewPlaybook> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubCreatePlaybook(input);
    });
  }
  const form = new FormData();
  form.append("gestora_id", input.gestoraId);
  form.append("title", input.title);
  form.append("content", input.content);
  if (input.branch) form.append("branch", input.branch);
  if (input.docType) form.append("doc_type", input.docType);
  if (input.file) form.append("file", input.file);
  const res = await fetchMultipart(apiPaths.playbooks(), form);
  return mapPlaybook((await res.json()) as ReviewPlaybookWire);
}

/** Partial update of a playbook (title / content / scope). */
export async function updatePlaybook(
  id: string,
  fields: {
    title?: string;
    content?: string;
    branch?: string | null;
    docType?: string | null;
  },
): Promise<ReviewPlaybook> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubUpdatePlaybook(id, fields);
    });
  }
  const body: Record<string, unknown> = {};
  if (fields.title !== undefined) body.title = fields.title;
  if (fields.content !== undefined) body.content = fields.content;
  if (fields.branch !== undefined) body.branch = fields.branch;
  if (fields.docType !== undefined) body.doc_type = fields.docType;
  const wire = await apiFetch<ReviewPlaybookWire>(apiPaths.playbook(id), {
    method: "PATCH",
    body,
  });
  return mapPlaybook(wire);
}

/** Activates or deactivates a playbook. */
export async function setPlaybookActive(
  id: string,
  active: boolean,
): Promise<ReviewPlaybook> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubSetPlaybookActive(id, active);
    });
  }
  const wire = await apiFetch<ReviewPlaybookWire>(
    active ? apiPaths.playbookActivate(id) : apiPaths.playbookDeactivate(id),
    { method: "POST" },
  );
  return mapPlaybook(wire);
}

export async function deletePlaybook(id: string): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      stub.stubDeletePlaybook(id);
    });
  }
  await fetchVoid(apiPaths.playbook(id), { method: "DELETE" });
}

/* ------------------------------------------------------------------ */
/* Drafting lessons (admin-only, gestora-siloed)                       */
/* ------------------------------------------------------------------ */

interface DraftingLessonWire {
  id: string;
  gestora_id: string;
  branch: Branch;
  doc_type?: string | null;
  lesson: string;
  weight: number;
  created_at?: string | null;
}

/** The accumulated drafting lessons learned for one gestora (admin-only).
 * Optional branch filter. */
export async function getGestoraLessons(
  gestoraId: string,
  branch?: string,
): Promise<DraftingLesson[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubGestoraLessons(gestoraId, branch);
    });
  }
  const rows = await apiFetch<DraftingLessonWire[]>(
    apiPaths.gestoraLessons(gestoraId, branch),
  );
  return rows.map((r) => ({
    id: r.id,
    gestoraId: r.gestora_id,
    branch: r.branch,
    docType: r.doc_type ?? null,
    lesson: r.lesson,
    weight: r.weight,
    createdAt: r.created_at ?? null,
  }));
}
