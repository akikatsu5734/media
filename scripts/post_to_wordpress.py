#!/usr/bin/env python3
"""
WordPress 投稿スクリプト（下書き / 予約投稿 / 確認）
data/drafts/ 内の Markdown ファイルを WordPress REST API 経由で投稿する。

モード:
  下書き保存（デフォルト）: --file <path>
  予約投稿:                 --file <path> --schedule "2026-04-25T10:00:00"
  確認のみ（投稿しない）:  --file <path> --dry-run

使用例:
  python scripts/post_to_wordpress.py --file data/drafts/20260424_世田谷区.md
  python scripts/post_to_wordpress.py --file data/drafts/20260424_世田谷区.md --schedule "2026-04-25T10:00:00"
  python scripts/post_to_wordpress.py --file data/drafts/20260424_世田谷区.md --dry-run
"""

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
POSTED_LOG = BASE_DIR / "data" / "posted.json"


def load_posted_log() -> list[dict]:
    if POSTED_LOG.exists():
        with open(POSTED_LOG, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_posted_log(log: list[dict]) -> None:
    POSTED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(POSTED_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def parse_front_matter(content: str) -> tuple[dict, str]:
    """Markdown のフロントマター（---〜---）を解析して返す。"""
    meta: dict = {}
    body = content

    match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if match:
        fm_text = match.group(1)
        body = match.group(2).strip()
        for line in fm_text.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                meta[key.strip()] = val.strip().strip('"')
    return meta, body


def markdown_to_html(md: str) -> str:
    """最小限の Markdown → HTML 変換（h2, h3, p, ul のみ対応）。"""
    lines = md.splitlines()
    html_lines = []
    in_ul = False

    for line in lines:
        if line.startswith("## "):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append(f"<h2>{line[3:].strip()}</h2>")
        elif line.startswith("### "):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append(f"<h3>{line[4:].strip()}</h3>")
        elif line.startswith("- "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{line[2:].strip()}</li>")
        elif line.strip() == "":
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append("")
        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if line.strip():
                html_lines.append(f"<p>{line.strip()}</p>")

    if in_ul:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def parse_schedule(schedule_str: str) -> str:
    """--schedule で渡された日時文字列を検証して返す。WordPressはサイトのローカル時刻を期待する。"""
    try:
        dt = datetime.fromisoformat(schedule_str)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        print(f"[ERROR] --schedule の日時フォーマットが不正です: {schedule_str}")
        print("       正しい形式: YYYY-MM-DDTHH:MM:SS  例: 2026-04-25T10:00:00")
        sys.exit(1)


def post_draft(draft_path: Path, dry_run: bool = False, schedule: str = "") -> dict | None:
    if not draft_path.exists():
        print(f"[ERROR] ファイルが見つかりません: {draft_path}")
        sys.exit(1)

    content_raw = draft_path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(content_raw)

    title = meta.get("title", draft_path.stem)
    excerpt = meta.get("excerpt", "")
    category_id = int(os.environ.get("WP_DEFAULT_CATEGORY_ID", "1"))

    html_body = markdown_to_html(body)

    if schedule:
        mode_label = f"予約投稿（{schedule}）"
        post_status = "future"
    else:
        mode_label = "下書き保存"
        post_status = "draft"

    print(f"📄 ファイル: {draft_path.name}")
    print(f"📝 タイトル: {title}")
    print(f"🗂  モード: {mode_label}")
    print(f"📋 メタ情報: {json.dumps(meta, ensure_ascii=False)[:120]}")

    if dry_run:
        print("\n[DRY-RUN] 以下の内容で WordPress に投稿します（実際には投稿しません）:")
        print(f"  title:   {title}")
        print(f"  status:  {post_status}")
        if schedule:
            print(f"  date:    {schedule}")
            print("  ※ WordPress サイトのタイムゾーン設定に合わせた日時を指定してください。")
        print(f"  excerpt: {excerpt[:80]}")
        print(f"  content（先頭200字）: {html_body[:200]}")
        return None

    wp_url = os.environ.get("WP_URL", "").rstrip("/")
    wp_username = os.environ.get("WP_USERNAME", "")
    wp_app_password = os.environ.get("WP_APP_PASSWORD", "")

    if not all([wp_url, wp_username, wp_app_password]):
        print("[ERROR] WP_URL / WP_USERNAME / WP_APP_PASSWORD が .env に設定されていません。")
        sys.exit(1)

    credentials = base64.b64encode(f"{wp_username}:{wp_app_password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
    }

    post_data: dict = {
        "title": title,
        "content": html_body,
        "status": post_status,
        "excerpt": excerpt,
        "categories": [category_id],
    }
    if schedule:
        post_data["date"] = schedule

    api_url = f"{wp_url}/wp-json/wp/v2/posts"
    print(f"\n🚀 投稿中: {api_url}")

    resp = requests.post(api_url, json=post_data, headers=headers, timeout=30)

    if resp.status_code in (200, 201):
        result = resp.json()
        post_id = result.get("id")
        post_link = result.get("link", "")

        if schedule:
            print(f"\n✅ 予約投稿成功！ post_id={post_id}  公開予定: {schedule}")
        else:
            print(f"\n✅ 下書き投稿成功！ post_id={post_id}")
        print(f"   WordPress 管理画面で確認: {wp_url}/wp-admin/post.php?post={post_id}&action=edit")

        log = load_posted_log()
        log.append({
            "post_id": post_id,
            "title": title,
            "draft_file": str(draft_path),
            "posted_at": datetime.now().isoformat(),
            "scheduled_at": schedule or None,
            "status": post_status,
            "link": post_link,
        })
        save_posted_log(log)
        return result
    else:
        print(f"\n[ERROR] 投稿失敗: HTTP {resp.status_code}")
        print(resp.text[:500])
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WordPress 投稿スクリプト（下書き / 予約投稿 / 確認）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
モード:
  下書き保存（デフォルト）: --file <path>
  予約投稿:                 --file <path> --schedule "2026-04-25T10:00:00"
  確認のみ（投稿しない）:  --file <path> --dry-run
        """,
    )
    parser.add_argument("--file", required=True, help="投稿する Markdown ファイルのパス")
    parser.add_argument(
        "--schedule",
        default="",
        metavar="DATETIME",
        help="予約公開日時（例: 2026-04-25T10:00:00）。WordPressサイトのタイムゾーン基準。",
    )
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿せず内容を確認のみ")
    args = parser.parse_args()

    schedule = parse_schedule(args.schedule) if args.schedule else ""

    draft_path = Path(args.file)
    if not draft_path.is_absolute():
        draft_path = BASE_DIR / draft_path

    post_draft(draft_path, dry_run=args.dry_run, schedule=schedule)


if __name__ == "__main__":
    main()
