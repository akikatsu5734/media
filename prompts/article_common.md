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
- `id="mokuji"` を h2 に付与して目次のアンカーとして使う
- 目次リンクには `target="_blank"` を付けない（同一ページ内リンクのため）
- 各セクションのアンカー ID は `sec1` / `sec2` のような連番は使わない。内容に対応した短いローマ字（例: `akiya-toha` / `tetsuzuki` / `faq`）を使う
- 目次に列挙した項目は、必ず本文側にも対応する見出しを出力する（目次と本文の対応を一致させる）

**目次リンクの必須HTMLクラス構造：**
- `ul`: `class="swell-block-linkList is-style-default"`
- `li`: `class="swell-block-linkList__item"`
- `a`: `class="swell-block-linkList__link"`（内部リンクのため `target` / `rel` は付けない）
- `a` タグ内に必ず `<!-- icon-placeholder -->` を入れる
- `span`: `class="swell-block-linkList__text"`

**禁止：**
- 通常の `ul` / `li` のみで出力（classなし）
- `a` タグに class なし・`icon-placeholder` なし
- div 形式の link-list-item

---

## 公的情報・参考ページ一覧の実装ルール（エビデンス最重要）

- **エビデンスは記事生成において最重要項目である**
- 掲載できるサイトは原則として公的サイトのみとする
  - 国の機関（国土交通省・法務局・国税庁・総務省・消費者庁 等）
  - 自治体公式サイト
  - 法務局・裁判所・公的機関
  - e-Gov法令検索など制度・法律の公式ページ
- 民間ブログ・まとめサイト・出典不明ページは原則使用しない
- リンクテキストとリンク先URLの内容を必ず一致させる
- リンクテキストは `省庁名｜ページの正式名称または制度名` を基本形にする
- URLが不明確な場合は深いURLを推測せず、省庁トップページや公式検索ページを使う
- URLがPDFの場合は資料名がわかるタイトルにする
- 架空URLは禁止
- 明らかな404 / 410は禁止
- 403 / 405 / 429 はbotブロック・HEAD拒否の可能性があるため、それだけで不正URL扱いしない
- 公的情報・参考リンクの一覧は目次と同じ SWELL link-list 構造で実装する
- `is-style-crease` は使わない（目次と区別するため）
- 外部リンクには必ず `target="_blank" rel="noopener noreferrer"` を付ける
- 実在する公式URLのみ使用する（架空URLは絶対禁止）

**参考リンクの必須HTMLクラス構造：**
- `ul`: `class="swell-block-linkList is-style-default"`
- `li`: `class="swell-block-linkList__item"`
- `a`: `class="swell-block-linkList__link"` + 必ず `target="_blank" rel="noopener noreferrer"` を付ける
- `a` タグ内に必ず `<!-- icon-placeholder -->` を入れる
- `span`: `class="swell-block-linkList__text"`

**禁止：**
- 通常のリスト / 通常リンクだけで出力
- `a` タグに class なし・`icon-placeholder` なし
- 架空URLの使用

---

## CTAボタンの実装ルール

- CTAボタンは必ず SWELL ボタン（`loos/button`）を使う
- `wp:buttons` や `wp:button` は使わない
- 色は原則 `green`
- className は `is-style-btn_normal` を使う

---

## ステップブロックの実装ルール

- 「手続きの流れ」「進め方」「確認の順番」など、順番がある内容は通常の番号付きリストではなく必ず SWELL の step ブロックを使う
- STEPブロック全体は必ず `has-border -border02` のボーダー付き `wp:group` で囲む
- 手順系セクションでSTEPを裸のまま（border groupなしで）出力しない

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

### 目次リンクリスト

目次アイテムは以下の HTML 構造を厳守する（classの省略・変更・div化は禁止）。

```html
<!-- wp:loos/link-list {"className":"is-style-default"} -->
<ul class="swell-block-linkList is-style-default">

  <!-- wp:loos/link-list-item {"url":"#section-id","label":"セクションタイトル"} -->
  <li class="swell-block-linkList__item">
    <a class="swell-block-linkList__link" href="#section-id"><!-- icon-placeholder --><span class="swell-block-linkList__text">セクションタイトル</span></a>
  </li>
  <!-- /wp:loos/link-list-item -->

</ul>
<!-- /wp:loos/link-list -->
```

