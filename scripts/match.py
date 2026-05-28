# -*- coding: utf-8 -*-
"""
주간 시책 자동 매칭 스크립트
============================

사용법:
    python scripts/match.py 2605_4              # OCR + 수동 매칭
    python scripts/match.py 2605_4 --no-ocr     # 파일명 hint 만 사용
    python scripts/match.py 2605_4 --dry-run    # 실제 복사 안함

기능:
    1. 주차 폴더(예: 2605_4) 내의 모든 이미지를 읽음
    2. 파일명 hint로 1차 매칭 시도
    3. 매칭 실패 시 EasyOCR로 이미지 상단 35% OCR
    4. agencies.json 의 대리점 리스트와 fuzzy 매칭
    5. 매칭 실패 시 콘솔에서 수동 선택
    6. organized/2605_4/대리점한글명_N.확장자 형태로 저장

요구사항:
    pip install easyocr pillow rapidfuzz
    (easyocr 첫 실행 시 한국어 모델 약 100MB 자동 다운로드)

이 스크립트는 프로젝트 루트(이 폴더의 부모 폴더)에서 실행해도 되고,
스크립트 위치 자동 인식으로 어디서 실행해도 됩니다.
"""

import sys
import os
import json
import shutil
import re
from pathlib import Path
from collections import defaultdict

# ------------------------------------------------------------
# 경로 설정 - 스크립트 위치 기준 자동 계산
# ------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent   # 프로젝트 루트 = 주간 시책 검색 자동화 폴더

# 원본 시책 폴더 (주차별 폴더들이 위치) - 프로젝트 루트와 동일
SOURCE_ROOT = ROOT_DIR

# 정리된 결과가 저장될 폴더 - 이 폴더만 GitHub 저장소에 푸시됨
ORGANIZED_ROOT = ROOT_DIR / "organized"

DATA_DIR = ROOT_DIR / "data"
# ----------------------------------------------------------


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
    """EasyOCR 리더 초기화. 첫 실행 시 한국어 모델 다운로드(약 100MB)."""
    import easyocr
    print("[INFO] EasyOCR 초기화 중... (첫 실행 시 한국어 모델 다운로드, 1-2분 소요)")
    reader = easyocr.Reader(['ko', 'en'], gpu=False)
    print("[INFO] OCR 준비 완료")
    return reader


def ocr_top_region(reader, image_path):
    """이미지의 상단 35% 영역만 OCR (대리점명이 상단에 위치)."""
    from PIL import Image
    import numpy as np

    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    top = img.crop((0, 0, w, int(h * 0.35)))
    arr = np.array(top)
    results = reader.readtext(arr, detail=0)
    return " ".join(results)


def normalize(text):
    """매칭용 정규화: 공백/특수문자/괄호 제거 + 소문자."""
    text = re.sub(r"[\(\)（）㈜\s\-_\.,/]", "", text)
    return text.lower()


def best_match(ocr_text, agencies, threshold=70):
    """OCR 텍스트에서 대리점명 추출. (full_name, score) 또는 (None, score)."""
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
            # 부분 문자열 포함 - 가장 신뢰도 높음
            if norm_alias in norm_ocr and len(norm_alias) >= 3:
                score = 95 + min(len(norm_alias), 5)
                if score > best[1]:
                    best = (a['full_name'], score)
                continue
            # fuzzy partial ratio
            score = fuzz.partial_ratio(norm_alias, norm_ocr)
            if len(norm_alias) < 4:
                score = max(0, score - 20)
            if score > best[1]:
                best = (a['full_name'], score)

    if best[1] >= threshold:
        return best
    return None, best[1]


def filename_hint_match(filename, hints, agencies):
    """파일명 stem으로 hint dict 매칭.
    여러 단계로 fallback:
      1. 전체 stem 그대로 (예: 'hanbo_cs')
      2. 끝의 숫자 제거 (예: 'aplus2' → 'aplus')
      3. 첫 _ 이전 부분만 (예: 'hanbo_cs' → 'hanbo')
    """
    stem = Path(filename).stem.lower()
    candidates = [stem]
    # 끝 숫자 제거
    candidates.append(re.sub(r"[_]?\d+$", "", stem))
    # _ 이전 부분
    if '_' in stem:
        candidates.append(stem.split('_')[0])

    all_full = {a['full_name'] for a in agencies}
    for key in candidates:
        if key and key in hints and hints[key] in all_full:
            return hints[key]
    return None


def canonical_short_name(full_name, agencies):
    """저장용 한글 짧은 이름 (가장 짧고 깔끔한 alias)."""
    for a in agencies:
        if a['full_name'] == full_name:
            candidates = [al for al in a['aliases']
                          if not re.search(r"[\(\)（）㈜]", al) and len(al) >= 2]
            if candidates:
                return min(candidates, key=len)
            return a['full_name'].replace('(주)', '').replace('㈜', '').strip()
    return full_name


