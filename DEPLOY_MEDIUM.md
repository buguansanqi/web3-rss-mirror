# Medium 源国内访问方案 —— 部署完成说明

## 状态：已部署并运行中 ✅

仓库地址：**https://github.com/buguansanqi/web3-rss-mirror**（公开）

GitHub Actions 正在自动抓取 224 个 Medium feed，通过 jsDelivr CDN 供国内读取。

```
Medium (国外)  --抓取-->  GitHub Actions (国外)  --存-->  GitHub 仓库 (buguansanqi/web3-rss-mirror)
                                                              |
你的阅读器 (国内)  <--读取--  jsDelivr CDN (国内可达)  <--------+
```

---

## 你只需要做一件事：导入 OPML

本机已生成好 `RAW_domestic.opml`（位于本目录），直接导入你的 RSS 阅读器即可：
- Fluent Reader / Raven Reader / Feedbro / Inoreader 等，选"导入 OPML"，选这个文件。

当前文件包含 **462 个源**：其中 387 个可直连的源 + 75 个已转为 CDN 地址的 Medium 源。

后续 Medium 源会逐步增多（见下方"抓取进度"），需要更新时重跑：

```bash
cd RSS-RAW
git pull                                              # 拉取最新抓取结果
python build_domestic_opml.py buguansanqi web3-rss-mirror main
```

然后把重新生成的 `RAW_domestic.opml` 再导入一次阅读器（或在阅读器里刷新订阅）。

---

## 抓取进度说明

Medium 对 GitHub 的出口 IP 有**持续性 429 限流**，无法一次性抓完 224 个。因此采用增量策略：

- **每 3 小时自动补抓 60 个**（北京时间 08:00/11:00/14:00/17:00/20:00/23:00/02:00/05:00）
- 每次只抓尚未成功的源，已成功的不重复抓
- 预计 1-2 天内基本补齐（确认失效的 404 源会被剔除）

当前进度（2026-11-26 09:18 UTC）：**75 / 224 成功**，剩余中 3 个是 404（真失效），146 个待补抓。

查看实时进度：
- 打开 https://github.com/buguansanqi/web3-rss-mirror/actions 看运行记录
- 或本机 `git pull` 后看 `manifest.json` 里的 `ok` 字段

想手动加速：打开仓库 Actions 页面 → 选 `Fetch Medium Feeds` → Run workflow，在 `batch` 输入想抓的数量（如 100）。

---

## 实测依据（2026-11-26 本机验证）

| 服务 | 国内连通性 |
|------|-----------|
| medium.com / rsshub.app 各实例 / Inoreader / Feedly | ❌ 超时 |
| r.jina.ai / allorigins / ghproxy 转发非 GitHub 站 | ❌ 超时或被拒 |
| github.com / api.github.com | ✅ 200 |
| cdn.jsdelivr.net（读取仓库 XML / manifest） | ✅ 200 |

结论：没有现成公共代理可直接中转 Medium，GitHub Actions + jsDelivr 是免费且无需代理的方案。

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `RAW_domestic.opml` | **给阅读器导入的最终文件**（462 个源） |
| `build_domestic_opml.py` | 本机运行，用最新抓取结果重建 OPML |
| `.github/workflows/fetch-medium-feeds.yml` | GitHub 上的定时抓取工作流（每 3 小时） |
| `scripts/fetch_medium.py` | 在 GitHub 上运行的增量抓取脚本 |
| `manifest.json` / `feeds/` | 从仓库拉取的抓取结果（git pull 更新） |
| `feed_final_report.txt` / `feed_final_detail.csv` | 首轮 611 个源的 URL 健康检测报告 |

---

## 注意事项

1. **feed 是缓存快照**：每 3 小时更新，不是实时。博客内容足够。
2. **jsDelivr 缓存**：`@main` 路径有缓存，manifest 可能滞后几小时；`build_domestic_opml.py` 已做本地/缓存对比，会自动选更新的那份。
3. **仓库必须保持公开**：私有仓库 jsDelivr 读不到。
4. **合规**：仅抓取公开 RSS 订阅源，使用公开的 GitHub Actions 与 CDN 服务，请遵守相关服务条款和当地法律法规。
