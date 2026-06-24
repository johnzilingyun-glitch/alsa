"""Agent Memory — cross-job memory system for AI analyst agents.

Enables agents to recall prior analyses and learn from past outcomes.
Uses LanceDB for semantic vector search and SQLite for structured queries.
"""
import logging
from dataclasses import dataclass, field
from typing import List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A single memory entry from a past analysis."""
    memory_id: str
    symbol: str
    role: str
    analysis_summary: str
    key_conclusions: str
    confidence: float
    outcome: str  # win/lose/unknown/pending
    created_at: str


@dataclass
class RecallResult:
    """Result of a memory recall query."""
    entries: List[MemoryEntry] = field(default_factory=list)
    source: str = "mixed"  # vector/exact/mixed

    @property
    def summary(self) -> str:
        if not self.entries:
            return "无历史记忆"
        return f"召回 {len(self.entries)} 条相关记忆"


class AgentMemory:
    """
    Cross-job memory system for AI analyst agents.
    
    Stores analysis outputs and outcomes, enabling agents to:
    1. Recall prior analyses for the same stock
    2. Learn from past mistakes (failed predictions)
    3. Build on successful patterns
    """

    def __init__(self, db_session_factory=None):
        self._db_session_factory = db_session_factory
        self._lancedb_store = None

    @property
    def lancedb_store(self):
        """Lazy-load LanceDB store to avoid circular imports."""
        if self._lancedb_store is None:
            try:
                from ..vector.lancedb_store import LanceResearchStore
                self._lancedb_store = LanceResearchStore()
            except Exception as e:
                logger.warning(f"[AgentMemory] LanceDB unavailable: {e}")
        return self._lancedb_store

    async def recall(self, symbol: str, role: str, query: str = "", limit: int = 3) -> RecallResult:
        """
        Recall relevant memories for a given stock and role.
        
        Args:
            symbol: Stock symbol
            role: Agent role name
            query: Optional query text for semantic search
            limit: Max memories to return
            
        Returns:
            RecallResult with relevant memory entries
        """
        entries = []

        # Try vector search first (semantic similarity)
        if query and self.lancedb_store:
            try:
                vector_entries = await self._recall_vector(symbol, role, query, limit)
                entries.extend(vector_entries)
            except Exception as e:
                logger.debug(f"[AgentMemory] Vector recall failed: {e}")

        # Supplement with exact DB lookup
        if len(entries) < limit:
            try:
                exact_entries = await self._recall_exact(symbol, role, limit - len(entries))
                # Deduplicate by memory_id
                seen_ids = {e.memory_id for e in entries}
                for e in exact_entries:
                    if e.memory_id not in seen_ids:
                        entries.append(e)
                        seen_ids.add(e.memory_id)
            except Exception as e:
                logger.debug(f"[AgentMemory] Exact recall failed: {e}")

        return RecallResult(entries=entries[:limit], source="mixed")

    async def store(
        self,
        symbol: str,
        role: str,
        analysis: str,
        key_conclusions: str = "",
        confidence: float = 0.5,
        outcome: str = "unknown",
    ):
        """
        Store an analysis result for future recall.
        
        Args:
            symbol: Stock symbol
            role: Agent role name
            analysis: Full analysis text (truncated for storage)
            key_conclusions: Key conclusions extracted from analysis
            confidence: Confidence score (0-1)
            outcome: Outcome label (win/lose/unknown)
        """
        import uuid
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"

        # Store in vector DB for semantic search
        if self.lancedb_store:
            try:
                self.lancedb_store.upsert_documents([{
                    "doc_id": memory_id,
                    "symbol": symbol,
                    "text": f"[{role}] {analysis[:2000]}",
                    "source_type": "agent_memory",
                    "published_at": datetime.now().isoformat(),
                    "observed_at": datetime.now().isoformat(),
                    "ingested_at": datetime.now().isoformat(),
                    "effective_from": datetime.now().isoformat(),
                    "effective_to": None,
                    "credibility_score": confidence,
                }])
            except Exception as e:
                logger.debug(f"[AgentMemory] LanceDB store failed: {e}")

        # Store in SQLite for structured queries
        if self._db_session_factory:
            try:
                self._store_exact(memory_id, symbol, role, analysis, key_conclusions, confidence, outcome)
            except Exception as e:
                logger.debug(f"[AgentMemory] SQLite store failed: {e}")

        logger.info(f"[AgentMemory] Stored memory {memory_id} for {symbol}/{role}")

    async def update_outcome(self, symbol: str, outcome: str, return_pct: float = None):
        """
        Update outcome for recent memories of a symbol.
        Called after prediction evaluation.
        """
        if not self._db_session_factory:
            return

        try:
            from sqlmodel import text
            with self._db_session_factory() as session:
                update = text(
                    "UPDATE agent_memory SET outcome = :outcome "
                    "WHERE symbol = :symbol AND outcome = 'unknown' "
                    "ORDER BY created_at DESC LIMIT 5"
                )
                session.execute(update, {"outcome": outcome, "symbol": symbol})
                session.commit()
        except Exception as e:
            logger.debug(f"[AgentMemory] Outcome update failed: {e}")

    async def _recall_vector(self, symbol: str, role: str, query: str, limit: int) -> List[MemoryEntry]:
        """Recall memories using vector similarity search."""
        results = self.lancedb_store.search(
            symbol=symbol,
            query=f"{role}: {query}",
            limit=limit,
        )

        entries = []
        for r in results:
            text = r.get("text", "")
            # Extract role prefix if present
            entry_role = role
            if text.startswith("[") and "]" in text[:30]:
                entry_role = text[1:text.index("]")]

            entries.append(MemoryEntry(
                memory_id=r.get("doc_id", ""),
                symbol=symbol,
                role=entry_role,
                analysis_summary=text[:500],
                key_conclusions="",
                confidence=r.get("credibility_score", 0.5),
                outcome="unknown",
                created_at=r.get("published_at", ""),
            ))
        return entries

    async def _recall_exact(self, symbol: str, role: str, limit: int) -> List[MemoryEntry]:
        """Recall memories using exact DB query."""
        if not self._db_session_factory:
            return []

        from sqlmodel import text
        with self._db_session_factory() as session:
            result = session.execute(
                text(
                    "SELECT memory_id, symbol, role, analysis_summary, key_conclusions, "
                    "confidence, outcome, created_at "
                    "FROM agent_memory "
                    "WHERE symbol = :symbol AND role = :role "
                    "ORDER BY created_at DESC "
                    "LIMIT :limit"
                ),
                {"symbol": symbol, "role": role, "limit": limit},
            )
            rows = result.fetchall()

        return [
            MemoryEntry(
                memory_id=row[0],
                symbol=row[1],
                role=row[2],
                analysis_summary=row[3] or "",
                key_conclusions=row[4] or "",
                confidence=row[5] or 0.5,
                outcome=row[6] or "unknown",
                created_at=str(row[7]) if row[7] else "",
            )
            for row in rows
        ]

    def _store_exact(self, memory_id, symbol, role, analysis, key_conclusions, confidence, outcome):
        """Store memory in SQLite."""
        from sqlmodel import text
        with self._db_session_factory() as session:
            session.execute(
                text(
                    "INSERT INTO agent_memory (memory_id, symbol, role, analysis_summary, "
                    "key_conclusions, confidence, outcome, created_at) "
                    "VALUES (:memory_id, :symbol, :role, :summary, :conclusions, :confidence, :outcome, :created_at)"
                ),
                {
                    "memory_id": memory_id,
                    "symbol": symbol,
                    "role": role,
                    "summary": analysis[:5000],
                    "conclusions": key_conclusions[:2000],
                    "confidence": confidence,
                    "outcome": outcome,
                    "created_at": datetime.now().isoformat(),
                },
            )
            session.commit()


# Singleton
agent_memory = AgentMemory()
