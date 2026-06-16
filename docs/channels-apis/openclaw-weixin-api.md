# 腾讯 iLink Bot API (Weixin 个人通道) 参考文档

> 本文档基于 `@tencent-weixin/openclaw-weixin` 源码提取，整理了调用腾讯 iLink Bot API 实现微信个人号 Bot 所需的**底层 API 接口**，供 YuanBot 或其他 Bot 框架直接参考使用。
>
> 抛弃了 OpenClaw 插件框架层（ChannelPlugin、gateway、monitor 等），仅保留：
> - **API 端点定义**（HTTP 请求/响应格式）
> - **鉴权与登录流程**（QR 码扫码登录）
> - **消息收发协议**（文本/图片/语音/文件/视频）
> - **CDN 媒体上传与下载**（AES-128-ECB 加解密）
> - **类型定义**（请求/响应结构体、枚举值）
>
> 源码参考: `docs/channels-apis/openclaw-weixin-main/`

---

## 📋 目录

1. [概述](#-概述)
2. [基础配置](#-基础配置)
3. [QR 码登录流程](#-qr-码登录流程)
4. [iLink Bot API 接口](#-ilink-bot-api-接口)
5. [消息结构](#-消息结构)
6. [消息发送](#-消息发送)
7. [CDN 媒体上传](#-cdn-媒体上传)
8. [CDN 媒体下载与解密](#-cdn-媒体下载与解密)
9. [类型与枚举定义](#-类型与枚举定义)

---

## 🏗️ 概述

腾讯 iLink Bot API 通过 HTTP/JSON 长轮询实现微信个人号的 Bot 功能：

```
用户微信客户端  ←→  腾讯 iLink 服务器  ←→  你的 Bot 服务
                                              │
                                ┌─────────────┴─────────────┐
                                │   getUpdates (长轮询接收)    │
                                │   sendMessage (下发消息)     │
                                │   getUploadUrl + CDN (媒体) │
                                └─────────────────────────────┘
```

### 核心数据流

```
接收消息: POST getUpdates  (长轮询, 最长35s)
发送文本: POST sendMessage
发送图片/文件: POST getUploadUrl → POST CDN上传 → POST sendMessage
登录:    POST get_bot_qrcode → GET get_qrcode_status (长轮询)
```

### 媒体文件流程

```
发送:
  明文文件 → AES-128-ECB 加密 → CDN 上传 → sendMessage(含CDN引用)
接收:
  getUpdates(含CDN引用) → CDN 下载 → AES-128-ECB 解密 → 明文文件
```

---

## ⚙️ 基础配置

### API Base URL

```
PROD: https://ilinkai.weixin.qq.com
```

可根据需要在登录后切换（当服务端返回 `scaned_but_redirect` + `redirect_host` 时）。

### CDN Base URL

```
IMAGE/AUDIO/VIDEO: https://novac2c.cdn.weixin.qq.com/c2c
```

### HTTP 请求头

所有对 iLink 服务器的请求需携带以下 Headers：

| Header | 值 | 说明 |
|--------|-----|------|
| `Content-Type` | `application/json` | 固定 |
| `Authorization` | `Bearer {bot_token}` | QR 登录获取的 Bot Token |
| `AuthorizationType` | `ilink_bot_token` | 固定 |
| `iLink-App-Id` | 由腾讯分配的 App ID | 见 package.json 的 `ilink_appid` 字段 |
| `iLink-App-ClientVersion` | `0x00MMNNPP` 编码 | version 字段编码：major<<16 \| minor<<8 \| patch |
| `X-WECHAT-UIN` | 随机 base64 | 随机 uint32 → 十进制字符串 → base64 |

> 注：`iLink-App-Id` 和 `iLink-App-ClientVersion` 用于腾讯侧识别 Bot 应用，实际接入时需向腾讯申请。

### 公共请求体字段

每个 API 请求携带 `base_info`：

```json
{
  "base_info": {
    "channel_version": "x.y.z",  // 版本号
    "bot_agent": "MyBot/1.0"     // 自定义 UA 风格标识，ASCII 仅，<=256 字节
  }
}
```

### CDN 上传请求头

| Header | 值 |
|--------|-----|
| `Content-Type` | `application/octet-stream` |

CDN 上传响应通过 `x-encrypted-param` 响应头返回下载参数。

---

## 🔐 QR 码登录流程

> 流程: 获取二维码 → 展示 → 用户扫码 → 轮询确认 → 获取 Token

### 第 1 步：获取二维码

**请求**: `POST {baseUrl}/ilink/bot/get_bot_qrcode?bot_type=3`

```json
{
  "local_token_list": ["已有的token1", "已有的token2"]
}
```

| 参数 | 说明 |
|------|------|
| bot_type | query参数，固定 `3` |
| local_token_list | 本地已有的 Bot Token 列表（最多 10 个），用于服务端判重 |

**响应**:

```json
{
  "ret": 0,
  "qrcode": "a1b2c3d4...",
  "qrcode_img_content": "https://liteapp.weixin.qq.com/q/xxx?qrcode=xxx&bot_type=3"
}
```

| 字段 | 说明 |
|------|------|
| qrcode | 二维码标识（后续轮询状态用） |
| qrcode_img_content | 二维码链接（在微信中打开自动跳转，可用 qrcode 库生成图片） |

### 第 2 步：展示二维码

将 `qrcode_img_content` URL 生成 QR 码图片展示给用户。

### 第 3 步：轮询二维码状态

**请求**: `GET {baseUrl}/ilink/bot/get_qrcode_status?qrcode={qrcode}&verify_code={code}`

**参数**:

| 参数 | 必填 | 说明 |
|------|------|------|
| qrcode | 是 | 第 1 步返回的 qrcode |
| verify_code | 否 | 配对码（当返回 `need_verifycode` 时用户输入） |

**超时**: 建议 35 秒客户端超时，超时后应重试轮询。

**状态跳转**:

```
  wait ───→ scaned ───→ confirmed (成功 🎉)
    │                     │
    ├──→ expired          └──→ 返回 bot_token + ilink_bot_id
    ├──→ need_verifycode  → 用户输入数字 → 继续轮询
    ├──→ verify_code_blocked → 重新获取二维码
    ├──→ scaned_but_redirect → 切换到 redirect_host
    └──→ binded_redirect → 已绑定，无需重复登录
```

**成功响应 (status=`confirmed`)**:

```json
{
  "status": "confirmed",
  "bot_token": "xxx@im.bot:xxxxx",
  "ilink_bot_id": "hex@im.bot",
  "ilink_user_id": "hex@im.wechat",
  "baseurl": "https://ilinkai.weixin.qq.com"
}
```

| 字段 | 说明 |
|------|------|
| bot_token | **Bot Token**，后续 API 请求的 `Authorization: Bearer {token}` |
| ilink_bot_id | Bot ID，格式 `{hex}@im.bot` |
| ilink_user_id | 扫码者的微信用户 ID，格式 `{hex}@im.wechat` |
| baseurl | 后续 API 的基础 URL |

**其他状态**:

```json
{ "status": "wait" }              // 等待扫码
{ "status": "scaned" }            // 已扫码
{ "status": "need_verifycode" }   // 需要配对码
{ "status": "expired" }           // 二维码过期
{ "status": "scaned_but_redirect", "redirect_host": "newhost.com" }  // 重定向
{ "status": "binded_redirect" }   // 已绑定
```

### 第 4 步（可选）：刷新二维码

当二维码过期（`expired`）或验证码被锁定（`verify_code_blocked`），重新调用第 1 步获取新二维码。最多可刷新 3 次。

### 超时

- 单次轮询超时：35 秒（长轮询）
- 总登录超时：480 秒（8 分钟）

---

## 🌐 iLink Bot API 接口

### 1️⃣ 消息获取: getUpdates

**请求**: `POST {baseUrl}/ilink/bot/getupdates`

**说明**: 长轮询获取新消息。服务器保持连接直到有新消息或超时。没有消息时返回空数组。

```json
{
  "get_updates_buf": "",
  "base_info": {}
}
```

| 参数 | 说明 |
|------|------|
| get_updates_buf | 同步游标。首次请求传空字符串 `""`，之后传上次响应返回的值。需持久化保存，服务重启后恢复。 |

**响应**:

```json
{
  "ret": 0,
  "errcode": 0,
  "errmsg": "",
  "msgs": [],
  "get_updates_buf": "base64-string",
  "longpolling_timeout_ms": 35000
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| ret | number | 返回码，0=成功 |
| errcode | number | 错误码，`-14`=会话过期 |
| errmsg | string | 错误消息 |
| msgs | WeixinMessage[] | 消息列表（见下方消息结构） |
| get_updates_buf | string | **新的同步游标**，必须持久化并在下次请求时传回 |
| longpolling_timeout_ms | number | 服务端建议的下次轮询超时 |

**错误处理**:
- `errcode=-14` → 会话过期，暂停 Bot 1 小时后重试
- 网络超时 → 返回空 `{ret:0}`，重试
- 连续失败 3 次 → 退避 30 秒

**客户端超时**: 建议 35 秒。超时后返回空响应，非中止信号时应继续轮询。

---

### 2️⃣ 发送消息: sendMessage

**请求**: `POST {baseUrl}/ilink/bot/sendmessage`

**说明**: 下发消息到用户。

```json
{
  "msg": { /* WeixinMessage */ },
  "base_info": {}
}
```

消息体见下方「消息结构」和「消息发送」章节。

---

### 3️⃣ 获取 CDN 上传 URL: getUploadUrl

**请求**: `POST {baseUrl}/ilink/bot/getuploadurl`

**说明**: 获取预签名的 CDN 上传 URL，用于发送媒体文件前。

```json
{
  "filekey": "32-char-hex-string",
  "media_type": 1,
  "to_user_id": "xxx@im.wechat",
  "rawsize": 12345,
  "rawfilemd5": "hex-md5-of-plaintext",
  "filesize": 12400,
  "thumb_rawsize": 5000,
  "thumb_rawfilemd5": "hex-md5-of-thumb",
  "thumb_filesize": 5050,
  "no_need_thumb": true,
  "aeskey": "aes-key-in-hex-32-chars",
  "base_info": {}
}
```

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| filekey | 是 | string | 文件密钥，32 位随机 hex |
| media_type | 是 | number | 1=图片, 2=视频, 3=文件, 4=语音 |
| to_user_id | 是 | string | 目标用户 ID |
| rawsize | 是 | number | 原文件明文大小（字节） |
| rawfilemd5 | 是 | string | 原文件明文 MD5（hex） |
| filesize | 是 | number | AES-128-ECB 加密后的文件大小 |
| thumb_rawsize | 图片/视频 | number | 缩略图明文大小 |
| thumb_rawfilemd5 | 图片/视频 | string | 缩略图明文 MD5 |
| thumb_filesize | 图片/视频 | number | 缩略图密文大小 |
| no_need_thumb | 否 | boolean | 不需要缩略图上传 URL |
| aeskey | 是 | string | AES 密钥（hex 编码，32 字符 = 16 字节） |

**响应**:

```json
{
  "upload_param": "base64-encrypted-param",
  "thumb_upload_param": "",
  "upload_full_url": "https://cdn-url"
}
```

| 字段 | 说明 |
|------|------|
| upload_param | 原图上传加密参数（构建 CDN 上传 URL 用） |
| thumb_upload_param | 缩略图上传加密参数 |
| upload_full_url | **优先使用的完整上传 URL**（有此字段时优先使用，比 upload_param 更可靠） |

---

### 4️⃣ 获取 Bot 配置: getConfig

**请求**: `POST {baseUrl}/ilink/bot/getconfig`

```json
{
  "ilink_user_id": "xxx@im.wechat",
  "context_token": "context-token-from-getupdates",
  "base_info": {}
}
```

**响应**:

```json
{
  "ret": 0,
  "errmsg": "",
  "typing_ticket": "base64-string"
}
```

| 字段 | 说明 |
|------|------|
| typing_ticket | 用于发送输入状态的 Ticket（24h 缓存，按 userId 粒度） |

---

### 5️⃣ 发送输入状态: sendTyping

**请求**: `POST {baseUrl}/ilink/bot/sendtyping`

```json
{
  "ilink_user_id": "xxx@im.wechat",
  "typing_ticket": "ticket-from-getconfig",
  "status": 1
}
```

| 参数 | 说明 |
|------|------|
| typing_ticket | 从 getConfig 获取 |
| status | 1=typing, 2=cancel typing |

---

### 6️⃣ 通知上线: notifyStart

**请求**: `POST {baseUrl}/ilink/bot/msg/notifystart`

```json
{ "base_info": {} }
```

通知服务器 Bot 开始监听，建议在启动长轮询前调用。失败可忽略。

---

### 7️⃣ 通知下线: notifyStop

**请求**: `POST {baseUrl}/ilink/bot/msg/notifystop`

```json
{ "base_info": {} }
```

通知服务器 Bot 停止监听，建议在关闭连接时调用。失败可忽略。

---

## 📦 消息结构

### 消息类型枚举

```
MessageType.NONE = 0
MessageType.USER = 1    // 用户消息(入站)
MessageType.BOT  = 2    // Bot消息(出站)
```

### 消息状态枚举

```
MessageState.NEW        = 0   // 新建
MessageState.GENERATING = 1   // 生成中
MessageState.FINISH     = 2   // 完成
```

### 消息段类型枚举

```
MessageItemType.NONE  = 0
MessageItemType.TEXT  = 1   // 文本
MessageItemType.IMAGE = 2   // 图片
MessageItemType.VOICE = 3   // 语音
MessageItemType.FILE  = 4   // 文件
MessageItemType.VIDEO = 5   // 视频
```

### WeixinMessage（完整消息）

```json
{
  "seq": 1,
  "message_id": 123456,
  "from_user_id": "xxx@im.wechat",
  "to_user_id": "yyy@im.wechat",
  "client_id": "unique-client-id",
  "create_time_ms": 1700000000000,
  "update_time_ms": 1700000001000,
  "session_id": "session-id",
  "group_id": "group-id",
  "message_type": 1,
  "message_state": 2,
  "item_list": [],
  "context_token": "context-token"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| seq | number | 序号 |
| message_id | number | 消息 ID |
| from_user_id | string | 发送者 ID，格式 `hex@im.wechat` |
| to_user_id | string | 接收者 ID |
| client_id | string | 客户端唯一 ID（出站时生成） |
| create_time_ms | number | 创建时间戳（毫秒） |
| message_type | number | 1=用户消息, 2=Bot消息 |
| message_state | number | 0=新建, 1=生成中, 2=完成（入站消息只处理 FINISH=2） |
| item_list | MessageItem[] | 消息段列表 |
| context_token | string | **上下文 Token**，收到消息后必须保存，**出站消息必须回传** |
| group_id | string | 群 ID（当前仅私聊，此字段可能为空） |

### MessageItem（消息段）

```json
{
  "type": 1,
  "msg_id": "msg-item-id",
  "create_time_ms": 1700000000000,
  "is_completed": true,
  "ref_msg": { /* RefMessage */ },
  "text_item": { "text": "你好" },
  "image_item": { /* ImageItem */ },
  "voice_item": { /* VoiceItem */ },
  "file_item": { /* FileItem */ },
  "video_item": { /* VideoItem */ }
}
```

### TextItem (type=1)

```json
{ "text": "消息文本" }
```

### ImageItem (type=2)

```json
{
  "media": {
    "encrypt_query_param": "base64-encrypted-param",
    "aes_key": "base64-aes-key",
    "encrypt_type": 1,
    "full_url": "https://cdn-url"
  },
  "thumb_media": {
    "encrypt_query_param": "...",
    "aes_key": "..."
  },
  "aeskey": "hex-aes-key-32-chars",
  "url": "https://...",
  "mid_size": 12345,
  "hd_size": 23456
}
```

| 字段 | 说明 |
|------|------|
| media | 原图 CDN 引用 |
| thumb_media | 缩略图 CDN 引用 |
| aeskey | AES 密钥（hex，16 字节，入站解密时优先使用） |
| url | 图片 URL（可选） |
| mid_size | 原图密文大小（字节），出站时填加密后大小 |
| hd_size | 高清图大小 |

### VoiceItem (type=3)

```json
{
  "media": {
    "encrypt_query_param": "...",
    "aes_key": "base64-aes-key",
    "full_url": "https://..."
  },
  "encode_type": 6,
  "playtime": 3000,
  "text": "语音转文字结果"
}
```

| 字段 | 说明 |
|------|------|
| encode_type | 编码：1=pcm, 2=adpcm, 3=feature, 4=speex, 5=amr, **6=silk**, 7=mp3, 8=ogg-speex |
| text | 语音转文字内容（如有则直接作为消息文本） |

### FileItem (type=4)

```json
{
  "media": {
    "encrypt_query_param": "...",
    "aes_key": "base64-aes-key",
    "full_url": "https://..."
  },
  "file_name": "document.pdf",
  "md5": "file-md5",
  "len": "12345"
}
```

### VideoItem (type=5)

```json
{
  "media": {
    "encrypt_query_param": "...",
    "aes_key": "base64-aes-key",
    "full_url": "https://..."
  },
  "video_size": 1234567,
  "play_length": 30,
  "video_md5": "md5-hex",
  "thumb_media": { "encrypt_query_param": "...", "aes_key": "..." }
}
```

### CDNMedia（CDN 媒体引用）

```json
{
  "encrypt_query_param": "加密参数（CDN下载用）",
  "aes_key": "AES密钥（base64）",
  "encrypt_type": 1,
  "full_url": "完整下载URL"
}
```

> `encrypt_type=0` 只加密 fileid，`encrypt_type=1` 打包缩略图/中图等信息。
> `full_url` 优先于 `encrypt_query_param` 使用。

### RefMessage（引用消息）

```json
{
  "message_item": { /* MessageItem */ },
  "title": "消息摘要"
}
```

---

## ✉️ 消息发送

### 发送文本消息

**流程**: 直接调用 `sendMessage`

```json
{
  "msg": {
    "from_user_id": "",
    "to_user_id": "recipient@im.wechat",
    "client_id": "unique-id",
    "message_type": 2,
    "message_state": 2,
    "item_list": [
      {
        "type": 1,
        "text_item": { "text": "你好！" }
      }
    ],
    "context_token": "token-from-inbound-message"
  },
  "base_info": {}
}
```

### 发送图片消息

**流程**: `getUploadUrl` → **CDN 上传加密文件** → `sendMessage`（含 CDN 引用）

步骤 1: 调用 `getUploadUrl`（见 API 接口 3️⃣）

步骤 2: CDN 上传（使用 `upload_full_url` 或 `upload_param` 构建 URL）

步骤 3: `sendMessage`:

```json
{
  "msg": {
    "from_user_id": "",
    "to_user_id": "recipient@im.wechat",
    "client_id": "unique-id",
    "message_type": 2,
    "message_state": 2,
    "item_list": [
      {
        "type": 2,
        "image_item": {
          "media": {
            "encrypt_query_param": "cdn返回的x-encrypted-param",
            "aes_key": "base64-of-aes-key",
            "encrypt_type": 1
          },
          "mid_size": 12400
        }
      }
    ],
    "context_token": "token-from-inbound"
  }
}
```

### 发送视频消息

**流程**: 同图片，但 `media_type=2`，使用 `video_item`：

```json
{
  "item_list": [{
    "type": 5,
    "video_item": {
      "media": {
        "encrypt_query_param": "...",
        "aes_key": "base64-aes-key",
        "encrypt_type": 1
      },
      "video_size": 1234567
    }
  }]
}
```

### 发送文件消息

**流程**: 同图片，但 `media_type=3`，使用 `file_item`：

```json
{
  "item_list": [{
    "type": 4,
    "file_item": {
      "media": {
        "encrypt_query_param": "...",
        "aes_key": "base64-aes-key",
        "encrypt_type": 1
      },
      "file_name": "document.pdf",
      "len": "12345"
    }
  }]
}
```

### 文本+媒体组合

可先发一个 TEXT 消息段，再跟一个媒体消息段，但建议**分两次 sendMessage 调用**（每个 item_list 只放一个段）以保证兼容性。

### contextToken 管理

- **入站**: 从 `getUpdates` 的 `context_token` 字段获取
- **出站**: 必须回传该 token 到 `msg.context_token` 字段
- **持久化**: token 按 `(accountId, userId)` 键值对存储，需在重启后恢复

---

## ☁️ CDN 媒体上传

### 完整上传流程

```
1. 读取文件 → 计算明文 size + MD5
2. 生成 16 字节随机 AES 密钥 (filekey) + 16 字节随机 AES 密钥 (aeskey)
3. 调用 getUploadUrl 获取上传 URL
4. AES-128-ECB 加密文件（PKCS7 填充）
5. POST 加密数据到 CDN URL
6. 从响应头 x-encrypted-param 获取下载参数
```

### AES-128-ECB 加密

**加密算法**: AES-128-ECB，PKCS7 填充

**填充后大小计算**:
```
paddedSize = rawSize + (16 - (rawSize % 16))  // PKCS7 对齐到 16 字节
```

**密钥生成**: `crypto.randomBytes(16)` → 32 位 hex 字符串

### CDN 上传请求

```
POST {cdn_url}
Content-Type: application/octet-stream

{AES-128-ECB 加密后的二进制数据}
```

**成功响应 Headers**:
```
x-encrypted-param: {下载加密参数}
```

> `cdn_url` 优先使用 `getUploadUrl` 返回的 `upload_full_url`（完整 URL）。
> 当没有 `upload_full_url` 时，用 `upload_param` + `filekey` 构建：
> ```
> buildCdnUploadUrl(cdnBaseUrl, uploadParam, filekey) → string
> ```

**重试**: CDN 上传建议最多重试 3 次
- 服务端错误 (5xx)：重试
- 客户端错误 (4xx)：直接抛出，不重试

### CDN 上传工具（参考实现）

```typescript
// 伪代码
async function uploadToCdn(plaintext, aeskey, uploadFullUrl, uploadParam, filekey, cdnBaseUrl) {
  const ciphertext = aesEcbEncrypt(plaintext, aeskey);
  const url = uploadFullUrl || buildCdnUrl(cdnBaseUrl, uploadParam, filekey);
  
  for (let retry = 1; retry <= 3; retry++) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: ciphertext,
    });
    if (res.status >= 400 && res.status < 500) throw new Error('client error');
    if (res.status === 200) {
      return res.headers.get('x-encrypted-param');
    }
  }
}
```

---

## 🔓 CDN 媒体下载与解密

### 下载解密流程

```
1. 从消息中提取 CDNMedia (encrypt_query_param + aes_key + full_url)
2. 解析 aes_key（支持两种编码）
3. 从 CDN 下载加密数据
4. AES-128-ECB 解密 → 得到明文文件数据
```

### AES 密钥解析

`aes_key` 字段有两种编码方式，需自动检测：

**方式 1**: base64(16 字节原始密钥)
- 解码后直接得到 16 字节 AES 密钥
- 常见于图片消息

**方式 2**: base64(32 字符 hex 字符串)
- 先 base64 解码得到 32 字节 ASCII 字符串
- 再将 32 字符 hex 解析为 16 字节密钥
- 常见于文件/语音/视频消息

```python
# Python 参考实现
def parse_aes_key(aes_key_b64: str) -> bytes:
    decoded = base64.b64decode(aes_key_b64)
    if len(decoded) == 16:
        return decoded  # 方式1：直接16字节密钥
    if len(decoded) == 32 and all(c in '0123456789abcdefABCDEF' for c in decoded.decode()):
        return bytes.fromhex(decoded.decode())  # 方式2：hex转16字节
    raise ValueError(f"Invalid aes_key length: {len(decoded)}")
```

### CDN 下载

```python
# Python 参考实现
def download_cdn_file(encrypt_query_param: str, cdn_base_url: str, full_url: str = None) -> bytes:
    url = full_url or build_cdn_download_url(encrypt_query_param, cdn_base_url)
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.content  # AES-128-ECB 加密数据
```

### AES-128-ECB 解密

```python
from Crypto.Cipher import AES

def aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_ECB)
    plaintext = cipher.decrypt(ciphertext)
    # 移除 PKCS7 填充
    pad_len = plaintext[-1]
    return plaintext[:-pad_len]
```

### 语音文件特殊处理

下载解密后的语音数据为 **SILK** 编码（`encode_type=6`），如需播放需转码为 WAV：

```
SILK → SILK解码器 → WAV
```

或直接保存为 `.silk` 文件（部分播放器支持）。

---

## 🔣 类型与枚举定义

### 上传媒体类型

| 常量 | 值 | 说明 |
|------|-----|------|
| `IMAGE` | 1 | 图片 |
| `VIDEO` | 2 | 视频 |
| `FILE` | 3 | 文件附件 |
| `VOICE` | 4 | 语音 |

### 消息类型

| 常量 | 值 | 说明 |
|------|-----|------|
| `NONE` | 0 | 无 |
| `USER` | 1 | 用户消息（入站） |
| `BOT` | 2 | Bot 消息（出站） |

### 消息段类型

| 常量 | 值 | 说明 |
|------|-----|------|
| `NONE` | 0 | 无 |
| `TEXT` | 1 | 文本 |
| `IMAGE` | 2 | 图片 |
| `VOICE` | 3 | 语音 |
| `FILE` | 4 | 文件 |
| `VIDEO` | 5 | 视频 |

### 消息状态

| 常量 | 值 | 说明 |
|------|-----|------|
| `NEW` | 0 | 新建 |
| `GENERATING` | 1 | 生成中 |
| `FINISH` | 2 | 完成（只处理此状态的消息） |

### 输入状态

| 常量 | 值 | 说明 |
|------|-----|------|
| `TYPING` | 1 | 正在输入 |
| `CANCEL` | 2 | 取消输入 |

### 语音编码类型

| 值 | 说明 |
|-----|------|
| 1 | PCM |
| 2 | ADPCM |
| 3 | Feature |
| 4 | Speex |
| 5 | AMR |
| **6** | **SILK**（微信语音常用） |
| 7 | MP3 |
| 8 | OGG-Speex |

### QR 登录状态

| 值 | 说明 |
|-----|------|
| `wait` | 等待扫码 |
| `scaned` | 已扫码，等待确认 |
| `confirmed` | ✅ 已确认，登录成功 |
| `expired` | 二维码过期 |
| `scaned_but_redirect` | 已扫码，需切换到新的服务器 |
| `need_verifycode` | 需要输入配对码 |
| `verify_code_blocked` | 验证码多次错误 |
| `binded_redirect` | 已绑定到该实例 |

### 错误码

| errcode | 说明 |
|---------|------|
| 0 | 成功 |
| -14 | 会话过期，需要暂停 Bot 1 小时 |

---

## 📝 实现要点总结

### 启动流程

1. 加载持久化的 `get_updates_buf`（无则空字符串）
2. 调用 `notifyStart`（可选，失败可忽略）
3. 进入 `getUpdates` 长轮询循环
4. 每次成功轮询后持久化新的 `get_updates_buf`

### contextToken 管理

- 收到消息时提取 `context_token`
- 按 `(bot_account_id, from_user_id)` 键存储
- 重启后需恢复（磁盘持久化）
- 出站消息时回传

### 会话过期处理

- `getUpdates` 返回 `errcode=-14` → **暂停 Bot 1 小时**
- 暂停期间所有 API 调用应抛出异常
- 1 小时后自动恢复

### 重试策略

| 场景 | 行为 |
|------|------|
| getUpdates 超时 | 重试 |
| getUpdates 单次失败 | 2 秒后重试 |
| getUpdates 连续失败 3 次 | 退避 30 秒后重置计数器 |
| CDN 上传 5xx | 重试最多 3 次 |
| CDN 上传 4xx | 立即失败 |
| getConfig 失败 | 指数退避 2s→4s→8s→...→1h |

### 关键区别：入站 vs 出站

| 场景 | message_type | 方向 |
|------|-------------|------|
| 用户发给 Bot | `1` (USER) | 从 getUpdates 接收 |
| Bot 回复用户 | `2` (BOT) | 通过 sendMessage 发送 |

---

> **文档版本**: 基于 `@tencent-weixin/openclaw-weixin` v2.x 源码提取
> **源码位置**: `docs/channels-apis/openclaw-weixin-main/`
> **协议归属**: 腾讯 iLink Bot API（非标准 HTTP 协议，非 OneBot 协议）
