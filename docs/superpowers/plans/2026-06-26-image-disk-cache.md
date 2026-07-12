# 图片磁盘缓存实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为远程图片添加磁盘缓存，避免每次渲染都重新下载，提升渲染速度并减少网络请求。

**Architecture:** 创建独立的磁盘缓存模块 `disk_cache.py`，使用 URL 的 MD5 哈希作为文件名，支持 TTL 过期和自动清理。修改 `playwright_renderer.py` 中的 `_embed_images()` 函数，优先从磁盘缓存加载图片。

**Tech Stack:** Python 标准库 (`hashlib`, `pathlib`, `time`, `json`), 现有 `httpx` 依赖

## Global Constraints

- 缓存目录：`assets/image_cache/`
- 缓存格式：原始图片二进制 + 元数据 JSON
- 默认 TTL：7 天（可配置）
- 最大缓存大小：500MB（可配置）
- 缓存清理：LRU 策略，超过大小限制时清理最旧的文件

---

### Task 1: 创建磁盘缓存模块

**Files:**
- Create: `libs/disk_cache.py`

**Interfaces:**
- Produces: `get(key: str) -> bytes | None`, `set(key: str, value: bytes, ttl_seconds: int)`, `delete(key: str)`, `clear()`, `cleanup()`

- [ ] **Step 1: 创建磁盘缓存模块骨架**

```python
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


---

### Task 2: 修改 `_embed_images()` 集成磁盘缓存

**Files:**
- Modify: `libs/playwright_renderer.py:539-604`

**Interfaces:**
- Consumes: `disk_cache.get()`, `disk_cache.set()`
- Produces: 修改后的 `_embed_images()` 函数，优先从磁盘缓存加载图片

- [ ] **Step 1: 添加导入语句**

在 `playwright_renderer.py` 文件顶部添加导入：

```python
from . import disk_cache
```

- [ ] **Step 2: 修改 `_download_sync()` 函数**

将 `_download_sync()` 函数改为使用磁盘缓存：

```python
def _download_sync(url: str) -> str | None:
    """同步下载图片转base64，优先从磁盘缓存加载"""
    import httpx
    import asyncio
    
    # 尝试从磁盘缓存获取
    loop = asyncio.get_event_loop()
    try:
        cached_data = loop.run_until_complete(disk_cache.get(url))
        if cached_data:
            # 从缓存获取成功，直接转换为 base64
            stripped = cached_data.lstrip()
            mime = 'image/png'
            for prefix, m in _MIME_MAP.items():
                if stripped[:4].startswith(prefix) or stripped[:5].startswith(prefix):
                    mime = m
                    break
            b64 = base64.b64encode(cached_data).decode()
            return f"data:{mime};base64,{b64}"
    except Exception:
        pass
    
    # 缓存未命中，从网络下载
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://apexlegendsstatus.com/",
            "Accept": "image/svg+xml,image/png,image/*,*/*;q=0.8",
        }
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as c:
            r = c.get(url)
            r.raise_for_status()
            raw = r.content
            if not raw:
                return None
            
            # 写入磁盘缓存（7天过期）
            try:
                loop.run_until_complete(disk_cache.set(url, raw, 7 * 24 * 3600))
            except Exception:
                pass  # 缓存写入失败不影响主流程
            
            stripped = raw.lstrip()
            mime = 'image/png'
            for prefix, m in _MIME_MAP.items():
                if stripped[:4].startswith(prefix) or stripped[:5].startswith(prefix):
                    mime = m
                    break
            b64 = base64.b64encode(raw).decode()
            return f"data:{mime};base64,{b64}"
    except Exception as e:
        from astrbot.api import logger
        logger.warning(f"[Renderer] 下载失败 {url[:80]}: {e}")
        return None
```

- [ ] **Step 3: 优化 `_embed_images()` 函数**

修改 `_embed_images()` 函数，移除内存缓存逻辑，完全依赖磁盘缓存：

```python
async def _embed_images(html: str) -> str:
    """将远程图片URL替换为base64 data URI（使用磁盘缓存）"""
    urls = set()
    urls.update(re.findall(r'src="(https?://[^"]+)"', html))
    urls.update(re.findall(r'url\((https?://[^)]+)\)', html))

    if not urls:
        return html

    # 并发下载所有图片（磁盘缓存会自动处理缓存命中）
    async def _fetch(url):
        loop = asyncio.get_running_loop()
        b64 = await loop.run_in_executor(None, _download_sync, url)
        return url, b64

    results = await asyncio.gather(*[_fetch(u) for u in urls], return_exceptions=True)
    
    # 构建替换映射
    replacements = {}
    for result in results:
        if isinstance(result, Exception):
            continue
        url, b64 = result
        if b64:
            replacements[url] = b64

    # 执行替换
    def _replace(m):
        url = m.group(1)
        return m.group(0).replace(url, replacements.get(url, url))

    html = re.sub(r'src="(https?://[^"]+)"', _replace, html)
    html = re.sub(r'url\((https?://[^)]+)\)', _replace, html)
    return html
