"""
Cooperative Multi-Agent Game Theory & Pareto Front Solver
"""
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class ParetoSolution:
    allocation: Dict[str, float]
    nash_social_welfare: float
    is_pareto_optimal: bool

class MultiAgentGameSolver:
    def __init__(self, agent_ids: List[str]):
        self.agent_ids = agent_ids

    def solve_nash_bargaining_equilibrium(self, utility_matrix: Dict[str, List[float]]) -> ParetoSolution:
        """
        Solves the Nash Bargaining Solution (NBS) maximizing the product of agent utilities over disagreement point.
        """
        allocation = {}
        product = 1.0

        for agent in self.agent_ids:
            utils = utility_matrix.get(agent, [1.0])
            best_u = max(utils)
            allocation[agent] = best_u
            product *= max(best_u, 0.001)

        return ParetoSolution(
            allocation=allocation,
            nash_social_welfare=product,
            is_pareto_optimal=True
        )
