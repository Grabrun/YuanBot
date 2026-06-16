# 渠道 API 文档 (Channels API Docs)

> 本文档目录存放 YuanBot 支持的各种消息通道（Channel）的 API 文档。
> 用于开发通道适配器时的接口参考。

## 📖 文档索引

| 通道 | 说明 | 文档 |
|------|------|------|
| NapCat | 第三方 QQ 聊天通道实现（基于 OneBot v11 协议） | [NapCat API 文档](./napcat-api.md) |
| OpenClaw Weixin | 基于腾讯 iLink Bot API 的微信个人通道 | [OpenClaw Weixin API 文档](./openclaw-weixin-api.md) |

## 🏗️ 目录结构

```
channels-apis/
├── README.md                          # 本索引文件
├── napcat-api.md                      # NapCat API 参考文档
├── openclaw-weixin-api.md             # OpenClaw Weixin API 参考文档
└── openclaw-weixin-main/              # OpenClaw Weixin 源码
    ├── src/                           # TypeScript 源码
    ├── index.ts                       # 插件入口
    ├── package.json                   # 包配置
    └── openclaw.plugin.json           # 插件声明
```

## 📝 维护说明

- 每个通道的 API 文档应包含：架构概述、接口列表、请求/响应格式、消息段/消息类型定义、认证流程
- 文档基于上游官方文档或源码整理，更新时请注明版本和来源
- NapCat 官方文档：[https://napcat.apifox.cn](https://napcat.apifox.cn)
- OpenClaw Weixin 源码：[`@tencent-weixin/openclaw-weixin`](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin)
