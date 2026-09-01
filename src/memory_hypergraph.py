"""
Universal Dynamic Memory & Neural-Symbolic Hypergraph Store
"""
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional

@dataclass
class HyperEdge:
    edge_id: str
    nodes: Set[str]
    relation: str
    weight: float = 1.0
    embedding: List[float] = field(default_factory=list)

class DynamicHypergraphMemory:
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[str, HyperEdge] = {}
        self.active_working_context: List[str] = []

    def insert_entity(self, entity_id: str, attributes: Dict[str, Any], embedding: Optional[List[float]] = None):
        self.nodes[entity_id] = {
            "attributes": attributes,
            "embedding": embedding or [0.0] * 64,
            "links": set()
        }

    def create_hyperedge(self, edge_id: str, node_ids: Set[str], relation: str, weight: float = 1.0):
        for node_id in node_ids:
            if node_id not in self.nodes:
                self.insert_entity(node_id, {"name": node_id})
            self.nodes[node_id]["links"].add(edge_id)
        
        self.edges[edge_id] = HyperEdge(
            edge_id=edge_id,
            nodes=node_ids,
            relation=relation,
            weight=weight
        )

    def query_context(self, active_focus: str) -> Dict[str, Any]:
        """Retrieves associative subgraph for zero-hallucination factual grounding."""
        if active_focus not in self.nodes:
            return {"focus": active_focus, "associated_facts": []}
        
        connected_edges = self.nodes[active_focus]["links"]
        facts = []
        for edge_id in connected_edges:
            edge = self.edges[edge_id]
            facts.append({
                "relation": edge.relation,
                "related_entities": list(edge.nodes - {active_focus}),
                "confidence": edge.weight
            })
        return {"focus": active_focus, "associated_facts": facts}
