"""
GA 시상 현황 — 대리점별 시책 파일 관리
- 관리자: 대리점 선택 → 월/주차 선택 → 시상 파일(이미지) 등록
- 조회(데스크탑): 대리점 검색 → 월 선택 → 주차 선택 → 시상 파일 열람
- 조회(모바일):   채팅형 인터페이스 → 월/주차 선택 → 섬네일 → 확대

[리팩토링] 이미지를 JSON이 아닌 디스크 파일로 저장하여 성능 개선
"""

import streamlit as st
import json, os, copy, base64, shutil, hashlib, re
from pathlib import Path
from agents import AGENT_LIST

# ── 설정 ─────────────────────────────────────────────────────
ADMIN_PASSWORD = "meritz0505"
DATA_FILE = "awards_data.json"
IMAGES_DIR = "awards_images"          # 이미지 파일 저장 폴더
MONTHS = [f"{m}월" for m in range(1, 13)]
WEEKS = ["1주차", "2주차", "3주차", "4주차", "5주차"]

st.set_page_config(
    page_title="GA 시상 현황",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════
# 이미지 파일 I/O 헬퍼
# ══════════════════════════════════════════════════════════════
def _safe_dirname(name: str) -> str:
    """파일시스템에 안전한 디렉토리명으로 변환"""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def _img_dir(agent: str, period_key: str) -> Path:
    """대리점+기간별 이미지 디렉토리 경로"""
    return Path(IMAGES_DIR) / _safe_dirname(agent) / _safe_dirname(period_key)

def save_image_file(agent: str, period_key: str, filename: str, img_bytes: bytes) -> str:
    """이미지를 디스크에 저장하고 상대 경로를 반환"""
    d = _img_dir(agent, period_key)
    d.mkdir(parents=True, exist_ok=True)
    # 동일 이름 충돌 방지: 해시 prefix 추가
    h = hashlib.md5(img_bytes).hexdigest()[:8]
    safe_name = _safe_dirname(filename)
    dest = d / f"{h}_{safe_name}"
    dest.write_bytes(img_bytes)
    return str(dest)

def load_image_b64(path: str) -> str | None:
    """디스크에서 이미지를 읽어 base64 문자열로 반환"""
    try:
        return base64.standard_b64encode(Path(path).read_bytes()).decode("utf-8")
    except Exception:
        return None

def load_image_bytes(path: str) -> bytes | None:
    """디스크에서 이미지를 읽어 bytes로 반환"""
    try:
        return Path(path).read_bytes()
    except Exception:
        return None

def delete_image_file(path: str):
    """디스크에서 이미지 파일 삭제"""
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass

def delete_agent_images(agent: str):
    """대리점 전체 이미지 폴더 삭제"""
    d = Path(IMAGES_DIR) / _safe_dirname(agent)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)

def get_media_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    return {"png": "image/png", "jpg": "image/jpeg",
            "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")

# ══════════════════════════════════════════════════════════════
# 데이터 I/O  (JSON에는 경로만 저장)
# ══════════════════════════════════════════════════════════════
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def migrate_if_needed(data: dict) -> dict:
    """기존 base64 인라인 데이터 → 파일 기반으로 마이그레이션"""
    changed = False
    for agent, agent_data in data.items():
        if not isinstance(agent_data, dict) or "periods" not in agent_data:
            continue
        for pk, pd in agent_data["periods"].items():
            for img in pd.get("images", []):
                if "data" in img and "path" not in img:
                    # base64 → 파일로 저장
                    img_bytes = base64.standard_b64decode(img["data"])
                    fname = img.get("name", "image.png")
                    path = save_image_file(agent, pk, fname, img_bytes)
                    img["path"] = path
                    img["media_type"] = img.get("media_type", get_media_type(fname))
                    del img["data"]
                    changed = True
    if changed:
        save_data(data)
    return data

