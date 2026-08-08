# 识图能力

你的底层模型不具备原生识图能力。遇到图片时，**不要用 Read 工具**，改用 vision.js：

```
node vision.js "<图片路径>" "用中文描述这张图片"
```

## 触发场景

- 用户分享图片路径（本地或网络 URL）
- 消息中出现 "Saved attachments:" 并列出图片
- 用户要求分析、描述、识别图片内容

## 配置好之后

用户直接发图片，自动识图，无需手动打命令。

## 本项目配置（已就绪）

- 服务：MiniMax-M3（OpenAI 兼容），Base URL `https://api.bingshanvip.com/v1`
- Key 存于项目根目录 `.env`（已被 `.gitignore` 排除，勿提交）
- `vision.js` 内置轻量 `.env` 解析，无需 dotenv 依赖
- 支持网络图片：`node vision.js --url "https://..." "描述"`（依赖服务商能否访问目标图源，被墙域名可能超时失败，本地文件最稳）
