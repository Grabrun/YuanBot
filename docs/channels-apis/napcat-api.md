# NapCat API 参考文档

> NapCat 是一个第三方 QQ 聊天通道实现，基于 OneBot v11 (OB11) 协议。
> 所有 API 均为 HTTP POST 请求，Content-Type: `application/json`。
>
> 官方文档：[https://napcat.apifox.cn](https://napcat.apifox.cn)
> 协议版本：OB11 + NapCat 扩展

---

## 📋 目录

1. [基础响应格式](#-基础响应格式)
2. [消息接口](#-消息接口)
3. [群组接口](#-群组接口)
4. [用户接口](#-用户接口)
5. [系统接口](#-系统接口)
6. [文件接口](#-文件接口)
7. [消息段类型 (OB11MessageData)](#-消息段类型)
8. [事件上报 (WebSocket)](#-事件上报)
9. [群组扩展 API](#-群组扩展-api)
10. [消息扩展 API](#-消息扩展-api)
11. [系统扩展 API](#-系统扩展-api)
12. [文件扩展 API](#-文件扩展-api)
13. [用户扩展 API](#-用户扩展-api)
14. [流式接口](#-流式接口)
15. [频道接口](#-频道接口)
16. [AI 扩展](#-ai-扩展)
17. [Go-CQHTTP 兼容接口](#-go-cqhttp-兼容接口)
18. [数据类型定义](#-数据类型定义)

---

## 🔄 基础响应格式

所有接口返回统一格式：

```json
{
  "status": "ok",            // 状态: ok | failed
  "retcode": 0,              // 返回码: 0=成功
  "data": { /* 业务数据 */ },
  "message": "",
  "wording": "",
  "stream": "normal-action"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | `ok` 或 `failed` |
| retcode | int | 返回码，0 表示成功 |
| data | object/null | 业务数据 |
| message | string | 消息 |
| wording | string | 详细说明 |
| stream | string | 流式标识 |

### 常见错误码

| retcode | 说明 |
|---------|------|
| 0 | 成功 |
| 1400 | 请求参数错误或业务逻辑执行失败 |

---

## 📨 消息接口

### 发送消息 `send_msg`

- **端点**: `POST /send_msg`
- **说明**: 发送私聊或群聊消息。自动根据 `message_type` 路由。

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message_type | string | 否 | `private` / `group` |
| user_id | string | 否 | 用户 QQ |
| group_id | string | 否 | 群号 |
| message | OB11MessageMixType | **是** | 消息内容 |
| auto_escape | boolean/string | 否 | 是否作为纯文本发送 |
| timeout | number | 否 | 自定义发送超时（毫秒） |

**响应 `data`:**

| 字段 | 类型 | 说明 |
|------|------|------|
| message_id | number | 消息 ID |
| res_id | string | 转发消息的 res_id |
| forward_id | string | 转发消息的 forward_id |

**请求示例:**
```json
{
  "message_type": "group",
  "group_id": "123456",
  "message": "hello"
}
```

**响应示例:**
```json
{
  "status": "ok",
  "retcode": 0,
  "data": { "message_id": 123456 },
  "message": "",
  "wording": "",
  "stream": "normal-action"
}
```

---

### 发送私聊消息 `send_private_msg`

- **端点**: `POST /send_private_msg`
- **说明**: 发送私聊消息。

**请求参数:** 同 `send_msg`，但自动标记为私聊。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 否 | 用户 QQ |
| message | OB11MessageMixType | **是** | 消息内容 |

---

### 发送群消息 `send_group_msg`

- **端点**: `POST /send_group_msg`
- **说明**: 发送群消息。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | string | 否 | 群号 |
| message | OB11MessageMixType | **是** | 消息内容 |

---

### 获取消息 `get_msg`

- **端点**: `POST /get_msg`
- **说明**: 根据消息 ID 获取消息详细信息。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message_id | number/string | **是** | 消息 ID |

**响应 `data`:**

| 字段 | 类型 | 说明 |
|------|------|------|
| time | number | 发送时间戳 |
| message_type | string | 消息类型 |
| message_id | number | 消息 ID |
| real_id | number | 真实 ID |
| message_seq | number | 消息序号 |
| sender | object | 发送者信息 |
| message | object/array | 消息内容 (OB11MessageData) |
| raw_message | string | 原始消息内容 |
| font | number | 字体 |
| group_id | number/string | 群号 |
| user_id | number/string | 发送者 QQ |

---

### 撤回消息 `delete_msg`

- **端点**: `POST /delete_msg`
- **说明**: 撤回已发送的消息。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message_id | number/string | **是** | 消息 ID |

---

### 转发单条消息

- **端点**: `POST /forward_single_msg`
- **说明**: 转发单条消息到指定目标。

---

### 标记群聊已读

- **端点**: `POST /mark_group_read`
- **说明**: 标记指定群聊的消息为已读。

---

### 标记私聊已读

- **端点**: `POST /mark_friend_read`
- **说明**: 标记指定私聊的消息为已读。

---

### 标记消息已读 (Go-CQHTTP)

- **端点**: `POST /mark_read`
- **说明**: 标记指定渠道的消息为已读（Go-CQHTTP 兼容）。

---

### 标记所有消息已读

- **端点**: `POST /mark_all_read`
- **说明**: 标记所有消息为已读。

---

## 👥 群组接口

### 发送群消息

见 [发送群消息 `send_group_msg`](#发送群消息-send_group_msg)

---

### 获取群列表 `get_group_list`

- **端点**: `POST /get_group_list`
- **说明**: 获取当前账号的群聊列表。

---

### 获取群信息 `get_group_info`

- **端点**: `POST /get_group_info`
- **说明**: 获取群聊的基本信息。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |

---

### 获取群详细信息 `get_group_info_ex`

- **端点**: `POST /get_group_info_ex`
- **说明**: 获取群聊的详细信息，包括成员数、最大成员数等。

---

### 获取群成员列表 `get_group_member_list`

- **端点**: `POST /get_group_member_list`
- **说明**: 获取群聊中的所有成员列表。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |

---

### 获取群成员信息 `get_group_member_info`

- **端点**: `POST /get_group_member_info`
- **说明**: 获取群聊中指定成员的信息。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |
| user_id | number/string | **是** | 用户 QQ |

---

### 退出群组 `set_group_leave`

- **端点**: `POST /set_group_leave`
- **说明**: 退出或解散指定群聊。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |
| is_dismiss | boolean | 否 | 是否解散（群主权限） |

---

### 群组踢人 `set_group_kick`

- **端点**: `POST /set_group_kick`
- **说明**: 将指定成员踢出群聊。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |
| user_id | number/string | **是** | 成员 QQ |
| reject_add_request | boolean | 否 | 是否拒绝再次加群 |

---

### 群组禁言 `set_group_ban`

- **端点**: `POST /set_group_ban`
- **说明**: 禁言群聊中的指定成员。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |
| user_id | number/string | **是** | 成员 QQ |
| duration | number | **是** | 禁言时长（秒），0 为解除禁言 |

---

### 全员禁言 `set_group_whole_ban`

- **端点**: `POST /set_group_whole_ban`
- **说明**: 开启或关闭指定群聊的全员禁言。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |
| enable | boolean | **是** | 是否开启 |

---

### 设置群管理员 `set_group_admin`

- **端点**: `POST /set_group_admin`
- **说明**: 设置或取消群聊中的管理员。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |
| user_id | number/string | **是** | 成员 QQ |
| enable | boolean | **是** | true=设置为管理员 |

---

### 设置群名片 `set_group_card`

- **端点**: `POST /set_group_card`
- **说明**: 设置群聊中指定成员的群名片。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |
| user_id | number/string | **是** | 成员 QQ |
| card | string | **是** | 群名片 |

---

### 设置群名称 `set_group_name`

- **端点**: `POST /set_group_name`
- **说明**: 修改指定群聊的名称。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |
| group_name | string | **是** | 新群名 |

---

### 处理加群请求 `set_group_add_request`

- **端点**: `POST /set_group_add_request`
- **说明**: 同意或拒绝加群请求或邀请。

---

### 获取群公告 `get_group_notice`

- **端点**: `POST /get_group_notice`
- **说明**: 获取指定群聊中的公告列表。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | number/string | **是** | 群号 |

---

### 获取群精华消息 `get_essence_msg_list`

- **端点**: `POST /get_essence_msg_list`
- **说明**: 获取指定群聊中的精华消息列表。

---

### 设置精华消息 `set_essence_msg`

- **端点**: `POST /set_essence_msg`
- **说明**: 将一条消息设置为群精华消息。

---

### 移出精华消息 `delete_essence_msg`

- **端点**: `POST /delete_essence_msg`
- **说明**: 将一条消息从群精华消息列表中移出。

---

### 删除群公告 `delete_group_notice`

- **端点**: `POST /delete_group_notice`
- **说明**: 删除群聊中的公告。

---

### 获取群禁言列表

- **端点**: `POST /get_group_shut_list`
- **说明**: 获取群聊中的禁言成员列表。

---

### 获取群被忽略的加群请求

- **端点**: `POST /get_group_ignored_add_requests`
- **说明**: 获取被忽略的入群申请和邀请通知。

---

## 👤 用户接口

### 发送私聊消息

见 [发送私聊消息 `send_private_msg`](#发送私聊消息-send_private_msg)

---

### 获取好友列表 `get_friend_list`

- **端点**: `POST /get_friend_list`
- **说明**: 获取当前账号的好友列表。

---

### 获取陌生人信息 `get_stranger_info`

- **端点**: `POST /get_stranger_info`
- **说明**: 获取指定非好友用户的信息。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | number/string | **是** | 用户 QQ |

---

### 点赞 `send_like`

- **端点**: `POST /send_like`
- **说明**: 给指定用户点赞。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | number/string | **是** | 用户 QQ |
| times | number | 否 | 点赞次数 |

---

### 处理加好友请求 `set_friend_add_request`

- **端点**: `POST /set_friend_add_request`
- **说明**: 同意或拒绝加好友请求。

---

### 设置好友备注

- **端点**: `POST /set_friend_remark`
- **说明**: 设置好友备注。

---

### 获取 Cookies

- **端点**: `POST /get_cookies`
- **说明**: 获取指定域名的 Cookies。

---

### 获取最近会话

- **端点**: `POST /get_recent_contact`
- **说明**: 获取最近会话列表。

---

## ⚙️ 系统接口

### 获取登录号信息 `get_login_info`

- **端点**: `POST /get_login_info`
- **说明**: 获取当前登录账号的信息。

---

### 获取版本信息 `get_version_info`

- **端点**: `POST /get_version_info`
- **说明**: 获取版本信息。

---

### 获取运行状态 `get_status`

- **端点**: `POST /get_status`
- **说明**: 获取运行状态。

---

### 获取 CSRF Token `get_csrf_token`

- **端点**: `POST /get_csrf_token`
- **说明**: 获取 CSRF Token。

---

### 获取登录凭证 `get_credentials`

- **端点**: `POST /get_credentials`
- **说明**: 获取登录凭证。

---

### 是否可以发送语音 `can_send_record`

- **端点**: `POST /can_send_record`
- **说明**: 检查是否可以发送语音。

---

### 是否可以发送图片 `can_send_image`

- **端点**: `POST /can_send_image`
- **说明**: 检查是否可以发送图片。

---

### 获取 Packet 状态

- **端点**: `POST /get_packet_status`
- **说明**: 获取底层 Packet 服务的运行状态。

---

### 重启服务

- **端点**: `POST /set_restart`
- **说明**: 重启服务。

---

### 获取群系统消息 `get_group_system_msg`

- **端点**: `POST /get_group_system_msg`
- **说明**: 获取群系统消息。

---

### 清理缓存

- **端点**: `POST /clean_cache`
- **说明**: 清理缓存。

---

## 📁 文件接口

### 获取文件 `get_file`

- **端点**: `POST /get_file`
- **说明**: 获取指定文件的详细信息及下载路径。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_id | string | **是** | 文件 ID |

---

### 获取图片 `get_image`

- **端点**: `POST /get_image`
- **说明**: 获取指定图片的信息及路径。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_id | string | **是** | 图片文件 ID |

---

### 获取语音 `get_record`

- **端点**: `POST /get_record`
- **说明**: 获取指定语音文件的信息，并支持格式转换。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_id | string | **是** | 语音文件 ID |
| out_format | string | 否 | 输出格式 |

---

### 获取群文件 URL

- **端点**: `POST /get_group_file_url`
- **说明**: 获取指定群文件的下载链接。

---

### 获取私聊文件 URL

- **端点**: `POST /get_private_file_url`
- **说明**: 获取指定私聊文件的下载链接。

---

## 🧩 消息段类型

> NapCat 遵循 OneBot v11 协议的消息段格式。
> 消息由多个消息段组成，每个消息段包含 `type` 和 `data` 字段。

### 基础结构

```json
{
  "type": "text",
  "data": { "text": "你好" }
}
```

### 消息段完整列表

| type | 说明 | data 字段 |
|------|------|-----------|
| `text` | 纯文本 | `text`: 文本内容 |
| `face` | QQ 表情 | `id`: 表情 ID |
| `image` | 图片 | `file`: 图片文件, `url`: 图片 URL, `cache` |
| `record` | 语音 | `file`: 语音文件, `url`: 语音 URL |
| `video` | 视频 | `file`: 视频文件, `url`: 视频 URL |
| `at` | @某人 | `qq`: QQ 号（`all`=全体） |
| `rps` | 猜拳 | `result`: 结果 |
| `dice` | 骰子 | `result`: 点数 |
| `shake` | 窗口抖动 | - |
| `poke` | 戳一戳 | `type`: 类型, `id`: ID |
| `reply` | 回复 | `id`: 消息 ID 映射, `seq`: 序列号 |
| `forward` | 合并转发 | `id`: 转发 ID |
| `node` | 合并转发节点 | `id`, `user_id`, `nickname`, `content` |
| `xml` | XML 消息 | `data`: XML 数据 |
| `json` | JSON 消息 | `data`: JSON 数据 |
| `markdown` | Markdown | `data`: Markdown 内容 |
| `music` | 音乐分享 | `type`: 来源, `id`: 歌曲 ID / `url`: 链接 |
| `custom_music` | 自定义音乐 | `url`, `audio`, `title`, `image` |
| `location` | 位置 | `lat`, `lng`, `title`, `content` |
| `contact` | 推荐好友/群 | `type`: `qq`/`group`, `id`: 目标 |
| `mini_app` | 小程序 | `appid`, `title`, `description`, `thumb`, `url` |
| `mface` | 表情商店表情 | `id`, `name`, `file` |
| `file` | 文件 | `file`, `name`, `size`, `url` |
| `onlinefile` | 在线文件 | `msgId`, `elementId` |
| `flash_transfer` | 闪照 | `file`: 图片文件 |
| `share_pc` | 分享群/用户 PC | 特定 Ark 格式 |

### 消息段混合类型 (OB11MessageMixType)

消息内容可以是：
- **字符串**: 纯文本形式 `"hello"`
- **数组**: 多个消息段 `[{"type":"text","data":{"text":"hi"}}, {"type":"image","data":{"file":"xxx.jpg"}}]`

### 完整消息对象 (OB11Message)

| 字段 | 类型 | 说明 |
|------|------|------|
| message_id | number | 消息 ID |
| message_seq | number | 消息序列号 |
| real_id | number | 真实 ID |
| user_id | number/string | 发送者 QQ |
| group_id | number/string | 群号 |
| group_name | string | 群名称 |
| message_type | string | `private` / `group` |
| sub_type | string | `friend` / `group` / `normal` |
| sender | OB11Sender | 发送者信息 |
| message | OB11MessageData[]/string | 消息内容 |
| self_id | number | 机器人 QQ |
| time | number | 消息时间戳 |
| target_id | number | 目标 ID |

### 发送者信息 (OB11Sender)

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | number/string | 发送者 QQ |
| nickname | string | 昵称 |
| card | string | 群名片 |
| role | string | 角色（owner/admin/member） |
| sex | string | 性别 |
| age | number | 年龄 |
| area | string | 地区 |
| level | string | 等级 |
| title | string | 头衔 |

### 图片消息段 (OB11MessageImage)

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | `image` |
| data.file | string | 图片文件标识（本地文件或 URL） |
| data.url | string | 图片 URL（响应中返回） |
| data.cache | boolean | 是否使用缓存 |
| data.sum | string | 图片摘要 |
| data.sub_type | number | 图片子类型 |

### 语音消息段 (OB11MessageRecord)

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | `record` |
| data.file | string | 语音文件标识 |
| data.url | string | 语音 URL（响应中返回） |
| data.cache | boolean | 是否使用缓存 |

### 视频消息段 (OB11MessageVideo)

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | `video` |
| data.file | string | 视频文件标识 |
| data.url | string | 视频 URL |
| data.cache | boolean | 是否使用缓存 |

### 回复消息段 (OB11MessageReply)

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | `reply` |
| data.id | string | 消息 ID 的短 ID 映射 |
| data.seq | number | 消息序列号（优先使用） |

---

## 📡 事件上报

NapCat 通过 WebSocket 或 HTTP Webhook 向客户端推送事件。

### 消息事件

```json
{
  "post_type": "message",
  "message_type": "private",     // private | group
  "sub_type": "friend",         // friend | group | normal
  "message_id": 123456,
  "user_id": 123456789,
  "group_id": 987654321,        // 群消息时存在
  "message": [ /* OB11MessageData[] */ ],
  "raw_message": "原始消息文本",
  "font": 0,
  "sender": {
    "user_id": 123456789,
    "nickname": "昵称",
    "card": "群名片",
    "role": "member"
  },
  "self_id": 10001,
  "time": 1700000000
}
```

### 请求事件

- **加好友请求**: `post_type: "request"`, `request_type: "friend"`
- **加群请求**: `post_type: "request"`, `request_type: "group"`, `sub_type: "add"`/`invite"`

### 通知事件

- **群成员增加/减少**: `post_type: "notice"`, `notice_type: "group_increase"`/`group_decrease"`
- **群管理员变更**: `notice_type: "group_admin"`
- **群禁言**: `notice_type: "group_ban"`
- **好友添加**: `notice_type: "friend_add"`
- **群消息撤回**: `notice_type: "group_recall"`
- **好友消息撤回**: `notice_type: "friend_recall"`
- **通知**: `notice_type: "notify"`, `sub_type: "poke"`(戳一戳)/`"honor"`(群荣誉)/`"lucky_king"`(运气王)/`"title"`(群头衔)

---

## 🔧 群组扩展 API

> NapCat 特有的群组扩展功能。

### 获取群详细信息 (扩展)

- **端点**: `POST /get_group_info_ex`
- 扩展的群信息接口，返回更详细的群数据。

### 群打卡

- **端点**: `POST /group_sign`
- 在群聊中完成每日打卡。

### 获取群组今日打卡列表

- **端点**: `POST /get_group_today_sign`

### 设置群加群选项

- **端点**: `POST /set_group_add_option`

### 设置群机器人加群选项

- **端点**: `POST /set_group_bot_add_option`

### 设置群搜索选项

- **端点**: `POST /set_group_search_option`

### 设置群备注

- **端点**: `POST /set_group_remark`

### 获取群相册列表

- **端点**: `POST /get_group_album_list`

### 获取群相册媒体列表

- **端点**: `POST /get_group_album_media_list`

### 上传图片到群相册

- **端点**: `POST /upload_group_album`

### 删除群相册媒体

- **端点**: `POST /delete_group_album_media`

### 点赞群相册媒体

- **端点**: `POST /like_group_album_media`

### 取消点赞群相册媒体

- **端点**: `POST /cancel_like_group_album_media`

### 发表群相册评论

- **端点**: `POST /comment_group_album`

---

## 🧩 消息扩展 API

### 设置消息表情点赞

- **端点**: `POST /set_msg_like`
- **说明**: 给指定消息添加表情回应。

### 获取表情点赞详情

- **端点**: `POST /get_msg_like_detail`

### 获取消息表情点赞列表

- **端点**: `POST /get_msg_like_list`

### 获取语音转文字结果

- **端点**: `POST /get_voice_to_text`

### 点击内联键盘按钮

- **端点**: `POST /click_inline_keyboard`

### 分享群 (Ark)

- **端点**: `POST /share_group_ark`

### 分享用户 (Ark)

- **端点**: `POST /share_user_ark`

---

## 🔩 系统扩展 API

### 设置在线状态

- **端点**: `POST /set_online_status`

### 设置输入状态

- **端点**: `POST /set_input_status`

### 获取用户在线状态

- **端点**: `POST /get_user_online_status`

### 获取自定义表情

- **端点**: `POST /get_custom_face`

### 获取自定义表情详情

- **端点**: `POST /get_custom_face_detail`

### 添加自定义表情

- **端点**: `POST /add_custom_face`

### 删除自定义表情

- **端点**: `POST /delete_custom_face`

### 修改自定义表情描述

- **端点**: `POST /modify_custom_face_desc`

### 获取机器人 UIN 范围

- **端点**: `POST /get_bot_uin_range`

### 获取 RKey

- **端点**: `POST /get_rkey`

### 获取扩展 RKey

- **端点**: `POST /get_extended_rkey`

### 获取 RKey 服务器

- **端点**: `POST /get_rkey_server`

### 获取小程序 Ark

- **端点**: `POST /get_mini_app_ark`

### 发送原始数据包

- **端点**: `POST /send_raw_packet`

### 获取收藏列表

- **端点**: `POST /get_collection_list`

### 退出登录

- **端点**: `POST /logout`

---

## 📎 文件扩展 API

### 移动群文件

- **端点**: `POST /move_group_file`

### 重命名群文件

- **端点**: `POST /rename_group_file`

### 传输群文件

- **端点**: `POST /transfer_group_file`

### 创建闪传任务

- **端点**: `POST /create_flash_transfer`

### 获取闪传文件列表

- **端点**: `POST /get_flash_transfer_list`

### 获取闪传文件链接

- **端点**: `POST /get_flash_transfer_url`

### 发送闪传消息

- **端点**: `POST /send_flash_transfer`

### 获取文件分享链接

- **端点**: `POST /get_file_share_url`

### 获取文件集信息

- **端点**: `POST /get_file_collection_info`

### 获取在线文件消息

- **端点**: `POST /get_online_file_msg`

### 发送在线文件

- **端点**: `POST /send_online_file`

### 发送在线文件夹

- **端点**: `POST /send_online_folder`

### 接收在线文件

- **端点**: `POST /receive_online_file`

### 拒绝在线文件

- **端点**: `POST /reject_online_file`

### 取消在线文件

- **端点**: `POST /cancel_online_file`

### 下载文件集

- **端点**: `POST /download_file_collection`

### 获取文件集 ID

- **端点**: `POST /get_file_collection_id`

---

## 👤 用户扩展 API

### 获取带分组的好友列表

- **端点**: `POST /get_friend_list_with_category`

### 获取资料点赞

- **端点**: `POST /get_profile_like`

### 获取单向好友列表

- **端点**: `POST /get_one_way_friend_list`

### 设置自定义在线状态

- **端点**: `POST /set_custom_online_status`
- **说明**: 设置自定义在线状态，包括文字、表情等。

---

## 🌊 流式接口

> NapCat 的流式传输扩展，用于大文件的上传和下载。

### 下载文件流

- **端点**: `POST /download_stream`
- **说明**: 以流式方式从网络或本地下载文件。

### 上传文件流

- **端点**: `POST /upload_stream`
- **说明**: 以流式方式上传文件数据到机器人。

### 流式传输扩展

| 端点 | 说明 |
|------|------|
| `POST /stream/download_image` | 下载图片文件流 |
| `POST /stream/download_record` | 下载语音文件流 |
| `POST /stream/download_test` | 测试下载流 |
| `POST /stream/clean_temp` | 清理流式传输临时文件 |

---

## 📢 频道接口

> QQ 频道（Guild）相关接口。

### 获取频道列表

- **端点**: `POST /get_guild_list`
- **说明**: 获取当前账号已加入的频道列表。

### 获取频道个人信息

- **端点**: `POST /get_guild_profile`
- **说明**: 获取当前账号在频道中的个人资料。

---

## 🤖 AI 扩展

### 获取 AI 语音

- **端点**: `POST /get_ai_record`
- **说明**: 通过 AI 语音引擎获取指定文本的语音 URL。

### 发送群 AI 语音

- **端点**: `POST /send_group_ai_record`
- **说明**: 发送 AI 生成的语音到指定群聊。

---

## 🔄 Go-CQHTTP 兼容接口

> 为兼容 OneBot v11 标准协议提供的接口。

### 获取群历史消息

- **端点**: `POST /get_group_msg_history`

### 获取好友历史消息

- **端点**: `POST /get_friend_msg_history`

### 获取合并转发消息 `get_forward_msg`

- **端点**: `POST /get_forward_msg`
- **说明**: 获取合并转发消息的具体内容。

### 发送合并转发消息 `send_forward_msg`

- **端点**: `POST /send_forward_msg`

### 发送群合并转发消息

- **端点**: `POST /send_group_forward_msg`

### 发送私聊合并转发消息

- **端点**: `POST /send_private_forward_msg`

### 上传群文件

- **端点**: `POST /upload_group_file`

### 上传私聊文件

- **端点**: `POST /upload_private_file`

### 下载文件

- **端点**: `POST /download_file`

### 删除好友

- **端点**: `POST /delete_friend`

### 获取群根目录文件列表

- **端点**: `POST /get_group_root_files`

### 获取群文件夹文件列表

- **端点**: `POST /get_group_files_by_folder`

### 获取群文件系统信息

- **端点**: `POST /get_group_file_system_info`

### 创建群文件目录

- **端点**: `POST /create_group_file_folder`

### 删除群文件

- **端点**: `POST /delete_group_file`

### 删除群文件目录

- **端点**: `POST /delete_group_file_folder`

### 发送群公告 `_send_group_notice`

- **端点**: `POST /_send_group_notice`

### 设置群头像

- **端点**: `POST /set_group_portrait`

### 设置 QQ 资料

- **端点**: `POST /set_qq_profile`
- **说明**: 修改当前账号的昵称、个性签名等资料。

### 设置机型

- **端点**: `POST /set_model_show`

### 获取机型显示

- **端点**: `POST /get_model_show`

### 获取群荣誉信息

- **端点**: `POST /get_group_honor_info`

### 获取群艾特全体剩余次数

- **端点**: `POST /get_group_at_all_remain`

### 检查 URL 安全性

- **端点**: `POST /check_url_safely`

### 获取在线客户端

- **端点**: `POST /get_online_client`

### 处理快速操作

- **端点**: `POST /handle_quick_operation`
- **说明**: 处理来自事件上报的快速操作请求。

---

## 📐 数据类型定义

### BaseResponse

```json
{
  "status": "ok",
  "retcode": 0,
  "data": { /* ... */ },
  "message": "",
  "wording": "",
  "stream": "normal-action"
}
```

### EmptyData

空的 data 对象，用于不需要返回数据的接口。

### FileBaseData

| 字段 | 类型 | 说明 |
|------|------|------|
| file | string | 文件标识 |
| url | string | 文件 URL |
| cache | boolean | 是否使用缓存 |

### OB11GroupMember

| 字段 | 类型 | 说明 |
|------|------|------|
| group_id | number/string | 群号 |
| user_id | number/string | 成员 QQ |
| nickname | string | 昵称 |
| card | string | 群名片 |
| sex | string | 性别 |
| age | number | 年龄 |
| area | string | 地区 |
| join_time | number | 入群时间 |
| last_sent_time | number | 最后发言时间 |
| level | string | 等级 |
| role | string | 角色（owner/admin/member） |
| title | string | 专属头衔 |
| title_expire_time | number | 头衔过期时间 |
| shut_up_timestamp | number | 禁言到期时间 |

### OB11Group

| 字段 | 类型 | 说明 |
|------|------|------|
| group_id | number/string | 群号 |
| group_name | string | 群名称 |
| group_create_time | number | 创建时间 |
| member_count | number | 成员数 |
| max_member_count | number | 最大成员数 |

### OB11User

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | number/string | QQ 号 |
| nickname | string | 昵称 |
| sex | string | 性别 |
| age | number | 年龄 |

### OB11Notify

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | number/string | 操作者 QQ |
| target_id | number/string | 目标 QQ |
| group_id | number/string | 群号 |
| sub_type | string | 通知子类型 |

### OB11ActionMessage

| 字段 | 类型 | 说明 |
|------|------|------|
| action | string | 动作名称 |
| params | object | 动作参数 |
| echo | string | 回显标识 |

### OB11LatestMessage

| 字段 | 类型 | 说明 |
|------|------|------|
| message_id | number | 消息 ID |
| message | OB11MessageData[] | 消息内容 |
| message_type | string | 消息类型 |
| user_id | number/string | 发送者 QQ |
| group_id | number/string | 群号 |

---

## 扩展接口

### 批量踢出群成员

- **端点**: `POST /batch_kick_group_member`
- **说明**: 从指定群聊中批量踢出多个成员。

### 创建收藏

- **端点**: `POST /create_collection`

### 设置个性签名

- **端点**: `POST /set_signature`

### 设置 QQ 头像

- **端点**: `POST /set_qq_avatar`

### 设置专属头衔

- **端点**: `POST /set_group_special_title`

### 英文单词翻译

- **端点**: `POST /translate_en_word`

### 获取 ClientKey

- **端点**: `POST /get_client_key`

### 获取 AI 角色列表

- **端点**: `POST /get_ai_characters`

### 图片 OCR 识别

- **端点**: `POST /ocr_image`
- **说明**: 识别图片中的文字内容（仅 Windows 端支持）。

### 图片 OCR 识别 (内部)

- **端点**: `POST /ocr_image_internal`

### 核心接口

### 设置群待办

- **端点**: `POST /set_group_todo`
- **说明**: 将指定消息设置为群待办。

### 完成群待办

- **端点**: `POST /finish_group_todo`
- **说明**: 将指定消息对应的群待办标记为已完成。

### 取消群待办

- **端点**: `POST /cancel_group_todo`
- **说明**: 将指定消息对应的群待办取消。

### 发送戳一戳

- **端点**: `POST /send_poke`
- **说明**: 在群聊或私聊中发送戳一戳动作。

### 处理可疑好友申请

- **端点**: `POST /handle_suspicious_friend`
- **说明**: 同意或拒绝系统的可疑好友申请。

### 获取可疑好友申请

- **端点**: `POST /get_suspicious_friend_list`
- **说明**: 获取系统的可疑好友申请列表。

---

> **文档版本**: 基于 NapCat 官方 llms.txt (2026年6月) 整理
> **原始来源**: [https://napcat.apifox.cn](https://napcat.apifox.cn)
> **协议标准**: OneBot v11 + NapCat 扩展
