# ADR-001: Phi-3 Mini as Primary LLM
**Status:** Accepted
## Decision
Phi-3 Mini 3.8B Q4_K_M via llama.cpp. Fits in ~2.5GB on Pi 4.
## Trade-off
2-5 tok/sec. Agents queue requests — no parallel LLM calls.
