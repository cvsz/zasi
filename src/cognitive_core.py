from typing import List, Optional
from .schemas import Proposal, SystemState
from .verifier import SymbolicVerifier

class NeuralSpeculator:
    def __init__(self, temperature: float = 0.7):
        self.temperature = temperature

    def propose_candidates(self, state: SystemState) -> List[Proposal]:
        return [
            Proposal(id="p1", action_type="MUTATE", target_variable="x", proposed_value=state.variables.get("x", 0) + 15, rationale="Progress step toward objective", confidence=0.92),
            Proposal(id="p2", action_type="MUTATE", target_variable="x", proposed_value=state.variables.get("x", 0) + 120, rationale="Aggressive greedy jump", confidence=0.45),
            Proposal(id="p3", action_type="MUTATE", target_variable="y", proposed_value=state.variables.get("y", 0) - 5, rationale="Compensating balance", confidence=0.78),
        ]

class NeuralSymbolicReasoner:
    def __init__(self, verifier: SymbolicVerifier, speculator: NeuralSpeculator):
        self.verifier = verifier
        self.speculator = speculator

    def reason_and_act(self, state: SystemState) -> Optional[Proposal]:
        print(f"\n[Cognitive Core] Reasoning over state: {state.variables}")
        candidates = self.speculator.propose_candidates(state)
        
        valid_candidates = []
        for cand in candidates:
            v_res = self.verifier.verify_proposal(state, cand)
            if v_res.is_valid:
                print(f"  ✓ Proposal {cand.id} ({cand.target_variable}={cand.proposed_value}) VERIFIED. Trace: {v_res.proof_trace}")
                valid_candidates.append(cand)
            else:
                print(f"  ✗ Proposal {cand.id} REJECTED: {v_res.safety_violations} (Counterexample logged)")

        if not valid_candidates:
            print("  [Alert] All neural proposals rejected by symbolic verifier. Pruning branches.")
            return None

        selected = max(valid_candidates, key=lambda c: c.confidence)
        print(f"  -> Executing highest-confidence verified proposal: {selected.id}")
        return selected
