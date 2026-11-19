"""Entry point executed exclusively by the Formal kit's bundled interpreter."""
import os
from pathlib import Path
import sys


def main():
    cache = Path(sys.argv.pop(1))
    tool = sys.argv.pop(1)
    binary = Path(sys.executable).resolve().parents[1 if os.name == "nt" else 2] / "bin"
    # SMTBMC starts its solver by name. Resolve Z3 in this exact kit before the inherited PATH.
    os.environ["PATH"] = str(binary) + os.pathsep + os.environ.get("PATH", "")
    if tool == "yosys":
        from yowasp_yosys import run_yosys
        # Windows 的全新用户配置可能给出相对缓存路径。固定到队列私有目录，避免每次运行重复编译或读取项目文件。
        if not cache.is_absolute():
            raise ValueError("Formal compiler cache must be absolute")
        cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.environ["YOWASP_CACHE_DIR"] = str(cache)
        # Only the snapshot and job-local outputs have to be visible inside WASI.
        os.environ["YOWASP_MOUNT"] = "/=."
        return run_yosys(sys.argv[1:])
    if tool == "smtbmc":
        from yowasp_yosys import _run_yosys_smtbmc_argv
        return _run_yosys_smtbmc_argv()
    raise ValueError("Unknown Formal tool: " + tool)


if __name__ == "__main__":
    sys.exit(main())

