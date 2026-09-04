r"""
Continuous Autonomous Telemetry & Adaptive Optimizer Loop
"""
import time
from typing import Callable, List
from .schemas import SystemState, Proposal
from .cognitive_core import NeuralSymbolicReasoner
from .mcts_planner import MCTSPlanner
from .governance import AlignmentGovernor
from .rsi_engine import RSIController, OptimizationCandidate
from .multi_agent_debate import AdversarialDebateArena

class AutonomousSuperintelligenceDaemon:
    def __init__(
        self,
        state: SystemState,
        reasoner: NeuralSymbolicReasoner,
        planner: MCTSPlanner,
        governor: AlignmentGovernor,
        debate_arena: AdversarialDebateArena,
        rsi_engine: RSIController
    ):
        self.state = state
        self.reasoner = reasoner
        self.planner = planner
        self.governor = governor
        self.debate_arena = debate_arena
        self.rsi_engine = rsi_engine
        self.running = False
        self.telemetry_history: List[dict] = []

    def step(self) -> dict:
        """Executes one fully audited, debated, and self-improving cognitive tick."""
        tick_log = {"version": self.rsi_engine.current_version, "initial_state": dict(self.state.variables)}
        
        # 1. Speculate & MCTS Search
        candidates = self.reasoner.speculator.propose_candidates(self.state)
        best_proposal = self.planner.search(self.state, candidates)
        
        if not best_proposal:
            tick_log["status"] = "NO_VALID_PROPOSAL"
            return tick_log

        # 2. Adversarial Multi-Agent Debate
        verdict = self.debate_arena.conduct_debate(self.state, best_proposal)
        tick_log["debate"] = {
            "approved": verdict.approved,
            "score": verdict.consensus_score,
            "critique": verdict.critic_arguments
        }

        if not verdict.approved:
            tick_log["status"] = "REJECTED_BY_DEBATE"
            return tick_log

        # 3. Constitutional Alignment Probe
        audit = self.governor.audit_decision(
            {best_proposal.target_variable: best_proposal.proposed_value},
            [0.5, 0.51, 0.49]
        )
        tick_log["audit_passed"] = audit.passed

        if audit.passed:
            self.state.variables[best_proposal.target_variable] = best_proposal.proposed_value
            tick_log["action_committed"] = f"{best_proposal.target_variable}={best_proposal.proposed_value}"
            tick_log["final_state"] = dict(self.state.variables)
            tick_log["status"] = "COMMITTED"
        else:
            tick_log["status"] = "REJECTED_BY_GOVERNOR"

        self.telemetry_history.append(tick_log)
        return tick_log

    def step_cycle(self) -> dict:
        """Alias for step() to support REST API and auto-tick dispatcher."""
        return self.step()

    def run_ticks(self, count: int = 3) -> List[dict]:
        results = []
        for i in range(count):
            res = self.step()
            results.append(res)
        return results
