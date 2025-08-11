# -*- coding: utf-8 -*-
"""
safe_rewrite.py
Geminiを用いた“安全リライト”ユーティリティ
- 元記事全文＋改善案＋保持必須要素を前提に段階的リライト
- 差分検証で改悪（数値/固有名詞/リンクの欠落）を防止
- 失敗時は自動で再生成（最大2リトライ）
"""

from __future__ import annotations
import re
import difflib
import time
from typing import Dict, List, Tuple, Optional
import google.generativeai as genai

# ====== 抽出ユーティリティ ======

URL_RE = re.compile(r"https?://[^\s)<>\"']+")
NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?%?")
DATE_RE = re.compile(r"(20\d{2}[/.-]\d{1,2}[/.-]\d{1,2}|20\d{2}年\d{1,2}月\d{1,2}日)")
# “固有名詞らしさ”簡易抽出：カタカナ語/アルファベット語/長めの漢字語
NE_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-_/]+|[ァ-ンヴー]{2,}|[一-龥]{2,}")

def extract_key_facts(text: str) -> Dict[str, List[str]]:
    """元記事から“保持すべき要素”候補を抽出（簡易ルールベース）"""
    urls = list(dict.fromkeys(URL_RE.findall(text)))
    nums = list(dict.fromkeys(NUM_RE.findall(text)))
    dates = list(dict.fromkeys(DATE_RE.findall(text)))
    nes = list(dict.fromkeys([m.group(0) for m in NE_RE.finditer(text)]))
    return {
        "urls": urls[:50],
        "numbers": nums[:100],
        "dates": dates[:50],
        "entities": nes[:100],
    }

def coverage_score(baseline: List[str], rewritten: str) -> float:
    """保持率スコア（0-1）。要素が多すぎると過剰判定になるので上限でクリップ。"""
    if not baseline:
        return 1.0
    kept = sum(1 for x in baseline if x and x in rewritten)
    return kept / max(5, min(len(baseline), 100))

# ====== Gemini呼び出し ======

def init_gemini(api_key: str, model: str = "gemini-1.5-flash"):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model)

def prompt_extract_must_keep(original_text: str) -> str:
    return f"""
あなたは編集監修者です。以下の元記事から『保持必須要素』を箇条書きで抽出してください。
- 事実・数値・日付・固有名詞・商品名・法的注意・免責・内部/外部リンクの要点
- セクション見出し（H2/H3）と要旨

# 出力形式（JSONで返答）
{{
  "headings": [ ...見出しと要旨... ],
  "facts": [ ...保持必須の事実... ],
  "numbers": [ ...必須数値... ],
  "dates": [ ...重要日付... ],
  "entities": [ ...固有名詞... ],
  "links": [ ...重要リンク（アンカーテキスト+URL）... ]
}}

# 元記事
{original_text[:18000]}
"""

def prompt_rewrite_with_constraints(
    keyword: str,
    original_text: str,
    ai_suggestions: str,
    must_keep_json: str,
    style_guidelines: Optional[str] = None
) -> str:
    style = style_guidelines or "・冗長回避・具体/簡潔・事実改変禁止・トーンは既存踏襲・見出しは検索意図に整合"
    return f"""
あなたはSEOライティングの専門家です。下記の条件を**すべて満たす**形で、元記事を改良してください。

# 制約
- 「保持必須要素」を**削除/改変しない**（事実・数値・日付・リンク・免責）
- 元記事の**約70%は維持**し、改善案の適用は**約30%**まで
- 新情報の創作禁止。根拠なき追記禁止
- 構造は見出し単位で最適化（H2/H3）。検索意図に直結する順序に改善
- 日本語。です/ます調。ブランドトーン維持
- 出力は**HTML**（本文のみ）。インライン改行は`<br>`可。見出しは<h2>/<h3>
- 箇条書き・表は適宜活用

# ターゲットキーワード
{keyword}

# 保持必須要素（JSON）
{must_keep_json}

# 改善案（AI提案）
{ai_suggestions}

# 元記事（全文）
{original_text[:18000]}

# スタイル指針
{style}
"""

# ====== 検証・リトライ ======

