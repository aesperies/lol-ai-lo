"use client";

/**
 * Chat Q&A sobre el RAG de la gestora (021_chat.sql).
 *
 * El cliente pregunta en lenguaje natural a los precedentes/modelos de su
 * gestora. La respuesta llega por SSE (sources → delta* → verification? →
 * done): las citas se pintan ANTES de que empiece el texto y cada respuesta
 * termina con sus fuentes y, si procede, el aviso del verificador de
 * grounding.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import PrecedentHtmlModal from "@/components/PrecedentHtmlModal";
import { Banner, Button, Card, PageHeader, Spinner, Textarea } from "@/components/ui";
import {
  createChatConversation,
  deleteChatConversation,
  getChatConversations,
  getChatMessages,
  sendChatFeedback,
  sendChatMessage,
} from "@/lib/api";
import { docTypeLabel } from "@/lib/catalog";
import type {
  ChatCitation,
  ChatConversation,
  ChatMessage,
  ChatVerification,
} from "@/lib/types";

/* ------------------------------------------------------------------ */
/* Subcomponents                                                       */
/* ------------------------------------------------------------------ */

function CitationChips({
  citations,
  onOpen,
}: {
  citations: ChatCitation[];
  onOpen?: (citation: ChatCitation) => void;
}) {
  const { t } = useI18n();
  if (citations.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] font-medium uppercase tracking-wide text-ink-400">
        {t("chat.sources")}
      </span>
      {citations.map((citation) => {
        const label = citation.section
          ? `${docTypeLabel(citation.docType)} · ${citation.section}`
          : docTypeLabel(citation.docType);
        const used = citation.used !== false;
        return (
          <button
            key={`${citation.index}-${citation.precedentVersionId}`}
            type="button"
            title={
              citation.used
                ? `${t("chat.sourceUsed")} — ${citation.snippet}`
                : citation.snippet
            }
            onClick={onOpen ? () => onOpen(citation) : undefined}
            className={
              (used
                ? "bg-brand-50 text-brand-800 ring-brand-200 "
                : "bg-ink-100 text-ink-500 ring-ink-200 opacity-80 ") +
              "inline-flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-xs ring-1 ring-inset transition-colors hover:ring-brand-400"
            }
          >
            <span className="font-semibold">[{citation.index}]</span>
            <span className="max-w-[16rem] truncate">{label}</span>
          </button>
        );
      })}
    </div>
  );
}

function FeedbackButtons({
  message,
  onFeedback,
}: {
  message: ChatMessage;
  onFeedback: (messageId: string, feedback: "up" | "down") => void;
}) {
  const { t } = useI18n();
  if (message.id.startsWith("local-")) return null;
  return (
    <div className="mt-2 flex items-center gap-1">
      {(["up", "down"] as const).map((kind) => {
        const active = message.feedback === kind;
        return (
          <button
            key={kind}
            type="button"
            aria-label={kind === "up" ? t("chat.feedbackUp") : t("chat.feedbackDown")}
            title={kind === "up" ? t("chat.feedbackUp") : t("chat.feedbackDown")}
            onClick={() => onFeedback(message.id, kind)}
            className={
              (active
                ? "bg-brand-50 text-brand-700 "
                : "text-ink-300 hover:bg-ink-100 hover:text-ink-600 ") +
              "inline-flex h-6 w-6 items-center justify-center rounded-md transition-colors"
            }
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill={active ? "currentColor" : "none"}
              aria-hidden="true"
              className={kind === "down" ? "rotate-180" : undefined}
            >
              <path
                d="M7 11v9H4a1 1 0 01-1-1v-7a1 1 0 011-1h3zm0 0l4-7a2 2 0 012 2v4h5a2 2 0 012 2.3l-1 6A2 2 0 0117 19h-8"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        );
      })}
    </div>
  );
}

function VerificationNote({
  verification,
}: {
  verification: ChatVerification | null;
}) {
  const { t } = useI18n();
  if (!verification || verification.findings.length === 0) return null;
  return (
    <Banner tone="warning" className="mt-2">
      {t("chat.verificationWarning", {
        count: verification.findings.length,
      })}
      <ul className="mt-1 list-disc pl-5 text-xs">
        {verification.findings.map((finding, i) => (
          <li key={i}>
            «{finding.quote}» — {finding.problem}
          </li>
        ))}
      </ul>
    </Banner>
  );
}

