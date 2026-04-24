#!/usr/bin/env python3
"""
記事下書き生成スクリプト
タイトルとキーワードを受け取り、Claude API を使って記事下書きを生成する。
出力は data/drafts/YYYYMMDD_<slug>.md に保存される。

使用例:
  python scripts/generate_draft.py --title "世田谷区の空き家補助金2026年最新版" --keyword "空き家 補助金 世田谷"
  python scripts/generate_draft.py --interactive  # 対話モード
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
PROMPT_FILE = BASE_DIR / "prompts" / "article_draft.md"


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:40].strip("_").lower()


def load_prompt_template() -> str:
    if PROMPT_FILE.exists():
        with open(PROMPT_FILE, encoding="utf-8") as f:
            return f.read()
    return ""


def build_article_prompt(title: str, keyword: str, region: str = "", notes: str = "") -> str:
    template = load_prompt_template()

    base_prompt = f"""あなたは空き家・不動産メディア「アキカツ」の専門ライターです。
以下の条件で記事を執筆してください。

## 記事情報
- タイトル: {title}
- メインキーワード: {keyword}
- 地域: {region if region else "指定なし（全国向け）"}
- 特記事項: {notes if notes else "なし"}

## 執筆ルール
- 読者は空き家を抱える40〜60代の所有者・相続予定者
- 専門用語は必ず平易な言葉で補足説明する
- 法律・制度・補助金の数値は「※要確認」と明記し、必ず一次ソースを確認するよう促す
- 文末は「〜です」「〜ます」調で統一する
- 記事末尾に必ずCTA（行動喚起）を入れる
- 見出しはH2・H3の2階層で構成する
- 文字数目安: 2,000〜3,000字

## 出力フォーマット（Markdown）

まず以下のフロントマターを出力してください:

---
title: "{title}"
keyword: "{keyword}"
region: "{region}"
excerpt: "（120字以内のメタディスクリプション）"
tags: ["タグ1", "タグ2", "タグ3"]
category: "（カテゴリ案）"
eyecatch_instruction: "（アイキャッチ画像の制作指示文）"
fact_check_required: true
status: draft
created_at: {datetime.now().strftime('%Y-%m-%d')}
---

次に本文を出力してください。

# {title}

（本文）

---
※この記事はAIが生成した下書きです。公開前に事実確認・編集を行ってください。
"""
    return template + "\n" + base_prompt if template else base_prompt


def generate(title: str, keyword: str, region: str = "", notes: str = "", dry_run: bool = False) -> str:
    print(f"📝 記事タイトル: {title}")
    print(f"🔑 キーワード: {keyword}")
    if region:
        print(f"📍 地域: {region}")
    print("🤖 Claude API で下書きを生成中...")

    prompt = build_article_prompt(title, keyword, region, notes)

    if dry_run:
        print("\n[DRY-RUN] プロンプトのみ出力（API 呼び出しなし）:")
        print(prompt[:400] + "...")
        return prompt

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
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


def interactive_mode(dry_run: bool = False) -> None:
    print("=== 記事下書き生成（対話モード）===\n")
    title = input("記事タイトル: ").strip()
    if not title:
        print("タイトルは必須です。")
        sys.exit(1)
    keyword = input("メインキーワード（スペース区切りで複数可）: ").strip()
    region = input("地域（例: 世田谷区 / 空白でスキップ）: ").strip()
    notes = input("特記事項（空白でスキップ）: ").strip()
    generate(title, keyword, region, notes, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="記事下書き生成スクリプト")
    parser.add_argument("--title", help="記事タイトル")
    parser.add_argument("--keyword", help="メインキーワード", default="")
    parser.add_argument("--region", help="地域（例: 世田谷区）", default="")
    parser.add_argument("--notes", help="特記事項", default="")
    parser.add_argument("--interactive", action="store_true", help="対話モードで実行")
    parser.add_argument("--dry-run", action="store_true", help="API を呼ばずプロンプトのみ確認")
    args = parser.parse_args()

    if args.interactive:
        interactive_mode(dry_run=args.dry_run)
    elif args.title:
        generate(args.title, args.keyword, args.region, args.notes, dry_run=args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
