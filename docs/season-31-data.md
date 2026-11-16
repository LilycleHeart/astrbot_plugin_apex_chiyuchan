# Season 31「破译天机」(Cipher) 赛季数据核实报告

> 调研日期：2026-11-16（Asia/Shanghai）
> 用途：为 `libs/season_scraper.py` 的硬编码赛季日期（当前仍为 Season 30「诸神烙印」Marked）提供 Season 31 的替换数据。
> 本文件为纯调研产出，未修改任何源码。

---

## 一、结论速览

| 字段 | 值（UTC） | 值（北京时间 Asia/Shanghai） | 置信度 | 性质 |
| --- | --- | --- | --- | --- |
| 英文赛季名 | `Cipher` | — | 高 | 官方确认 |
| 官方简体中文名 | `破译天机` | — | 高 | 官方确认（EA 官方中文站） |
| `season_start` | 2026-11-03 18:00 UTC | 2026-11-04 02:00 | 高 | 官方确认（商店 SKU 时间戳） |
| `split1_end` | 2026-12-15 18:00 UTC | 2026-12-16 02:00 | 高 | 官方确认（通行证售卖截止 + ALS 倒计时） |
| `season_end` | 2027-02-09 18:00 UTC | 2027-02-10 02:00 | 中 | **预估**（日期来自 wiki，时刻为惯例推定） |

**给 `season_scraper.py` 的建议值（UTC）：**

```python
_SPLIT_DATES_S31 = {
    "season_start": _dt.datetime(2026, 11, 3, 18, 0, tzinfo=_UTC),
    "split1_end":   _dt.datetime(2026, 12, 15, 18, 0, tzinfo=_UTC),
    "season_end":   _dt.datetime(2027, 2, 9, 18, 0, tzinfo=_UTC),
}
```

> ⚠️ **关键修正**：仓库现有注释写「Apex 更新惯例为 17:00 UTC」，那是**夏令时（PDT, UTC-7）**时期的换算。Season 31 于 2026-11-03 开赛，此时美国已于 **2026-11-01 结束夏令时**，太平洋时间回到 **PST = UTC-8**，因此 10:00 PT = **18:00 UTC**（北京次日 02:00），比夏季晚 1 小时。Season 30 的 17:00 UTC 是 8 月（PDT）的正确换算，Season 31 必须改成 18:00 UTC。

---

## 二、英文名与中文译名

### 2.1 英文名：`Cipher`（确认）

- EA 官方补丁说明标题即 `Apex Legends™: Cipher Patch Notes`（2026-11-02 发布）。
- Apex Legends Wiki 的 Season 31 页面 infobox 与正文均写作 *Cipher*。
- 拼写无歧义，非 *Cypher*（部分第三方站点如 esportstales 误写为 "Cypher"，属笔误，不予采信）。

### 2.2 官方简体中文名：`破译天机`（官方确认，非意译候选）

**这是本次调研最重要的发现：Season 31 有 EA 官方简体中文译名，不需要自创意译。**

证据链：

1. **EA 官方中文站（繁体）** 的补丁说明页标题为《Apex 英雄：**破譯天機**》改版資訊，正文首句「《Apex 英雄：破譯天機》登場！」。
   <https://www.ea.com/zh-hant/games/apex-legends/apex-legends/news/cipher-patch-notes>
2. **EA 官方中文站（繁体）赛季专题页** 标题《Apex 英雄：破譯天機》，副标题「在《Apex 英雄：破譯天機》中駭入戰鬥」。
   <https://www.ea.com/zh-hant/games/apex-legends/apex-legends/seasons/cipher>
3. **EA Help 简体中文支持文章**（这是**简体**官方文本，直接给出简体译名）：「《Apex Legends》最新赛季"**破译天机**"将于 2026 年 11 月 3 日开启。」并在过往赛季列表中写作「诸神烙印（第 30 赛季）」「超频（第 29 赛季）」——与仓库 `SEASON_NAME_ZH` 的历史译名完全一致，说明该表本就以 EA 官方中文名为准。
   <https://help.ea.com/zh/articles/apex-legends/seasons-and-updates/>
