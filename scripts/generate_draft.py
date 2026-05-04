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
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
DRAFTS_DIR = BASE_DIR / "data" / "drafts"
PROMPTS_DIR = BASE_DIR / "prompts"

ARTICLE_TYPES = {
    "general":     "article_general.md",
    "case":        "article_case.md",
    "tokyo23":     "article_tokyo23.md",
    "seasonal_pr": "article_seasonal_pr.md",
}

DEFAULT_CTA_URL = "https://aki-katsu.co.jp/counter/"

_REQUIRED_SECTIONS = [
    ("公的情報・参考ページ一覧", ["公的情報", "参考ページ", "参考リンク"]),
    ("よくある質問", ["wp:details", "よくある質問", "FAQ"]),
    ("まとめ", ["まとめ"]),
    ("CTA", ["swell-block-button", "aki-katsu.co.jp/counter", "loos/button"]),
]


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:40].strip("_").lower()


def _check_url(url: str):
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url, method=method, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (405, 429):
                continue
            return e.code
        except socket.gaierror:
            print(f"   [WARN] DNSエラー: {url}")
            return None
        except Exception:
            print(f"   [WARN] URL確認スキップ: {url}")
            return None
    return None


def strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:html)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def validate_draft(draft: str) -> list:
    errors = []

    if re.search(r"```", draft):
        errors.append("コードフェンス ``` が残存しています")

    if not re.search(r"公的情報|参考ページ|参考リンク", draft):
        errors.append("「公的情報・参考ページ一覧」セクションが見つかりません")

    if not re.search(r"wp:details|よくある質問|FAQ", draft):
        errors.append("「よくある質問」セクションが見つかりません")

    if not re.search(r"まとめ", draft):
        errors.append("「まとめ」セクションが見つかりません")

    if not re.search(r"swell-block-button|aki-katsu\.co\.jp/counter|loos/button", draft):
        errors.append("CTA（loos/button または swell-block-button）が見つかりません")

    details_open = len(re.findall(r"<!-- wp:details", draft))
    details_close = len(re.findall(r"<!-- /wp:details", draft))
    if details_open != details_close:
        errors.append(
            f"wp:details の開始({details_open})と終了({details_close})の数が一致しません"
        )

    tail = draft[-300:] if len(draft) > 300 else draft
    if re.search(r"<li>[^<]*$", tail):
        errors.append("末尾が <li> の途中で終わっています（出力途中終了の可能性）")
    if re.search(r"<p>[^<]*$", tail):
        errors.append("末尾が <p> の途中で終わっています（出力途中終了の可能性）")
    if re.search(r"[%…]$|\.{3}$", draft.rstrip()):
        errors.append("末尾が % または ... で終わっています（出力途中終了の可能性）")

    for url in set(re.findall(r'href=["\'](https?://[^"\'>\s]+)', draft)):
        code = _check_url(url)
        if code in (404, 410):
            errors.append(f"URL が {code} を返しています: {url}")
        elif code in (403, 405, 429):
            print(f"   [WARN] {url} → {code}（botブロック・HEAD拒否の可能性）")

    return errors


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
    theme_id: str = "",
) -> str:
    cta_url = os.environ.get("WP_CTA_URL", DEFAULT_CTA_URL)

    # theme_id が指定されている場合は articles_state.json から補完 & ステータス更新
    _theme_article = None
    if theme_id:
        try:
            from scripts.state import find_article, update_article as _update_article
            _theme_article = find_article(theme_id)
            if _theme_article is None:
                print(f"[WARN] theme-id={theme_id} の記事が articles_state.json に見つかりません。")
            else:
                if not keyword and _theme_article.get("keyword"):
                    keyword = _theme_article["keyword"]
                if not region and _theme_article.get("region"):
                    region = _theme_article["region"]
                if not dry_run:
                    _update_article(theme_id, status="drafting")
        except Exception as e:
            print(f"[WARN] articles_state.json の読み込みに失敗しました: {e}")
            _theme_article = None

    print(f"📝 記事タイプ: {article_type}")
    if article_type == "tokyo23":
        print(f"📍 対象区名: {title}")
    else:
        print(f"📝 記事タイトル: {title}")
        if keyword:
            print(f"🔑 キーワード: {keyword}")
        if region:
            print(f"📍 地域: {region}")
    if theme_id:
        print(f"🔗 テーマID: {theme_id}")
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
        max_tokens=16000,
        extra_headers={"anthropic-beta": "output-128k-2025-02-19"},
        messages=[{"role": "user", "content": prompt}],
    )

    draft = strip_code_fences(message.content[0].text)
    errors = validate_draft(draft)

    date_str = datetime.now().strftime("%Y%m%d")
    slug = slugify(title)

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    if errors:
        filename = f"{date_str}_{slug}.incomplete.md"
        output_path = DRAFTS_DIR / filename
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(draft)
        print(f"\n⚠️  バリデーションエラーが検出されました:")
        for err in errors:
            print(f"   - {err}")
        print(f"\n📄 不完全な下書きを {output_path} に保存しました。")
    else:
        filename = f"{date_str}_{slug}.md"
        output_path = DRAFTS_DIR / filename
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(draft)
        print(f"\n✅ 下書きを {output_path} に保存しました。")

    print(f"\n--- 先頭300字 ---\n{draft[:300]}\n...")

    # articles_state.json を更新
    if theme_id and _theme_article:
        try:
            from scripts.state import update_article as _update_article
            draft_rel = str(output_path.relative_to(BASE_DIR))
            _update_article(theme_id, status="draft_ready", draft_file=draft_rel)
            print(f"📋 articles_state.json 更新: [{theme_id}] → draft_ready")
        except Exception as e:
            print(f"[WARN] articles_state.json の更新に失敗しました: {e}")

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
    parser.add_argument(
        "--theme-id",
        default="",
        metavar="ID",
        help="articles_state.json のテーマID（指定するとステータスを自動更新）",
    )
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
            theme_id=args.theme_id,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
