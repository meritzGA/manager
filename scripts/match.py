# -*- coding: utf-8 -*-
"""
주간 시책 자동 매칭 스크립트.

Usage:
    python scripts/match.py 2605_4              # OCR + 수동
    python scripts/match.py 2605_4 --no-ocr     # 파일명만
    python scripts/match.py 2605_4 --dry-run    # 미리보기
    python scripts/match.py 2605_4 --no-interactive  # 자동만

Matching order (top to bottom):
    1. English filename hint
    2. Korean filename fuzzy match against agency aliases
    3. EasyOCR on top 35% of image + fuzzy match
    4. Interactive manual selection
"""
import sys
import os
import json
import shutil
import re
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
SOURCE_ROOT = ROOT_DIR
ORGANIZED_ROOT = ROOT_DIR / "organized"
DATA_DIR = ROOT_DIR / "data"


def load_agencies():
    with open(DATA_DIR / "agencies.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_filename_hints():
    p = DATA_DIR / "filename_hints.json"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def init_ocr():
    import easyocr
    print("[INFO] EasyOCR initializing (first run downloads Korean model, ~100MB)...")
    reader = easyocr.Reader(['ko', 'en'], gpu=False)
    print("[INFO] OCR ready")
    return reader


def ocr_top_region(reader, image_path):
    from PIL import Image
    import numpy as np
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    top = img.crop((0, 0, w, int(h * 0.35)))
    arr = np.array(top)
    results = reader.readtext(arr, detail=0)
    return " ".join(results)


def normalize(text):
    text = re.sub(r"[\(\)\s\-_\.,/]", "", text)
    text = text.replace("(주)", "").replace("주식회사", "")
    return text.lower()


def best_match(ocr_text, agencies, threshold=70):
    from rapidfuzz import fuzz
    norm_ocr = normalize(ocr_text)
    if not norm_ocr:
        return None, 0
    best = (None, 0)
    for a in agencies:
        for alias in a['aliases']:
            norm_alias = normalize(alias)
            if not norm_alias or len(norm_alias) < 2:
                continue
            if norm_alias in norm_ocr and len(norm_alias) >= 3:
                score = 95 + min(len(norm_alias), 5)
                if score > best[1]:
                    best = (a['full_name'], score)
                continue
            score = fuzz.partial_ratio(norm_alias, norm_ocr)
            if len(norm_alias) < 4:
                score = max(0, score - 20)
            if score > best[1]:
                best = (a['full_name'], score)
    if best[1] >= threshold:
        return best
    return None, best[1]


def filename_hint_match(filename, hints, agencies):
    stem = Path(filename).stem.lower()
    candidates = [stem]
    candidates.append(re.sub(r"[_]?\d+$", "", stem))
    if '_' in stem:
        candidates.append(stem.split('_')[0])
    all_full = {a['full_name'] for a in agencies}
    for key in candidates:
        if key and key in hints and hints[key] in all_full:
            return hints[key]
    return None


def filename_korean_match(filename, agencies, threshold=80):
    from rapidfuzz import fuzz
    stem = Path(filename).stem
    base = re.sub(r"[_\-]?\d+$", "", stem).strip()
    if not base:
        return None, 0
    norm_base = normalize(base)
    if len(norm_base) < 2:
        return None, 0
    best = (None, 0)
    for a in agencies:
        for alias in a['aliases']:
            norm_alias = normalize(alias)
            if not norm_alias or len(norm_alias) < 2:
                continue
            if norm_alias == norm_base:
                return a['full_name'], 100
            # alias가 base에 포함 (예: alias='메가' base='메가기본시상')
            # 추가 조건: 별칭과 다른 부분이 '기본시상', '추가시상', 'TM', '대면' 같은 부가어인지
            # 짧은 alias도 허용하되 가산점 차등
            if norm_alias in norm_base and len(norm_alias) >= 2:
                ratio_len = len(norm_alias) / len(norm_base)
                # 부가어가 흔히 나오는 경우 가산점
                rest = norm_base.replace(norm_alias, "", 1)
                bonus_terms = ["기본시상", "추가시상", "추가", "기본", "tm", "대면",
                               "지사", "본사", "직판", "정규", "cs", "direct", "new"]
                rest_is_bonus = any(t in rest for t in bonus_terms)
                if rest_is_bonus or len(norm_alias) >= 3:
                    score = 80 + int(15 * ratio_len)
                    if rest_is_bonus and len(norm_alias) >= 2:
                        score = max(score, 88)  # 부가어 매칭은 안정적
                    if score > best[1]:
                        best = (a['full_name'], score)
                    continue
            if norm_base in norm_alias and len(norm_base) >= 3:
                ratio_len = len(norm_base) / len(norm_alias)
                score = 80 + int(10 * ratio_len)
                if score > best[1]:
                    best = (a['full_name'], score)
                continue
            score = fuzz.ratio(norm_alias, norm_base)
            if len(norm_alias) < 3 or len(norm_base) < 3:
                score = max(0, score - 30)
            if score > best[1]:
                best = (a['full_name'], score)
    if best[1] >= threshold:
        return best
    return None, best[1]


def canonical_short_name(full_name, agencies):
    for a in agencies:
        if a['full_name'] == full_name:
            candidates = [al for al in a['aliases']
                          if not re.search(r"[\(\)]", al) and "주식회사" not in al and len(al) >= 2]
            if candidates:
                return min(candidates, key=len)
            return a['full_name'].replace('(주)', '').replace('주식회사', '').strip()
    return full_name


def manual_select(filename, ocr_text, agencies, score_hint):
    print("\n" + "=" * 60)
    print("[Manual match needed] " + filename)
    if ocr_text:
        print("OCR result (top): " + ocr_text[:200])
    print("Auto-match best score: " + str(score_hint))
    print("=" * 60)
    print("Input options:")
    print("  - Type part of agency name (Korean)")
    print("  - 's' to skip")
    print("  - 'q' to quit")
    while True:
        query = input("> ").strip()
        if query.lower() == 's':
            return None
        if query.lower() == 'q':
            raise KeyboardInterrupt("user quit")
        if not query:
            continue
        from rapidfuzz import fuzz
        norm_q = normalize(query)
        matches = []
        seen = set()
        for a in agencies:
            for alias in a['aliases']:
                if normalize(alias).startswith(norm_q) or norm_q in normalize(alias):
                    if a['full_name'] not in seen:
                        matches.append(a['full_name'])
                        seen.add(a['full_name'])
                    break
        if not matches:
            scored = []
            for a in agencies:
                bsc = max((fuzz.partial_ratio(norm_q, normalize(al)) for al in a['aliases']), default=0)
                if bsc > 50:
                    scored.append((bsc, a['full_name']))
            scored.sort(reverse=True)
            matches = [name for _, name in scored[:10]]
        if not matches:
            print("  No matches. Try again.")
            continue
        print("\nSearch results:")
        for i, full in enumerate(matches[:15]):
            print("  [" + str(i + 1) + "] " + full)
        print("  [0] new search")
        choice = input("Pick number > ").strip()
        if choice == '0' or not choice.isdigit():
            continue
        idx = int(choice) - 1
        if 0 <= idx < len(matches):
            return matches[idx]


def process_week_folder(week_id, reader=None, agencies=None, hints=None,
                        interactive=True, dry_run=False):
    if agencies is None:
        agencies = load_agencies()
    if hints is None:
        hints = load_filename_hints()
    src_folder = SOURCE_ROOT / week_id
    if not src_folder.exists():
        print("[ERROR] folder not found: " + str(src_folder))
        return
    dst_folder = ORGANIZED_ROOT / week_id
    if not dry_run:
        dst_folder.mkdir(parents=True, exist_ok=True)
    img_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    files = sorted([f for f in src_folder.iterdir()
                    if f.is_file() and f.suffix.lower() in img_exts])
    if not files:
        print("[WARN] no images in: " + str(src_folder))
        return
    print("[INFO] " + week_id + ": " + str(len(files)) + " files")
    counter = defaultdict(int)
    results = []
    for f in files:
        matched = filename_hint_match(f.name, hints, agencies)
        ocr_text = ""
        score = 0
        method = "E"
        if not matched:
            matched, score = filename_korean_match(f.name, agencies)
            if matched:
                method = "K"
        if not matched and reader is not None:
            try:
                ocr_text = ocr_top_region(reader, f)
                matched, score = best_match(ocr_text, agencies)
                method = "O"
            except Exception as e:
                print("[WARN] OCR failed " + f.name + ": " + str(e))
        if not matched and interactive:
            try:
                matched = manual_select(f.name, ocr_text, agencies, score)
                method = "M"
            except KeyboardInterrupt:
                print("\n[INFO] User stopped. Saving results so far.")
                break
        if not matched:
            print("  X " + f.name + " - no match")
            results.append((f.name, None, None))
            continue
        short = canonical_short_name(matched, agencies)
        counter[short] += 1
        idx = counter[short]
        new_name = short + "_" + str(idx) + f.suffix.lower()
        dst = dst_folder / new_name
        while dst.exists():
            idx += 1
            counter[short] = idx
            new_name = short + "_" + str(idx) + f.suffix.lower()
            dst = dst_folder / new_name
        if not dry_run:
            shutil.copy2(f, dst)
        print("  [" + method + "] " + f.name.ljust(30) + " -> " + new_name + "  (" + matched + ")")
        results.append((f.name, new_name, matched))
    ok = sum(1 for _, n, _ in results if n)
    fail = sum(1 for _, n, _ in results if not n)
    print("\n[SUMMARY] " + week_id + ": ok=" + str(ok) + ", fail=" + str(fail))
    return results


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    week_id = sys.argv[1]
    no_ocr = '--no-ocr' in sys.argv
    dry_run = '--dry-run' in sys.argv
    non_interactive = '--no-interactive' in sys.argv
    agencies = load_agencies()
    hints = load_filename_hints()
    reader = None
    if not no_ocr:
        try:
            reader = init_ocr()
        except ImportError:
            print("[WARN] easyocr not installed. Using filename only.")
            print("       Install: pip install easyocr")
    process_week_folder(week_id, reader=reader, agencies=agencies, hints=hints,
                        interactive=not non_interactive, dry_run=dry_run)


if __name__ == "__main__":
    main()
