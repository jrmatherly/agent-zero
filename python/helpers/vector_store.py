"""pgVector backend for durable vector storage.

Provides async write-behind and read-fallback for the hybrid
FAISS (hot cache) + pgVector (durable store) architecture.

This module is only active when running against PostgreSQL.
On SQLite (local dev), all methods are no-ops and FAISS remains
the sole vector store.

Usage:
    from python.helpers.vector_store import pgvector_store

    # Write-behind (non-blocking)
    await pgvector_store.insert_documents(docs, embeddings, tenant_ctx)

    # Read-fallback (on FAISS cache miss)
    results = await pgvector_store.search(query_embedding, tenant_ctx, limit, threshold)

    # Check availability
    if pgvector_store.is_available():
        ...
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from python.helpers.auth_db import get_engine, get_session
from python.helpers.print_style import PrintStyle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_pgvector_available: bool | None = None  # lazily detected


class PgVectorStore:
    """Durable vector store backed by PostgreSQL + pgVector.

    All public methods are safe to call regardless of database backend —
    they degrade gracefully to no-ops on SQLite.
    """

    def is_available(self) -> bool:
        """Check if pgVector is available (PostgreSQL with vector extension)."""
        global _pgvector_available
        if _pgvector_available is not None:
            return _pgvector_available

        try:
            engine = get_engine()
            if engine.dialect.name != "postgresql":
                _pgvector_available = False
                return False

            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                )
                _pgvector_available = result.scalar() is not None

            if _pgvector_available:
                PrintStyle.info("pgVector extension detected — hybrid mode enabled")
            else:
                PrintStyle.warning(
                    "PostgreSQL detected but pgVector extension not installed. "
                    "Run migration 004 or install the extension manually."
                )
        except Exception as e:
            logger.debug(f"pgVector availability check failed: {e}")
            _pgvector_available = False

        return _pgvector_available

    def insert_sync(
        self,
        doc_id: str,
        content: str,
        embedding: list[float],
        metadata: dict,
        memory_subdir: str,
        user_id: str,
        org_id: str,
        team_id: str | None = None,
        embedding_model: str | None = None,
    ) -> bool:
        """Synchronously insert a single vector document.

        Returns True on success, False on failure (non-fatal).
        """
        if not self.is_available():
            return False

        try:
            with get_session() as session:
                self._upsert_document(
                    session,
                    doc_id=doc_id,
                    content=content,
                    embedding=embedding,
                    metadata=metadata,
                    memory_subdir=memory_subdir,
                    area=metadata.get("area", "main"),
                    user_id=user_id,
                    org_id=org_id,
                    team_id=team_id,
                    embedding_model=embedding_model,
                )
            return True
        except Exception as e:
            logger.warning(f"pgVector insert failed (non-fatal): {e}")
            return False

    async def insert_async(
        self,
        doc_id: str,
        content: str,
        embedding: list[float],
        metadata: dict,
        memory_subdir: str,
        user_id: str,
        org_id: str,
        team_id: str | None = None,
        embedding_model: str | None = None,
    ) -> bool:
        """Async wrapper for insert — runs in thread pool to avoid blocking."""
        if not self.is_available():
            return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.insert_sync(
                doc_id=doc_id,
                content=content,
                embedding=embedding,
                metadata=metadata,
                memory_subdir=memory_subdir,
                user_id=user_id,
                org_id=org_id,
                team_id=team_id,
                embedding_model=embedding_model,
            ),
        )

    async def insert_batch_async(
        self,
        documents: list[dict],
        memory_subdir: str,
        user_id: str,
        org_id: str,
        team_id: str | None = None,
        embedding_model: str | None = None,
    ) -> int:
        """Batch insert documents. Each dict needs: id, content, embedding, metadata.

        Returns count of successfully inserted documents.
        """
        if not self.is_available():
            return 0

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._batch_insert_sync(
                documents, memory_subdir, user_id, org_id, team_id, embedding_model
            ),
        )

    def _batch_insert_sync(
        self,
        documents: list[dict],
        memory_subdir: str,
        user_id: str,
        org_id: str,
        team_id: str | None,
        embedding_model: str | None,
    ) -> int:
        """Batch insert in a single transaction, 100 docs per batch."""
        count = 0
        batch_size = 100

        try:
            with get_session() as session:
                for i in range(0, len(documents), batch_size):
                    batch = documents[i : i + batch_size]
                    for doc in batch:
                        self._upsert_document(
                            session,
                            doc_id=doc["id"],
                            content=doc["content"],
                            embedding=doc["embedding"],
                            metadata=doc.get("metadata", {}),
                            memory_subdir=memory_subdir,
                            area=doc.get("metadata", {}).get("area", "main"),
                            user_id=user_id,
                            org_id=org_id,
                            team_id=team_id,
                            embedding_model=embedding_model,
                        )
                        count += 1
        except Exception as e:
            logger.warning(f"pgVector batch insert failed at {count} docs: {e}")

        return count

    def search_sync(
        self,
        query_embedding: list[float],
        memory_subdir: str,
        limit: int = 10,
        threshold: float = 0.0,
        area: str | None = None,
    ) -> list[dict]:
        """Synchronous similarity search against pgVector.

        Returns list of dicts with: id, content, metadata, score.
        """
        if not self.is_available():
            return []

        try:
            with get_session() as session:
                return self._search(
                    session,
                    query_embedding=query_embedding,
                    memory_subdir=memory_subdir,
                    limit=limit,
                    threshold=threshold,
                    area=area,
                )
        except Exception as e:
            logger.warning(f"pgVector search failed (non-fatal): {e}")
            return []

    async def search_async(
        self,
        query_embedding: list[float],
        memory_subdir: str,
        limit: int = 10,
        threshold: float = 0.0,
        area: str | None = None,
    ) -> list[dict]:
        """Async similarity search — runs in thread pool."""
        if not self.is_available():
            return []

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.search_sync(
                query_embedding=query_embedding,
                memory_subdir=memory_subdir,
                limit=limit,
                threshold=threshold,
                area=area,
            ),
        )

    async def delete_by_ids_async(
        self,
        ids: list[str],
        memory_subdir: str,
    ) -> int:
        """Delete documents by IDs. Returns count deleted."""
        if not self.is_available() or not ids:
            return 0

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._delete_by_ids_sync(ids, memory_subdir),
        )

    def _delete_by_ids_sync(self, ids: list[str], memory_subdir: str) -> int:
        """Delete documents by IDs in a single transaction."""
        try:
            with get_session() as session:
                result = session.execute(
                    text(
                        "DELETE FROM vector_documents "
                        "WHERE id = ANY(:ids) AND memory_subdir = :subdir"
                    ),
                    {"ids": ids, "subdir": memory_subdir},
                )
                return result.rowcount  # type: ignore
        except Exception as e:
            logger.warning(f"pgVector delete failed (non-fatal): {e}")
            return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _upsert_document(
        self,
        session: Session,
        *,
        doc_id: str,
        content: str,
        embedding: list[float],
        metadata: dict,
        memory_subdir: str,
        area: str,
        user_id: str,
        org_id: str,
        team_id: str | None,
        embedding_model: str | None,
    ) -> None:
        """Insert or update a vector document using PostgreSQL UPSERT."""
        # Strip non-serializable fields from metadata
        clean_metadata = {
            k: v for k, v in metadata.items() if k not in ("id", "embedding")
        }

        session.execute(
            text("""
                INSERT INTO vector_documents
                    (id, user_id, org_id, team_id, memory_subdir, area,
                     content, metadata_json, embedding, embedding_model,
                     embedding_dimensions, created_at)
                VALUES
                    (:id, :user_id, :org_id, :team_id, :memory_subdir, :area,
                     :content, :metadata_json, :embedding, :embedding_model,
                     :embedding_dimensions, :created_at)
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    metadata_json = EXCLUDED.metadata_json,
                    embedding = EXCLUDED.embedding,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding_dimensions = EXCLUDED.embedding_dimensions
            """),
            {
                "id": doc_id,
                "user_id": user_id,
                "org_id": org_id,
                "team_id": team_id,
                "memory_subdir": memory_subdir,
                "area": area,
                "content": content,
                "metadata_json": json.dumps(clean_metadata),
                "embedding": str(embedding),  # pgvector accepts text representation
                "embedding_model": embedding_model,
                "embedding_dimensions": len(embedding),
                "created_at": datetime.now(timezone.utc),
            },
        )

    def _search(
        self,
        session: Session,
        *,
        query_embedding: list[float],
        memory_subdir: str,
        limit: int,
        threshold: float,
        area: str | None,
    ) -> list[dict]:
        """Execute cosine similarity search using pgVector HNSW index."""
        # Cosine similarity: 1 - cosine_distance
        # pgvector's <=> operator returns cosine distance, so similarity = 1 - distance
        area_filter = "AND area = :area" if area else ""

        query = text(f"""
            SELECT
                id,
                content,
                metadata_json,
                1 - (embedding <=> :query_embedding::vector) AS score
            FROM vector_documents
            WHERE memory_subdir = :memory_subdir
                {area_filter}
                AND 1 - (embedding <=> :query_embedding::vector) >= :threshold
            ORDER BY embedding <=> :query_embedding::vector
            LIMIT :limit
        """)

        params: dict = {
            "query_embedding": str(query_embedding),
            "memory_subdir": memory_subdir,
            "threshold": threshold,
            "limit": limit,
        }
        if area:
            params["area"] = area

        rows = session.execute(query, params).fetchall()

        results = []
        for row in rows:
            metadata = {}
            if row.metadata_json:
                try:
                    metadata = json.loads(row.metadata_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            metadata["id"] = row.id

            results.append(
                {
                    "id": row.id,
                    "content": row.content,
                    "metadata": metadata,
                    "score": float(row.score),
                }
            )

        return results


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

pgvector_store = PgVectorStore()
