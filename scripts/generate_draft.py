#!/usr/bin/env python3
"""
記事下書き生成スクリプト
記事タイプとタイトルを受け取り、Claude API を使って記事下書きを生成する。
出力は data/drafts/YYYYMMDD_<slug>.md に保存される。

使用例:
  # 記事タイプを指定（推奨）
  python scripts/generate_draft.py --type general --title "空き家の売却手順完全ガイド" --keyword "空き家 売却"
  python scripts/generate_draft.py --type case --title "相続した実家の空き家問題を解決した事例"
  python scripts/generate_draft.py --type tokyo23 --title "世田谷区"
  python scripts/generate_draft.py --type seasonal_pr --title "夏の台風前に空き家点検を済ませておく理由"

  # 動作確認（API 呼び出しなし）
  python scripts/generate_draft.py --type general --title "テスト記事" --keyword "テスト" --dry-run

  # 対話モード
  python scripts/generate_draft.py --interactive
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DRAFTS_DIR = BASE_DIR / "data" / "drafts"
PROMPTS_DIR = BASE_DIR / "prompts"

ARTICLE_TYPES = {
    "general":     "article_general.md",
    "case":        "article_case.md",
    "tokyo23":     "article_tokyo23.md",
    "seasonal_pr": "article_seasonal_pr.md",
}

DEFAULT_CTA_URL = "https://aki-katsu.co.jp/counter/"


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:40].strip("_").lower()


def load_file(path: Path) -> str:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def build_prompt(
    article_type: str,
    title: str,
    keyword: str = "",
    region: str = "",
    notes: str = "",
    cta_url: str = DEFAULT_CTA_URL,
) -> str:
    common = load_file(PROMPTS_DIR / "article_common.md")
    specific = load_file(PROMPTS_DIR / ARTICLE_TYPES[article_type])

    combined = (common + "\n\n---\n\n" + specific).strip()

    if article_type == "tokyo23":
        combined = combined.replace("{{対象区名}}", title)
        combined = combined.replace("{{補足}}", notes)
    else:
        combined = combined.replace("{{記事タイトル}}", title)
        combined = combined.replace("{{キーワード}}", keyword)
        combined = combined.replace("{{対象地域}}", region)
        combined = combined.replace("{{補足}}", notes)

    combined = combined.replace("{{WP_CTA_URL}}", cta_url)

    return combined


def generate(
    article_type: str,
    title: str,
    keyword: str = "",
    region: str = "",
    notes: str = "",
    dry_run: bool = False,
) -> str:
    cta_url = os.environ.get("WP_CTA_URL", DEFAULT_CTA_URL)

    print(f"📝 記事タイプ: {article_type}")
    if article_type == "tokyo23":
        print(f"📍 対象区名: {title}")
    else:
        print(f"📝 記事タイトル: {title}")
        if keyword:
            print(f"🔑 キーワード: {keyword}")
        if region:
            print(f"📍 地域: {region}")
    print("🤖 Claude API で下書きを生成中...")

    prompt = build_prompt(article_type, title, keyword, region, notes, cta_url)

    if dry_run:
        print("\n[DRY-RUN] 統合プロンプト（先頭600字）:")
        print("-" * 60)
        print(prompt[:600])
        print("-" * 60)
        print(f"(全体: {len(prompt)} 文字)")
        return prompt

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    draft = message.content[0].text

    date_str = datetime.now().strftime("%Y%m%d")
    slug = slugify(title)
    filename = f"{date_str}_{slug}.md"

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DRAFTS_DIR / filename

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(draft)

    print(f"\n✅ 下書きを {output_path} に保存しました。")
    print(f"\n--- 先頭300字 ---\n{draft[:300]}\n...")

    return str(output_path)


def interactive_mode() -> None:
    print("=== 記事下書き生成（対話モード）===\n")
    type_choices = " / ".join(ARTICLE_TYPES.keys())
    article_type = input(f"記事タイプ ({type_choices}) [省略=general]: ").strip() or "general"
    if article_type not in ARTICLE_TYPES:
        print(f"無効なタイプです: {article_type}")
        sys.exit(1)

    if article_type == "tokyo23":
        title = input("対象区名（例: 世田谷区）: ").strip()
        if not title:
            print("区名は必須です。")
            sys.exit(1)
        notes = input("補足（空白でスキップ）: ").strip()
        generate(article_type, title, notes=notes)
    else:
        title = input("記事タイトル: ").strip()
        if not title:
            print("タイトルは必須です。")
            sys.exit(1)
        keyword = input("メインキーワード（スペース区切りで複数可）: ").strip()
        region = input("地域（例: 世田谷区 / 空白でスキップ）: ").strip()
        notes = input("特記事項（空白でスキップ）: ").strip()
        generate(article_type, title, keyword, region, notes)


def main() -> None:
    parser = argparse.ArgumentParser(description="記事下書き生成スクリプト")
    parser.add_argument(
        "--type",
        dest="article_type",
        choices=list(ARTICLE_TYPES.keys()),
        default="general",
        metavar="TYPE",
        help="記事タイプ: general / case / tokyo23 / seasonal_pr（デフォルト: general）",
    )
    parser.add_argument("--title", help="記事タイトル（tokyo23 の場合は対象区名）")
    parser.add_argument("--keyword", help="メインキーワード", default="")
    parser.add_argument("--region", help="地域（例: 世田谷区）", default="")
    parser.add_argument("--notes", help="特記事項", default="")
    parser.add_argument("--interactive", action="store_true", help="対話モードで実行")
    parser.add_argument("--dry-run", action="store_true", help="API を呼ばずプロンプトのみ確認")
    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
    elif args.title:
        generate(
            args.article_type,
            args.title,
            args.keyword,
            args.region,
            args.notes,
            dry_run=args.dry_run,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
