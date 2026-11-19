# ZCode 验证 Agent 部署说明

本分支基于 ZCode v3.18.2，基线提交为 `fec975905a2abd4c07e35c40d51fa097a2258ec9`。扩展包括免登录的原生「验证」页、VM 内的作业服务和供对话调用的验证 MCP。桌面与对话使用同一份作业历史和证据。RTL、SV、UVM 和 SVA 由 EDA 工具直接处理。

- `fifo/` 提供同步 FIFO 的 RTL、SV smoke、UVM scoreboard、Formal 属性和 `verify.yaml`。
- `runner/` 提供作业服务、VCS/URG、IFV 执行和 MCP 入口。
- `compat/` 与 `runtime/desktop-entry/` 用于构建和打开 CentOS 7 VM 上的原生 Linux 桌面。

[验证工作台规格](../../specs/verification-workbench.md) · [上游许可](../../LICENSE) · [第三方声明](../../THIRD-PARTY-NOTICES.md)

## 在已部署的 VM 启动

在 VM 的图形桌面打开终端，以维护账号执行下列命令。

```bash
su -
/home/verification-agent/compat/start-zcode.sh /home/verification-agent/fifo
```

启动后直接进入「验证」页。选好 SV、UVM 或 Formal 配置后点击「运行」。可以按运行 ID 查看日志、覆盖率或反例，并从原始源码快照重跑。需要通过对话提交作业时，可在 ZCode 设置中配置模型。「验证」页执行 EDA 作业无需 ZCode 账号或模型 API Key。

## 准备开发 VM

已验证的目标为 CentOS 7 x86_64、Linux 3.10、glibc 2.17，图形会话用户为 `host`。项目内的 Bookworm 用户空间用于 Node 24.14.0、pnpm 10.33.2 和 Electron 44.7.0。VCS O-2018.09-SP2、UVM 1.2、URG 和 Cadence IFV 15.2 在 CentOS 宿主执行。先在 VM 安装 Python 3 与 pip，并准备 EDA 工具及可用许可。

把此仓库检出到 `/home/verification-agent/zcode`。首次准备项目目录时，从仓库根目录以 VM 维护账号运行。

```bash
base=/home/verification-agent
cd "$base/zcode"
install -d "$base"/{artifacts,cache,evidence,runtime,compat}
cp -a deploy/centos7/{compat,fifo,runner,runtime} "$base/"
chown -R host:host "$base"/{artifacts,cache,fifo,runtime,zcode}

"$base/compat/prepare-desktop.sh"
"$base/compat/install-electron.sh"
python3 -m pip install --target "$base/cache/import-pip" 'pip==21.3.1'
PYTHONPATH="$base/cache/import-pip" python3 -m pip install --target "$base/runtime/python" -r "$base/runner/requirements.txt"
install -d -o host -g host "$base/knowledge"
```

在 Bookworm 里安装源码依赖、生成 CLI 资源并构建桌面。

```bash
"$base/compat/bookworm.sh" /bin/bash -c '
  set -e
  cd /home/verification-agent/zcode
  export ELECTRON_OVERRIDE_DIST_PATH=/opt/verification-electron
  export ELECTRON_SKIP_BINARY_DOWNLOAD=1
  export npm_config_store_dir=/home/verification-agent/cache/pnpm-store
  pnpm install --frozen-lockfile
  pnpm --filter @zcode/desktop prepare:agent-bundle
'
"$base/compat/rebuild.sh"
```

VCS 与 IFV 的安装目录可通过 `VERIFICATION_VCS_HOME`、`VERIFICATION_IFV_HOME` 指定。验证服务使用 VM 的 EDA 许可证环境。可以在 VM 内设置 `VERIFICATION_VCS_LICENSE` 为本地 VCS 许可地址。启动时需要加载在图形会话可访问的 `DISPLAY` 和 `XAUTHORITY`。

## 选择视觉模型

在 VM 桌面的 **设置 → 模型设置** 中选择供应商，点击对应模型旁的铅笔，在 **高级配置 → 输入类型** 勾选或取消 **图片（视觉模型）**，然后保存。该选择按供应商和模型保存。关闭后，Agent 从后续模型请求中省略聊天附件、工具结果及旧消息里的图片。知识库翻阅原始 PDF 时仍提供正文和页码，只有图片能说明的问题保留为待复核。用户仍可在本地知识库窗口查看原页。