4. 中文媒体一致沿用该官方译名：游侠网《Apex英雄：破译天机》11 月 3 日上线、17173、TapTap 官方社区、VeryApex、Steam 中文社区等。

**结论**：`SEASON_NAME_ZH` 应新增 `"Cipher": "破译天机"`。

### 2.3 备选意译（仅作记录，不推荐使用）

若未来某赛季确实没有官方译名，可参考以下思路；但 Season 31 已有官方名，**不应采用**：

| 候选 | 理由 | 问题 |
| --- | --- | --- |
| 密文 / 密码 | cipher 的字面义，直白 | 过于平淡，缺少赛季主题的「情报战」张力 |
| 暗码 | 呼应本赛季主角密客（Crypto）与「情报即武器」主题 | 与官方名冲突 |
| 破译天机 | **官方译名**，取「破解天机、抢占先机」之意 | — |

---

## 三、三个时间点的推导与依据

### 3.1 `season_start` = 2026-11-03 18:00 UTC（北京 2026-11-04 02:00）

**DST 校验**：美国 2026 年夏令时于 **2026-11-01** 结束（2:00 AM PDT → 1:00 AM PST）。2026-11-03 处于 **PST（UTC-8）**。Apex 赛季更新惯例为太平洋时间 10:00 AM，故：

```
10:00 PST (UTC-8) = 18:00 UTC = 北京时间 2026-11-04 02:00
```

（若按夏季 PDT/UTC-7 换算才会得到 17:00 UTC / 北京 01:00 —— 这正是仓库旧注释的来源，Season 31 不适用。）

**证据：**

| 来源 | 内容 | 分级 |
| --- | --- | --- |
| Microsoft Store 商品 API（Cipher Ultimate+ Battle Pass Split 1，ProductId `9PHG4V7CMHJD`） | SKU `StartDate: "2026-11-03T18:00:00Z"` —— **机器可读的官方商店时间戳，最硬证据** | 官方确认 |
| <https://apexranked.com/apex-season-31> | "Season 31 started Tuesday, November 3, 2026 at 10:00 AM PST (6:00 PM UTC)"，并列出各城市对照（London 6:00 PM、Tokyo Wed 3:00 AM） | 媒体（与官方一致） |
| <https://clip.dor.gg/zh-CN/blog/apex-new-season> | 「美国夏令时已在 11 月 1 日结束，换算北京时间是 11 月 4 日（周三）凌晨 2 点……网上有些时间表仍按夏令时换算，会差 1 小时」 | 媒体（明确点出 DST 陷阱） |
| <https://www.ea.com/games/apex-legends/apex-legends/news/cipher-patch-notes> | "Season 31 begins on November 3rd"（只给日期，未给时刻） | 官方确认（日期） |
| <https://help.ea.com/en/articles/apex-legends/seasons-and-updates/> | "Cipher, the newest Season of Apex Legends, launches on November 3, 2026"（只给日期） | 官方确认（日期） |

> 注：EA 官方公告**从不公布具体开服时刻**，只给日期。18:00 UTC 的依据是「官方商店 SKU 时间戳 + 10:00 PT 惯例 + DST 校验」三者吻合。

### 3.2 `split1_end` = 2026-12-15 18:00 UTC（北京 2026-12-16 02:00）

**证据：**

