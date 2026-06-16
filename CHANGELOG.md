# Changelog

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
