"""Document ingestion pipeline - stub"""
from pathlib import Path

ROUTE_MAP = {
    ".pdf":  ["stan", "oemx"],
    ".odx":  ["oscar"],
    ".pdx":  ["oscar"],
    ".docx": ["oemx", "tara"],
    ".html": ["intel"],
    ".url":  ["intel"],
}

class IngestionPipeline:
    def ingest(self, file_path: Path):
        raise NotImplementedError

    def _detect_type(self, file_path: Path) -> str:
        return file_path.suffix.lower()

    def _route(self, doc_type: str) -> list:
        return ROUTE_MAP.get(doc_type, ["stan"])