| 来源 | 内容 | 分级 |
| --- | --- | --- |
| Microsoft Store 商品 API（同上 SKU） | `EndDate: "2026-12-15T17:59:59Z"`（即 18:00 UTC 截止） | 官方确认 |
| PlayStation Store（Cipher Ultimate+ Battle Pass Split 1） | "The \"Cipher\" Ultimate+ Battle Pass Split 1 is available until **December 15th, 2026 10 AM PT**." | 官方确认 |
| Xbox Store（Cipher Ultimate Battle Pass Split 1） | "available until December 15th, 2026 at 10 AM PT" | 官方确认 |
| <https://apexlegendsstatus.com/new-season-countdown.php> | 页面内嵌 `let startTime = 1797357600;` → 换算 UTC **2026-12-15 18:00:00**（周二），页面渲染为 "Releases 16/12 @ 02:00"（本地时区北京） | 社区权威（ALS） |
| <https://blog.gamee.games/apex-season31-split1-end-date-2026/> | 「スプリット1終了：日本時間 2026年12月16日（水）午前3:00（太平洋標準時 12月15日 10:00 AM PST）」，并说明依据是 PS/Xbox 商店「Cipher Ultimate Battle Pass Split 1」商品页的售卖截止 | 媒体（与官方商店一致） |
| <https://www.propelrc.com/apex-legends-next-season-start-date/> | "Season 31 Split 1 reset is scheduled for December 15, 2026, around 10:00 AM, per EA Help and the Apex Legends Status tracker" | 媒体 |

**换算校验**：`1797357600` → UTC `2026-12-15 18:00:00`（周二）→ 北京 `2026-12-16 02:00`（周三）→ JST `2026-12-16 03:00`。与日媒「12月16日午前3:00」完全吻合，交叉验证通过。

**Split 1 时长**：2026-11-03 → 2026-12-15 = **42 天（6 周整）**，与 Apex 惯例（约 6 周）一致。

### 3.3 `season_end` = 2027-02-09 18:00 UTC（北京 2027-02-10 02:00）—— **预估**

**日期部分（2027-02-09）来源：**

| 来源 | 内容 | 分级 |
| --- | --- | --- |
| <https://apexlegends.wiki.gg/wiki/Season_31> | infobox `End date: February 9, 2027`；正文 "will be ended on February 9, 2027" | 社区 wiki（非官方，但为最常被引用的赛季表） |
| <https://apexseasons.online/seasons/season-31-cipher/> | "Ends Feb 9, 2027"，Duration 98 days，Data Confidence: **medium**；并明确 "February 9, 2027 at 18:00 UTC is a planning estimate using the 14-week length of recent November seasons, not an announced Season 32 release" | 媒体预估（自述为 estimate） |

**时刻部分（18:00 UTC）**：EA **未公布** Season 31 结束时刻。采用 18:00 UTC 的理由：
1. 与 `season_start` / `split1_end` 同为 PST 时期 10:00 AM PT 的换算结果，赛季切换与 Split 切换在 Apex 中始终同一时刻；
2. 2027-02-09 仍处于 PST（美国 2027 年夏令时 3 月才开始），故 10:00 PT = 18:00 UTC。

**矛盾来源（必须记录）：**

| 来源 | 给出的结束日 | 说明 |
| --- | --- | --- |
| wiki.gg / apexseasons.online | **2027-02-09** | 98 天赛季长度（14 周），与近期 11 月赛季节奏一致 |
| <https://ggseason.com/apex/> | 2027-02-02（EST.） | 按「约 3 个月」粗估，未考虑 14 周 |
| <https://boostroyal.com/apex-season> | 2027-02-02（expected） | 同上，且自述 "Respawn has not published an end date" |
| <https://apexdb.gg/season/season-31/> | 区间 2027-01-25 ~ 2027-02-08 | 按 83~97 天区间推算，明确 "That's an estimate, not EA's date" |
| <https://blog.gamee.games/apex-season32-when-2027/> | 2027-02-03（JST 03:00） | 由 Split 1 结束 + 7 周推算 |
| <https://www.esportstales.com/apex-legends/season-end-date> | "around mid February, 2027" | 只给模糊区间 |

**最终采信**：`2027-02-09 18:00 UTC`。理由：wiki.gg 的 2/9 与 98 天（14 周）赛季长度自洽，且 11 月开赛的赛季历史上多为 14 周（如 Season 23 From the Rift 97 天、Season 27 Amped 98 天）；其余站点多为「3 个月」粗估。**但必须标注为预估，EA 未确认。**

---

## 四、完整来源清单