- 内部リンクのため `target` / `rel` は付けない。
- `icon-placeholder` コメントと `swell-block-linkList__text` span は必須。

### 公的情報・参考リンク

- **エビデンスは記事生成において最重要項目である。公的サイト以外は原則禁止。**
- 架空URLは絶対に使用禁止。
- 実在する公式URL（国の機関・自治体・法務局・裁判所・e-Gov法令検索等）のみ使用する。
- 民間ブログ・まとめサイト・出典不明ページは原則使用しない。
- リンクテキストとリンク先URLの内容を必ず一致させる。
- リンクテキストは `省庁名｜ページの正式名称または制度名` を基本形にする。
- URLが不明確な場合は深いURLを推測せず、省庁トップページや公式検索ページを使う。
- URLがPDFの場合は資料名がわかるタイトルにする。
- 外部リンクには必ず `target="_blank" rel="noopener noreferrer"` を付ける。
- 403 / 405 / 429 はbotブロック・HEAD拒否の可能性があるため、それだけで不正URL扱いしない。
- 明らかな404 / 410は使用しない。
- 通常のリスト / 通常リンクだけで出力しない。必ず以下の link-list 構造を使う。

**参考リンク（外部リンク）の標準構造：**

```html
<!-- wp:loos/link-list {"className":"is-style-default"} -->
<ul class="swell-block-linkList is-style-default">

  <!-- wp:loos/link-list-item {"url":"https://example.go.jp/page","label":"参考ページ名"} -->
  <li class="swell-block-linkList__item">
    <a class="swell-block-linkList__link" href="https://example.go.jp/page" target="_blank" rel="noopener noreferrer"><!-- icon-placeholder --><span class="swell-block-linkList__text">参考ページ名</span></a>
  </li>
  <!-- /wp:loos/link-list-item -->

</ul>
<!-- /wp:loos/link-list -->
```

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

### CTA全体構造（loos/cap-block必須）

- `wp:group {"className":"cap-block"}` は使用禁止。CTA全体は必ず `loos/cap-block` を使う。
- `cap_box_ttl` はdivとして実装する。H3にしない。
- `cap_box_content` の中に本文・箇条書き・spacer・CTAボタンをすべて含める。
- CTAボタンを `cap_box_content` の外に出さない。
- `<!-- /wp:loos/cap-block -->` はすべての内容を出力した後、最後に置く。
- CTA直前にH2「迷ったら無料相談へ」などを置かない。

**標準構造：**

```html
<!-- wp:loos/cap-block -->
<div class="swell-block-capbox cap_box">
  <div class="cap_box_ttl">
    <span><strong><span class="swl-fz u-fz-l">無料でアドバイザーに相談する</span></strong></span>
  </div>
  <div class="cap_box_content">

    <!-- wp:paragraph -->
    <p>読者の状況に合わせた本文を入れる。まだ決め切れていない段階でも相談できる、という安心感を伝える。</p>
    <!-- /wp:paragraph -->

    <!-- wp:paragraph -->
    <p>相談前に、次の情報があると話が進みやすくなります。</p>
    <!-- /wp:paragraph -->

    <!-- wp:list {"className":"wp-block-list"} -->
    <ul class="wp-block-list">
      <!-- wp:list-item -->
      <li>物件の所在地・現在の状態・空き家になった経緯</li>
      <!-- /wp:list-item -->
      <!-- wp:list-item -->
      <li>名義・相続・権利関係の状況</li>
      <!-- /wp:list-item -->
      <!-- wp:list-item -->
      <li>売却・賃貸・活用など、現時点で考えている方向性</li>
      <!-- /wp:list-item -->
    </ul>
    <!-- /wp:list -->

    <!-- wp:paragraph -->
    <p>まだ迷っている段階でも、状況を整理することで次の一歩が見つかります。</p>
    <!-- /wp:paragraph -->

    <!-- wp:spacer {"height":"16px"} -->
    <div style="height:16px" aria-hidden="true" class="wp-block-spacer"></div>
    <!-- /wp:spacer -->

    <!-- wp:loos/button {"hrefUrl":"{{WP_CTA_URL}}","color":"green","className":"is-style-btn_normal"} -->
    <div class="swell-block-button green_ is-style-btn_normal">
      <a href="{{WP_CTA_URL}}" class="swell-block-button__link" target="_blank" rel="noopener noreferrer">
        <span>無料相談 総合窓口を確認する</span>
      </a>
    </div>
    <!-- /wp:loos/button -->

  </div>
</div>
<!-- /wp:loos/cap-block -->
```

