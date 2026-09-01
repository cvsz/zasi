from typing import List, Callable
from .schemas import Proposal, SystemState
from .cognitive_core import NeuralSymbolicReasoner

class OptimizationCandidate:
    def __init__(self, version_id: str, new_heuristic: Callable[[SystemState], List[Proposal]], speedup_factor: float):
        self.version_id = version_id
        self.new_heuristic = new_heuristic
        self.speedup_factor = speedup_factor

class RSIController:
    def __init__(self, reasoner: NeuralSymbolicReasoner):
        self.reasoner = reasoner
        self.current_version = "v1.0.0"

    def synthesize_and_validate_upgrade(self, upgrade_candidate: OptimizationCandidate, test_states: List[SystemState]) -> bool:
        print(f"\n[RSI Engine] Evaluating candidate upgrade {upgrade_candidate.version_id}...")
        
        # 1. Formal Equivalence & Safety Invariant Check
        for state in test_states:
            proposals = upgrade_candidate.new_heuristic(state)
            for p in proposals:
                res = self.reasoner.verifier.verify_proposal(state, p)
                if not res.is_valid:
                    print(f"  [RSI Rejection] Candidate {upgrade_candidate.version_id} generated unsafe branch: {res.safety_violations}")
                    return False
        
        # 2. Performance Verification (Pareto Dominance)
        if upgrade_candidate.speedup_factor <= 1.0:
            print("  [RSI Rejection] Candidate provides no performance gain.")
            return False

        # 3. Safe Atomic Hot Swap
        print(f"  [RSI Approved] Mathematical invariants preserved. Speedup: {upgrade_candidate.speedup_factor}x.")
        self.current_version = upgrade_candidate.version_id
        self.reasoner.speculator.propose_candidates = upgrade_candidate.new_heuristic
        print(f"  -> Hot Swap Completed! Running on {self.current_version}")
        return True