## RTL 实例与信号查询

在 VM 桌面打开项目，进入 **工具 → RTL 实例与信号连接 → 打开工具**。点击「选择 KDB 文件」，选取该次 VCS 构建生成的 `simv.kdb`，也可以输入它的相对路径、绝对路径、`simv.daidir` 或 `kdb.elab++` 目录。示例文件是 `/home/verification-agent/examples/npi/build/simv.daidir/simv.kdb`。本机 VCS 将展开后的设计保存在同级 `kdb.elab++` 中，复制工程时请保留完整 `simv.daidir`。每次查询都使用这次构建的宏、参数、顶层和 generate 层次。

「Module 实例」按定义名和层次路径查找。支持 `*` 和 `?`，方括号表示实际的 generate 或数组下标。「信号连接」接受普通信号、具体 interface 成员、modport 视图及绑定后的形参路径。可追踪逐层转接、interface 数组元素和 `.push(value)` 形式的 modport 成员改名。Driver 和 Load 分栏显示实际引用的作用域、NPI 对象类型和源码位置。Interface 端口绑定另列声明方向。查询的是展开后的静态设计，class/UVM 在仿真时分配的 virtual interface 句柄需要运行时信息。

以图形会话用户在 VM 终端运行同一工具：

```bash
cd /home/verification-agent/examples/npi
python3 /home/verification-agent/runner/design-query.py instances --kdb build/simv.daidir/simv.kdb --definition sender
python3 /home/verification-agent/runner/design-query.py signal --kdb build/simv.daidir/simv.kdb --signal 'npi_demo.lane[0].u_tx.port.valid'
```

在打开示例工程的 Agent 对话中可以说「用 build/simv.daidir/simv.kdb，通过 NPI 找出 npi_demo.lane[0].bus.valid 的所有 driver 和 loader，列出源码行和查询 ID」。Agent 通过 `design_query` 提交，用 `design_query_status` 读取结果。桌面和命令行都可以在同一工作区按 ID 打开。每次查询有独立的 JSON、Verdi 日志和 NPI 原始记录。默认每组最多显示 50 条，MCP 或 CLI 的 `limit` 可提高到 200。结果同时记录总数、截断和部分解析状态。

从源码部署上述示例时执行 `install -d /home/verification-agent/examples/npi`，将 `deploy/centos7/tests/npi/design.sv` 与 `design.f` 复制到该目录。在已加载 VCS、Verdi 环境的终端进入示例目录，执行 `mkdir -p build` 和 `vcs -full64 -sverilog -kdb -debug_access+all -f design.f -top npi_demo -o build/simv` 生成示例 KDB。后续查询复用该构建。[接口与验收场景](../../specs/verification-npi-query.md)

## 验证工具与项目扩展

在 VM 桌面的 ZCode 打开工程，点击顶部的 **工具**。可以用 `modport`、`触发前`、`covergroup` 或 MCP 方法名搜索。选择工具后，「打开工具」进入对应原生面板；在输入框写下需求，点「交给 Agent」会在当前工程创建对话。也可从普通新对话直接提出需求。图形面板和脚本可以直接使用，对话使用 ZCode 设置中选定的模型。

| 工具 | 普通对话示例 | 可编辑的工程脚本 |
| --- | --- | --- |
| RTL 实例与信号连接 | 用 build/simv.daidir/simv.kdb 找 sender 的全部实例，列出实例路径。 | `verification_extensions/rtl_endpoints.py` 导出驱动和负载位置 |
| FSDB 波形提取 | 从 demo.fsdb 提取 wave_demo.data 的第 8 到 12 tick，给我波形和查询 ID。 | `verification_extensions/fsdb_edges.py` 统计区间跳变 |
| VDB 覆盖率提取 | 查 simv.vdb 合并视图中哪些 FSM 转移未命中。 | `verification_extensions/coverage_gaps.py` 分页汇总覆盖空洞 |

需要定制时，选择「二次开发」并写明要新增的处理和输出，例如「在 FSDB 跳变统计上增加含 X/Z 的时间点，写入项目 JSON 并实际运行」。也可点「创建项目示例」自行修改。首次生成文件，后续使用同一路径会保留已有代码。详情里的示例命令使用 VM 对应演示工程的输入，自己的工程请填写实际信号和对应构建产物的路径。

