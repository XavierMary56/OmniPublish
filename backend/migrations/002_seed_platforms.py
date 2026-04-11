#!/usr/bin/env python3
"""OmniPublish V2.0 — 初始化 35 个平台种子数据"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database import get_pool, init_db

PLATFORMS = [
    {"name": "男同网",        "dept": "1部4组", "categories": ["同性","视频"]},
    {"name": "91视频web",     "dept": "1部4组", "categories": ["今日吃瓜","网红黑料","热门大瓜","学生校园"]},
    {"name": "黑料情报局",    "dept": "1部4组", "categories": ["今日吃瓜","黑料爆料","网红八卦"]},
    {"name": "91短视频",      "dept": "1部3组", "categories": ["热门","推荐"]},
    {"name": "91porn",        "dept": "1部3组", "categories": []},
    {"name": "9色视频",       "dept": "1部3组", "categories": ["今日吃瓜","热门大瓜"]},
    {"name": "YouTube",       "dept": "1部3组", "categories": []},
    {"name": "91av",          "dept": "1部2组", "categories": ["推荐","热门"]},
    {"name": "91暗网",        "dept": "1部2组", "categories": []},
    {"name": "海角社区",      "dept": "1部2组", "categories": ["今日吃瓜","校园","网红黑料","热门大瓜"]},
    {"name": "妻友",          "dept": "1部2组", "categories": ["投稿","原创"]},
    {"name": "色花堂",        "dept": "2部1组", "categories": ["原创","转载"]},
    {"name": "TikTok成人版",  "dept": "2部1组", "categories": []},
    {"name": "91hub",         "dept": "3部2组", "categories": ["视频","图文"]},
    {"name": "第一吃瓜网",    "dept": "3部2组", "categories": ["吃瓜","黑料","校园"]},
    {"name": "抖阴",          "dept": "3部3组", "categories": ["推荐","热门"]},
    {"name": "海角社区web-b", "dept": "3部3组", "categories": ["今日吃瓜","校园"]},
    {"name": "草榴社区",      "dept": "3部5组", "categories": ["原创","转载","技术讨论"]},
    {"name": "51成人破解",    "dept": "4部1组", "categories": []},
    {"name": "91抖阴",        "dept": "4部1组", "categories": ["推荐"]},
    {"name": "推特社区",      "dept": "4部1组", "categories": []},
    {"name": "糖心",          "dept": "4部1组", "categories": ["今日吃瓜","热门大瓜","网红黑料"]},
    {"name": "51tkitok破解",  "dept": "4部2组", "categories": []},
    {"name": "pornhub免费版", "dept": "4部2组", "categories": []},
    {"name": "xivdeo免费版",  "dept": "4部2组", "categories": []},
    {"name": "黄色仓库",      "dept": "4部2组", "categories": []},
    {"name": "51看片",        "dept": "4部2组", "categories": []},
    {"name": "51av",          "dept": "4部2组", "categories": []},
    {"name": "尤物百科",      "dept": "4部2组", "categories": ["推荐"]},
    {"name": "小蓝视频网",    "dept": "5部1组", "categories": ["热门","推荐"]},
    {"name": "GossipLust",    "dept": "5部2组", "categories": ["gossip","leaked"]},
    {"name": "玩物社区",      "dept": "5部2组", "categories": ["原创","投稿"]},
    {"name": "黑料吃瓜网",    "dept": "5部3组", "categories": ["吃瓜","黑料","网红"]},
    {"name": "18黑料",        "dept": "5部3组", "categories": ["吃瓜","黑料"]},
    {"name": "海角社区 web",  "dept": "5部4组", "categories": ["今日吃瓜","校园","网红黑料"]},
]


async def seed():
    await init_db()
    pool = await get_pool()
    async with pool.acquire() as conn:
        for p in PLATFORMS:
            await conn.execute(
                """INSERT INTO platforms (name, dept, categories)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (name) DO NOTHING""",
                p["name"], p["dept"], json.dumps(p["categories"], ensure_ascii=False),
            )

        count = await conn.fetchval("SELECT COUNT(*) FROM platforms")
        print(f"[SEED] Platforms: {count} total ({len(PLATFORMS)} in seed)")


if __name__ == "__main__":
    asyncio.run(seed())
