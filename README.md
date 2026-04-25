# アキカツ 記事編集自動化ワークフロー

空き家課題解決メディア「アキカツ」の記事制作を、Claude Code + RSS + WordPress API で半自動化するツール群。

## 実装状況

| スクリプト | 状態 | 概要 |
|-----------|------|------|
| `collect_rss.py` | ✅ 実装済み | RSS から空き家関連の話題を収集 |
| `propose_themes.py` | ✅ 実装済み | Claude API でテーマ・タイトル案を生成 |
| `generate_draft.py` | ✅ 実装済み | Claude API で記事下書きを生成 |
| `post_to_wordpress.py` | ✅ 実装済み（予約投稿対応） | WordPress に下書き保存 / 予約投稿 |
| `analyze_performance.py` | 🔧 スタブ実装（手動データ入力が必要） | 記事パフォーマンスを分析・レポート生成 |
| `suggest_improvements.py` | 🔧 スタブ実装（performance_data.json が必要） | Claude API で記事改善提案を生成 |

**🔧 スタブ**: 骨格・ロジックは実装済みだが、GA4/Search Console API への接続は未完了。手動でデータを用意することで動作する。

## 全体フロー
【記事制作フロー（稼働中）】

collect_rss.py → RSS から空き家関連の話題を収集
propose_themes.py → Claude API でテーマ・タイトル案を生成（人間が選択）
generate_draft.py → Claude API で記事下書きを生成
post_to_wordpress.py → WordPress に下書き保存 / 予約投稿（人間が確認・公開）
【公開後分析フロー（手動データ入力で動作可能）】
5. analyze_performance.py → パフォーマンスデータを集計・レポート生成
6. suggest_improvements.py → 改善対象を抽出し Claude API で改善提案を生成
↓
→ 3. generate_draft.py（リライト）に戻る

## セットアップ
### 1. 依存ライブラリのインストール
```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定
```bash
cp .env.example .env
# .env を編集して以下を設定:
# - ANTHROPIC_API_KEY
# - WP_URL
# - WP_USERNAME
# - WP_APP_PASSWORD
```

### 3. RSS ソースの設定
data/rss_sources.json を開き、利用したいソースの "enabled": false を "enabled": true に変更してください。

## 使い方
### Step 1: 情報収集
```bash
python scripts/collect_rss.py
```

### Step 2: テーマ提案の生成
```bash
python scripts/propose_themes.py
```

### Step 3: 記事下書きの生成
```bash
python scripts/generate_draft.py --interactive
```

### Step 4: WordPress に下書き保存 / 予約投稿
```bash
python scripts/post_to_wordpress.py --file data/drafts/example.md --dry-run
python scripts/post_to_wordpress.py --file data/drafts/example.md
python scripts/post_to_wordpress.py --file data/drafts/example.md --schedule "2026-04-25T10:00:00"
```

### Step 5: パフォーマンス分析（公開後）
```bash
python scripts/analyze_performance.py --create-example
cp data/performance_data.json.example data/performance_data.json
python scripts/analyze_performance.py
```

### Step 6: 改善提案の生成
```bash
python scripts/suggest_improvements.py --dry-run
```

## 重要な注意事項
- 完全自動公開は禁止
- 事実確認は必須
- スクレイピング禁止
- API キーの管理に注意

## 次に人間がやるべき設定
- Search Console / GA4 データの手動入力
- Google API の自動接続
- 予約投稿のタイムゾーン確認
