"""
Benchmark reproducible de operaciones de lectura/escritura en Persistence (Issue #21).

Mide latencias (avg, p50, p95, p99) y throughput (ops/s) sobre MongoDB real
con índices de producción (`_id`, `uq_checksum_sha256`, `ix_created_at_id`)
para evaluar con evidencia si incorporar Redis aporta beneficio neto.
"""

import asyncio
import hashlib
import json
import os
import statistics
import time
import uuid
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGODB_DB", "persistence_benchmark_db")

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.models import Document
from app.infrastructure.database.connection import close_client, ensure_indexes, get_client
from app.infrastructure.repositories.mongo import MongoDocumentRepository
from app.main import create_app


def _percentile(sorted_samples: list[float], pct: float) -> float:
    if not sorted_samples:
        return 0.0
    idx = min(len(sorted_samples) - 1, int(round((pct / 100.0) * (len(sorted_samples) - 1))))
    return sorted_samples[idx]


def _summarize(name: str, latencies_ms: list[float], total_wall_s: float) -> dict:
    ordered = sorted(latencies_ms)
    ops_per_sec = len(latencies_ms) / total_wall_s if total_wall_s > 0 else 0.0
    return {
        "operation": name,
        "iterations": len(latencies_ms),
        "avg_ms": round(statistics.mean(ordered), 3),
        "p50_ms": round(_percentile(ordered, 50), 3),
        "p95_ms": round(_percentile(ordered, 95), 3),
        "p99_ms": round(_percentile(ordered, 99), 3),
        "throughput_ops_s": round(ops_per_sec, 1),
    }


