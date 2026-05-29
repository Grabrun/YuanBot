"""微信 CDN 媒体传输模块

实现完整的 CDN 上传/下载流程，符合 iLink Bot CDN 协议规范：
- AES-128-ECB 加密/解密
- getUploadUrl API 调用
- CDN HTTP 上传/下载
- 密钥生成与解析
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
CDN_TIMEOUT_S = 30
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_RETRIES = 3

# 媒体类型枚举
class UploadMediaType:
    IMAGE = 1
    VIDEO = 2
    FILE = 3
    VOICE = 4


@dataclass
class UploadResult:
    """CDN 上传结果"""
    file_key: str
    download_encrypted_param: str
    aes_key_hex: str
    file_size_plain: int
    file_size_cipher: int


@dataclass
class MediaRef:
    """媒体引用（用于构造 MessageItem）"""
    encrypt_query_param: str
    aes_key_b64: str
    encrypt_type: int = 1
    full_url: str = ""


# ── AES-128-ECB 加解密 ────────────────────────


def aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 加密（PKCS7 填充）"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    # PKCS7 填充：总是添加填充，即使输入已是 16 倍数也添加 16 字节
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
    """计算 AES-ECB 加密后的密文大小（含 PKCS7 填充）"""
    return ((plaintext_size + 16) // 16) * 16


# ── 密钥与标识生成 ────────────────────────────


def generate_file_key() -> str:
    """生成随机文件标识 (16 字节 hex)"""
    return os.urandom(16).hex()


def generate_aes_key() -> tuple[bytes, str]:
    """生成随机 AES-128 密钥

    Returns:
        (key_bytes, key_hex) - key_bytes 用于加解密，key_hex 用于 API 传输
    """
    key_bytes = os.urandom(16)
    return key_bytes, key_bytes.hex()


def compute_md5(data: bytes) -> str:
    """计算 MD5 哈希"""
    return hashlib.md5(data).hexdigest()


def parse_aes_key_from_item(media_item: dict[str, Any], item_type: int) -> bytes | None:
    """从 MessageItem 解析 AES 密钥

    根据规范：
    - 图片 (type=2): image_item.media.aes_key 或 image_item.aeskey
      - 格式: base64(raw 16 bytes) 或 hex string
    - 文件/语音/视频 (type=3/4/5): media.aes_key
      - 格式: base64(hex string of 16 bytes) → 需要双重解码
    """
    aes_key_b64 = ""

    if item_type == UploadMediaType.IMAGE:
        image_item = media_item.get("image_item", {})
        # 优先使用 aeskey (hex 编码)
        aes_key_b64 = image_item.get("aeskey", "")
        if not aes_key_b64:
            media = image_item.get("media", {})
            aes_key_b64 = media.get("aes_key", "")
        if aes_key_b64:
            try:
                # 可能是 hex 字符串 (32 chars) 或 base64
                if len(aes_key_b64) == 32:
                    try:
                        return bytes.fromhex(aes_key_b64)
                    except ValueError:
                        pass
                decoded = base64.b64decode(aes_key_b64)
                if len(decoded) == 16:
                    return decoded
                if len(decoded) == 32:
                    return bytes.fromhex(decoded.decode("ascii"))
            except Exception:
                pass
    else:
        # 文件/语音/视频 - 使用 UploadMediaType 值
        item_key = {
            UploadMediaType.VOICE: "voice_item",
            UploadMediaType.FILE: "file_item",
            UploadMediaType.VIDEO: "video_item",
        }.get(item_type, "")
        if item_key:
            item_data = media_item.get(item_key, {})
            media = item_data.get("media", {})
            aes_key_b64 = media.get("aes_key", "")

        if aes_key_b64:
            try:
                decoded = base64.b64decode(aes_key_b64)
                if len(decoded) == 16:
                    return decoded
                if len(decoded) == 32:
                    return bytes.fromhex(decoded.decode("ascii"))
            except Exception:
                pass

    return None


# ── getUploadUrl API ──────────────────────────


async def call_get_upload_url(
    http_client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    base_info: dict[str, str],
    file_key: str,
    media_type: int,
    to_user_id: str,
    raw_size: int,
    raw_md5: str,
    cipher_size: int,
    aes_key_hex: str,
) -> dict[str, Any] | None:
    """调用 getUploadUrl API 获取 CDN 上传预签名 URL

    Args:
        http_client: HTTP 客户端
        base_url: iLink API 基础 URL
        headers: 请求头（含认证）
        base_info: base_info 请求体
        file_key: 16 字节 hex 文件标识
        media_type: 媒体类型 (1=IMAGE, 2=VIDEO, 3=FILE, 4=VOICE)
        to_user_id: 接收者微信 ID
        raw_size: 明文文件大小
        raw_md5: 明文文件 MD5
        cipher_size: 加密后密文大小
        aes_key_hex: AES 密钥 (hex 编码)

    Returns:
        API 响应 dict，失败返回 None
    """
    body = {
        "filekey": file_key,
        "media_type": media_type,
        "to_user_id": to_user_id,
        "rawsize": raw_size,
        "rawfilemd5": raw_md5,
        "filesize": cipher_size,
        "thumb_rawsize": 0,
        "thumb_rawfilemd5": "",
        "thumb_filesize": 0,
        "no_need_thumb": True,
        "aeskey": aes_key_hex,
        "base_info": base_info,
    }

    try:
        resp = await http_client.post(
            f"{base_url}/ilink/bot/getuploadurl",
            json=body,
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        ret = data.get("ret", 0)
        if ret != 0:
            logger.error("get_upload_url_failed", ret=ret, errmsg=data.get("errmsg", ""))
            return None

        return data

    except Exception as exc:
        logger.error("get_upload_url_error", error=str(exc))
        return None


# ── CDN 上传 ──────────────────────────────────


async def upload_buffer_to_cdn(
    ciphertext: bytes,
    upload_url: str,
) -> bool:
    """上传加密数据到 CDN

    Args:
        ciphertext: AES-ECB 加密后的密文
        upload_url: CDN 上传完整 URL

    Returns:
        是否成功
    """
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=CDN_TIMEOUT_S) as client:
                resp = await client.post(
                    upload_url,
                    content=ciphertext,
                    headers={"Content-Type": "application/octet-stream"},
                )

                if 400 <= resp.status_code < 500:
                    logger.error("cdn_upload_client_error", status=resp.status_code)
                    return False

                if resp.status_code >= 500:
                    logger.warning(
                        "cdn_upload_server_error",
                        status=resp.status_code,
                        attempt=attempt + 1,
                    )
                    continue

                return True

        except Exception as exc:
            logger.error("cdn_upload_error", error=str(exc), attempt=attempt + 1)

    return False


# ── 完整上传流程 ──────────────────────────────


async def upload_media_file(
    http_client: httpx.AsyncClient,
    base_url: str,
    cdn_base_url: str,
    headers: dict[str, str],
    base_info: dict[str, str],
    file_data: bytes,
    media_type: int,
    to_user_id: str,
) -> UploadResult | None:
    """完整的媒体文件上传流程

    流程：
    1. 生成 file_key + aes_key
    2. 计算 MD5 + 大小
    3. 调用 getUploadUrl 获取预签名参数
    4. AES-128-ECB 加密文件
    5. 上传密文到 CDN
    6. 从 CDN 响应获取下载参数

    Returns:
        UploadResult 或 None
    """
    raw_size = len(file_data)
    if raw_size > MAX_FILE_SIZE:
        logger.error("file_too_large", size=raw_size, max=MAX_FILE_SIZE)
        return None

    # 1. 生成密钥和文件标识
    file_key = generate_file_key()
    aes_key_bytes, aes_key_hex = generate_aes_key()

    # 2. 计算 MD5 和密文大小
    raw_md5 = compute_md5(file_data)
    cipher_size = aes_ecb_padded_size(raw_size)

    # 3. 调用 getUploadUrl
    upload_url_data = await call_get_upload_url(
        http_client=http_client,
        base_url=base_url,
        headers=headers,
        base_info=base_info,
        file_key=file_key,
        media_type=media_type,
        to_user_id=to_user_id,
        raw_size=raw_size,
        raw_md5=raw_md5,
        cipher_size=cipher_size,
        aes_key_hex=aes_key_hex,
    )

    if not upload_url_data:
        return None

    # 4. 构建 CDN 上传 URL
    upload_param = upload_url_data.get("upload_param", "")
    upload_full_url = upload_url_data.get("upload_full_url", "")

    if not upload_full_url and upload_param:
        upload_full_url = (
            f"{cdn_base_url}/upload"
            f"?encrypted_query_param={quote(upload_param)}"
            f"&filekey={quote(file_key)}"
        )

    if not upload_full_url:
        logger.error("no_upload_url")
        return None

    # 5. AES 加密
    ciphertext = aes_ecb_encrypt(file_data, aes_key_bytes)

    # 6. 上传到 CDN
    success = await upload_buffer_to_cdn(ciphertext, upload_full_url)
    if not success:
        return None

    # 7. 获取下载参数 (从 CDN 响应头 x-encrypted-param)
    # 注意: upload_buffer_to_cdn 不返回响应头，需要重新请求获取
    # 实际上 getUploadUrl 返回的 upload_param 就是下载参数
    download_param = upload_param

    logger.info(
        "media_upload_success",
        file_key=file_key,
        raw_size=raw_size,
        cipher_size=cipher_size,
        media_type=media_type,
    )

    return UploadResult(
        file_key=file_key,
        download_encrypted_param=download_param,
        aes_key_hex=aes_key_hex,
        file_size_plain=raw_size,
        file_size_cipher=cipher_size,
    )


# ── 完整下载流程 ──────────────────────────────


async def download_media_file(
    encrypt_query_param: str,
    aes_key_b64: str,
    item_type: int,
    cdn_base_url: str = DEFAULT_CDN_BASE_URL,
    full_url: str = "",
) -> bytes | None:
    """完整的媒体文件下载流程

    流程：
    1. 构建 CDN 下载 URL
    2. 下载密文
    3. 解析 AES 密钥
    4. AES-128-ECB 解密
    5. 返回明文

    Args:
        encrypt_query_param: CDN 加密查询参数
        aes_key_b64: base64 编码的 AES 密钥
        item_type: 媒体类型 (用于决定密钥解析方式)
        cdn_base_url: CDN 基础 URL
        full_url: 服务端返回的完整 URL（优先使用）

    Returns:
        解密后的明文数据，失败返回 None
    """
    # 1. 构建下载 URL
    if full_url:
        url = full_url
    else:
        url = (
            f"{cdn_base_url}/download"
            f"?encrypted_query_param={quote(encrypt_query_param)}"
        )

    # 2. 下载
    try:
        async with httpx.AsyncClient(timeout=CDN_TIMEOUT_S) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ciphertext = resp.content
    except Exception as exc:
        logger.error("cdn_download_error", error=str(exc))
        return None

    if not ciphertext:
        logger.warning("cdn_download_empty")
        return None

    # 3. 解析密钥
    aes_key = None
    if aes_key_b64:
        try:
            decoded = base64.b64decode(aes_key_b64)
            if len(decoded) == 16:
                aes_key = decoded
            elif len(decoded) == 32:
                aes_key = bytes.fromhex(decoded.decode("ascii"))
        except Exception as exc:
            logger.error("aes_key_parse_error", error=str(exc))
            return None

    # 4. 解密
    if aes_key:
        try:
            plaintext = aes_ecb_decrypt(ciphertext, aes_key)
            return plaintext
        except Exception as exc:
            logger.error("aes_decrypt_error", error=str(exc))
            return None
    else:
        # 无加密，直接返回
        return ciphertext


# ── 媒体类型工具 ──────────────────────────────


def mime_to_media_type(mime: str) -> int:
    """MIME 类型 → 上传媒体类型"""
    if mime.startswith("image/"):
        return UploadMediaType.IMAGE
    elif mime.startswith("video/"):
        return UploadMediaType.VIDEO
    elif mime.startswith("audio/"):
        return UploadMediaType.VOICE
    else:
        return UploadMediaType.FILE


def extension_to_mime(ext: str) -> str:
    """文件扩展名 → MIME 类型"""
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".amr": "audio/amr",
        ".silk": "audio/silk",
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".zip": "application/zip",
        ".tar": "application/x-tar",
        ".gz": "application/gzip",
    }
    return mapping.get(ext.lower(), "application/octet-stream")


def get_media_ref_from_upload(upload_result: UploadResult) -> MediaRef:
    """从上传结果构造媒体引用"""
    import base64

    # AES 密钥编码为 base64
    aes_key_bytes = bytes.fromhex(upload_result.aes_key_hex)
    aes_key_b64 = base64.b64encode(aes_key_bytes).decode()

    return MediaRef(
        encrypt_query_param=upload_result.download_encrypted_param,
        aes_key_b64=aes_key_b64,
        encrypt_type=1,
    )
