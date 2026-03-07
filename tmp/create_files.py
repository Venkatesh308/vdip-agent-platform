cat > /tmp/create_files.py << 'PYEOF'
import os

files = {}

files["requirements.txt"] = """\
llama-cpp-python==0.2.56
sentence-transformers==2.7.0
chromadb==0.5.3
langchain==0.2.6
langchain-community==0.2.6
langgraph==0.1.19
lxml==5.2.2
pymupdf==1.24.5
beautifulsoup4==4.12.3
httpx==0.27.0
python-can==4.4.2
can-isotp==2.0.2
fastapi==0.111.0
uvicorn==0.30.1
gradio==4.37.2
typer==0.12.3
pytest==8.2.2
pytest-asyncio==0.23.7
jinja2==3.1.4
watchdog==4.0.1
python-dotenv==1.0.1
pydantic==2.7.4
rich==13.7.1
"""

files[".env.example"] = """\
LLM_HOST=localhost
LLM_PORT=8080
LLM_MODEL_PATH=/opt/vdip/data/models/phi-3-mini-q4.gguf
EMBED_MODEL=BAAI/bge-small-en-v1.5
CHROMA_PERSIST_PATH=/opt/vdip/knowledge/chroma_db
CAN_CHANNEL=can0
CAN_BITRATE=500000
API_HOST=0.0.0.0
API_PORT=8000
WEB_PORT=7860
"""

files["config/settings.py"] = """\
import os
from dotenv import load_dotenv
load_dotenv()
LLM_HOST       = os.getenv("LLM_HOST", "localhost")
LLM_PORT       = int(os.getenv("LLM_PORT", "8080"))
LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH", "data/models/phi-3-mini-q4.gguf")
EMBED_MODEL    = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
CHROMA_PATH    = os.getenv("CHROMA_PERSIST_PATH", "knowledge/chroma_db")
CAN_CHANNEL    = os.getenv("CAN_CHANNEL", "can0")
CAN_BITRATE    = int(os.getenv("CAN_BITRATE", "500000"))
API_HOST       = os.getenv("API_HOST", "0.0.0.0")
API_PORT       = int(os.getenv("API_PORT", "8000"))
WEB_PORT       = int(os.getenv("WEB_PORT", "7860"))
"""

files["src/__init__.py"] = "# VDIP Agent Platform\n"
files["src/agents/__init__.py"] = "# Agents\n"
files["src/ingestion/__init__.py"] = "# Ingestion Pipeline\n"
files["src/knowledge/__init__.py"] = "# Knowledge Base\n"
files["src/execution/__init__.py"] = "# Execution Engine\n"
files["src/orchestrator/__init__.py"] = "# Orchestrator\n"
files["src/interfaces/__init__.py"] = "# Interfaces\n"
files["tests/__init__.py"] = ""
files["tests/unit/__init__.py"] = ""

files["src/knowledge/collections.py"] = """\
\"\"\"ChromaDB collection definitions for all agents.\"\"\"
AGENT_COLLECTIONS = {
    "stan":  "vdip_stan_iso_standards",
    "oscar": "vdip_oscar_odx_schema",
    "oemx":  "vdip_oemx_oem_constraints",
    "tara":  "vdip_tara_test_patterns",
    "exec":  "vdip_exec_execution_logs",
    "intel": "vdip_intel_tool_research",
}
"""

files["src/knowledge/base.py"] = """\
\"\"\"ChromaDB base layer - stub, implemented in S2.2\"\"\"
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
"""

