"use client";

/** Admin — per-gestora model configuration (BYO provider/model/keys). */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardTitle,
  Input,
  Label,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import { getGestoras, getModelConfig, updateModelConfig } from "@/lib/api";
import type { Gestora, ModelConfig } from "@/lib/types";

const LLM_PROVIDERS = ["", "ollama", "anthropic", "mistral"];
const EMBEDDING_PROVIDERS = ["", "ollama", "openai"];

export default function AdminModelConfigPage() {
  const { t } = useI18n();

  const [gestoras, setGestoras] = useState<Gestora[] | null>(null);
  const [gestoraId, setGestoraId] = useState("");
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Form fields (provider/model/url are inherited-when-empty; keys are write-only).
  const [llmProvider, setLlmProvider] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [embeddingProvider, setEmbeddingProvider] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [mistralKey, setMistralKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");

  useEffect(() => {
    void getGestoras()
      .then((list) => {
        setGestoras(list);
        if (list.length > 0) setGestoraId((prev) => prev || list[0].id);
      })
      .catch(() => setGestoras([]));
  }, []);

  useEffect(() => {
    if (!gestoraId) return;
    setConfig(null);
    void getModelConfig(gestoraId)
      .then((c) => {
        setConfig(c);
        setLlmProvider(c.llmProvider ?? "");
        setLlmModel(c.llmModel ?? "");
        setEmbeddingProvider(c.embeddingProvider ?? "");
        setEmbeddingModel(c.embeddingModel ?? "");
        setOllamaBaseUrl(c.ollamaBaseUrl ?? "");
        setAnthropicKey("");
        setMistralKey("");
        setOpenaiKey("");
      })
      .catch(() => setConfig(null));
  }, [gestoraId]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const saved = await updateModelConfig(gestoraId, {
        llmProvider,
        llmModel,
        embeddingProvider,
        embeddingModel,
        ollamaBaseUrl,
        // Only send keys when the admin typed something (write-only).
        ...(anthropicKey ? { anthropicApiKey: anthropicKey } : {}),
        ...(mistralKey ? { mistralApiKey: mistralKey } : {}),
        ...(openaiKey ? { openaiApiKey: openaiKey } : {}),
      });
      setConfig(saved);
      setAnthropicKey("");
      setMistralKey("");
      setOpenaiKey("");
      setNotice(t("modelconfig.saved"));
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title={t("modelconfig.title")}
        subtitle={t("modelconfig.subtitle")}
      />

      {notice ? (
        <Banner tone="info" className="mb-6">
          {notice}
        </Banner>
      ) : null}

      <Card className="max-w-2xl">
        <div className="mb-4 max-w-sm">
          <Label htmlFor="mc-gestora">{t("modelconfig.gestora")}</Label>
          <Select
            id="mc-gestora"
            value={gestoraId}
            onChange={(e) => setGestoraId(e.target.value)}
          >
            {(gestoras ?? []).map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </Select>
        </div>

        {config === null ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : (
          <form className="space-y-5" onSubmit={handleSave}>
            <Badge tone={config.isDefault ? "slate" : "indigo"}>
              {config.isDefault
                ? t("modelconfig.usingDefault")
                : t("modelconfig.usingCustom")}
            </Badge>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="mc-llm-provider">
                  {t("modelconfig.llmProvider")}
                </Label>
                <Select
                  id="mc-llm-provider"
                  value={llmProvider}
                  onChange={(e) => setLlmProvider(e.target.value)}
                >
                  {LLM_PROVIDERS.map((p) => (
                    <option key={p} value={p}>
                      {p || t("modelconfig.inherit")}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="mc-llm-model">{t("modelconfig.llmModel")}</Label>
                <Input
                  id="mc-llm-model"
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                  placeholder="qwen2.5:14b-instruct"
                />
              </div>
              <div>
                <Label htmlFor="mc-emb-provider">
                  {t("modelconfig.embeddingProvider")}
                </Label>
                <Select
                  id="mc-emb-provider"
                  value={embeddingProvider}
                  onChange={(e) => setEmbeddingProvider(e.target.value)}
                >
                  {EMBEDDING_PROVIDERS.map((p) => (
                    <option key={p} value={p}>
                      {p || t("modelconfig.inherit")}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="mc-emb-model">
                  {t("modelconfig.embeddingModel")}
                </Label>
                <Input
                  id="mc-emb-model"
                  value={embeddingModel}
                  onChange={(e) => setEmbeddingModel(e.target.value)}
                  placeholder="bge-m3"
                />
              </div>
            </div>

            <div>
              <Label htmlFor="mc-ollama-url">
                {t("modelconfig.ollamaBaseUrl")}
              </Label>
              <Input
                id="mc-ollama-url"
                value={ollamaBaseUrl}
                onChange={(e) => setOllamaBaseUrl(e.target.value)}
                placeholder="http://localhost:11434"
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="mc-anthropic-key">
                    {t("modelconfig.anthropicKey")}
                  </Label>
                  <Badge tone={config.anthropicKeySet ? "emerald" : "slate"}>
                    {config.anthropicKeySet
                      ? t("modelconfig.keySet")
                      : t("modelconfig.keyUnset")}
                  </Badge>
                </div>
                <Input
                  id="mc-anthropic-key"
                  type="password"
                  value={anthropicKey}
                  onChange={(e) => setAnthropicKey(e.target.value)}
                  placeholder={
                    config.anthropicKeySet
                      ? t("modelconfig.keyPlaceholderSet")
                      : ""
                  }
                />
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="mc-mistral-key">
                    {t("modelconfig.mistralKey")}
                  </Label>
                  <Badge tone={config.mistralKeySet ? "emerald" : "slate"}>
                    {config.mistralKeySet
                      ? t("modelconfig.keySet")
                      : t("modelconfig.keyUnset")}
                  </Badge>
                </div>
                <Input
                  id="mc-mistral-key"
                  type="password"
                  value={mistralKey}
                  onChange={(e) => setMistralKey(e.target.value)}
                  placeholder={
                    config.mistralKeySet ? t("modelconfig.keyPlaceholderSet") : ""
                  }
                />
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="mc-openai-key">
                    {t("modelconfig.openaiKey")}
                  </Label>
                  <Badge tone={config.openaiKeySet ? "emerald" : "slate"}>
                    {config.openaiKeySet
                      ? t("modelconfig.keySet")
                      : t("modelconfig.keyUnset")}
                  </Badge>
                </div>
                <Input
                  id="mc-openai-key"
                  type="password"
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  placeholder={
                    config.openaiKeySet ? t("modelconfig.keyPlaceholderSet") : ""
                  }
                />
              </div>
            </div>

            <Button type="submit" disabled={busy || !gestoraId}>
              {t("modelconfig.save")}
            </Button>
          </form>
        )}
      </Card>
    </div>
  );
}
