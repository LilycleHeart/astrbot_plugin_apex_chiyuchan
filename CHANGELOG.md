# Changelog

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
