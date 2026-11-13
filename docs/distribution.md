# 微光 0.2.0 安装包与首次使用

普通使用：macOS 13+，安装 Codex 并打开目标对话。App 内置固定版本 CPython，
不依赖用户机器的 Python、Xcode 或源码目录。微信可选，仍依赖本人账号支持 iLink/ClawBot
以及当前 Codex 的本地控制接口；安装包不能替上游开放这些能力。

## 首次使用

1. 按芯片选择 arm64 / x86_64 DMG，拖入 Applications 后打开。
2. 在目标 Codex 对话发一条消息，在引导中手动选择它的一份会话记录。
   文件选择器默认打开 `~/.codex/sessions`；不知道文件时请当前助手给出路径。
3. 自动识别 UUID，输入任务名，连接后自动创建第一个任务。
4. 复制进度接入说明给同一对话。说明包含实际 App 路径、状态目录、当前任务 ID。
   公开事件自动采集；阶段状态由助手通过内置 `weiguang-cli` 显式发布。
5. 微信从卡片的可选入口扫码。手机正式请求默认关闭，需本人显式启用。
   不安装自启动，不迁移已有凭据。关闭卡片不会停止独立微信进程。

只读取所选文件，不遍历其他会话内容。不替人批准请求。切换已有任务需要确认，
旧记录保留；失败会恢复绑定、任务和历史文件。不会取消 Codex 的实际工作。

## 构建预览包

开发环境：macOS，Xcode Command Line Tools，Python 3.10+，首次下载需要网络。

```sh
bash scripts/verify.sh
python3 desktop/package.py --arch both --preview
```

输出 `dist/Weiguang-0.2.0-macos-ARCH-preview.dmg` 和 `SHA256SUMS`。
脚本拒绝覆盖同名包；需要重建时先保留旧产物。
预览包使用 ad-hoc 签名，**没有 Developer ID 或 Apple 公证**，不能当作已完成公证的公开发行。
不会提供关闭 Gatekeeper 的步骤，也不自动安装、上传或发布。

Python 来源锁定于 `desktop/runtime/python-lock.json`，使用
python-build-standalone 20261110 / CPython 3.12.16 的两个架构归档，下载必须匹配 SHA-256。
解包检查路径、链接及数量/容量。保留完整库和许可证，排除不使用的 pip/idle/pydoc/config 启动脚本。
运行时位于 App Resources；所有 Mach-O 由内到外单独签名，最后签整个 App，
不用 `--deep` 代替签名顺序。`--deep --strict` 用于最终验证。
缓存与产物忽略入 Git，许可证随 App 分发。参见 [第三方声明](../THIRD_PARTY_NOTICES.md)。

## Developer ID 与 Apple 公证

本次机器检查为 **0 个有效代码签名身份**，因此没有执行正式签名、公证或公开发布。
需要发行者本人提供 Apple Developer Program 的 Developer ID Application 证书及私钥，
并在 Keychain 中配置 notarytool 凭据配置。密码、私钥、认证文件不得提交到 Git。

准备完成后，发行者可执行以下命令；它会把构建产物提交给 Apple 公证服务：

```sh
python3 desktop/package.py --arch both --release \
  --identity 'Developer ID Application: YOUR NAME (TEAMID)' \
  --notarize-profile YOUR_KEYCHAIN_PROFILE
```

流程：校验证书 → hardened runtime + timestamp 内层签名 → App 签名 → 创建/签名 DMG →
notarytool submit/wait → 仅 Accepted 后 staple/validate → 验证 DMG → 输出无 preview 后缀的包。
尚未用真实 Developer ID 执行过这条路径；若 Apple 返回问题，按实际日志修复，不能以预览签名测试代替。

正式发布前还需从浏览器下载带 quarantine 的产物，在干净机器测试 Gatekeeper、首次引导、
更新旧版和实际业务连接。当前主机的执行验证不能替代真实 Intel 与最低 macOS 版本验收。

## 本地验收

```sh
python3 scripts/test-package.py 'build/微光.app'
```

该脚本复制到包含空格、引号、中文的路径，限制 PATH 并污染外部 Python 环境，
检查内置 SSL/SQLite、首次连接、重复连接拒绝、状态更新、watcher、worker 白名单、
应用搬迁后签名和未包含用户状态。全部使用临时合成数据，不联系真实微信。
镜像还需 `hdiutil verify`，挂载后对其中 App 执行同样检查。

升级前退出旧 App，并保留可回退副本；已有数据目录继续使用
`~/Library/Application Support/AgentProgressCard/`。不自动替换已安装的 App、操作 Dock 或启用登录项。

参考：[Python 独立运行环境](https://gregoryszorc.com/docs/python-build-standalone/main/running.html)、
[Apple 发行签名](https://developer.apple.com/documentation/xcode/creating-distribution-signed-code-for-the-mac/)、
[Apple 公证工作流](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow)。
