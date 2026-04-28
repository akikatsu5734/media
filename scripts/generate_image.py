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
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
IMAGES_DIR = BASE_DIR / "data" / "images"
PROMPTS_DIR = BASE_DIR / "prompts"

# common_file=None の場合は specific_file が自己完結（tokyo23）
IMAGE_TYPES = {
    "general":     ("image_common.md", "image_general.md"),
    "case":        ("image_common.md", "image_case.md"),
    "tokyo23":     (None,              "image_tokyo23.md"),
    "seasonal_pr": ("image_common.md", "image_seasonal_pr.md"),
}

# --prompt 直接指定（旧方式）のみで付加する安全付記
_DIRECT_PROMPT_SUFFIX = " --style photorealistic, no people, no text overlay"


def load_file(path: Path) -> str:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def build_image_prompt(image_type: str, title: str) -> str:
    common_file, specific_file = IMAGE_TYPES[image_type]
    specific = load_file(PROMPTS_DIR / specific_file)

    if common_file:
        common = load_file(PROMPTS_DIR / common_file)
        combined = (common + "\n\n---\n\n" + specific).strip()
    else:
        combined = specific.strip()

    if image_type == "tokyo23":
        combined = combined.replace("{{対象区名}}", title)
    else:
        combined = combined.replace("{{記事タイトル}}", title)

    return combined


def generate_image(prompt: str, output_path: Path, dry_run: bool = False) -> Optional[Path]:
    """Gemini Imagen で画像を生成して output_path に保存する。"""
    if dry_run:
        print("[DRY-RUN] 画像生成をスキップします。")
        print(f"  出力先（予定）: {output_path}")
        print("\n--- 送信プロンプト全文 ---")
        print(prompt)
        print("---")
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

    print("🎨 Gemini Imagen で画像生成中...")
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
    print(f"✅ 画像を保存しました: {output_path}")
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

    # プロンプト決定
    if args.image_type:
        if not args.title:
            parser.error("--type を使う場合は --title も指定してください。")
        prompt = build_image_prompt(args.image_type, args.title)
    else:
        prompt = args.prompt + _DIRECT_PROMPT_SUFFIX

    # 出力先決定
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = BASE_DIR / args.output
    else:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = IMAGES_DIR / f"{timestamp}.png"

    generate_image(prompt, output_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
