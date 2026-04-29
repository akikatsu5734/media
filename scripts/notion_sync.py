#!/usr/bin/env python3
"""
Notion 同期スクリプト

articles_state.json を Notion "Articles" データベースと同期する。

使用例:
  # ローカル → Notion へ反映（新規作成 + 更新）
  python scripts/notion_sync.py --push

  # Notion → ローカルへ Status を反映（承認ゲート用）
  python scripts/notion_sync.py --pull

  # 差分確認のみ（API 呼び出しなし）
  python scripts/notion_sync.py --push --dry-run
  python scripts/notion_sync.py --pull --dry-run

必要な設定:
  .env に以下を追加してください。
    NOTION_API_KEY=secret_...
    NOTION_ARTICLES_DB_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

  Notion DB のセットアップ手順は docs/notion_setup_guide.md を参照。
"""

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.state import load_state, save_state


def _build_properties(article: dict) -> dict:
    """articles_state のエントリから Notion ページプロパティを構築する。"""
    props: dict = {
        "Title": {
            "title": [{"text": {"content": article.get("title", "（タイトルなし）")}}]
        },
        "Article ID": {
            "rich_text": [{"text": {"content": article.get("id", "")}}]
        },
        "Type": {
            "select": {"name": article.get("type", "general")}
        },
        "Status": {
            "select": {"name": article.get("status", "proposed")}
        },
        "Priority": {
            "select": {"name": article.get("priority", "med")}
        },
    }

    for key, field in [
        ("Keyword",        "keyword"),
        ("Region",         "region"),
        ("Draft File",     "draft_file"),
        ("Image File",     "image_file"),
        ("Decision Notes", "decision_notes"),
    ]:
        val = article.get(field)
        if val:
            props[key] = {"rich_text": [{"text": {"content": str(val)}}]}

    for key, field in [
        ("Source URL", "source_url"),
        ("Public URL", "public_url"),
    ]:
        val = article.get(field)
        if val:
            props[key] = {"url": val}

    if article.get("source_type"):
        props["Source Type"] = {"select": {"name": article["source_type"]}}

    if article.get("wp_post_id") is not None:
        props["WP Post ID"] = {"number": article["wp_post_id"]}

    if article.get("created_at"):
        props["Created"] = {"date": {"start": article["created_at"][:10]}}

    if article.get("published_at"):
        props["Published"] = {"date": {"start": article["published_at"][:10]}}

    return props


def _get_client():
    try:
        from notion_client import Client
    except ImportError:
        print("[ERROR] notion-client がインストールされていません。")
        print("  pip install notion-client>=2.2.0")
        sys.exit(1)

    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        print("[ERROR] NOTION_API_KEY が .env に設定されていません。")
        sys.exit(1)

    return Client(auth=api_key)


def _get_db_id() -> str:
    db_id = os.environ.get("NOTION_ARTICLES_DB_ID", "")
    if not db_id:
        print("[ERROR] NOTION_ARTICLES_DB_ID が .env に設定されていません。")
        sys.exit(1)
    return db_id


