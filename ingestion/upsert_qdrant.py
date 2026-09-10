"""Create (if needed) and populate the hybrid Qdrant tourism collection.

Run this module only when the knowledge base changes. The running agent reuses
the existing Qdrant Cloud collection and never invokes this ingestion command.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any, Iterator

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer

from tourism_agent.core.config import get_settings


DEFAULT_VECTOR_SIZE = 768  # paraphrase-multilingual-mpnet-base-v2


def iter_chunk_files(input_dir: Path) -> Iterator[Path]:
    yield from sorted(path for path in input_dir.rglob("*.json") if path.is_file())


def load_chunks(input_dir: Path) -> list[dict[str, Any]]:
    """Load chunk arrays emitted by ``python -m ingestion.crawl``."""
    chunks: list[dict[str, Any]] = []
    for path in iter_chunk_files(input_dir):
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            print(f"Skipping {path}: expected a JSON array of chunks")
            continue
        valid = [item for item in data if isinstance(item, dict) and item.get("content")]
        chunks.extend(valid)
        print(f"Loaded {len(valid)} chunks from {path}")
    return chunks


def point_id(chunk: dict[str, Any]) -> str:
    """Generate a stable UUID, so re-ingestion updates rather than duplicates a chunk."""
    identity = "|".join(
        str(chunk.get(key, "")) for key in ("source", "province", "section", "content")
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


def build_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": chunk["content"],
        "province": chunk.get("province"),
        "name": chunk.get("name"),
        "section": chunk.get("section"),
        "type": chunk.get("type"),
        "source": chunk.get("source", "unknown"),
        "tokens": chunk.get("tokens"),
    }


def ensure_collection(client: QdrantClient, collection_name: str, vector_size: int) -> None:
    existing = {item.name for item in client.get_collections().collections}
    if collection_name in existing:
        print(f"Using existing collection: {collection_name}")
        return
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "dense": qdrant_models.VectorParams(
                size=vector_size,
                distance=qdrant_models.Distance.COSINE,
            )
        },
        sparse_vectors_config={"sparse": qdrant_models.SparseVectorParams()},
    )
    print(f"Created collection: {collection_name}")


def upsert_chunks(
    client: QdrantClient,
    collection_name: str,
    chunks: list[dict[str, Any]],
    dense_model: SentenceTransformer,
    sparse_model: SparseTextEmbedding,
    batch_size: int,
) -> None:
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [str(chunk["content"]) for chunk in batch]
        dense_vectors = dense_model.encode(texts, normalize_embeddings=True)
        sparse_vectors = list(sparse_model.embed(texts))
        points = [
            qdrant_models.PointStruct(
                id=point_id(chunk),
                vector={
                    "dense": dense_vector.tolist(),
                    "sparse": {
                        "indices": sparse_vector.indices.tolist(),
                        "values": sparse_vector.values.tolist(),
                    },
                },
                payload=build_payload(chunk),
            )
            for chunk, dense_vector, sparse_vector in zip(batch, dense_vectors, sparse_vectors)
        ]
        client.upsert(collection_name=collection_name, points=points, wait=True)
        print(f"Upserted {min(start + batch_size, len(chunks))}/{len(chunks)} chunks")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upsert tourism chunks into hybrid Qdrant.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory containing chunk JSON files")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--vector-size", type=int, default=DEFAULT_VECTOR_SIZE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {args.input_dir}")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")

    chunks = load_chunks(args.input_dir)
    if not chunks:
        raise SystemExit("No valid chunks found; nothing was uploaded.")

    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=100)
    ensure_collection(client, settings.collection_name, args.vector_size)
    print(f"Loading dense model: {settings.embed_model}")
    dense_model = SentenceTransformer(settings.embed_model)
    sparse_model = SparseTextEmbedding("Qdrant/bm25")
    upsert_chunks(
        client,
        settings.collection_name,
        chunks,
        dense_model,
        sparse_model,
        args.batch_size,
    )


if __name__ == "__main__":
    main()
