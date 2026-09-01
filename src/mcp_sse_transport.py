"""
Server-Sent Events (SSE) & HTTP Streaming Transport for MCP Protocol Server
Provides persistent HTTP SSE event streams for web clients, microservices, and distributed agents.
"""
from typing import Dict, Any, Generator
from .mcp_protocol_server import MCPProtocolServer

class MCPSSETransport:
    def __init__(self, mcp_server: MCPProtocolServer):
        self.server = mcp_server

    def format_sse_message(self, event_type: str, data: Dict[str, Any]) -> str:
        import json
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    def process_http_post_message(self, post_payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.server.handle_json_rpc_request(post_payload)
