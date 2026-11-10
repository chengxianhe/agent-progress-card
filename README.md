# Agent Progress Card · AI 任务小看板

[English](README.en.md)

一个独立的 macOS 桌面小卡片，用来查看 AI 助手当前在做什么：任务状态、公开工作说明、
工具调用、最近回复和任务历史。可选接入本人微信，把文字指令发到已绑定的 Codex 会话，
并接收该会话的进度与结果。

无需网页服务或模型 API Key；本工具不包含 Agent 执行引擎。任务仍由你已打开的助手会话执行。

## 功能

- 原生 SwiftUI / AppKit 窗口：拖动、置顶、展开和收起。
- 当前/历史任务切换；概览、过程、工具、结果分类。
- 按命令、文件、网页、MCP 筛选工具，查看失败项与有长度限制的参数/结果。
- 工具调用下方显示公开工作说明，保留当前会话最近一次完成回复。
- 可显式发布编号选项：小看板弹出选择，微信回复编号后将选项送入已绑定会话。
- 显式绑定单个 Codex 会话，读取公开事件并脱敏；不会显示内部推理或自动读取其他聊天。
- 微信扫码、配对码、连接状态与停止同步放在卡片内，仅接受扫码本人。

当前为源码发布，macOS 13+；需要 Xcode Command Line Tools、Python 3.10+。
原生采集进程使用 CLT 提供的 `/usr/bin/python3`，该采集子集兼容 Python 3.9。
本次发布不提供 Apple 公证安装包，不承诺所有系统版本均已验证。

## 构建与打开

```bash
git clone https://github.com/chengxianhe/agent-progress-card.git
cd agent-progress-card
bash desktop/build.sh
open build/AgentProgressCard.app
```

若没有编译工具，先运行 `xcode-select --install`。应用用本机架构构建并作 ad-hoc 签名。
构建脚本在检测到重复且内容一致的 CLT module map 时使用局部 overlay，不修改系统 SDK。

可选安装：

```bash
python3 desktop/install.py
```

安装到 `~/Applications/AgentProgressCard.app`，目标已存在时拒绝覆盖。
旧版用户请先阅读 [迁移说明](docs/migration.md)。关闭窗口只隐藏窗口，Cmd+Q 完全退出。

## 让卡片显示任务

单纯打开窗口不会自动猜测任务。由助手或脚本明确发布状态：

```bash
PYTHONPATH=src python3 -m agent_progress_card begin \
  --title '更新项目文档' --action '核对功能与现状'
# 将返回的 task_id 填入下方 TASK_ID。
PYTHONPATH=src python3 -m agent_progress_card update --task-id TASK_ID \
  --status running --action '检查文档链接' --detail '正在核对本地引用'
PYTHONPATH=src python3 -m agent_progress_card update --task-id TASK_ID \
  --status succeeded --action '文档检查完成'
```

状态有 `running / waiting / succeeded / failed`；待人工审查时使用 `waiting`。
新任务默认不覆盖活动任务，`begin --replace` 只切换显示，不取消助手正在执行的工作。
也可在虚拟环境中 `python3 -m pip install .`，使用 `agent-progress-card` 命令。

需要你在几个方案中选择时，助手先发布编号选项：

```bash
PYTHONPATH=src python3 -m agent_progress_card choice \
  --question '先做哪项？' --option '修复卡片' --option '完善微信'
```

微信回复 `1` 或 `2`，或点击卡片选项；成功送达后自动清除。仅在聊天里直接答复，
或主动取消这道题时手动运行：

```bash
PYTHONPATH=src python3 -m agent_progress_card clear-choice
```

