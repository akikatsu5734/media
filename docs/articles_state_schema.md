# articles_state.json スキーマ定義

`data/articles_state.json` は記事制作フローの単一の真実 (single source of truth)。
Notion DB はこのファイルを人間向けにミラーしたダッシュボードであり、状態の本体はこのファイルにある。

---

## トップレベル

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `version` | string | スキーマバージョン（現在: `"1.0"`） |
| `articles` | array | 記事エントリの配列 |

---

## articles[n] — 記事エントリ

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `id` | string | ✓ | 8文字の UUID 短縮形（例: `"a1b2c3d4"`） |
| `title` | string | ✓ | 記事タイトル（確定 or 候補A） |
| `type` | string | ✓ | `general` / `case` / `tokyo23` / `seasonal_pr` |
| `status` | string | ✓ | ステータス（下記の状態機械を参照） |
| `priority` | string | ✓ | `high` / `med` / `low` |
| `keyword` | string | | メインキーワード（スペース区切り複数可） |
| `region` | string | | 対象地域（例: `"世田谷区"`） |
| `source_url` | string | | 元ネタ RSS 記事 URL |
| `source_type` | string | | `rss` / `manual` / `seasonal` / `tokyo23` |
| `title_options` | object | | タイトル候補（下記参照） |
| `draft_file` | string\|null | | 下書きファイルの相対パス（例: `"data/drafts/20260428_....md"`） |
| `image_file` | string\|null | | アイキャッチ画像の相対パス（例: `"data/images/20260428_....png"`） |
| `wp_post_id` | number\|null | | WordPress 投稿 ID（投稿後に設定） |
| `public_url` | string\|null | | 公開後の URL |
| `notion_page_id` | string\|null | | Notion ページ ID（同期後に自動設定） |
| `created_at` | string | ✓ | ISO 8601 形式の作成日時（例: `"2026-04-28T10:00:00"`） |
| `published_at` | string\|null | | ISO 8601 形式の公開日時 |
| `decision_notes` | string | | 承認/却下の判断メモ（人間が記入） |

### title_options オブジェクト

`propose_themes.py` が生成したタイトル候補を保持する。

| キー | 説明 |
|------|------|
| `seo` | タイトル案A（SEO重視） |
| `user` | タイトル案B（ユーザー課題重視） |
| `regional` | タイトル案C（地域特化） |

---

## ステータス状態機械
proposed
├─→ rejected （人間が却下。終端）
└─→ approved （人間が Notion または JSON を直接編集して承認）
└─→ drafting （generate_draft.py 実行開始時）
└─→ draft_ready （下書き保存完了時）
└─→ image_ready （generate_image.py 実行完了時）
└─→ wp_draft （post_to_wordpress.py で下書き投稿時）
├─→ scheduled （予約投稿時）
└─→ published （公開済み）
└─→ needs_rewrite （パフォーマンス分析で判定）
└─→ drafting（リライトループ）

| ステータス | 設定タイミング |
|-----------|--------------|
| `proposed` | `propose_themes.py` 実行時 |
| `approved` | 人間が Notion または JSON を直接編集 |
| `rejected` | 人間が Notion または JSON を直接編集 |
| `drafting` | `generate_draft.py --theme-id` 実行開始時 |
| `draft_ready` | `generate_draft.py` 下書き保存完了時 |
| `image_ready` | `generate_image.py` 画像保存完了時（将来実装） |
| `wp_draft` | `post_to_wordpress.py` 下書き投稿成功時 |
| `scheduled` | `post_to_wordpress.py --schedule` 実行成功時 |
| `published` | `post_to_wordpress.py` 公開ステータスで投稿成功時 |
| `needs_rewrite` | `analyze_performance.py` による判定（将来実装） |
| `archived` | 人間が手動で設定 |

---

## サンプル
```json
{
  "version": "1.0",
  "articles": [
    {
      "id": "a1b2c3d4",
      "title": "世田谷区の空き家補助金2026年最新情報",
      "type": "tokyo23",
      "status": "approved",
      "priority": "high",
      "keyword": "世田谷区 空き家 補助金",
      "region": "世田谷区",
      "source_url": "https://example.com/news/123",
      "source_type": "rss",
      "title_options": {
        "seo": "世田谷区の空き家補助金2026年最新情報",
        "user": "世田谷区で空き家の補助金を使う方法",
        "regional": "世田谷区｜空き家補助金の申請手順と注意点"
      },
      "draft_file": "data/drafts/20260428_世田谷区の空き家補助金.md",
      "image_file": null,
      "wp_post_id": null,
      "public_url": null,
      "notion_page_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "created_at": "2026-04-28T10:00:00",
      "published_at": null,
      "decision_notes": "今月の補助金申請シーズンに合わせて優先度高"
    }
  ]
}
```
