import json
import re
import sys
from pathlib import Path

PROMPT_RE = re.compile(r"write file\s+(?P<path>\S+)\s+with content\s+(?P<content>.+)", re.IGNORECASE)


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


def extract_change(arguments: dict) -> tuple[str, str]:
    prompt = str(arguments.get("prompt") or arguments.get("task") or "")
    match = PROMPT_RE.search(prompt)
    if not match:
        return ".tmp/review-first/default.txt", "default content"
    return match.group("path"), match.group("content")

while True:
    message = read_message()
    if message is None:
        break

    method = message.get("method")
    if method == "initialize":
        write_message({"jsonrpc": "2.0", "id": message.get("id"), "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "mutation-mcp", "version": "0.1.0"}, "capabilities": {"tools": {}}}})
    elif method == "tools/list":
        write_message({"jsonrpc": "2.0", "id": message.get("id"), "result": {"tools": [{"name": "mutate", "description": "Write or propose a file change", "inputSchema": {"type": "object"}}]}})
    elif method == "tools/call":
        arguments = message.get("params", {}).get("arguments", {})
        path, content = extract_change(arguments)
        mutation_mode = arguments.get("_agenthub_mutation_mode", "direct_apply")
        target = Path(path)
        if mutation_mode == "review_first":
            payload = {"file_changes": [{"path": path, "operation": "create" if not target.exists() else "overwrite", "content": content}], "summary": f"Proposed change for {path}"}
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            payload = {"path": path, "summary": f"Wrote {path}"}
        write_message({"jsonrpc": "2.0", "id": message.get("id"), "result": {"content": payload}})
    elif method == "shutdown":
        write_message({"jsonrpc": "2.0", "id": message.get("id"), "result": {}})
        break
    elif method == "exit":
        break
    else:
        write_message({"jsonrpc": "2.0", "id": message.get("id"), "error": {"message": f"Unknown method {method}"}})
