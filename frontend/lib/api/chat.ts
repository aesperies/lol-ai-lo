"use client";

/* ------------------------------------------------------------------ */
/* Chat Q&A sobre el RAG de la gestora (021_chat.sql)                  */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type {
  ChatCitation,
  ChatConversation,
  ChatMessage,
  ChatStreamEvent,
  ChatVerification,
} from "@/lib/types";
import {
  STUB_LATENCY,
  apiFetch,
  apiPaths,
  fetchSse,
  fetchVoid,
  stubCall,
} from "./http";

/* ------------------------------ wire ------------------------------ */

interface ChatConversationWire {
  id: string;
  title?: string | null;
  created_at?: string | null;
}

interface ChatCitationWire {
  index?: number;
  precedent_id?: string;
  precedent_version_id?: string;
  doc_type?: string;
  source?: string;
  snippet?: string;
}

interface ChatMessageWire {
  id: string;
  role: string;
  content: string;
  citations?: ChatCitationWire[] | null;
  verification?: ChatVerification | null;
  created_at?: string | null;
}

function mapConversation(wire: ChatConversationWire): ChatConversation {
  return {
    id: wire.id,
    title: wire.title ?? null,
    createdAt: wire.created_at ?? null,
  };
}

function mapCitation(wire: ChatCitationWire): ChatCitation {
  return {
    index: wire.index ?? 0,
    precedentId: wire.precedent_id ?? "",
    precedentVersionId: wire.precedent_version_id ?? "",
    docType: wire.doc_type ?? "",
    source: wire.source ?? "",
    snippet: wire.snippet ?? "",
  };
}

function mapMessage(wire: ChatMessageWire): ChatMessage {
  return {
    id: wire.id,
    role: wire.role === "user" ? "user" : "assistant",
    content: wire.content,
    citations: (wire.citations ?? []).map(mapCitation),
    verification: wire.verification ?? null,
    createdAt: wire.created_at ?? null,
  };
}

/** Un evento crudo del SSE (snake_case) al tipo de la UI. */
function mapEvent(raw: Record<string, unknown>): ChatStreamEvent | null {
  switch (raw.type) {
    case "sources":
      return {
        type: "sources",
        citations: ((raw.citations as ChatCitationWire[]) ?? []).map(mapCitation),
      };
    case "delta":
      return { type: "delta", text: String(raw.text ?? "") };
    case "verification":
      return {
        type: "verification",
        verification: {
          findings:
            (raw.findings as ChatVerification["findings"]) ?? [],
          provider: (raw.provider as string) ?? null,
          model: (raw.model as string) ?? null,
        },
      };
    case "done":
      return { type: "done", messageId: String(raw.message_id ?? "") };
    case "error":
      return { type: "error", detail: String(raw.detail ?? "") };
    default:
      return null;
  }
}

/* --------------------------- functions ---------------------------- */

export async function getChatConversations(): Promise<ChatConversation[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubChatConversations();
    });
  }
  const rows = await apiFetch<ChatConversationWire[]>(apiPaths.chatConversations);
  return rows.map(mapConversation);
}

export async function createChatConversation(): Promise<ChatConversation> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubCreateChatConversation();
    });
  }
  const row = await apiFetch<ChatConversationWire>(apiPaths.chatConversations, {
    method: "POST",
    body: {},
  });
  return mapConversation(row);
}

export async function getChatMessages(
  conversationId: string,
): Promise<ChatMessage[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubChatMessages(conversationId);
    });
  }
  const rows = await apiFetch<ChatMessageWire[]>(
    apiPaths.chatMessages(conversationId),
  );
  return rows.map(mapMessage);
}

export async function deleteChatConversation(
  conversationId: string,
): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      stub.stubDeleteChatConversation(conversationId);
    });
  }
  await fetchVoid(apiPaths.chatConversation(conversationId));
}

/** Envía una pregunta y consume el stream SSE (sources → delta* → done). */
export async function sendChatMessage(
  conversationId: string,
  content: string,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  if (isStubMode()) {
    return stubCall((stub) =>
      stub.stubSendChatMessage(conversationId, content, onEvent),
    );
  }
  await fetchSse(apiPaths.chatMessages(conversationId), { content }, (raw) => {
    const event = mapEvent(raw as Record<string, unknown>);
    if (event) onEvent(event);
  });
}
