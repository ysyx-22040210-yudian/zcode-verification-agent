"""Check the actual loopback HTTP request body. Log counts and outcomes only."""
import importlib.util
import json
from pathlib import Path
import re
import sys
from http.server import HTTPServer

spec = importlib.util.spec_from_file_location("transport", str(Path(__file__).resolve().parents[1] / "knowledge-model.py"))
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


def route(body):
    messages = body["messages"]
    names = {t["function"]["name"].split("__")[-1]: t["function"]["name"] for t in body.get("tools", [])}
    prompts = [(i, match.group(1)) for i, msg in enumerate(messages) if msg["role"] == "user"
               for match in re.finditer(r"VISION_CASE_(OFF|ON|REPLAY)", " ".join(transport.strings(msg["content"])))]
    if not prompts or not names:
        return "Vision input test", []
    index, phase = prompts[-1]
    visual = phase == "ON"
    wire = json.dumps(messages)
    def image_count(records):
        return sum(block.get("type") in ("image_url", "image", "input_image", "image-data")
                   for msg in records if isinstance(msg.get("content"), list)
                   for block in msg["content"] if isinstance(block, dict))

    images = image_count(messages)
    encoded = bool(re.search(r"(?:data:image/[^;\s]+;base64,|iVBORw0KGgo)[A-Za-z0-9+/=]{24}", wire, re.I))
    reply = [i for i in range(index, len(messages)) if messages[i]["role"] == "tool"]
    print("WIRE", phase, "afterOriginal" if reply else "attachment", "images", images, "encoded", encoded, flush=True)
    if (not visual and (images or encoded)) or (visual and (not images or not encoded)):
        return "VISION_WIRE_" + phase + "_FAIL image payload", []
    if not reply:
        return "", [{"id": "original_" + phase, "type": "function", "function": {
            "name": names["knowledge_read_original"], "arguments": json.dumps({"sourceId":"vc-apps-npi", "page":1})}}]
    result = " ".join(transport.strings(messages[reply[-1]]["content"]))
    if not all(key in result for key in ("original_pdf", "text", "page", "Programming Interface")):
        return "VISION_WIRE_" + phase + "_FAIL original text", []
    if ('"originalEvidence"' in result) != visual or ('"imageRegions"' in result) != visual:
        return "VISION_WIRE_" + phase + "_FAIL original visual receipt", []
    original_images = image_count(messages[reply[-1]:])
    print("ORIGINAL", phase, "page", 1, "images", original_images, flush=True)
    if bool(original_images) != visual:
        return "VISION_WIRE_" + phase + "_FAIL original image", []
    if phase == "REPLAY" and not any("VISION_CASE_ON" in s for s in transport.strings(messages[:index])):
        return "VISION_WIRE_REPLAY_FAIL missing earlier turn", []
    return "VISION_WIRE_" + phase + "_OK", []


if __name__ == "__main__":
    transport.route = route
    HTTPServer(("127.0.0.1", int(sys.argv[1])), transport.Provider).serve_forever()