### CTA見出しの重複禁止

- CTA直前のH2と cap_box_ttl に同じ文言を使う構成は禁止。
- 例：H2「迷ったら無料相談へ」＋ cap_box_ttl「迷ったら無料相談へ」は使わない。
- CTAはH2なしで loos/cap-block を直接出力し、cap_box_ttlでタイトルを表現する。
- 目次アンカー `id="cta"` が必要な場合は、loos/cap-block の親要素に付与する。

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

**STEPブロック全体のラッパー（ボーダー付きgroup必須）：**

```html
<!-- wp:group {"className":"has-border -border02"} -->
<div class="wp-block-group has-border -border02">

  <!-- wp:loos/step -->
  <div class="swell-block-step" data-num-style="circle">
    <!-- STEPアイテムをここに入れる -->
  </div>
  <!-- /wp:loos/step -->

</div>
<!-- /wp:group -->
```

- 手順系セクションでSTEPを裸のまま（border groupなしで）出力しない。

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
- 各カードの本文量は80〜120字程度で揃える。
- 各カードの `<!-- /wp:group -->` 直前に必ず以下のspacerを入れる。
- `columns` / `column` の `verticalAlignment:"stretch"` は維持する。

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
      <p><strong>太字の要点テキスト（Point 1）</strong></p>
      <!-- /wp:paragraph -->
      <!-- wp:paragraph -->
      <p>補足本文テキスト。読者が理解しやすいよう80〜120字程度でまとめる。</p>
      <!-- /wp:paragraph -->
      <!-- wp:spacer {"height":"10px"} -->
      <div style="height:10px" aria-hidden="true" class="wp-block-spacer"></div>
      <!-- /wp:spacer -->
    </div>
    <!-- /wp:group -->
  </div>
  <!-- /wp:column -->

  <!-- wp:column {"verticalAlignment":"stretch"} -->
  <div class="wp-block-column is-vertically-aligned-stretch">
    <!-- wp:group {"className":"has-border -border02 is-style-big_icon_point"} -->
    <div class="wp-block-group has-border -border02 is-style-big_icon_point">
      <!-- wp:heading {"level":3} -->
      <h3 class="wp-block-heading">Point 2</h3>
      <!-- /wp:heading -->
      <!-- wp:paragraph -->
      <p><strong>太字の要点テキスト（Point 2）</strong></p>
      <!-- /wp:paragraph -->
      <!-- wp:paragraph -->
      <p>補足本文テキスト。読者が理解しやすいよう80〜120字程度でまとめる。</p>
      <!-- /wp:paragraph -->
      <!-- wp:spacer {"height":"10px"} -->
      <div style="height:10px" aria-hidden="true" class="wp-block-spacer"></div>
      <!-- /wp:spacer -->
    </div>
    <!-- /wp:group -->
  </div>
  <!-- /wp:column -->

  <!-- wp:column {"verticalAlignment":"stretch"} -->
  <div class="wp-block-column is-vertically-aligned-stretch">
    <!-- wp:group {"className":"has-border -border02 is-style-big_icon_point"} -->
    <div class="wp-block-group has-border -border02 is-style-big_icon_point">
      <!-- wp:heading {"level":3} -->
      <h3 class="wp-block-heading">Point 3</h3>
      <!-- /wp:heading -->
      <!-- wp:paragraph -->
      <p><strong>太字の要点テキスト（Point 3）</strong></p>
      <!-- /wp:paragraph -->
      <!-- wp:paragraph -->
      <p>補足本文テキスト。読者が理解しやすいよう80〜120字程度でまとめる。</p>
      <!-- /wp:paragraph -->
      <!-- wp:spacer {"height":"10px"} -->
      <div style="height:10px" aria-hidden="true" class="wp-block-spacer"></div>
      <!-- /wp:spacer -->
    </div>
    <!-- /wp:group -->
  </div>
  <!-- /wp:column -->

</div>
<!-- /wp:columns -->
```

