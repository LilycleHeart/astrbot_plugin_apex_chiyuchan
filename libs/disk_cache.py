"""磁盘缓存模块 — 用于持久化远程图片"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

# 默认配置
DEFAULT_TTL = 7 * 24 * 3600  # 7 天
DEFAULT_MAX_SIZE = 500 * 1024 * 1024  # 500MB
CACHE_DIR_NAME = "image_cache"


def _get_cache_dir() -> Path:
    """获取缓存目录路径"""
    cache_dir = Path(__file__).parent.parent / "assets" / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _hash_key(key: str) -> str:
    """将 URL 转换为安全的文件名（MD5 哈希）"""
    return hashlib.md5(key.encode()).hexdigest()


def _get_meta_path(key_hash: str) -> Path:
    """获取元数据文件路径"""
    return _get_cache_dir() / f"{key_hash}.meta"


def _get_data_path(key_hash: str) -> Path:
    """获取数据文件路径"""
    return _get_cache_dir() / f"{key_hash}.data"


async def get(key: str) -> Optional[bytes]:
    """从磁盘缓存获取图片数据

    Args:
        key: 缓存键（通常是图片 URL）

    Returns:
        图片二进制数据，如果不存在或已过期则返回 None
    """
    key_hash = _hash_key(key)
    meta_path = _get_meta_path(key_hash)
    data_path = _get_data_path(key_hash)

    # 检查文件是否存在
    if not meta_path.exists() or not data_path.exists():
        return None

    try:
        # 读取元数据
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        # 检查是否过期
        expires_at = meta.get('expires_at', 0)
        if time.time() > expires_at:
            # 过期了，删除文件
            _delete_files(meta_path, data_path)
            return None

        # 读取数据
        with open(data_path, 'rb') as f:
            return f.read()
    except Exception:
        # 读取失败，删除可能损坏的文件
        _delete_files(meta_path, data_path)
        return None


async def set(key: str, value: bytes, ttl_seconds: int = DEFAULT_TTL) -> bool:
    """将图片数据写入磁盘缓存

    Args:
        key: 缓存键（通常是图片 URL）
        value: 图片二进制数据
        ttl_seconds: 缓存过期时间（秒）

    Returns:
        是否写入成功
    """
    key_hash = _hash_key(key)
    meta_path = _get_meta_path(key_hash)
    data_path = _get_data_path(key_hash)

    try:
        # 写入数据
        with open(data_path, 'wb') as f:
            f.write(value)

        # 写入元数据
        meta = {
            'key': key,
            'created_at': time.time(),
            'expires_at': time.time() + ttl_seconds,
            'size': len(value),
        }
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False)

        return True
    except Exception:
        # 写入失败，清理可能不完整的文件
        _delete_files(meta_path, data_path)
        return False


async def delete(key: str) -> None:
    """删除指定缓存

    Args:
        key: 缓存键（通常是图片 URL）
    """
    key_hash = _hash_key(key)
    meta_path = _get_meta_path(key_hash)
    data_path = _get_data_path(key_hash)
    _delete_files(meta_path, data_path)


async def clear() -> None:
    """清空所有缓存"""
    cache_dir = _get_cache_dir()
    for file_path in cache_dir.glob("*.meta"):
        file_path.unlink(missing_ok=True)
    for file_path in cache_dir.glob("*.data"):
        file_path.unlink(missing_ok=True)


async def cleanup(max_size: int = DEFAULT_MAX_SIZE) -> int:
    """清理过期和超限的缓存

    Args:
        max_size: 最大缓存大小（字节）

    Returns:
        清理的文件数量
    """
    cache_dir = _get_cache_dir()
    now = time.time()
    cleaned = 0

    # 第一步：删除过期文件
    for meta_path in cache_dir.glob("*.meta"):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            if now > meta.get('expires_at', 0):
                key_hash = meta_path.stem
                _delete_files(meta_path, _get_data_path(key_hash))
                cleaned += 1
        except Exception:
            # 元数据损坏，删除
            meta_path.unlink(missing_ok=True)
            cleaned += 1

    # 第二步：如果超过大小限制，按 LRU 策略删除最旧的文件
    total_size = _get_total_cache_size()
    if total_size > max_size:
        # 收集所有缓存项的元数据
        items = []
        for meta_path in cache_dir.glob("*.meta"):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                items.append({
                    'meta_path': meta_path,
                    'data_path': _get_data_path(meta_path.stem),
                    'created_at': meta.get('created_at', 0),
                    'size': meta.get('size', 0),
                })
            except Exception:
                continue

        # 按创建时间排序（最旧的在前）
        items.sort(key=lambda x: x['created_at'])

        # 删除直到低于限制
        for item in items:
            if total_size <= max_size:
                break

            _delete_files(item['meta_path'], item['data_path'])
            total_size -= item['size']
            cleaned += 1

    return cleaned


def _delete_files(meta_path: Path, data_path: Path) -> None:
    """删除缓存文件"""
    meta_path.unlink(missing_ok=True)
    data_path.unlink(missing_ok=True)


def _get_total_cache_size() -> int:
    """获取缓存总大小（字节）"""
    cache_dir = _get_cache_dir()
    total = 0

    for file_path in cache_dir.glob("*.data"):
        try:
            total += file_path.stat().st_size
        except Exception:
            continue

    return total


def get_cache_stats() -> dict:
    """获取缓存统计信息

    Returns:
        包含缓存统计信息的字典
    """
    cache_dir = _get_cache_dir()
    total_size = _get_total_cache_size()
    file_count = len(list(cache_dir.glob("*.data")))

    return {
        'cache_dir': str(cache_dir),
        'file_count': file_count,
        'total_size': total_size,
        'total_size_mb': total_size / (1024 * 1024),
    }
