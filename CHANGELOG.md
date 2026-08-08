# Changelog

## 未发布

### 🐛 修复
- 修复赛季卡片时区：赛季日期数据源为 UTC（Apex 更新惯例 17:00 UTC），抓取时转换为北京时间，结束日期与倒计时修正（08-04 → 08-05）

## v1.4.0 (2026-06-24)

### ✨ 新功能
- **赛季信息卡**: `/season` 命令，展示当前赛季名称、分区、倒计时、META 胜率 Top 6
- **`apex_season` LLM 工具**: 用户询问赛季信息时自动触发
- **赛季数据爬取**: `season_scraper.py` 从 esportstales 获取赛季日期，ALS 获取 META 英雄胜率/选取率
- **北京时区明暗主题**: 所有卡片（除战绩/个人资料）根据北京时间 06:00-18:00 自动切换亮色/暗色主题
- **混合模式（Mixtape）地图轮换**: 支持区域控制、团队死斗、枪械升级赛、移动据点争夺模式
- **外卡（Wildcard）地图轮换**: 支持外卡模式地图显示

### 🔧 优化
- **Playwright 强制渲染**: 所有卡片通过 Playwright HTML→PNG 渲染，移除所有 Pillow 渲染器
- **Playwright 失败降级**: 渲染失败时返回 `None`，调用方降级为纯文本消息
- **`device_scale_factor=3`**: 所有卡片统一 3x DPR 渲染，文字更清晰
- **ALS 国旗图标**: 服务器状态卡片使用 ALS 自带 `flag-icon.min.css` 显示国旗
- **猎杀者分数线 24h 变动**: 展示各平台猎杀者分数线 24 小时内涨跌（▲/▼/—）
- **混合模式地图名汉化**: 区域控制、团队死斗等模式名称使用官方简体中文翻译
- **地图轮换时间戳**: 使用 API 返回的真实开始/结束时间，不再仅依赖倒计时估算

### 🐛 修复
- 修复 LFG 卡片 HTML 重复 footer 块导致 SyntaxError (`·` 字符)
- 修复 `_latency_color()` 对 "100% up" 误判为高延迟
- 修复 steamcharts 卡片 `emulate_media("dark")` 强制深色导致亮色主题失效
- 修复 steamcharts JS `isDark` 变量从 `matchMedia` 改为 `body.classList` 检测
- 修复 `draw_player_list_card` 硬编码深色配色，改为根据北京时间动态切换
- 修复 `device_scale_factor` 参数被忽略：`run_with_page()` 传入的 df 值从未应用到浏览器 context，所有截图实际为 1x 分辨率

### 🗑️ 移除
- 移除所有 Pillow 渲染器（`draw_text_card` 等），保留仅 Moe Counter GIF 帧处理
- 移除 `config.py` 中的字体加载逻辑（`preload_fonts` 改为空操作）
- 移除 `emulate_media(color_scheme="dark")` 强制深色

---

## v1.3.0 (2026-06-22)

### ✨ 新功能
- **Steam 日活卡片**: `/online`（别名 `在线`/`在线人数`/`日活`）命令，展示 Apex Steam 当前在线人数、24 小时峰值、历史峰值
- **7 日在线趋势图**: 卡片含 Chart.js 折线图，展示最近 7 天在线人数趋势（约 169 个数据点），支持深色/浅色主题
- **`apex_online` LLM 工具**: 用户询问在线人数/日活/活跃玩家数时自动触发，返回卡片 + 文本摘要
- **Jinja2 模板渲染**: 新增 `steamcharts_template.jinja` MD3 模板，Material Design 3 风格，绿色 primary 配色
- **等级行重新设计**: 移除大数字 `1601`，改为 ALS 风格等级图标 + 红色渐变等级数字 + 进度条 + `% to next` 副标签
- **等级图标修复**: 从 ALS `/core/level_badge/?level={total}` 下载 SVG，MIME 类型自动检测，User-Agent + Referer 头绕过 ALS 反爬

### 🔧 优化
- **MD3 搜索列表卡片**: Diamond 主题配色，圆角 24px，描边边框，平台图标着色
- **特殊勋章改为纯图标**: 去掉名称文字，40px 圆形容器内 28px 图标
- **赛季徽章尺寸加大**: 36×36（原 28×28）
- **图片下载改进**: 移除 `@lru_cache`（避免永久缓存失败值），增加 User-Agent/Referer 头，内容嗅探 MIME 类型（SVG/PNG/JPEG/WebP/GIF）
- **下载失败日志**: `_download_sync` 失败时输出 warning 日志便于排查
- **卡片外背景透明**: Steamcharts 卡片 `body` 改为 `transparent`，配合 `omit_background=True` 截图

