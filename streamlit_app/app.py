# -*- coding: utf-8 -*-
"""
주간 시책 조회 Streamlit 앱.
월/주차/대리점을 선택하면 organized/ 폴더의 시책 이미지를 보여줍니다.
모바일 친화: 사이드바 대신 상단에 필터 배치.
"""

import streamlit as st
from pathlib import Path
import re
import json
from collections import defaultdict

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
ORGANIZED_DIR = ROOT_DIR / "organized"
DATA_DIR = ROOT_DIR / "data"

st.set_page_config(
    page_title="주간 시책 조회",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS: 사이드바 + 토글 + 헤더 메뉴까지 모두 숨김, 모바일 패딩 조정
st.markdown("""
<style>
/* 사이드바 본체 제거 */
section[data-testid="stSidebar"],
div[data-testid="stSidebar"],
aside[data-testid="stSidebar"] { display: none !important; width: 0 !important; }

/* 사이드바 열기/닫기 토글 (Streamlit 버전별 셀렉터 모두 커버) */
button[data-testid="stSidebarCollapseButton"],
button[data-testid="collapsedControl"],
div[data-testid="collapsedControl"],
[data-testid="stSidebarNavCollapseButton"],
[data-testid="stSidebarHeader"],
button[kind="header"] { display: none !important; }

/* 상단 우측 햄버거 메뉴 + 배포 버튼 */
#MainMenu, header [data-testid="stHeader"], header [data-testid="stToolbar"] { display: none !important; }

/* 메인 컨테이너 패딩 */
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; padding-left: 1rem; padding-right: 1rem; }
@media (max-width: 640px) {
  .block-container { padding-left: 0.6rem; padding-right: 0.6rem; }
}

/* 사이드바가 차지하던 왼쪽 공백 제거 */
.main .block-container { max-width: 100% !important; margin-left: 0 !important; }
</style>
""", unsafe_allow_html=True)

WEEK_PATTERN = re.compile(r"^(\d{2})(\d{2})_(\d+)$")
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


@st.cache_data(show_spinner=False)
def load_agency_map():
    """짧은 별칭 -> full_name 매핑 + full_name 정렬 리스트 반환."""
    p = DATA_DIR / "agencies.json"
    if not p.exists():
        return {}, []
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    alias_to_full = {}
    full_names = []
    for a in data:
        full = a.get("full_name", "")
        full_names.append(full)
        for al in a.get("aliases", []):
            alias_to_full.setdefault(al, full)
            alias_to_full.setdefault(al.lower(), full)
    return alias_to_full, sorted(full_names)


@st.cache_data(show_spinner=False)
def scan_organized():
    """organized/ 폴더 스캔. 파일명에서 추출한 short name 기준으로 그룹화."""
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
        ym_key = "20" + yy + "-" + mm
        wk_key = str(int(ww)) + "주차"
        for f in sorted(week_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in IMG_EXTS:
                continue
            stem = f.stem
            mname = re.match(r"^(.+?)(?:_(\d+))?$", stem)
            short_name = mname.group(1) if mname else stem
            catalog[ym_key][wk_key][short_name].append(f)
    return {ym: {w: dict(ags) for w, ags in wks.items()} for ym, wks in catalog.items()}


def short_to_full(short, alias_map):
    """파일명 기반 short name을 가능한 한 full_name으로 변환."""
    if not short:
        return short
    if short in alias_map:
        return alias_map[short]
    if short.lower() in alias_map:
        return alias_map[short.lower()]
    return short


def display_name(full_name):
    """법인 표기를 제거한 표시용 이름.
    (주), ㈜, 주식회사 를 앞/뒤에서 제거하고 공백 정리.
    예: (주)글로벌금융판매 -> 글로벌금융판매
        굿리치주식회사 -> 굿리치
        주식회사 메타리치 -> 메타리치
        메가(주) -> 메가
    """
    s = full_name or ""
    for token in ["(주)", "㈜", "(유)", "(재)"]:
        s = s.replace(token, "")
    # "주식회사" 앞뒤 모두 제거 (공백 포함)
    s = re.sub(r"^\s*주식회사\s*", "", s)
    s = re.sub(r"\s*주식회사\s*$", "", s)
    s = re.sub(r"\s*유한회사\s*$", "", s)
    return s.strip()


def reload_catalog():
    scan_organized.clear()
    load_agency_map.clear()


# ===== UI =====
st.title("📋 주간 시책 조회")

catalog = scan_organized()
alias_map, _ = load_agency_map()

if not catalog:
    st.warning("정리된 시책 데이터가 없습니다. scripts/match.py 를 먼저 실행하세요.")
    if st.button("🔄 새로고침"):
        reload_catalog()
        st.rerun()
    st.stop()

# 상단 필터: 4컬럼 (월, 주차, 대리점, 새로고침)
months = sorted(catalog.keys(), reverse=True)

col_m, col_w, col_a, col_r = st.columns([1.2, 1.2, 3, 0.8])

with col_m:
    selected_month = st.selectbox(
        "월",
        months,
        format_func=lambda x: x[:4] + "년 " + str(int(x[5:])) + "월",
        key="month_sel",
    )

# 최신 주차가 맨 위로 오도록 내림차순 (예: 5주차, 4주차, 3주차...)
weeks = sorted(
    catalog[selected_month].keys(),
    key=lambda w: int(w.replace("주차", "")),
    reverse=True,
)
with col_w:
    selected_week = st.selectbox("주차", weeks, key="week_sel")

# 현재 주차에 존재하는 대리점들. 표시는 display_name, 내부 키는 full_name
short_names = sorted(catalog[selected_month][selected_week].keys())
full_to_short = {}  # full_name -> short_name (파일 접근용)
for s in short_names:
    full = short_to_full(s, alias_map)
    if full not in full_to_short:
        full_to_short[full] = s
# 표시명 기준 가나다순 정렬
agencies_sorted = sorted(full_to_short.keys(), key=lambda f: display_name(f))
# 표시명 -> full_name 매핑 (드롭다운 선택값을 full로 복원)
display_to_full = {display_name(f): f for f in agencies_sorted}

with col_a:
    options = ["(전체 보기)"] + [display_name(f) for f in agencies_sorted]
    selected_display = st.selectbox(
        "대리점 (" + str(len(agencies_sorted)) + "개)",
        options,
        key="agency_sel",
    )
selected_full = display_to_full.get(selected_display, selected_display)

with col_r:
    st.write("")  # 라벨 자리 맞춤
    if st.button("🔄", help="새로고침"):
        reload_catalog()
        st.rerun()

st.divider()

# 메인 영역
year_num = selected_month[:4]
month_num = int(selected_month[5:])
week_num = int(selected_week.replace("주차", ""))

if selected_display == "(전체 보기)":
    st.subheader(year_num + "년 " + str(month_num) + "월 " + str(week_num) + "주차 — 전체 " + str(len(agencies_sorted)) + "개 대리점")
    cols_per_row = 3
    rows = [agencies_sorted[i:i + cols_per_row] for i in range(0, len(agencies_sorted), cols_per_row)]
    for row in rows:
        cols = st.columns(cols_per_row)
        for col, full in zip(cols, row):
            short = full_to_short[full]
            files = catalog[selected_month][selected_week][short]
            with col:
                st.markdown("**" + display_name(full) + "**")
                st.image(str(files[0]), width="stretch")
                if len(files) > 1:
                    st.caption("+" + str(len(files) - 1) + "장 더")
else:
    short = full_to_short[selected_full]
    files = catalog[selected_month][selected_week][short]
    st.subheader(display_name(selected_full))
    st.caption(year_num + "년 " + str(month_num) + "월 " + str(week_num) + "주차 · " + str(len(files)) + "장")

    if len(files) == 1:
        st.image(str(files[0]), width="stretch")
    else:
        cols_per_row = 2
        rows = [files[i:i + cols_per_row] for i in range(0, len(files), cols_per_row)]
        for row in rows:
            cols = st.columns(cols_per_row)
            for col, fpath in zip(cols, row):
                with col:
                    st.image(str(fpath), width="stretch")

st.divider()
st.caption("같은 대리점에 여러 시책(지사별/TM/대면 등)이 있으면 모두 표시됩니다.")
