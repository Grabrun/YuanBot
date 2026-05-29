"""微信 CDN 媒体传输模块

实现 AES-128-ECB 加密上传/下载，符合 iLink Bot CDN 协议。
"""

from __future__ import annotations

import hashlib
import os

import httpx
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
CDN_TIMEOUT_S = 30
MAX_RETRIES = 3


def aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 加密（PKCS7 填充）"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    # PKCS7 填充
    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len] * pad_len)

    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 解密（PKCS7 填充）"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    cipher = Cipher(algorithms.AES(key), modes.ECB())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    # 去除 PKCS7 填充
    pad_len = padded[-1]
    if 1 <= pad_len <= 16 and padded[-pad_len:] == bytes([pad_len] * pad_len):
        return padded[:-pad_len]
    return padded


def aes_ecb_padded_size(plaintext_size: int) -> int:
    """计算 AES-ECB 加密后的密文大小（含 PKCS7 填充）

    PKCS7 总是添加填充：即使输入已是 16 的倍数，也会添加 16 字节填充块。
    """
    return ((plaintext_size + 16) // 16) * 16


def parse_aes_key(key_b64: str, use_hex_decode: bool = False) -> bytes:
    """解析 AES 密钥

    Args:
        key_b64: base64 编码的密钥
        use_hex_decode: True 时先 base64 解码为 hex 字符串再 hex 解码（文件/语音/视频用）
    """
    import base64

    decoded = base64.b64decode(key_b64)
    if use_hex_decode and len(decoded) == 32:
        # hex 字符串 -> 16 字节
        return bytes.fromhex(decoded.decode("ascii"))
    return decoded  # 直接 16 字节


async def upload_to_cdn(
    file_data: bytes,
    aes_key: bytes,
    file_key: str,
    upload_param: str,
    cdn_base_url: str = DEFAULT_CDN_BASE_URL,
    upload_full_url: str = "",
) -> str | None:
    """上传加密文件到 CDN

    Returns:
        download_param (x-encrypted-param 响应头)，失败返回 None
    """
    # 加密文件内容
    ciphertext = aes_ecb_encrypt(file_data, aes_key)

    # 构建上传 URL
    if upload_full_url:
        url = upload_full_url
    else:
        from urllib.parse import quote
        url = (
            f"{cdn_base_url}/upload?encrypted_query_param={quote(upload_param)}"
            f"&filekey={quote(file_key)}"
        )

    # 上传（带重试）
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=CDN_TIMEOUT_S) as client:
                resp = await client.post(
                    url,
                    content=ciphertext,
                    headers={"Content-Type": "application/octet-stream"},
                )

                if 400 <= resp.status_code < 500:
                    logger.error("cdn_upload_client_error", status=resp.status_code)
                    return None

                if resp.status_code >= 500:
                    logger.warning(
                        "cdn_upload_server_error",
                        status=resp.status_code, attempt=attempt + 1,
                    )
                    continue

                # 成功，获取下载参数
                download_param = resp.headers.get("x-encrypted-param", "")
                return download_param

        except Exception as exc:
            logger.error("cdn_upload_error", error=str(exc), attempt=attempt + 1)

    return None


async def download_from_cdn(
    encrypt_query_param: str,
    aes_key: bytes | None,
    cdn_base_url: str = DEFAULT_CDN_BASE_URL,
    full_url: str = "",
) -> bytes | None:
    """从 CDN 下载并解密文件

    Args:
        encrypt_query_param: CDN 加密查询参数
        aes_key: AES-128 密钥（None 时不解密）
        cdn_base_url: CDN 基础 URL
        full_url: 服务端返回的完整 URL（优先使用）

    Returns:
        解密后的明文数据，失败返回 None
    """
    if full_url:
        url = full_url
    else:
        from urllib.parse import quote
        url = f"{cdn_base_url}/download?encrypted_query_param={quote(encrypt_query_param)}"

    try:
        async with httpx.AsyncClient(timeout=CDN_TIMEOUT_S) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ciphertext = resp.content

            if aes_key:
                return aes_ecb_decrypt(ciphertext, aes_key)
            else:
                # 无加密，直接返回
                return ciphertext

    except Exception as exc:
        logger.error("cdn_download_error", error=str(exc))
        return None


def generate_file_key() -> str:
    """生成随机文件标识 (16 字节 hex)"""
    return os.urandom(16).hex()


def generate_aes_key() -> tuple[bytes, str]:
    """生成随机 AES-128 密钥

    Returns:
        (key_bytes, key_hex) - key_bytes 用于加密，key_hex 用于 API 传输
    """
    key_bytes = os.urandom(16)
    return key_bytes, key_bytes.hex()


def compute_md5(data: bytes) -> str:
    """计算 MD5 哈希"""
    return hashlib.md5(data).hexdigest()
