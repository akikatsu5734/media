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
    patterns = cat_data.get("composition_patterns", ["single_scene"])
    fallback = cat_data.get("fallback_center_motif", "やさしい光の中の静かな日本の家")
    reader_concerns = cat_data.get("reader_concerns", [])

    center_motif = (
        main_motifs[hash_select(title, len(main_motifs))]
        if main_motifs else fallback
    )
    composition = select_composition(title, patterns)
    comp_desc = COMPOSITION_DESCRIPTIONS.get(composition, composition)
    reader_concern = (
        reader_concerns[hash_select(title + "_concern", len(reader_concerns))]
        if reader_concerns else ""
    )

    brief_lines = [
        "## カテゴリ別設計指示",
        "",
        f"カテゴリ: {category}",
        f"読者の懸念: {reader_concern}",
        f"中心モチーフ: {center_motif}",
        f"サポートモチーフ: {', '.join(supporting)}",
        f"構図パターン: {comp_desc}",
        f"必ず避けるモチーフ: {', '.join(avoid)}",
    ]
    brief = "\n".join(brief_lines)

    metadata = {
        "article_title": title,
        "detected_category": category,
        "matched_keywords": matched_kws,
        "reader_concern": reader_concern,
        "center_motif": center_motif,
        "supporting_motifs": supporting,
        "avoid_motifs": avoid,
        "composition_pattern": composition,
        "composition_description": comp_desc,
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


def _print_post_checklist() -> None:
    print("\n--- 生成後チェックリスト ---")
    for item in POST_CHECK_LIST:
        print(f"  □ {item}")


def _print_dry_run(prompt: str, output_path: Path, metadata: dict) -> None:
    print("\n=== DRY-RUN: 画像生成パラメータ確認 ===\n")
    if metadata:
        w = 18
        print(f"  {'記事タイトル':<{w}}: {metadata.get('article_title', '-')}")
        print(f"  {'検出カテゴリ':<{w}}: {metadata.get('detected_category', '-')}")
        kws = metadata.get("matched_keywords", [])
        print(f"  {'マッチキーワード':<{w}}: {', '.join(kws) if kws else '（なし）'}")
        print(f"  {'読者の懸念':<{w}}: {metadata.get('reader_concern', '-')}")
        print(f"  {'中心モチーフ':<{w}}: {metadata.get('center_motif', '-')}")
        supporting = metadata.get("supporting_motifs", [])
        print(f"  {'サポートモチーフ':<{w}}: {', '.join(supporting) if supporting else '-'}")
        avoid = metadata.get("avoid_motifs", [])
        print(f"  {'回避モチーフ':<{w}}: {', '.join(avoid[:4]) + (' …' if len(avoid) > 4 else '') if avoid else '-'}")
        comp = metadata.get("composition_pattern", "-")
        comp_desc = metadata.get("composition_description", "")
        print(f"  {'構図パターン':<{w}}: {comp} — {comp_desc}")
    print(f"  {'出力先（予定）':<18}: {output_path}")
    _print_post_checklist()
    print("\n--- 送信プロンプト全文 ---")
    print(prompt)
    print("---")


def generate_image(
    prompt: str,
    output_path: Path,
    dry_run: bool = False,
    metadata: Optional[dict] = None,
) -> Optional[Path]:
    """Gemini Imagen で画像を生成して output_path に保存する。"""
    if dry_run:
        _print_dry_run(prompt, output_path, metadata or {})
        return None

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY が .env に設定されていません。")
        print("  Google AI Studio ( https://aistudio.google.com/ ) で API キーを発行し、")
        print("  .env に GEMINI_API_KEY=your_key を追加してください。")
        sys.exit(1)

    try:
        import google.generativeai as genai
    except ImportError:
        print("[ERROR] google-generativeai がインストールされていません。")
        print("  pip install google-generativeai")
        sys.exit(1)

    print("画像生成中...")
    print(f"  プロンプト（先頭120字）: {prompt[:120]}")

    genai.configure(api_key=api_key)
    model = genai.ImageGenerationModel("imagen-3.0-generate-002")

    result = model.generate_images(
        prompt=prompt,
        number_of_images=1,
        aspect_ratio="16:9",
        safety_filter_level="block_some",
        person_generation="dont_allow",
    )

    if not result.images:
        print("[ERROR] 画像が生成されませんでした。")
        print("  プロンプトが安全フィルターで拒否された可能性があります。")
        print("  プロンプトを見直して再試行してください。")
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.images[0].save(str(output_path))
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
        prompt, metadata = build_image_prompt(args.image_type, args.title)
    else:
        prompt = args.prompt + _DIRECT_PROMPT_SUFFIX

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = BASE_DIR / args.output
    else:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = IMAGES_DIR / f"{timestamp}.png"

    generate_image(prompt, output_path, dry_run=args.dry_run, metadata=metadata)


if __name__ == "__main__":
    main()
