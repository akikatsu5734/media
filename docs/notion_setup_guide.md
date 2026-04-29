# Notion セットアップガイド

アキカツメディアの記事管理 Notion DB を構築する手順。

---

## 1. Notion インテグレーションを作成する

1. [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations) を開く
2. **「New integration」** をクリック
3. 以下を設定する
   - Name: `akikatsu-media`（任意）
   - Associated workspace: 使用するワークスペースを選択
   - Type: Internal
4. **「Submit」** をクリック
5. **「Internal Integration Secret」** をコピーして `.env` に設定する

```env
NOTION_API_KEY=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 2. Articles データベースを作成する

1. Notion で新しいページを作成する（「Akikatsu Media」など）
2. ページ内に **データベース（Table ビュー）** を追加する
3. データベース名を **`Articles`** にする
4. 以下のプロパティを追加する（デフォルトの「Name」プロパティは「Title」に改名する）

### プロパティ設定

| プロパティ名（英語） | 型 | 設定値 |
|--------------------|----|--------|
| Title | Title | （デフォルト。名前を「Title」に変更） |
| Article ID | テキスト | — |
| Type | セレクト | `general` `case` `tokyo23` `seasonal_pr` |
| Status | セレクト | 下記のステータスを全て追加 |
| Priority | セレクト | `high` `med` `low` |
| Keyword | テキスト | — |
| Region | テキスト | — |
| Source URL | URL | — |
| Source Type | セレクト | `rss` `manual` `seasonal` `tokyo23` |
| Draft File | テキスト | — |
| Image File | テキスト | — |
| WP Post ID | 数値 | — |
| Public URL | URL | — |
| Created | 日付 | — |
| Published | 日付 | — |
| Decision Notes | テキスト | — |

### Status セレクトに追加する値（全11種）

```text
proposed
approved
rejected
drafting
draft_ready
image_ready
wp_draft
scheduled
published
needs_rewrite
archived
```

> **ヒント**: Status にカラーを設定しておくと Kanban ビューで見やすくなります。  
> 例: proposed=グレー, approved=青, published=緑, rejected=赤

---

## 3. データベースをインテグレーションと共有する

1. 作成したデータベースページを開く
2. 右上の **「…」（More）** → **「Add connections」** をクリック
3. ステップ1で作成したインテグレーション（`akikatsu-media`）を選択して **確認**

---

## 4. データベース ID を取得する

1. データベースページのURLを確認する

```text
https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...
```

2. `notion.so/` の直後の32文字の英数字がデータベース ID  
（ハイフン区切りで `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` の形式でもOK）

3. `.env` に設定する

```env
NOTION_ARTICLES_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 5. 動作確認

```bash
# dry-run で同期予定を確認
python scripts/notion_sync.py --push --dry-run

# 実際に同期（articles_state.json にデータがある場合）
python scripts/notion_sync.py --push
```

## 6. 推奨ビュー設定

Notion DB に以下のビューを追加しておくと便利です。

| ビュー名 | 種類 | グループ化 | 説明 |
|---------|------|------------|------|
| 全記事 | テーブル | — | 全ステータスを一覧 |
| 承認待ち | テーブル | — | フィルタ: Status = proposed |
| 進行中 | カンバン | Status でグループ化 | drafting〜wp_draft の記事を可視化 |
| 公開済み | テーブル | — | フィルタ: Status = published |

## 7. 承認ゲートの使い方

1. `propose_themes.py` を実行 → Notion DB に `proposed` で記事が追加される  
2. 湯浅さんが Notion 上でタイトル案を確認し、Status を `approved` に変更  
3. `notion_sync.py --pull` を実行 → articles_state.json に `approved` が反映される  
4. `generate_draft.py --theme-id <id>` を実行 → 承認済み記事の下書き生成開始  

Phase 2 実装後は `generate_draft.py` が自動で `--pull` を呼び出すため、手動での pull は不要になります。
