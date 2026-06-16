#!/usr/bin/env python3
"""YuanBot 个人微信通道 QR 码登录

流程:
1. 调用 iLink Bot API 获取二维码
2. 用户用另一台微信扫码
3. 轮询登录状态，获取 token
4. 保存到 configs/Channels/wechat.yaml
"""

import asyncio
import json
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

BASE_URL = "https://ilinkai.weixin.qq.com"
BOT_TYPE = "3"
QR_POLL_INTERVAL = 3  # 秒
QR_POLL_TIMEOUT = 60  # 秒


async def fetch_qrcode(client: httpx.AsyncClient) -> dict:
    """获取登录二维码"""
    resp = await client.post(
        f"{BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}",
        json={"local_token_list": []},
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    qrcode = data.get("qrcode", "")
    qrcode_img_url = data.get("qrcode_img_content", "")
    if not qrcode:
        print("❌ 获取二维码失败:", json.dumps(data, ensure_ascii=False, indent=2))
        sys.exit(1)

    return {"qrcode": qrcode, "qrcode_img_url": qrcode_img_url}


async def poll_status(client: httpx.AsyncClient, qrcode: str) -> dict:
    """轮询二维码状态"""
    url = f"{BASE_URL}/ilink/bot/get_qrcode_status?qrcode={urllib.parse.quote(qrcode)}"
    resp = await client.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


async def main():
    print("🌸 YuanBot 个人微信登录")
    print("=" * 40)

    async with httpx.AsyncClient() as client:
        # 1. 获取二维码
        print("\n📱 正在获取二维码...")
        qr_data = await fetch_qrcode(client)
        qrcode = qr_data["qrcode"]
        qrcode_img_url = qr_data["qrcode_img_url"]

        print(f"\n✅ 二维码获取成功！")
        print(f"   🔗 二维码 URL: {qrcode_img_url}")
        print(f"\n   ⚠️  请用另一台微信扫描上方二维码")
        print(f"   🤳 扫码后按 Enter 开始轮询...")
        input()

        # 2. 轮询二维码状态
        print("\n⏳ 正在轮询登录状态...")
        start_time = time.time()

        while time.time() - start_time < QR_POLL_TIMEOUT:
            result = await poll_status(client, qrcode)
            ret = result.get("ret", -1)

            if ret == 0:
                token = result.get("token", "")
                ilink_user_id = result.get("ilink_user_id", "")
                bot_id = result.get("bot_id", "")
                print(f"\n🎉 登录成功！")
                print(f"   Token: {token[:20]}...{token[-8:]}")
                print(f"   iLink User ID: {ilink_user_id}")
                print(f"   Bot ID: {bot_id}")

                # 3. 保存配置
                config_path = Path("configs/Channels/wechat.yaml")
                if config_path.exists():
                    content = config_path.read_text(encoding="utf-8")
                    # 更新配置
                    import yaml

                    with open(config_path) as f:
                        config = yaml.safe_load(f) or {}

                    config["enabled"] = True
                    config["config"]["token"] = token
                    config["config"]["ilink_user_id"] = ilink_user_id
                    config["config"]["bot_id"] = bot_id

                    with open(config_path, "w") as f:
                        yaml.safe_dump(
                            config,
                            f,
                            allow_unicode=True,
                            default_flow_style=False,
                            sort_keys=False,
                        )

                    print(f"\n✅ 配置已保存到: {config_path}")
                else:
                    print(f"\n⚠️  未找到 {config_path}，请手动记录以上信息")

                return

            elif ret == -6:
                print("⏳ 等待扫码...")
            elif ret == 100:
                print("✅ 已扫码，等待确认...")
            else:
                print(f"⏳ 状态码: {ret}")

            await asyncio.sleep(QR_POLL_INTERVAL)

        print("\n❌ 二维码已过期，请重新运行脚本")


if __name__ == "__main__":
    asyncio.run(main())