抓取时间均为 **2026-11-16 15:00–15:25 (Asia/Shanghai)**。

### 官方（EA / Respawn / 平台商店）

| # | URL | 提供的信息 | 分级 |
| --- | --- | --- | --- |
| 1 | <https://www.ea.com/games/apex-legends/apex-legends/news/cipher-patch-notes> | 赛季名 Cipher；"Season 31 begins on November 3rd"；Split 1 内容 | 官方确认 |
| 2 | <https://www.ea.com/zh-hant/games/apex-legends/apex-legends/news/cipher-patch-notes> | **官方中文名《Apex 英雄：破譯天機》** | 官方确认 |
| 3 | <https://www.ea.com/zh-hant/games/apex-legends/apex-legends/seasons/cipher> | 官方中文赛季专题页《Apex 英雄：破譯天機》 | 官方确认 |
| 4 | <https://help.ea.com/zh/articles/apex-legends/seasons-and-updates/> | **简体官方文本「破译天机」**；过往赛季中文名表（诸神烙印/超频…） | 官方确认 |
| 5 | <https://help.ea.com/en/articles/apex-legends/seasons-and-updates/> | "Cipher … launches on November 3, 2026"；Season 30 Marked 结束于 2026-11-02 | 官方确认 |
| 6 | <https://www.ea.com/games/apex-legends/apex-legends/news/cipher-game-updates> | 2026-10-29 玩法预告（Crypto 重做、Akimbo Wingman、Strongholds） | 官方确认 |
| 7 | Microsoft Store 商品 API `https://storeedgefd.dsx.mp.microsoft.com/v9.0/products/9PHG4V7CMHJD?market=US&locale=en-US&deviceFamily=Windows.Xbox` | **`StartDate 2026-11-03T18:00:00Z` / `EndDate 2026-12-15T17:59:59Z`** | 官方确认（机器可读） |
| 8 | <https://store.playstation.com/en-us/product/UP0006-CUSA12540_00-S310ULTIMATEPLUS> | "available until December 15th, 2026 10 AM PT" | 官方确认 |
| 9 | <https://www.xbox.com/en-US/games/store/apex-legends-cipher-ultimate-battle-pass-split-1/9nwbnp4lxq86> | "available until December 15th, 2026 at 10 AM PT" | 官方确认 |

### 社区 / 媒体（交叉验证）

| # | URL | 提供的信息 | 分级 |
| --- | --- | --- | --- |
| 10 | <https://apexlegends.wiki.gg/wiki/Season_31> | Start 2026-11-03 / End **2027-02-09**；主题 Nanite；Reactive Wingman | 社区 wiki |
| 11 | <https://apexlegendsstatus.com/new-season-countdown.php> | `startTime = 1797357600` → 2026-12-15 18:00 UTC；"Season 31 : Cipher, split 1" | 社区权威（ALS） |
| 12 | <https://apexranked.com/apex-season-31> | "10:00 AM PST (6:00 PM UTC)"，各城市时刻表 | 媒体（与官方一致） |
| 13 | <https://apexranked.com/apex-ranked-reset> | "Season 31 Split 1 Started Nov 3, 2026 10:00 AM PST"；"next reset time has not been confirmed" | 媒体 |
| 14 | <https://clip.dor.gg/zh-CN/blog/apex-new-season> | 北京 11-04 02:00；明确 DST 陷阱说明 | 媒体（中文） |
| 15 | <https://blog.gamee.games/apex-season31-split1-end-date-2026/> | Split 1 结束 JST 2026-12-16 03:00（= PST 12-15 10:00） | 媒体（日文） |
| 16 | <https://blog.gamee.games/apex-season32-when-2027/> | S32 预估 2027-02-03 JST（= 02-02 10:00 PST） | 媒体预估 |
| 17 | <https://apexseasons.online/seasons/season-31-cipher/> | End Feb 9 2027 18:00 UTC（自述 estimate，confidence medium） | 媒体预估 |
| 18 | <https://apexdb.gg/season/season-31/> | "EA hasn't said when Season 31 ends"；区间 2027-01-25 ~ 02-08 | 媒体预估 |
| 19 | <https://ggseason.com/apex/> | 预估 2027-02-02 | 媒体预估 |
| 20 | <https://boostroyal.com/apex-season> | 预估 2027-02-02；"Respawn has not published an end date" | 媒体预估 |
| 21 | <https://www.esportstales.com/apex-legends/season-end-date> | "around mid February, 2027"；赛季起止表（S31 写作 "Cypher"，笔误） | 媒体预估 |
| 22 | <https://www.propelrc.com/apex-legends-next-season-start-date/> | Split 1 reset 2026-12-15 约 10:00 AM | 媒体 |
| 23 | <https://www.ali213.net/news/html/2026-10/1050531.html> | 游侠网：《Apex英雄：破译天机》11 月 3 日上线（官方稿件转载） | 媒体（中文） |
| 24 | <https://www.taptap.cn/moment/866656388753919185> | TapTap：新赛季「破译天机」正式上线 | 媒体（中文） |