`verification_tool_catalog` 按 `toolId` 返回接口参数、命令行程序和原生源码位置。`verification_tool_scaffold` 生成使用同一验证服务的 Python 脚本。脚本中的 `VerificationClient.run()` 提交查询并等待终态，`call()` 读取单次结果，`coverage_rows()` 自动翻页。每类查询使用其原生作业 ID，可回到对应工具查看证据。

## FSDB 波形窗口

在 VM 桌面打开工程，点击 ZCode 顶部的「FSDB 波形」。可以从项目文件列表或文件选择器选择已有的 `.fsdb`，也可以填写 VM 上的绝对路径。工具通过 Verdi 的 NPI FSDB 模型读取二进制波形。SV/UVM 作业在运行目录中新生成的 FSDB 会保留在该作业的证据目录中。在「验证」页点击对应的 `.fsdb` 产物即可载入波形工具。

1. 点击「查找信号」，用层次名、子串、`*` 或 `?` 缩小范围。勾选要一起查看的信号，最多 16 条。
2. 选择「时间区间」填开始和结束 tick，留空采用文件边界。选择「触发前后」可以指定触发信号、边沿、搜索起点，以及要提前、延后多少 tick。页面显示文件的实际时间刻度。
3. 点击「提取波形」。在图中点击可移动所有信号共用的游标，也可输入精确 tick。工具栏支持缩放、平移、回到全区间和总线进制切换。「独立波形窗口」在单独的 Electron 窗口中打开同一份数据。
4. 对话中可以说「从 demo.fsdb 找到 wave_demo.clk 在第 6 tick 之后的第一个上升沿，提前 7 tick、延后 3 tick，显示 clk、valid 和 data 的波形并给我查询 ID」。Agent 通过 `fsdb_files`、`fsdb_signals`、`fsdb_wave` 和 `fsdb_get` 查询；在同一项目按 ID 可重开。每个成功的波形查询也会保存独立的 `waveform.html`。

在已部署的 VM 上，示例目录是 `/home/verification-agent/examples/fsdb`。在图形桌面以维护账号运行 `/home/verification-agent/compat/start-zcode.sh /home/verification-agent/examples/fsdb` 即可打开。命令行使用同一个服务。

```bash
cd /home/verification-agent/examples/fsdb
python3 /home/verification-agent/runner/fsdb-wave.py signals --file demo.fsdb --pattern '*lane.observed'
python3 /home/verification-agent/runner/fsdb-wave.py wave --file demo.fsdb \
  --signal wave_demo.clk --signal wave_demo.valid --signal wave_demo.data \
  --trigger wave_demo.clk --edge rising --from 6 --before 7 --after 3
```

`0→1` 和 `1→0` 分别匹配上升沿和下降沿，选择「任意变化」也能匹配 X/Z 的变化。数字总线保留四态值。每条信号默认提取至多 512 次变化，命令行 `--max-changes` 可设为 1–2048；单次读取还有总数据量限制。灰色截断区域表示需缩小区间重新读取。数据以原始 tick 字符串保存，超过 53 位的时间也可逐 tick 定位。[FSDB 规格与验收](../../specs/verification-fsdb.md)

## NPI 覆盖率数据

在 VM 原生 ZCode 中打开「验证 → 覆盖率数据」。填入现有 VCS `.vdb` 目录、库内文件路径，或点击「从所选作业提取」。可填写配套的 `.el` 排除文件。完成后按测试、指标、层次名和状态筛选，点击对象路径可查看行号、原生状态位、目标、计数及父对象 ID。指标旁的数量是该测试视图中的数据对象数，归属测试和 cross 组成关系可在明细中查看。命中次数为 0 与 NPI 没有提供该字段在表中分别显示为 0 和横线。

在示例工程 `/home/verification-agent/examples/coverage` 可以对 Agent 说「把 simv.vdb 的所有覆盖数据提取出来，对比 quiet 和 active 的 mode_cp.on，列出合并结果中未覆盖的 FSM 转移」。Agent 通过 `coverage_extract`、`coverage_get` 和 `coverage_rows` 调用相同的服务。查询 ID 可在同一项目中重开。

