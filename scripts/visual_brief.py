"""
visual_brief.py — 記事本文から画像生成用 visual brief を抽出するモジュール。

使用方法:
    from visual_brief import load_brief_from_file, extract_visual_brief
    from visual_brief import validate_visual_brief, build_brief_cluster_prose

    body = load_brief_from_file("data/drafts/article.md")
    brief = extract_visual_brief(body, "記事タイトル")
    if validate_visual_brief(brief):
        prose = build_brief_cluster_prose(brief)
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
BRIEF_TEMPLATE = PROMPTS_DIR / "extract_visual_brief.md"


def load_brief_from_file(body_file_path: str) -> str:
    """記事本文ファイルを読み込む。失敗時は "" を返す。"""
    try:
        path = Path(body_file_path)
        if not path.is_absolute():
            path = BASE_DIR / body_file_path
        return path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[WARN] visual_brief: 本文ファイルの読み込みに失敗しました: {e}", file=sys.stderr)
        return ""


def _load_template() -> str:
    if not BRIEF_TEMPLATE.exists():
        raise FileNotFoundError(f"extract_visual_brief.md が見つかりません: {BRIEF_TEMPLATE}")
    return BRIEF_TEMPLATE.read_text(encoding="utf-8")


def _clean_json_response(text: str) -> str:
    """コードフェンスなどを除去して JSON 文字列を取り出す。"""
    text = text.strip()
    # ```json ... ``` または ``` ... ``` を除去
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def extract_visual_brief(article_body: str, article_title: str) -> dict:
    """Claude API で visual brief を抽出する。

    失敗時（API エラー / JSON パース失敗 / スキーマ不備）は {} を返し、
    画像生成全体は止めない。
    """
    if not article_body.strip():
        print("[WARN] visual_brief: 本文が空のため brief 抽出をスキップします。", file=sys.stderr)
        return {}

    try:
        template = _load_template()
    except FileNotFoundError as e:
        print(f"[WARN] visual_brief: {e}", file=sys.stderr)
        return {}

    prompt = template.replace("{{article_title}}", article_title).replace("{{article_body}}", article_body)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[WARN] visual_brief: ANTHROPIC_API_KEY が設定されていないため brief 抽出をスキップします。", file=sys.stderr)
        return {}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        print("  Visual brief を抽出中...", file=sys.stderr)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else ""
        cleaned = _clean_json_response(raw)
        brief = json.loads(cleaned)
    except ImportError:
        print("[WARN] visual_brief: anthropic パッケージが未インストールです。", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"[WARN] visual_brief: JSON パース失敗 ({e})。タイトル駆動にフォールバックします。", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"[WARN] visual_brief: brief 抽出エラー ({e})。タイトル駆動にフォールバックします。", file=sys.stderr)
        return {}

    if not validate_visual_brief(brief):
        print("[WARN] visual_brief: 抽出された brief が不完全です。タイトル駆動にフォールバックします。", file=sys.stderr)
        return {}

    return brief


def validate_visual_brief(brief: dict) -> bool:
    """narrative_clusters が 1 個以上あれば有効とみなす。"""
    if not isinstance(brief, dict):
        return False
    clusters = brief.get("narrative_clusters", [])
    return isinstance(clusters, list) and len(clusters) >= 1


# supporting_motifs から除外するキーワード（矩形・紙・看板・デジタル系）
_MOTIF_BLOCKLIST: frozenset[str] = frozenset({
    "clipboard", "document", "paper", "form", "board", "sign", "panel",
    "card", "screen", "poster", "label", "nameplate", "certificate",
    "checklist", "ui", "smartphone", "tablet", "phone", "laptop",
    "folder", "binder", "sheet", "flyer", "brochure", "contract",
})


def _filter_supporting_motifs(motifs: list) -> list[str]:
    """paper-like / board-like / text-like な語を supporting_motifs から除外する。"""
    result = []
    for m in motifs:
        m_lower = m.lower()
        if not any(blocked in m_lower for blocked in _MOTIF_BLOCKLIST):
            result.append(m)
    return result


def build_brief_cluster_prose(brief: dict) -> str:
    """narrative_clusters から assertive な prose を生成する。

    brief が空 / 無効な場合は "" を返す（OPTIONAL_MOTIF_HINTS にフォールバック）。
    """
    if not validate_visual_brief(brief):
        return ""

    clusters = brief.get("narrative_clusters", [])[:3]
    parts: list[str] = []

    connectors = ["", "Meanwhile, ", "Also, "]
    for i, cluster in enumerate(clusters):
        scene = cluster.get("scene", "").strip()
        action = cluster.get("people_action", "").strip()
        if not scene:
            continue
        sentence = scene
        if action:
            sentence += f" {action}"
        if not sentence.endswith("."):
            sentence += "."
        parts.append(f"{connectors[i]}{sentence}")

    if not parts:
        return ""

    intro = "The illustration shows these specific small story moments within one continuous watercolor scene: "
    story_text = " ".join(parts)

    # フィルタリング後の supporting_motif_candidates のみ使用
    raw_motifs = brief.get("supporting_motif_candidates", [])
    motifs = _filter_supporting_motifs(raw_motifs)[:4]
    motif_text = ""
    if motifs:
        motif_text = f" Environmental setting elements present: {', '.join(motifs)}."

    footer = (
        " These small moments are distributed as naturally grounded scene clusters — "
        "NOT separate panels, NOT comic frames, NOT icon groups, NOT freestanding white boards. "
        "All clusters flow together as one warm continuous watercolor illustration. "
        "All figures wear casual everyday civilian clothes. No uniforms, no official caps. "
        "No foreground-dominant objects, no large white rectangles, no readable marks of any kind."
    )

    return intro + story_text + motif_text + footer
