"""测试磁盘缓存功能"""

import asyncio
import sys
import time
from pathlib import Path

# 设置标准输出编码为 UTF-8
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# 添加项目根目录到路径
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
