"""
Standard I/O (stdio) Transport Adapter for MCP Protocol Server
Enables direct CLI & IDE integration (e.g. Claude Desktop, VS Code, Antigravity)
via JSON-RPC 2.0 standard input / standard output streams.
"""
import sys
import json
from typing import TextIO
from .mcp_protocol_server import MCPProtocolServer

class MCPStdioTransport:
    def __init__(self, mcp_server: MCPProtocolServer):
        self.server = mcp_server

    def run_stdio_loop(self, in_stream: TextIO = sys.stdin, out_stream: TextIO = sys.stdout):
        """
        Runs the blocking stdio event loop reading JSON-RPC lines from stdin and emitting to stdout.
        """
        for line in in_stream:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                response = self.server.handle_json_rpc_request(payload)
                out_stream.write(json.dumps(response) + "\n")
                out_stream.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
                }
                out_stream.write(json.dumps(err_resp) + "\n")
                out_stream.flush()
