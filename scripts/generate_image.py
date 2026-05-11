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
_DIRECT_PROMPT_SUFFIX = " hand-drawn watercolor style, blank papers only with no readable text anywhere"

POST_CHECK_LIST = [
    # ── 暴走チェック（最優先・NG即廃棄） ──
    "【NG】写真風・3D・CG・物撮り・動物・食べ物になっていないか",
    "【NG】人物2名の大きなバストアップ・会話クローズアップ・ポートレートになっていないか",
    "【NG】緑や青の色付き外枠・カード枠・ベタ塗り背景が出ていないか",
    "【NG】文字・数字・記号・ロゴが混入していないか（書類内・看板・コイン面も含む）",
    # ── 人物チェック ──
    "人物が出るべきカテゴリで人物ゼロになっていないか",
    "人物が画像高の28%以下の小〜中サイズか（大きすぎないか）",
    "人物は自然な相談・確認・作業などの生活シーンの一部として配置されているか",
    # ── 構図・多要素チェック ──
    "4分割・説明図・アイコン集・スライド風になっていないか（1枚の自然な絵か）",
    "単一シーンに偏っていないか（家・人・道具・環境が異なる部分に自然に存在しているか）",
    "道具・書類・鍵が巨大化して前景を支配していないか",
    "画面中央だけに絵が固まり、左右・端が空きすぎていないか（端近くまで描画されているか）",
    "水彩のにじみで要素が自然につながっているか（直線的な区切りや枠がないか）",
    # ── スタイル・色チェック ──
    "背景色が特定エリアに集中していないか（中央ハロー・ベタ塗り外枠がないか）",
    "外周が水彩として自然に白へ溶けているか",
    "線が縮小表示でも視認できる濃さか（薄すぎず、硬い漫画線でもないか）",
    "色が淡すぎず、暖かいアンバー・緑・茶が適度に鮮やかか",
    "公開中アキカツ記事のアイキャッチに比べて、人物・家・道具・背景の密度が近いか",
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
    "hands_only": "allow_adult",  # 人物をシーン要素として自然に入れる（scene描写でサイズ・スタイルを制御）
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

# Imagen API 送信用 英語 scene contract（カテゴリ別）
# 誘発語（editorial/magazine/article/thumbnail）を使わず視覚場面のみで記述
CATEGORY_SCENE_CONTRACTS: dict[str, dict[str, str]] = {
    "庭木剪定": {
        "subject":     "neatly trimmed garden trees beside a small Japanese vacant house",
        "objects":     "pruning shears, gardening gloves, small broom, bundled cut branches, blank checklist paper, plain pencil",
        "support":     "stone garden path, low wooden fence, trimmed green hedge, scattered amber leaves, warm amber tones",
        "composition": "calm horizontal scene, house visible in background, tools and papers fill the foreground garden path, warm amber and green fills the canvas, watercolor fades into white edges",
        "avoid":       "not a portrait, no close-up face, no people as main subject, no readable writing, no signboard text, no logo, no numbers, not three-dimensional render, no dark forest, no horror abandoned house",
        "tone":        "bright, reassuring, organized, practical",
        # リッチな自然文（APIプロンプト用。ラベルなし）
        "api_scene": (
            "Illustrated scene — hand-drawn ink-outline watercolor, NOT photorealistic. "
            "A Japanese residential garden with a traditional house and freshly trimmed trees in the background. "
            "A garden consultant in work jacket and yellow safety helmet stands at small scale "
            "(about 20% of image height), showing a blank clipboard to a homeowner couple nearby. "
            "A work truck is parked beside the garden. "
            "Pruning shears and gardening gloves lie on the stone garden path. "
            "A bundle of cut branches rests near a trimmed hedge; "
            "a blank notepad and pencil sit on a garden stone. "
            "Golden-orange autumn trees fill the upper canvas; "
            "stone path and amber fallen leaves spread across the ground. "
            "The scene is balanced and readable — house, people, and tools "
            "distributed across the canvas at natural, consistent scale. "
            "Warm soft amber and fresh green fill the canvas; outermost edges dissolve to white."
        ),
    },
    "解体": {
        "subject":     "a small Japanese vacant house model as the central focus of a calm planning scene",
        "objects":     "safety helmet, work gloves, blank planning paper, plain pencil, basic work tools",
        "support":     "fresh green plant sprouts from clean earth, simple wooden boards, warm amber and earth tones",
        "composition": "horizontal watercolor scene, house and safety tools as main subjects, sprouts in foreground, warm amber fills canvas, watercolor fades into white edges",
        "avoid":       "not a portrait, no close-up face, no text, no logo, no numbers, not three-dimensional render, not a horror scene, no collapsing building, no warning sign text, no disaster imagery",
        "tone":        "calm, resolved, practical, forward-looking — demolition as a new beginning",
        "api_scene": (
            "Illustrated scene — hand-drawn ink-outline watercolor, NOT photorealistic. "
            "A traditional Japanese property site — the house stands at the center of the setting. "
            "A bright yellow safety helmet and work gloves rest on the ground nearby. "
            "A blank white planning paper and a plain pencil lie on a flat surface in the scene. "
            "Small fresh green plant sprouts emerge from warm earth, suggesting renewal and new beginnings. "
            "Simple wooden boards and basic work tools are part of the surroundings. "
            "The scene is balanced and readable — house, tools, and props "
            "distributed across the canvas at natural, consistent scale. "
            "Warm soft amber, earth brown, and soft cream fill the canvas; outermost edges dissolve to white."
        ),
    },
    "売買": {
        "subject":     "a small Japanese house model next to a house key and blank registration papers on a simple desk",
        "objects":     "small Japanese house model, old-fashioned house key, blank white papers, plain folder, simple pencil",
        "support":     "blank clipboard in background, warm amber and cream tones, simple wooden desk texture",
        "composition": "horizontal desk-view watercolor scene, house model and key prominent, papers and folder arranged around them, warm amber fills canvas, watercolor fades into white edges",
        "avoid":       "not a portrait, no close-up face, no readable text, no logo, no numbers, not three-dimensional render, no for-sale sign text, no price tags",
        "tone":        "calm, trustworthy, organized, hopeful — the registration and handover process feels clear and manageable",
        "api_scene": (
            "Illustrated scene — hand-drawn ink-outline watercolor, NOT photorealistic. "
            "A traditional Japanese house surrounded by green garden trees forms the setting. "
            "A homeowner and property advisor stand at small scale (about 20% of image height), "
            "one holding blank plain papers, the other gesturing toward the house. "
            "A small house key and a small blank notepad rest on the garden path nearby — "
            "small scene props, not isolated foreground objects. "
            "A stone garden path winds through green plants and warm soft amber fallen leaves. "
            "The scene is balanced and readable — house, people, key, and props "
            "distributed across the canvas at natural, consistent scale. "
            "Warm soft amber and golden tones fill the canvas; outermost edges dissolve to white."
        ),
    },
    "相続・生前対策": {
        "subject":     "an elderly couple and adult child sitting around a low Japanese table with a small house model",
        "objects":     "small Japanese house model, blank documents on table, teacup, simple indoor table",
        "support":     "soft indoor light, small potted plant, warm amber watercolor wash",
        "composition": "horizontal watercolor scene, small simple figures around a table, house model prominent, warm amber wash, watercolor fades into white edges, no border frame",
        "avoid":       "no close-up face, not a portrait, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "gentle, warm, organized, thoughtful",
        "api_scene": (
            "Illustrated scene — hand-drawn ink-outline watercolor, NOT photorealistic. "
            "A traditional Japanese house with garden trees forms the warm background setting. "
            "An elderly couple and an adult family member sit and stand together at small scale "
            "(about 20-25% of image height), looking at a small house model on a garden table. "
            "An adult holds a blank plain paper; a teacup and small potted plant rest on the table. "
            "Garden stones, a warm amber path, and green plants fill the surrounding scene. "
            "The scene is balanced and readable — house, family, and props "
            "distributed across the canvas at natural, consistent scale. "
            "Warm soft amber and golden tones fill the canvas; outermost edges dissolve to white."
        ),
    },
    "お金の手配": {
        "subject":     "a small Japanese house model surrounded by coins, a calculator form, and blank planning documents on a desk",
        "objects":     "small Japanese house model, plain round coin shapes, calculator form without readable numbers, blank planning paper, plain pencil, simple folder",
        "support":     "warm amber and gold watercolor tones, cream paper whites, soft desk light",
        "composition": "horizontal desk-view watercolor scene, house model and coins prominent, papers and folder arranged around them, warm amber and gold fills canvas, watercolor fades into white edges",
        "avoid":       "not a portrait, no close-up face, no text anywhere, no numbers on coins, no price tags, no logo, not three-dimensional render",
        "tone":        "calm, practical, reassuring, organized — cost planning and subsidy review feels manageable",
        "api_scene": (
            "Illustrated scene — hand-drawn ink-outline watercolor, NOT photorealistic. "
            "A traditional Japanese house in a garden forms the warm background. "
            "A homeowner and advisor sit together at small scale (about 20% of image height), "
            "reviewing blank plain papers in a brief consultation. "
            "A small house model and a few stacked coins are visible nearby in the scene. "
            "A plain folder rests naturally in the setting. "
            "Garden path, warm earth, and green plants fill the surroundings. "
            "The scene is balanced and readable — house, people, and props "
            "distributed across the canvas at natural, consistent scale. "
            "Warm soft amber and cream tones fill the canvas; outermost edges dissolve to white."
        ),
    },
    "建築リフォーム": {
        "subject":     "a small Japanese house being renovated with helmeted workers around it",
        "objects":     "small Japanese house model, safety helmet, paint roller shape, simple wooden planks, basic tools",
        "support":     "warm amber watercolor wash, construction activity around house, soft natural light",
        "composition": "horizontal watercolor scene, house at center with workers and tools around it, warm amber wash, watercolor fades into white edges, no border frame",
        "avoid":       "not a portrait, no close-up face, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "active, hopeful, practical, warm",
    },
    "片付け": {
        "subject":     "a neatly organized Japanese vacant house room with cardboard boxes and cleaning items",
        "objects":     "cardboard boxes, small broom shape, cleaning cloth, neatly stacked household items",
        "support":     "clean room interior, soft window light, warm cream watercolor wash",
        "composition": "horizontal watercolor scene, organized room interior, warm cream wash, watercolor fades into white edges, no border frame",
        "avoid":       "not a portrait, no close-up face, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "organized, calm, clean, resolved",
    },
    "買取": {
        "subject":     "a small Japanese house model next to a handshake and simple coin shapes on a desk",
        "objects":     "small Japanese house model, two people shaking hands in greeting, a few stacked coins on a surface, blank papers",
        "support":     "warm amber watercolor wash, soft desk light, simple indoor setting",
        "composition": "horizontal watercolor scene, house and handshake as main subjects, warm amber wash, watercolor fades into white edges, no border frame",
        "avoid":       "not a portrait, no close-up face, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "trustworthy, organized, calm, reassuring",
        "api_scene": (
            "Illustrated scene — hand-drawn ink-outline watercolor, NOT photorealistic. "
            "A traditional Japanese house with garden trees forms the warm background setting. "
            "A homeowner and a property advisor shake hands warmly at small scale (about 20% of image height), "
            "standing in the garden in front of the house. "
            "A small house model rests on a garden stone nearby. "
            "Blank papers and a few coins lie on a simple flat surface beside them. "
            "Garden trees, green shrubs, and a stone path fill the surroundings. "
            "The scene is balanced and readable — house, people, and props "
            "distributed across the canvas at natural, consistent scale. "
            "Warm soft amber and golden tones fill the canvas; outermost edges dissolve to white."
        ),
    },
    "賃貸": {
        "subject":     "a small Japanese house for rent with a small family group and a key nearby",
        "objects":     "small Japanese house model, blank key set, small family figures in the distance, blank plain papers",
        "support":     "warm amber watercolor wash, garden path, soft outdoor light",
        "composition": "horizontal watercolor scene, house at center, small distant figures around, warm amber wash, watercolor fades into white edges, no border frame",
        "avoid":       "no close-up face, not a portrait, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "warm, practical, trustworthy, organized",
    },
    "管理": {
        "subject":     "a small Japanese vacant house with a calendar shape and inspection tools nearby",
        "objects":     "small Japanese house model, blank calendar grid shape, blank clipboard, simple tools",
        "support":     "warm amber watercolor wash, neatly maintained surroundings, soft outdoor light",
        "composition": "horizontal watercolor scene, house and maintenance tools prominent, warm amber wash, watercolor fades into white edges, no border frame",
        "avoid":       "not a portrait, no close-up face, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "responsible, organized, calm, reliable",
    },
    "保険": {
        "subject":     "a small Japanese house sheltered under a simple open umbrella shape",
        "objects":     "small Japanese house model, simple open umbrella shape, plain round coin shapes, blank plain paper sheet",
        "support":     "warm cream watercolor wash, soft light, a few leaves or small plants",
        "composition": "horizontal watercolor scene, house under umbrella as main subject, warm cream wash, watercolor fades into white edges, no border frame",
        "avoid":       "not a portrait, no close-up face, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "safe, calm, reassuring, warm",
    },
    "民泊": {
        "subject":     "a small inviting Japanese house with open door and a small traveler figure with luggage",
        "objects":     "small Japanese house with open door, small traveler figure with suitcase, garden path to the entrance",
        "support":     "warm amber watercolor wash, garden path, soft outdoor light",
        "composition": "horizontal watercolor scene, house and welcoming scene prominent, warm amber wash, watercolor fades into white edges, no border frame",
        "avoid":       "no close-up face, not a portrait, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "welcoming, warm, organized, hopeful",
    },
    "駐車場": {
        "subject":     "a simple parking area with a small car parked on a clean paved surface",
        "objects":     "simple car shape, parking space lines on ground, simple low fence, plain round coin shapes",
        "support":     "warm amber watercolor wash, soft outdoor light, small vacant lot feel",
        "composition": "horizontal watercolor scene, parking area and car as main subjects, warm amber wash, watercolor fades into white edges, no border frame",
        "avoid":       "not a portrait, no close-up face, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "practical, organized, calm, forward-looking",
        "api_scene": (
            "Illustrated scene — hand-drawn ink-outline watercolor. "
            "A small vacant lot converted into a tidy parking area. "
            "A car is parked neatly on a clean paved surface with simple ground lane markings. "
            "A low wooden fence borders the lot; green shrubs grow along the fence line. "
            "A traditional Japanese house or building is visible in the background. "
            "A few coins rest on a flat stone ledge beside the lot — a natural prop suggesting income. "
            "Warm amber trees and soft natural light fill the surroundings. "
            "The scene is balanced and readable — house, car, fence, plants, and coins "
            "distributed across the canvas at natural, consistent scale. "
            "Warm soft amber and golden tones fill the canvas; outermost edges dissolve to white."
        ),
    },
    "解決事例": {
        "subject":     "a small restored Japanese house with a satisfied couple standing in front",
        "objects":     "small Japanese house model, simple checkmark shape, small couple figures, green plants",
        "support":     "warm amber watercolor wash, blue sky suggestion, soft outdoor light",
        "composition": "horizontal watercolor scene, restored house and satisfied couple prominent, warm amber wash, watercolor fades into white edges, no border frame",
        "avoid":       "no close-up face, not a portrait, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "resolved, warm, hopeful, reassuring",
    },
    "その他": {
        "subject":     "a small traditional Japanese vacant house on a quiet calm street",
        "objects":     "small Japanese house model, simple key shape, a few green leaves, blank clipboard",
        "support":     "warm cream watercolor wash, soft natural light, simple surroundings",
        "composition": "horizontal watercolor scene, house as main subject, warm cream wash, watercolor fades into white edges, no border frame",
        "avoid":       "not a portrait, no close-up face, no text, no logo, no numbers, not three-dimensional render",
        "tone":        "calm, warm, organized, reassuring",
    },
}

# APIプロンプト preflight チェック用（誘発語リスト）
# 否定形でも Imagen が拾う可能性があるため、原則として API プロンプトに含めない
_PROMPT_PREFLIGHT_WORDS = [
    # スタイル誘発語（否定形でも原則NG）
    "photorealistic", "photo",
    "portrait",
    "3d rendering", "cgi",
    "product photo",
    "food", "animal", "lizard", "reptile",
    # レイアウト誘発語
    "card frame", "thumbnail", "magazine", "editorial", "poster", "cover",
    # その他
    "eyecatch", "アイキャッチ", "記事", "タイトル", "日本語",
]
# text prohibition として必要なため例外的に許可する語（preflight 対象外）
_PREFLIGHT_ALLOWED_PHRASES = [
    "no readable text", "blank papers", "no numbers", "no symbols", "no logos",
    "no letters", "no kanji", "no hiragana",
    # スタイルロック用途での使用を許可（否定語付きで使われるため問題なし）
    "not photorealistic",
    "hand-drawn style, not photorealistic",
    "ink-outline watercolor, not photorealistic",
    "ink-outline watercolor.",
    # 商用イラスト表現（editorial の代替）
    "commercial illustration",
]


def _preflight_check_api_prompt(prompt: str) -> list[str]:
    """APIプロンプトに誘発語が含まれていたら警告リストを返す。
    否定形・肯定形いずれでも検出する（Imagen は否定語の対象語も拾うため）。
    _PREFLIGHT_ALLOWED_PHRASES に含まれるフレーズ内の語は例外とする。
    """
    warnings: list[str] = []
    lower = prompt.lower()

    # 許可フレーズを除外してからチェック
    clean = lower
    for allowed in _PREFLIGHT_ALLOWED_PHRASES:
        clean = clean.replace(allowed, " " * len(allowed))

    for word in _PROMPT_PREFLIGHT_WORDS:
        if word.lower() in clean:
            warnings.append(f"  ⚠  誘発語 '{word}' がAPIプロンプトに含まれています（否定形も含む）")
    return warnings


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


def _build_multi_zone_scene(
    subject: str,
    objects_req: str,
    objects_sup: str,
) -> str:
    """カテゴリ固有 api_scene がない場合のシーン description を生成する。

    機械的なゾーン指定ではなく、物語的な奥行き記述で自然な一枚絵を生成させる。
    subject     → 場面の設定・背景（家・庭・室内など）
    objects_req → 場面内の主要要素（人物・家模型・道具など）
    objects_sup → 環境的補助要素（光・草・地面・周囲の色調など）
    """
    bg = subject.strip().rstrip(".")
    obj_parts = [o.strip() for o in objects_req.split(",") if o.strip()]
    sup_parts = [o.strip() for o in objects_sup.split(",") if o.strip()]

    primary   = ", ".join(obj_parts[:3]) if obj_parts else "relevant props"
    secondary = ", ".join(obj_parts[3:]) if len(obj_parts) > 3 else ""
    env       = ", ".join(sup_parts[:2]) if sup_parts else "warm garden surroundings"

    secondary_part = (
        f" Also present in the setting: {secondary}."
        if secondary else ""
    )

    return (
        "Illustrated scene — hand-drawn ink-outline watercolor. "
        f"The setting: {bg}. "
        f"In this scene, {primary} are naturally present in the environment."
        f"{secondary_part} "
        f"The surroundings include {env}, giving the scene warm texture and depth. "
        "The scene is balanced and readable — house, people, and props "
        "distributed across the canvas at natural, consistent scale. "
        "Warm soft amber tones throughout; outermost edges dissolve to white."
    ).strip()


def build_api_prompt(title: str, metadata: dict) -> str:
    """Imagen API に送る英語 scene contract プロンプトを生成する。
    誘発語（editorial/magazine/article/thumbnail など）を一切使わず、
    視覚的な場面記述のみで構成する。
    日本語の記事タイトルは API プロンプトに含めない。
    カテゴリ別 scene contract から subject/objects/composition などを取得する。
    """
    category    = metadata.get("detected_category", "その他")
    people_mode = metadata.get("people_mode", "none")
    allow_blank = metadata.get("allow_blank_documents", False)

    # scene contract の取得（カテゴリ固有 or フォールバック）
    contract = CATEGORY_SCENE_CONTRACTS.get(category)
    if contract:
        subject     = contract["subject"]
        objects_req = contract["objects"]
        objects_sup = contract["support"]
        composition = contract["composition"]
        avoid_str   = contract["avoid"]
        tone        = contract["tone"]
    else:
        # フォールバック: 既存の英語マッピングから生成
        cat_en      = CATEGORY_EN.get(category, "vacant house")
        center_motif = metadata.get("center_motif", "")
        supporting   = metadata.get("supporting_motifs", [])
        layout       = metadata.get("layout_family", "central_storyboard")
        subject     = f"a small traditional Japanese vacant house with objects related to {cat_en}"
        objects_req = f"small Japanese house model, {center_motif}" if center_motif else "small Japanese house model, house key"
        objects_sup = ", ".join(supporting[:3]) if supporting else "warm watercolor background, soft light, simple props"
        composition = LAYOUT_EN.get(layout, "centered horizontal composition, warm amber wash, watercolor fades into white edges, no border frame")
        avoid_str   = "not a portrait, no close-up face, no text, no logo, no numbers, not three-dimensional rendering"
        tone        = "calm, warm, organized, reassuring"

    # B. 人物描写（人物はシーン要素の1つ。単一主役にしない）
    if people_mode == "none":
        people_note = "No human figures — the scene is conveyed through objects, setting, and atmosphere."
    else:
        people_note = (
            "People appear at natural small-to-medium scale (about 15-28% of image height), "
            "visible as one element among the house, garden, and other props — "
            "in a brief consultation, work, or confirmation activity. "
            "Shown in natural full-scene context, not filling the frame. "
            "People are part of the rich scene, not the primary subject."
        )

    blank_note = "Simple blank papers and clipboards appear naturally as props." if allow_blank else ""

    # api_scene がある場合はそれを使用（自然文・ラベルなし）
    if contract and "api_scene" in contract:
        scene_prose = contract["api_scene"]
    else:
        # 多ゾーン統合型テンプレートで scene_prose を構築
        scene_prose = _build_multi_zone_scene(
            subject     = subject     if subject     else "a small Japanese vacant house",
            objects_req = objects_req if objects_req else "house key, blank clipboard",
            objects_sup = objects_sup if objects_sup else "warm amber garden, natural surroundings",
        )

    lines = [
        # ──── A. Style Contract（全カテゴリ共通・固定） ────
        "Hand-painted commercial illustration: clear ink outlines on every element, "
        "filled with vivid warm watercolor. Hand-drawn style, NOT photorealistic.",
        "Every figure, building, tool, and prop has a distinct ink outline "
        "with warm watercolor fills — the style of a published Japanese commercial illustration.",
        "The full 16:9 canvas shows a balanced, readable scene: house clearly visible, "
        "people and props distributed across the canvas — all elements at natural, consistent scale.",
        "People appear at about 15-25% of image height — small enough that the house, "
        "garden, and props are equally prominent — one element among many in the scene.",
        "Props and small items appear at appropriate scale within the overall scene — "
        "visible but not dominant, placed naturally, not filling the frame.",
        "Colors are warm but soft: gentle amber, pale cream, soft golden yellow, light green — "
        "watercolor washes with a warm illustrated tone, not deeply saturated.",
        "A pale cream and soft amber watercolor wash fills the background; "
        "only the very outermost edges dissolve gently into white.",
        "The composition is balanced and readable across the full canvas — "
        "no strong near/far perspective, no oval spotlight, no empty zones.",
        "Documents and papers are blank plain sheets — physical pages on surfaces or in hands, "
        "with no writing, marks, printed content, or symbols of any kind.",
        # ──── C. Safety（Scene Contractより前に配置し優先度を上げる） ────
        "All papers, signs, surfaces, and objects in the scene carry no text — "
        "no readable letters, no numbers, no printed marks anywhere in the image.",
        "",
        # ──── B. Scene Contract（カテゴリ別） ────
        scene_prose,
        people_note,
    ]

    if blank_note:
        lines.append(blank_note)

    lines += [
        "",
        # ──── D. Output tone ────
        f"Overall impression: {tone}.",
    ]

    return "\n".join(lines)


def build_fallback_prompt(title: str, metadata: dict) -> str:
    """generated_images が空だった場合の短縮リトライプロンプト。
    英語 scene contract の短縮版。誘発語は使わない。
    """
    category    = metadata.get("detected_category", "その他")
    people_mode = metadata.get("people_mode", "none")
    allow_blank = metadata.get("allow_blank_documents", False)

    contract   = CATEGORY_SCENE_CONTRACTS.get(category)
    subject    = contract["subject"] if contract else f"a small Japanese vacant house with {CATEGORY_EN.get(category, 'vacant house')} objects"
    blank_note = "Simple blank papers appear as props." if allow_blank else ""
    scene      = contract.get("api_scene", subject) if contract else subject
    tone       = contract.get("tone", "calm, warm, organized") if contract else "calm, warm, organized"

    if people_mode == "none":
        people_note = "No human figures — scene conveyed through objects and atmosphere."
    else:
        people_note = "People at small-to-medium scale (15-28% of image height) as one element among house, garden, and props — not the primary focus."

    return "\n".join([
        "Commercial hand-painted watercolor illustration: soft ink outlines, "
        "warm soft watercolor washes. Hand-drawn, NOT photorealistic.",
        "Balanced scene: house, people (15-25% of image height), props, environment — "
        "distributed across the full 16:9 canvas at natural, consistent scale.",
        "Warm soft colors — gentle amber, pale cream, soft golden yellow. "
        "Pale cream and amber wash throughout; only the outermost edges dissolve to white.",
        f"{scene}.",
        people_note,
        blank_note,
        "All papers and surfaces remain blank — no readable text, no numbers, no symbols.",
        f"Overall impression: {tone}.",
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
        raw_title = metadata.get("article_title", "-")
        title_theme = raw_title[:25] + "…" if len(raw_title) > 25 else raw_title
        print(f"  {'記事タイトル':<{w}}: {raw_title}")
        print(f"  {'変換後テーマ':<{w}}: {title_theme}")
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
    # preflight チェック
    pf_warnings = _preflight_check_api_prompt(api_prompt)
    if pf_warnings:
        print("\n--- ⚠ Preflight チェック（誘発語検出） ---")
        for w in pf_warnings:
            print(w)
        print("---")
    else:
        print("\n  ✓ Preflight チェック: 誘発語なし")
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
<<<<<<< HEAD
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
=======
    print("画像生成中...")
    print(f"  モデル: {model_name}")
    print(f"  プロンプト（先頭120字）: {prompt[:120]}")

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_images(
            model=model_name,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                output_mime_type="image/png",
                aspect_ratio="16:9",
                person_generation="dont_allow",
            ),
        )
    except Exception as e:
        print(f"[ERROR] 画像生成APIエラー: {e}")
        print("  以下を確認してください:")
        print("  - GEMINI_API_KEY が正しいか")
        print("  - APIの課金・利用制限が有効か")
        print("  - ご利用の地域で Imagen API が利用可能か")
        print("  - モデル名が正しいか（GEMINI_IMAGE_MODEL 環境変数で上書き可能）")
        print("  - google-genai SDK が最新か: pip install -U google-genai")
        return None

    if not response.generated_images:
        print("[ERROR] 画像が生成されませんでした。")
        print("  プロンプトが安全フィルターで拒否された可能性があります。")
        print("  プロンプトを見直して再試行してください。")
>>>>>>> origin/main
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
