"""FastAPI application for MemLite-Agent.

Provides REST endpoints for:
- Memory CRUD (/v1/memories)
- Retrieval (/v1/retrieval/query)
- Cache management (/v1/cache)
- Health check (/health)
"""

from __future__ import annotations

import math
import os
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import Response

from memlite.cache import CacheEventType, ScopeContext
from memlite.engine import MemLiteEngine
from memlite.models import MemoryType, SourceType

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.getenv("MEMLITE_DATA_DIR", "./data"))
DB_PATH = DATA_DIR / "memlite.db"

# ---------------------------------------------------------------------------
# Global engine (managed by lifespan)
# ---------------------------------------------------------------------------

_engine: MemLiteEngine | None = None


def get_engine() -> MemLiteEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialized")
    return _engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _engine
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _engine = MemLiteEngine(DB_PATH)
    try:
        yield
    finally:
        _engine.close()
        _engine = None
        _rate_limits.clear()
        _token_usage.clear()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MemLite-Agent API",
    description="A lightweight hierarchical memory and semantic cache system for LLM agents.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Rate Limiting & Budget Cap
# ---------------------------------------------------------------------------

_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = int(os.getenv("MEMLITE_RATE_LIMIT", "100"))
RATE_LIMIT_WINDOW = 60  # seconds

_token_usage: dict[str, int] = defaultdict(int)
TOKEN_BUDGET_CAP = int(os.getenv("MEMLITE_TOKEN_BUDGET", "100000"))


def _estimate_tokens(text: str) -> int:
    return math.ceil(len(text.encode("utf-8")) / 4)


def check_and_update_budget(scope_id: str, text: str) -> None:
    if not scope_id.strip() or not text.strip():
        raise HTTPException(status_code=400, detail="scope and text must not be empty")
    tokens = _estimate_tokens(text)
    if _token_usage[scope_id] + tokens > TOKEN_BUDGET_CAP:
        raise HTTPException(status_code=429, detail="Token budget exceeded")
    _token_usage[scope_id] += tokens


@contextmanager
def budget_reservation(scope_id: str, text: str) -> Iterator[None]:
    tokens = _estimate_tokens(text)
    check_and_update_budget(scope_id, text)
    try:
        yield
    except Exception:
        _token_usage[scope_id] = max(0, _token_usage[scope_id] - tokens)
        raise


@app.middleware("http")
async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.url.path == "/health":
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    _rate_limits[client_ip] = [t for t in _rate_limits[client_ip] if now - t < RATE_LIMIT_WINDOW]

    if len(_rate_limits[client_ip]) >= RATE_LIMIT_REQUESTS:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    _rate_limits[client_ip].append(now)
    return await call_next(request)


# ---------------------------------------------------------------------------
# Endpoints: Budget
# ---------------------------------------------------------------------------


@app.get("/v1/budget/{scope_id}", tags=["Budget"])
async def get_budget(scope_id: str) -> dict[str, Any]:
    used = _token_usage[scope_id]
    remaining = max(0, TOKEN_BUDGET_CAP - used)
    return {
        "scope_id": scope_id,
        "used": used,
        "remaining": remaining,
        "cap": TOKEN_BUDGET_CAP,
        "kind": "estimated_input_tokens",
        "persistent": False,
    }


@app.post("/v1/budget/{scope_id}/reset", tags=["Budget"])
async def reset_budget(scope_id: str) -> dict[str, Any]:
    _token_usage[scope_id] = 0
    return {"scope_id": scope_id, "used": 0, "remaining": TOKEN_BUDGET_CAP, "cap": TOKEN_BUDGET_CAP}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class MemoryCreateRequest(BaseModel):
    memory_type: MemoryType
    scope_id: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)
    source_type: SourceType = SourceType.USER
    source_ref: str | None = None
    importance: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=1.0, ge=0, le=1)
    ttl_seconds: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] | None = None


class MemoryResponse(BaseModel):
    id: str
    memory_type: str
    scope_id: str
    content: str
    importance: float
    confidence: float
    status: str
    created_at: str
    updated_at: str
    access_count: int
    version: int


class SupersedeRequest(BaseModel):
    content: str


class RetrievalRequest(BaseModel):
    query: str
    scope_id: str
    memory_types: list[MemoryType] | None = None


class CacheStoreRequest(BaseModel):
    query: str
    response: str
    scope_id: str
    ttl_seconds: int | None = Field(default=None, gt=0)
    system_prompt_version: str = ""
    model_id: str = ""
    tool_schema_version: str = ""
    context_fingerprint: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _memory_to_response(item: Any) -> MemoryResponse:
    return MemoryResponse(
        id=item.id,
        memory_type=item.memory_type.value,
        scope_id=item.scope_id,
        content=item.content,
        importance=item.importance,
        confidence=item.confidence,
        status=item.status.value,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
        access_count=item.access_count,
        version=item.version,
    )


