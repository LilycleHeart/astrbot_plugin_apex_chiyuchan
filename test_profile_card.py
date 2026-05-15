"""测试玩家详情卡片 Pillow 渲染"""
import asyncio
import sys
sys.path.insert(0, r"D:\opencode\chiyu\astrbot-plugin-apex-xiaochiyu")

from libs.image_renderer import draw_player_profile_card

DATA = {
    "name": "Liliumcordis",
    "tag": "YURI",
    "alias": "AncallBelle",
    "platform": "PC",
    "online_status": "offline",
    "uid": "1000392976892",
    "avatar_url": "https://secure.download.dm.origin.com/production/avatar/prod/1/599/208x208.JPEG",
    "level": 54,
    "prestige": 3,
    "level_pct": 53,

    "rank_name": "Platinum",
    "rank_div": 3,
    "rank_score": 9552,
    "rank_top_pct": "24.7",
    "rank_top_pct_global": "24.8",
    "rank_icon_url": "https://api.mozambiquehe.re/assets/ranks/platinum3.png",

    "kills": 27672,
    "damage": 3611374,
    "wins": 418,

    "selected_legend": {
        "name": "Mad Maggie",
        "stats": [
            {"name": "Passive", "value": "11,110s"},
            {"name": "Ultimate", "value": "24,424m"},
        ],
    },

    "top_legends": [
        {"name": "Wraith", "kills": 8942, "damage": 2389669, "wins": 288,
         "icon_url": "https://api.mozambiquehe.re/assets/icons/wraith.png"},
        {"name": "Horizon", "kills": 1972, "damage": 681475, "wins": 89,
         "icon_url": "https://api.mozambiquehe.re/assets/icons/horizon.png"},
        {"name": "Valkyrie", "kills": 762, "damage": 340477, "wins": 41,
         "icon_url": "https://api.mozambiquehe.re/assets/icons/valkyrie.png"},
        {"name": "Mirage", "kills": 311, "damage": 96096,
         "icon_url": "https://api.mozambiquehe.re/assets/icons/mirage.png"},
    ],

    "season_badges": [
        {"season": 6, "badge_url": "https://apexlegendsstatus.com/assets/badges/badges_new/you_re_tiering_me_apart_bronze_rs6.png"},
        {"season": 12, "badge_url": "https://apexlegendsstatus.com/assets/badges/badges_new/you_re_tiering_me_apart_master_rs12.png"},
        {"season": 15, "badge_url": "https://apexlegendsstatus.com/assets/badges/badges_new/you_re_tiering_me_apart_master_rs15.png"},
        {"season": 16, "badge_url": "https://apexlegendsstatus.com/assets/badges/badges_new/you_re_tiering_me_apart_diamond_rs16.png"},
        {"season": 17, "badge_url": "https://apexlegendsstatus.com/assets/badges/badges_new/you_re_tiering_me_apart_master_rs17.png"},
        {"season": 20, "badge_url": "https://apexlegendsstatus.com/assets/badges/badges_new/you_re_tiering_me_apart_diamond_rs20.png"},
        {"season": 24, "badge_url": "https://apexlegendsstatus.com/assets/badges/badges_new/you_re_tiering_me_apart_master_rs24.png"},
        {"season": 25, "badge_url": "https://apexlegendsstatus.com/assets/badges/badges_new/you_re_tiering_me_apart_master_rs25.png"},
        {"season": 27, "badge_url": "https://apexlegendsstatus.com/assets/badges/badges_new/you_re_tiering_me_apart_master_rs27.png"},
    ],

    "special_badges": [
        {"name": "Team. Work. Lv.3",
         "url": "https://apexlegendsstatus.com/assets/badges/badges_new/team._work._iii.png"},
        {"name": "Assassin Lv.4",
         "url": "https://apexlegendsstatus.com/assets/badges/badges_new/assassin_iv.png"},
        {"name": "Wraith's Wrath Lv.4",
         "url": "https://apexlegendsstatus.com/assets/badges/badges_new/legends_wrath_iv.png"},
    ],
}


async def main():
    png_bytes = await draw_player_profile_card(DATA)
    output = r"C:\Users\27280\AppData\Local\Temp\opencode\profile_card.png"
    with open(output, "wb") as f:
        f.write(png_bytes)
    print(f"Generated: {output} ({len(png_bytes)} bytes)")


asyncio.run(main())
