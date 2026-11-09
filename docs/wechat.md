# 本人微信连接

默认使用当前会话 relay。条件是小看板已绑定目标会话，Codex 客户端已打开该会话，
本机存在可用的控制 socket，微信账号支持 iLink/ClawBot 配对。此通道是实验性适配。

```bash
PYTHONPATH=src python3 -m agent_progress_wechat.relay \
  --state-dir "$PWD/runs/wechat" --thread-id THREAD_UUID
```

小看板“连接设置”显示二维码、配对码及连接状态。首次扫码后凭据保存在指定目录；
凭据有效时重启可继续使用，失效时使用新的状态目录重新扫码，不跨账号复用队列。
不要上传 `credentials.json`、`relay.sqlite3`、二维码或含真实消息的日志。

普通文本成为绑定会话的用户输入；忙碌时追加指令，空闲时开启该会话的下一轮。
不新建/分叉/恢复其他会话、不覆盖模型、工作区、沙箱或权限策略、不响应权限审批。
收到服务端回执只表示输入被接受，不代表任务完成。

发送后断线或回执丢失时记录“投递结果不确定”，不自动重发指令；未发送的任务可等待重连。
公开工作说明限频回传，最终回复立即排队；重启恢复的历史消息不自动补发。
结果沿用卡片的脱敏与长度限制，可能截断。回复最多重试 5 次，不承诺网络层恰好一次投递。

`进度`、`结果`、`帮助`从本地记录回答，不额外调用模型。普通聊天会产生会话的正常模型用量。
卡片里“停止同步”或命令行 Ctrl-C 停止转发，不取消 Codex 已接收并正在执行的任务。
电脑休眠、断网、客户端退出或绑定切换会影响连接；没有开机自启或无人值守保证。

如启动失败，核对 thread UUID、卡片绑定和客户端运行状态；不要通过降低原会话权限限制解决连接问题。
扫码入口不可用以微信实际返回为准；不支持个人聊天列表、群消息、语音、图片和附件。

## 保留的独立只读模式

旧的独立执行器作为可选兼容入口保留，默认 README 不使用它。它不会续接现有会话：

```bash
bash desktop/build-wechat.sh
PYTHONPATH=src python3 -m agent_progress_wechat \
  --workspace /absolute/path/to/your/workspace --state-dir "$PWD/runs/wechat-legacy" \
  --window "$PWD/build/WeChatLogin"
```

此模式新建独立 Codex CLI 任务，使用只读沙箱和禁止提权策略；不应与当前会话 relay 混用状态目录。
只读沙箱限制写入，并不意味着只能读 workspace 内的文件。它仅供本人使用，不是接收陌生人任务的服务。
