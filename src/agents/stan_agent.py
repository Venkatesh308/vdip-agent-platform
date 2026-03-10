"""
STAN Agent — ISO Standards Analyst
Stores ISO 14229-1 and ISO 15765-2 knowledge in ChromaDB.
Answers requirement queries grounded in real standard clauses.
"""

import os
import json
from dataclasses import dataclass
from typing import Optional
from stan_knowledge import ISO_14229_KNOWLEDGE


# ── ChromaDB + Embeddings ────────────────────────────────
try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("WARNING: chromadb not installed. Run: pip3 install chromadb")

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False
    print("WARNING: sentence-transformers not installed.")


COLLECTION_NAME = "vdip_stan_iso_standards"
CHROMA_PATH     = os.getenv("CHROMA_PERSIST_PATH",
                  "/home/minu/vdip-agent-platform/knowledge/chroma_db")


# ── Data Classes ─────────────────────────────────────────
@dataclass
class STANResult:
    query: str
    answer: str
    sources: list[str]
    clauses: list[str]
    confidence: str


# ── STAN Agent ────────────────────────────────────────────
class STANAgent:
    """
    STAN — Standards Analyst Agent.
    Answers ISO 14229-1 and ISO 15765-2 requirement queries
    using ChromaDB vector search over built-in knowledge base.
    """

    def __init__(self, chroma_path: str = CHROMA_PATH):
        self.chroma_path = chroma_path
        self.collection  = None
        self.embed_model = None
        self._ready      = False

    # ── Setup ────────────────────────────────────────────
    def setup(self) -> bool:
        """Initialise ChromaDB collection and embedding model."""
        if not CHROMA_AVAILABLE:
            print("ERROR: chromadb not available.")
            return False

        print("→ Initialising STAN agent...")

        # ChromaDB persistent client
        os.makedirs(self.chroma_path, exist_ok=True)
        client = chromadb.PersistentClient(path=self.chroma_path)

        # Embedding function
        if ST_AVAILABLE:
            print("→ Loading BGE-small embedding model...")
            self.embed_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="BAAI/bge-small-en-v1.5"
            )
        else:
            print("→ Using default ChromaDB embeddings...")
            ef = embedding_functions.DefaultEmbeddingFunction()

        # Get or create collection
        self.collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"description": "ISO 14229-1 and ISO 15765-2 knowledge"}
        )

        print(f"→ Collection '{COLLECTION_NAME}' ready.")
        self._ready = True
        return True

    # ── Ingest ───────────────────────────────────────────
    def ingest_knowledge(self, force: bool = False) -> int:
        """
        Ingest built-in ISO knowledge into ChromaDB.
        Skips if already ingested unless force=True.
        """
        if not self._ready:
            self.setup()

        existing = self.collection.count()
        if existing > 0 and not force:
            print(f"→ STAN: {existing} chunks already in ChromaDB. Skipping ingest.")
            print("   Use force=True to re-ingest.")
            return existing

        print(f"→ Ingesting {len(ISO_14229_KNOWLEDGE)} ISO knowledge chunks...")

        ids       = []
        documents = []
        metadatas = []

        for chunk in ISO_14229_KNOWLEDGE:
            ids.append(chunk["id"])
            documents.append(chunk["content"].strip())
            metadatas.append({
                "standard":     chunk["standard"],
                "section":      chunk["section"],
                "service_sid":  chunk["service_sid"],
                "service_name": chunk["service_name"],
                "topic":        chunk["topic"],
            })

        # Batch upsert
        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )

        total = self.collection.count()
        print(f"✓ STAN: {total} chunks ingested into ChromaDB.")
        return total

    # ── Query ────────────────────────────────────────────
    def query(self, question: str, n_results: int = 3,
              service_filter: Optional[str] = None) -> STANResult:
        """
        Query STAN with a natural language or technical question.
        Returns grounded answer with source references.
        """
        if not self._ready:
            self.setup()
            self.ingest_knowledge()

        # Optional filter by service SID
        where = None
        if service_filter:
            where = {"service_sid": {"$in": [service_filter, "ALL"]}}

        results = self.collection.query(
            query_texts=[question],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        docs      = results["documents"][0]
        metas     = results["metadatas"][0]
        distances = results["distances"][0]

        # Build grounded answer
        sources = []
        clauses = []
        context_parts = []

        for doc, meta, dist in zip(docs, metas, distances):
            ref = f"{meta['standard']} §{meta['section']} — {meta['topic']}"
            sources.append(ref)
            clauses.append(meta["section"])
            context_parts.append(
                f"[{meta['standard']} §{meta['section']} — {meta['topic']}]\n{doc}"
            )

        # Confidence based on distance
        avg_dist   = sum(distances) / len(distances) if distances else 1.0
        confidence = "HIGH" if avg_dist < 0.5 else "MEDIUM" if avg_dist < 1.0 else "LOW"

        # Build answer from top result
        top_meta = metas[0] if metas else {}
        answer = (
            f"Based on {top_meta.get('standard','ISO14229-1')} "
            f"§{top_meta.get('section','?')} "
            f"({top_meta.get('topic','')}):\n\n"
            + docs[0][:800] if docs else "No relevant clause found."
        )

        return STANResult(
            query=question,
            answer=answer,
            sources=sources,
            clauses=clauses,
            confidence=confidence
        )

    # ── Convenience Methods ──────────────────────────────
    def get_timing_requirements(self, service_sid: str) -> STANResult:
        """Get timing requirements for a specific service."""
        return self.query(
            f"What are the P2 and P2* timing requirements for service {service_sid}?",
            service_filter=service_sid
        )

    def get_nrc_rules(self, service_sid: str) -> STANResult:
        """Get NRC rules for a specific service."""
        return self.query(
            f"What negative response codes NRC apply to service {service_sid}?",
            service_filter=service_sid
        )

    def get_did_requirements(self, did_hex: str) -> STANResult:
        """Get requirements for a specific DID."""
        return self.query(
            f"What are the requirements for DID {did_hex} in ReadDataByIdentifier?",
            service_filter="0x22"
        )

    def get_session_rules(self, session_type: str) -> STANResult:
        """Get session transition rules."""
        return self.query(
            f"What are the rules for {session_type} session transitions?",
            service_filter="0x10"
        )

    def validate_test_case(self, tc_description: str) -> STANResult:
        """Validate a test case against ISO requirements."""
        return self.query(
            f"Is this test case correct per ISO 14229-1: {tc_description}"
        )

    def print_result(self, result: STANResult):
        """Pretty print a STAN query result."""
        print("\n" + "═" * 60)
        print(f"QUERY:      {result.query}")
        print(f"CONFIDENCE: {result.confidence}")
        print("─" * 60)
        print("SOURCES:")
        for s in result.sources:
            print(f"  ▸ {s}")
        print("─" * 60)
        print("ANSWER:")
        print(result.answer[:600])
        print("═" * 60)


# ── CLI Entry Point ───────────────────────────────────────
if __name__ == "__main__":
    import sys

    stan = STANAgent()
    stan.setup()
    stan.ingest_knowledge()

    print("\n" + "═" * 60)
    print("STAN Agent — Interactive Query Mode")
    print("Type your question. Commands: 'exit', 'stats'")
    print("═" * 60)

    # Run validation queries
    test_queries = [
        ("0x10 timing", "0x10"),
        ("What NRC should be returned for unsupported session type?", "0x10"),
        ("VIN requirements for 0xF190", "0x22"),
        ("What NRC for unsupported DID in ReadDataByIdentifier?", "0x22"),
        ("P2ServerMax default value", None),
        ("Is NRC 0x33 valid for VIN read in default session?", "0x22"),
    ]

    print("\n→ Running validation queries...\n")
    for question, sid_filter in test_queries:
        result = stan.query(question, service_filter=sid_filter)
        stan.print_result(result)

    print(f"\n✓ STAN agent validation complete.")
    print(f"  Total chunks in ChromaDB: {stan.collection.count()}")

    # Interactive mode
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        while True:
            try:
                q = input("\nSTAN> ").strip()
                if q.lower() in ("exit", "quit"):
                    break
                if q.lower() == "stats":
                    print(f"Chunks in DB: {stan.collection.count()}")
                    continue
                if q:
                    result = stan.query(q)
                    stan.print_result(result)
            except KeyboardInterrupt:
                break