# ── 헬퍼: period_key에서 월/주차 파싱 ─────────────────────────
def parse_period(period_key: str):
    parts = period_key.split(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (period_key, "")

def get_months_from_periods(period_keys: list) -> list:
    months, seen = [], set()
    for pk in sorted(period_keys, reverse=True):
        m, _ = parse_period(pk)
        if m not in seen:
            seen.add(m)
            months.append(m)
    return months

def get_weeks_for_month(period_keys: list, month: str) -> list:
    weeks = []
    for pk in sorted(period_keys, reverse=True):
        m, w = parse_period(pk)
        if m == month:
            weeks.append(w)
    return weeks

# ── 세션 초기화 ───────────────────────────────────────────────
for k, v in {
    "all_data": None, "page": "viewer", "admin_auth": False,
    "m_search": "", "m_agent": None, "m_month": None, "m_week": None, "m_expanded": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.all_data is None:
    raw = load_data()
    st.session_state.all_data = migrate_if_needed(raw)

# ── 모바일 감지 ───────────────────────────────────────────────
def _is_mobile() -> bool:
    try:
        ua = st.context.headers.get("User-Agent", "")
        return any(x in ua.lower() for x in ["mobile", "android", "iphone"])
    except Exception:
        return False

IS_MOBILE = _is_mobile()

# ══════════════════════════════════════════════════════════════
# CSS  (변경 없음)
# ══════════════════════════════════════════════════════════════
BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"],.stApp{font-family:'Pretendard',-apple-system,sans-serif!important}
.stApp{background:#f5f5f7!important}

section[data-testid="stSidebar"]{background:#1a0000!important}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div{color:#f0e0e0!important}
section[data-testid="stSidebar"] .stButton>button{
  background:rgba(255,255,255,.08)!important;color:#f0e0e0!important;
  border:1px solid rgba(255,255,255,.18)!important;border-radius:10px!important;font-weight:600!important}
section[data-testid="stSidebar"] .stButton>button:hover{background:rgba(128,0,0,.55)!important}
section[data-testid="stSidebar"] [data-testid="stButton-primary"]>button{
  background:#800000!important;border-color:#a00000!important;color:#fff!important}

.top-bar{
  background:linear-gradient(135deg,#800000 0%,#5a0000 55%,#380000 100%);
  border-radius:16px;padding:1.4rem 2rem;color:#fff;margin-bottom:1.2rem;
  box-shadow:0 6px 24px rgba(128,0,0,.22);position:relative;overflow:hidden}
.top-bar::before{content:'';position:absolute;top:-50%;right:-3%;
  width:260px;height:260px;background:rgba(255,255,255,.04);border-radius:50%}
.top-title{font-size:1.4rem;font-weight:800;letter-spacing:-.02em;margin:0}
.top-sub{font-size:.82rem;opacity:.6;margin-top:.2rem}
.sec-label{font-size:.75rem;font-weight:700;color:#800000;
  letter-spacing:.08em;text-transform:uppercase;margin:1.2rem 0 .6rem}
.period-tag{display:inline-block;background:#800000;color:#fff;
  border-radius:20px;padding:.25rem .8rem;font-size:.78rem;font-weight:700;margin:.2rem .3rem .2rem 0}
.viewer-agent-name{font-size:1.3rem;font-weight:800;color:#800000;
  margin:.5rem 0 .2rem;padding-bottom:.5rem;border-bottom:2px solid #800000}
.viewer-img-wrap{width:100%;margin-bottom:.8rem;display:flex;justify-content:center}
.viewer-img-wrap img{max-height:88vh;max-width:100%;width:auto;height:auto;
  object-fit:contain;display:block;border-radius:10px;
  box-shadow:0 2px 12px rgba(0,0,0,.08)}
.stButton>button{border-radius:9px!important;font-weight:700!important}
div[data-baseweb="select"]>div{border-radius:10px!important;font-weight:600!important}
</style>
"""

MOBILE_CSS = """
<style>
.m-header{background:linear-gradient(135deg,#800000,#5a0000);
  border-radius:14px;padding:1rem 1.2rem;color:#fff;margin-bottom:1rem;text-align:center}
.m-header-title{font-size:1.1rem;font-weight:800}
.m-header-sub{font-size:.72rem;opacity:.6;margin-top:.15rem}

.m-bubble-user{background:#800000;color:#fff;border-radius:16px 16px 4px 16px;
  padding:.7rem 1rem;margin:.4rem 0;display:inline-block;max-width:80%;
  font-weight:600;font-size:.92rem;float:right;clear:both}
.m-bubble-bot{background:#fff;color:#222;border-radius:16px 16px 16px 4px;
  padding:.7rem 1rem;margin:.4rem 0;display:inline-block;max-width:90%;
  font-size:.88rem;box-shadow:0 1px 4px rgba(0,0,0,.08);float:left;clear:both}
.m-clearfix{clear:both}

.m-agent-btn{display:block;background:#fff;border:1.5px solid #800000;color:#800000;
  border-radius:12px;padding:.6rem 1rem;margin:.3rem 0;font-weight:700;
  font-size:.9rem;cursor:pointer;transition:all .15s;text-align:left;width:100%}
.m-agent-btn:hover,.m-agent-btn:active{background:#800000;color:#fff}

.m-period-btn{display:inline-block;background:#f5f0f0;border:1.5px solid #dcc;
  color:#800000;border-radius:20px;padding:.35rem .9rem;margin:.2rem .2rem;
  font-weight:700;font-size:.8rem;cursor:pointer;transition:all .15s}
.m-period-btn:hover,.m-period-btn:active{background:#800000;color:#fff;border-color:#800000}

.m-thumb-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.5rem;margin:.5rem 0}
.m-thumb{border-radius:10px;overflow:hidden;cursor:pointer;
  box-shadow:0 1px 6px rgba(0,0,0,.1);transition:transform .15s;aspect-ratio:4/3}
.m-thumb:active{transform:scale(.96)}
.m-thumb img{width:100%;height:100%;object-fit:cover;display:block}

.m-full-img{width:100%;margin:.5rem 0;display:flex;justify-content:center}
.m-full-img img{max-height:82vh;max-width:100%;width:auto;height:auto;
  object-fit:contain;border-radius:10px;box-shadow:0 2px 16px rgba(0,0,0,.12)}
</style>
"""

# ══════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:1.2rem 0 .6rem'>
        <span style='font-size:2.2rem'>🏆</span><br>
        <b style='font-size:1rem;color:#ffcccc;letter-spacing:.03em'>GA 시상 현황</b>
    </div>""", unsafe_allow_html=True)
    st.markdown("---")
    if st.button("🔍  시상 조회", use_container_width=True,
                 type="primary" if st.session_state.page == "viewer" else "secondary"):
        st.session_state.page = "viewer"
        st.session_state.m_search = ""
        st.session_state.m_agent = None
        st.session_state.m_month = None
        st.session_state.m_week = None
        st.session_state.m_expanded = False
        st.rerun()
    if st.button("⚙️  관리자", use_container_width=True,
                 type="primary" if st.session_state.page == "admin" else "secondary"):
        st.session_state.page = "admin"
        st.rerun()
    st.markdown("---")
    st.caption("Meritz Fire Insurance")


# ══════════════════════════════════════════════════════════════
# 조회 — 데스크탑
# ══════════════════════════════════════════════════════════════
def page_viewer_desktop():
    st.markdown(BASE_CSS, unsafe_allow_html=True)
    st.markdown("""
    <div class="top-bar">
        <div class="top-title">🔍 대리점 시상 조회</div>
        <div class="top-sub">대리점명을 검색하면 등록된 시상 파일을 확인할 수 있습니다</div>
    </div>""", unsafe_allow_html=True)

    all_data = st.session_state.all_data
    registered = [k for k, v in all_data.items() if isinstance(v, dict) and v.get("periods")]

    search = st.text_input("대리점명 검색", placeholder="대리점명을 입력하세요",
                           key="search_input", label_visibility="collapsed")

    if not search.strip():
        st.markdown("""<div style='text-align:center;padding:4rem;color:#bbb'>
            <div style='font-size:3rem'>🔍</div>
            <div style='margin-top:.6rem;font-weight:500;font-size:1rem'>
                대리점명을 입력하여 검색하세요</div>
        </div>""", unsafe_allow_html=True)
        return

    matched = [name for name in registered if search.strip() in name]
    if not matched:
        st.markdown(f"""<div style='text-align:center;padding:3rem;color:#bbb'>
            <div style='font-size:2.5rem'>📋</div>
            <div style='margin-top:.5rem'>'{search}'에 대한 검색 결과가 없습니다</div>
        </div>""", unsafe_allow_html=True)
        return

    selected = matched[0] if len(matched) == 1 else st.selectbox(
        f"{len(matched)}개 대리점 검색됨", matched, key="viewer_select", label_visibility="collapsed")

    agent_data = all_data.get(selected, {})
    periods = agent_data.get("periods", {})
    period_keys = sorted(periods.keys(), reverse=True)

    st.markdown(f'<div class="viewer-agent-name">📋 {selected}</div>', unsafe_allow_html=True)

    if not period_keys:
        st.info("등록된 시상 파일이 없습니다.")
        return

    available_months = get_months_from_periods(period_keys)

    c_month, c_week = st.columns(2)
    with c_month:
        sel_month = st.selectbox("월 선택", available_months, key="viewer_month")
    with c_week:
        available_weeks = get_weeks_for_month(period_keys, sel_month)
        sel_week = st.selectbox("주차 선택", available_weeks, key="viewer_week")

    selected_period = f"{sel_month} {sel_week}"
    p_images = periods.get(selected_period, {}).get("images", [])

    st.markdown(f'<span class="period-tag" style="font-size:.95rem">{selected_period}</span>'
                f'<span style="font-size:.82rem;color:#888;margin-left:.5rem">'
                f'{len(p_images)}장</span>', unsafe_allow_html=True)

    if not p_images:
        st.info(f"{selected_period}에 등록된 시상 파일이 없습니다.")
        return

    for img_info in p_images:
        try:
            b64 = load_image_b64(img_info["path"])
            if not b64:
                st.warning(f"이미지 파일을 찾을 수 없습니다: {img_info.get('name', '')}")
                continue
            mt = img_info.get("media_type", "image/png")
            st.markdown(f'<div class="viewer-img-wrap"><img src="data:{mt};base64,{b64}"></div>',
                        unsafe_allow_html=True)
            if img_info.get("name"):
                st.caption(img_info["name"])
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# 조회 — 모바일 (채팅형)
# ══════════════════════════════════════════════════════════════
def page_viewer_mobile():
    st.markdown(BASE_CSS, unsafe_allow_html=True)
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)

    all_data = st.session_state.all_data
    registered = [k for k, v in all_data.items() if isinstance(v, dict) and v.get("periods")]

    st.markdown("""
    <div class="m-header">
        <div class="m-header-title">🏆 GA 시상 조회</div>
        <div class="m-header-sub">대리점명을 입력해 주세요</div>
    </div>""", unsafe_allow_html=True)

    search_val = st.text_input(
        "대리점 검색", placeholder="대리점명을 입력하세요 (예: 한국)",
        key="m_search_input", label_visibility="collapsed",
    )
    if search_val.strip() and search_val.strip() != st.session_state.m_search:
        st.session_state.m_search = search_val.strip()
        st.session_state.m_agent = None
        st.session_state.m_month = None
        st.session_state.m_week = None
        st.session_state.m_expanded = False
        st.rerun()

    # STEP 1: 검색어 → 대리점 매칭
    if st.session_state.m_search:
        st.markdown(f'<div class="m-bubble-user">{st.session_state.m_search}</div>'
                    f'<div class="m-clearfix"></div>', unsafe_allow_html=True)

        matched = [n for n in registered if st.session_state.m_search in n]

        if not matched:
            st.markdown('<div class="m-bubble-bot">검색 결과가 없습니다. 다시 입력해 주세요 😅</div>'
                        '<div class="m-clearfix"></div>', unsafe_allow_html=True)
        elif st.session_state.m_agent is None:
            st.markdown('<div class="m-bubble-bot">아래에서 대리점을 선택해 주세요 👇</div>'
                        '<div class="m-clearfix"></div>', unsafe_allow_html=True)
            for name in matched:
                if st.button(f"📋 {name}", key=f"m_sel_{name}", use_container_width=True):
                    st.session_state.m_agent = name
                    st.session_state.m_month = None
                    st.session_state.m_week = None
                    st.rerun()

    # STEP 2: 대리점 → 월 → 주차 → 이미지
    if st.session_state.m_agent:
        agent = st.session_state.m_agent
        periods = all_data.get(agent, {}).get("periods", {})
        period_keys = sorted(periods.keys(), reverse=True)

        st.markdown(f'<div class="m-bubble-user">{agent}</div>'
                    f'<div class="m-clearfix"></div>', unsafe_allow_html=True)

        if not period_keys:
            st.markdown('<div class="m-bubble-bot">등록된 시상 파일이 없습니다 📋</div>'
                        '<div class="m-clearfix"></div>', unsafe_allow_html=True)
        else:
            available_months = get_months_from_periods(period_keys)

            st.markdown('<div class="m-bubble-bot">📅 월을 선택하세요</div>'
                        '<div class="m-clearfix"></div>', unsafe_allow_html=True)

            month_cols = st.columns(min(len(available_months), 4))
            for i, mo in enumerate(available_months):
                with month_cols[i % min(len(available_months), 4)]:
                    btn_type = "primary" if st.session_state.m_month == mo else "secondary"
                    if st.button(mo, key=f"m_month_{mo}", use_container_width=True, type=btn_type):
                        st.session_state.m_month = mo
                        st.session_state.m_week = None
                        st.session_state.m_expanded = False
                        st.rerun()

            if st.session_state.m_month:
                sel_month = st.session_state.m_month
                available_weeks = get_weeks_for_month(period_keys, sel_month)

                st.markdown(f'<div class="m-bubble-bot">📋 {sel_month} — 주차를 선택하세요</div>'
                            f'<div class="m-clearfix"></div>', unsafe_allow_html=True)

                week_cols = st.columns(min(len(available_weeks), 4))
                for i, wk in enumerate(available_weeks):
                    with week_cols[i % min(len(available_weeks), 4)]:
                        btn_type = "primary" if st.session_state.m_week == wk else "secondary"
                        if st.button(wk, key=f"m_week_{wk}", use_container_width=True, type=btn_type):
                            st.session_state.m_week = wk
                            st.session_state.m_expanded = False
                            st.rerun()

            # ── 이미지 표시 ────────────────────────────────────
            if st.session_state.m_month and st.session_state.m_week:
                sel_period = f"{st.session_state.m_month} {st.session_state.m_week}"
                p_images = periods.get(sel_period, {}).get("images", [])

                if p_images:
                    is_expanded = st.session_state.m_expanded

                    if not is_expanded:
                        st.markdown(f'<div class="m-bubble-bot">'
                                    f'<b>{sel_period}</b> 시상 파일 ({len(p_images)}장)</div>'
                                    f'<div class="m-clearfix"></div>', unsafe_allow_html=True)

                        thumb_cols = st.columns(2)
                        for idx, img_info in enumerate(p_images):
                            with thumb_cols[idx % 2]:
                                img_bytes = load_image_bytes(img_info["path"])
                                if img_bytes:
                                    st.image(img_bytes, use_container_width=True)

                        if st.button("🔍 탭하면 크게 볼 수 있어요", key="m_toggle_expand",
                                     use_container_width=True):
                            st.session_state.m_expanded = True
                            st.rerun()
                    else:
                        st.markdown(f'<div class="m-bubble-bot">'
                                    f'<b>{sel_period}</b> 시상 파일 ({len(p_images)}장)</div>'
                                    f'<div class="m-clearfix"></div>', unsafe_allow_html=True)

                        if st.button("🔽 섬네일로 줄이기", key="m_toggle_collapse",
                                     use_container_width=True):
                            st.session_state.m_expanded = False
                            st.rerun()

                        for idx, img_info in enumerate(p_images):
                            b64 = load_image_b64(img_info["path"])
                            if b64:
                                mt = img_info.get("media_type", "image/png")
                                st.markdown(
                                    f'<div class="m-full-img">'
                                    f'<img src="data:{mt};base64,{b64}"></div>',
                                    unsafe_allow_html=True)

                    # 카톡 공유 버튼
                    img_data_js_parts = []
                    for img in p_images:
                        b64 = load_image_b64(img["path"])
                        if b64:
                            mt = img.get("media_type", "image/png")
                            img_data_js_parts.append(f'"data:{mt};base64,{b64}"')
                    img_data_js = ",".join(img_data_js_parts)

                    share_html = f"""
                    <button id="shareBtn" style="
                        width:100%;padding:.75rem;margin:.6rem 0;
                        background:#FEE500;color:#3C1E1E;border:none;border-radius:12px;
                        font-size:.95rem;font-weight:800;cursor:pointer;
                        display:flex;align-items:center;justify-content:center;gap:.5rem;
                        box-shadow:0 2px 8px rgba(0,0,0,.1);
                        font-family:'Pretendard',sans-serif;
                    " onclick="doShare()">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="#3C1E1E">
                            <path d="M12 3C6.48 3 2 6.58 2 10.94c0 2.8 1.86 5.27 4.66 6.67-.15.56-.96 3.58-1 3.73 0 0-.02.09.03.13.06.04.13.02.13.02.17-.02 2.98-1.97 4.15-2.78.33.04.67.06 1.03.06 5.52 0 10-3.58 10-7.83C22 6.58 17.52 3 12 3z"/>
                        </svg>
                        카카오톡으로 보내기
                    </button>
                    <script>
                    async function doShare() {{
                        try {{
                            var srcs = [{img_data_js}];
                            var files = [];
                            for (var i = 0; i < srcs.length; i++) {{
                                var res = await fetch(srcs[i]);
                                var blob = await res.blob();
                                var ext = srcs[i].indexOf('image/png') > -1 ? '.png' : '.jpg';
                                files.push(new File([blob], '{agent}_' + (i+1) + ext, {{type: blob.type}}));
                            }}
                            if (navigator.canShare && navigator.canShare({{files: files}})) {{
                                await navigator.share({{
                                    title: '{agent} {sel_period} 시상',
                                    text: '{agent} {sel_period} 시상 파일입니다',
                                    files: files
                                }});
                            }} else {{
                                alert('이 브라우저에서는 파일 공유를 지원하지 않습니다.\\n이미지를 길게 눌러 저장 후 공유해 주세요.');
                            }}
                        }} catch(e) {{
                            if (e.name !== 'AbortError') {{
                                alert('공유 중 오류: ' + e.message);
                            }}
                        }}
                    }}
                    </script>
                    """
                    import streamlit.components.v1 as components
                    components.html(share_html, height=60)
                else:
                    st.markdown(f'<div class="m-bubble-bot">{sel_period}에 등록된 파일이 없습니다</div>'
                                f'<div class="m-clearfix"></div>', unsafe_allow_html=True)

    if st.session_state.m_agent:
        if st.button("🔄 다른 대리점 검색", key="m_reset", use_container_width=True):
            st.session_state.m_search = ""
            st.session_state.m_agent = None
            st.session_state.m_month = None
            st.session_state.m_week = None
            st.session_state.m_expanded = False
            st.rerun()


# ══════════════════════════════════════════════════════════════
# 관리자 화면
# ══════════════════════════════════════════════════════════════
def page_admin():
    st.markdown(BASE_CSS, unsafe_allow_html=True)
    st.markdown("""
    <div class="top-bar">
        <div class="top-title">⚙️ 관리자 — 시상 파일 등록</div>
        <div class="top-sub">대리점 선택 → 월/주차 선택 → 시상 이미지 업로드 → 저장</div>
    </div>""", unsafe_allow_html=True)

    # ── 로그인 ─────────────────────────────────────────────────
    if not st.session_state.admin_auth:
        _, mid, _ = st.columns([1, 1.5, 1])
        with mid:
            st.markdown("""
            <div style='text-align:center;padding:2rem 0 1rem'>
                <div style='font-size:2.5rem'>🔐</div>
                <h3 style='color:#800000;margin:.5rem 0 .2rem;font-size:1.2rem'>관리자 로그인</h3>
            </div>""", unsafe_allow_html=True)
            pw = st.text_input("비밀번호", type="password", label_visibility="collapsed",
                               placeholder="비밀번호 입력", key="admin_pw_input")
            if st.button("로그인", use_container_width=True, type="primary", key="login_btn"):
                if pw == ADMIN_PASSWORD:
                    st.session_state.admin_auth = True
                    st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다.")
        return

    c_top1, c_top2 = st.columns([6, 1])
    with c_top2:
        if st.button("로그아웃", key="logout"):
            st.session_state.admin_auth = False
            st.rerun()

    # ── 대리점 선택 ────────────────────────────────────────────
    st.markdown('<div class="sec-label">1. 대리점 선택</div>', unsafe_allow_html=True)
    agent = st.selectbox("대리점", ["선택하세요"] + AGENT_LIST,
                         key="admin_agent", label_visibility="collapsed")

    # ── 백업 / 복원 ───────────────────────────────────────────
    with st.expander("💾 데이터 백업 / 복원", expanded=False):
        bc1, bc2 = st.columns(2, gap="large")
        with bc1:
            st.markdown("**📥 백업 다운로드**")
            st.caption("모든 대리점 데이터 다운로드 (이미지 포함)")

            # 백업 시 이미지를 base64로 인라인 — 기존 형식 호환
            if st.button("📥 백업 파일 생성", use_container_width=True, key="backup_gen"):
                with st.spinner("백업 파일 생성 중..."):
                    backup = copy.deepcopy(st.session_state.all_data)
                    for ag, ag_data in backup.items():
                        if not isinstance(ag_data, dict) or "periods" not in ag_data:
                            continue
                        for pk, pd in ag_data["periods"].items():
                            for img in pd.get("images", []):
                                if "path" in img:
                                    b64 = load_image_b64(img["path"])
                                    if b64:
                                        img["data"] = b64
                                    del img["path"]
                    backup_json = json.dumps(backup, ensure_ascii=False, indent=2)
                    st.session_state["_backup_json"] = backup_json

            if st.session_state.get("_backup_json"):
                st.download_button(
                    label="💾 다운로드",
                    data=st.session_state["_backup_json"].encode("utf-8"),
                    file_name="ga_awards_backup.json",
                    mime="application/json",
                    use_container_width=True, key="backup_download",
                )

            agent_count = len([k for k, v in st.session_state.all_data.items()
                               if isinstance(v, dict) and v.get("periods")])
            st.caption(f"등록 대리점: {agent_count}곳")
        with bc2:
            st.markdown("**📤 백업 복원**")
            st.caption("백업 파일 업로드 시 기존 데이터를 덮어씁니다")
            restore_file = st.file_uploader("백업 JSON", type=["json"],
                                            key="restore_upload", label_visibility="collapsed")
            if restore_file:
                try:
                    restore_data = json.loads(restore_file.read().decode("utf-8"))
                    restore_count = len([k for k, v in restore_data.items()
                                         if isinstance(v, dict) and v.get("periods")])
                    st.info(f"📋 {restore_count}개 대리점 데이터 감지")
                    if st.button("⚠️ 복원 실행", use_container_width=True,
                                 type="primary", key="restore_btn"):
                        with st.spinner("복원 중... (이미지 파일 변환)"):
                            # base64 → 파일 저장으로 마이그레이션
                            restored = migrate_if_needed(restore_data)
                            st.session_state.all_data = restored
                            save_data(restored)
                        st.success(f"✅ 복원 완료! ({restore_count}개 대리점)")
                        st.rerun()
                except json.JSONDecodeError:
                    st.error("올바른 JSON 파일이 아닙니다.")
                except Exception as e:
                    st.error(f"복원 오류: {e}")

    if agent == "선택하세요":
        st.info("👆 대리점을 선택하세요.")
        return

    # ── 월/주차 선택 ───────────────────────────────────────────
    st.markdown('<div class="sec-label">2. 기간 선택</div>', unsafe_allow_html=True)
    c_month, c_week = st.columns(2)
    with c_month:
        month = st.selectbox("월", MONTHS, index=2, key="admin_month", label_visibility="collapsed")
    with c_week:
        week = st.selectbox("주차", WEEKS, key="admin_week", label_visibility="collapsed")

    period_key = f"{month} {week}"
    st.markdown(f'<span class="period-tag" style="font-size:.9rem">{period_key}</span>',
                unsafe_allow_html=True)

    # ── 기존 데이터 로드 ───────────────────────────────────────
    agent_data = st.session_state.all_data.get(agent, {})
    if isinstance(agent_data, list):
        agent_data = {}
    if "periods" not in agent_data:
        agent_data["periods"] = {}
    period_data = agent_data["periods"].get(period_key, {})
    existing_images = period_data.get("images", [])

    # ── 이미지 업로드 ──────────────────────────────────────────
    st.markdown('<div class="sec-label">3. 시상 파일 업로드</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("시상 이미지 업로드 (여러 장)",
                                type=["png", "jpg", "jpeg", "webp"],
                                accept_multiple_files=True,
                                key=f"admin_img_{agent}_{period_key}",
                                label_visibility="collapsed")
    if uploaded:
        for uf in uploaded:
            file_id = f"{uf.name}_{uf.size}"
            already = any(img.get("file_id") == file_id for img in existing_images)
            if not already:
                img_bytes = uf.read(); uf.seek(0)
                # 디스크에 저장
                path = save_image_file(agent, period_key, uf.name, img_bytes)
                mt = get_media_type(uf.name)
                existing_images.append({
                    "path": path,
                    "media_type": mt,
                    "name": uf.name,
                    "file_id": file_id,
                })

    # ── 저장 함수 ──────────────────────────────────────────────
    def _do_save():
        agent_data["periods"][period_key] = {"images": copy.deepcopy(existing_images)}
        st.session_state.all_data[agent] = agent_data
        save_data(st.session_state.all_data)

    # ── 상단 저장 버튼 ─────────────────────────────────────────
    if st.button("💾  저장", use_container_width=True, type="primary", key="save_top"):
        _do_save()
        st.success(f"✅ '{agent}' — {period_key} 저장 완료! ({len(existing_images)}장)")

    # ── 등록된 이미지 미리보기 ─────────────────────────────────
    if existing_images:
        st.markdown(f'<div class="sec-label">등록된 이미지 ({len(existing_images)}장)</div>',
                    unsafe_allow_html=True)
        for idx, img_info in enumerate(existing_images):
            col_img, col_del = st.columns([6, 1])
            with col_img:
                img_bytes = load_image_bytes(img_info.get("path", ""))
                if img_bytes:
                    st.image(img_bytes, caption=img_info.get("name", ""),
                             use_container_width=True)
                else:
                    st.warning("이미지 파일을 찾을 수 없습니다")
            with col_del:
                st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)
                if st.button("🗑", key=f"del_img_{idx}_{period_key}"):
                    delete_image_file(img_info.get("path", ""))
                    existing_images.pop(idx)
                    st.rerun()
    else:
        st.markdown("<div style='text-align:center;padding:1.5rem;color:#bbb'>"
                    "아직 등록된 이미지가 없습니다</div>", unsafe_allow_html=True)

    # ── 하단 저장 버튼 ─────────────────────────────────────────
    st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
    if st.button("💾  저장", use_container_width=True, type="primary", key="save_bottom"):
        _do_save()
        st.success(f"✅ '{agent}' — {period_key} 저장 완료! ({len(existing_images)}장)")

    # ── 전체 등록 현황 ─────────────────────────────────────────
    all_periods = agent_data.get("periods", {})
    if all_periods:
        st.markdown("---")
        st.markdown(f'<div class="sec-label">📋 {agent} 전체 등록 현황</div>',
                    unsafe_allow_html=True)
        for pk in sorted(all_periods.keys(), reverse=True):
            p_imgs = all_periods[pk].get("images", [])
            st.markdown(f'<span class="period-tag">{pk}</span>'
                        f'<span style="font-size:.82rem;color:#888;margin-left:.4rem">'
                        f'{len(p_imgs)}장</span>', unsafe_allow_html=True)

        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
        if st.button("🗑 이 대리점 전체 데이터 삭제", key="del_all_agent"):
            if agent in st.session_state.all_data:
                delete_agent_images(agent)          # 이미지 파일도 삭제
                del st.session_state.all_data[agent]
                save_data(st.session_state.all_data)
                st.success(f"'{agent}' 전체 데이터가 삭제되었습니다.")
                st.rerun()


# ══════════════════════════════════════════════════════════════
# 라우터
# ══════════════════════════════════════════════════════════════
if st.session_state.page == "viewer":
    if IS_MOBILE:
        page_viewer_mobile()
    else:
        page_viewer_desktop()
else:
    page_admin()
