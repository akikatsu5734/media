#!/usr/bin/env python3
"""
情報収集スクリプト
RSS フィードからキーワードに関連する話題を収集し、data/collected_topics.json に保存する。
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
SOURCES_FILE = BASE_DIR / "data" / "rss_sources.json"
OUTPUT_FILE = BASE_DIR / "data" / "collected_topics.json"


def load_sources() -> dict:
    with open(SOURCES_FILE, encoding="utf-8") as f:
        return json.load(f)


def fetch_feed(url: str, timeout: int = 10) -> list[dict]:
    """RSS フィードを取得してエントリのリストを返す。"""
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "AkikatsuBot/1.0"})
        return feed.entries
    except Exception as e:
        print(f"  [WARN] フィード取得失敗: {url} - {e}", file=sys.stderr)
        return []


def matches_keywords(text: str, keywords: list[str]) -> list[str]:
    """テキストにマッチするキーワードのリストを返す。"""
    text_lower = text.lower()
    return [kw for kw in keywords if kw in text_lower]


def entry_to_topic(entry: object, source_name: str, keywords: list[str]) -> dict | None:
    """feedparser のエントリをトピック辞書に変換する。マッチしない場合は None。"""
    title = getattr(entry, "title", "") or ""
    summary = getattr(entry, "summary", "") or ""
    link = getattr(entry, "link", "") or ""

    combined = title + " " + summary
    matched = matches_keywords(combined, keywords)
    if not matched:
        return None

    published_raw = getattr(entry, "published", None)
    published = ""
    if published_raw:
        try:
            import email.utils
            ts = email.utils.parsedate_to_datetime(published_raw)
            published = ts.isoformat()
        except Exception:
            published = published_raw

    return {
        "source": source_name,
        "title": title.strip(),
        "url": link,
        "published": published,
        "summary": summary[:300].strip(),
        "keywords_matched": matched,
    }


def collect(dry_run: bool = False) -> list[dict]:
    config = load_sources()
    keywords = config["keywords"]
    topics: list[dict] = []

    for source in config["sources"]:
        if not source.get("enabled", False):
            print(f"[SKIP] {source['name']} (disabled)")
            continue

        print(f"[FETCH] {source['name']} ...")
        entries = fetch_feed(source["url"])
        count_before = len(topics)

        for entry in entries:
            topic = entry_to_topic(entry, source["name"], keywords)
            if topic:
                topics.append(topic)

        added = len(topics) - count_before
        print(f"  → {added} 件マッチ（全 {len(entries)} 件中）")

    # 重複 URL を除去（URL が同じものは最初の1件だけ残す）
    seen: set[str] = set()
    unique: list[dict] = []
    for t in topics:
        if t["url"] not in seen:
            seen.add(t["url"])
            unique.append(t)

    unique.sort(key=lambda x: x.get("published", ""), reverse=True)

    if not dry_run:
        output = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "total": len(unique),
            "topics": unique,
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n✅ {len(unique)} 件を {OUTPUT_FILE} に保存しました。")
    else:
        print(f"\n[DRY-RUN] {len(unique)} 件がマッチしました（保存なし）。")

    return unique


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    collect(dry_run=dry_run)
