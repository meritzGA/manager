# -*- coding: utf-8 -*-
"""
주간 시책 조회 Streamlit 앱
==========================

월 / 주차 / 대리점을 선택하면 해당 시책 이미지를 보여주는 앱.
GitHub 저장소의 organized/ 폴더 구조를 그대로 읽음.

폴더 구조:
    organized/
        2604_1/   ← 26년 4월 1주차
            굿리치_1.jpg
            굿리치_2.jpg
            에이플러스에셋_1.png
            ...
        2605_3/
            ...

실행:
    streamlit run streamlit_app/app.py
"""

import streamlit as st
from pathlib import Path
import re
from collections import defaultdict

# ----------------------------------------------------------
# 경로 - GitHub 저장소 루트 기준
# ----------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
ORGANIZED_DIR = ROOT_DIR / "organized"

# ----------------------------------------------------------
# 페이지 설정
# ----------------------------------------------------------
st.set_page_config(
    page_title="주간 시책 조회",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ----------------------------------------------------------
# 데이터 로드
# ----------------------------------------------------------
WEEK_PATTERN = re.compile(r"^(\d{2})(\d{2})_(\d+)$")
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


@st.cache_data(show_spinner=False)
def scan_organized():
    """
    organized/ 폴더 스캔.
    반환 구조:
      { '2026-04': { '1주차': { '대리점명': [Path, Path, ...], ... }, ... }, ... }
    """
    catalog = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    if not ORGANIZED_DIR.exists():
        return {}

    for week_dir in sorted(ORGANIZED_DIR.iterdir()):
        if not week_dir.is_dir():
            continue
        m = WEEK_PATTERN.match(week_dir.name)
        if not m:
            continue
        yy, mm, ww = m.group(1), m.group(2), m.group(3)
        year_month_key = f"20{yy}-{mm}"
        week_key = f"{int(ww)}주차"

        for f in sorted(week_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in IMG_EXTS:
                continue
            # 파일명에서 대리점명 추출: 대리점명_N.확장자
            stem = f.stem
            mname = re.match(r"^(.+?)(?:_(\d+))?$", stem)
            agency_name = mname.group(1) if mname else stem
            catalog[year_month_key][week_key][agency_name].append(f)

    # defaultdict → dict 변환
    return {ym: {w: dict(ags) for w, ags in wks.items()} for ym, wks in catalog.items()}


def reload_catalog():
    scan_organized.clear()


# ----------------------------------------------------------
# UI
# ----------------------------------------------------------
st.title("📋 주간 시책 조회")
st.caption("월 → 주차 → 대리점을 선택하면 시책 이미지를 볼 수 있어요.")

catalog = scan_organized()

if not catalog:
    st.warning(
        "정리된 시책 데이터가 없습니다.\n\n"
        "프로젝트 폴더에서 다음 명령을 실행하세요:\n"
        "```\npython scripts/match.py <주차ID>\n```"
    )
    if st.button("🔄 새로고침"):
        reload_catalog()
        st.rerun()
    st.stop()


# 사이드바: 월/주차/대리점 선택
with st.sidebar:
    st.header("필터")

    # 월 선택
    months = sorted(catalog.keys(), reverse=True)
    selected_month = st.selectbox("월", months, format_func=lambda x: f"{x[:4]}년 {int(x[5:])}월")

    # 주차 선택
    weeks = sorted(catalog[selected_month].keys(), key=lambda w: int(w.replace("주차", "")))
    selected_week = st.selectbox("주차", weeks)

    # 대리점 선택
    agencies = sorted(catalog[selected_month][selected_week].keys())
    agency_count = len(agencies)
    st.caption(f"📊 {agency_count}개 대리점")

    selected_agency = st.selectbox(
        "대리점",
        ["(전체 보기)"] + agencies,
    )

    st.divider()
    if st.button("🔄 새로고침"):
        reload_catalog()
        st.rerun()

    st.caption("같은 대리점에 여러 시책(지사별/TM/대면 등)이 있으면 모두 표시됩니다.")


# 메인 영역
year = selected_month[:4]
month_num = int(selected_month[5:])
week_num = int(selected_week.replace("주차", ""))

st.subheader(f"{year}년 {month_num}월 {week_num}주차 시책")

if selected_agency == "(전체 보기)":
    # 전체 대리점 목록 표시
    st.write(f"**전체 {agency_count}개 대리점**")
    cols_per_row = 4
    rows = [agencies[i:i + cols_per_row] for i in range(0, len(agencies), cols_per_row)]
    for row in rows:
        cols = st.columns(cols_per_row)
        for col, agency in zip(cols, row):
            files = catalog[selected_month][selected_week][agency]
            with col:
                st.markdown(f"**{agency}**")
                # 첫 이미지를 썸네일로
                st.image(str(files[0]), width="stretch")
                if len(files) > 1:
                    st.caption(f"+{len(files) - 1}장 더")
else:
    files = catalog[selected_month][selected_week][selected_agency]
    st.write(f"**{selected_agency}**  ·  {len(files)}장")

    if len(files) == 1:
        st.image(str(files[0]), width="stretch")
    else:
        # 여러 장 - 2열 그리드
        cols_per_row = 2
        rows = [files[i:i + cols_per_row] for i in range(0, len(files), cols_per_row)]
        for row in rows:
            cols = st.columns(cols_per_row)
            for col, fpath in zip(cols, row):
                with col:
                    st.image(str(fpath), caption=fpath.name, width="stretch")

# 푸터
st.divider()
st.caption(
    "원본 시책 이미지가 정리된 상태로 표시됩니다. "
    "새 시책을 추가하려면 `scripts/match.py` 실행 후 GitHub에 푸시하세요."
)
