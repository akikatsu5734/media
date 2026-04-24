#!/usr/bin/env python3
"""
記事テーマ提案スクリプト
collected_topics.json を読み込み、Claude API を使って今週書くべき記事テーマ候補を生成する。
出力は data/theme_proposals.md に保存される。
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
TOPICS_FILE = BASE_DIR / "data" / "collected_topics.json"
PROPOSALS_FILE = BASE_DIR / "data" / "theme_proposals.md"
PROMPT_FILE = BASE_DIR / "prompts" / "theme_proposal.md"

SEASONAL_THEMES = {
    1:  ["年明けに考える空き家整理", "固定資産税の納付と空き家の関係", "相続と空き家"],
    2:  ["確定申告と空き家の税務", "春の売却シーズン前の空き家整備"],
    3:  ["年度末の不動産市況と空き家売却タイミング", "新年度に向けた空き家活用"],
    4:  ["新生活と空き家の賃貸活用", "空き家バンク登録の春"],
    5:  ["ゴールデンウィークの空き家点検", "空き家の草木管理"],
    6:  ["梅雨の空き家湿気・カビ対策", "空き家の固定資産税軽減措置"],
    7:  ["夏の空き家管理・害虫対策", "空き家の熱中症・火災リスク"],
    8:  ["お盆に考える実家の将来", "空き家の水まわりトラブル予防"],
    9:  ["台風・大雨前の空き家点検", "秋の売却・賃貸検討シーズン"],
    10: ["空き家活用の秋・補助金申請シーズン", "古民家リノベーションのすすめ"],
    11: ["空き家の冬支度と管理", "年内売却を考える空き家所有者へ"],
    12: ["年末に考える空き家の行く末", "相続前に確認すべき空き家のこと"],
}


def load_topics() -> dict:
    if not TOPICS_FILE.exists():
        print(f"[ERROR] {TOPICS_FILE} が見つかりません。先に collect_rss.py を実行してください。")
        sys.exit(1)
    with open(TOPICS_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_prompt_template() -> str:
    if PROMPT_FILE.exists():
        with open(PROMPT_FILE, encoding="utf-8") as f:
            return f.read()
    return ""


def build_prompt(topics: list[dict], seasonal: list[str], today: str) -> str:
    template = load_prompt_template()

    topics_text = "\n".join(
        f"- [{t['source']}] {t['title']} ({t['published'][:10] if t['published'] else '不明'})\n  {t['summary'][:150]}"
        for t in topics[:20]
    )

    seasonal_text = "\n".join(f"- {s}" for s in seasonal)

    base_prompt = f"""あなたは空き家・不動産メディア「アキカツ」の編集長です。
今日は {today} です。

以下の情報を参考に、今週アキカツが発信すべき記事テーマを5つ提案してください。

## 今週収集した話題（一部）
{topics_text}

## 今月の季節性テーマ候補
{seasonal_text}

## 提案フォーマット（5テーマ分）

各テーマについて以下を出力してください。

### テーマ [番号]: [テーマの要旨]

**選定理由**: （なぜ今このテーマか・ユーザー課題との整合性）

**タイトル案A（SEO重視）**: 「...」
**タイトル案B（ユーザー課題重視）**: 「...」
**タイトル案C（地域特化）**: 「...」（特定の区・地域が絡む場合）

**想定キーワード**: キーワード1, キーワード2, キーワード3
**ターゲット読者**: （例: 相続した空き家を持つ40〜60代）
**推定優先度**: 高 / 中 / 低

---

## 条件
- 空き家所有者・相続予定者の実際の悩みに直結するテーマを優先する
- 地域性（特に東京23区）があるテーマを1つ以上含める
- 季節性・タイムリー性があるテーマを1つ以上含める
- 法律・制度・補助金は正確性を要するため「要確認」と明記する
- 完全自動公開でなく人間が確認する前提で提案する
"""
    return template + "\n" + base_prompt if template else base_prompt


def propose(dry_run: bool = False) -> str:
    data = load_topics()
    topics = data.get("topics", [])
    today = datetime.now().strftime("%Y年%m月%d日")
    month = datetime.now().month
    seasonal = SEASONAL_THEMES.get(month, [])

    print(f"📰 収集済みトピック: {len(topics)} 件")
    print(f"🌸 今月の季節性テーマ: {len(seasonal)} 件")
    print("🤖 Claude API でテーマを生成中...")

    prompt = build_prompt(topics, seasonal, today)

    if dry_run:
        print("\n[DRY-RUN] プロンプトのみ出力（API 呼び出しなし）:")
        print(prompt[:500] + "...")
        return prompt

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    result = message.content[0].text

    header = f"# 記事テーマ提案レポート\n\n生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"
    output = header + result

    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n✅ テーマ提案を {PROPOSALS_FILE} に保存しました。")
    print("\n--- 提案内容（先頭500字）---")
    print(result[:500])
    return result


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    propose(dry_run=dry_run)
