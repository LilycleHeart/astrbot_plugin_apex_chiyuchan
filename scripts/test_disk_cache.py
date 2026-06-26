"""测试磁盘缓存功能（永久缓存）"""

import asyncio
import sys
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
    
    result = await disk_cache.set(test_key, test_data)
    assert result, "写入应该成功"
    print("  ✅ 写入成功")
    
    # 测试读取
    cached = await disk_cache.get(test_key)
    assert cached == test_data, "读取的数据应该一致"
    print("  ✅ 读取成功")
    
    # 测试重复写入（应该跳过）
    result2 = await disk_cache.set(test_key, b"new data")
    assert result2, "重复写入应该返回 True"
    cached2 = await disk_cache.get(test_key)
    assert cached2 == test_data, "重复写入不应覆盖已有数据"
    print("  ✅ 重复写入跳过")
    
    # 测试删除
    await disk_cache.delete(test_key)
    cached = await disk_cache.get(test_key)
    assert cached is None, "删除后应该返回 None"
    print("  ✅ 删除成功")
    
    print("✅ 基本操作测试通过\n")


async def test_persistence():
    """测试永久保存"""
    print("🧪 测试永久保存...")
    
    test_key = "https://example.com/persistent.png"
    test_data = b"persistent data"
    
    # 写入
    await disk_cache.set(test_key, test_data)
    
    # 立即读取应该成功
    cached = await disk_cache.get(test_key)
    assert cached is not None, "立即读取应该成功"
    assert cached == test_data, "数据应该一致"
    print("  ✅ 数据永久保存")
    
    # 清理测试数据
    await disk_cache.delete(test_key)
    
    print("✅ 永久保存测试通过\n")


async def test_cleanup():
    """测试大小限制清理"""
    print("🧪 测试大小限制清理...")
    
    # 写入一些测试数据
    for i in range(5):
        await disk_cache.set(
            f"https://example.com/cleanup_{i}.png",
            b"test data" * 100
        )
    
    # 检查统计
    stats = disk_cache.get_cache_stats()
    print(f"  📊 缓存统计: {stats['file_count']} 个文件, {stats['total_size_mb']:.2f} MB")
    
    # 清理（设置很小的限制应该触发清理）
    cleaned = await disk_cache.cleanup(max_size=100)
    print(f"  ✅ 清理了 {cleaned} 个文件")
    
    # 清空所有
    await disk_cache.clear()
    stats = disk_cache.get_cache_stats()
    print(f"  📊 清空后: {stats['file_count']} 个文件")
    
    print("✅ 大小限制清理测试通过\n")


async def test_large_file():
    """测试大文件缓存"""
    print("🧪 测试大文件缓存...")
    
    test_key = "https://example.com/large.png"
    # 创建 1MB 的测试数据
    test_data = b"x" * (1024 * 1024)
    
    # 写入
    result = await disk_cache.set(test_key, test_data)
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
    print("🚀 开始测试磁盘缓存功能（永久缓存）\n")
    
    await test_basic_operations()
    await test_persistence()
    await test_cleanup()
    await test_large_file()
    
    # 最终清理
    await disk_cache.clear()
    
    print("🎉 所有测试通过！")


if __name__ == "__main__":
    asyncio.run(main())
