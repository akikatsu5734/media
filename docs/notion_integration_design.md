# Notion 連携設計

アキカツメディアの記事制作フローにおける Notion 連携の設計方針と実装概要。

---

## 背景・課題

ファイルベースの記事制作自動化において以下の「情報の途切れ」が存在する。

1. `propose_themes.py` が出す `data/theme_proposals.md` は非構造 Markdown。承認/却下を追跡できない
2. テーマ → 下書き → 画像 → WP 投稿の各スクリプトが独立し、対応関係を中央管理する場所がない
3. 公開後の追跡が WordPress 管理画面の手動確認に依存している

---

## アーキテクチャ

```text
[ scripts/propose_themes.py ]
[ scripts/generate_draft.py ]
[ scripts/generate_image.py ]
[ scripts/post_to_wordpress.py ]
          ↕ 読み書き
[ data/articles_state.json ] ← 単一の真実（machine-readable）
          ↕ 同期（notion_sync.py）
[ Notion "Articles" DB ] ← 人間ダッシュボード（human-readable）
          ↕ 参照
[ data/drafts/.md, images/.png ] ← 成果物（ファイルのまま）
```

### 役割分担

| データ | 置き場所 | 理由 |
|--------|---------|------|
| 記事の状態（status, type, priority, dates） | JSON + Notion 両方 | 人間も AI も見る |
| タイトル案・判断メモ・承認状況 | Notion | 人間が編集する |
| 下書き本文 Markdown | `data/drafts/*.md` | 大きすぎる、AI が頻繁に書き換える |
| 画像ファイル | `data/images/*.png` | バイナリ、Notion に不向き |
| 認証情報 | `.env` | Notion に絶対置かない |

---

## Notion DB 設計（Articles DB 1つのみ）

### プロパティ一覧

| プロパティ名 | 型 | 用途 |
|-------------|-----|------|
| Title | title | タイトル案 / 確定タイトル |
| Article ID | rich_text | articles_state.json の id（照合キー） |
| Type | select | general / case / tokyo23 / seasonal_pr |
| Status | select | 下記ステータス一覧 |
| Priority | select | high / med / low |
| Keyword | rich_text | メインキーワード |
| Region | rich_text | 対象地域 |
| Source URL | URL | 元ネタ RSS URL |
| Source Type | select | rss / manual / seasonal / tokyo23 |
| Draft File | rich_text | data/drafts/...md のパス |
| Image File | rich_text | data/images/...png のパス |
| WP Post ID | number | WordPress 投稿 ID |
| Public URL | URL | 公開後の URL |
| Created | date | テーマ提案日 |
| Published | date | 公開日 |
| Decision Notes | rich_text | 承認/却下の判断メモ |

### ステータス一覧

`proposed` → `approved` / `rejected` → `drafting` → `draft_ready` → `image_ready` → `wp_draft` → `scheduled` / `published` → `needs_rewrite`

詳細は `docs/articles_state_schema.md` の状態機械を参照。

---

## 実装フェーズ

### Phase 0: ローカル状態ファイルの構造化（Notion なし）✅
- `data/articles_state.json` 新設
- `scripts/state.py` 読み書きヘルパ
- `propose_themes.py` が articles_state.json に追記
- `generate_draft.py` が `--theme-id` でステータス追跡
- `post_to_wordpress.py` が投稿成功時に articles_state.json を更新

### Phase 1: Notion 同期（file → Notion）✅
- `scripts/notion_sync.py` 新設
  - `--push`: articles_state.json → Notion DB（新規作成 + 更新）
  - `--pull`: Notion DB の Status → articles_state.json（承認ゲート用）
  - `--dry-run`: API を呼ばず差分確認

### Phase 2: 承認ゲート（将来）
- `generate_draft.py --theme-id` が Notion の status="approved" を確認してから実行
- `notion_sync.py --pull` を各スクリプト実行前に自動呼び出し

### Phase 3: 双方向同期 + 改善ループ（将来）
- Notion コメントを `decision_notes` に取り込む
- `analyze_performance.py` が低パフォーマンス記事を `needs_rewrite` に自動設定

---

## 設計上の判断

| 判断 | 理由 |
|------|------|
| 真実は articles_state.json、Notion は同期先 | Notion 障害でスクリプトが止まらないよう。ファイルなら git 履歴も追える |
| DB は最初の1つだけ | 複数 DB はリンク管理が複雑。1つで十分回る |
| 同期は file → Notion から開始 | 双方向は競合解決が難しい。Status の pull のみ例外として許容 |
| 下書き本文は Notion に置かない | 数千字 × Notion API は遅い。パスのみ参照 |
| notion_sync.py に集約 | 各スクリプトに Notion コードを散らさない |
| Notion 失敗はベストエフォート | 本業フローを止めない。エラーは警告として出力 |

---

## セットアップ手順

`docs/notion_setup_guide.md` を参照。
