# Local models on Apple Silicon (16 GB RAM)

A practical guide to running Lol-AI-lo's LLM and embeddings **locally** via [Ollama](https://ollama.com), tuned for an Apple Silicon Mac (M1/M2/M3/M4) with **16 GB of unified memory**.

## Why local for legal documents

- **Confidentiality.** Precedents are a gestora's most sensitive asset. With local inference, precedent text and client data are never transmitted to a third-party API — they stay on the machine doing the work.
- **GDPR posture.** Keeping generation and embedding on-device avoids sending personal data to external processors, which simplifies the data-protection story (see [GDPR.md](GDPR.md)). No cloud LLM contract, no transfer, no extra processor in the chain.
- **No per-token cost / no rate limits.** Run as many generations as the hardware allows.

The trade-off is quality and speed versus the largest cloud models. For most fund/corporate documents, a well-chosen local model is more than adequate — and you can always flip an individual request path to a cloud provider (see the README "Switching to cloud providers").

## RAM budget reality on 16 GB

Apple Silicon uses **unified memory** shared between CPU, GPU and everything else. On a 16 GB Mac:

- macOS itself + a browser + your editor easily consume **4–6 GB**.
- The Next.js dev server and the Python/uvicorn backend add **~1–2 GB**.
- That leaves roughly **~10–11 GB usable** for the model weights + KV cache (context).

Practical implication: a **~9 GB** model (a 14B at q4) *fits* but is **tight** — close other heavy apps, or you risk memory pressure and swap, which tanks tokens/sec. A **~5 GB** model (a 7–8B at q4) is **comfortable** and leaves real headroom. The embedding model (`bge-m3`, ~1.2 GB) runs alongside the generation model, so budget for both being resident.

> Quantization shorthand: `q4_K_M` is the usual sweet spot (smallest with good quality). `q5_K_M` is a bit larger and slightly higher quality — only choose it if you have the RAM to spare. On 16 GB, prefer q4 for anything 13B+.

## Generation model recommendations

Set with `OLLAMA_LLM_MODEL`. Sizes are approximate q4_K_M download/RAM footprints.

| Model | Ollama tag | ~q4 size | Fit on 16 GB | Notes (legal / multilingual) |
|-------|-----------|----------|--------------|------------------------------|
| **Qwen2.5 14B Instruct** | `qwen2.5:14b-instruct` | ~9 GB | Tight — close other apps | **Best quality** here; strong multilingual incl. **ES**, good FR/DE. Recommended if RAM allows. |
| **Qwen2.5 7B Instruct** | `qwen2.5:7b-instruct` | ~5 GB | Comfortable | **Safe default.** Excellent ES/EN, solid FR/DE legal register. Use this if the 14B swaps. |
| Llama 3.1 8B Instruct | `llama3.1:8b-instruct` | ~5 GB | Comfortable | Strong general instruction-following; English-leaning, weaker on ES/FR/DE nuance than Qwen. |
| Mistral Small | `mistral-small` | ~14 GB (24B) | Does **not** fit well on 16 GB | Good European-language coverage but too large here; mention only for 32 GB+ machines. |

**Recommendation for this project's ES/EN/FR/DE legal text: the Qwen2.5 family.** Use **`qwen2.5:14b-instruct`** for the best output quality if your 16 GB box has headroom; drop to **`qwen2.5:7b-instruct`** as the safe default if you see memory pressure or swapping with the 14B. (The README's headline path uses 14B and notes the 7B fallback.)

## Embedding model recommendations

Set with `OLLAMA_EMBED_MODEL`. Embeddings power RAG retrieval over the gestora's precedent silo.

| Model | Ollama tag | ~size | When to use |
|-------|-----------|-------|-------------|
| **BGE-M3** | `bge-m3` | ~1.2 GB | **Recommended.** Multilingual (ES/EN/FR/DE) — matches the platform's languages. Default. |
| Nomic Embed Text | `nomic-embed-text` | ~270 MB | Smaller/faster, **English-leaning**. Use if your precedents are overwhelmingly English and you want to save RAM. |

For a Spanish-first, multi-jurisdiction European corpus, **`bge-m3`** is the right default — its multilingual retrieval quality is worth the extra ~1 GB over `nomic-embed-text`.

> If embeddings are unavailable entirely (Ollama down, or you removed the embed model), RAG **degrades gracefully** to deterministic `rag_weight` + recency ranking within the gestora silo. Retrieval still works and isolation is still hard — it just loses the semantic ranking signal. Nothing crashes.

## Swapping models — no code change

Models are configured purely by env var. To switch:

```bash
ollama pull qwen2.5:7b-instruct        # download the new model
# then set in backend/.env (or root .env for Docker):
#   OLLAMA_LLM_MODEL=qwen2.5:7b-instruct
# restart the backend.
```

Same for embeddings via `OLLAMA_EMBED_MODEL` (e.g. `ollama pull nomic-embed-text`). No application code changes are required. List what you have locally with `ollama list`.

## Performance tips

- **Expect roughly ~15–40 tokens/sec** for a 7B and **~8–20 tok/s** for a 14B on M-series chips (q4) — highly dependent on the specific chip and how much else is running. These are honest ballparks, not guarantees. A long, multi-page legal document can take **a minute or more** to generate end to end; the backend's `OLLAMA_TIMEOUT_SECONDS=600` default leaves plenty of room.
- **Keep the model warm.** Ollama unloads idle models to reclaim RAM. Set a longer `keep_alive` (e.g. `OLLAMA_KEEP_ALIVE=30m` when launching `ollama serve`, or via the API) so the first request after a pause isn't paying the cold-load cost.
- **Context length vs. RAM.** A larger context window grows the KV cache and eats into your ~10–11 GB budget. Long precedents + long output can push a 14B into swap on 16 GB — another reason the 7B is the safe default for big documents.
- **Close other heavy apps.** Browsers with many tabs, Slack, Docker builds, and other models all compete for unified memory. Freeing RAM directly improves tokens/sec by avoiding swap.
- **One big model at a time.** The generation model + `bge-m3` together are fine; trying to keep two large *generation* models resident on 16 GB will thrash.
- **Watch for swap.** If generation suddenly crawls, check Activity Monitor → Memory: high "Swap Used" / red memory pressure means you should drop to a smaller model or close apps.

## Cloud fallback

If a particular workload needs more than local hardware can give, switch that half to the cloud (`LLM_PROVIDER=anthropic` and/or `EMBEDDING_PROVIDER=openai`) — see the README. Local and cloud can be mixed per-provider.