def validate_rewrite(original: str, rewritten_html: str) -> Dict[str, float]:
    """改悪防止のための簡易スコアリング"""
    base = extract_key_facts(original)
    scores = {
        "url_keep": coverage_score(base["urls"], rewritten_html),
        "num_keep": coverage_score(base["numbers"], rewritten_html),
        "date_keep": coverage_score(base["dates"], rewritten_html),
        "ent_keep": coverage_score(base["entities"], rewritten_html),
    }
    # 粗い文字数下限（過剰圧縮の検知）
    orig_len = len(re.sub(r"\s+", "", original))
    new_len = len(re.sub(r"\s+", "", rewritten_html))
    length_ratio = new_len / max(1, orig_len)
    scores["length_ratio"] = length_ratio
    return scores

def is_pass(scores: Dict[str, float],
            url_min=0.8, num_min=0.7, date_min=0.7, ent_min=0.6, len_min=0.6) -> bool:
    return (
        scores["url_keep"] >= url_min and
        scores["num_keep"] >= num_min and
        scores["date_keep"] >= date_min and
        scores["ent_keep"] >= ent_min and
        scores["length_ratio"] >= len_min
    )

def diff_preview(original: str, rewritten: str, n: int = 3) -> str:
    """人間確認用の差分（行単位）"""
    diff = difflib.unified_diff(
        original.splitlines(), rewritten.splitlines(),
        lineterm="", n=n
    )
    return "\n".join(diff)

# ====== 外部IF：1関数で安全リライト ======

def safe_rewrite(
    gemini_model,
    keyword: str,
    original_html_or_text: str,
    ai_suggestions_text: str,
    style_guidelines: Optional[str] = None,
    max_retries: int = 2,
    sleep_sec: float = 1.0,
) -> Tuple[str, Dict[str, float], str]:
    """
    1. 保持必須要素（Gemini JSON）を抽出
    2. その制約＋改善案でリライト生成
    3. 差分検証。閾値未達なら自動で再生成（最大max_retries）

    Returns:
        rewritten_html, scores, must_keep_json
    """
    # 1) 抽出
    keep_resp = gemini_model.generate_content(prompt_extract_must_keep(original_html_or_text))
    must_keep_json = keep_resp.text

    # 2) 生成 + 3) 検証&リトライ
    last_scores = {}
    for attempt in range(max_retries + 1):
        prompt = prompt_rewrite_with_constraints(
            keyword, original_html_or_text, ai_suggestions_text, must_keep_json, style_guidelines
        )
        resp = gemini_model.generate_content(prompt)
        rewritten = resp.text or ""
        last_scores = validate_rewrite(original_html_or_text, rewritten)

        if is_pass(last_scores):
            return rewritten, last_scores, must_keep_json

        # 失敗時は不足点をフィードバックして再生成
        weak = [k for k, v in last_scores.items() if k != "length_ratio" and v < 0.8]
        feedback = f"""
以下の保持率が不足しています: {", ".join(weak)}。元記事の該当要素を**必ず維持**して再生成してください。
- URL/参照リンクは本文に残す（アンカーも可）
- 数値/日付は原文通り。単位・表記も維持
- 固有名詞は必ず残す（表記ゆれ禁止）
- 全体の長さは原文の{int(100*max(0.6, last_scores.get('length_ratio', 0)))}%以上
"""
        retry_prompt = prompt + "\n\n# フィードバック（必ず反映）\n" + feedback
        time.sleep(sleep_sec)
        resp = gemini_model.generate_content(retry_prompt)
        rewritten = resp.text or ""
        last_scores = validate_rewrite(original_html_or_text, rewritten)
        if is_pass(last_scores):
            return rewritten, last_scores, must_keep_json

    # 最終失敗時も結果は返す（スコアで判断できるように）
    return rewritten, last_scores, must_keep_json

# ====== 例：WP下書きに送る（任意） ======

import requests

def push_to_wordpress_draft(
    wp_base: str, user: str, app_password: str,
    title: str, html: str, status: str = "draft"
) -> str:
    """WP REST APIで下書き作成。成功時は投稿URLを返す"""
    url = wp_base.rstrip("/") + "/wp-json/wp/v2/posts"
    r = requests.post(
        url,
        auth=(user, app_password),
        json={"title": title, "content": html, "status": status},
        timeout=30
    )
    r.raise_for_status()
    data = r.json()
    return data.get("link") or f"{wp_base.rstrip('/')}/?p={data.get('id')}"
