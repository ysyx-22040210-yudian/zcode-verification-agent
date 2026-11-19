"""Exercise the distributed launcher and read the same run through MCP."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run(root, *args, codes=(0,)):
    python = root / "formal-toolchain/python" / ("python.exe" if sys.platform == "win32" else "bin/python3.11")
    proc = subprocess.run([str(python), "-E", "-s", "-X", "utf8", str(root / "portable.py"), *args],
                          capture_output=True, encoding="utf-8", timeout=300)
    assert proc.returncode in codes, (proc.returncode, proc.stdout, proc.stderr)
    return json.loads(proc.stdout)


if __name__ == "__main__":
    kit = Path(sys.argv[1]).resolve()
    good = run(kit, "run", str(kit / "fifo"), "--profile", "formal")
    assert good["status"] == "pass", good
    assert {p["status"] for p in good["properties"]} == {"proven", "reached"}
    bad = run(kit, "run", str(kit / "fifo"), "--profile", "formal", "--variant", "mutant", codes=(1,))
    assert bad["status"] == "fail", bad
    assert any(a["kind"] == "waveform" and a["bytes"] > 0 for a in bad["artifacts"])
    python = kit / "formal-toolchain/python" / ("python.exe" if sys.platform == "win32" else "bin/python3.11")
    requests = [{"jsonrpc": "2.0", "id": n, "method": "tools/call",
                 "params": {"name": method, "arguments": args}}
                for n, (method, args) in enumerate([
                    ("verification_get", {"runId": bad["id"]}),
                    ("verification_read_artifact", {"runId": bad["id"], "name": "p_simultaneous_hold.cex.vcd"}),
                    ("verification_rerun", {"runId": bad["id"]})], 1)]
    result = subprocess.run([str(python), "-E", "-s", "-X", "utf8", str(kit / "portable.py"), "mcp", str(kit / "fifo")],
                            input="".join(json.dumps(item) + "\n" for item in requests),
                            capture_output=True, encoding="utf-8", timeout=60, check=True)
    replies = [json.loads(json.loads(line)["result"]["content"][0]["text"]) for line in result.stdout.splitlines()]
    assert replies[0]["id"] == bad["id"] and "$enddefinitions" in replies[1]["text"]
    assert replies[2]["rerunOf"] == bad["id"] and replies[2]["inputDigest"] == bad["inputDigest"]
    with tempfile.TemporaryDirectory(prefix="second DUT ") as directory:
        project = Path(directory)
        (project / "SPEC.md").write_text("COUNT-HOLD", encoding="utf-8")
        (project / "sources.f").write_text('"counter harness.sv"\n', encoding="utf-8")
        rtl = """module counter(input clk, input en);
  reg [3:0] value = 0;
  reg valid = 0;
  always @(posedge clk) begin
    if (en) value <= value + 1;
    valid <= 1;
    if (valid && !$past(en)) p_hold: assert(value == $past(value));
    c_seven: cover(value == 7);
  end
endmodule
"""
        (project / "counter harness.sv").write_text(rtl, encoding="utf-8")
        config = {"version": 1, "spec": "SPEC.md", "inputs": ["SPEC.md", "sources.f", "counter harness.sv"],
                  "profiles": {"formal": {"mode": "formal", "top": "counter", "filelist": "sources.f",
                               "strategy": "bmc", "depth": 3, "properties": {"p_hold": "assert"}}},
                  "checks": [{"id": "COUNT-HOLD", "title": "hold", "profiles": ["formal"]}]}
        def check(status):
            (project / "verify.yaml").write_text(json.dumps(config), encoding="utf-8")
            receipt = run(kit, "run", str(project), codes=(0, 1))
            assert receipt["status"] == status, receipt
            return receipt
        bounded = check("bounded")
        assert bounded["properties"][0]["depth"] == 3
        config["profiles"]["formal"]["properties"]["c_seven"] = "cover"
        assert any(p["kind"] == "cover" and p["status"] == "unknown" for p in check("unknown")["properties"])
        config["profiles"]["formal"]["properties"] = {"p_missing": "assert"}
        check("missing_result")
        config["profiles"]["formal"]["properties"] = {"p_hold": "assert"}
        source = project / "counter harness.sv"
        source.write_text(rtl.replace("valid <= 1;", "valid <= 1; assume(1'b0);"), encoding="utf-8")
        assert check("unknown")["properties"][0]["status"] == "unknown"
        source.write_text("""module counter(input clk_a, clk_b, en);
reg a = 0, b = 0;
always @(posedge clk_a) a <= en;
always @(negedge clk_b) b <= en;
always @* p_hold: assert(a == b);
endmodule
""", encoding="utf-8")
        check("compile_error")
    if os.environ.get("ZCODE_FORMAL_STATE"):
        runs = Path(os.environ["ZCODE_FORMAL_STATE"]) / "runs"
        assert len(list((runs / ".formal-cache").rglob("yosys.wasm/*"))) == 1
        assert not list(runs.glob("*/*/work/YoWASP"))
    print(json.dumps({"golden": good["id"], "mutant": bad["id"], "properties": bad["properties"]}))

