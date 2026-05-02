#!/usr/bin/env python3
"""
articles_state.json の読み書きヘルパ
articles_state.json は全記事の状態を管理する単一の真実 (single source of truth)。
Notion はこのファイルの人間向けミラー（ダッシュボード・承認ゲート）として同期される。
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
STATE_FILE = BASE_DIR / "data" / "articles_state.json"

VALID_STATUSES = frozenset({
    "proposed", "approved", "drafting", "draft_ready",
    "image_ready", "wp_draft", "scheduled", "published",
    "needs_rewrite", "archived", "rejected",
})
VALID_TYPES = frozenset({"general", "case", "tokyo23", "seasonal_pr"})
VALID_PRIORITIES = frozenset({"high", "med", "low"})


def load_state() -> dict:
    """articles_state.json を読み込む。ファイルがなければ空の状態を返す。"""
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"version": "1.0", "articles": []}


def save_state(state: dict) -> None:
    """articles_state.json に書き込む。"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def add_article(
    title: str,
    article_type: str = "general",
    status: str = "proposed",
    priority: str = "med",
    keyword: str = "",
    region: str = "",
    source_url: str = "",
    source_type: str = "manual",
    decision_notes: str = "",
    title_options: Optional[dict] = None,
) -> dict:
    """新しい記事エントリを追加して返す。"""
    state = load_state()
    article: dict = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "type": article_type,
        "status": status,
        "priority": priority,
        "keyword": keyword,
        "region": region,
        "source_url": source_url,
        "source_type": source_type,
        "title_options": title_options or {},
        "draft_file": None,
        "image_file": None,
        "wp_post_id": None,
        "public_url": None,
        "notion_page_id": None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "published_at": None,
        "decision_notes": decision_notes,
    }
    state["articles"].append(article)
    save_state(state)
    return article


def update_article(article_id: str, **fields) -> Optional[dict]:
    """指定 ID の記事を更新して返す。見つからなければ None。"""
    state = load_state()
    for article in state["articles"]:
        if article["id"] == article_id:
            article.update(fields)
            save_state(state)
            return article
    return None


def find_article(article_id: str) -> Optional[dict]:
    """ID で記事を検索する。"""
    state = load_state()
    for a in state["articles"]:
        if a["id"] == article_id:
            return a
    return None


def find_by_draft_file(draft_path: str) -> Optional[dict]:
    """draft_file パスで記事を検索する（相対パスで照合）。"""
    state = load_state()
    needle = str(Path(draft_path))
    needle_rel = needle.replace(str(BASE_DIR) + "/", "")
    for a in state["articles"]:
        stored = a.get("draft_file")
        if stored and (stored == needle or stored == needle_rel):
            return a
    return None


def get_by_status(status: str) -> list[dict]:
    """指定ステータスの記事一覧を返す。"""
    state = load_state()
    return [a for a in state["articles"] if a.get("status") == status]


def all_articles() -> list[dict]:
    """全記事の一覧を返す。"""
    return load_state().get("articles", [])
