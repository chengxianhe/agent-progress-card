# 微光应用图标

`AppIcon.png` 是微光的源图标，带透明圆角外边缘。由本会话内置 imagegen 工具于 2026-11-13 生成，
以用户选定的“微光”暖橙光带概念为参考；未使用第三方品牌标识。原有 LICENSE / NOTICE 保留。
这是产品品牌资源，非用户数据。原始生成图为 1254 × 1254 RGBA PNG。

`desktop/build-icon.sh` 使用 macOS 自带 `sips` 生成 16–1024 像素图标，再由 `iconutil` 打包为
`AppIcon.icns`；源 PNG 同时进入应用 Resources，用于窗口内的品牌标识。

## 生成提示词（内置工具，单张参考图）

> Create the FINAL production macOS application icon for the chosen app 微光, based on the RIGHT-hand warm orange icon in the reference comparison board. The reference is design direction only: output a SINGLE icon, no board, no UI, no text, no labels, no variants. Square 1024x1024 composition. A beautifully polished warm burnt-orange/copper macOS rounded square tile centered with a consistent small transparent outer margin of about 5%. Within the tile one simple creamy ivory softly sculpted folded ribbon rising diagonally, ending near a single small warm glowing point, evoking a tiny guiding light. Preserve the reference right-hand icon's distinctive broad flowing folded ribbon and calm premium visual weight. Refined 3D depth and soft edge lighting, mostly matte/subtly satiny, no busy texture. Rich amber upper portion gently transitioning to deeper terracotta lower portion. Clear strong silhouette that works at 16px and 32px. Keep all motif comfortably inside the tile. Truly transparent outside the rounded tile, including softly transparent subtle shadow; NOT white corners, NO checkerboard graphic. No letters, no stars, no robot, no existing brand symbols. This is a shippable native Mac app icon asset, centered and symmetrically balanced in the square canvas.

工具生成时指定透明背景。生成器输出尺寸与提示目标略有差异；构建流程按原生图标规格转换，未手工重绘。
