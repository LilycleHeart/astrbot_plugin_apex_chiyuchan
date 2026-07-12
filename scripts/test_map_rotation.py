#!/usr/bin/env python3
"""测试地图轮换 API 数据"""
import sys
import asyncio
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Stub astrbot modules
astrbot_pkg = types.ModuleType("astrbot")
astrbot_api = types.ModuleType("astrbot.api")
class _L:
    @staticmethod
    def info(msg, *a, **kw): print(f"[INFO] {msg}")
    @staticmethod
    def warning(msg, *a, **kw): print(f"[WARN] {msg}")
    @staticmethod
    def error(msg, *a, **kw): print(f"[ERR]  {msg}")
    @staticmethod
    def debug(msg, *a, **kw): pass
astrbot_api.logger = _L()
astrbot_pkg.api = astrbot_api
sys.modules["astrbot"] = astrbot_pkg
sys.modules["astrbot.api"] = astrbot_api

API_KEY = "796c7ebc049ebf34b1b4c7b93b8a0960"

import types

async def main():
    import httpx
    
    headers = {"Authorization": API_KEY, "User-Agent": "ApexChiyuchan/1.0"}
    
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        r = await client.get(
            "https://api.mozambiquehe.re/maprotation",
            params={"version": "2"},
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
        
        print("=== 外卡模式 (Wildcard) ===")
        wildcard = data.get("wildcard", {})
        print(json.dumps(wildcard, indent=2, ensure_ascii=False))
        
        print("\n=== 混合模式 (LTM) ===")
        ltm = data.get("ltm", {})
        print(json.dumps(ltm, indent=2, ensure_ascii=False))
        
        print("\n=== 匹配模式 (Battle Royale) ===")
        br = data.get("battle_royale", {})
        print(json.dumps(br.get("current", {}), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
