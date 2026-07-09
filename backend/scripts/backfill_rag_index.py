"""One-off backfill of the persisted RAG index (precedent_chunks, 018).

Chunks + embeds every indexable precedent version that is not indexed yet:
the global template pool (Temis library) first, then every gestora silo.
Idempotent — re-running skips versions that already have chunk rows and
fills in vectors for rows stored while the embedding provider was down.

Usage (from backend/, with production env vars set — needs SUPABASE_URL,
SUPABASE_SERVICE_ROLE_KEY, EMBEDDING_PROVIDER, MISTRAL_API_KEY):

    python -m scripts.backfill_rag_index            # everything
    python -m scripts.backfill_rag_index --global-only
"""
from __future__ import annotations

import argparse
import sys
import time

from services import db as dbmod
from services import indexer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-only", action="store_true", help="only the template pool")
    args = parser.parse_args()

    db = dbmod.get_db()

    start = time.monotonic()
    print("Sincronizando el pool global de plantillas…", flush=True)
    indexer.sync_global(db)
    print(f"  pool global listo ({time.monotonic()-start:.0f}s)")

    if not args.global_only:
        gestoras = db.unscoped_select("gestoras")
        for gestora in gestoras:
            t0 = time.monotonic()
            print(f"Sincronizando silo de {gestora.get('name') or gestora['id']}…", flush=True)
            indexer.sync_gestora(db, gestora["id"])
            print(f"  listo ({time.monotonic()-t0:.0f}s)")

    print(f"\nBackfill completado en {time.monotonic()-start:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