### 🐛 修复
- 修复等级图标不显示：`_download_sync` 的 `@lru_cache` 永久缓存 `None` 失败值导致重试无效
- 修复 SVG 内容被标记为 `image/png` MIME 类型导致部分浏览器不渲染
- 修复 `image_renderer` 未 re-export `draw_steamcharts_card` 导致 `/online` 命令报 `AttributeError`

---

## v1.2.0 (2026-06-16)

### ✨ 新功能
- **LFG 找队友**: `/lfg 排位|娱乐|列表|退出`，按群隔离，卡片展示在线状态及战绩
- **管理员代操作**: 命令加 `@目标` 可为他人 bind/unbind/lfg，LLM 工具加 `target_qq` 参数
- **ALS 实时爬取**: 排名/击杀/等级数据每次实时从 ALS 抓取（`force=True`）
- **DB 媒体缓存**: 赛季/特殊徽章永久存 `badge_cache` 表，仅首次爬取
- **rankTopPct/rankPcPos DOM 提取**: 从 `.v2-sb-stat__pill--rank/top` 直接提取，不再用分布估算
- **段位分布参考**: 卡片底部展示各段位人数分布（全平台）
- **LVL 计算**: `P3 100` 合并显示为 `1600`（prestige × 500 + level）
- **LFG 列表 DB 缓存**: kills/level/prestige/rank 等静态数据 30min 缓存，在线状态始终实时
- **`/stats @某人`**: 解析 CQ 码查对方绑定账号战绩

### 🔧 优化
- **排名编号优先级**: `rankPcPos`(ALS DOM) > `rankPos`(ALS text) > `rank_ladder_pos`(API)
- **Top% 标签按平台**: 非大师/猎杀显示 `Top (PC/PS/Xbox)`，大师/猎杀显示 `Top (全平台)`
- **SLOW 不再推送**: 服务器监控仅对 DOWN/UNSTABLE 推送
- **段位分布标签加 `(全平台)`** 注释
- **`use_local_fonts` 配置**: 开启时跳过 CDN 字体
- **水印居中**: `auth.赤羽真白 · Apex Chiyuchan` 始终在 footer 居中
- **LLM 工具收紧**: `apex_stats` 描述防"介绍我/评价我"误触发
- **LFG 爬虫**: 优先用 `users` 表 UID 避免消歧页，消歧页自动重定向到 `/profile/uid/`
- **LFG 注册降级**: 纯文本消息确认，不渲染卡片

### 🗑️ 移除
- 移除 `/team` 组队系统（-313 行）

### 🐛 修复
- 修复大师/猎杀不显示 I-IV 分段号
- 修复 `_calc_global_pct` 对 Predator/Master 返回空字符串
- 修复排名卡片重复显示 Top% 的问题
- 修复 `image_renderer.py` 缩进错误
- 修复 LLM `apex_lfg` handler 缩进错误

---

## v1.1.0 (2026-05-21)

### ✨ 新功能
- **服务器状态监控**: `/monitor on|off|status` 命令，每 15 分钟后台检测 ALS 服务器状态，异常时自动推送卡片
- **服务器状态汉化**: 所有服务区块名、状态文本、footer 均已汉化为中文
- **异常颜色调整**: UNSTABLE/SLOW 改为琥珀色 (#FFA500 / #FFB347)，DOWN 改为红色 (#FF4444)，UP 保持绿色 (#4CE5B1)
- **可配置监控间隔**: 通过插件配置 `monitor_interval` 自定义检测周期（默认 900 秒）
- **DOWN 状态支持**: 检测逻辑和卡片渲染均支持 DOWN 状态（红色高亮）
- **Section 异常覆盖**: 当服务区块整体异常时，其下所有条目统一使用警告色，不再保留绿色

### 🔧 优化
- **ALS 抓取替代 API**: 服务器状态数据源从 mozambiquehe.re API 替换为 ALS 网站抓取，数据更准确、无 403 问题
- **项目改名**: 仓库/目录名从 `astrbot-plugin-apex-chiyuchan` 改为 `astrbot_plugin_apex_chiyuchan`
- **导入路径修复**: `MessageChain` 改用 `astrbot.api.event` 导入，兼容 AstrBot v4.24.5
- **日志增强**: 监控循环、状态切换、推送均有 INFO 级别日志输出
- **双推防护**: `update_monitor_state` 在 `send_message` 前执行，防止状态切换推送两次
- **渲染/发送分离**: 卡片渲染失败时仅发纯文本，不会出现卡片+重复文本两条消息

### 🐛 修复
- 修复 `_detect_als_state` 只查 UNSTABLE 不查 SLOW/DOWN 的问题
- 修复 `_locale_status` 键大小写不匹配导致 pill 状态未汉化的问题
- 修复 entry 级状态检测 `"unstable" in entry.status.upper()` 永远 False 的 bug
- 修复初始异常未推送的问题