# ---------------------------------------------------------------------------
# Endpoints: Health
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Return service health status."""
    engine = get_engine()
    db_status = "ok"
    try:
        # Quick check: can we retrieve from the store?
        engine.retrieve("health-check", scope_id="__health__")
    except Exception:
        db_status = "degraded"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version="0.1.0",
        database=db_status,
    )


# ---------------------------------------------------------------------------
# Endpoints: Memories CRUD
# ---------------------------------------------------------------------------


@app.post("/v1/memories", response_model=MemoryResponse, tags=["Memories"])
async def create_memory(req: MemoryCreateRequest) -> MemoryResponse:
    """Store a new memory."""
    engine = get_engine()
    try:
        item = engine.remember(
            memory_type=MemoryType(req.memory_type),
            scope_id=req.scope_id,
            content=req.content,
            source_type=SourceType(req.source_type),
            source_ref=req.source_ref,
            importance=req.importance,
            confidence=req.confidence,
            ttl_seconds=req.ttl_seconds,
            metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _memory_to_response(item)


@app.get("/v1/memories", response_model=list[MemoryResponse], tags=["Memories"])
async def list_memories(
    scope_id: str = Query(...),
    memory_type: Annotated[MemoryType | None, Query()] = None,
    limit: int = Query(20, ge=1, le=1000),
) -> list[MemoryResponse]:
    """List active memories in a scope."""
    engine = get_engine()
    types = {MemoryType(memory_type)} if memory_type else None
    items = engine._store.list_active(scope_id=scope_id, memory_types=types, limit=limit)
    return [_memory_to_response(item) for item in items]


@app.get("/v1/memories/{memory_id}", response_model=MemoryResponse, tags=["Memories"])
async def get_memory(memory_id: str) -> MemoryResponse:
    """Get a single memory by ID."""
    engine = get_engine()
    item = engine._store.get(memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _memory_to_response(item)


@app.patch("/v1/memories/{memory_id}", response_model=MemoryResponse, tags=["Memories"])
async def supersede_memory(memory_id: str, req: SupersedeRequest) -> MemoryResponse:
    """Supersede a memory with new content."""
    engine = get_engine()
    try:
        replacement = engine.supersede(memory_id, content=req.content)
    except LookupError as e:
        raise HTTPException(status_code=404, detail="Active memory not found") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _memory_to_response(replacement)


@app.delete("/v1/memories/{memory_id}", tags=["Memories"])
async def delete_memory(memory_id: str) -> dict[str, Any]:
    """Soft-delete a memory."""
    engine = get_engine()
    deleted = engine.forget(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Active memory not found")
    return {"deleted": True, "memory_id": memory_id}


# ---------------------------------------------------------------------------
# Endpoints: Retrieval
# ---------------------------------------------------------------------------


@app.post("/v1/retrieval/query", tags=["Retrieval"])
async def query_retrieval(req: RetrievalRequest) -> dict[str, Any]:
    """Retrieve relevant memories for a query."""
    engine = get_engine()
    types = set(req.memory_types) if req.memory_types is not None else None
    try:
        with budget_reservation(req.scope_id, req.query):
            response = engine.retrieve(req.query, scope_id=req.scope_id, memory_types=types)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return response.to_dict()


# ---------------------------------------------------------------------------
# Endpoints: Cache
# ---------------------------------------------------------------------------


@app.get("/v1/cache", tags=["Cache"])
async def cache_stats() -> dict[str, Any]:
    """Return cache statistics."""
    engine = get_engine()
    stats = engine.cache_stats()
    return {
        "total": stats.total_entries,
        "active": stats.active_entries,
        "hits": stats.hits,
        "misses": stats.misses,
        "rejected_hits": stats.rejected_hits,
        "hit_rate": stats.hit_rate,
    }


@app.post("/v1/cache/lookup", tags=["Cache"])
async def cache_lookup(
    query: str = Query(...),
    scope_id: str = Query(...),
    system_prompt_version: str = "",
    model_id: str = "",
    tool_schema_version: str = "",
    context_fingerprint: str = "",
) -> dict[str, Any]:
    """Look up a cached response."""
    engine = get_engine()
    ctx = ScopeContext(system_prompt_version, model_id, tool_schema_version, context_fingerprint)
    try:
        with budget_reservation(scope_id, query):
            result = engine.cache_lookup(query, scope_id=scope_id, scope_context=ctx)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if result.event_type is CacheEventType.HIT and result.entry is not None:
        return {
            "hit": True,
            "entry_id": result.entry.id,
            "response": result.entry.response,
            "similarity": result.similarity,
            "event_type": result.event_type.value,
        }
    return {"hit": False, "event_type": result.event_type.value}


@app.post("/v1/cache/store", tags=["Cache"])
async def cache_store(req: CacheStoreRequest) -> dict[str, Any]:
    """Store a query-response pair in the cache."""
    engine = get_engine()
    try:
        with budget_reservation(req.scope_id, req.query + req.response):
            entry = engine.cache_store(
                query=req.query,
                response=req.response,
                scope_id=req.scope_id,
                ttl_seconds=req.ttl_seconds,
                scope_context=ScopeContext(
                    req.system_prompt_version,
                    req.model_id,
                    req.tool_schema_version,
                    req.context_fingerprint,
                ),
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"id": entry.id, "stored": True}


@app.delete("/v1/cache/{cache_id}", tags=["Cache"])
async def cache_invalidate(cache_id: str) -> dict[str, Any]:
    """Invalidate a cache entry."""
    engine = get_engine()
    invalidated = engine.cache_invalidate(cache_id)
    if not invalidated:
        raise HTTPException(status_code=404, detail="Cache entry not found")
    return {"invalidated": True, "cache_id": cache_id}
