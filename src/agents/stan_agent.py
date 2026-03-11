import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "knowledge"))

from dataclasses import dataclass
from typing import Optional
from stan_knowledge import ISO_14229_KNOWLEDGE
from vector_store import VectorStoreClient

COLLECTION_NAME = "vdip_stan_iso_standards"
PERSIST_PATH = "/home/minu/vdip-agent-platform/knowledge/chroma_db"


@dataclass
class STANResult:
    query: str
    answer: str
    sources: list
    clauses: list
    confidence: str


class STANAgent:

    def __init__(self, persist_path=PERSIST_PATH):
        self.persist_path = persist_path
        self.collection = None
        self._ready = False

    def setup(self):
        client = VectorStoreClient(path=self.persist_path)
        self.collection = client.get_or_create_collection(COLLECTION_NAME)
        print("STAN VectorStore ready. Chunks:", self.collection.count())
        self._ready = True
        return True

    def ingest_knowledge(self, force=False):
        if not self._ready:
            self.setup()
        if self.collection.count() > 0 and not force:
            print("Already indexed", self.collection.count(), "chunks.")
            return self.collection.count()
        print("Ingesting", len(ISO_14229_KNOWLEDGE), "ISO chunks...")
        ids = []
        docs = []
        metas = []
        for chunk in ISO_14229_KNOWLEDGE:
            ids.append(chunk["id"])
            docs.append(chunk["content"].strip())
            metas.append({
                "standard":    chunk["standard"],
                "section":     chunk["section"],
                "service_sid": chunk["service_sid"],
                "service_name": chunk["service_name"],
                "topic":       chunk["topic"]
            })
            print("  OK", chunk["id"])
        self.collection.upsert(ids=ids, documents=docs, metadatas=metas)
        print("STAN: indexed", self.collection.count(), "chunks.")
        return self.collection.count()

    def query(self, question, n_results=3, service_filter=None):
        if not self._ready:
            self.setup()
            self.ingest_knowledge()
        where = None
        if service_filter:
            where = {"service_sid": {"$in": [service_filter, "ALL"]}}
        results = self.collection.query([question], n_results, where=where)
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]
        sources = []
        for m in metas:
            sources.append(m.get("standard", "?") + " S" + m.get("section", "?") + " " + m.get("topic", ""))
        clauses = [m["section"] for m in metas]
        avg_dist = sum(distances) / len(distances) if distances else 1.0
        conf = "HIGH" if avg_dist < 0.3 else "MEDIUM" if avg_dist < 0.6 else "LOW"
        top = metas[0] if metas else {}
        ans = (
            "[" + top.get("standard", "?") + " S" + top.get("section", "?") + " " + top.get("topic", "") + "]\n\n"
            + (docs[0][:600] if docs else "No clause found.")
        )
        return STANResult(
            query=question,
            answer=ans,
            sources=sources,
            clauses=clauses,
            confidence=conf
        )

    def get_timing_requirements(self, sid):
        return self.query("P2 timing requirements " + sid, service_filter=sid)

    def get_nrc_rules(self, sid):
        return self.query("Negative response codes NRC " + sid, service_filter=sid)

    def get_did_requirements(self, did):
        return self.query("DID " + did + " requirements", service_filter="0x22")

    def print_result(self, r):
        print("\n" + "=" * 60)
        print("Q: ", r.query)
        print("[" + r.confidence + "] SOURCES:")
        for s in r.sources:
            print("  >", s)
        print("ANSWER:")
        print(r.answer[:400])
        print("=" * 60)


if __name__ == "__main__":
    stan = STANAgent()
    stan.setup()
    stan.ingest_knowledge()
    queries = [
        ("P2ServerMax default timing value", "0x10"),
        ("NRC for unsupported session type", "0x10"),
        ("VIN DID F190 requirements",        "0x22"),
        ("NRC for unsupported DID",          "0x22"),
        ("S3Server session timeout rules",   "0x10"),
    ]
    for q, sid in queries:
        stan.print_result(stan.query(q, service_filter=sid))
    print("\nSTAN ready.", stan.collection.count(), "chunks indexed.")
