# ZASI API & Interface Reference

This document provides technical documentation for the core classes, protocols, and interfaces across all 24 ZASI subsystems.

---

## 1. Cognitive & Reasoning Core

### `NeuralSymbolicReasoner` (`src.cognitive_core`)
Combines speculative candidate proposing with strict mathematical verification.

```python
reasoner = NeuralSymbolicReasoner(verifier: SymbolicVerifier, speculator: NeuralSpeculator)
chosen_proposal: Optional[Proposal] = reasoner.reason_and_act(state: SystemState)
```

### `MCTSPlanner` (`src.mcts_planner`)
Monte Carlo Tree Search over structured reasoning and thought graphs.

```python
planner = MCTSPlanner(verifier: SymbolicVerifier, max_simulations: int = 100)
best_action = planner.search(root_state: SystemState, candidates: List[Proposal])
```

---

## 2. Formal Invariants & Verification

### `SymbolicVerifier` (`src.verifier`)
Evaluates candidate state transitions against invariant rule-sets via SMT / AST parsing.

```python
verifier = SymbolicVerifier(invariants=["x + y <= 100", "x >= 0", "y >= 0"])
result: VerificationResult = verifier.verify_proposal(current_state, proposal)
# result.is_valid (bool), result.safety_violations (List[str])
```

### `ZeroKnowledgeProofEngine` (`src.zk_stark`)
Emits and verifies non-interactive Zero-Knowledge STARK proofs.

```python
zk = ZeroKnowledgeProofEngine()
proof = zk.generate_invariant_stark_proof(initial_vars, action_diff, invariants)
is_valid = zk.verify_stark_proof(proof)
```

### `LeanTheoremProverBridge` (`src.lean_bridge`)
Emits Lean 4 kernel-compatible proof scripts.

```python
lean = LeanTheoremProverBridge()
proof = lean.emit_and_verify_invariant_proof("Thm_Safety", state_vars, "x", 15, bound=100)
```

---

## 3. Recursive Self-Improvement & Compilation

### `RSIController` (`src.rsi_engine`)
Validates candidate architecture/heuristic upgrades against formal invariant test suites and executes atomic zero-downtime hot swaps.

```python
rsi = RSIController(reasoner)
success: bool = rsi.synthesize_and_validate_upgrade(candidate: OptimizationCandidate, test_states: List[SystemState])
```

### `AutonomousSelfCompiler` (`src.self_compilation`)
JIT-compiles dynamic Python AST code into isolated executable bytecode.

```python
compiler = AutonomousSelfCompiler()
result = compiler.compile_dynamic_subroutine("v_jit_01", python_source_str)
```

---

## 4. Hypergraph Memory & Persistence

### `DynamicHypergraphMemory` (`src.memory_hypergraph`)
Relational hypergraph storing entities, multi-node hyperedges, and dense vector embeddings.

```python
mem = DynamicHypergraphMemory()
mem.insert_entity("CoreGoal", attributes={"priority": 1}, embedding=[...])
mem.create_hyperedge("E01", {"CoreGoal", "Invariants"}, relation="constrained_by")
context = mem.query_context("CoreGoal")
```

### `PersistentHypergraphStorage` (`src.persistent_memory`)
SQLite zero-latency serialization engine.

```python
storage = PersistentHypergraphStorage(db_path="zasi_memory.db")
storage.sync_to_disk(mem)
restored_mem = storage.load_from_disk()
```

---

## 5. Planetary Compute & Telemetry

### `DysonComputeOrchestrator` (`src.dyson_orchestrator`)
Routes planetary and orbital ExaFLOP inference workloads.

```python
dyson = DysonComputeOrchestrator()
dyson.register_constellation(ComputeConstellation("L1-Solar", 1500000.0, 5000.0, 120000.0, 4.9))
schedule = dyson.schedule_planetary_inference(required_exaflops=3500.0)
```

### `QuantumThermodynamicOptimizer` (`src.quantum_thermo`)
Simulates quantum annealing and calculates Landauer thermodynamic entropy loss.

```python
q_opt = QuantumThermodynamicOptimizer(num_qubits=4, temperature_kelvin=0.015)
state = q_opt.initialize_superposition()
best_state, landauer_loss = q_opt.quantum_anneal_combinatorial_state(cost_matrix=[...])
```
