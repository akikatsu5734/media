# 記事生成 共通ルール

このファイルは全記事タイプで共通のルールを定義する。
`generate_draft.py` はこのファイルをタイプ別テンプレートの前にプレペンドして使用する。

---

## 出力形式の最重要ルール

- 出力は **WordPressブロックHTML のみ**。解説・前置き・補足・注意書きは一切不要
- **` ```html ` や ` ``` ` のコードフェンスは絶対に出力しない**（CLIスクリプトが直接ファイルに書き出すため、コードフェンスが混入すると破損する）
- 本文先頭は `<!-- wp:paragraph -->` などの WordPressブロックコメントから始める
- 省略記号や途中省略を入れない
- WordPressブロックコメント形式（`<!-- wp:... -->`）で出力する
- H1は本文に入れない（記事タイトルはWordPressの投稿タイトル欄で設定する前提）
- SWELLテーマでそのまま使いやすい、現実的で崩れにくい構成にする
- カスタムCSSやJavaScriptに依存しない
- `<!-- wp:tag-cloud /-->` は出力しない
- 関連記事ブロックは不要

---

## 事前調査の要件

- 記事を生成する前に、必ず必要な情報を徹底的に調べること
- 公的機関・一次情報を最優先する（国土交通省、法務局、国税庁、総務省、消費者庁、自治体公式サイト、不動産関連団体等）
- 民間情報を使う場合も、信頼性の高い情報源を優先する
- 数値・年度・制度名・期限・金額は必ず最新情報を確認する
- 不明・未確認の情報は「※要確認」と明記して捏造しない
- 変動する可能性のある情報（補助金額・申請期限・制度内容）は「最新情報は公式サイトをご確認ください」と必ず付記する

---

## リンクの実装ルール

- 外部リンク・内部リンク（別記事）・CTAリンクの a タグには必ず以下を付与する
  - `target="_blank"`
  - `rel="noopener noreferrer"`
- 目次内のアンカーリンク（`#mokuji` 等、同一ページ内リンク）には target・rel を付けない

---

## 目次の実装ルール

- 目次は必ず `is-style-crease` の `wp:group` で囲む
- 内部は `loos/link-list` + `loos/link-list-item` の正規構造を使う
- 各リンクは `a` タグ1つ + `span.swell-block-linkList__text` の構造にする
- `id="mokuji"` を h2 に付与して目次のアンカーとして使う
- 目次リンクには `target="_blank"` を付けない（同一ページ内リンクのため）
- 各セクションのアンカー ID は `sec1` / `sec2` のような連番は使わない。内容に対応した短いローマ字（例: `akiya-toha` / `tetsuzuki` / `faq`）を使う
- 目次に列挙した項目は、必ず本文側にも対応する見出しを出力する（目次と本文の対応を一致させる）

---

## 公的情報・参考ページ一覧の実装ルール

- 公的情報・参考リンクの一覧は `loos/link-list` で実装する
- `is-style-crease` は使わない（目次と区別するため）
- 外部リンクには必ず `target="_blank" rel="noopener noreferrer"` を付ける

---

## CTAボタンの実装ルール

- CTAボタンは必ず SWELL ボタン（`loos/button`）を使う
- `wp:buttons` や `wp:button` は使わない
- 色は原則 `green`
- className は `is-style-btn_normal` を使う

---

## ステップブロックの実装ルール

- 「手続きの流れ」「進め方」「確認の順番」など、順番がある内容は通常の番号付きリストではなく必ず SWELL の step ブロックを使う

---

## FAQの実装ルール

- FAQ は WordPress の `details` ブロックを使う
- `<!-- wp:details -->` 形式で実装する
- 質問文は `<summary>` タグに入れる

---

## 表の実装ルール

- 表は `wp:table` で実装する
- `hasFixedLayout: true` は使わない（列幅を均等固定にしない）
- セルの幅はコンテンツに合わせて自然に調整される形にする
- `className` に `is-style-stripes` を付けると縞模様になる（使う場合のみ）

---

## 複数カラムカードの実装ルール

- 3カラムのカード構成には `wp:columns` を使う
- `verticalAlignment: "stretch"` を必ず付ける（縦幅を揃えるため）
- 各カラム内のテキスト量が異なる場合、`wp:spacer` を末尾に置いて縦幅を揃える

---

## 必須セクションの出力ルール

以下のセクションは **省略禁止**。必ず最後まで出力すること。

1. 公的情報・参考ページ一覧
2. よくある質問（`wp:details` ブロック）
3. まとめ（記事全体の要点）
4. CTA（`loos/button` を使った `swell-block-button`）

- 中盤の解説セクションを長くしすぎず、後半のFAQ・まとめ・CTAまで必ず到達することを最優先する
- **各H2セクションの本文は 400〜600字程度を目安にする**（長すぎると後半のセクションが省略されるため）

---

## 文体・トーンのルール

- 文末は「〜です」「〜ます」調で統一する
- 専門用語は初出時に平易な言葉で補足する
- 断定表現を避け、法律・制度は「〜とされています」「〜の場合があります」等の表現を使う
- 読者を「あなた」と呼ぶのは避け、「空き家の所有者の方」等の表現を使う
- カタカナ語は最小限にする（「コンサルタント」→「相談員」等）


