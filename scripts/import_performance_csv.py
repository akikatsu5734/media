#!/usr/bin/env python3
"""
パフォーマンスCSVインポートスクリプト

Search Console / GA4 からエクスポートしたCSVを読み込み、
data/performance_data.json を生成する。

対応CSVフォーマット:
  Search Console: 検索パフォーマンス → ページ → CSVエクスポート
  GA4: レポート → エンゲージメント → ページとスクリーン → CSVエクスポート

使用例:
  # Search Console のみ（最小構成）
  python scripts/import_performance_csv.py --sc data/csv/sc_pages.csv

  # SC + GA4 の両方
  python scripts/import_performance_csv.py --sc data/csv/sc_pages.csv --ga4 data/csv/ga4_pages.csv

  # 確認のみ（ファイルを書かない）
  python scripts/import_performance_csv.py --sc data/csv/sc_pages.csv --dry-run
"""

import argparse
import csv
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
POSTED_LOG = DATA_DIR / "posted.json"
OUTPUT_FILE = DATA_DIR / "performance_data.json"


# ---------------------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------------------

def parse_percent(value: str) -> float:
    """'4.00%' → 0.04 、'0.04' → 0.04 のどちらも受け付ける。"""
    value = value.strip()
    if value.endswith("%"):
        try:
            return float(value[:-1]) / 100
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def parse_duration_sec(value: str) -> int:
    """'3:00' → 180秒、'0:02:30' → 150秒、'180' → 180秒 に変換する。"""
    value = value.strip()
    parts = value.split(":")
    try:
        if len(parts) == 1:
            return int(float(parts[0]))
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
    except (ValueError, IndexError):
        pass
    return 0


def find_column(headers: list[str], keywords: list[str]) -> int:
    """ヘッダーリストからキーワードにマッチする列インデックスを返す。見つからない場合は -1。"""
    for i, h in enumerate(headers):
        if any(kw.lower() in h.lower() for kw in keywords):
            return i
    return -1


def detect_header_row(lines: list[str], required_keywords: list[str], min_match: int = 2) -> tuple[int, list[str]]:
    """
    required_keywords のうち min_match 個以上を含む行をヘッダーとして検出する。
    Returns: (header_line_index, column_names)
    """
    for i, line in enumerate(lines):
        line_lower = line.lower()
        matched = sum(1 for kw in required_keywords if kw in line_lower)
        if matched >= min_match:
            return i, [c.strip() for c in line.split(",")]
    return -1, []


def read_csv_lines(path: Path) -> list[str]:
    """UTF-8（BOM付き含む）でCSVを読み込み、行リストを返す。"""
    content = path.read_text(encoding="utf-8-sig")
    return content.splitlines()


# ---------------------------------------------------------------------------
# Search Console CSV パーサー
# ---------------------------------------------------------------------------

