"""Model Context Protocol (MCP) Gateway for the Autonomy Boundary Framework.

Implements an MCP-compliant Policy Enforcement Point (PEP) that wraps agent tools,
enforcing all eight ABF controls on incoming `tools/call` and `tools/list` JSON-RPC
requests before any tool effect reaches enterprise systems.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from abf.boundary import AutonomyBoundary
from abf.controls.legibility import approve
from abf.intent import Intent

DEFAULT_WINDOW = "2099-01-01T00:00:00+00:00"


@dataclass
class MCPTool:
    """Definition of an MCP tool governed by the Autonomy Boundary."""

    name: str
    description: str
    handler: Callable[[dict[str, Any]], Any]
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    irreversible: bool = False
    high_risk: bool = False
    required_deps: list[str] = field(default_factory=list)

    def to_mcp_dict(self) -> dict[str, Any]:
        """Serializes tool into MCP standard tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }


class ABFMCPGateway:
    """Policy Enforcement Point (PEP) Gateway for Model Context Protocol (MCP) clients.

    Intercepts JSON-RPC 2.0 `tools/list` and `tools/call` requests. For every call,
    it synthesizes a canonical `Intent`, asserts ledger integrity, enforces all
    eight controls in lifecycle order, and logs the proof triple before returning.
    """

    def __init__(
        self,
        boundary: AutonomyBoundary,
        signing_key: bytes,
        *,
        approver_key: bytes | None = None,
        default_identity: str = "mcp:agent",
        default_data_boundary: str = "*",
    ) -> None:
        self.boundary = boundary
        self.signing_key = signing_key
        self.approver_key = approver_key
        self.default_identity = default_identity
        self.default_data_boundary = default_data_boundary
        self.tools: dict[str, MCPTool] = {}

    def register_tool(
        self,
        name: str,
        handler: Callable[[dict[str, Any]], Any],
        description: str = "",
        parameters: dict[str, Any] | None = None,
        irreversible: bool = False,
        high_risk: bool = False,
        required_deps: list[str] | None = None,
    ) -> MCPTool:
        """Registers a tool with boundary governance parameters."""
        tool = MCPTool(
            name=name,
            description=description or f"Tool {name}",
            handler=handler,
            parameters=parameters or {"type": "object", "properties": {}},
            irreversible=irreversible,
            high_risk=high_risk,
            required_deps=required_deps or [],
        )
        self.tools[name] = tool
        return tool

    def tool(
        self,
        name: str | None = None,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        irreversible: bool = False,
        high_risk: bool = False,
        required_deps: list[str] | None = None,
    ) -> Callable[[Callable[[dict[str, Any]], Any]], MCPTool]:
        """Decorator to register a tool with the gateway."""

        def decorator(fn: Callable[[dict[str, Any]], Any]) -> MCPTool:
            tool_name = name or fn.__name__
            doc = description or (fn.__doc__ or "").strip()
            return self.register_tool(
                name=tool_name,
                handler=fn,
                description=doc,
                parameters=parameters,
                irreversible=irreversible,
                high_risk=high_risk,
                required_deps=required_deps,
            )

        return decorator

    def create_intent(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        context: dict[str, Any] | None = None,
        intent_id: str | None = None,
    ) -> Intent:
        """Builds and signs a canonical ABF Intent for an MCP tool call."""
        ctx = context or {}
        resource = (
            arguments.get("resource")
            or arguments.get("account_id")
            or arguments.get("path")
            or arguments.get("target")
            or "default"
        )
        action_verb = f"mcp.{tool_name}"
        approval_ctx = ctx.get("approval")
        resolved_intent_id = (
            intent_id
            or (approval_ctx or {}).get("intent_id")
            or arguments.get("intent_id")
            or f"mcp-{tool_name}"
        )

        return Intent(
            action=action_verb,
            resource=str(resource),
            params=dict(arguments),
            intent_id=resolved_intent_id,
            resolved_target=str(resource),
            effective_identity=ctx.get("instance_id", self.default_identity),
            capabilities=(tool_name,),
            data_boundary=ctx.get("data_boundary", self.default_data_boundary),
            expiry=ctx.get("expiry", DEFAULT_WINDOW),
            state_deps=ctx.get("bound_deps", {}),
            validity_window=ctx.get("validity_window", DEFAULT_WINDOW),
        ).sign(self.signing_key)

    def list_tools(self) -> list[dict[str, Any]]:
        """Returns the list of registered tools formatted for MCP `tools/list`."""
        return [tool.to_mcp_dict() for tool in self.tools.values()]

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Executes a tool under boundary enforcement."""
        tool = self.tools.get(tool_name)
        intent = self.create_intent(tool_name, arguments, context)

        def _action_fn(it: Intent) -> Any:
            if not tool:
                raise PermissionError(f"unregistered MCP tool: {tool_name}")
            return tool.handler(it.params)

        return self.boundary.execute(intent, _action_fn, context)

    def handle_jsonrpc(
        self,
        message: str | dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Processes an incoming JSON-RPC 2.0 message according to MCP specification."""
        if isinstance(message, str):
            try:
                msg = json.loads(message)
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                }
        else:
            msg = message

        req_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.list_tools()},
            }

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                output = self.call_tool(tool_name, arguments, context)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": str(output)}]},
                }
            except PermissionError as perm_err:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": f"Autonomy Boundary Denied: {perm_err}"},
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": f"Internal execution error: {exc}"},
                }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
        }

    handle_mcp_request = handle_jsonrpc

    def run_stdio(self) -> None:
        """Runs the gateway as a standard MCP stdio server."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            response = self.handle_jsonrpc(line)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