卡片会弹出问题与选项，也保留页内选择入口；已连接的微信在回信上下文有效时会收到相同通知。
没收到时，在扫码绑定的机器人会话发送“选项”，即可取回当前问题，再回复 `1`、`2` 等编号。
微信编号会转换为完整选项文本，作为用户消息送入当前 Codex 会话；也可以直接点击卡片选项，
通过本机会话发送，不依赖微信转发进程。收到会话的投递回执后，选项自动关闭，卡片保留短暂回执；
这表示消息被接收，不代表任务已经完成。结果不确定时禁止重复选择，先在桌面核对。
普通文字仍原样转入会话。这里处理的是工作方案选择。
旧选项在 24 小时后自动过期，切换绑定会话后也不会显示。
微信接口的回信上下文会过期；长期未在微信发消息时，通知会保留排队。
此时在绑定的机器人会话发“选项”或“进度”，转发器获得新上下文后优先回复当前问题。
普通选项需由助手显式发布到小看板。Codex 命令行自身显示的交互式选项不会被自动捕获；
微信回复编号也不会直接回答那份终端请求。工具和系统权限仍只能在原客户端批准。

卡片显示的是**本轮平均输出 token/秒**，按记录中的输出用量与本轮经过时间计算；
包含工具等待时间，只有收到用量事件后才显示，不能代表模型瞬时生成速度或费用。

## 显示真实工具调用

绑定你明确指定的本机 Codex 会话记录与会话 UUID：

```bash
PYTHONPATH=src python3 -m agent_progress_card.attach \
  --transcript /absolute/path/to/rollout.jsonl --thread-id THREAD_UUID
```

两项必须来自同一会话，绑定会校验文件元数据；只读最近一轮及后续公开事件。
可从会话工具提供的记录路径定位；没有可靠路径/UUID 时不要猜测或批量扫描其他聊天。
App 启动采集子进程，退出后采集停止；没有开机自启动或全局 hooks。

会话格式和本地控制接口为实验性适配，历史验证基于 Codex CLI 0.167.0。
客户端升级后需要重新验证兼容性；本项目不是官方稳定接口或官方产品。

## 可选：通过本人微信交互

先完成上述绑定，并在 Codex 客户端打开对应会话，然后运行：

```bash
PYTHONPATH=src python3 -m agent_progress_wechat.relay \
  --state-dir "$PWD/runs/wechat" --thread-id THREAD_UUID
```

保持小看板与该命令运行，在小看板连接设置内扫码、输入配对码并确认连接。
微信端需支持相应 iLink/ClawBot 连接，是否可用以账号和服务返回为准。
连接后普通文字送入绑定会话；`进度`、`结果`、`帮助`由本地记录回答。
详细边界、停止与故障处理见 [微信连接](docs/wechat.md)。

不读取个人微信聊天列表、群聊或数据库。权限审批仍在原客户端处理；微信“同意”不能代替审批。
轮询和显示本身不调用模型；转入会话的普通文字会触发正常模型用量。

## 数据与隐私

- 卡片状态保存在 `~/Library/Application Support/AgentProgressCard/`。
- 微信凭据和队列保存在你指定的 `--state-dir`，默认示例位于已忽略的 `runs/wechat/`。
- 使用私有文件权限、脱敏和长度限制；脱敏不是覆盖所有敏感内容的保证。
- 历史最多保留 12 个任务，每任务最多 20 条调用与 30 条工作记录，不是完整审计系统。
- 完成回复不自动代表任务通过人工验收；服务心跳不代表模型正在工作。
- 不提交凭据、原始聊天、数据库、二维码或构建产物。

## 开发与验证

```bash
bash scripts/verify.sh
```

Python 使用标准库测试；macOS 同时构建卡片与可选扫码窗口，运行六组原生模型测试。
日志位于忽略的 `build/verification/`。测试使用临时目录与合成数据，不连接真实微信。
原生窗口交互与真实扫码须另行验证，不能由单测通过推断。

```text
desktop/                    SwiftUI/AppKit 界面、构建与安装工具
src/agent_progress_card/    状态 CLI、绑定、事件采集与脱敏
src/agent_progress_wechat/  本人微信桥接与实验性当前会话通道
tests/                     Python 回归测试与合成原生测试数据
scripts/                   可重复的验证入口
docs/                      微信与迁移说明
```

独立仓库使用自己的包名与 Git 历史，不依赖原演示工程。
许可证为 [MIT](LICENSE)，来源与保留声明见 [NOTICE](NOTICE)。维护者：`chengxianhe`。
