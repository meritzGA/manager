import streamlit as st
import json
import re
from pathlib import Path
from PIL import Image

# ── 경로 설정 (repo 기준) ──
BASE_DIR = Path(__file__).resolve().parent
MAPPING_FILE = BASE_DIR / "mapping.json"
IMG_ROOT = BASE_DIR / "시상"

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

# ── 베이스명 추출 ──
SEP_SUFFIX = re.compile(r"[_\-]\d+$")
BARE_SUFFIX = re.compile(r"\d+$")

def get_base_stem(stem):
    m = SEP_SUFFIX.search(stem)
    if m and stem[:m.start()]:
        return stem[:m.start()]
    m = BARE_SUFFIX.search(stem)
    if m and m.start() >= 2:
        return stem[:m.start()]
    return None

def find_match(stem, mapping):
    if stem in mapping:
        return mapping[stem], stem
    base = get_base_stem(stem)
    if base and base in mapping:
        return mapping[base], base
    return None, None

# ── 데이터 ──
@st.cache_data
def load_mapping():
    if MAPPING_FILE.exists():
        return json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    return {}

def list_weeks():
    if not IMG_ROOT.is_dir():
        return []
    return sorted([d.name for d in IMG_ROOT.iterdir() if d.is_dir()])

def scan_and_group(folder_path, mapping):
    groups = {}
    unmatched = []
    p = Path(folder_path)
    if not p.is_dir():
        return groups, unmatched
    for f in sorted(p.iterdir()):
        if f.suffix.lower() not in IMG_EXTS:
            continue
        stem = f.stem
        agent, _ = find_match(stem, mapping)
        info = {"stem": stem, "filename": f.name, "path": str(f)}
        if agent:
            groups.setdefault(agent, []).append(info)
        else:
            unmatched.append(info)
    return groups, unmatched


# ══════════════════════════════════
st.set_page_config(
    page_title="대리점 시상 조회",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .title-bar {
        background: linear-gradient(135deg, #1e3a5f, #2c5f8a);
        color: white;
        padding: 20px 30px;
        border-radius: 12px;
        margin-bottom: 20px;
        text-align: center;
    }
    .title-bar h1 { margin: 0; font-size: 1.8em; }
    .title-bar p { margin: 4px 0 0; opacity: 0.8; font-size: 0.95em; }
    .week-badge {
        background: #ff4b4b;
        color: white;
        padding: 6px 24px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 1.3em;
        display: inline-block;
    }
    .agent-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .agent-name {
        font-size: 1.05em;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 8px;
        padding-bottom: 8px;
        border-bottom: 2px solid #2c5f8a;
    }
</style>
""", unsafe_allow_html=True)


def main():
    # ── 헤더 ──
    st.markdown(
        '<div class="title-bar">'
        '<h1>📊 메리츠화재 대리점 시상 조회</h1>'
        '<p>대리점별 주차 시상 현황</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    mapping = load_mapping()
    if not mapping:
        st.error("매핑 데이터(`mapping.json`)가 없습니다.")
        st.stop()

    weeks = list_weeks()
    if not weeks:
        st.error("`시상/` 폴더가 없거나 주차 폴더가 비어있습니다.")
        st.stop()

    # ── 주차 선택 ──
    selected_week = st.selectbox(
        "📅 주차",
        options=weeks,
        index=len(weeks) - 1,
    )

    # ── 스캔 ──
    target = IMG_ROOT / selected_week
    groups, unmatched = scan_and_group(target, mapping)

    if not groups and not unmatched:
        st.warning(f"이미지 파일이 없습니다: `시상/{selected_week}/`")
        st.stop()

    agent_list = sorted(groups.keys())

    # ── 대리점 선택 ──
    selected_agent = st.selectbox(
        "🏢 대리점 선택",
        options=agent_list,
        index=None,
        placeholder="대리점을 선택하세요...",
    )

    st.markdown(
        f'<div style="text-align:center; margin: 8px 0 16px;">'
        f'<span class="week-badge">{selected_week}</span></div>',
        unsafe_allow_html=True,
    )

    if not selected_agent:
        st.info(f"총 {len(agent_list)}개 대리점이 있습니다. 위에서 선택해주세요.")
        st.stop()

    # ══════════════════════════════════
    #  선택된 대리점 시상 표시
    # ══════════════════════════════════
    images = groups[selected_agent]

    st.markdown(
        f'<div class="agent-card">'
        f'<div class="agent-name">🏢 {selected_agent}'
        f'<span style="float:right; color:#888; font-weight:normal; font-size:0.85em;">'
        f'{len(images)}장</span></div></div>',
        unsafe_allow_html=True,
    )

    for img in images:
        try:
            st.image(Image.open(img["path"]), use_container_width=True)
        except:
            st.error(f"이미지 로드 실패: {img['filename']}")
        if len(images) > 1:
            st.caption(img["filename"])


if __name__ == "__main__":
    main()
