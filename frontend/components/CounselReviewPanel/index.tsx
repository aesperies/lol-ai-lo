"use client";

import { useEffect, useRef, useState } from "react";
import DocumentHtmlViewer from "@/components/DocumentHtmlViewer";
import { useI18n } from "@/components/I18nProvider";
import StatusBadge from "@/components/StatusBadge";
import { Banner, Button, Card, CardTitle, Textarea } from "@/components/ui";
import {
  addComment,
  downloadDocument,
  saveCounselEdit,
  triggerBlobDownload,
  uploadCounselDocx,
  validateRequest,
} from "@/lib/api";
import type { CounselComment, RequestItem, ReviewBundle } from "@/lib/types";

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\n", "<br/>");
}

/**
 * Step 6 of the master workflow — COUNSEL REVIEW (Exit B):
 * - Draft + redline side by side (real rendered HTML via DocumentHtmlViewer)
 * - Rich-text inline editor (contentEditable, no heavy deps)
 * - .docx download / upload
 * - Comments / flags
 * - [Validar y Entregar] → validated → delivered; doc enters the precedent
 *   library automatically (counsel validation sufficient, no admin approval)
 */
export default function CounselReviewPanel({
  bundle,
  onValidated,
}: {
  bundle: ReviewBundle;
  onValidated?: (req: RequestItem) => void;
}) {
  const { t } = useI18n();
  const { request, draftText } = bundle;

  const editorRef = useRef<HTMLDivElement>(null);
  const [comments, setComments] = useState<CounselComment[]>(bundle.comments);
  const [newComment, setNewComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validated, setValidated] = useState(
    request.status === "validated" || request.status === "delivered",
  );

  // Seed the contentEditable editor with the draft text once.
  useEffect(() => {
    if (editorRef.current && editorRef.current.innerHTML === "") {
      editorRef.current.innerHTML = escapeHtml(draftText);
    }
  }, [draftText]);

  function exec(command: "bold" | "italic" | "underline") {
    // contentEditable formatting without external dependencies.
    document.execCommand(command);
    editorRef.current?.focus();
  }

  async function handleDownload() {
    setError(null);
    try {
      const blob = await downloadDocument(request.id, "draft");
      triggerBlobDownload(blob, `${request.id}_draft.docx`);
    } catch {
      setError(t("common.error"));
    }
  }

  async function handleUpload(file: File) {
    setBusy("upload");
    setError(null);
    try {
      await uploadCounselDocx(request.id, file);
      setNotice(t("counsel.uploadDone"));
    } catch {
      setError(t("common.error"));
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveEdit() {
    setBusy("save");
    setError(null);
    try {
      const text = editorRef.current?.innerText ?? "";
      await saveCounselEdit(request.id, text);
      setNotice(t("counsel.editSaved"));
    } catch {
      setError(t("common.error"));
    } finally {
      setBusy(null);
    }
  }

  async function handleAddComment() {
    const text = newComment.trim();
    if (!text) return;
    setBusy("comment");
    setError(null);
    try {
      const comment = await addComment(request.id, text);
      setComments((prev) => [...prev, comment]);
      setNewComment("");
    } catch {
      setError(t("common.error"));
    } finally {
      setBusy(null);
    }
  }

  async function handleValidate() {
    setBusy("validate");
    setError(null);
    try {
      const updated = await validateRequest(request.id);
      setValidated(true);
      setNotice(t("counsel.validatedOk"));
      onValidated?.(updated);
    } catch {
      setError(t("common.error"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <CardTitle>{t("counsel.reviewTitle")}</CardTitle>
            <p className="mt-1 text-sm text-slate-500">
              {request.docTypeLabel ?? request.docType} — {request.fundName}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">
              {t("counsel.requestedBy")}: {request.requestedByName ?? request.userId}
            </p>
          </div>
          <StatusBadge status={validated ? "validated" : request.status} />
        </div>
        {request.fallbackLevel === 3 ? (
          <Banner tone="danger" className="mt-4">
            {t("viewer.level3Warning")}
          </Banner>
        ) : null}
      </Card>

      {notice ? <Banner tone="success">{notice}</Banner> : null}
      {error ? <Banner tone="danger">{error}</Banner> : null}

      {/* Draft + redline side by side — real rendered HTML (view mode) */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle className="mb-3">{t("counsel.draftPane")}</CardTitle>
          <DocumentHtmlViewer requestId={request.id} versionType="draft" />
        </Card>
        <Card>
          <CardTitle className="mb-3">{t("counsel.redlinePane")}</CardTitle>
          <DocumentHtmlViewer requestId={request.id} versionType="redline" />
        </Card>
      </div>

      {/* Inline rich-text editor */}
      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>{t("counsel.editorTitle")}</CardTitle>
            <p className="mt-0.5 text-xs text-slate-500">{t("counsel.editorHint")}</p>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="ghost" className="px-2 py-1 font-bold" onClick={() => exec("bold")}>
              B
            </Button>
            <Button variant="ghost" className="px-2 py-1 italic" onClick={() => exec("italic")}>
              I
            </Button>
            <Button variant="ghost" className="px-2 py-1 underline" onClick={() => exec("underline")}>
              U
            </Button>
          </div>
        </div>
        <div
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          className="counsel-editor font-serif"
          data-placeholder={t("counsel.editorPlaceholder")}
        />
        <div className="mt-3 flex flex-wrap gap-3">
          <Button
            variant="secondary"
            disabled={busy !== null}
            onClick={() => void handleSaveEdit()}
          >
            {t("counsel.saveEdit")}
          </Button>
          <Button variant="secondary" onClick={() => void handleDownload()}>
            ⬇ {t("counsel.downloadDocx")}
          </Button>
          <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50">
            ⬆ {t("counsel.uploadDocx")}
            <input
              type="file"
              accept=".docx"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleUpload(file);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      </Card>

      {/* Comments */}
      <Card>
        <CardTitle className="mb-3">{t("counsel.comments")}</CardTitle>
        {comments.length === 0 ? (
          <p className="text-sm text-slate-400">{t("counsel.noComments")}</p>
        ) : (
          <ul className="space-y-3">
            {comments.map((c) => (
              <li key={c.id} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                <p className="text-sm text-slate-700">{c.text}</p>
                <p className="mt-1 text-xs text-slate-400">
                  {c.author} — {new Date(c.createdAt).toLocaleString()}
                </p>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-4 flex gap-2">
          <Textarea
            rows={2}
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder={t("counsel.commentPlaceholder")}
          />
          <Button
            variant="secondary"
            disabled={busy !== null || newComment.trim() === ""}
            onClick={() => void handleAddComment()}
          >
            {t("counsel.addComment")}
          </Button>
        </div>
      </Card>

      {/* Validate & deliver */}
      <div className="flex justify-end">
        <Button
          disabled={busy !== null || validated}
          onClick={() => void handleValidate()}
        >
          ✓ {t("counsel.validate")}
        </Button>
      </div>
    </div>
  );
}
