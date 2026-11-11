# Agent Progress Card · AI 任务小看板

[English](README.en.md)

一个原生 macOS 桌面小卡片，展示 AI 助手的任务状态、公开工作说明、工具调用、最近回复和任务历史。
可选连接本人微信，在手机上向已绑定的 Codex 会话发任务、查进度，并处理已适配的命令、MCP 工具授权和表单。

无需网页服务或额外的模型 API Key。本工具不包含 Agent 执行引擎，任务仍由已打开的 Codex 会话执行。
不展示内部推理，不读取其他会话、个人微信聊天列表或群聊。

## 功能

- SwiftUI / AppKit 窗口，可拖动、置顶、展开和收起。
- 当前/历史任务切换；概览、过程、工具、结果分类，以及工具类型/失败项筛选。
- 工具调用下方展示公开工作说明，保留最近完成回复；参数与结果有脱敏和长度限制。
- 显示本轮平均输出 token/秒，包含工具等待时间，不代表瞬时生成速度或费用。
- 普通看板选项支持卡片点选、微信编号回复；原生提问历史记录显示只读通知，正式请求按适配类型处理。
- 本人微信扫码与连接管理；消息排队、退避重试及发送异常提示。
- 显式开启后，在微信选择命令/MCP 授权、填写表单；文件修改与权限申请使用独立回复格式。
- 可选用户级后台常驻：登录后启动、异常退出后恢复，尊重手动停止。

## 构建与安装

需要 macOS 13+、Xcode Command Line Tools 和 Python 3.10+。
App 内置采集入口使用 CLT 的 `/usr/bin/python3`，该子集兼容 Python 3.9。

```bash
git clone https://github.com/chengxianhe/agent-progress-card.git
cd agent-progress-card
bash desktop/build.sh
open build/AgentProgressCard.app
```

缺少编译工具时先运行 `xcode-select --install`。应用按本机架构构建，使用 ad-hoc 签名，未经过 Apple 公证。
构建脚本只使用局部 module-map overlay，不修改系统 SDK。

可选安装到 `~/Applications/AgentProgressCard.app`：

```bash
python3 desktop/install.py
```

目标已存在时安装器拒绝覆盖，更新请先阅读[迁移说明](docs/migration.md)，保留旧版本与本机状态。
关闭窗口仅隐藏窗口；Cmd+Q 退出 App 并停止它启动的事件采集。微信后台服务单独管理。

## 绑定会话与显示进度

卡片不会自动猜测当前任务。绑定你明确指定的会话记录与对应 UUID：

```bash
PYTHONPATH=src python3 -m agent_progress_card.attach \
  --transcript /absolute/path/to/rollout.jsonl --thread-id THREAD_UUID
```

两项必须来自同一会话；只读最近一轮及后续公开事件。不要批量扫描其他聊天来猜测绑定目标。
App 退出后采集停止；微信常驻服务不会替代这个采集进程。

也可以由助手或脚本显式发布任务：

```bash
PYTHONPATH=src python3 -m agent_progress_card begin \
  --title '更新项目文档' --action '核对功能与现状'
# 使用上一步返回的 TASK_ID。
PYTHONPATH=src python3 -m agent_progress_card update --task-id TASK_ID \
  --status running --action '检查文档链接'
PYTHONPATH=src python3 -m agent_progress_card update --task-id TASK_ID \
  --status succeeded --action '自动检查完成'
```

状态支持 `running / waiting / succeeded / failed`；等待人工审查时使用 `waiting`。
最终回复和 `succeeded` 状态不等于用户已验收。`begin --replace` 只切换显示，不取消正在执行的任务。

## 通过本人微信交互

先绑定会话，并在 Codex 客户端打开该会话，然后启动：

```bash
PYTHONPATH=src python3 -m agent_progress_wechat.relay \
  --state-dir "$PWD/runs/wechat" --thread-id THREAD_UUID
```

在小看板连接设置里扫码、输入需要的配对码。账号需支持 iLink/ClawBot，是否可用以实际服务返回为准。
仅接收绑定本人的文字；消息送入原会话，不另开一个 AI 对话。详见[微信连接](docs/wechat.md)。

| 微信内容 | 处理方式 |
| --- | --- |
| 普通文字 | 送入已绑定的 Codex 会话，产生正常模型用量 |
| `进度` / `结果` / `帮助` | 从本地状态回复，不转成新的模型任务 |
| `选项` | 查询普通看板选项；没有时显示最近的原生提问记录 |
| `审批` | 查询当前手机授权与表单，并重新发送详情 |

轮询、状态显示及本地查询本身不调用模型。退出 App 不等于停止微信同步；暂停请用“停止微信同步”。

### 三种选项的区别

