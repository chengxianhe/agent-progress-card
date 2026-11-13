<div align="center">
  <img src="desktop/Assets/AppIcon.png" width="96" alt="微光应用图标">
  <h1>微光</h1>
  <p><strong>让 Codex 在忙什么，一眼就能看见。</strong></p>
  <p>桌面进度卡片 · 任务与工具记录 · 可选本人微信交互</p>
  <p>macOS 13+ · SwiftUI / AppKit · Python 标准库 · MIT</p>
  <p><a href="README.en.md">English</a> · <a href="#快速开始">快速开始</a> · <a href="#通过本人微信交互">微信使用</a> · <a href="#常见问题">常见问题</a></p>
</div>

微光（原名 Agent Progress Card）把一个明确绑定的 **Codex 会话**放到桌面上：当前任务、公开工作说明、工具调用和最近回复随时可见。
需要离开电脑时，还可以连接本人微信，查进度、发任务，并回复已支持的选择与请求。

任务仍由原有 Codex 会话执行。桌面记录和本地查询不额外调用模型；发任务与回复选择使用该会话的正常模型用量，无需为微光另配模型 API Key。

## 它可以帮你做什么

| 你遇到的情况 | 微光提供的帮助 |
| --- | --- |
| 助手跑了很久，不知道做到哪一步 | 置顶小卡片展示当前动作、公开说明与最近工具记录，减少反复切回聊天 |
| 已经结束一轮，想找它刚才的回复 | 单独显示最近回复，并在「结果」中回看当前任务记录 |
| 助手需要你作出选择 | 普通选项可直接在卡片点选，也可在微信按通知回复编号；多题和文字回答有表单 |
| 想看看刚才调用了什么、哪里失败了 | 「工具」可按类型筛选、仅看失败项，并展开脱敏后的参数与返回内容 |
| 暂时离开电脑，仍想跟进 | 可选本人微信通道支持本地进度查询、向原会话发文字，以及已适配的正式请求 |