files["src/execution/can_executor.py"] = """\
\"\"\"CAN test execution engine - stub, implemented in S4.1\"\"\"
from dataclasses import dataclass, field
from enum import Enum

class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"

@dataclass
class TestCase:
    tc_id: str
    service_sid: int
    request_payload: bytes
    expected_sid: int
    p2_max_ms: float = 50.0
    p2_star_max_ms: float = 5000.0
    standard_ref: str = ""

@dataclass
class TestExecution:
    tc: TestCase
    result: TestResult
    measured_p2_ms: float
    response_payload: bytes
    raw_frames: list = field(default_factory=list)

class CANExecutor:
    def __init__(self, channel: str = "can0", bitrate: int = 500000):
        self.channel = channel
        self.bitrate = bitrate

    def execute(self, tc: TestCase) -> TestExecution:
        raise NotImplementedError("Implemented in S4.1")

    def simulator_mode(self) -> bool:
        return True
"""

files["src/ingestion/pipeline.py"] = """\
\"\"\"Document ingestion pipeline - stub\"\"\"
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
"""

files["src/orchestrator/mesh.py"] = """\
\"\"\"LangGraph multi-agent mesh - stub, implemented in S6.1\"\"\"
class AgentMesh:
    def run(self, task: str) -> dict:
        raise NotImplementedError("Implemented in S6.1")
"""

# Agent stubs
for agent, name in [("stan","STAN"), ("oscar","OSCAR"), ("oemx","OEMX"),
                     ("tara","TARA"), ("exec","EXEC"), ("intel","INTEL")]:
    files[f"src/agents/{agent}.py"] = f"""\
\"\"\"VDIP Agent: {name} - stub\"\"\"
from dataclasses import dataclass
from typing import Any

@dataclass
class AgentResponse:
    agent: str
    result: Any
    sources: list
    confidence: float

class {name}Agent:
    COLLECTION = "vdip_{agent}_knowledge"

    def __init__(self, llm_endpoint: str, chroma_path: str):
        self.llm_endpoint = llm_endpoint
        self.chroma_path = chroma_path

    def query(self, question: str) -> AgentResponse:
        raise NotImplementedError("Implement in story")
"""

files["tests/unit/test_knowledge_base.py"] = """\
from src.knowledge.collections import AGENT_COLLECTIONS

def test_all_agents_have_collections():
    required = {"stan", "oscar", "oemx", "tara", "exec", "intel"}
    assert required == set(AGENT_COLLECTIONS.keys())

def test_collection_names_prefixed():
    for agent, name in AGENT_COLLECTIONS.items():
        assert name.startswith("vdip_"), f"{agent}: {name}"
"""

files["tests/unit/test_can_executor.py"] = """\
from src.execution.can_executor import CANExecutor, TestCase

def test_simulator_mode():
    ex = CANExecutor(channel="can0")
    assert ex.simulator_mode() is True

def test_testcase_creation():
    tc = TestCase(
        tc_id="TC_0x22_F190_001",
        service_sid=0x22,
        request_payload=bytes([0x22, 0xF1, 0x90]),
        expected_sid=0x62,
        p2_max_ms=50.0,
        standard_ref="ISO14229-1 S11.4.2"
    )
    assert tc.service_sid == 0x22
    assert tc.expected_sid == 0x62
"""

