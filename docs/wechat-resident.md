# 微信后台常驻

用户于 2026-11-11 明确要求常驻，使用当前用户的 macOS LaunchAgent。
`agent_progress_wechat.resident` 监督既有 relay，保持原账号、会话和本机凭据，不创建新会话。

## 行为

- 登录 macOS 后启动；监督进程异常退出由 launchd 重启，relay 异常退出在约 15 秒后重试。
- 已有 relay 持锁时等待，不启动第二个微信轮询进程。
- 手动“停止微信同步”后尊重 stop-request，不自动恢复；重新扫码/显式启动原 relay 后可继续监督。
- 登录失效等待本人重新扫码；不自动删除或更换凭据、不反复弹出二维码。
- 小看板绑定切换时不追随到别的会话。Codex 关闭时只重试原绑定，不恢复或另建会话。
- 电脑休眠/关机期间无法实时通信。看板进度同步仍需要原有公开事件采集正常运行。
- 常驻只负责本机进程可用，不保证微信服务器始终接受主动推送。

本机诊断：发送短测试文字也返回 `ret=-2 / prepare failed`；后台在运行，不能等同于登录失效。
当前会话模式在拒收或网络报错后暂停主动推送，等待新的本人消息刷新回信上下文。
所有未送出的通知类别在断开后均丢弃，恢复只自动发一条当前摘要；有效审批/选项按需查询。未确定服务端的具体
限制原因或固定有效期，不能承诺通过重启/保活永久消除拒收。
腾讯协议要求回复时带回入站上下文，但不保证缺失/旧上下文可无限主动发送：
https://github.com/Tencent/openclaw-weixin/blob/main/docs/protocol.md

## 显式安装

先构建并安装已验证版本，再生成 launchd 配置：

```sh
python3 desktop/resident-plist.py --app "$HOME/Applications/微光.app" \
  --card-dir "$HOME/Library/Application Support/AgentProgressCard" \
  --output /tmp/agent-progress-wechat.plist
```

审核配置后，将其安装到 `~/Library/LaunchAgents/io.github.chengxianhe.agentprogresscard.wechat.plist`，
用 `launchctl bootstrap gui/<当前UID> <配置路径>` 启动。不修改系统级 daemon、不嵌入 token。
用 `launchctl print gui/<当前UID>/io.github.chengxianhe.agentprogresscard.wechat` 检查状态。
停用自启用 `launchctl bootout gui/<当前UID>/io.github.chengxianhe.agentprogresscard.wechat`，
再移走该 plist；暂停微信同步仍使用小看板的停止按钮。

`resident.json` 只记录监督状态、受监督子进程标识与检查时刻，不保存微信消息或凭据。

### 内部停滞与手机自检

已启动的桥接每3秒发布工作进展，内部线程120秒没有进展会尝试受控退出；监督进程也检查自己启动的
子进程心跳，必要时先终止、40秒后仍未退出才强制结束，再按既有循环重试。手动停止、登录过期与绑定
仍优先检查；外部已运行进程仅等待，不凭任意PID接管。重启不重做回执不确定的动作。

休眠或时钟发生超过30秒跳变时预留20秒刷新心跳。微信操作自身采用固定子进程总预算（默认收件40秒、
发件20秒），超时结束等待并回收子进程，不把DNS或慢速分段读等同于正常进展。

发送“诊断”或“出门检查”可查询通信、任务、审批、采集和监督证据。后端暂不可用也保留本人本地查询，
但不会自动打开关闭的任务会话。只有新鲜且匹配本桥接的监督记录才提示正在受管；缺失证据明确提示。
以上为新版实现，不能把源码测试通过当成已安装版本的常驻或真实手机验收。

## 验证范围

完整自动验证通过：148 项 Python 测试、两个原生入口构建及 7 组原生模型测试。
本机安装用户级 LaunchAgent 后，对转发进程执行停止测试，监督进程自动恢复了 relay，凭据未改变。

未验证实际重启后的登录启动和长期睡眠/断网恢复。常驻恢复通过不代表微信消息已经送达；
微信接口拒收后由本人发一条新消息恢复推送；不通过定时重发旧上下文来保证送达。
