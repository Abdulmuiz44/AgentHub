import json
import sys


def read_message() -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
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
    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    sys.stdout.buffer.flush()


while True:
    message = read_message()
    if message is None:
        break

    method = message.get("method")
    if method == "initialize":
        write_message({
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "stub-mcp", "version": "0.1.0"}, "capabilities": {"tools": {}}},
        })
    elif method == "tools/list":
        write_message({
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {"tools": [{"name": "echo", "description": "Echo input", "inputSchema": {"type": "object"}}]},
        })
    elif method == "tools/call":
        arguments = message.get("params", {}).get("arguments", {})
        write_message({
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {"content": [{"type": "text", "text": f"echo:{arguments.get('prompt') or arguments.get('task') or 'ok'}"}]},
        })
    elif method == "shutdown":
        write_message({"jsonrpc": "2.0", "id": message.get("id"), "result": {}})
        break
    elif method == "exit":
        break
    else:
        write_message({"jsonrpc": "2.0", "id": message.get("id"), "error": {"message": f"Unknown method {method}"}})
