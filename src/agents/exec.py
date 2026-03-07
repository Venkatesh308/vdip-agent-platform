"""VDIP Agent: EXEC - stub"""
from dataclasses import dataclass
from typing import Any

@dataclass
class AgentResponse:
    agent: str
    result: Any
    sources: list
    confidence: float

class EXECAgent:
    COLLECTION = "vdip_exec_knowledge"

    def __init__(self, llm_endpoint: str, chroma_path: str):
        self.llm_endpoint = llm_endpoint
        self.chroma_path = chroma_path

    def query(self, question: str) -> AgentResponse:
        raise NotImplementedError("Implement in story")
