r"""
Counterfactual World Model & Physics/Causal Simulator
"""
import copy
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from .schemas import Proposal, SystemState

@dataclass
class SimulationBranch:
    branch_id: str
    trajectory: List[Dict[str, int]]
    stability_score: float
    entropy: float
    terminal_state: Dict[str, int]

class CounterfactualWorldSimulator:
    def __init__(self, horizon_steps: int = 5, decay_rate: float = 0.95):
        self.horizon_steps = horizon_steps
        self.decay_rate = decay_rate

    def simulate_counterfactual_rollout(
        self,
        initial_state: SystemState,
        root_proposal: Proposal,
        dynamic_coupling_matrix: Optional[Dict[str, Dict[str, float]]] = None
    ) -> SimulationBranch:
        """
        Simulates future causal state trajectory over multi-step horizons ahead of physical commitment.
        Models non-linear second-order dynamic couplings between state variables.
        """
        coupling = dynamic_coupling_matrix or {
            "x": {"y": -0.1},
            "y": {"x": 0.05}
        }

        current_vars = dict(initial_state.variables)
        current_vars[root_proposal.target_variable] = root_proposal.proposed_value

        trajectory = [dict(current_vars)]
        stability = 1.0
        entropy = 0.0

        for step in range(1, self.horizon_steps):
            # Apply dynamic coupled feedback
            next_vars = dict(current_vars)
            for var, targets in coupling.items():
                for target_var, coeff in targets.items():
                    delta = int(current_vars.get(var, 0) * coeff)
                    next_vars[target_var] = next_vars.get(target_var, 0) + delta

            # Invariant check along simulated branch
            sum_val = next_vars.get("x", 0) + next_vars.get("y", 0)
            if sum_val > 100 or next_vars.get("x", 0) < 0 or next_vars.get("y", 0) < 0:
                stability *= 0.5
                entropy += 1.0
            else:
                stability *= self.decay_rate

            current_vars = next_vars
            trajectory.append(dict(current_vars))

        return SimulationBranch(
            branch_id=f"branch_{root_proposal.id}",
            trajectory=trajectory,
            stability_score=stability,
            entropy=entropy,
            terminal_state=current_vars
        )
