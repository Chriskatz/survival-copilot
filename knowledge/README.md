# Knowledge base (RAG corpus)

Bilingual offline reference material that grounds every answer. The RAG pipeline
embeds and retrieves from this directory — there is no cloud lookup.

## Layout

```
en/  *.md     English topics
zh/  *.md     Traditional-Chinese topics (parallel to en/)
index.json    built artifact — embeddings for every chunk (do not hand-edit)
```

Each `.md` is split into chunks by `##` heading. Current topics: snake-bite
first aid, hypothermia, lost-navigation, earthquake, flood, power-outage.

## How it is used

1. `python bot/build_index.py` embeds every `##` section via `@qvac/sdk`
   (EmbeddingGemma 300M, L2-normalized 768-dim) → writes `index.json`.
2. `bot/retriever.py` loads `index.json` and returns cosine top-k per query.
   Retrieval is **cross-lingual** — a Chinese query can match English chunks.
3. If the top score is below `0.40`, the bot refuses **before** the LLM runs
   (no confident wrong answers on life-critical topics).

## Adding content

1. Add a `topic.md` under both `en/` and `zh/`, using `##` section headings and
   keeping the same safety-disclaimer style as the existing files.
2. Re-run `python bot/build_index.py` (needs `qvac serve openai` up) to rebuild
   `index.json`.

> ⚠️ Demo corpus only — small and hackathon-scoped. Not a substitute for
> professional emergency guidance.
