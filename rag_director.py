"""
rag_director.py — RAG-based persistent memory for the AI Wave Director.

ARCHITECTURE:
    This module implements a full Retrieval Augmented Generation pipeline
    for the DeadZone AI director. Instead of only using the last 5 waves
    of the current session, the director now has persistent memory across
    ALL past runs stored in a local ChromaDB vector database.

PIPELINE:
    1. END OF RUN → run summary embedded as a vector → stored in ChromaDB
    2. START OF WAVE → query ChromaDB for semantically similar past runs
    3. Retrieved context injected into Groq prompt alongside current stats
    4. AI director generates wave composition with historical awareness

WHY THIS MATTERS (interview answer):
    - Embeddings: text → dense vector representation (sentence-transformers)
    - Vector store: ChromaDB persists vectors locally, enables similarity search
    - Retrieval: cosine similarity finds runs where player showed same patterns
    - Augmentation: retrieved context added to LLM prompt as grounding
    - Generation: Groq/LLaMA generates wave composition with full context
    Same architecture as enterprise RAG systems (document Q&A, chatbots, etc.)

STORAGE:
    ChromaDB persists to ./deadzone_memory/ directory locally.
    Each run is stored as one document with metadata.
"""

import os
import json
import datetime

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("[RAG] ChromaDB not available — persistent memory disabled")


