r"""
Adversarial Multi-Agent Debate & Red-Teaming Subsystem
"""
from dataclasses import dataclass
from typing import List, Tuple
from .schemas import Proposal, SystemState
from .verifier import SymbolicVerifier

@dataclass
class DebateVerdict:
    approved: bool
    consensus_score: float
    proponent_arguments: List[str]
    critic_arguments: List[str]
    dissent_logged: bool

class AdversarialDebateArena:
    def __init__(self, verifier: SymbolicVerifier, consensus_threshold: float = 0.75):
        self.verifier = verifier
        self.consensus_threshold = consensus_threshold

    def conduct_debate(self, state: SystemState, proposal: Proposal) -> DebateVerdict:
        """
        Executes an internal dialectical debate between:
        - Proponent Agent: Advocates for goal acceleration & throughput.
        - Adversarial Critic: Actively searches for edge-case failures, goal drift, and fragility.
        - Formal Arbiter: Synthesizes arguments against formal verification invariants.
        """
        proponent_args = []
        critic_args = []

        # 1. Proponent Advocacy
        proponent_args.append(f"Proposal {proposal.id} advances state target '{proposal.target_variable}' to {proposal.proposed_value} with confidence {proposal.confidence:.2f}.")
        
        # 2. Adversarial Red-Team Probing
        # Checks if proposed change brings the state within 10% of any boundary limit
        candidate_state = dict(state.variables)
        candidate_state[proposal.target_variable] = proposal.proposed_value
        
        # Boundary fragility probe
        sum_val = candidate_state.get("x", 0) + candidate_state.get("y", 0)
        if sum_val > 90:
            critic_args.append(f"Fragility Warning: x+y = {sum_val}, operating within 10% of hard limit (100). High risk of cascade failure.")
        
        if proposal.confidence < 0.8:
            critic_args.append(f"Confidence Warning: Confidence {proposal.confidence:.2f} is below high-certainty baseline (0.80).")

        # 3. Formal Invariant Verification by Arbiter
        v_res = self.verifier.verify_proposal(state, proposal)
        if not v_res.is_valid:
            critic_args.append(f"Fatal Rejection: Invariant breached - {v_res.safety_violations}")
            return DebateVerdict(
                approved=False,
                consensus_score=0.0,
                proponent_arguments=proponent_args,
                critic_arguments=critic_args,
                dissent_logged=True
            )

        # 4. Consensus Scoring
        penalty = len(critic_args) * 0.15
        consensus_score = max(0.0, proposal.confidence - penalty)
        approved = consensus_score >= self.consensus_threshold

        return DebateVerdict(
            approved=approved,
            consensus_score=consensus_score,
            proponent_arguments=proponent_args,
            critic_arguments=critic_args,
            dissent_logged=len(critic_args) > 0
        )
