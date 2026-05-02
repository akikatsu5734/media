#!/usr/bin/env python3
"""
記事改善提案スクリプト

data/performance_data.json と data/posted.json を読み込み、
改善対象記事を抽出して Claude API で改善提案を生成する。
出力は data/improvement_proposals.md に保存される。

前提: analyze_performance.py を先に実行してデータを確認しておくこと。

使用例:
  python scripts/suggest_improvements.py
  python scripts/suggest_improvements.py --dry-run  # API呼び出しなしでプロンプトを確認
  python scripts/suggest_improvements.py --max 5    # 最大5件を対象にする（デフォルト: 10）
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
        print("  先に analyze_performance.py を実行してください:")
        print("  python scripts/analyze_performance.py --create-example")
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
    """
    改善優先度スコアを計算して上位記事を返す。
    各記事に _improvement_reason（選定理由）を付与する。
    """
    today = datetime.now().date()
    scored = []

    for a in articles:
        sc = a.get("search_console", {})
        impressions = sc.get("impressions", 0)
        ctr = sc.get("ctr", 0.0)
        avg_pos = sc.get("avg_position", 0.0)
        published_str = a.get("published_at", "")

        days_since_publish = 0
        if published_str:
            try:
                pub_date = datetime.strptime(published_str, "%Y-%m-%d").date()
                days_since_publish = (today - pub_date).days
            except ValueError:
                pass

        # スコアリング: 改善インパクトが大きい順に並べる
        score = 0
        reasons = []

        # 表示が多いのにCTRが低い → 高スコア（タイトル改善でクリック増）
        if impressions >= 500 and ctr < 0.02:
            score += 30 + impressions // 100
            reasons.append(f"⚠️  表示{impressions:,}回あるがCTR {ctr*100:.1f}%（低い）→ タイトル・メタ改善が有効")

        # 11〜20位圏内 → 中スコア（リライトで上位進出の余地）
        if 10.0 < avg_pos <= 20.0 and impressions >= 100:
            score += 20
            reasons.append(f"🎯 平均順位{avg_pos:.1f}位（11〜20位圏）→ リライトで上位進出の余地あり")

        # 公開済みで長期間インプレッションが少ない → 低スコア（構造的問題）
        if impressions < 100 and days_since_publish >= 30:
            score += 10
            reasons.append(f"📉 公開{days_since_publish}日後も表示{impressions}回のみ → SEO強化が必要")

        # CTRが極端に低い場合は加点
        if impressions > 0 and ctr < 0.01:
            score += 5
            reasons.append(f"   CTR {ctr*100:.2f}%（極端に低い）")

        # スコア0の記事は良好なのでスキップ
        if score > 0:
            a["_improvement_reason"] = reasons
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
        title = a.get("title") or a.get("url", "（タイトル不明）")
        articles_text += f"""
### 記事 {i}: {title}
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
- 補助金・法律・制度の数値は引用しない（ファクトチェック対象外のため）
"""
    return template + "\n" + base_prompt if template else base_prompt


def main() -> None:
    parser = argparse.ArgumentParser(description="記事改善提案スクリプト")
    parser.add_argument("--max", type=int, default=10, help="改善対象の最大記事数（デフォルト: 10）")
    parser.add_argument("--dry-run", action="store_true", help="API を呼ばずプロンプトのみ確認")
    args = parser.parse_args()

    articles = load_performance_data()
    posted = load_posted_log()

    print(f"📊 パフォーマンスデータ: {len(articles)} 件")
    print(f"📝 投稿ログ: {len(posted)} 件")

    targets = select_improvement_targets(articles, max_articles=args.max)

    if not targets:
        print("\n✅ 改善が必要な記事は見つかりませんでした。（全記事が良好か、データが不十分です）")
        sys.exit(0)

    print(f"🎯 改善対象として選定: {len(targets)} 件\n")
    for i, a in enumerate(targets, 1):
        sc = a.get("search_console", {})
        title = a.get("title") or a.get("url", "（タイトル不明）")
        print(f"  {i}. {title}")
        print(f"     表示: {sc.get('impressions',0):,} / クリック: {sc.get('clicks',0):,} / CTR: {sc.get('ctr',0)*100:.1f}% / 順位: {sc.get('avg_position',0):.1f}位")
        for reason in a.get("_improvement_reason", []):
            print(f"     {reason}")
        print()

    prompt = build_prompt(targets)

    if args.dry_run:
        print("[DRY-RUN] API は呼び出しません。上記が改善対象の分析結果です。")
        print("         実際に提案を生成するには --dry-run を外して再実行してください。")
        return

    print("\n🤖 Claude API で改善提案を生成中...")
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

    print(f"\n✅ 改善提案を {OUTPUT_FILE} に保存しました。")
    print("\n--- 提案内容（先頭500字）---")
    print(result[:500])
    print(f"\n次のステップ: {OUTPUT_FILE} を確認し、対応する記事を選んで編集してください。")


if __name__ == "__main__":
    main()