def manual_select(filename, ocr_text, agencies, score_hint):
    """매칭 실패 시 사용자 직접 선택."""
    print(f"\n{'='*60}")
    print(f"[수동 매칭 필요] {filename}")
    if ocr_text:
        print(f"OCR 결과(상단): {ocr_text[:200]}")
    print(f"자동 매칭 최고 점수: {score_hint}")
    print(f"{'='*60}")
    print("입력 옵션:")
    print("  - 대리점명 일부 입력 (한글) → 검색")
    print("  - 's' → 스킵")
    print("  - 'q' → 중단 (지금까지 결과 저장)")

    while True:
        query = input("입력 > ").strip()
        if query.lower() == 's':
            return None
        if query.lower() == 'q':
            raise KeyboardInterrupt("사용자 중단")
        if not query:
            continue

        from rapidfuzz import fuzz
        norm_q = normalize(query)
        matches = []
        for a in agencies:
            for alias in a['aliases']:
                if normalize(alias).startswith(norm_q) or norm_q in normalize(alias):
                    matches.append(a['full_name'])
                    break
        # 중복 제거 유지순서
        seen = set()
        matches = [m for m in matches if not (m in seen or seen.add(m))]

        if not matches:
            scored = []
            for a in agencies:
                best = max((fuzz.partial_ratio(norm_q, normalize(al)) for al in a['aliases']), default=0)
                if best > 50:
                    scored.append((best, a['full_name']))
            scored.sort(reverse=True)
            matches = [name for _, name in scored[:10]]

        if not matches:
            print("  → 검색 결과 없음. 다시 입력해주세요.")
            continue

        print("\n검색 결과:")
        for i, full in enumerate(matches[:15]):
            print(f"  [{i+1}] {full}")
        print("  [0] 다시 검색")
        choice = input("번호 선택 > ").strip()
        if choice == '0' or not choice.isdigit():
            continue
        idx = int(choice) - 1
        if 0 <= idx < len(matches):
            return matches[idx]


def process_week_folder(week_id, reader=None, agencies=None, hints=None,
                        interactive=True, dry_run=False):
    """특정 주차 폴더 처리. week_id 예: '2605_4'"""
    if agencies is None:
        agencies = load_agencies()
    if hints is None:
        hints = load_filename_hints()

    src_folder = SOURCE_ROOT / week_id
    if not src_folder.exists():
        print(f"[ERROR] 폴더 없음: {src_folder}")
        return

    dst_folder = ORGANIZED_ROOT / week_id
    if not dry_run:
        dst_folder.mkdir(parents=True, exist_ok=True)

    img_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    files = sorted([f for f in src_folder.iterdir()
                    if f.is_file() and f.suffix.lower() in img_exts])

    if not files:
        print(f"[WARN] 이미지 파일 없음: {src_folder}")
        return

    print(f"[INFO] {week_id}: {len(files)}개 파일 처리 시작")

    counter = defaultdict(int)
    results = []

    for f in files:
        # 1차: 파일명 hint
        matched = filename_hint_match(f.name, hints, agencies)
        ocr_text = ""
        score = 0
        method = "hint"

        if not matched and reader is not None:
            # 2차: OCR
            try:
                ocr_text = ocr_top_region(reader, f)
                matched, score = best_match(ocr_text, agencies)
                method = "ocr"
            except Exception as e:
                print(f"[WARN] OCR 실패 {f.name}: {e}")

        if not matched and interactive:
            # 3차: 수동
            try:
                matched = manual_select(f.name, ocr_text, agencies, score)
                method = "manual"
            except KeyboardInterrupt:
                print("\n[INFO] 사용자 중단. 지금까지 처리 결과 저장.")
                break

        if not matched:
            print(f"  ✗ {f.name} → 매칭 실패")
            results.append((f.name, None, None))
            continue

        short = canonical_short_name(matched, agencies)
        counter[short] += 1
        idx = counter[short]
        new_name = f"{short}_{idx}{f.suffix.lower()}"
        dst = dst_folder / new_name

        while dst.exists():
            idx += 1
            counter[short] = idx
            new_name = f"{short}_{idx}{f.suffix.lower()}"
            dst = dst_folder / new_name

        if not dry_run:
            shutil.copy2(f, dst)
        marker = {'hint': '▸', 'ocr': '✓', 'manual': '※'}.get(method, '✓')
        print(f"  {marker} {f.name:30s} → {new_name}  [{method}]")
        results.append((f.name, new_name, matched))

    ok = sum(1 for _, n, _ in results if n)
    fail = sum(1 for _, n, _ in results if not n)
    print(f"\n[SUMMARY] {week_id}: 성공 {ok}, 실패 {fail}")
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
            print("[WARN] easyocr 미설치. 파일명 hint 만으로 진행.")
            print("       설치: pip install easyocr")

    process_week_folder(week_id, reader=reader, agencies=agencies, hints=hints,
                        interactive=not non_interactive, dry_run=dry_run)


if __name__ == "__main__":
    main()