def parse_sc_csv(path: Path) -> tuple[list[dict], dict]:
    """
    Search Console のページ別CSVを読み込む。

    エクスポート手順:
      Search Console → 検索パフォーマンス → ページタブ → CSVエクスポート

    Returns:
      rows: list of {url, clicks, impressions, ctr, avg_position}
      period: {start, end}  # CSVコメント行から抽出
    """
    lines = read_csv_lines(path)
    period = {"start": "", "end": ""}
    data_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # コメント行から集計期間を抽出
            if "start-date" in stripped.lower():
                m = re.search(r"(\d{4}-\d{2}-\d{2})", stripped)
                if m:
                    period["start"] = m.group(1)
            elif "end-date" in stripped.lower():
                m = re.search(r"(\d{4}-\d{2}-\d{2})", stripped)
                if m:
                    period["end"] = m.group(1)
        elif stripped:
            data_lines.append(line)

    if not data_lines:
        print("[WARN] SC CSV: 有効な行がありません。")
        return [], period

    # ヘッダー行検出（日本語・英語の両方に対応）
    header_keywords = ["ページ", "クリック", "表示", "ctr", "clicks", "impressions", "position"]
    header_idx, headers = detect_header_row(data_lines, header_keywords)
    if header_idx < 0:
        print("[WARN] SC CSV: ヘッダー行が見つかりませんでした。")
        return [], period

    col_url = find_column(headers, ["ページ", "top pages", "page", "url"])
    col_clicks = find_column(headers, ["クリック数", "clicks"])
    col_impressions = find_column(headers, ["表示回数", "impressions"])
    col_ctr = find_column(headers, ["ctr"])
    col_position = find_column(headers, ["掲載順位", "position"])

    if col_url < 0:
        print("[WARN] SC CSV: URLカラムが特定できませんでした。")
        return [], period

    rows = []
    reader = csv.reader(io.StringIO("\n".join(data_lines[header_idx + 1:])))
    for cols in reader:
        if not cols or not cols[0].strip():
            continue
        url = cols[col_url].strip()
        if not url.startswith("http"):
            continue  # 「合計」行などをスキップ

        def safe_int(idx: int) -> int:
            if 0 <= idx < len(cols):
                return int(cols[idx].strip().replace(",", "") or "0")
            return 0

        def safe_float(idx: int) -> float:
            if 0 <= idx < len(cols):
                try:
                    return float(cols[idx].strip().replace(",", ".") or "0")
                except ValueError:
                    return 0.0
            return 0.0

        clicks = safe_int(col_clicks)
        impressions = safe_int(col_impressions)
        ctr_raw = cols[col_ctr].strip() if 0 <= col_ctr < len(cols) else ""
        ctr = parse_percent(ctr_raw) if ctr_raw else (clicks / impressions if impressions > 0 else 0.0)
        position = safe_float(col_position)

        rows.append({
            "url": url,
            "clicks": clicks,
            "impressions": impressions,
            "ctr": round(ctr, 6),
            "avg_position": round(position, 2),
        })

    return rows, period


# ---------------------------------------------------------------------------
# GA4 CSV パーサー
# ---------------------------------------------------------------------------

def parse_ga4_csv(path: Path, base_url: str = "") -> list[dict]:
    """
    GA4 のページとスクリーンCSVを読み込む。

    エクスポート手順:
      GA4 → レポート → エンゲージメント → ページとスクリーン → CSVエクスポート
      ※「ページ パスとスクリーン クラス」ディメンションを使用すること（デフォルト）

    Returns:
      list of {page_identifier, is_path, url, sessions, page_views,
               engagement_rate, bounce_rate, avg_session_duration_sec}
    """
    lines = read_csv_lines(path)
    # コメント行・空行を除外
    data_lines = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    if not data_lines:
        print("[WARN] GA4 CSV: 有効な行がありません。")
        return []

    # ヘッダー行検出
    header_keywords = ["セッション", "ページ", "sessions", "page", "エンゲージメント"]
    header_idx, headers = detect_header_row(data_lines, header_keywords)
    if header_idx < 0:
        print("[WARN] GA4 CSV: ヘッダー行が見つかりませんでした。")
        return []

    col_page = find_column(headers, ["ページ パス", "page path", "ページのタイトル", "page title", "スクリーン クラス"])
    col_sessions = find_column(headers, ["セッション", "sessions"])
    col_pageviews = find_column(headers, ["ページ ビュー", "pageview", "表示回数", "views"])
    col_engagement = find_column(headers, ["エンゲージメント率", "engagement rate"])
    col_duration = find_column(headers, ["平均エンゲージメント時間", "平均セッション", "avg. engagement", "average engagement"])

    if col_page < 0:
        print("[WARN] GA4 CSV: ページカラムが特定できませんでした。")
        return []

    # カラム名からパスかタイトルかを判定
    is_path = any(kw in headers[col_page].lower() for kw in ["パス", "path"])

    rows = []
    reader = csv.reader(io.StringIO("\n".join(data_lines[header_idx + 1:])))
    for cols in reader:
        if not cols or not cols[0].strip():
            continue
        page_val = cols[col_page].strip() if col_page < len(cols) else ""
        if not page_val or page_val.lower() in ["合計", "total", "(other)"]:
            continue

        def safe_int(idx: int) -> int:
            if 0 <= idx < len(cols):
                return int(cols[idx].strip().replace(",", "") or "0")
            return 0

        sessions = safe_int(col_sessions)
        page_views = safe_int(col_pageviews)
        engagement_rate_raw = cols[col_engagement].strip() if 0 <= col_engagement < len(cols) else "0"
        engagement_rate = parse_percent(engagement_rate_raw)
        duration_raw = cols[col_duration].strip() if 0 <= col_duration < len(cols) else "0"
        duration_sec = parse_duration_sec(duration_raw)

        # パスをフルURLに変換
        url = ""
        if is_path and base_url:
            path_val = page_val if page_val.startswith("/") else "/" + page_val
            url = base_url.rstrip("/") + path_val

        rows.append({
            "page_identifier": page_val,
            "is_path": is_path,
            "url": url,
            "sessions": sessions,
            "page_views": page_views,
            "engagement_rate": round(engagement_rate, 4),
            "bounce_rate": round(max(0.0, 1 - engagement_rate), 4),
            "avg_session_duration_sec": duration_sec,
        })

    return rows


