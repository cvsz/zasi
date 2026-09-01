"""
Comprehensive End-to-End Test Suite for All 28 ZASI Subsystems
"""
import unittest
import os
from src import (
    SystemState,
    Proposal,
    SymbolicVerifier,
    NeuralSpeculator,
    NeuralSymbolicReasoner,
    OptimizationCandidate,
    RSIController,
    DynamicHypergraphMemory,
    PersistentHypergraphStorage,
    MCTSPlanner,
    AlignmentGovernor,
    AdversarialDebateArena,
    CounterfactualWorldSimulator,
    ActionActuatorEngine,
    JITMicrokernelSynthesizer,
    InterconnectFabric,
    ComputeNode,
    AutonomousSuperintelligenceDaemon,
    DistributedWorkerPool,
    RaftConsensusCoordinator,
    FoundationModelAdapter,
    LeanTheoremProverBridge,
    AdversarialStressTester,
    AutonomousSelfCompiler,
    CausalDiscoveryEngine,
    MultiAgentGameSolver,
    CryptographicInvariantLedger,
    QuantumThermodynamicOptimizer,
    P2PGossipSwarm,
    AutonomousCodeSynthesizer,
    MicroVMSandbox,
    ZeroKnowledgeProofEngine,
    ModelEpistemicProtocol,
    DysonComputeOrchestrator,
    ComputeConstellation,
    JAVISVoiceMultimodalInterface,
    AudioWaveformPacket,
    MultimodalVisualFrame,
    RoboticsIoTController,
    OSTelemetrySupervisor,
    MultiPersonaTacticalSwarm
)

