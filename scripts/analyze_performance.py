#!/usr/bin/env python3
"""
記事パフォーマンス分析スクリプト

data/performance_data.json を読み込み、記事ごとの指標を集計して
data/performance_report.md に出力する。
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
PERFORMANCE_FILE = BASE_DIR / "data" / "performance_data.json"
PERFORMANCE_EXAMPLE = BASE_DIR / "data" / "performance_data.json.example"
REPORT_FILE = BASE_DIR / "data" / "performance_report.md"


def create_example_data() -> dict:
    base_url = "https://aki-katsu.co.jp/magazine/"
    today = datetime.now()
    return {
        "_comment": "このファイルは手動で編集するか、将来的にAPIで自動生成されます。",
        "fetched_at": today.isoformat(),
        "period": {
            "start": (today - timedelta(days=28)).strftime("%Y-%m-%d"),
            "end": today.strftime("%Y-%m-%d"),
        },
        "articles": [
            {
                "url": f"{base_url}setagaya-akiya-hojokin/",
                "title": "世田谷区の空き家補助金2026年最新版",
                "wp_post_id": 101,
                "published_at": "2026-04-01",
                "search_console": {
                    "impressions": 1200,
                    "clicks": 48,
                    "ctr": 0.04,
                    "avg_position": 8.5,
                    "top_queries": ["世田谷区 空き家 補助金", "空き家 補助金 東京"],
                },
                "ga4": {
                    "sessions": 60,
                    "page_views": 75,
                    "bounce_rate": 0.55,
                    "avg_session_duration_sec": 180,
                },
            }
        ],
    }


def classify_articles(articles: list[dict]) -> dict:
    high_impression_low_ctr = []
    low_impression_old = []
    mid_position = []
    good_performers = []
    today = datetime.now().date()
    for a in articles:
        sc = a.get("search_console", {})
        impressions = sc.get("impressions", 0)
        ctr = sc.get("ctr", 0.0)
        avg_pos = sc.get("avg_position", 0.0)
        published_str = a.get("published_at", "")
        days_since_publish = 9999
        if published_str:
            try:
                pub_date = datetime.strptime(published_str, "%Y-%m-%d").date()
                days_since_publish = (today - pub_date).days
            except ValueError:
                pass
        if impressions >= 500 and ctr < 0.02:
            high_impression_low_ctr.append(a)
        elif impressions < 100 and days_since_publish >= 30:
            low_impression_old.append(a)
        elif 10.0 < avg_pos <= 20.0 and impressions >= 100:
            mid_position.append(a)
        else:
            good_performers.append(a)
    return {
        "high_impression_low_ctr": high_impression_low_ctr,
        "low_impression_old": low_impression_old,
        "mid_position": mid_position,
        "good_performers": good_performers,
    }


def format_article_row(a: dict) -> str:
    sc = a.get("search_console", {})
    ga = a.get("ga4", {})
    ctr_pct = f"{sc.get('ctr', 0) * 100:.1f}%"
    pos = f"{sc.get('avg_position', 0):.1f}"
    queries = ", ".join(sc.get("top_queries", [])[:2]) or "—"
    return (
        f"- **{a['title']}**\n"
        f"  - 表示回数: {sc.get('impressions', 0):,} / クリック: {sc.get('clicks', 0):,} / CTR: {ctr_pct} / 平均順位: {pos}\n"
        f"  - 代表クエリ: {queries}\n"
        f"  - セッション: {ga.get('sessions', 0):,} / 直帰率: {ga.get('bounce_rate', 0)*100:.0f}%\n"
        f"  - URL: {a.get('url', '')}"
    )


def generate_report(data: dict) -> str:
    articles = data.get("articles", [])
    period = data.get("period", {})
    classified = classify_articles(articles)
    lines = [
        "# 記事パフォーマンスレポート",
        "",
        f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"分析期間: {period.get('start', '不明')} 〜 {period.get('end', '不明')}",
        f"対象記事数: {len(articles)} 件",
        "",
        "---",
        "",
    ]
    total_imp = sum(a.get("search_console", {}).get("impressions", 0) for a in articles)
    total_clicks = sum(a.get("search_console", {}).get("clicks", 0) for a in articles)
    avg_ctr = total_clicks / total_imp if total_imp > 0 else 0
    lines += [
        "## サマリー",
        "",
        "| 指標 | 合計 / 平均 |",
        "|------|------------|",
        f"| 総表示回数 | {total_imp:,} |",
        f"| 総クリック数 | {total_clicks:,} |",
        f"| 平均CTR | {avg_ctr*100:.2f}% |",
        "",
    ]
    groups = [
        ("high_impression_low_ctr", "⚠️ 表示は多いがCTRが低い記事（タイトル・メタ改善が有効）", "impressions >= 500, CTR < 2%"),
        ("mid_position", "🎯 11〜20位圏内でリライト余地がある記事", "avg_position 11〜20, impressions >= 100"),
        ("low_impression_old", "📉 公開から30日以上経過しているのに表示が少ない記事", "impressions < 100, 公開30日以上"),
        ("good_performers", "✅ 良好なパフォーマンスの記事", "上記以外"),
    ]
    for key, heading, condition in groups:
        group = classified[key]
        lines += [f"## {heading}", "", f"条件: {condition}", ""]
        if group:
            for a in group:
                lines.append(format_article_row(a))
                lines.append("")
        else:
            lines += ["（該当なし）", ""]
    lines += [
        "---",
        "",
        "## 次のステップ",
        "",
        "1. `suggest_improvements.py` を実行して改善提案を生成する",
        "   ```bash",
        "   python scripts/suggest_improvements.py",
        "   ```",
        "2. 生成された `data/improvement_proposals.md` を確認して優先対応記事を選ぶ",
        "",
    ]
    return "\n".join(lines)


def fetch_from_ga4(property_id: str, start_date: str, end_date: str) -> list[dict]:
    raise NotImplementedError("GA4 API 接続は未実装です。data/performance_data.json を手動で用意してください。")


def fetch_from_search_console(site_url: str, start_date: str, end_date: str) -> list[dict]:
    raise NotImplementedError("Search Console API 接続は未実装です。data/performance_data.json を手動で用意してください。")


def main() -> None:
    parser = argparse.ArgumentParser(description="記事パフォーマンス分析スクリプト")
    parser.add_argument("--create-example", action="store_true", help="data/performance_data.json.example を生成して終了")
    args = parser.parse_args()

    if args.create_example:
        example = create_example_data()
        PERFORMANCE_EXAMPLE.parent.mkdir(parents=True, exist_ok=True)
        with open(PERFORMANCE_EXAMPLE, "w", encoding="utf-8") as f:
            json.dump(example, f, ensure_ascii=False, indent=2)
        print(f"✅ サンプルデータを生成しました: {PERFORMANCE_EXAMPLE}")
        return

    if not PERFORMANCE_FILE.exists():
        print(f"[ERROR] {PERFORMANCE_FILE} が見つかりません。")
        print("python scripts/analyze_performance.py --create-example")
        sys.exit(1)

    with open(PERFORMANCE_FILE, encoding="utf-8") as f:
        data = json.load(f)

    report = generate_report(data)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ レポートを生成しました: {REPORT_FILE}")


if __name__ == "__main__":
    main()