```

- [ ] **Step 4: 删除旧的内存缓存变量**

删除 `playwright_renderer.py:539` 行的 `_image_cache: dict[str, str] = {}` 变量定义。

- [ ] **Step 5: 验证修改**

运行测试脚本验证修改是否正确：

```bash
cd D:\opencode\chiyu\astrbot_plugin_apex_chiyuchan
python -c "from libs.playwright_renderer import _embed_images; print('导入成功')"
```

- [ ] **Step 6: Commit**

```bash
git add libs/disk_cache.py libs/playwright_renderer.py
git commit -m "feat: 添加图片磁盘缓存，避免每次渲染重新下载"
```

---

### Task 3: 添加缓存管理命令

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `disk_cache.clear()`, `disk_cache.cleanup()`, `disk_cache.get_cache_stats()`
- Produces: 新增 `/apex cache` 命令用于管理缓存

- [ ] **Step 1: 在 `main.py` 中添加缓存管理命令**

在 `main.py` 的命令处理部分添加缓存管理命令：

```python
@command(
    name="apex cache",
    description="管理 Apex 图片缓存",
    usage="/apex cache [stats|clear|cleanup]",
)
async def apex_cache(self, event: AstrMessageEvent, action: str = "stats"):
    """管理 Apex 图片缓存"""
    from .libs import disk_cache
    
    if action == "stats":
        stats = disk_cache.get_cache_stats()
        msg = (
            f"📊 图片缓存统计\n"
            f"缓存目录: {stats['cache_dir']}\n"
            f"文件数量: {stats['file_count']}\n"
            f"总大小: {stats['total_size_mb']:.1f} MB"
        )
        yield event.plain_result(msg)
    
    elif action == "clear":
        await disk_cache.clear()
        yield event.plain_result("✅ 图片缓存已清空")
    
    elif action == "cleanup":
        cleaned = await disk_cache.cleanup()
        yield event.plain_result(f"✅ 缓存清理完成，清理了 {cleaned} 个文件")
    
    else:
        yield event.plain_result("❌ 未知操作，可用: stats, clear, cleanup")
```

- [ ] **Step 2: 验证命令注册**

运行以下命令验证命令是否正确注册：

```bash
cd D:\opencode\chiyu\astrbot_plugin_apex_chiyuchan
python -c "from main import ApexPlugin; print('命令注册成功')"
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: 添加 /apex cache 命令用于管理图片缓存"
```

---

### Task 4: 添加启动时自动清理

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `disk_cache.cleanup()`
- Produces: 插件启动时自动清理过期缓存

- [ ] **Step 1: 在插件初始化中添加自动清理**

在 `main.py` 的 `__init__` 或 `setup` 方法中添加启动时清理：

```python
async def setup(self):
    """插件初始化"""
    from .libs import disk_cache
    
    # 启动时清理过期缓存
    try:
        cleaned = await disk_cache.cleanup()
        if cleaned > 0:
            logger.info(f"[Apex] 启动时清理了 {cleaned} 个过期缓存文件")
    except Exception as e:
        logger.warning(f"[Apex] 缓存清理失败: {e}")
    
    # 其他初始化代码...
```

- [ ] **Step 2: 验证启动清理**

运行以下命令验证启动清理逻辑：

```bash
cd D:\opencode\chiyu\astrbot_plugin_apex_chiyuchan
python -c "
import asyncio
from libs import disk_cache

async def test():
    cleaned = await disk_cache.cleanup()
    print(f'清理了 {cleaned} 个文件')

asyncio.run(test())
"
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: 插件启动时自动清理过期缓存"
```

---

### Task 5: 测试完整流程

**Files:**
- Create: `scripts/test_disk_cache.py`

**Interfaces:**
- Consumes: 所有已实现的缓存功能
- Produces: 验证磁盘缓存功能正常工作

- [ ] **Step 1: 创建测试脚本**

```python
"""测试磁盘缓存功能"""

import asyncio
import time
from pathlib import Path

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from libs import disk_cache


async def test_basic_operations():
    """测试基本操作"""
    print("🧪 测试基本操作...")
    
    # 测试写入
    test_key = "https://example.com/test.png"
    test_data = b"fake image data"
    
    result = await disk_cache.set(test_key, test_data, ttl_seconds=60)
    assert result, "写入应该成功"
    print("  ✅ 写入成功")
    
    # 测试读取
    cached = await disk_cache.get(test_key)
    assert cached == test_data, "读取的数据应该一致"
    print("  ✅ 读取成功")
    
    # 测试删除
    await disk_cache.delete(test_key)
    cached = await disk_cache.get(test_key)
    assert cached is None, "删除后应该返回 None"
    print("  ✅ 删除成功")
    
    print("✅ 基本操作测试通过\n")