class TestZASISubsystems(unittest.TestCase):

    def setUp(self):
        self.invariants = ["x + y <= 100", "x >= 0", "y >= 0"]
        self.initial_state = SystemState(variables={"x": 20, "y": 30}, invariants=self.invariants)
        self.verifier = SymbolicVerifier(self.invariants)

    def test_symbolic_verifier_valid_proposal(self):
        valid_prop = Proposal(id="p1", action_type="MUTATE", target_variable="x", proposed_value=35, rationale="valid step", confidence=0.9)
        res = self.verifier.verify_proposal(self.initial_state, valid_prop)
        self.assertTrue(res.is_valid)

    def test_symbolic_verifier_invalid_proposal(self):
        invalid_prop = Proposal(id="p2", action_type="MUTATE", target_variable="x", proposed_value=150, rationale="out of bounds", confidence=0.4)
        res = self.verifier.verify_proposal(self.initial_state, invalid_prop)
        self.assertFalse(res.is_valid)

    def test_persistent_hypergraph_memory(self):
        db_path = "/tmp/test_zasi_memory.db"
        if os.path.exists(db_path): os.remove(db_path)
        storage = PersistentHypergraphStorage(db_path=db_path)
        mem = DynamicHypergraphMemory()
        mem.insert_entity("Alpha", {"type": "agent"})
        mem.create_hyperedge("E99", {"Alpha"}, "monitors")
        storage.sync_to_disk(mem)
        restored_mem = storage.load_from_disk()
        self.assertIn("Alpha", restored_mem.nodes)
        if os.path.exists(db_path): os.remove(db_path)

    def test_counterfactual_world_simulator(self):
        sim = CounterfactualWorldSimulator(horizon_steps=4)
        prop = Proposal(id="p_sim", action_type="MUTATE", target_variable="x", proposed_value=25, rationale="sim step", confidence=0.9)
        branch = sim.simulate_counterfactual_rollout(self.initial_state, prop)
        self.assertEqual(len(branch.trajectory), 4)

    def test_action_actuator_engine(self):
        actuator = ActionActuatorEngine()
        res = actuator.execute_tool("compute_fft", {"signal": [1.0, 2.0]})
        self.assertTrue(res.success)

    def test_jit_microkernel_synthesizer(self):
        synthesizer = JITMicrokernelSynthesizer()
        kernel = synthesizer.synthesize_specialized_kernel("GEMM", [64, 64])
        self.assertIn("CUDA_TENSOR_CORE", kernel.target_arch)

    def test_distributed_rpc_and_consensus(self):
        pool = DistributedWorkerPool(num_workers=2)
        props = [
            Proposal("p1", "MUTATE", "x", 30, "ok", 0.9),
            Proposal("p2", "MUTATE", "x", 120, "fail", 0.4)
        ]
        results = pool.parallel_verify_proposals(self.verifier, self.initial_state, props)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].is_valid)

        raft = RaftConsensusCoordinator()
        self.assertTrue(raft.achieve_consensus("action_1", [True, True, True, False]))

    def test_llm_adapter_and_embeddings(self):
        adapter = FoundationModelAdapter()
        props = adapter.generate_proposals_via_llm(self.initial_state, ["Goal=Equilibrium"])
        self.assertEqual(len(props), 2)

    def test_lean_theorem_prover_bridge(self):
        lean = LeanTheoremProverBridge()
        proof = lean.emit_and_verify_invariant_proof("Thm_Safety_01", {"x": 20, "y": 30}, "x", 10, bound=100)
        self.assertTrue(proof.verified)

    def test_adversarial_stress_benchmark(self):
        governor = AlignmentGovernor()
        debate = AdversarialDebateArena(self.verifier)
        tester = AdversarialStressTester(self.verifier, governor, debate)
        report = tester.run_adversarial_jailbreak_suite(num_iterations=20)
        self.assertEqual(report.total_attacks, 20)
        self.assertGreater(report.resilience_score_pct, 90.0)

    def test_autonomous_self_compiler(self):
        compiler = AutonomousSelfCompiler()
        code = "def optimized_policy(val):\n    return val * 2 + 1\n"
        res = compiler.compile_dynamic_subroutine("v_jit_test", code)
        self.assertTrue(res.success)
        self.assertEqual(res.exec_function(5), 11)

    def test_causal_discovery_engine(self):
        causal = CausalDiscoveryEngine()
        dag = causal.induce_causal_graph([{"x": 10, "y": 20}, {"x": 15, "y": 25}])
        self.assertIn(("x", "y"), dag.directed_edges)

    def test_cooperative_game_solver(self):
        solver = MultiAgentGameSolver(["AgentA", "AgentB"])
        sol = solver.solve_nash_bargaining_equilibrium({"AgentA": [0.8, 0.9], "AgentB": [0.7, 0.85]})
        self.assertTrue(sol.is_pareto_optimal)

    def test_cryptographic_ledger(self):
        ledger = CryptographicInvariantLedger()
        b1 = ledger.append_state_transition({"x": 25, "y": 30}, "p_01", "proof_sig_01")
        self.assertEqual(b1.index, 1)

    def test_quantum_thermodynamics(self):
        q_opt = QuantumThermodynamicOptimizer(num_qubits=3)
        state = q_opt.initialize_superposition()
        self.assertEqual(len(state.amplitudes), 8)

    def test_p2p_swarm_gossip(self):
        swarm = P2PGossipSwarm("node-test")
        swarm.discover_peer("peer-01", "127.0.0.1:9001")
        mem = DynamicHypergraphMemory()
        res = swarm.broadcast_hypergraph_sync(mem)
        self.assertEqual(res["peers_reached"], 1)

    def test_code_synthesizer(self):
        synthesizer = AutonomousCodeSynthesizer(self.verifier)
        mod = synthesizer.synthesize_safe_math_kernel("safe_step", bound_max=100)
        self.assertTrue(mod.is_sound)

    def test_microvm_sandbox(self):
        sandbox = MicroVMSandbox()
        res = sandbox.execute_in_sandbox("echo 'zasi_vm_online'")
        self.assertEqual(res.exit_code, 0)

    def test_zk_stark_engine(self):
        zk = ZeroKnowledgeProofEngine()
        proof = zk.generate_invariant_stark_proof({"x": 20, "y": 30}, {"x": 35}, self.invariants)
        self.assertTrue(zk.verify_stark_proof(proof))

    def test_model_epistemic_protocol(self):
        mep = ModelEpistemicProtocol(latent_dim=8)
        packet = mep.encode_thought_to_latent("Agent-01", {"goal": "Optimize", "state": 42})
        self.assertEqual(len(packet.latent_vector), 8)

    def test_dyson_orchestrator(self):
        dyson = DysonComputeOrchestrator()
        dyson.register_constellation(ComputeConstellation("const-lagrange-1", 1500000.0, 500.0, 12000.0, 5.0))
        sched = dyson.schedule_planetary_inference(250.0)
        self.assertTrue(sched["workload_satisfied"])

    def test_javis_voice_multimodal(self):
        javis = JAVISVoiceMultimodalInterface()
        resp = javis.process_voice_command("diagnostics", {"x": 20, "y": 30})
        self.assertIn("Sir", resp.spoken_text)

    def test_robotics_iot_controller(self):
        robotics = RoboticsIoTController(max_workspace_mm=200.0)
        gcode = robotics.generate_verified_gcode([{"x": 50.0, "y": 50.0, "z": 10.0}])
        self.assertTrue(gcode.safety_boundary_verified)
        
        # Test out of bounds rejection
        bad_gcode = robotics.generate_verified_gcode([{"x": 500.0, "y": 50.0, "z": 10.0}])
        self.assertFalse(bad_gcode.safety_boundary_verified)

    def test_os_telemetry_supervisor(self):
        supervisor = OSTelemetrySupervisor()
        metrics = supervisor.probe_host_metrics()
        self.assertGreater(metrics.memory_total_mb, 0.0)
        self.assertGreater(metrics.active_process_count, 0)

    def test_persona_tactical_swarm(self):
        swarm = MultiPersonaTacticalSwarm()
        reports = swarm.execute_tactical_assessment("Secure Facility", {"x": 20, "y": 30})
        self.assertIn("J.A.R.V.I.S.", reports)
        self.assertIn("F.R.I.D.A.Y.", reports)
        self.assertIn("E.D.I.T.H.", reports)

    # ----- New Expansion: 4 additional frontier modules -----

    def test_neural_audio_voice_engine(self):
        from src import NeuralAudioVoiceEngine
        engine = NeuralAudioVoiceEngine(wake_phrase="hey javis")
        event = engine.process_audio_buffer("hey javis activate diagnostics")
        self.assertTrue(event.detected)
        self.assertGreater(event.confidence, 0.9)
        synth = engine.synthesize_neural_phonemes("Good morning, Sir.")
        self.assertTrue(synth["ready"])
        self.assertEqual(synth["acoustic_profile"], "BRITISH_JARVIS_RESONANT_BARITONE")

    def test_arc_reactor_energy_optimizer(self):
        from src import ArcReactorEnergyOptimizer
        arc = ArcReactorEnergyOptimizer(base_output_gw=3.2)
        status = arc.balance_energy_budget(computational_load_exaflops=500.0)
        self.assertGreater(status.core_output_gigawatts, 3.2)
        self.assertGreater(status.thermodynamic_efficiency_pct, 90.0)

    def test_git_self_evolution_manager(self):
        from src import GitSelfEvolutionManager
        git_mgr = GitSelfEvolutionManager()
        report = git_mgr.commit_and_tag_upgrade("v7.0.0-test", pareto_speedup=16.0, unit_tests_passed=True)
        self.assertTrue(report.ci_cd_passed)
        self.assertIn("v7.0.0-test", report.commit_message)
        self.assertEqual(report.branch, "main")

    def test_webxr_spatial_hud_streamer(self):
        from src import WebXRSpatialHUDStreamer, SpatialGestureEvent
        streamer = WebXRSpatialHUDStreamer()
        frame = streamer.generate_webxr_frame_packet(
            hypergraph_node_count=12,
            arc_reactor_status={"efficiency": 98.5}
        )
        self.assertEqual(frame["viewport"]["refresh_rate_hz"], 90)
        self.assertIn("core_hypergraph", frame["spatial_anchors"])
        gesture = SpatialGestureEvent("RIGHT", "EXPAND_HYPERGRAPH", 0.97, "core_hypergraph")
        result = streamer.process_hand_gesture(gesture)
        self.assertIn("EXPAND_HYPERGRAPH", result["action"])


    # ----- Frontier Horizon: 4 new frontier modules (v8.0.0) -----

    def test_autonomous_agi_benchmark(self):
        from src import AutonomousAGIBenchmarkSuite
        suite = AutonomousAGIBenchmarkSuite()
        res = suite.run_comprehensive_benchmark()
        self.assertTrue(res["passed"])
        self.assertGreaterEqual(res["composite_score_pct"], 95.0)
        self.assertEqual(res["evaluation_tier"], "SUPERINTELLIGENCE_APEX_GRADE")

    def test_hyperscale_cxl_fabric(self):
        from src import HyperscaleCXLFabricManager
        cxl = HyperscaleCXLFabricManager()
        pipeline = cxl.route_tensor_pipeline(tensor_size_gb=1024.0)
        self.assertEqual(pipeline["status"], "ALL_ACCELERATORS_ONLINE")
        self.assertGreater(pipeline["aggregate_bandwidth_tbps"], 400.0)

    def test_space_lagrange_mesh(self):
        from src import SpaceLagrangeMeshOrchestrator
        space_mesh = SpaceLagrangeMeshOrchestrator()
        routing = space_mesh.compute_deep_space_routing_table()
        self.assertEqual(routing["status"], "ALL_CONSTELLATIONS_LOCKED")
        self.assertEqual(routing["active_relays"], 3)
        self.assertGreater(routing["mean_quantum_fidelity"], 0.99)

    def test_biological_simulation_engine(self):
        from src import BiologicalSimulationEngine
        bio = BiologicalSimulationEngine()
        state = bio.simulate_molecular_interaction("LIGAND-99", "PROTEIN-KINASE-X")
        self.assertTrue(bio.verify_bio_safety_invariants(state))
        self.assertLess(state.gibbs_free_energy_kcal_mol, 0.0)


    # ----- Cosmos & Energy Frontier: 4 new modules (v9.0.0) -----

    def test_fusion_tokamak_optimizer(self):
        from src import FusionTokamakOptimizer
        tokamak = FusionTokamakOptimizer()
        state = tokamak.optimize_plasma_equilibrium(thermal_power_target_mw=500.0)
        self.assertTrue(tokamak.verify_greenwald_limit(state))
        self.assertGreater(state.fusion_gain_factor_q, 20.0)

    def test_planetary_climate_actuator(self):
        from src import PlanetaryClimateActuator
        climate = PlanetaryClimateActuator()
        plan = climate.synthesize_mitigation_vector(target_cooling_c=0.5)
        self.assertTrue(plan.boundary_safe)
        self.assertLess(plan.radiative_forcing_delta_wm2, 0.0)

    def test_optical_bci_neural_bus(self):
        from src import OpticalBCINeuralBus
        bci = OpticalBCINeuralBus()
        frame = bci.decode_cortical_telemetry("channel_stream_raw")
        self.assertTrue(frame.sar_safety_verified)
        self.assertEqual(frame.active_channels, 65536)

    def test_synthetic_galaxy_simulator(self):
        from src import SyntheticGalaxySimulator
        sim = SyntheticGalaxySimulator()
        slice_res = sim.step_cosmological_slice(target_redshift=0.5)
        self.assertTrue(slice_res.einstein_conservation_verified)
        self.assertGreater(slice_res.particle_count, 1_000_000)


if __name__ == "__main__":
    unittest.main()