| 类型 | 展示与回复 |
| --- | --- |
| 助手显式发布的普通看板选项 | 卡片点选或微信编号回复，作为用户消息送入当前会话 |
| Codex 原生普通表单 | 收到正式请求时可按编号或填写 JSON 作答；只有历史记录时不能假称已提交原生表单 |
| 命令权限审批 | 显式启用后，微信决定通过正式审批协议回传；不作为聊天消息发送 |

发布普通看板选项：

```bash
PYTHONPATH=src python3 -m agent_progress_card choice \
  --question '先做哪项？' --option '修复卡片' --option '完善微信'
```

收到投递回执后自动关闭选项；回执不确定时不会自动重发。用户在聊天里直接回答或取消问题时，
由助手调用 `PYTHONPATH=src python3 -m agent_progress_card clear-choice`。旧选项 24 小时后过期。

### 手机授权与表单

正常停止旧 relay，再在原启动命令中加入 `--remote-approvals`。设置按绑定账号和会话保存在本机，
重启沿用；以 `--no-remote-approvals` 重启可关闭。默认不开启，也不修改 Codex 的权限或模型配置。

微信按服务端提供的原顺序列出选项。例如某次请求为：

1. 仅此次允许
2. 允许同类命令以后执行（需电脑端操作）
3. 拒绝并结束本轮

编号以每次实际通知为准。回复“选项号 A审批编号”；仅有一项已通知审批、且没有普通选项时可直接回数字。
通知会展示命令、目录和原因；编号最多有效 10 分钟，断线、重启或电脑已处理后失效。
命令正文最多 60,000 字符；长正文按每段 2,200 字符完整分段发到微信，所有分段送达后才能选择。超过总量上限或涉及敏感内容时会说明原因。
支持单次命令允许、拒绝或取消；MCP 工具 Allow/Cancel、正式原生问题、简单 MCP 表单、附完整差异的单次文件修改和本轮权限申请也有独立适配。
唯一已通知且没有其他选项时，也可回复 `Allow` 或 `Cancel`。多题/文字表单按通知使用 `填写 A编号 {"问题ID":"答案"}`。
长期规则、会话放行、专用身份验证、含敏感信息或不能完整展示的请求不自动转换为单次允许；会发送具体限制通知。
审批关闭回执不等于命令成功，执行结果仍看任务进度。详见[审批实现与验证](docs/remote-approvals.md)。

### 后台常驻与收不到消息

可显式安装用户级 LaunchAgent，使桥接在登录后运行、异常退出后恢复；不会重复启动轮询进程，
手动停止仍有效。安装与停用见[常驻说明](docs/wechat-resident.md)。

常驻不能保证微信一直接受主动推送。微信返回 `-2 / prepare failed` 时，程序可能仍正常接收消息，
只是暂时发不出去；这不等于登录凭据失效。通知保留并重试，最长退避 5 分钟。
在机器人会话发送 `进度` 或 `选项` 可刷新回信上下文；确实显示登录失效时才重新扫码。
接口接受消息不证明手机已显示；电脑休眠、断网、Codex 关闭也会影响使用。

## 数据、兼容性与验证

- 卡片状态位于 `~/Library/Application Support/AgentProgressCard/`；微信凭据和队列位于指定的 `--state-dir`。
- 不提交凭据、原始聊天、真实会话标识、数据库、二维码、日志或构建产物；脱敏不能保证覆盖所有敏感内容。
- 历史最多保留 12 个任务，每任务最多 20 条调用与 30 条工作记录，不是完整审计系统。
- Codex 会话格式与控制通道属于实验性适配，已验证版本为 CLI 0.167.0；客户端升级后需复验。

```bash
bash scripts/verify.sh
```

当前包括 148 项 Python 测试、两个 macOS 原生入口构建和 7 组原生模型测试。
测试使用合成数据，不连接真实微信；真实收发、手机审批与桌面交互需另行验证。
日志保存在已忽略的 `build/verification/`；验证范围与限制见[验证记录](docs/verification.md)。

本次手机实测：MCP 四选项中的单次允许，以及 3,798 字符命令分两段后回复编号执行，均已成功。
60,000 字符边界、分段重组、未全部送达时禁止授权由自动测试覆盖；不代表同等长度已在微信实测。
正式表单、文件修改、本轮权限请求的适配已有自动测试，仍待对应手机实测。普通客户端表单若只出现在历史记录中，不能通过微信提交原生答案。

源码分布：`desktop/` 为原生界面与构建工具，`src/agent_progress_card/` 为状态与事件采集，
`src/agent_progress_wechat/` 为微信桥接，`tests/` 为回归测试。

本仓库有独立包名和 Git 历史，不依赖原演示引擎。许可证为 [MIT](LICENSE)，来源声明见 [NOTICE](NOTICE)。
