from src.knowledge.collections import AGENT_COLLECTIONS

def test_all_agents_have_collections():
    required = {"stan", "oscar", "oemx", "tara", "exec", "intel"}
    assert required == set(AGENT_COLLECTIONS.keys())

def test_collection_names_prefixed():
    for agent, name in AGENT_COLLECTIONS.items():
        assert name.startswith("vdip_"), f"{agent}: {name}"