async def test_ttl_expiration():
    """测试 TTL 过期"""
    print("🧪 测试 TTL 过期...")
    
    test_key = "https://example.com/test_ttl.png"
    test_data = b"ttl test data"
    
    # 写入 1 秒过期的缓存
    await disk_cache.set(test_key, test_data, ttl_seconds=1)
    
    # 立即读取应该成功
    cached = await disk_cache.get(test_key)
    assert cached is not None, "立即读取应该成功"
    print("  ✅ 立即读取成功")
    
    # 等待过期
    await asyncio.sleep(1.1)
    
    # 过期后读取应该返回 None
    cached = await disk_cache.get(test_key)
    assert cached is None, "过期后应该返回 None"
    print("  ✅ 过期后返回 None")
    
    print("✅ TTL 过期测试通过\n")


async def test_cleanup():
    """测试清理功能"""
    print("🧪 测试清理功能...")
    
    # 写入一些测试数据
    for i in range(5):
        await disk_cache.set(
            f"https://example.com/cleanup_{i}.png",
            b"test data" * 100,
            ttl_seconds=1
        )
    
    # 等待过期
    await asyncio.sleep(1.1)
    
    # 清理
    cleaned = await disk_cache.cleanup()
    assert cleaned >= 5, f"应该清理至少 5 个文件，实际清理了 {cleaned}"
    print(f"  ✅ 清理了 {cleaned} 个文件")
    
    # 检查统计
    stats = disk_cache.get_cache_stats()
    print(f"  📊 缓存统计: {stats['file_count']} 个文件, {stats['total_size_mb']:.2f} MB")
    
    print("✅ 清理功能测试通过\n")


async def test_large_file():
    """测试大文件缓存"""
    print("🧪 测试大文件缓存...")
    
    test_key = "https://example.com/large.png"
    # 创建 1MB 的测试数据
    test_data = b"x" * (1024 * 1024)
    
    # 写入
    result = await disk_cache.set(test_key, test_data, ttl_seconds=60)
    assert result, "大文件写入应该成功"
    print("  ✅ 大文件写入成功")
    
    # 读取
    cached = await disk_cache.get(test_key)
    assert cached == test_data, "大文件读取应该成功"
    print("  ✅ 大文件读取成功")
    
    # 清理
    await disk_cache.delete(test_key)
    
    print("✅ 大文件缓存测试通过\n")


async def main():
    """运行所有测试"""
    print("🚀 开始测试磁盘缓存功能\n")
    
    await test_basic_operations()
    await test_ttl_expiration()
    await test_cleanup()
    await test_large_file()
    
    # 最终清理
    await disk_cache.clear()
    
    print("🎉 所有测试通过！")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 运行测试**

```bash
cd D:\opencode\chiyu\astrbot_plugin_apex_chiyuchan
python scripts/test_disk_cache.py
```

预期输出：
```
🚀 开始测试磁盘缓存功能

🧪 测试基本操作...
  ✅ 写入成功
  ✅ 读取成功
  ✅ 删除成功
✅ 基本操作测试通过

🧪 测试 TTL 过期...
  ✅ 立即读取成功
  ✅ 过期后返回 None
✅ TTL 过期测试通过

🧪 测试清理功能...
  ✅ 清理了 5 个文件
  📊 缓存统计: 0 个文件, 0.00 MB
✅ 清理功能测试通过

🧪 测试大文件缓存...
  ✅ 大文件写入成功
  ✅ 大文件读取成功
✅ 大文件缓存测试通过

🎉 所有测试通过！
```

- [ ] **Step 3: Commit**

```bash
git add scripts/test_disk_cache.py
git commit -m "test: 添加磁盘缓存功能测试脚本"
```

---

### Task 6: 更新文档

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: 更新 README 文档，说明新的缓存功能

- [ ] **Step 1: 在 README.md 中添加缓存说明**

在 README.md 的适当位置添加：

```markdown
## 图片缓存

插件现在支持图片磁盘缓存，可以避免每次渲染都重新下载远程图片，显著提升渲染速度。

### 缓存配置

- **缓存目录**: `assets/image_cache/`
- **默认 TTL**: 7 天
- **最大缓存大小**: 500MB

### 缓存管理命令

使用 `/apex cache` 命令管理缓存：

- `/apex cache stats` - 查看缓存统计信息
- `/apex cache clear` - 清空所有缓存
- `/apex cache cleanup` - 清理过期和超限缓存

### 自动清理

插件启动时会自动清理过期缓存，无需手动干预。
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: 更新文档，说明图片缓存功能"
```