function MessageBubble({
  message,
  onOpenCitation,
  onFeedback,
}: {
  message: ChatMessage;
  onOpenCitation: (citation: ChatCitation) => void;
  onFeedback: (messageId: string, feedback: "up" | "down") => void;
}) {
  const isUser = message.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-2xl rounded-br-sm bg-brand-700 px-4 py-2.5 text-sm text-white dark:text-brand-900"
            : "max-w-[85%] rounded-2xl rounded-bl-sm border border-ink-200 bg-surface px-4 py-2.5 text-sm text-ink-800 shadow-card"
        }
      >
        <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        {!isUser ? (
          <>
            <CitationChips citations={message.citations} onOpen={onOpenCitation} />
            <VerificationNote verification={message.verification} />
            <FeedbackButtons message={message} onFeedback={onFeedback} />
          </>
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function ChatPage() {
  const { t } = useI18n();
  const [conversations, setConversations] = useState<ChatConversation[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamCitations, setStreamCitations] = useState<ChatCitation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [viewingCitation, setViewingCitation] = useState<ChatCitation | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const handleFeedback = useCallback(
    (messageId: string, feedback: "up" | "down") => {
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, feedback } : m)),
      );
      void sendChatFeedback(messageId, feedback).catch(() => {
        /* telemetría: un fallo no debe molestar al usuario */
      });
    },
    [],
  );

  useEffect(() => {
    void getChatConversations()
      .then((rows) => {
        setConversations(rows);
        if (rows.length > 0) setActiveId(rows[0].id);
      })
      .catch(() => setConversations([]));
  }, []);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    void getChatMessages(activeId)
      .then(setMessages)
      .catch(() => setMessages([]));
  }, [activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamText]);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await getChatConversations());
    } catch {
      /* la lista es informativa; el hilo activo sigue funcionando */
    }
  }, []);

  async function startConversation() {
    setError(null);
    try {
      const conversation = await createChatConversation();
      setConversations((prev) => [conversation, ...(prev ?? [])]);
      setActiveId(conversation.id);
    } catch {
      setError(t("common.error"));
    }
  }

  async function removeConversation(id: string) {
    try {
      await deleteChatConversation(id);
      setConversations((prev) => (prev ?? []).filter((c) => c.id !== id));
      if (activeId === id) setActiveId(null);
    } catch {
      setError(t("common.error"));
    }
  }

  async function send() {
    const content = input.trim();
    if (!content || sending) return;
    setError(null);
    setSending(true);
    setInput("");
    setStreamText("");
    setStreamCitations([]);

    let conversationId = activeId;
    try {
      if (!conversationId) {
        const conversation = await createChatConversation();
        setConversations((prev) => [conversation, ...(prev ?? [])]);
        setActiveId(conversation.id);
        conversationId = conversation.id;
      }

      const userMessage: ChatMessage = {
        id: `local-${Date.now()}`,
        role: "user",
        content,
        citations: [],
        verification: null,
        feedback: null,
        createdAt: null,
      };
      setMessages((prev) => [...prev, userMessage]);

      let accumulated = "";
      let citations: ChatCitation[] = [];
      let verification: ChatVerification | null = null;
      let messageId: string | null = null;
      let failed: string | null = null;

      await sendChatMessage(conversationId, content, (event) => {
        switch (event.type) {
          case "sources":
            citations = event.citations;
            setStreamCitations(event.citations);
            break;
          case "delta":
            accumulated += event.text;
            setStreamText(accumulated);
            break;
          case "verification":
            verification = event.verification;
            break;
          case "error":
            failed = event.detail;
            break;
          case "done":
            messageId = event.messageId;
            citations = citations.map((c) => ({
              ...c,
              used: event.usedIndexes.includes(c.index),
            }));
            break;
        }
      });

      if (failed !== null) {
        setError(t("chat.error"));
      } else {
        setMessages((prev) => [
          ...prev,
          {
            // El id real (evento done) habilita el feedback inmediato.
            id: messageId ?? `local-${Date.now()}-assistant`,
            role: "assistant",
            content: accumulated,
            citations,
            verification,
            feedback: null,
            createdAt: null,
          },
        ]);
        void refreshConversations();
      }
    } catch {
      setError(t("chat.error"));
    } finally {
      setStreamText("");
      setStreamCitations([]);
      setSending(false);
    }
  }

  if (conversations === null) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("chat.title")}
        subtitle={t("chat.subtitle")}
        actions={
          <Button variant="secondary" onClick={() => void startConversation()}>
            {t("chat.newConversation")}
          </Button>
        }
      />

      {error ? (
        <Banner tone="danger" className="mb-4">
          {error}
        </Banner>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        {/* Conversation list */}
        <Card className="h-fit p-3">
          {conversations.length === 0 ? (
            <p className="px-2 py-3 text-sm text-ink-400">
              {t("chat.noConversations")}
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {conversations.map((conversation) => {
                const active = conversation.id === activeId;
                return (
                  <li key={conversation.id} className="group flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setActiveId(conversation.id)}
                      className={
                        active
                          ? "flex-1 truncate rounded-lg bg-brand-50 px-3 py-2 text-left text-sm font-medium text-brand-800"
                          : "flex-1 truncate rounded-lg px-3 py-2 text-left text-sm text-ink-600 hover:bg-ink-100"
                      }
                    >
                      {conversation.title ?? t("chat.untitled")}
                    </button>
                    <button
                      type="button"
                      aria-label={t("chat.deleteConversation")}
                      onClick={() => void removeConversation(conversation.id)}
                      className="hidden h-7 w-7 items-center justify-center rounded-lg text-ink-400 hover:bg-red-50 hover:text-red-600 group-hover:inline-flex"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <path
                          d="M4 7h16M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m1 0v12a2 2 0 01-2 2H8a2 2 0 01-2-2V7"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                        />
                      </svg>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        {/* Thread */}
        <Card className="flex min-h-[60vh] flex-col p-0">
          <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6">
            {messages.length === 0 && !sending ? (
              <p className="m-auto max-w-sm text-center text-sm text-ink-400">
                {t("chat.emptyThread")}
              </p>
            ) : (
              messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  onOpenCitation={setViewingCitation}
                  onFeedback={handleFeedback}
                />
              ))
            )}

            {sending ? (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-ink-200 bg-surface px-4 py-2.5 text-sm text-ink-800 shadow-card">
                  {streamText ? (
                    <p className="whitespace-pre-wrap leading-relaxed">
                      {streamText}
                      <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-brand-500 align-text-bottom" />
                    </p>
                  ) : (
                    <span className="inline-flex items-center gap-2 text-ink-400">
                      <Spinner className="h-4 w-4" />
                      {t("chat.thinking")}
                    </span>
                  )}
                  <CitationChips
                    citations={streamCitations}
                    onOpen={setViewingCitation}
                  />
                </div>
              </div>
            ) : null}
            <div ref={bottomRef} />
          </div>

          <form
            className="border-t border-ink-200 p-4"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <div className="flex items-end gap-2">
              <Textarea
                rows={2}
                maxLength={4000}
                value={input}
                placeholder={t("chat.placeholder")}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void send();
                  }
                }}
                className="resize-none"
              />
              <Button type="submit" disabled={sending || !input.trim()}>
                {t("chat.send")}
              </Button>
            </div>
            <p className="mt-2 text-xs text-ink-400">{t("chat.disclaimer")}</p>
          </form>
        </Card>
      </div>

      <PrecedentHtmlModal
        versionId={viewingCitation?.precedentVersionId ?? null}
        title={
          viewingCitation
            ? viewingCitation.section
              ? `${docTypeLabel(viewingCitation.docType)} · ${viewingCitation.section}`
              : docTypeLabel(viewingCitation.docType)
            : undefined
        }
        fallback={viewingCitation?.snippet}
        onClose={() => setViewingCitation(null)}
      />
    </div>
  );
}
