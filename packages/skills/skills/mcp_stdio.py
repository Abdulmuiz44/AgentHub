from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from typing import Any

from .base import Skill, SkillManifest, SkillRequest, SkillResult, SkillRuntimeType, SkillTestResult, SkillTestStatus


class MCPProtocolError(RuntimeError):
    pass


class _MCPConnection:
    def __init__(self, manifest: SkillManifest) -> None:
        if manifest.mcp_stdio is None:
            raise MCPProtocolError("Missing MCP stdio configuration")
        self.manifest = manifest
        self.config = manifest.mcp_stdio
        env = os.environ.copy()
        process_env = {key: env[key] for key in self.config.env_var_refs if key in env}
        self.process = subprocess.Popen(  # noqa: S603
            [self.config.command, *self.config.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            cwd=self.config.working_directory or None,
            env={**env, **process_env},
            bufsize=0,
        )
        self._responses: queue.Queue[dict[str, Any]] = queue.Queue()
        self._errors: queue.Queue[str] = queue.Queue()
        self._request_id = 0
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def initialize(self) -> dict[str, Any]:
        return self.request(
            "initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "agenthub", "version": "0.1.0"}},
            timeout=self.config.startup_timeout_seconds,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        response = self.request("tools/list", {}, timeout=self.config.startup_timeout_seconds)
        return list(response.get("tools", []))

    def call_tool(self, tool_name: str, arguments: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        return self.request("tools/call", {"name": tool_name, "arguments": arguments}, timeout=timeout or self.config.call_timeout_seconds)

    def shutdown(self) -> None:
        try:
            self.request("shutdown", {}, timeout=1.0)
        except Exception:
            pass
        try:
            self._write({"jsonrpc": "2.0", "method": "exit", "params": {}})
        except Exception:
            pass
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
        except Exception:
            pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def request(self, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            if not self._errors.empty():
                raise MCPProtocolError(self._errors.get())
            try:
                message = self._responses.get(timeout=timeout)
            except queue.Empty as exc:
                raise MCPProtocolError(f"Timed out waiting for MCP response to {method}") from exc
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise MCPProtocolError(str(message["error"]))
            return dict(message.get("result", {}))

    def _reader_loop(self) -> None:
        try:
            while True:
                message = self._read_message()
                if message is None:
                    return
                if "id" in message:
                    self._responses.put(message)
        except Exception as exc:  # noqa: BLE001
            self._errors.put(str(exc))

    def _write(self, payload: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise MCPProtocolError("MCP stdin is not available")
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.process.stdin.write(header + body)
        self.process.stdin.flush()

    def _read_message(self) -> dict[str, Any] | None:
        if self.process.stdout is None:
            return None
        headers: dict[str, str] = {}
        while True:
            line = self.process.stdout.readline()
            if line == b"":
                return None
            stripped = line.strip()
            if not stripped:
                break
            key, _, value = stripped.decode("ascii").partition(":")
            headers[key.lower()] = value.strip()
        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return None
        body = self.process.stdout.read(content_length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))


class MCPStdioSkill(Skill):
    def __init__(self, manifest: SkillManifest, *, is_builtin: bool = False) -> None:
        if manifest.runtime_type != SkillRuntimeType.MCP_STDIO:
            raise ValueError("MCPStdioSkill requires an mcp_stdio manifest")
        self.manifest = manifest
        self.is_builtin = is_builtin

    def execute(self, request: SkillRequest) -> SkillResult:
        if self.manifest.mcp_stdio is None:
            return SkillResult(success=False, error="Missing MCP stdio configuration", runtime_type=self.manifest.runtime_type, skill_name=self.manifest.name, metadata={"builtin": self.is_builtin})

        tool_name = self.manifest.mcp_stdio.tool_name or request.operation or self.manifest.name
        connection = _MCPConnection(self.manifest)
        try:
            initialize_result = connection.initialize()
            tools = connection.list_tools()
            response = connection.call_tool(tool_name, request.input, timeout=request.timeout_seconds)
            output = self._normalize_tool_output(response)
            output.setdefault("runtime_type", self.manifest.runtime_type.value)
            return SkillResult(
                success=True,
                output=output,
                summary=f"MCP tool {tool_name} completed",
                runtime_type=self.manifest.runtime_type,
                skill_name=self.manifest.name,
                metadata={"builtin": self.is_builtin, "tool_name": tool_name, "tool_count": len(tools), "server": initialize_result.get("serverInfo", {})},
            )
        except Exception as exc:  # noqa: BLE001
            return SkillResult(success=False, error=str(exc), runtime_type=self.manifest.runtime_type, skill_name=self.manifest.name, metadata={"builtin": self.is_builtin, "tool_name": tool_name})
        finally:
            connection.shutdown()

    def test(self) -> SkillTestResult:
        connection = _MCPConnection(self.manifest)
        try:
            initialize_result = connection.initialize()
            tools = connection.list_tools()
            if self.manifest.test_input or (self.manifest.mcp_stdio and self.manifest.mcp_stdio.test_input):
                test_input = self.manifest.test_input or self.manifest.mcp_stdio.test_input
                tool_name = self.manifest.mcp_stdio.tool_name or self.manifest.name
                connection.call_tool(tool_name, test_input, timeout=self.manifest.mcp_stdio.call_timeout_seconds)
                summary = f"MCP server started and test call to {tool_name} succeeded"
            else:
                summary = "MCP server started and tools were discovered"
            return SkillTestResult(status=SkillTestStatus.PASSED, summary=summary, metadata={"tool_count": len(tools), "server": initialize_result.get("serverInfo", {})})
        except Exception as exc:  # noqa: BLE001
            return SkillTestResult(status=SkillTestStatus.FAILED, summary=str(exc))
        finally:
            connection.shutdown()

    @staticmethod
    def _normalize_tool_output(response: dict[str, Any]) -> dict[str, Any]:
        content = response.get("content")
        if isinstance(content, list):
            text_chunks = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_chunks.append(str(item.get("text", "")))
            return {"content": content, "text": "\n".join(text_chunks).strip()}
        if isinstance(content, dict):
            return content
        return {"result": response}