---

## WordPress SWELL ブロック出力ルール（最優先）

以下のルールは、WordPressコードエディター用の本文HTMLを生成する際に必ず優先する。

### 公的情報・参考リンク

- 架空URLは絶対に使用禁止。
- 実在する公式URL（中央省庁・自治体・国の機関の公式サイト）のみ使用する。
- 外部リンクには必ず `target="_blank" rel="noopener noreferrer"` を付ける。
- curlで403が返る場合はbotブロックの可能性があるため、403だけを理由に不正URL扱いしない。
- 明らかな404や誤ったURLパスは使用しない。

### CTAボタン

**禁止：** `wp-block-loos-button` div や `swell-block-btn` を `<a>` タグの class に使う構造は使わない。

**標準構造：**

```html
<!-- wp:loos/button {"hrefUrl":"{{WP_CTA_URL}}","color":"green","className":"is-style-btn_normal"} -->
<div class="swell-block-button green_ is-style-btn_normal">
  <a href="{{WP_CTA_URL}}" class="swell-block-button__link" target="_blank" rel="noopener noreferrer">
    <span>ボタンテキスト</span>
  </a>
</div>
<!-- /wp:loos/button -->
```

- 空き家相談系記事のデフォルトURLは `{{WP_CTA_URL}}` を使う。
- CTAリンクには必ず `target="_blank" rel="noopener noreferrer"` を付ける。

### CTA見出しの重複禁止

- CTA直前のH2と cap_box_ttl に同じ文言を使う構成は禁止。
- 例：H2「迷ったら無料相談へ」＋ cap_box_ttl「迷ったら無料相談へ」は使わない。
- CTAはH2なしでcap-blockを直接出力し、cap_box_ttlでタイトルを表現する。
- 目次アンカー `id="cta"` が必要な場合は、cap-blockの親要素に付与する。

### ステップブロック

手順系・流れ系セクションでは、通常の番号付きリストではなく、必ずSWELLのstepブロックを使う。

**禁止：**
- `swell-block-stepItem`
- `swell-block-stepItem__num`
- `STEP01` / `STEP02` 形式

**標準構造：**

```html
<!-- wp:loos/step -->
<div class="swell-block-step" data-num-style="circle">

  <!-- wp:loos/step-item {"stepLabel":"STEP"} -->
  <div class="swell-block-step__item">
    <div class="swell-block-step__number u-bg-main"><span class="__label">STEP</span></div>
    <div class="swell-block-step__title u-fz-l">ステップタイトル</div>
    <div class="swell-block-step__body">
      <!-- wp:paragraph -->
      <p>本文テキスト</p>
      <!-- /wp:paragraph -->
    </div>
  </div>
  <!-- /wp:loos/step-item -->

</div>
<!-- /wp:loos/step -->
```

### FAQ

- FAQは `<!-- wp:details -->` ブロックで出力する。
- 質問文は `<summary>` タグに入れる。
- `<!-- wp:details -->` の開始タグ数と `<!-- /wp:details -->` の終了タグ数を必ず一致させる。

**禁止する回りくどい表現：**
- 「〜とは限らないのでしょうか？」
- 「〜ということになるのでしょうか？」
- 「〜にはなりませんか？」

**推奨する直接的な表現：**
- 「〜ますか？」
- 「〜できますか？」
- 「〜は必要ですか？」
- 「〜したら、〜になりますか？」

### まとめ3ポイント・複数カラムカード

- 複数カードを横並びにする場合は `columns` / `column` に `"verticalAlignment":"stretch"` を使う。
- カード間で本文量に差がある場合は `wp:spacer` を必要最小限で使い、目視上の高さを揃える。
- spacerは過剰に乱用しない。

**まとめ3ポイントの禁止構造：**
- `<p class="is-style-big_icon_point">Point1</p>` のように、Point表記だけをparagraphで出す形式は禁止。

**まとめ3ポイントの標準構造：**

- 各カードのgroupには `has-border -border02 is-style-big_icon_point` を指定する。
- 各カード内の順番は、H3（Point 1 / Point 2 / Point 3）→ 太字要点paragraph → 補足本文paragraph とする。

```html
<!-- wp:columns {"verticalAlignment":"stretch"} -->
<div class="wp-block-columns are-vertically-aligned-stretch">

  <!-- wp:column {"verticalAlignment":"stretch"} -->
  <div class="wp-block-column is-vertically-aligned-stretch">
    <!-- wp:group {"className":"has-border -border02 is-style-big_icon_point"} -->
    <div class="wp-block-group has-border -border02 is-style-big_icon_point">
      <!-- wp:heading {"level":3} -->
      <h3 class="wp-block-heading">Point 1</h3>
      <!-- /wp:heading -->
      <!-- wp:paragraph -->
      <p><strong>太字の要点テキスト</strong></p>
      <!-- /wp:paragraph -->
      <!-- wp:paragraph -->
      <p>補足本文テキスト</p>
      <!-- /wp:paragraph -->
    </div>
    <!-- /wp:group -->
  </div>
  <!-- /wp:column -->

  <!-- Point 2、Point 3 も同じ構造で作成する -->

</div>
<!-- /wp:columns -->
```