```bash
cd /home/verification-agent/examples/coverage
coverage_cli=/home/verification-agent/runner/coverage-query.py
job_id=$(python3 "$coverage_cli" extract --path simv.vdb | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
python3 "$coverage_cli" rows "$job_id" --view merged --metric fsm --kind TransBin --state missed
```

「完整导出文件」提供逐行 NPI 对象 `coverage.jsonl`、可查询的 `coverage.sqlite`、VDB XML 节点及字段 `vdb-xml.jsonl`、逐文件 SHA-256 清单，以及可还原所有源文件内容的 `source-vdb.zip`。每个测试保留单独视图，多测试库还提供 NPI 合并视图。低功耗记录随源库采集情况出现。CLI 和 Agent 分页时传入上一页的 `nextAfter`，直到返回空值。[覆盖率提取规格](../../specs/verification-coverage.md)

## 知识库

桌面顶部的「知识库」可选择已导入的手册、检索 API 和主题、浏览章节，按 PDF 页码阅读原文。「原始 PDF」会打开对应页，适用于图表及代码排版核对。对话 Agent 可调用 `knowledge_list`、`knowledge_search`、`knowledge_read` 检索同一份资料。

在实现需求时，如果检索结果或索引文本不够，Agent 可主动调用 `knowledge_read_original`，直接读取保存在 VM 的 PDF，取得所选页的原文和图像，并继续翻阅相邻页。该工具使用 CentOS 宿主的 `pdftotext` 和 `pdftoppm`。返回的文件路径也可供 Agent 的文档工具读取，桌面启动环境会将本地知识目录挂载为只读。

在 VM 的「知识库」点击「添加 PDF 并归档」，选择项目目录、桌面、文档或下载目录中的 PDF。选择文件会自动开启普通 Agent 对话，使用当前配置的模型和工具权限。也可以直接在对话中说「把项目里的 docs/interface.pdf 加入知识库并整理」。启动器将通用归档技能注册到 Agent 的配置中，每本新手册共用这套流程。

Agent 保留原件并建立全文索引，再逐批阅读页码证据，保存主题、摘要、检索别名和出处。同一文件换名导入会得到已有来源，内容变化会创建独立来源。知识库显示模型已整理的页数、归档主题及待复核的原页。归档中断后，选择手册并点击「继续模型归档」即可从检查点继续。设置中需要有可用模型才能进行模型归档。检索和翻看已导入的手册可离线使用。

也可在已安装 PyMuPDF 和 SQLite FTS4 的环境中运行索引导入器，随后在知识库中启动模型归档。在 CentOS 7 宿主使用部署的 Python 依赖：

```bash
base=/home/verification-agent
runuser -u host -- env PYTHONPATH="$base/runtime/python" python3 "$base/runner/import-manual.py" \
  /path/to/manual.pdf --library "$base/knowledge"
```

回到知识库点击「刷新」。原始 PDF、全文索引和模型归档都保存在 VM 的知识目录中。

## 样例验收记录

在原生 Electron 窗口以空应用配置打开 FIFO，验证了免登录启动、VCS SV、UVM 功能覆盖率 100%、IFV 属性证明和重启后恢复同一运行 ID。FIFO 的故障版能触发 UVM scoreboard 失败，以及 IFV 反例。

项目里的本地作业记录保存在 VM 的 `/home/verification-agent/artifacts`。自有项目可在项目根目录按 [FIFO 的配置](fifo/verify.yaml) 添加 `verify.yaml`，再把项目路径传给启动器。

## 开源 Formal 与商业适配器

在 FIFO 工作台选择 `formal · Yosys + Z3` 运行开源验证，选择 `formal-ifv · IFV` 使用已安装的 Cadence 工具。其他 Windows x64 和 Linux x86-64 设备可直接使用对应的离线 Formal 包。项目格式、双入口、安装包构建和商业适配器协议见 [Formal 工具包说明](../formal/README.md)。

Debian 桌面完整包使用 electron-builder 的 Linux x64 `linux-unpacked` 产物。在有 `dpkg-deb` 的构建环境执行 `bash deploy/formal/package-desktop-deb.sh /path/to/linux-unpacked ./zcode-verification-agent_amd64.deb`。安装后的应用菜单有独立的「ZCode 验证 Agent」入口，命令 `zcode-verification-agent` 打开 FIFO 示例，`zcode-verification-agent /path/to/project` 打开用户工程。