class RAGDirector:
    """
    Manages persistent run memory using ChromaDB vector store.
    All methods are safe to call even if ChromaDB is unavailable —
    falls back to no-op silently so the game always works.
    """

    COLLECTION_NAME = "deadzone_runs"
    DB_PATH         = "./deadzone_memory"
    MAX_RESULTS     = 3   # how many similar runs to retrieve

    def __init__(self) -> None:
        self._client     = None
        self._collection = None
        self._ready      = False

        if not CHROMA_AVAILABLE:
            return

        try:
            # Persistent client — survives game restarts
            self._client = chromadb.PersistentClient(path=self.DB_PATH)

            # Use sentence-transformers for embeddings (runs locally, no API key)
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"   # small, fast, good quality
            )

            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"}
            )

            count = self._collection.count()
            print(f"[RAG] Memory loaded — {count} past runs in vector store")
            self._ready = True

        except Exception as e:
            print(f"[RAG] Init failed: {e}")
            self._ready = False

    # ── Public API ────────────────────────────────────────────────────────────

    def store_run(self, player_name: str, score: int, wave: int,
                  kills: int, wave_history: list, ai_review: str = "") -> None:
        """
        Called at end of run. Converts run data into a text document,
        embeds it, and stores in ChromaDB.
        """
        if not self._ready:
            return

        try:
            # Build a natural language summary — this is what gets embedded
            avg_acc = round(
                sum(w["accuracy_pct"] for w in wave_history) / max(1, len(wave_history)), 1
            )
            avg_dmg = round(
                sum(w["damage_taken"] for w in wave_history) / max(1, len(wave_history)), 1
            )
            total_kills = sum(w["kills"] for w in wave_history)

            # Identify patterns for better retrieval
            struggled_fast  = any(
                w["damage_taken"] > 40 and w["composition"].get("fast_ratio", 0) > 0.4
                for w in wave_history
            )
            struggled_tanks = any(
                w["damage_taken"] > 40 and w["composition"].get("tank_ratio", 0) > 0.2
                for w in wave_history
            )
            high_accuracy   = avg_acc > 65
            low_accuracy    = avg_acc < 35

            patterns = []
            if struggled_fast:  patterns.append("struggled against fast zombies")
            if struggled_tanks: patterns.append("struggled against tank zombies")
            if high_accuracy:   patterns.append("high accuracy shooter")
            if low_accuracy:    patterns.append("low accuracy sprayer")
            if wave > 8:        patterns.append("reached deep waves")
            if wave < 3:        patterns.append("died early")

            pattern_str = ", ".join(patterns) if patterns else "average performance"

            # Natural language document — ChromaDB embeds this
            document = (
                f"Player {player_name} survived {wave} waves with score {score}. "
                f"Total kills: {total_kills}. Average accuracy: {avg_acc}%. "
                f"Average damage taken per wave: {avg_dmg} HP. "
                f"Performance patterns: {pattern_str}. "
                f"Wave history summary: {self._summarise_history(wave_history)}. "
                f"AI analysis: {ai_review[:200] if ai_review else 'none'}."
            )

            # Unique ID per run
            run_id = f"run_{player_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

            self._collection.add(
                documents=[document],
                ids=[run_id],
                metadatas=[{
                    "player":    player_name,
                    "score":     score,
                    "wave":      wave,
                    "kills":     kills,
                    "avg_acc":   avg_acc,
                    "avg_dmg":   avg_dmg,
                    "timestamp": datetime.datetime.now().isoformat(),
                }]
            )

            print(f"[RAG] Run stored: {run_id} ({self._collection.count()} total)")

        except Exception as e:
            print(f"[RAG] Store failed: {e}")

    def retrieve_context(self, current_stats: dict) -> str:
        """
        Called before generating a wave composition.
        Queries ChromaDB for similar past runs and returns a formatted
        context string to inject into the Groq prompt.

        Returns empty string if no relevant history found.
        """
        if not self._ready:
            return ""

        try:
            count = self._collection.count()
            if count == 0:
                return ""

            # Build query from current session state
            wave     = current_stats.get("next_wave", 1)
            acc      = current_stats.get("avg_accuracy", 50)
            dmg      = current_stats.get("avg_damage", 0)
            kills    = current_stats.get("recent_kills", 0)

            acc_desc  = "high accuracy" if acc > 65 else "low accuracy" if acc < 35 else "average accuracy"
            dmg_desc  = "taking heavy damage" if dmg > 60 else "taking light damage" if dmg < 20 else "moderate damage"
            wave_desc = "early waves" if wave < 4 else "mid waves" if wave < 8 else "deep waves"

            query = (
                f"Player in {wave_desc} with {acc_desc} and {dmg_desc}, "
                f"{kills} recent kills, approaching wave {wave}"
            )

            results = self._collection.query(
                query_texts=[query],
                n_results=min(self.MAX_RESULTS, count),
                include=["documents", "metadatas", "distances"]
            )

            if not results["documents"] or not results["documents"][0]:
                return ""

            # Format retrieved context for the prompt
            lines = ["=== SIMILAR PAST RUNS (from persistent memory) ==="]
            for i, (doc, meta, dist) in enumerate(zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )):
                similarity = round((1 - dist) * 100, 1)
                lines.append(
                    f"  Past run {i+1} (similarity: {similarity}%): {doc[:300]}"
                )

            context = "\n".join(lines)
            print(f"[RAG] Retrieved {len(results['documents'][0])} similar runs")
            return context

        except Exception as e:
            print(f"[RAG] Retrieve failed: {e}")
            return ""

    def get_stats(self) -> dict:
        """Returns basic stats about the memory store — useful for debugging."""
        if not self._ready:
            return {"ready": False, "runs": 0}
        try:
            return {"ready": True, "runs": self._collection.count()}
        except Exception:
            return {"ready": False, "runs": 0}

    # ── Private helpers ───────────────────────────────────────────────────────

    def _summarise_history(self, wave_history: list) -> str:
        """Convert wave history list into a compact readable string."""
        if not wave_history:
            return "no waves completed"
        parts = []
        for w in wave_history[-5:]:   # last 5 waves only
            comp = w.get("composition", {})
            parts.append(
                f"wave {w['wave']}: {w['kills']}k "
                f"{w['accuracy_pct']}%acc "
                f"{w['damage_taken']}dmg "
                f"[N{comp.get('normal_ratio',0):.1f}"
                f" F{comp.get('fast_ratio',0):.1f}"
                f" T{comp.get('tank_ratio',0):.1f}]"
            )
        return " | ".join(parts)


# Module-level singleton — imported by waves.py and game.py
_instance: RAGDirector | None = None


def get() -> RAGDirector:
    """Get or create the singleton RAGDirector instance."""
    global _instance
    if _instance is None:
        _instance = RAGDirector()
    return _instance