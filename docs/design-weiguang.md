# 微光：界面与应用身份

微光将明确绑定的 Codex 会话显示为 macOS 原生桌面卡片，可选连接本人微信。
本文记录当前显示层设计与兼容边界；使用入口见 [README](../README.md)。

## 界面层级

- 品牌头部使用光带图标与“微光”，原生标题栏也使用同一品牌。
- 任务标题与状态徽标成组展示，历史任务从菜单切换。
- 概览、过程、工具、结果各自保留原有数据来源与筛选。
- 普通待选问题使用独立卡片，编号、文字表单和回执状态保持原语义。
- 短问题按内容测量高度，长问题与表单保持可滚动；空态提供明确说明。
- 收起内容区为 380 × 360，展开为 380 × 540；AppKit 管理窗口尺寸与屏幕边界。

## 配色与图标

系统浅色使用中性灰表面；深色使用石墨灰与柔和正文，铜色只作少量点缀。
配色在 `desktop/GlimmerTheme.swift` 集中维护。已检查选定正文/次要文字与对应表面的对比，
这不代表完整 VoiceOver 或所有辅助功能验收。

`desktop/Assets/AppIcon.png` 是生成的品牌源图；来源与完整提示词见[资源说明](../desktop/Assets/README.md)。
构建使用 sips 生成原生尺寸，再由 iconutil 打包 ICNS；启动时显式设置 NSApp 的应用图标。
标题栏使用原生 titlebar accessory 的 leading 位置，在窗口按钮之后显示图标与名称。

## 系统身份与迁移

实际构建与安装包为 `微光.app`，CFBundleName 与 CFBundleDisplayName 均为“微光”。
Dock 使用该应用身份与光带图标。bundle ID、内部可执行文件名、Python 包名、窗口位置键与
Application Support 数据目录继续保留，以兼容已有任务、绑定和凭据。

旧安装路径可保留指向新名应用的固定路径符号链接，既有微信后台资源路径继续有效。
桌面快捷方式指向新应用；安装器拒绝覆盖旧名/新名应用，受控更新有哈希和进程路径核验。
进程核验显式使用可用的 UTF-8 locale，避免中文路径被 ps 转义后发生误判。
具体步骤与限制见[迁移说明](migration.md)。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `desktop/CardView.swift` | 品牌头部、连接入口、页脚和既有提示订阅 |
| `desktop/GlimmerTheme.swift` | 深浅配色、表面、状态徽标、编号按钮和问题区域测量 |
| `desktop/GlimmerTitlebarAccessory.swift` | 原生标题栏品牌 |
| `desktop/TaskDashboard.swift`、各 `*View.swift` | 任务分类、公开记录、结果与表单的显示 |
| `desktop/AgentProgressCard.swift` | 窗口入口、应用图标与菜单接线 |
| `desktop/build.sh`、`build-icon.sh` | 原生构建、元数据与 ICNS 打包 |
| `desktop/install.py`、`update.py` | 安装拒绝覆盖、受控更新与回滚包 |

显示层改版没有改变 Python 微信传输、正式审批协议、状态模型或数据格式。
普通问题仍作为本人聊天回复；正式工具授权必须来自支持的服务端请求，不能互相代替。

## 验证范围

统一入口为 `bash scripts/verify.sh`，包含 Python 回归、两个原生入口构建与 8 组模型测试。
本机源码、日志摘要、退出码和安装证据保存在忽略的 `build/verification/`。
本轮 Dock 名称与图标、柔和配色已由用户实际确认；微信后台、绑定与凭据保持兼容。

README 图片通过生产视图配合合成的惰性模型离屏渲染，不读取私人会话、启动微信服务或提交选择。
它们展示正文布局，不等同于完整真实鼠标、键盘、扫码或手机验收；模拟模型中的自动弹窗订阅关闭，
展开初始值仅用于展示。真实手机号、消息、会话标识和运行数据库不进入公开图片或提交。

未执行另需授权的 WindowTests，也不把构建/模型测试当成所有 macOS 版本、长期运行或所有手机请求已通过。
手机恢复与各协议适配的独立未验项仍见[验证记录](verification.md)。
