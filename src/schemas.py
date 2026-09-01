from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class Proposal:
    id: str
    action_type: str
    target_variable: str
    proposed_value: int
    rationale: str
    confidence: float

@dataclass
class VerificationResult:
    is_valid: bool
    counterexample: Optional[Dict[str, Any]] = None
    proof_trace: Optional[str] = None
    safety_violations: List[str] = field(default_factory=list)

@dataclass
class SystemState:
    variables: Dict[str, int]
    invariants: List[str]
    step_count: int = 0
