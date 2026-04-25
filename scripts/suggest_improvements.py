#!/usr/bin/env python3
"""
記事改善提案スクリプト
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
PERFORMANCE_FILE = BASE_DIR / "data" / "performance_data.json"
POSTED_LOG = BASE_DIR / "data" / "posted.json"
OUTPUT_FILE = BASE_DIR / "data" / "improvement_proposals.md"
PROMPT_FILE = BASE_DIR / "prompts" / "article_review.md"


def load_performance_data() -> list[dict]:
    if not PERFORMANCE_FILE.exists():
        print(f"[ERROR] {PERFORMANCE_FILE} が見つかりません。")
        sys.exit(1)
    with open(PERFORMANCE_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("articles", [])


def load_posted_log() -> list[dict]:
    if not POSTED_LOG.exists():
        return []
    with open(POSTED_LOG, encoding="utf-8") as f:
        return json.load(f)


def load_prompt_template() -> str:
    if PROMPT_FILE.exists():
        with open(PROMPT_FILE, encoding="utf-8") as f:
            return f.read()
    return ""


def select_improvement_targets(articles: list[dict], max_articles: int = 10) -> list[dict]:
    scored = []
    for a in articles:
        sc = a.get("search_console", {})
        impressions = sc.get("impressions", 0)
        ctr = sc.get("ctr", 0.0)
        avg_pos = sc.get("avg_position", 0.0)
        score = 0
        if impressions >= 500 and ctr < 0.02:
            score += 30 + impressions // 100
        if 10.0 < avg_pos <= 20.0 and impressions >= 100:
            score += 20
        if impressions > 0 and ctr < 0.01:
            score += 5
        if score > 0:
            scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored[:max_articles]]


def build_prompt(targets: list[dict]) -> str:
    template = load_prompt_template()
    articles_text = ""
    for i, a in enumerate(targets, 1):
        sc = a.get("search_console", {})
        ga = a.get("ga4", {})
        queries = ", ".join(sc.get("top_queries", [])[:3]) or "データなし"
        articles_text += f"""
### 記事 {i}: {a.get('title', '（タイトル不明）')}
- URL: {a.get('url', '')}
- 公開日: {a.get('published_at', '不明')}
- 表示回数: {sc.get('impressions', 0):,} / クリック: {sc.get('clicks', 0):,} / CTR: {sc.get('ctr', 0)*100:.1f}% / 平均順位: {sc.get('avg_position', 0):.1f}位
- 流入クエリ（上位）: {queries}
- セッション: {ga.get('sessions', 0):,} / 直帰率: {ga.get('bounce_rate', 0)*100:.0f}% / 平均滞在: {ga.get('avg_session_duration_sec', 0)}秒
"""
    base_prompt = f"""あなたは空き家・不動産メディア「アキカツ」のSEOコンサルタントです。
今日は {datetime.now().strftime('%Y年%m月%d日')} です。

以下の記事パフォーマンスデータをもとに、各記事の改善提案を生成してください。

## 改善対象記事（{len(targets)} 件）
{articles_text}

## 出力の要件
- 各記事について、数値データに基づいた具体的な改善提案を2〜3点出す
- タイトル改善案がある場合は、変更前→変更後の形で具体的に示す
- 優先度（高/中/低）を各提案に付ける
- 全体サマリーとして「最初に着手すべき記事トップ3」を最後にまとめる
- 根拠のない楽観的な見通しは書かない
"""
    return template + "\n" + base_prompt if template else base_prompt


def main() -> None:
    parser = argparse.ArgumentParser(description="記事改善提案スクリプト")
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    articles = load_performance_data()
    posted = load_posted_log()
    print(f"📊 パフォーマンスデータ: {len(articles)} 件")
    print(f"📝 投稿ログ: {len(posted)} 件")

    targets = select_improvement_targets(articles, max_articles=args.max)
    if not targets:
        print("改善が必要な記事は見つかりませんでした。")
        sys.exit(0)

    prompt = build_prompt(targets)
    if args.dry_run:
        print(prompt[:600] + "...")
        return

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    result = message.content[0].text

    header = (
        f"# 記事改善提案レポート\n\n"
        f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"対象記事数: {len(targets)} 件\n\n---\n\n"
    )
    output = header + result
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"✅ 改善提案を {OUTPUT_FILE} に保存しました。")


if __name__ == "__main__":
    main()
