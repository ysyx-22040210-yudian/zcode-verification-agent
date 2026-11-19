# ZCode Formal 离线工具包

本包供 Windows x64 和 Linux x86-64 设备运行本地 RTL 属性验证。每个平台的 ZIP 包都带有 CPython 3.11、Yosys 0.50、yosys-smtbmc 和 Z3 4.13.4。解压后可离线使用，普通用户即可运行。工具版本、上游来源和下载摘要见 `formal-toolchain/toolchain.lock.json`，开源许可随包提供。

## 运行示例

Windows 在解压目录打开 PowerShell。Linux 解压时使用保留执行权限的 `unzip`。以下命令会等待求解完成，打印运行 ID、每条属性的结果和证据文件名。缺陷用例的退出码为 1。

```powershell
.\zcode-formal.cmd run .\fifo
.\zcode-formal.cmd run .\fifo --variant mutant
```

```sh
./zcode-formal run ./fifo
./zcode-formal run ./fifo --variant mutant
```

在本版 ZCode 桌面打开含 `verify.yaml` 的项目，进入「验证」，选择 `formal` 并点击「运行」。也可在对话中要求「用 formal 跑当前项目，列出每条断言和反例」。本版 Linux x64 和 Windows x64 桌面打包时会加入相应工具包。单独使用工具包时，`zcode-formal desktop <本版桌面可执行文件> <项目目录>` 可将该桌面接入同一后台。VM 上的原生桌面启动器已接入宿主验证服务。

要接入支持 stdio MCP 的其他客户端，命令使用包内 `formal-toolchain/python/python.exe`（Windows）或 `formal-toolchain/python/bin/python3.11`（Linux）的绝对路径。参数依次为 `-E`、`-s`、`-X`、`utf8`、`<工具包绝对路径>/portable.py`、`mcp`。工作目录默认为当前项目，也可在最后传入项目绝对路径。工具依次为 `verification_inspect`、`verification_submit`、`verification_get` 和 `verification_read_artifact`，支持 `verification_cancel` 和 `verification_rerun`。桌面和 MCP 使用同一份快照和证据。

默认数据目录在 Linux 的 `~/.local/state/zcode/formal/<安装路径摘要>` 或 Windows 的 `%LOCALAPPDATA%\zcode\formal\<安装路径摘要>`。运行前可用 `ZCODE_FORMAL_STATE` 指定专用目录。每次作业的 `run.json`、`inputs/` 和 `evidence/` 位于 `runs/<项目摘要>/<运行ID>/`。已安装的原生验证服务可将 `VERIFICATION_FORMAL_HOME` 指向解压包内的 `formal-toolchain`。

## 为自己的 RTL 编写配置

参见 `fifo/verify.yaml` 和 `fifo/formal/fifo_open.sv`。将 RTL、验证顶层、filelist 和规格列入 `inputs`。开源 profile 的 `filelist` 每行一个相对于项目根目录的源文件，支持空行、整行注释和双引号包围的空格路径。按编译顺序列出文件，头文件也要放进快照。用可综合的 Verilog/SystemVerilog、一个采样时钟和验证顶层内带名称的立即 `assert` / `cover`，用 `assume` 显式描述复位和环境约束。名称与配置逐一对应。需要完整并发 SVA 或厂商 Tcl 的工程可以选择商业 profile。

```yaml
profiles:
  formal:
    mode: formal
    backend: yosys
    top: fifo_open
    filelist: formal-open.f
    strategy: prove
    depth: 16
    properties:
      p_count_range: assert
      c_simultaneous: cover
```

`prove` 先从初始约束检查指定步数，再做时间归纳。两步都通过才显示 `proven`。`strategy: bmc` 只做有界检查，成功显示 `bounded_pass` 和检查步数。反例和 cover 的 `depth` 是从 0 起算的见证步号。归纳未成功会保留已检查的界限，矛盾假设或界内未触达的 cover 标为 `unknown`。缺少命名属性、求解报告或必要波形会给出错误状态。展开目录中的 VCD 可在工作台查看。

## 接入商业 Formal 工具

已有 IFV 项目可用 `backend: ifv`。此前只声明 Tcl 脚本的 profile 仍解析为 IFV。FIFO 的 `formal-ifv` 是可选 profile。其他产品可由站点维护一个适配器，用自己的许可证、命令和报告解析器运行。许可设置留在运行验证服务的账号环境中。

1. 复制 `adapters/registry.example.json` 到验证服务账号的 `~/.zcode/formal-adapters.json`，或设置 `VERIFICATION_FORMAL_ADAPTERS` 指向站点登记表。将 `argv[0]` 换成宿主上的绝对可执行文件路径，后面可跟固定参数。每个登记项的键就是 backend ID。
2. 在项目的 Formal profile 写入该 ID，例如 `backend: site-fpv`，并声明 `top`、`filelist` 和 `properties`。若需要 Tcl，`script` 也须列入 `inputs`。可选的商业 profile 可设置 `optional: true`。
3. 服务以快照副本为工作目录，直接执行 `argv + [request.json 的绝对路径, result.json 的绝对路径]`。请求包含 `protocolVersion: 1`、`runId`、`backend`、`profile`、`workDir`、`inputsDir`、`inputDigest`、`inputHashes`、`variant`、`seed` 和 `artifactsDir`。在 `artifactsDir` 生成原始报告、波形。完成求解后写 result 并退出 0，发现设计反例也按正常完成退出。
4. 结果必须回传相同的版本和运行 ID、实际工具名及版本，并为每条声明的属性给出一条结果。证据路径相对于 `artifactsDir`，报告随作业发布。可报告的 assert 状态有 `proven`、`bounded_pass`、`counterexample`、`vacuous`、`unknown`，cover 状态有 `reached`、`unreachable`、`unknown`。有界通过必须附正整数 `depth`。支持可选的 `trace` 和原始 `toolStatus`。以下结果对应只声明一条断言的项目。

```json
{
  "protocolVersion": 1,
  "runId": "<请求中的 runId>",
  "tool": {"name": "<实际产品>", "version": "<实际版本>"},
  "properties": [{"name": "p_count_range", "kind": "assert", "status": "counterexample", "depth": 4, "trace": "cex.vcd"}],
  "artifacts": ["formal.log", "cex.vcd"]
}
```

签出失败等情况可在同一结果信封中填写 `error: {"status":"license_error","message":"..."}` 和现有证据列表。服务还接受 `compile_error`、`tool_error`、`missing_result`、`timeout`。收到超时或取消时服务终止作业进程树，适配器启动的工具应留在该进程树内。可运行的完整实现见 `runner/formal_ifv_adapter.py` 及 `runner/engines.py` 里的 IFV 调用和报告解析。

## 从源码打包

在仓库根目录运行 `python deploy/formal/build_bundle.py linux-x64 --output dist/zcode-formal-linux-x64.zip`。Windows 目标名为 `win-x64`。指定 `--cache <目录>` 可复用原始制品，缓存齐全后加 `--offline` 可断网重建。每个原始制品均按锁文件校验 SHA-256。

求解语义可查阅 [YosysHQ 的 Formal 断言说明](https://yosyshq.readthedocs.io/projects/sby/en/latest/verilog.html)。工具分发使用 [YoWASP](https://yowasp.org/)、[Z3](https://github.com/Z3Prover/z3) 和 [Python Build Standalone](https://github.com/astral-sh/python-build-standalone) 的发行物。

