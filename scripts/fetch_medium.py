"""在 GitHub Actions（境外服务器）运行：抓取 RAW.opml 中所有 medium.com 订阅源，
保存为本地 XML 文件，并生成 manifest.json 供国内侧重建 OPML。

针对 Medium 对 GitHub IP 的持续 429 限流，采用增量策略：
- 读取已有 manifest.json，保留此前成功的记录（文件已在仓库中）
- 每次只补抓「尚未成功」的源，且限制单次数量，避免超时和加重限流
- 多次运行逐步积累，直到全部成功或确认为 404

用法（在 Actions 中自动执行，也可本地在境外网络环境手动跑）：
    python scripts/fetch_medium.py [每次补抓数量，默认 60]
"""
import os
import sys
import re
import json
import time
import random
import hashlib
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
}
MAX_WORKERS = 3
REQUEST_DELAY = 1.5
MAX_RETRIES = 2
BATCH_LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 60
OUT_DIR = 'feeds'
MANIFEST = 'manifest.json'


def slugify(title):
    s = re.sub(r'[^\w\u4e00-\u9fff\-]+', '_', title).strip('_')
    h = hashlib.md5(title.encode('utf-8')).hexdigest()[:8]
    return f'{s[:60]}_{h}'


def fetch_one(item):
    time.sleep(REQUEST_DELAY + random.uniform(0, 1))
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(item['url'], headers=HEADERS,
                                timeout=(10, 25), allow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 100:
                return item, resp.text, ''
            if resp.status_code == 429:
                if attempt < MAX_RETRIES:
                    time.sleep(2 ** (attempt + 1) + random.uniform(0, 1))
                    continue
                return item, None, 'HTTP 429 (限流)'
            return item, None, f'HTTP {resp.status_code}'
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt + 1))
                continue
            return item, None, str(e)[:120]
    return item, None, '未知错误'


def load_all_items():
    opml_path = os.path.join(os.path.dirname(__file__), '..', 'RAW.opml')
    tree = ET.parse(opml_path)
    root = tree.getroot()
    items = []
    for cat in root[1]:
        category = cat.attrib.get('title', '')
        for feed in cat:
            url = feed.attrib.get('xmlUrl', '')
            if 'medium.com' in url.lower():
                items.append({
                    'category': category,
                    'title': feed.attrib.get('title', ''),
                    'url': url,
                    'filename': slugify(feed.attrib.get('title', '')),
                })
    return items


def main():
    all_items = load_all_items()
    print(f'RAW.opml 中共有 {len(all_items)} 个 Medium feed', flush=True)

    # 读取已有 manifest，保留成功记录与失败原因
    existing = {}   # url -> 成功条目
    last_errors = {}  # url -> 上次的失败原因
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding='utf-8') as fp:
            old = json.load(fp)
        for f in old.get('feeds', []):
            if f.get('ok'):
                existing[f['url']] = f
            elif f.get('error'):
                last_errors[f['url']] = f['error']
        print(f'已有 {len(existing)} 个成功记录，将保留', flush=True)

    # 待抓：不在成功记录中的
    todo = [it for it in all_items if it['url'] not in existing]
    print(f'待补抓 {len(todo)} 个，本次最多抓 {BATCH_LIMIT} 个', flush=True)
    todo = todo[:BATCH_LIMIT]

    if todo:
        os.makedirs(OUT_DIR, exist_ok=True)
        start = time.time()
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(fetch_one, it): it for it in todo}
            for i, future in enumerate(as_completed(futures), 1):
                item, xml_text, err = future.result()
                if xml_text:
                    entry = {**item, 'ok': True, 'error': ''}
                    with open(os.path.join(OUT_DIR, item['filename'] + '.xml'),
                              'w', encoding='utf-8') as fp:
                        fp.write(xml_text)
                    existing[item['url']] = entry  # 成功的加入累积池
                else:
                    print(f'  [{i}/{len(todo)}] 失败 {item["title"][:30]}: {err}', flush=True)
                if i % 20 == 0:
                    print(f'  进度 {i}/{len(todo)}，耗时 {int(time.time()-start)}s', flush=True)
        print(f'本次补抓耗时 {time.time()-start:.1f}s', flush=True)

    # 写回完整 manifest：所有源，成功的标记 ok=True
    manifest_feeds = []
    for it in all_items:
        if it['url'] in existing:
            manifest_feeds.append(existing[it['url']])
        else:
            manifest_feeds.append({**it, 'ok': False,
                                   'error': last_errors.get(it['url'], '待抓取')})

    manifest_feeds.sort(key=lambda x: (x['category'], x['title']))
    with open(MANIFEST, 'w', encoding='utf-8') as fp:
        json.dump({'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                   'total': len(manifest_feeds),
                   'ok': sum(1 for m in manifest_feeds if m['ok']),
                   'feeds': manifest_feeds}, fp, ensure_ascii=False, indent=2)

    print(f'累计成功 {sum(1 for m in manifest_feeds if m["ok"])}/{len(manifest_feeds)}', flush=True)


if __name__ == '__main__':
    main()
