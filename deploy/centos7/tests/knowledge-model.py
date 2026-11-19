"""Loopback-only model fixture for the desktop filing acceptance (synthetic document)."""
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


def strings(node):
    if isinstance(node, list):
        for child in node:
            yield from strings(child)
    elif isinstance(node, dict):
        for key, child in node.items():
            if key != "image_url":
                yield from strings(child)
    elif isinstance(node, str):
        yield node


def route(body):
    messages = body["messages"]
    names = {t["function"]["name"].split("__")[-1]: t["function"]["name"] for t in body.get("tools", [])}
    if not names:
        return "File the timing reference", []
    history = " ".join(strings(messages))
    calls = [c["function"]["name"].split("__")[-1] for m in messages for c in m.get("tool_calls", [])]
    latest = " ".join(strings([m.get("content") for m in messages if m.get("role") == "tool"][-1:]))
    ref = re.search(r"pdf-[a-f0-9]{48}", history)
    sha = re.search(r"(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])", history)
    if not ref or not sha:
        path = re.search(r'"path"\s*:\s*"([^"]+\.pdf)"', history)
        pending = re.search(r'"jobId"\s*:\s*"([0-9a-f]{32})"', latest)
        if path and (not calls or pending):
            action = "knowledge_import_status" if pending else "knowledge_import"
            args = {"jobId": pending.group(1)} if pending else {"path": path.group(1)}
            print("MODEL_CALL", action, flush=True)
            return "", [{"id": "call_start_" + str(len(calls)), "type": "function",
                         "function": {"name": names[action], "arguments": json.dumps(args)}}]
        return "Missing document identity", []
    identity = {"sourceId": ref.group(), "sha256": sha.group()}
    stage = sum(action not in ("knowledge_import", "knowledge_import_status") for action in calls)
    steps = ["knowledge_archive_next", "knowledge_archive_save", "knowledge_search", "knowledge_read",
             "knowledge_search", "knowledge_read_original"]
    if stage == 0:
        args = identity
    elif stage == 1 and "capture_edge" in latest:
        args = dict(identity, firstPage=1, reviewPages=[], topics=[{
            "page": 2, "title": "Clock sampling", "summary": "The rising edge samples the interface.",
            "keywords": ["采样时刻", "capture_edge"], "quote": "capture_edge samples on the rising edge."}])
    elif stage == 2 and re.search(r'"status"\s*:\s*"filed"', latest):
        args = dict(identity, query="采样时刻")
    elif stage == 3 and "model_guide" in latest:
        args = dict(identity, page=2)
    elif stage == 4 and "capture_edge" in latest:
        args = dict(identity, query="absent_layout_term_77201")
    elif stage == 5 and re.search(r'"total"\s*:\s*0', latest):
        args = dict(identity, page=2)
    elif stage >= 6 and "original_pdf" in latest:
        image_count = sum(m.get("type") == "image_url" for msg in messages
                          if isinstance(msg.get("content"), list) for m in msg["content"] if isinstance(m, dict))
        print("ORIGINAL_PAGE_IMAGES", image_count, flush=True)
        if image_count:
            return "ARCHIVE_CONVERSATION_VERIFIED. Timing Reference Fixture, PDF page 2.", []
        return "Missing original page images", []
    else:
        print("UNEXPECTED_TOOL_RESULT", stage, latest[:380], flush=True)
        return "Unexpected filing result", []
    action = steps[stage]
    print("MODEL_CALL", action, flush=True)
    return "", [{"id": "call_arch_" + str(stage), "type": "function",
                 "function": {"name": names[action], "arguments": json.dumps(args, ensure_ascii=False)}}]


class Provider(BaseHTTPRequestHandler):
    def send_json(self, value):
        buf = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(buf)))
        self.end_headers()
        self.wfile.write(buf)

    def do_GET(self):
        self.send_json({"object": "list", "data": [{"id": "verification-tool-test", "object": "model"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        content, calls = route(body)
        meta = {"id": "chatcmpl-archive", "created": int(time.time()), "model": body["model"]}
        reason = "tool_calls" if calls else "stop"
        usage = {"prompt_tokens": 16, "completion_tokens": 12, "total_tokens": 28}
        if not body.get("stream"):
            self.send_json(dict(meta, object="chat.completion", usage=usage, choices=[{"index": 0,
                "message": {"role": "assistant", "content": content, "tool_calls": calls}, "finish_reason": reason}]))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        delta = {"role": "assistant"}
        if calls:
            delta["tool_calls"] = [dict(c, index=i) for i, c in enumerate(calls)]
        else:
            delta["content"] = content
        for choice in [{"index": 0, "delta": delta, "finish_reason": None},
                       {"index": 0, "delta": {}, "finish_reason": reason}]:
            self.wfile.write(("data: " + json.dumps(dict(meta, object="chat.completion.chunk", choices=[choice])) + "\n\n").encode())
        self.wfile.write(("data: " + json.dumps(dict(meta, object="chat.completion.chunk", choices=[], usage=usage))
                          + "\n\ndata: [DONE]\n\n").encode())
        self.wfile.flush()


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), Provider).serve_forever()