async def _seed_documents(repo: MongoDocumentRepository, count: int) -> list[Document]:
    seeded: list[Document] = []
    # Mezcla representativa: 70% chicos (2 KB), 25% medianos (100 KB), 5% grandes (1 MB)
    for i in range(count):
        if i % 20 == 0:
            text_size = 1_024 * 1024  # 1 MB
        elif i % 4 == 0:
            text_size = 100 * 1024  # 100 KB
        else:
            text_size = 2 * 1024  # 2 KB

        raw_seed = f"bench-doc-{i}-{uuid.uuid4()}".encode()
        checksum = hashlib.sha256(raw_seed).hexdigest()
        now = datetime.now(timezone.utc)
        doc = Document(
            id=str(uuid.uuid4()),
            checksum_sha256=checksum,
            filename=f"documento_benchmark_{i:04d}.pdf",
            extracted_text=("A" * text_size),
            page_count=max(1, text_size // 2048),
            file_size_bytes=text_size * 2,
            metadata={"batch": "issue-21", "index": i},
            created_at=now,
            updated_at=now,
        )
        await repo.save(doc)
        seeded.append(doc)
    return seeded


async def run_benchmark(seed_count: int = 500, iterations: int = 300) -> list[dict]:
    client = get_client()
    db_name = os.environ["MONGODB_DB"]
    await client.drop_database(db_name)
    await ensure_indexes()

    repo = MongoDocumentRepository()
    docs = await _seed_documents(repo, seed_count)

    # Selección hot-set (20% de documentos más consultados, patrón Pareto 80/20)
    hot_docs = docs[: max(1, seed_count // 5)]
    small_doc = next(d for d in hot_docs if len(d.extracted_text) == 2 * 1024)
    medium_doc = next(d for d in hot_docs if len(d.extracted_text) == 100 * 1024)
    large_doc = next(d for d in hot_docs if len(d.extracted_text) == 1_024 * 1024)

    app = create_app()
    transport = ASGITransport(app=app)
    results: list[dict] = []

    async with AsyncClient(transport=transport, base_url="http://test") as http:
        # Warm-up
        for _ in range(10):
            await http.get(f"/api/v1/documents/{small_doc.id}")

        # 1. HTTP GET by ID (2 KB payload)
        lat = []
        t0 = time.perf_counter()
        for i in range(iterations):
            target = hot_docs[i % len(hot_docs)]
            if len(target.extracted_text) != 2 * 1024:
                target = small_doc
            s = time.perf_counter()
            r = await http.get(f"/api/v1/documents/{target.id}")
            assert r.status_code == 200
            lat.append((time.perf_counter() - s) * 1000.0)
        results.append(_summarize("GET /documents/{id} (2 KB)", lat, time.perf_counter() - t0))

        # 2. HTTP GET by Checksum SHA-256 (2 KB payload)
        lat = []
        t0 = time.perf_counter()
        for i in range(iterations):
            target = small_doc if i % 2 == 0 else hot_docs[i % len(hot_docs)]
            if len(target.extracted_text) != 2 * 1024:
                target = small_doc
            s = time.perf_counter()
            r = await http.get(f"/api/v1/documents/by-checksum/{target.checksum_sha256}")
            assert r.status_code == 200
            lat.append((time.perf_counter() - s) * 1000.0)
        results.append(
            _summarize("GET /documents/by-checksum/{sha256} (2 KB)", lat, time.perf_counter() - t0)
        )

        # 3. HTTP GET by ID (100 KB payload)
        lat = []
        t0 = time.perf_counter()
        for _ in range(iterations):
            s = time.perf_counter()
            r = await http.get(f"/api/v1/documents/{medium_doc.id}")
            assert r.status_code == 200
            lat.append((time.perf_counter() - s) * 1000.0)
        results.append(_summarize("GET /documents/{id} (100 KB)", lat, time.perf_counter() - t0))

        # 4. HTTP GET by ID (1 MB payload)
        lat = []
        t0 = time.perf_counter()
        for _ in range(100):
            s = time.perf_counter()
            r = await http.get(f"/api/v1/documents/{large_doc.id}")
            assert r.status_code == 200
            lat.append((time.perf_counter() - s) * 1000.0)
        results.append(_summarize("GET /documents/{id} (1 MB)", lat, time.perf_counter() - t0))

        # 5. HTTP GET paginated list (sin extracted_text)
        lat = []
        t0 = time.perf_counter()
        for i in range(iterations):
            skip = (i % 10) * 20
            s = time.perf_counter()
            r = await http.get(f"/api/v1/documents?skip={skip}&limit=20")
            assert r.status_code == 200
            lat.append((time.perf_counter() - s) * 1000.0)
        results.append(
            _summarize("GET /documents?skip&limit=20 (listado)", lat, time.perf_counter() - t0)
        )

        # 6. Overhead de serialización JSON pura (lo que igualmente pagaría Redis al deserializar)
        raw_json_1mb = json.dumps({"id": large_doc.id, "checksum_sha256": large_doc.checksum_sha256, "filename": large_doc.filename, "extracted_text": large_doc.extracted_text, "metadata": large_doc.metadata})
        lat = []
        t0 = time.perf_counter()
        for _ in range(100):
            s = time.perf_counter()
            parsed = json.loads(raw_json_1mb)
            _ = json.dumps(parsed)
            lat.append((time.perf_counter() - s) * 1000.0)
        results.append(
            _summarize("JSON encode/decode overhead (1 MB)", lat, time.perf_counter() - t0)
        )

    await client.drop_database(db_name)
    await close_client()
    return results


async def main() -> None:
    print("Ejecutando benchmark de Persistence contra MongoDB (500 docs sembrados)...")
    rows = await run_benchmark(seed_count=500, iterations=300)
    header = f"{'Operación':<44} {'N':>5} {'Avg(ms)':>9} {'p50(ms)':>9} {'p95(ms)':>9} {'p99(ms)':>9} {'ops/s':>9}"
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['operation']:<44} {r['iterations']:>5} "
            f"{r['avg_ms']:>9.3f} {r['p50_ms']:>9.3f} {r['p95_ms']:>9.3f} {r['p99_ms']:>9.3f} "
            f"{r['throughput_ops_s']:>9.1f}"
        )


if __name__ == "__main__":
    asyncio.run(main())


