import streamlit as st
import json
import re
from pathlib import Path
from PIL import Image

# ── 경로 설정 (repo 기준) ──
BASE_DIR = Path(__file__).resolve().parent
MAPPING_FILE = BASE_DIR / "mapping.json"
IMG_ROOT = BASE_DIR / "prize"

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
def load_mapping_from_file():
    if MAPPING_FILE.exists():
        return json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    return {}

def get_mapping():
    """session_state에 매핑 유지 (수정사항 세션 내 보존)"""
    if "mapping" not in st.session_state:
        st.session_state.mapping = load_mapping_from_file()
        st.session_state.mapping_modified = False
    return st.session_state.mapping

def save_mapping_session(mapping):
    st.session_state.mapping = mapping
    st.session_state.mapping_modified = True

def list_weeks():
    if not IMG_ROOT.is_dir():
        return []
    return sorted([d.name for d in IMG_ROOT.iterdir() if d.is_dir()])

def scan_folder(folder_path):
    """이미지 파일 리스트 반환"""
    files = []
    p = Path(folder_path)
    if not p.is_dir():
        return files
    for f in sorted(p.iterdir()):
        if f.suffix.lower() not in IMG_EXTS:
            continue
        stem = f.stem
        files.append({
            "stem": stem,
            "base": get_base_stem(stem),
            "filename": f.name,
            "path": str(f),
        })
    return files

def group_files(files, mapping):
    groups = {}
    unmatched = []
    for f in files:
        agent, _ = find_match(f["stem"], mapping)
        if agent:
            groups.setdefault(agent, []).append(f)
        else:
            unmatched.append(f)
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
    .modified-badge {
        background: #ff9800;
        color: white;
        padding: 3px 10px;
        border-radius: 10px;
        font-size: 0.75em;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


def main():
    mapping = get_mapping()

    # ── 헤더 ──
    header_extra = ""
    if st.session_state.get("mapping_modified"):
        header_extra = ' <span class="modified-badge">수정됨 — 다운로드 필요</span>'

    st.markdown(
        '<div class="title-bar">'
        f'<h1>📊 메리츠화재 대리점 시상 조회{header_extra}</h1>'
        '<p>대리점별 주차 시상 현황</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not mapping:
        st.error("매핑 데이터(`mapping.json`)가 없습니다.")
        st.stop()

    weeks = list_weeks()
    if not weeks:
        st.error("`prize/` 폴더가 없거나 주차 폴더가 비어있습니다.")
        st.stop()

    # ══════════════════════════════════
    #  모드 선택
    # ══════════════════════════════════
    mode = st.radio(
        "모드",
        ["📊 조회", "🔧 매칭 수정"],
        horizontal=True,
        label_visibility="collapsed",
    )

    # ── 주차 선택 ──
    selected_week = st.selectbox(
        "📅 주차",
        options=weeks,
        index=len(weeks) - 1,
    )

    target = IMG_ROOT / selected_week
    files = scan_folder(target)

    if not files:
        st.warning(f"이미지 파일이 없습니다: `prize/{selected_week}/`")
        st.stop()

    groups, unmatched = group_files(files, mapping)

    # ══════════════════════════════════
    #  조회 모드
    # ══════════════════════════════════
    if mode == "📊 조회":
        agent_list = sorted(groups.keys())

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

    # ══════════════════════════════════
    #  매칭 수정 모드
    # ══════════════════════════════════
    else:
        # 매핑에 등록된 모든 대리점명 수집
        all_agents = sorted(set(mapping.values()))

        st.markdown(
            f"**`{selected_week}/`** — 이미지 {len(files)}개　"
            f"매칭 {len(files) - len(unmatched)}개　"
            f"미매칭 {len(unmatched)}개"
        )

        # ── 미매칭 먼저 ──
        if unmatched:
            st.warning(f"❓ 미매칭 {len(unmatched)}개")
            already = set(mapping.values())

            for f in unmatched:
                st.divider()
                c1, c2, c3 = st.columns([1, 3, 2])
                with c1:
                    try:
                        st.image(Image.open(f["path"]), width=150)
                    except:
                        st.text("(미리보기 불가)")
                with c2:
                    st.markdown(f"**📄 `{f['filename']}`**")
                    save_key = f["stem"]
                    if f["base"]:
                        suffix = f["stem"][len(f["base"]):]
                        st.caption(f"베이스명: **{f['base']}** · 접미사: `{suffix}`")
                        save_key = f["base"]
                    else:
                        st.caption(f"파일명: **{f['stem']}**")
                with c3:
                    sel = st.selectbox(
                        "대리점",
                        ["-- 선택 --"] + all_agents,
                        key=f"new_{f['stem']}",
                        label_visibility="collapsed",
                    )
                    if st.button("✅ 매칭", key=f"sv_{f['stem']}", type="primary"):
                        if sel != "-- 선택 --":
                            mapping[save_key] = sel
                            save_mapping_session(mapping)
                            st.rerun()
                        else:
                            st.error("대리점을 선택해주세요.")

        # ── 매칭 완료 항목 ──
        st.divider()
        st.markdown(f"**🔗 매칭 완료 ({len(files) - len(unmatched)})**")

        for f in files:
            agent, matched_key = find_match(f["stem"], mapping)
            if not agent:
                continue

            c1, c2, c3, c4 = st.columns([1, 2, 3, 1])
            with c1:
                try:
                    st.image(Image.open(f["path"]), width=100)
                except:
                    st.text("(미리보기 불가)")
            with c2:
                st.markdown(f"**{f['filename']}**")
                suffix = ""
                if matched_key != f["stem"]:
                    suffix = f["stem"][len(matched_key):]
                if suffix:
                    st.caption(f"베이스: `{matched_key}` · 접미사: `{suffix}`")
            with c3:
                current_idx = all_agents.index(agent) + 1 if agent in all_agents else 0
                new_sel = st.selectbox(
                    "대리점",
                    ["-- 선택 --"] + all_agents,
                    index=current_idx,
                    key=f"edit_{f['stem']}",
                    label_visibility="collapsed",
                )
            with c4:
                changed = new_sel != agent and new_sel != "-- 선택 --"
                if changed:
                    if st.button("💾 변경", key=f"chg_{f['stem']}", type="primary"):
                        mapping[matched_key] = new_sel
                        save_mapping_session(mapping)
                        st.rerun()
                else:
                    if st.button("🗑 해제", key=f"un_{f['stem']}"):
                        del mapping[matched_key]
                        save_mapping_session(mapping)
                        st.rerun()
            st.divider()

        # ── 수정사항 다운로드 ──
        if st.session_state.get("mapping_modified"):
            st.markdown("---")
            st.warning(
                "매핑이 수정되었습니다. 아래에서 `mapping.json`을 다운로드하고 "
                "GitHub repo에 업로드(덮어쓰기)해주세요."
            )
            st.download_button(
                "⬇️ mapping.json 다운로드",
                data=json.dumps(mapping, ensure_ascii=False, indent=2),
                file_name="mapping.json",
                mime="application/json",
                type="primary",
            )


if __name__ == "__main__":
    main()