# ---------------------------------------------------------------------------
# SC と GA4 のマージ
# ---------------------------------------------------------------------------

def extract_path(url: str) -> str:
    """'https://example.com/path/to/page/' → '/path/to/page/'"""
    try:
        return urlparse(url).path
    except Exception:
        return ""


def merge_data(sc_rows: list[dict], ga4_rows: list[dict]) -> list[dict]:
    """SC のURL一覧に GA4 データを突合してマージする。"""
    # GA4 をパス・URLでインデックス化
    ga4_by_path: dict[str, dict] = {}
    ga4_by_url: dict[str, dict] = {}
    for r in ga4_rows:
        identifier = r.get("page_identifier", "")
        if r.get("is_path"):
            path = identifier if identifier.startswith("/") else "/" + identifier
            ga4_by_path[path] = r
        if r.get("url"):
            ga4_by_url[r["url"].rstrip("/")] = r

    merged = []
    for sc in sc_rows:
        url = sc["url"]
        path = extract_path(url)

        # GA4と突合: URL完全一致 → パス一致
        ga4 = ga4_by_url.get(url.rstrip("/")) or ga4_by_path.get(path)

        merged.append({
            "url": url,
            "title": "",
            "wp_post_id": 0,
            "published_at": "",
            "search_console": {
                "impressions": sc["impressions"],
                "clicks": sc["clicks"],
                "ctr": sc["ctr"],
                "avg_position": sc["avg_position"],
                "top_queries": [],
            },
            "ga4": {
                "sessions": ga4["sessions"] if ga4 else 0,
                "page_views": ga4["page_views"] if ga4 else 0,
                "bounce_rate": ga4["bounce_rate"] if ga4 else 0.0,
                "avg_session_duration_sec": ga4["avg_session_duration_sec"] if ga4 else 0,
            },
            "_ga4_matched": ga4 is not None,
        })

    return merged


def enrich_from_posted_log(articles: list[dict], posted_log: list[dict]) -> list[dict]:
    """posted.json の情報（タイトル・post_id・公開日）を突合して補完する。"""
    posted_by_link: dict[str, dict] = {}
    for p in posted_log:
        link = p.get("link", "").rstrip("/")
        if link:
            posted_by_link[link] = p

    for a in articles:
        url_key = a["url"].rstrip("/")
        matched = posted_by_link.get(url_key)
        if matched:
            a["title"] = matched.get("title", "")
            a["wp_post_id"] = matched.get("post_id", 0)
            posted_at = matched.get("posted_at", "")
            if posted_at:
                a["published_at"] = posted_at[:10]

    return articles


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search Console / GA4 の CSV を performance_data.json に変換する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CSVのエクスポート手順:
  Search Console:
    検索パフォーマンス → 上部の「ページ」タブをクリック → 右上「エクスポート」→ CSV
  GA4:
    レポート → エンゲージメント → ページとスクリーン → 右上「共有」→ CSVのダウンロード
    ※ディメンションが「ページ パスとスクリーン クラス」になっていることを確認