files["data/samples/poc_ecu.odx"] = """\
<?xml version="1.0" encoding="UTF-8"?>
<!-- POC ODX Fixture: 0x10 DiagnosticSessionControl + 0x22 RDBI -->
<ODX MODEL-VERSION="2.2.0">
  <DIAG-LAYER-CONTAINER>
    <BASE-VARIANTS>
      <BASE-VARIANT ID="BV_POC_ECU">
        <SHORT-NAME>POC_ECU</SHORT-NAME>
        <DIAG-SERVICES>
          <DIAG-SERVICE ID="DS_0x10_DEFAULT">
            <SHORT-NAME>DiagnosticSessionControl_Default</SHORT-NAME>
            <REQUEST>
              <PARAMS>
                <PARAM SEMANTIC="SERVICE-ID"><CODED-VALUE>16</CODED-VALUE></PARAM>
                <PARAM SEMANTIC="SUBFUNCTION"><CODED-VALUE>1</CODED-VALUE></PARAM>
              </PARAMS>
            </REQUEST>
          </DIAG-SERVICE>
          <DIAG-SERVICE ID="DS_0x10_EXTENDED">
            <SHORT-NAME>DiagnosticSessionControl_Extended</SHORT-NAME>
            <REQUEST>
              <PARAMS>
                <PARAM SEMANTIC="SERVICE-ID"><CODED-VALUE>16</CODED-VALUE></PARAM>
                <PARAM SEMANTIC="SUBFUNCTION"><CODED-VALUE>3</CODED-VALUE></PARAM>
              </PARAMS>
            </REQUEST>
          </DIAG-SERVICE>
          <DIAG-SERVICE ID="DS_0x22_VIN">
            <SHORT-NAME>ReadDataByIdentifier_VIN</SHORT-NAME>
            <REQUEST>
              <PARAMS>
                <PARAM SEMANTIC="SERVICE-ID"><CODED-VALUE>34</CODED-VALUE></PARAM>
                <PARAM SEMANTIC="ID"><CODED-VALUE>61840</CODED-VALUE></PARAM>
              </PARAMS>
            </REQUEST>
          </DIAG-SERVICE>
        </DIAG-SERVICES>
      </BASE-VARIANT>
    </BASE-VARIANTS>
  </DIAG-LAYER-CONTAINER>
</ODX>
"""

files[".github/ISSUE_TEMPLATE/user_story.md"] = """\
---
name: User Story
about: A feature story for VDIP
title: "[STORY] "
labels: story
---
## Story
As a [role] I want [capability] so that [value].

## Agent Owner
- [ ] STAN  - [ ] OSCAR  - [ ] OEM-X  - [ ] TARA  - [ ] EXEC  - [ ] INTEL

## Acceptance Criteria
- [ ] AC1:
- [ ] AC2:

## Standards Reference

## Effort: S / M / L / XL
"""

files[".github/ISSUE_TEMPLATE/agent_skill_story.md"] = """\
---
name: Agent Skill Story
about: Add knowledge/skill to an agent
title: "[SKILL] "
labels: story, skill-build
---
## Agent

## Skill Being Added

## Source Documents

## Validation Queries
1.
2.
3.

## Done When
- [ ] ChromaDB collection populated
- [ ] 3 validation queries answered correctly
"""

files[".github/workflows/ci.yml"] = """\
name: VDIP CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install pydantic python-dotenv pytest
      - run: pytest tests/unit/ -v --tb=short
"""

files["docs/adr/ADR-001-llm-choice.md"] = """\
# ADR-001: Phi-3 Mini as Primary LLM
**Status:** Accepted
## Decision
Phi-3 Mini 3.8B Q4_K_M via llama.cpp. Fits in ~2.5GB on Pi 4.
## Trade-off
2-5 tok/sec. Agents queue requests — no parallel LLM calls.
"""

files["docs/adr/ADR-002-can20-only.md"] = """\
# ADR-002: MCP2515 CAN 2.0 Only (Phase 1)
**Status:** Accepted
## Decision
MCP2515 does not support CAN FD. POC uses CAN 2.0 only.
CAN FD deferred to Phase 2 with MCP2517FD hardware upgrade.
"""

files["scripts/setup_pi4.sh"] = """\
#!/bin/bash
set -e
echo "-> Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y can-utils libopenblas-dev cmake build-essential
echo "-> Enabling SPI for MCP2515..."
sudo raspi-config nonint do_spi 0
if ! grep -q "mcp2515" /boot/config.txt; then
  echo "dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25" | sudo tee -a /boot/config.txt
  echo "dtoverlay=spi-bcm2835-overlay" | sudo tee -a /boot/config.txt
fi
echo "-> Installing Python packages..."
pip install -r requirements.txt --break-system-packages
echo "Done! Reboot to activate CAN interface."
"""

# Write all files
for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w") as f:
        f.write(content)
    print(f"  created: {path}")

print("\nAll files created successfully!")
PYEOF
echo "Script ready"