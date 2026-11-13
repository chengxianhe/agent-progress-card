# 从旧小看板迁移

此仓库是独立源码工程，包名改为 `agent_progress_card` / `agent_progress_wechat`，
应用 bundle ID 改为 `io.github.chengxianhe.agentprogresscard`。旧演示引擎、网页、模型适配器与 MCP 演示不在其中。
旧源码仓库和已安装程序不会因下载本仓库自动改变。

状态目录仍为 `~/Library/Application Support/AgentProgressCard`，以兼容已有任务历史和绑定格式。
不要同时启动旧版与新版采集器；切换应用前先退出旧版，并保留旧 App 和状态目录副本。
现有 `desktop/install.py` 拒绝覆盖旧 App；受控替换可参考 `python3 desktop/update.py --help`，
需要核对旧 App 哈希和进程路径，会保留回滚包。

微信状态目录可能还在原 checkout 下。此次源码拆分不复制或移动凭据，不切换运行中的 relay。
若需要迁移，先停止旧 relay，再由用户明确选择复用原状态目录或在新目录重新扫码；
同一状态目录不能运行两个 relay。新入口是 `python3 -m agent_progress_wechat.relay`。

原有脚本中的 `min_agent_desktop` / `min_agent_wechat` 导入和 `python -m` 名称需改成新包名。
新仓库不提供旧包名别名，避免意外从原 checkout 加载代码。

## 微光应用包名称

新构建输出为 `build/微光.app`，安装到 `~/Applications/微光.app`；bundle ID、内部可执行文件名、
Python 包名与 Application Support 目录保持。新版启动时显式设置 Dock 图标。
安装器遇到任何新名/旧名应用都会拒绝覆盖，旧名迁移需要受控备份与退出旧桌面采集器后再操作。

旧名 `~/Applications/AgentProgressCard.app` 可保留为指向 `微光.app` 的固定路径符号链接，
使既有微信常驻 PYTHONPATH 继续有效。迁移时需先核对两版 Python 资源完全一致，
备份旧 App 和本机状态，核对绑定、凭据不变，避免将后台服务切到不同协议实现。
桌面快捷方式指向新名应用；受控更新应只更新新名实际包，保留兼容链接。
系统登记仅刷新这一个新名应用，不重置全部 LaunchServices 或其它 Dock 项。