使用例:
  python scripts/import_performance_csv.py --sc data/csv/sc_pages.csv
  python scripts/import_performance_csv.py --sc data/csv/sc_pages.csv --ga4 data/csv/ga4_pages.csv
  python scripts/import_performance_csv.py --sc data/csv/sc_pages.csv --dry-run
        """,
    )
    parser.add_argument("--sc", metavar="FILE", help="Search Console のページ別CSV")
    parser.add_argument("--ga4", metavar="FILE", help="GA4 のページとスクリーンCSV（省略可）")
    parser.add_argument(
        "--base-url",
        default="",
        metavar="URL",
        help="サイトのベースURL（GA4のパスをURLに変換するために使用）。省略時は .env の WP_URL を使用。",
    )
    parser.add_argument("--output", default="", metavar="FILE", help="出力先（デフォルト: data/performance_data.json）")
    parser.add_argument("--dry-run", action="store_true", help="ファイルを書かずプレビューのみ")
    args = parser.parse_args()

    if not args.sc and not args.ga4:
        parser.print_help()
        print("\n[ERROR] --sc または --ga4 のどちらかは必須です。")
        sys.exit(1)

    base_url = args.base_url or os.environ.get("WP_URL", "").rstrip("/")

    # Search Console CSV
    sc_rows: list[dict] = []
    period: dict = {"start": "", "end": ""}
    if args.sc:
        sc_path = BASE_DIR / args.sc if not Path(args.sc).is_absolute() else Path(args.sc)
        if not sc_path.exists():
            print(f"[ERROR] SC CSV が見つかりません: {sc_path}")
            sys.exit(1)
        sc_rows, period = parse_sc_csv(sc_path)
        print(f"📊 Search Console: {len(sc_rows)} ページ読み込み完了")
        if period["start"]:
            print(f"   集計期間: {period['start']} 〜 {period['end']}")

    # GA4 CSV
    ga4_rows: list[dict] = []
    if args.ga4:
        ga4_path = BASE_DIR / args.ga4 if not Path(args.ga4).is_absolute() else Path(args.ga4)
        if not ga4_path.exists():
            print(f"[ERROR] GA4 CSV が見つかりません: {ga4_path}")
            sys.exit(1)
        ga4_rows = parse_ga4_csv(ga4_path, base_url)
        print(f"📈 GA4: {len(ga4_rows)} ページ読み込み完了")

    # マージ
    if sc_rows:
        articles = merge_data(sc_rows, ga4_rows)
        if ga4_rows:
            ga4_matched = sum(1 for a in articles if a.get("_ga4_matched"))
            print(f"🔗 GA4 突合: {ga4_matched}/{len(articles)} ページが一致")
    else:
        # GA4 のみの場合
        articles = []
        for r in ga4_rows:
            articles.append({
                "url": r.get("url") or r.get("page_identifier", ""),
                "title": "",
                "wp_post_id": 0,
                "published_at": "",
                "search_console": {"impressions": 0, "clicks": 0, "ctr": 0.0, "avg_position": 0.0, "top_queries": []},
                "ga4": {
                    "sessions": r["sessions"],
                    "page_views": r["page_views"],
                    "bounce_rate": r["bounce_rate"],
                    "avg_session_duration_sec": r["avg_session_duration_sec"],
                },
            })

    # 内部フラグを除去
    for a in articles:
        a.pop("_ga4_matched", None)

    # posted.json で補完
    if POSTED_LOG.exists():
        with open(POSTED_LOG, encoding="utf-8") as f:
            posted_log = json.load(f)
        articles = enrich_from_posted_log(articles, posted_log)
        matched = sum(1 for a in articles if a.get("title"))
        print(f"📝 posted.json 突合: {matched}/{len(articles)} 件タイトル補完")

    # プレビュー
    print(f"\n📋 変換結果（先頭3件）:")
    for a in articles[:3]:
        sc = a["search_console"]
        title_str = f" [{a['title']}]" if a.get("title") else ""
        print(f"  {a['url']}{title_str}")
        print(f"    表示: {sc['impressions']:,} / クリック: {sc['clicks']:,} / CTR: {sc['ctr']*100:.1f}% / 順位: {sc['avg_position']:.1f}")

    if args.dry_run:
        print(f"\n[DRY-RUN] {len(articles)} 件が生成されます（書き込みなし）")
        return

    output_path = Path(args.output) if args.output else OUTPUT_FILE
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "fetched_at": datetime.now().isoformat(),
        "source": "csv_import",
        "period": period,
        "articles": articles,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ {len(articles)} 件を {output_path} に保存しました。")
    print(f"次のステップ: python scripts/analyze_performance.py")


if __name__ == "__main__":
    main()