def _query_all_pages(client, db_id: str) -> list[dict]:
    """Notion DB の全ページを取得する（ページネーション対応）。"""
    pages = []
    cursor = None
    while True:
        kwargs: dict = {"database_id": db_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.databases.query(**kwargs)
        pages.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
        time.sleep(0.4)  # Notion API rate limit: 3 req/s
    return pages


def _extract_article_id(page: dict) -> str:
    """Notion ページから Article ID プロパティを取り出す。"""
    aid_prop = page.get("properties", {}).get("Article ID", {})
    items = aid_prop.get("rich_text", [])
    return items[0].get("text", {}).get("content", "") if items else ""


def push(dry_run: bool = False) -> None:
    """articles_state.json の内容を Notion DB へ反映する（新規作成 + 更新）。"""
    state = load_state()
    articles = state.get("articles", [])

    if not articles:
        print("articles_state.json に記事がありません。")
        return

    print(f"📤 push: {len(articles)} 件を Notion に同期します...")

    if dry_run:
        for a in articles:
            action = "UPDATE" if a.get("notion_page_id") else "CREATE"
            print(f"  [{action}] [{a['id']}] {a['title'][:50]}  status={a['status']}")
        print("\n[DRY-RUN] 実際の API 呼び出しはスキップしました。")
        return

    client = _get_client()
    db_id = _get_db_id()

    # 既存 Notion ページを Article ID でインデックス化
    existing: dict[str, str] = {}  # article_id → notion_page_id
    try:
        pages = _query_all_pages(client, db_id)
        for page in pages:
            aid = _extract_article_id(page)
            if aid:
                existing[aid] = page["id"]
    except Exception as e:
        print(f"[WARN] Notion DB クエリ中にエラー: {e}")

    created = updated = failed = 0
    for a in articles:
        props = _build_properties(a)
        page_id = a.get("notion_page_id") or existing.get(a["id"])
        try:
            if page_id:
                client.pages.update(page_id=page_id, properties=props)
                a["notion_page_id"] = page_id
                updated += 1
                print(f"  ✏️  UPDATE [{a['id']}] {a['title'][:40]}")
            else:
                new_page = client.pages.create(
                    parent={"database_id": db_id},
                    properties=props,
                )
                a["notion_page_id"] = new_page["id"]
                created += 1
                print(f"  ✅ CREATE [{a['id']}] {a['title'][:40]}")
            time.sleep(0.4)
        except Exception as e:
            failed += 1
            print(f"  [ERROR] [{a['id']}] {a['title'][:40]}: {e}")

    save_state(state)
    print(f"\n完了: 作成={created}  更新={updated}  失敗={failed}")


def pull(dry_run: bool = False) -> None:
    """Notion DB の Status を articles_state.json に反映する（承認ゲート用）。"""
    state = load_state()
    articles_by_id = {a["id"]: a for a in state.get("articles", [])}

    if not articles_by_id:
        print("articles_state.json に記事がありません。")
        return

    print("📥 pull: Notion DB から Status を取得...")

    if dry_run:
        print("[DRY-RUN] API 呼び出しをスキップします。--push --dry-run で差分を確認してください。")
        return

    client = _get_client()
    db_id = _get_db_id()

    updated = 0
    try:
        pages = _query_all_pages(client, db_id)
        for page in pages:
            aid = _extract_article_id(page)
            if aid not in articles_by_id:
                continue

            props = page.get("properties", {})
            notion_status = (props.get("Status", {}).get("select") or {}).get("name", "")
            if not notion_status:
                continue

            article = articles_by_id[aid]
            old_status = article.get("status", "")
            if notion_status != old_status:
                article["status"] = notion_status
                article["notion_page_id"] = page["id"]
                updated += 1
                print(f"  ↓ [{aid}] {article['title'][:40]}  {old_status} → {notion_status}")
    except Exception as e:
        print(f"[ERROR] Notion DB クエリ中にエラー: {e}")
        return

    if updated:
        save_state(state)
        print(f"\n完了: {updated} 件のステータスを更新しました。")
    else:
        print("\n変更なし（Notion と articles_state.json は一致しています）。")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="articles_state.json ↔ Notion DB 同期",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用例:
  python scripts/notion_sync.py --push            # ローカル → Notion
  python scripts/notion_sync.py --pull            # Notion → ローカル（Status のみ）
  python scripts/notion_sync.py --push --dry-run  # 差分確認のみ
        """,
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--push", action="store_true", help="articles_state.json → Notion DB")
    mode_group.add_argument("--pull", action="store_true", help="Notion DB → articles_state.json（Status のみ）")
    parser.add_argument("--dry-run", action="store_true", help="API を呼ばず差分のみ確認")
    args = parser.parse_args()

    if args.push:
        push(dry_run=args.dry_run)
    elif args.pull:
        pull(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
