#!/usr/bin/env python3
"""
画像生成スクリプト（Gemini Imagen）

記事のアイキャッチ画像を Gemini の Imagen API で生成して data/images/ に保存する。

使用例:
  # テンプレートから生成（推奨）
  python scripts/generate_image.py --type general --title "世田谷区の空き家補助金2026年"
  python scripts/generate_image.py --type tokyo23 --title "世田谷区"
  python scripts/generate_image.py --type case --title "相続した実家の空き家を売却した事例" --dry-run
  python scripts/generate_image.py --type seasonal_pr --title "夏の台風前に空き家点検を済ませておく理由"

  # プロンプト直接指定（旧方式・互換）
  python scripts/generate_image.py --prompt "古い日本家屋の外観、夕暮れ時、落ち着いた雰囲気"
  python scripts/generate_image.py --prompt "空き家 補助金 世田谷" --output data/images/test.png
  python scripts/generate_image.py --prompt "..." --dry-run

必要な設定:
  .env に GEMINI_API_KEY を追加してください。
  Google AI Studio ( https://aistudio.google.com/ ) で発行できます。
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
IMAGES_DIR = BASE_DIR / "data" / "images"
PROMPTS_DIR = BASE_DIR / "prompts"
CONFIG_DIR = BASE_DIR / "config"
MOTIFS_FILE = CONFIG_DIR / "image_motifs.json"

# common_file=None の場合は specific_file が自己完結（tokyo23）
IMAGE_TYPES = {
    "general":     ("image_common.md", "image_general.md"),
    "case":        ("image_common.md", "image_case.md"),
    "tokyo23":     (None,              "image_tokyo23.md"),
    "seasonal_pr": ("image_common.md", "image_seasonal_pr.md"),
}

# --prompt 直接指定（旧方式）のみで付加する安全付記
_DIRECT_PROMPT_SUFFIX = " --style photorealistic, no people, no text overlay"

POST_CHECK_LIST = [
    "文字・数字・記号が画像内に一切ないか",
    "看板・書類・画面・ラベル・封筒に文字が混入していないか",
    "FOR SALE / OPEN / 価格 / 申請 等のテキストがないか",
    "写真風・3D・CGに寄っていないか（手描き水彩か確認）",
    "背景が白〜淡いクリーム色か",
    "主役モチーフが明確に一つ存在するか",
    "記事一覧で他記事と差別化できるか（縮小時にカテゴリが伝わるか）",
    "不安を煽る表現がないか（整理・前進の印象があるか）",
]

COMPOSITION_DESCRIPTIONS = {
    "single_scene": "1シーン切り取り：主役モチーフが中央〜左寄り、背景が奥行きのある風景",
    "center_object_cluster": "中央オブジェクト集合：主役を中央に、関連モチーフが周囲に自然に集まる",
    "foreground_background": "手前・奥遠近感：手前に主役、奥に自然・建物・空が広がる",
    "top_view_workspace": "真上俯瞰：テーブルや地面を真上から見た、小物が並ぶ作業空間",
    "diagonal_flow": "対角流れ：左下→右上の視線誘導、開放感・変化のある場面",
}

LAYOUT_FAMILY_DESCRIPTIONS = {
    "single_scene":        "1つの場面。主役モチーフ中心、補助要素少なめ、余白少なく仕上げる",
    "central_storyboard":  "中央主題＋周囲4〜8個の補助要素。ストーリーボード的な高密度構成",
    "infographic_scene":   "メイン場面＋2〜3個の補助場面。説明力のあるインフォグラフィック構成",
    "center_with_corners": "中央主題＋四隅・周辺にカテゴリ要素を配置。整然としたカード型",
    "consultation_card":   "机上・相談シーン。人物・小物・書類・費用整理の要素が整然と並ぶ",
    "process_collage":     "流れ・比較・注意点向け。複数の小場面がコラージュ的に配置",
}

DENSITY_DESCRIPTIONS = {
    "low":         "補助要素1〜2個。シンプルな構成",
    "medium":      "補助要素3〜4個。補助場面1つ追加可",
    "medium_high": "補助要素4〜6個。補助場面1〜2つ",
    "high":        "補助要素5〜8個。補助場面2〜3つ",
}

PEOPLE_MODE_DESCRIPTIONS = {
    "none":       "人物なし（無生物モチーフで表現）",
    "hands_only": "手元のみ可（書類・コイン・鍵などを操作する手を使用可）",
    "up_to_2":    "最大2名可（相談・確認シーン）",
    "up_to_4":    "最大4名可（複数名の相談・案内・作業シーン）",
}

VISUAL_STYLE_DIRECTIVES = {
    "public_card_v1": (
        "## ビジュアルスタイル設計（記事一覧カード型サムネイル）\n\n"
        "この画像を「記事一覧に並ぶ横長カード型サムネイル」として設計すること：\n"
        "- 中央主題＋周辺補助要素で画面の70〜90%を主題関連要素で埋める\n"
        "- 余白を広く取りすぎない。右側・上部に大きな白い空白を残さない\n"
        "- 縮小表示でもカテゴリ差が分かる。情報密度は中〜高\n"
        "- rounded card feel / visually rich but organized\n"
        "- 静かな単体挿絵で終わらせない\n"
        "- 読める文字・数字・ロゴは一切入れない"
    ),
}

# Imagen API送信用: 英語マッピング辞書
CATEGORY_EN = {
    "解決事例":      "vacant house problem-solving case",
    "買取":          "vacant house quick buyout",
    "庭木剪定":      "garden and tree pruning",
    "片付け":        "vacant house cleanup and removal",
    "建築リフォーム": "renovation and repair",
    "保険":          "vacant house insurance",
    "駐車場":        "parking lot conversion",
    "相続・生前対策": "inheritance and estate planning",
    "お金の手配":    "subsidy, grant, and cost arrangement",
    "民泊":          "vacation rental (minpaku)",
    "賃貸":          "vacant house rental",
    "解体":          "demolition and clearance",
    "管理":          "vacant house management",
    "売買":          "vacant house sale",
    "その他":        "vacant house related topic",
}

LAYOUT_EN = {
    "single_scene":        "single focused scene, subject centered",
    "central_storyboard":  "central theme surrounded by 4-8 supporting elements",
    "infographic_scene":   "main scene with 2-3 supporting mini-scenes",
    "center_with_corners": "central subject with related elements in corners",
    "consultation_card":   "organized desktop consultation scene with house model and props",
    "process_collage":     "process collage with multiple small scenes",
}

DENSITY_EN = {
    "low":         "minimal, 1-2 supporting elements",
    "medium":      "moderate, 3-4 supporting elements",
    "medium_high": "medium-high, 4-6 supporting elements and 1-2 mini scenes",
    "high":        "rich, 5-8 supporting elements and 2-3 mini scenes",
}

PEOPLE_EN = {
    "none":       "no people",
    "hands_only": "hands only (showing hands interacting with props)",
    "up_to_2":    "1-2 people in a consultation or advisory scene",
    "up_to_4":    "2-4 people in a consultation, work, or advisory scene",
}

PERSON_GENERATION_MAP = {
    "none":       "dont_allow",
    "hands_only": "allow_adult",
    "up_to_2":    "allow_adult",
    "up_to_4":    "allow_adult",
}

# API送信プロンプト用: 日本語自然文マッピング（変数名をそのままAPIに出さない）
LAYOUT_JA = {
    "single_scene":        "ひとつの印象的な場面を中心に描く構図。主役モチーフを大きく配置する",
    "central_storyboard":  "中央に主役モチーフを大きく配置し、周囲に複数の関連要素を自然に配置する",
    "infographic_scene":   "メインシーンを中心に、いくつかの補助的な小場面を周辺に組み込む",
    "center_with_corners": "中央の主役モチーフを軸に、四隅や周辺にカテゴリを象徴する要素を配置する",
    "consultation_card":   "相談机を囲む俯瞰構図。家の模型や関連小物を机上に整然と配置し、手元や指差しで相談の動きを表現する",
    "process_collage":     "複数の小場面をコラージュ的に配置し、流れや注意点が一目で分かる構図",
}

DENSITY_JA = {
    "low":         "要素は少なめで、主役モチーフが際立つシンプルな構成",
    "medium":      "主役モチーフを引き立てる補助要素を控えめに配置した構成",
    "medium_high": "要素はやや多め。画面全体に情報が整理されて配置されている構成",
    "high":        "要素は多め。複数の小場面を含む情報量の高い構成",
}

PEOPLE_JA = {
    "none":       "人物は登場させない。小物・空間・構成要素だけで状況を表現する",
    "hands_only": "人物の顔は大きく映さず、手元・指差し・物を持つ動作で相談や整理の動きを表現する",
    "up_to_2":    "数名の人物を、自然な相談・確認のシーンとして登場させる",
    "up_to_4":    "複数名の人物を、相談・案内・作業の場面として自然に登場させる",
}


def load_file(path: Path) -> str:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def load_motifs() -> dict:
    if not MOTIFS_FILE.exists():
        print(f"[WARN] {MOTIFS_FILE} が見つかりません。その他カテゴリを使用します。")
        return {"categories": {}}
    with open(MOTIFS_FILE, encoding="utf-8") as f:
        return json.load(f)


def detect_category(title: str, motifs: dict) -> tuple[str, list[str]]:
    """タイトルからカテゴリを判定する。

    primary_keywords のマッチで +2pt、keywords のマッチで +1pt として採点し、
    最高得点のカテゴリを返す。同点の場合は priority の小さい（上位の）カテゴリを優先する。
    """
    categories = motifs.get("categories", {})
    scores: dict[str, tuple[int, list[str]]] = {}

    for cat_name, cat_data in categories.items():
        if cat_name == "その他":
            continue  # どれにも該当しない場合の fallback
        matched: list[str] = []
        score = 0
        for kw in cat_data.get("primary_keywords", []):
            if kw in title:
                matched.append(kw)
                score += 2
        for kw in cat_data.get("keywords", []):
            if kw in title and kw not in matched:
                matched.append(kw)
                score += 1
        if score > 0:
            scores[cat_name] = (score, matched)

    if not scores:
        return "その他", []

    priority_map = {
        cat: cat_data.get("priority", 999)
        for cat, cat_data in categories.items()
    }

    best_cat, (_, matched_kws) = sorted(
        scores.items(),
        key=lambda x: (-x[1][0], priority_map.get(x[0], 999)),
    )[0]
    return best_cat, matched_kws


def hash_select(seed: str, count: int) -> int:
    """seed 文字列のハッシュで再現性のある選択インデックスを返す。"""
    if count <= 0:
        return 0
    return int(hashlib.md5(seed.encode()).hexdigest(), 16) % count


def select_composition(title: str, patterns: list[str]) -> str:
    """タイトルのハッシュで構図パターンを決定論的に選択する。"""
    if not patterns:
        return "single_scene"
    return patterns[hash_select(title, len(patterns))]


def build_category_brief(title: str, motifs: dict) -> tuple[str, dict]:
    """カテゴリ別プロンプト挿入文と dry-run 表示用メタデータを返す。"""
    category, matched_kws = detect_category(title, motifs)
    categories = motifs.get("categories", {})
    cat_data = categories.get(category, categories.get("その他", {}))

    main_motifs = cat_data.get("main_motifs", [])
    supporting = cat_data.get("supporting_motifs", [])
    avoid = cat_data.get("avoid_motifs", [])
    fallback = cat_data.get("fallback_center_motif", "やさしい光の中の静かな日本の家")
    reader_concerns = cat_data.get("reader_concerns", [])

    # レイアウト・密度・人物・blank props・ビジュアルスタイル
    layout_family = cat_data.get("layout_family", "central_storyboard")
    density = cat_data.get("density", "medium")
    people_mode = cat_data.get("people_mode", "none")
    allow_blank_docs = cat_data.get("allow_blank_documents", False)
    allow_blank_signs = cat_data.get("allow_blank_signs", False)
    allow_ui_props = cat_data.get("allow_ui_like_props", False)
    visual_style = cat_data.get("visual_style_profile", "public_card_v1")

    center_motif = (
        main_motifs[hash_select(title, len(main_motifs))]
        if main_motifs else fallback
    )
    reader_concern = (
        reader_concerns[hash_select(title + "_concern", len(reader_concerns))]
        if reader_concerns else ""
    )

    layout_desc = LAYOUT_FAMILY_DESCRIPTIONS.get(layout_family, layout_family)
    density_desc = DENSITY_DESCRIPTIONS.get(density, density)
    people_desc = PEOPLE_MODE_DESCRIPTIONS.get(people_mode, people_mode)

    brief_lines = [
        "## カテゴリ別設計指示",
        "",
        f"カテゴリ: {category}",
        f"レイアウト: {layout_family} — {layout_desc}",
        f"情報密度: {density} — {density_desc}",
        f"人物設定: {people_mode} — {people_desc}",
        "",
        f"読者の懸念: {reader_concern}",
        f"中心モチーフ: {center_motif}",
        f"サポートモチーフ: {', '.join(supporting)}",
        f"必ず避けるモチーフ: {', '.join(avoid)}",
        "",
        "blank プロップ設定:",
    ]
    if allow_blank_docs:
        brief_lines.append("- 文字なし書類・クリップボード・フォームの使用可（形のみ、文字なし）")
    if allow_blank_signs:
        brief_lines.append("- 文字なし看板の使用可（形のみ、文字なし）")
    if allow_ui_props:
        brief_lines.append("- 文字なしスマホ・タブレット画面の使用可（画面表示なし）")
    if not any([allow_blank_docs, allow_blank_signs, allow_ui_props]):
        brief_lines.append("- 書類・看板・画面プロップは使用しない")

    if visual_style in VISUAL_STYLE_DIRECTIVES:
        brief_lines.extend(["", VISUAL_STYLE_DIRECTIVES[visual_style]])

    brief = "\n".join(brief_lines)

    metadata = {
        "article_title": title,
        "detected_category": category,
        "matched_keywords": matched_kws,
        "reader_concern": reader_concern,
        "center_motif": center_motif,
        "supporting_motifs": supporting,
        "avoid_motifs": avoid,
        "layout_family": layout_family,
        "density": density,
        "people_mode": people_mode,
        "visual_style_profile": visual_style,
        "allow_blank_documents": allow_blank_docs,
        "allow_blank_signs": allow_blank_signs,
        "allow_ui_like_props": allow_ui_props,
    }

    return brief, metadata


def build_image_prompt(image_type: str, title: str) -> tuple[str, dict]:
    """プロンプト文字列とメタデータ辞書を返す。"""
    common_file, specific_file = IMAGE_TYPES[image_type]
    specific = load_file(PROMPTS_DIR / specific_file)

    if common_file:
        common = load_file(PROMPTS_DIR / common_file)
        combined = (common + "\n\n---\n\n" + specific).strip()
    else:
        combined = specific.strip()

    metadata: dict = {}

    if image_type == "tokyo23":
        combined = combined.replace("{{対象区名}}", title)
    else:
        combined = combined.replace("{{記事タイトル}}", title)

        if image_type == "general":
            motifs = load_motifs()
            brief, metadata = build_category_brief(title, motifs)
            combined = combined.replace("{{カテゴリ別設計指示}}", brief)

    remaining = re.findall(r"\{\{[^}]+\}\}", combined)
    if remaining:
        print(f"[WARN] 未置換のプレースホルダーが残っています: {remaining}")

    return combined, metadata


def build_api_prompt(title: str, metadata: dict) -> str:
    """Imagen API に送る日本語自然文プロンプトを生成する。
    変数名はAPIプロンプトに出さず、すべて情景描写として埋め込む。
    成功ChatGPTプロンプトの役割設定・推論構造・感情的ゴールを踏襲する。
    """
    category    = metadata.get("detected_category", "その他")
    center_motif = metadata.get("center_motif", "")
    supporting  = metadata.get("supporting_motifs", [])
    layout      = metadata.get("layout_family", "central_storyboard")
    density     = metadata.get("density", "medium")
    people_mode = metadata.get("people_mode", "none")
    allow_blank = metadata.get("allow_blank_documents", False)

    layout_desc  = LAYOUT_JA.get(layout, "中央に主役モチーフを配置し、周辺に関連要素を自然に配置した構図")
    density_desc = DENSITY_JA.get(density, "要素はやや多め、画面全体に情報が整理されて配置されている")
    people_desc  = PEOPLE_JA.get(people_mode, "人物は必要に応じて登場させる")
    support_str  = "・".join(supporting[:5]) if supporting else "関連する小物"

    lines = [
        "あなたは、日本の情報メディア向けの最高峰の商用イラストレーターです。",
        "日本の空き家情報メディア「アキカツ」の記事アイキャッチ画像を1枚生成してください。",
        "",
        "【記事タイトル】",
        title,
        "",
        "【カテゴリと描くシーン】",
        f"カテゴリ：{category}",
        f"このイラストの中心：「{center_motif}」",
        f"周辺に配置する要素：{support_str}",
        f"構図：{layout_desc}",
        f"情報密度：{density_desc}",
        f"人物の扱い：{people_desc}",
    ]

    if allow_blank:
        lines.append("小道具：白紙の書類やクリップボードは文字なしの形のみで使用可。")

    lines += [
        "",
        "【テイスト】",
        "水彩絵の具で薄く塗ったような少しにじみのある手描きタッチ。鉛筆・色鉛筆・ペンで描いたやわらかい輪郭線。",
        "写真風・リアル3D・CGにしない。上品で親しみやすい挿絵風。",
        "背景は白〜薄い生成りベース。淡い水色・淡い黄色・薄い緑・やさしい茶色の水彩にじみをうっすら入れる。",
        "",
        "【構図】",
        "横長のアイキャッチ構図。余白を広く取りすぎず、主題要素をしっかり配置する。",
        "記事一覧で並んだとき他記事と見分けがつきやすい1枚にする。",
        "",
        "【文字禁止ルール】",
        "画像内のどこにも文字・数字・記号・ロゴを入れない。",
        "コインは文字・記号のないシンプルな金属円盤として描く。",
        "電卓は数字ボタン・画面表示を描かず、形だけで表現する。",
        "書類・クリップボードは白紙または読めない横線のみ。看板やラベルは形だけ。",
        "",
        "【仕上がりの印象】",
        "不安を煽るより「整理できそう」「読めば前に進めそう」という前向きな印象を与える。",
        "記事タイトルを知らなくても、記事テーマがイラストで直感的に伝わる仕上がりにする。",
    ]

    return "\n".join(lines)


def build_fallback_prompt(title: str, metadata: dict) -> str:
    """generated_images が空だった場合の短縮リトライプロンプト（日本語自然文）。
    役割設定・中心シーン・テイスト・文字禁止だけを残した短縮版。
    """
    category    = metadata.get("detected_category", "その他")
    center_motif = metadata.get("center_motif", "")
    people_mode = metadata.get("people_mode", "none")
    allow_blank = metadata.get("allow_blank_documents", False)

    people_desc = PEOPLE_JA.get(people_mode, "人物は必要に応じて登場させる")
    subject     = center_motif[:80] if center_motif else "日本の家と関連する小物"
    blank_note  = "白紙の書類や形だけのクリップボードは使用可。" if allow_blank else ""

    return "\n".join([
        "あなたは日本の情報メディア向けの商用イラストレーターです。",
        f"「{title}」のアイキャッチ画像を手描き水彩スタイルで生成してください。",
        f"カテゴリ：{category}。描くシーン：{subject}。",
        people_desc,
        f"手描き水彩。薄い生成り背景。淡い水色・黄色・緑のにじみ。関連する小物を周囲に自然に配置。{blank_note}",
        "画像内に文字・数字・記号・ロゴを入れない。コインは無地の金属円盤のみ。電卓は形のみ。",
        "「整理できそう」「前に進めそう」という明るい印象にする。",
    ])


def _print_post_checklist() -> None:
    print("\n--- 生成後チェックリスト ---")
    for item in POST_CHECK_LIST:
        print(f"  □ {item}")


def _print_dry_run(
    verbose_prompt: str,
    api_prompt: str,
    fallback_prompt: str,
    output_path: Path,
    metadata: dict,
) -> None:
    print("\n=== DRY-RUN: 画像生成パラメータ確認 ===\n")
    if metadata:
        w = 20
        print(f"  {'記事タイトル':<{w}}: {metadata.get('article_title', '-')}")
        print(f"  {'検出カテゴリ':<{w}}: {metadata.get('detected_category', '-')}")
        kws = metadata.get("matched_keywords", [])
        print(f"  {'マッチキーワード':<{w}}: {', '.join(kws) if kws else '（なし）'}")
        print(f"  {'読者の懸念':<{w}}: {metadata.get('reader_concern', '-')}")
        print(f"  {'レイアウト':<{w}}: {metadata.get('layout_family', '-')}")
        print(f"  {'情報密度':<{w}}: {metadata.get('density', '-')}")
        print(f"  {'人物設定':<{w}}: {metadata.get('people_mode', '-')}")
        print(f"  {'ビジュアルスタイル':<{w}}: {metadata.get('visual_style_profile', '-')}")
        print(f"  {'blank書類':<{w}}: {'可' if metadata.get('allow_blank_documents') else '不可'}")
        print(f"  {'blank看板':<{w}}: {'可' if metadata.get('allow_blank_signs') else '不可'}")
        print(f"  {'UI系プロップ':<{w}}: {'可' if metadata.get('allow_ui_like_props') else '不可'}")
        print(f"  {'中心モチーフ':<{w}}: {metadata.get('center_motif', '-')}")
        supporting = metadata.get("supporting_motifs", [])
        print(f"  {'サポートモチーフ':<{w}}: {', '.join(supporting) if supporting else '-'}")
        avoid = metadata.get("avoid_motifs", [])
        print(f"  {'回避モチーフ':<{w}}: {', '.join(avoid[:4]) + (' …' if len(avoid) > 4 else '') if avoid else '-'}")
    print(f"  {'出力先（予定）':<20}: {output_path}")
    _print_post_checklist()
    print("\n--- API送信プロンプト（compact） ---")
    print(api_prompt)
    print("---")
    print("\n--- fallback プロンプト ---")
    print(fallback_prompt)
    print("---")
    print("\n--- 詳細プロンプト（debug） ---")
    print(verbose_prompt)
    print("---")


def generate_image(
    verbose_prompt: str,
    api_prompt: str,
    fallback_prompt: str,
    output_path: Path,
    dry_run: bool = False,
    metadata: Optional[dict] = None,
) -> Optional[Path]:
    """Gemini Imagen で画像を生成して output_path に保存する。
    実API呼び出しには compact な api_prompt を使い、空だった場合は fallback_prompt で1回リトライする。
    """
    if dry_run:
        _print_dry_run(verbose_prompt, api_prompt, fallback_prompt, output_path, metadata or {})
        return None

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY が .env に設定されていません。")
        print("  Google AI Studio ( https://aistudio.google.com/ ) で API キーを発行し、")
        print("  .env に GEMINI_API_KEY=your_key を追加してください。")
        sys.exit(1)

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[ERROR] google-genai がインストールされていません。")
        print("  pip install google-genai")
        sys.exit(1)

    model_name = os.environ.get("GEMINI_IMAGE_MODEL", "imagen-4.0-generate-001")
    people_mode = (metadata or {}).get("people_mode", "none")
    person_gen = PERSON_GENERATION_MAP.get(people_mode, "dont_allow")

    def _call_api(prompt_text: str, label: str) -> Optional[object]:
        print(f"画像生成中... ({label})")
        print(f"  モデル: {model_name}")
        print(f"  プロンプト先頭: {prompt_text[:100]}")
        try:
            client = genai.Client(api_key=api_key)
            return client.models.generate_images(
                model=model_name,
                prompt=prompt_text,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/png",
                    aspect_ratio="16:9",
                    person_generation=person_gen,
                ),
            )
        except Exception as e:
            print(f"[ERROR] 画像生成APIエラー ({label}): {e}")
            print("  以下を確認してください:")
            print("  - GEMINI_API_KEY が正しいか")
            print("  - APIの課金・利用制限が有効か")
            print("  - ご利用の地域で Imagen API が利用可能か")
            print("  - モデル名が正しいか（GEMINI_IMAGE_MODEL 環境変数で上書き可能）")
            print("  - google-genai SDK が最新か: pip install -U google-genai")
            return None

    response = _call_api(api_prompt, "main")
    if response is None:
        return None

    if not response.generated_images:
        print("[INFO] メインプロンプトで画像が返りませんでした。fallback promptで1回リトライします...")
        response = _call_api(fallback_prompt, "fallback")
        if response is None:
            return None
        if not response.generated_images:
            print("[ERROR] API呼び出しは成功しましたが、どちらのプロンプトでも画像が返りませんでした。")
            print("  プロンプトがモデル側で画像化されなかった可能性があります。")
            print("  --dry-run で api prompt / fallback prompt を確認してください。")
            return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.generated_images[0].image.image_bytes)
    print(f"画像を保存しました: {output_path}")
    _print_post_checklist()
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gemini Imagen でアイキャッチ画像を生成する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # テンプレートから生成（推奨）
  python scripts/generate_image.py --type general --title "世田谷区の空き家補助金2026年"
  python scripts/generate_image.py --type tokyo23 --title "世田谷区"
  python scripts/generate_image.py --type case --title "相続した実家の空き家を売却した事例" --dry-run

  # プロンプト直接指定（旧方式）
  python scripts/generate_image.py --prompt "古い日本家屋、夕暮れ、郊外の住宅街"
  python scripts/generate_image.py --prompt "空き家 補助金" --output data/images/hojokin.png
        """,
    )

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--type",
        dest="image_type",
        choices=list(IMAGE_TYPES.keys()),
        metavar="TYPE",
        help="画像タイプ: general / case / tokyo23 / seasonal_pr（テンプレートから生成）",
    )
    source_group.add_argument(
        "--prompt",
        help="画像生成プロンプト直接指定（旧方式・互換）",
    )

    parser.add_argument(
        "--title",
        default="",
        help="記事タイトル（--type 指定時に必要。tokyo23 の場合は区名）",
    )
    parser.add_argument(
        "--output",
        default="",
        metavar="FILE",
        help="出力先（省略時: data/images/YYYYMMDD_HHMMSS.png）",
    )
    parser.add_argument("--dry-run", action="store_true", help="API を呼ばずプロンプトのみ確認")
    args = parser.parse_args()

    metadata: dict = {}

    if args.image_type:
        if not args.title:
            parser.error("--type を使う場合は --title も指定してください。")
        verbose_prompt, metadata = build_image_prompt(args.image_type, args.title)
        if args.image_type == "general" and metadata:
            api_prompt = build_api_prompt(args.title, metadata)
            fallback_prompt = build_fallback_prompt(args.title, metadata)
        else:
            api_prompt = verbose_prompt
            fallback_prompt = verbose_prompt
    else:
        verbose_prompt = args.prompt + _DIRECT_PROMPT_SUFFIX
        api_prompt = verbose_prompt
        fallback_prompt = verbose_prompt

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = BASE_DIR / args.output
    else:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = IMAGES_DIR / f"{timestamp}.png"

    generate_image(verbose_prompt, api_prompt, fallback_prompt, output_path, dry_run=args.dry_run, metadata=metadata)


if __name__ == "__main__":
    main()
