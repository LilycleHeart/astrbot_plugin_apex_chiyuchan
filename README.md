<h1 align="center">⚡ 小赤羽 / AstrBot Apex 数据查询插件</h1>

<p align="center">
  <b>一个专注于 Apex 英雄数据查询 · 组队 · 状态追踪 的 AstrBot 多功能插件</b>
</p>

<p align="center">
  <img src="https://count.getloli.com/@apex-chiyuchan?theme=rule34&name=apex-chiyuchan" />
</p>

<p align="center">
  <a href="https://astrbot.app"><img src="https://img.shields.io/badge/AstrBot-%3E%3D4.24-blue" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" />
  <a href="https://github.com/LilycleHeart/astrbot_plugin_apex_chiyuchan"><img src="https://img.shields.io/github/license/LilycleHeart/astrbot_plugin_apex_chiyuchan" /></a>
</p>

---

## ✨ 特性一览

### 📊 战绩查询
实时获取玩家数据并生成卡片：

- 段位 / RP / 变动趋势
- 击杀 / 伤害 / 胜场统计
- 常用英雄 TOP3
- 当前赛季徽章
- 当前传奇使用情况
- 段位分布参考

> ⚠️ 数据来源于第三方 API，可能存在延迟或缺失

---

### 🗺️ 地图轮换

- 当前匹配 / 排位地图
- 限时模式地图
- 剩余轮换时间
- 自动生成官方风格卡片

---

### 🌐 服务器状态

- EA 服务器状态
- 数据中心运行情况
- 异常 / 炸服检测

---

### 👑 猎杀 / 大师数据

- 四平台猎杀分数线
- 大师人数统计
- Moe Counter 风格可视化

---

### 👥 找队友系统 (LFG)

- 按群隔离的找队友列表
- 排位 / 娱乐两种模式
- 实时在线状态 + 30min 缓存战绩数据
- 管理员可代为注册/退出

---

### 🤖 LLM 自然语言支持

开启后可直接说：

```
看看我的战绩
现在什么地图
服务器炸了吗
大师多少分了
```

自动识别并返回结构化结果 + 卡片展示

---

## 📖 指令列表

| 指令 | 说明 |
|------|------|
| `/stats [玩家名]` | 查询战绩 |
| `/bind <玩家名> [平台]` | 绑定账号 |
| `/bind_uid <UID> [平台]` | UID 绑定 |
| `/unbind` | 解绑 |
| `/map` | 地图轮换 |
| `/server` | 服务器状态 |
| `/master` | 猎杀 / 大师数据 |
| `/lfg <排位|娱乐|列表|退出>` | 找队友 |

---

## 🖼️ 卡片预览

<p align="center">
  <img src="https://raw.githubusercontent.com/LilycleHeart/astrbot_plugin_apex_chiyuchan/master/preview/stats.png" width="45%" alt="战绩卡片" />
  <img src="https://raw.githubusercontent.com/LilycleHeart/astrbot_plugin_apex_chiyuchan/master/preview/map.png" width="45%" alt="地图卡片" />
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/LilycleHeart/astrbot_plugin_apex_chiyuchan/master/preview/master.png" width="45%" alt="猎杀/大师数据" />
  <img src="https://raw.githubusercontent.com/LilycleHeart/astrbot_plugin_apex_chiyuchan/master/preview/server.png" width="45%" alt="服务器状态" />
</p>

---

## 📦 安装

### 插件市场安装

搜索：
```
小赤羽
```

---

### 手动安装

```text
下载 ZIP 后上传至：
插件管理 → 上传插件
```

---

## ⚙️ 配置

```json
{
  "apex_api_key": "YOUR_API_KEY"
}
```

API 获取：
https://portal.apexlegendsapi.com

---

## 🔧 环境依赖

| 依赖 | 用途 |
|------|------|
| httpx | API 请求 |
| aiosqlite | 本地数据 |
| Pillow | 图片渲染 |
| playwright | 卡片渲染 |
| mcp | LLM 工具返回 |

安装浏览器内核：

```bash
python -m playwright install webkit
```

---

## 📚 数据来源

- Apex 数据：https://apexlegendsstatus.com  
- Moe Counter：https://github.com/journey-ad/Moe-Counter  
- 地图资源：https://www.ea.com/zh-hant/games/apex-legends/apex-legends/game-objects/maps-hub

---

## ⭐ 支持项目

<p align="center">
  如果觉得好用，欢迎 Star ⭐
</p>

---

## ❤️ 赞助

<p align="center">
  <img src="https://pub.mini-tools.uk/30-day/19d394f6-a896-4a2d-9716-a0d67fb8d132.jpg" width="100" style="border-radius:50%;" />
</p>

<p align="center">
  <b>感谢支持 小赤羽 / Apex 插件</b>
</p>