微信使用需要电脑保持运行、网络与绑定会话可用。支持范围见下方[微信说明](#通过本人微信交互)。

## 界面是什么样的

柔和中性灰、低饱和铜色点缀，跟随系统深浅色模式。原生小窗支持拖动、置顶、展开与收起。

<p align="center">
  <img src="docs/images/weiguang-light.png" width="300" alt="微光浅色界面：当前任务、内容分类、编号确认卡片与工作说明">
  <img src="docs/images/weiguang-dark.png" width="300" alt="微光深色界面：低亮度灰色背景与完整编号选项">
</p>

以上是**使用合成任务数据渲染的正文界面示例**，没有真实账号、聊天或会话信息。

- **概览**：当前动作、公开说明、待选问题和最近调用。
- **过程**：按时间回看最近的公开工作记录。
- **工具**：查看调用类型、耗时、失败项与可展开详情。
- **结果**：查看任务状态与最近完成回复；状态完成不等于已经人工验收。

<details>
<summary>看看收起状态和文字回答表单</summary>

<p>
  <img src="docs/images/weiguang-compact.png" width="300" alt="收起后的微光小窗，保留当前任务与待选问题">
  <img src="docs/images/weiguang-form.png" width="300" alt="普通问题的选项与文字回答表单">
</p>

短问题按内容高度显示；长问题、多个选项和表单可滚动查看。普通聊天回答与正式工具授权使用不同的处理方式。

</details>

## 快速开始

以下命令均在本仓库根目录执行。首次使用需要终端，当前流程是本机构建。

### 1. 准备并构建

需要 **macOS 13+、Xcode Command Line Tools、Python 3.10+**，以及已安装的 Codex 客户端。
命令行包使用 Python 标准库；App 内置采集入口使用 CLT 的 `/usr/bin/python3`，该子集兼容 Python 3.9。

缺少编译工具时先执行 `xcode-select --install`，完成安装后继续：

```bash
git clone https://github.com/chengxianhe/agent-progress-card.git
cd agent-progress-card
bash desktop/build.sh
```

构建生成 `build/微光.app`，按本机架构编译并使用 ad-hoc 签名，未经过 Apple 公证。

### 2. 选择并绑定一个 Codex 会话

在 Codex 中打开你要跟进的对话，并确保该会话已开始过至少一轮任务。确认这一个会话的：

| 参数 | 填什么 |
| --- | --- |
| `--transcript` | 该会话对应的 `rollout.jsonl` 完整路径 |
| `--thread-id` | 同一会话的 UUID |

不知道这两个值时，先请当前对话的助手协助核对；无需提供整个聊天目录。微光当前没有自动选择会话的图形向导。

```bash
# 将路径和 THREAD_UUID 替换为同一会话的真实值。
PYTHONPATH=src python3 -m agent_progress_card.attach \
  --transcript /absolute/path/to/rollout.jsonl \
  --thread-id THREAD_UUID
```

绑定会校验会话身份，从最近一轮及后续公开事件开始采集，不会自动猜测其他对话。

### 3. 发布第一个看板任务，再打开窗口

**绑定负责采集记录；任务标题和状态由你、助手或脚本显式发布。** 首次可先运行：

```bash
PYTHONPATH=src python3 -m agent_progress_card begin \
  --title '我的第一个任务' --action '等待新的工作说明'
open "build/微光.app"
```

保留 `begin` 返回的 `task_id`。这条命令只创建显示记录，实际工作仍需在绑定的 Codex 对话中发起。

接着在该对话继续一轮任务：窗口应出现你发布的任务标题，公开说明、工具记录和回复会随采集刷新。
后续用 `update` 更新阶段与状态，完整示例见下方[让助手或脚本更新进度](#让助手或脚本更新进度)。

### 4. 安装到应用目录，固定到 Dock

本地构建确认可用后，可选安装：

```bash
python3 desktop/install.py
open "$HOME/Applications/微光.app"
```

安装器遇到已有「微光」或旧名应用会拒绝覆盖；升级先读[迁移说明](docs/migration.md)。
已有任务、会话绑定和微信凭据继续使用原有数据目录，应用文件名与 Dock 显示名均为**微光**。

要固定到底部 Dock，打开 App 后右键点按其图标，选择「选项 → 在程序坞中保留」。
这是 macOS 的常规操作，见 [Apple 程序坞说明](https://support.apple.com/zh-cn/guide/mac-help/mh35859/mac)。
桌面需要可双击的入口时，可在访达中为「微光.app」创建替身并放到桌面；保留实际 App 在应用目录。

关闭窗口会隐藏卡片；`Cmd+Q` 退出 App，并让它启动的采集器随父进程退出。微信后台单独管理。

## 通过本人微信交互

**只想用桌面看板，可以跳过这一节。** 微信通道连接同一个已打开的 Codex 对话，不另开聊天上下文。
账号需要支持 iLink/ClawBot，且本机 Codex 控制 socket 可用；是否可配对以实际服务返回为准。

完成桌面绑定后，保持目标会话在 Codex 客户端中打开，运行：

```bash
PYTHONPATH=src python3 -m agent_progress_wechat.relay \
  --state-dir "$PWD/runs/wechat" --thread-id THREAD_UUID
```

在微光的「连接设置」中扫码，并按提示输入配对码。首次启动可在前台运行，`Ctrl+C` 可停止此进程。
需要后台监督时，再按[常驻说明](docs/wechat-resident.md)显式安装。

| 在本人机器人会话发送 | 你能做什么 |
| --- | --- |
| 普通文字 | 向已绑定的 Codex 会话发任务或补充要求，产生正常模型用量 |
| `进度` / `结果` / `帮助` | 从本地状态获取信息，不开启新的模型任务 |
| `选项` | 获取当前普通问题，按通知里的完整编号回复 |
| `审批` | 查询有效请求列表；`审批 2` 翻页，`审批 A编号` 获取一项完整详情 |
| `诊断` / `出门检查` | 查看微信、任务会话、审批、采集和监督的当前证据 |

**C 编号是普通聊天选择，A 编号是正式请求。** 按每次通知原文回复，不凭固定数字猜“允许”。
收到通知里的完整详情后，再作出明确选择。多题或文字输入按通知使用 `填写 C编号 JSON` 或 `填写 A编号 JSON`。

命令、MCP 授权及受支持的正式表单需要显式启用手机请求适配：先正常停止已有 relay，再在原命令中增加
`--remote-approvals`；以 `--no-remote-approvals` 重启可关闭。设置按绑定账号和会话保存，不修改 Codex 的模型或权限策略。
长期放行、身份验证、秘密输入和未支持结构仍需原客户端；完整范围见[手机请求说明](docs/remote-approvals.md)。

断开或重启后不补发历史通知；本人发送新消息后恢复，只自动发一条当前摘要。有效问题和请求按需查询。
登录失效、电脑休眠或上游拒收仍会影响送达，后台常驻不能保证手机永远在线。详见[微信连接](docs/wechat.md)与[恢复策略](docs/wechat-queue-policy.md)。

## 让助手或脚本更新进度

可以把下面的命令约定交给处理该任务的助手。所有命令在微光仓库根目录执行；用实际 `task_id` 替换 `TASK_ID`。

```bash
# 开始任务，返回 task_id。
PYTHONPATH=src python3 -m agent_progress_card begin \
  --title '更新项目文档' --action '核对现有功能'

# 发布一个阶段。
PYTHONPATH=src python3 -m agent_progress_card update \
  --task-id TASK_ID --status running --action '正在核对使用步骤'

# 留给人确认。
PYTHONPATH=src python3 -m agent_progress_card update \
  --task-id TASK_ID --status waiting --action '检查完成，等待你审阅'
```

支持 `running / waiting / succeeded / failed`。自动检查通过可记录为完成相应工作，人工验收仍由人确认。
已有任务时优先更新原 ID；`begin --replace` 仅明确切换显示，不会取消 Codex 正在执行的工作。

发布一个普通选择：

```bash
PYTHONPATH=src python3 -m agent_progress_card choice \
  --question '先做哪项？' --option '优化界面' --option '补充文档'
```

卡片或微信投递收到回执后自动关闭选择；聊天里直接回答后，由助手调用 `clear-choice`。
回执不确定时不自动重发，避免重复执行。

## 常见问题

| 问题 | 先检查什么 |
| --- | --- |
| 打开后一直等待任务 | 绑定不等于创建任务；先执行 `begin`，并确认打开的是绑定会话 |
| 提示「未找到会话轮次」 | 该 Codex 会话须先开始过一轮任务，路径和 UUID 也必须匹配 |
| 标题还在，记录不刷新 | 卡片可能是最后记录；检查 Codex、采集状态与绑定，微信可发 `诊断` |
| 微信收不到通知 | 先在本人机器人会话发送 `进度`；回信上下文失效与登录失效不同，按连接状态处理 |
| 关闭窗口后微信还在同步 | 窗口与微信后台独立；用「停止微信同步」暂停，而不是只关窗口 |
| 电脑关机或休眠后还能用吗 | 不能保证；现有电脑、网络与会话需要保持可用 |

微光只读指定会话的公开事件，不展示内部推理，也不读取个人微信联系人、聊天列表或群聊。
工具内容会脱敏、限长；历史保留最多 12 个任务，每任务最多 20 条调用和 30 条工作记录，不能当完整审计归档。

状态位于 `~/Library/Application Support/AgentProgressCard/`；微信凭据在你指定的状态目录。
请勿分享凭据、二维码、数据库、原始聊天或真实会话标识。脱敏属于尽力处理，分享记录前仍需检查。

## 更多文档与开发

- [微信连接与故障处理](docs/wechat.md) · [手机授权与表单](docs/remote-approvals.md)
- [手机编号分流](docs/mobile-approval-routing.md) · [请求覆盖与恢复边界](docs/recovery-and-mobile-requests.md)
- [后台常驻](docs/wechat-resident.md) · [旧版本迁移](docs/migration.md)
- [验证记录](docs/verification.md) · [界面设计与更名记录](docs/design-weiguang.md)

```bash
bash scripts/verify.sh
```

本轮 macOS 检查包含 **212 项 Python 测试、两个原生入口构建和 8 组模型测试**。
自动测试使用合成数据，不向真实微信发送消息。本机 Dock 图标与名称已由用户确认；这不等于所有手机请求均已实测。
正式表单、文件修改、本轮权限等仍按各自[验证边界](docs/verification.md)看待。Codex 本地接口属于实验性适配，升级客户端后需复验。

源码：`desktop/` 原生界面与构建，`src/agent_progress_card/` 记录与采集，`src/agent_progress_wechat/` 微信桥接，`tests/` 回归。

[MIT License](LICENSE) · 原始来源与归属见 [NOTICE](NOTICE)。