### 抓取失败 / 不可用（记录以便复现）

- `https://dotesports.com/apex-legends/news/start-end-dates-apex-legends-seasons` → HTTP 403（反爬），未能取得赛季起止表。
- `https://liquipedia.net/apexlegends/Season_31` → Cloudflare 人机验证，未取得内容。
- `https://apexlegends.wiki.gg/wiki/Season_31?action=raw` / `api.php` / `Special:Export` → HTTP 403，只能读渲染后的 HTML。
- `https://apexlegendsstatus.com/new-season-countdown`（无 `.php`）→ HTTP 406，必须用 `.php` 变体。
- `https://psdeals.net` / `https://xbdeals.net` 搜索页 → HTTP 403。
- `https://www.trueachievements.com/products/...` → HTTP 403。

---

## 五、与仓库现状的差异（供改代码时参考）

| 项 | 仓库当前（Season 30） | Season 31 应为 |
| --- | --- | --- |
| `season_number` | 30 | **31** |
| `season_name` | 诸神烙印 | **破译天机** |
| `SEASON_NAME_ZH` | 无 `Cipher` 键 | 新增 `"Cipher": "破译天机"` |
| `season_start` | 2026-08-04 17:00 UTC | **2026-11-03 18:00 UTC** |
| `split1_end` | 2026-09-15 17:00 UTC | **2026-12-15 18:00 UTC** |
| `season_end` | 2026-11-03 17:00 UTC | **2027-02-09 18:00 UTC**（预估） |
| 注释「惯例 17:00 UTC」 | 夏令时换算 | 应改为「夏令时 17:00 UTC / 冬令时 18:00 UTC」 |

**当前时点（2026-11-16）应显示**：Season 31、Split 1、距 Split 1 结束约 29 天。

---

## 六、置信度总结

| 结论 | 置信度 | 说明 |
| --- | --- | --- |
| EN 名 = Cipher | ★★★★★ | EA 官方标题 + wiki 双重确认 |
| 中文名 = 破译天机 | ★★★★★ | EA 官方中文站（繁）+ EA Help 简体中文文本，非意译 |
| season_start = 2026-11-03 18:00 UTC | ★★★★★ | 官方商店 SKU 时间戳 `2026-11-03T18:00:00Z` 直接命中 |
| split1_end = 2026-12-15 18:00 UTC | ★★★★★ | 官方商店 SKU `EndDate` + PS/Xbox 售卖截止 + ALS unix 时间戳三方吻合 |
| season_end 日期 = 2027-02-09 | ★★★☆☆ | 仅 wiki.gg 与 apexseasons 给出，EA 未公布；另有 2/2、2/3 等预估 |
| season_end 时刻 = 18:00 UTC | ★★★☆☆ | 按 PST 惯例推定，EA 未公布 |

---

*本报告仅写入 `docs/season-31-data.md`，未修改 `libs/`、`jinja/`、`main.py`、`CHANGELOG.md`、`tests/`、`scripts/`，未执行 git commit。*
