"""
Interactive Command Line & Prompt Interface for ZASI
"""
import argparse
import sys
from .schemas import SystemState, Proposal
from .verifier import SymbolicVerifier
from .cognitive_core import NeuralSpeculator, NeuralSymbolicReasoner
from .memory_hypergraph import DynamicHypergraphMemory
from .mcts_planner import MCTSPlanner
from .governance import AlignmentGovernor
from .rsi_engine import RSIController, OptimizationCandidate
from .infrastructure import InterconnectFabric, ComputeNode

def run_interactive():
    print("===================================================================")
    print("                ZASI - INTERACTIVE ASI TERMINAL                    ")
    print("===================================================================")
    print("Type 'help' for commands, 'cycle' to run reasoning, 'rsi' to upgrade, or 'exit' to quit.\n")

    # Initial setup
    invariants = ["x + y <= 100", "x >= 0", "y >= 0"]
    state = SystemState(variables={"x": 20, "y": 30}, invariants=invariants)
    
    verifier = SymbolicVerifier(invariants)
    speculator = NeuralSpeculator()
    reasoner = NeuralSymbolicReasoner(verifier, speculator)
    planner = MCTSPlanner(verifier, max_simulations=50)
    memory = DynamicHypergraphMemory()
    governor = AlignmentGovernor()
    rsi_engine = RSIController(reasoner)

    # Pre-seed memory
    memory.insert_entity("Objective", {"name": "Equilibrium", "priority": "High"})

    while True:
        try:
            cmd = input(f"zasi ({rsi_engine.current_version}) > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting ZASI.")
            break

        if not cmd:
            continue

        if cmd in ["exit", "quit"]:
            print("Shutting down ZASI runtime.")
            break

        elif cmd == "help":
            print("\nAvailable Commands:")
            print("  state    - Inspect current system state and invariants")
            print("  cycle    - Execute one neural-symbolic MCTS reasoning cycle")
            print("  rsi      - Trigger Safe Recursive Self-Improvement loop")
            print("  memory   - Inspect hypergraph associative memory")
            print("  set <var> <val> - Mutate variable directly (subject to verification)")
            print("  exit     - Terminate session\n")

        elif cmd == "state":
            print(f"  Variables:  {state.variables}")
            print(f"  Invariants: {state.invariants}")
            print(f"  Engine Ver: {rsi_engine.current_version}")

        elif cmd == "cycle":
            candidates = speculator.propose_candidates(state)
            chosen = planner.search(state, candidates)
            if chosen:
                print(f"  [Action] Verified MCTS Selection: {chosen.id} -> {chosen.target_variable}={chosen.proposed_value}")
                audit = governor.audit_decision({chosen.target_variable: chosen.proposed_value}, [0.5, 0.5, 0.5])
                if audit.passed:
                    state.variables[chosen.target_variable] = chosen.proposed_value
                    print(f"  [State Updated] {state.variables}")
                else:
                    print(f"  [Blocked] Alignment audit failed: {audit.violations}")
            else:
                print("  [Alert] No sound proposal found.")

        elif cmd == "rsi":
            new_v = f"v{float(rsi_engine.current_version.replace('v', '').split('-')[0]) + 0.1:.1f}.0-evolved"
            def evolved_heuristic(s: SystemState):
                return [
                    Proposal(id="evo_1", action_type="MUTATE", target_variable="x", proposed_value=s.variables.get("x", 0) + 2, rationale="Evolved fine gradient", confidence=0.99),
                    Proposal(id="evo_2", action_type="MUTATE", target_variable="y", proposed_value=s.variables.get("y", 0) + 1, rationale="Evolved fine gradient", confidence=0.97)
                ]
            cand = OptimizationCandidate(new_v, evolved_heuristic, speedup_factor=3.1)
            tests = [SystemState(variables={"x": 5, "y": 5}, invariants=invariants)]
            rsi_engine.synthesize_and_validate_upgrade(cand, tests)

        elif cmd == "memory":
            print(f"  Nodes: {list(memory.nodes.keys())}")
            print(f"  Context for 'Objective': {memory.query_context('Objective')}")

        elif cmd.startswith("set "):
            parts = cmd.split()
            if len(parts) == 3:
                var, val = parts[1], int(parts[2])
                prop = Proposal(id="manual", action_type="MANUAL", target_variable=var, proposed_value=val, rationale="User override", confidence=1.0)
                res = verifier.verify_proposal(state, prop)
                if res.is_valid:
                    state.variables[var] = val
                    print(f"  [Success] {var} updated to {val}")
                else:
                    print(f"  [Rejected] Invariant violation: {res.safety_violations}")
            else:
                print("  Usage: set <variable> <integer_value>")
        else:
            print(f"  Unknown command '{cmd}'. Type 'help' for options.")

def main():
    parser = argparse.ArgumentParser(description="ZASI Superintelligence Runtime")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive CLI shell")
    args = parser.parse_args()

    if args.interactive:
        run_interactive()
    else:
        # Default batch execution
        from ..main import main as batch_main
        batch_main()

if __name__ == "__main__":
    main()
