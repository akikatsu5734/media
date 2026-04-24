# アキカツ 記事編集自動化ワークフロー

空き家課題解決メディア「アキカツ」の記事制作を、Claude Code + RSS + WordPress API で半自動化するツール群。

## 全体フロー
- `collect_rss.py` → RSS から空き家関連の話題を収集
- `propose_themes.py` → Claude API でテーマ・タイトル案を生成（人間が選択）
- `generate_draft.py` → Claude API で記事下書きを生成
- `post_to_wordpress.py` → WordPress に下書き保存（人間が確認・公開）

## ディレクトリ構成
```text
.
├── scripts/
│   ├── collect_rss.py               # 情報収集
│   ├── propose_themes.py            # テーマ提案
│   ├── generate_draft.py            # 記事下書き生成
│   └── post_to_wordpress.py         # WordPress 下書き投稿
├── prompts/
│   ├── theme_proposal.md            # テーマ提案プロンプト補足
│   └── article_draft.md             # 記事生成プロンプト補足
├── data/
│   ├── rss_sources.json             # RSS ソース定義（要設定）
│   ├── collected_topics.json        # 収集した話題（自動生成）
│   ├── theme_proposals.md           # テーマ提案レポート（自動生成）
│   ├── posted.json                  # 投稿ログ（自動生成）
│   └── drafts/                      # 生成した記事下書き（自動生成）
├── docs/
│   ├── ai_strategy.md
│   ├── ai_strategy_tasks.md
│   └── claude_code_editorial_automation_feasibility.md
├── .env                             # 認証情報（git 管理外）
├── .env.example                     # 設定テンプレート
└── requirements.txt
```

## セットアップ

### 1. 依存ライブラリのインストール
```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定
```bash
cp .env.example .env
```

`.env` を編集して以下を設定してください。

- `ANTHROPIC_API_KEY`
- `WP_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD`

WordPress の Application Password は、管理画面 → ユーザー → プロフィール → アプリケーションパスワード から発行できます。

### 3. RSS ソースの設定
`data/rss_sources.json` を開き、利用したいソースの `"enabled": false` を `"enabled": true` に変更してください。

## 使い方

### Step 1: 情報収集
```bash
python scripts/collect_rss.py
```

`data/collected_topics.json` に保存されます。

### Step 2: テーマ提案の生成
```bash
python scripts/propose_themes.py
```

`data/theme_proposals.md` に5テーマの提案が保存されます。  
`data/theme_proposals.md` を開き、書きたいテーマとタイトルを選んでください。

### Step 3: 記事下書きの生成
```bash
python scripts/generate_draft.py \
  --title "世田谷区の空き家補助金2026年最新版" \
  --keyword "空き家 補助金 世田谷" \
  --region "世田谷区"
```

対話モードでも実行できます。

```bash
python scripts/generate_draft.py --interactive
```

生成された下書きは `data/drafts/` に保存されます。公開前に必ず内容を確認・編集してください。

### Step 4: WordPress に下書き保存
動作確認だけ行う場合：

```bash
python scripts/post_to_wordpress.py --file data/drafts/20260424_世田谷区.md --dry-run
```

実際に下書き投稿する場合：

```bash
python scripts/post_to_wordpress.py --file data/drafts/20260424_世田谷区.md
```

投稿後は WordPress 管理画面で確認し、人間が公開操作を行ってください。

## 重要な注意事項
- 完全自動公開は禁止: `post_to_wordpress.py` は常に `status: draft` で投稿します
- 事実確認は必須: 法律・制度・補助金の数値は必ず一次ソースで確認してください
- スクレイピング禁止: RSS / 公式 API のみ使用します
- API キーの管理: `.env` ファイルは絶対に git にコミットしないでください

## 将来の分析ループ（未実装）
公開後に GA4 / Search Console データを取得・分析し、次テーマへ反映するループは以下で拡張予定です。

- `scripts/analyze_performance.py`   # GA4 / Search Console データ取得・集計（未実装）
- `scripts/suggest_improvements.py`  # 記事改善提案（未実装）

`posted.json` に投稿記録が蓄積されるため、将来の分析ループと接続しやすい構造になっています。
