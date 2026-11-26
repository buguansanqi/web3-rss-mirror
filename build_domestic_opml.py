"""在本机（国内网络）运行：拉取 GitHub 仓库的 manifest.json，
把 Medium 源的 URL 替换成 jsDelivr CDN 地址，生成可导入阅读器的国内版 OPML。

前置条件：
  1. 用户已按 DEPLOY_MEDIUM.md 把仓库推到 GitHub，且 Actions 已跑完一轮
  2. 本机可访问 cdn.jsdelivr.net（已实测可达）

用法：
    python build_domestic_opml.py <GitHub用户名> <仓库名> [分支名]
例：
    python build_domestic_opml.py myuser web3-rss main
"""
import sys
import os
import json
import time
import xml.etree.ElementTree as ET

import requests

CDN = 'https://cdn.jsdelivr.net/gh/{user}/{repo}@{branch}/feeds/{filename}.xml'


def fetch_manifest(user, repo, branch):
    """从 jsDelivr 拉 manifest，加时间戳绕过 CDN 缓存。jsDelivr 对刚更新的文件可能缓存旧版。"""
    url = f'https://cdn.jsdelivr.net/gh/{user}/{repo}@{branch}/manifest.json?t={int(time.time())}'
    resp = requests.get(url, timeout=(10, 30), headers={'Cache-Control': 'no-cache'})
    resp.raise_for_status()
    return resp.json()


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    user, repo = sys.argv[1], sys.argv[2]
    branch = sys.argv[3] if len(sys.argv) > 3 else 'main'

    # jsDelivr 对 @branch 路径缓存较久（可能滞后数小时）。若本地有更新的
    # manifest.json（刚 git pull 过），优先使用本地版本，确保拿到最新抓取结果。
    local_path = os.path.join(os.path.dirname(__file__), 'manifest.json')
    manifest = None
    if os.path.exists(local_path):
        with open(local_path, encoding='utf-8') as fp:
            local = json.load(fp)
        try:
            cdn = fetch_manifest(user, repo, branch)
            if local.get('updated_at', '') >= cdn.get('updated_at', ''):
                manifest = local
                print(f'使用本地 manifest（比 CDN 更新）')
            else:
                manifest = cdn
                print(f'使用 CDN manifest（比本地更新）')
        except Exception as e:
            print(f'CDN 拉取失败（{e}），改用本地 manifest')
            manifest = local
    else:
        print(f'从 jsDelivr 拉取 manifest.json（{user}/{repo}@{branch}）...')
        manifest = fetch_manifest(user, repo, branch)
    print(f"仓库抓取时间: {manifest['updated_at']}，成功 {manifest['ok']}/{manifest['total']}")

    # 读取原始 OPML 作为骨架
    tree = ET.parse('RAW.opml')
    root = tree.getroot()
    body = root[1]

    # 建立 原始URL -> CDN URL 映射（仅替换抓取成功且为 medium 的源）
    mapping = {m['url']: CDN.format(user=user, repo=repo, branch=branch,
                                    filename=m['filename'])
               for m in manifest['feeds'] if m['ok']}

    replaced = 0
    removed = 0
    for cat in list(body):
        for feed in list(cat):
            url = feed.attrib.get('xmlUrl', '')
            if 'medium.com' not in url.lower():
                continue
            if url in mapping:
                feed.set('xmlUrl', mapping[url])
                replaced += 1
            else:
                # 抓取失败的源从国内版中移除，避免大量红叉
                cat.remove(feed)
                removed += 1

    out = 'RAW_domestic.opml'
    tree.write(out, encoding='utf-8', xml_declaration=True)
    print(f'已生成 {out}：替换 {replaced} 个 Medium 源为 CDN 地址，移除 {removed} 个失效源。')
    print('可直接把 RAW_domestic.opml 导入你的 RSS 阅读器。')


if __name__ == '__main__':
    main()
