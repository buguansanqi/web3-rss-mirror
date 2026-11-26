"""在 GitHub Actions（境外服务器）运行：抓取 RAW.opml 中所有 medium.com 订阅源，
保存为本地 XML 文件，并生成 manifest.json 供国内侧重建 OPML。

针对 Medium 的 429 限流做了优化：低并发 + 请求间隔 + 指数退避重试。

用法（在 Actions 中自动执行，也可本地在境外网络环境手动跑）：
    python scripts/fetch_medium.py
"""
import os
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
MAX_WORKERS = 3          # 低并发，避免触发 Medium 限流
REQUEST_DELAY = 1.0      # 每个请求前的固定间隔（秒）
MAX_RETRIES = 3          # 429 时的最大重试次数
OUT_DIR = 'feeds'


def slugify(title):
    """把标题转成安全文件名"""
    s = re.sub(r'[^\w\u4e00-\u9fff\-]+', '_', title).strip('_')
    h = hashlib.md5(title.encode('utf-8')).hexdigest()[:8]
    return f'{s[:60]}_{h}'


def fetch_one(item):
    """抓取单个 feed，带 429 退避重试。成功返回 (item, xml_text, '')，失败返回 (item, None, 错误)。"""
    time.sleep(REQUEST_DELAY + random.uniform(0, 0.5))  # 抖动，避免请求过于整齐
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(item['url'], headers=HEADERS,
                                timeout=(10, 25), allow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 100:
                return item, resp.text, ''
            if resp.status_code == 429:
                if attempt < MAX_RETRIES:
                    # 指数退避：2s, 4s, 8s
                    time.sleep(2 ** (attempt + 1) + random.uniform(0, 1))
                    continue
                return item, None, 'HTTP 429 (重试仍限流)'
            return item, None, f'HTTP {resp.status_code}'
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt + 1))
                continue
            return item, None, str(e)[:120]
    return item, None, '未知错误'


def main():
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
    print(f'共 {len(items)} 个 Medium feed 待抓取（并发 {MAX_WORKERS}，间隔 {REQUEST_DELAY}s）', flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_one, it) for it in items]
        for i, future in enumerate(as_completed(futures), 1):
            item, xml_text, err = future.result()
            entry = {**item, 'ok': bool(xml_text), 'error': err}
            if xml_text:
                with open(os.path.join(OUT_DIR, item['filename'] + '.xml'),
                          'w', encoding='utf-8') as fp:
                    fp.write(xml_text)
            manifest.append(entry)
            if i % 25 == 0:
                ok_so_far = sum(1 for m in manifest if m['ok'])
                print(f'  已抓取 {i}/{len(items)}，成功 {ok_so_far}，耗时 {int(time.time()-start)}s', flush=True)

    manifest.sort(key=lambda x: (x['category'], x['title']))
    with open('manifest.json', 'w', encoding='utf-8') as fp:
        json.dump({'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                   'total': len(manifest),
                   'ok': sum(1 for m in manifest if m['ok']),
                   'feeds': manifest}, fp, ensure_ascii=False, indent=2)

    print(f'完成，耗时 {time.time()-start:.1f}s；'
          f'成功 {sum(1 for m in manifest if m["ok"])}/{len(manifest)}', flush=True)


if __name__ == '__main__':
    main()
