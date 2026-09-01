r"""
Monte Carlo Tree Search (MCTS) & Search-over-Thoughts Engine
"""
import math
import random
from typing import List, Optional, Dict
from .schemas import Proposal, SystemState
from .verifier import SymbolicVerifier

class MCTSNode:
    def __init__(self, state: SystemState, parent: Optional['MCTSNode'] = None, action: Optional[Proposal] = None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children: List['MCTSNode'] = []
        self.visits: int = 0
        self.value: float = 0.0

    def is_fully_expanded(self, num_actions: int) -> bool:
        return len(self.children) >= num_actions

    def ucb1(self, c_param: float = 1.414) -> float:
        if self.visits == 0:
            return float('inf')
        return (self.value / self.visits) + c_param * math.sqrt(math.log(self.parent.visits) / self.visits)

class MCTSPlanner:
    def __init__(self, verifier: SymbolicVerifier, max_simulations: int = 50):
        self.verifier = verifier
        self.max_simulations = max_simulations

    def search(self, root_state: SystemState, candidate_proposals: List[Proposal]) -> Optional[Proposal]:
        root = MCTSNode(state=root_state)

        for _ in range(self.max_simulations):
            node = root

            # 1. Selection
            while node.children and node.is_fully_expanded(len(candidate_proposals)):
                node = max(node.children, key=lambda n: n.ucb1())

            # 2. Expansion & Formal Filter
            untried_actions = [a for a in candidate_proposals if a.id not in [c.action.id for c in node.children if c.action]]
            if untried_actions:
                action = random.choice(untried_actions)
                # Verify soundness before adding child
                v_res = self.verifier.verify_proposal(node.state, action)
                if v_res.is_valid:
                    new_vars = dict(node.state.variables)
                    new_vars[action.target_variable] = action.proposed_value
                    next_state = SystemState(variables=new_vars, invariants=node.state.invariants)
                    child_node = MCTSNode(state=next_state, parent=node, action=action)
                    node.children.append(child_node)
                    node = child_node

            # 3. Simulation / Value Estimation
            reward = node.action.confidence if node.action else 0.5

            # 4. Backpropagation
            curr = node
            while curr is not None:
                curr.visits += 1
                curr.value += reward
                curr = curr.parent

        if not root.children:
            return None

        # Return best child by visits
        best_child = max(root.children, key=lambda n: n.visits)
        return best_child.action
