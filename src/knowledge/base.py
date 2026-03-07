"""ChromaDB base layer - stub, implemented in S2.2"""
from .collections import AGENT_COLLECTIONS

class KnowledgeBase:
    def __init__(self, persist_path: str):
        self.persist_path = persist_path

    def get_collection(self, agent: str):
        raise NotImplementedError

    def add_documents(self, agent: str, chunks: list):
        raise NotImplementedError

    def query(self, agent: str, query: str, n_results: int = 5) -> list:
        raise NotImplementedError
