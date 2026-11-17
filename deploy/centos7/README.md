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
python3 -m pip install --target "$base/runtime/python" -r "$base/runner/requirements.txt"
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

## 样例验收

在原生 Electron 窗口以空应用配置打开 FIFO，验证了免登录启动、VCS SV、UVM 功能覆盖率 100%、IFV 属性证明和重启后恢复同一运行 ID。FIFO 的故障版能触发 UVM scoreboard 失败，以及 IFV 反例。

项目里的本地作业记录保存在 VM 的 `/home/verification-agent/artifacts`。自有项目可在项目根目录按 [FIFO 的配置](fifo/verify.yaml) 添加 `verify.yaml`，再把项目路径传给启动器。
