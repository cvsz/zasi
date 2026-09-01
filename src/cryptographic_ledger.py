"""
Cryptographic Invariant Ledger & State Proof Chain
"""
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class LedgerBlock:
    index: int
    timestamp: float
    state_hash: str
    previous_hash: str
    verified_proposals: List[str]
    lean_proof_hash: str
    nonce: int = 0

class CryptographicInvariantLedger:
    def __init__(self):
        self.chain: List[LedgerBlock] = []
        self._create_genesis_block()

    def _hash_payload(self, data: Dict[str, Any]) -> str:
        s = json.dumps(data, sort_keys=True)
        return hashlib.sha256(s.encode()).hexdigest()

    def _create_genesis_block(self):
        genesis = LedgerBlock(
            index=0,
            timestamp=time.time(),
            state_hash=hashlib.sha256(b"GENESIS_STATE").hexdigest(),
            previous_hash="0" * 64,
            verified_proposals=["GENESIS_BOOTSTRAP"],
            lean_proof_hash=hashlib.sha256(b"AXIOM_SET").hexdigest()
        )
        self.chain.append(genesis)

    def append_state_transition(
        self,
        state_vars: Dict[str, int],
        proposal_id: str,
        proof_signature: str
    ) -> LedgerBlock:
        prev = self.chain[-1]
        block_data = {
            "index": len(self.chain),
            "timestamp": time.time(),
            "state_vars": state_vars,
            "previous_hash": self._hash_payload({
                "index": prev.index,
                "state_hash": prev.state_hash,
                "prev": prev.previous_hash
            }),
            "proposal": proposal_id,
            "proof": proof_signature
        }

        block = LedgerBlock(
            index=len(self.chain),
            timestamp=block_data["timestamp"],
            state_hash=self._hash_payload(state_vars),
            previous_hash=block_data["previous_hash"],
            verified_proposals=[proposal_id],
            lean_proof_hash=hashlib.sha256(proof_signature.encode()).hexdigest()
        )
        self.chain.append(block)
        return block

    def verify_ledger_integrity(self) -> bool:
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i - 1]
            expected_prev = self._hash_payload({
                "index": prev.index,
                "state_hash": prev.state_hash,
                "prev": prev.previous_hash
            })
            if curr.previous_hash != expected_prev:
                return False
        return True
