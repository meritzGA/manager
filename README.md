# 주간 시책 검색 자동화

대리점별 주간 시책 이미지를 자동으로 정리하고 외부에서 조회할 수 있게 해주는 도구입니다.

## 동작 방식

```
[원본 시책 이미지]                [매칭 + 정리]                  [GitHub + Streamlit Cloud]
2605_4/                          organized/2605_4/                외부 조회 화면
  KakaoTalk_xxx.jpg     ──▶       에이플러스에셋_1.png     ──▶     월/주차/대리점 선택
  사진001.png                      굿리치_1.jpg                     → 시책 이미지 표시
  ...                              ...
```

1. 매주 새 주차 폴더(예: `2605_4`)에 시책 이미지들을 무더기로 넣음
2. `python scripts/match.py 2605_4` 실행
   - 파일명에 대리점 힌트(영문 약어 등)가 있으면 즉시 매칭
   - 없으면 EasyOCR로 이미지 상단의 대리점명을 읽어 자동 매칭
   - 그래도 매칭 실패면 콘솔에서 직접 선택 가능
3. `organized/2605_4/` 안에 `대리점한글명_N.확장자` 형태로 정리됨
4. `git add organized/ && git commit && git push` → Streamlit Cloud가 자동 반영
5. 외부에서 URL 접속 → 시책 조회

## 폴더 구조

```
주간 시책 검색 자동화/
├── 2605_4/                  # 원본 시책 (gitignore - 푸시 안 됨)
├── ...
├── organized/               # 정리된 결과 (GitHub에 푸시됨)
│   ├── 2604_1/
│   │   ├── 굿리치_1.jpg
│   │   └── ...
│   └── 2605_3/
├── data/
│   ├── agencies.json        # 대리점 마스터 리스트 (179개)
│   └── filename_hints.json  # 영문 파일명 → 한글 대리점명 힌트
├── scripts/
│   └── match.py             # 매칭/정리 스크립트
├── streamlit_app/
│   └── app.py               # 조회 앱
├── requirements.txt         # Streamlit Cloud 용
├── requirements-local.txt   # 로컬 매칭 스크립트 용
└── .gitignore
```

## 초기 설치 (한 번만)

### 1. Python 환경 (로컬 PC)

```powershell
# Python 3.9+ 설치되어 있어야 함
cd "D:\Prize_GA\주간 시책 검색 자동화"
python -m venv venv
venv\Scripts\activate
pip install -r requirements-local.txt
```

### 2. GitHub 저장소 만들기

1. [GitHub.com](https://github.com)에서 새 저장소 생성 (예: `weekly-policy`)
   - **Public**으로 설정 (Streamlit Community Cloud 무료 플랜은 public 저장소만 지원)
   - "Add a README" 체크 안 함 (이미 있음)
2. 로컬에서 첫 푸시:

```powershell
cd "D:\Prize_GA\주간 시책 검색 자동화"
git init
git branch -M main
git add .
git commit -m "Initial: 시책 조회 시스템"
git remote add origin https://github.com/YOURNAME/weekly-policy.git
git push -u origin main
```

### 3. Streamlit Cloud 배포

1. [share.streamlit.io](https://share.streamlit.io)에 GitHub 계정으로 로그인
2. "New app" 클릭
3. 저장소 / 브랜치 선택, **Main file path**: `streamlit_app/app.py`
4. Deploy 클릭
5. 1-2분 후 URL이 생성됨 (예: `https://YOURNAME-weekly-policy.streamlit.app`)

## 매주 작업 흐름

```powershell
cd "D:\Prize_GA\주간 시책 검색 자동화"
venv\Scripts\activate

# 1. 새 주차 폴더 만들고 시책 이미지들 무더기로 복사 (예: 26년 5월 4주차)
mkdir 2605_4
# (이미지 파일들을 2605_4/ 에 복사)

# 2. 매칭 실행
python scripts/match.py 2605_4

# 3. 결과 확인 (organized/2605_4/)
explorer organized\2605_4

# 4. GitHub에 푸시
git add organized/
git commit -m "Add 2605_4"
git push
```

푸시 후 1-2분 안에 Streamlit Cloud 앱에 자동 반영됩니다.

## 옵션

```
python scripts/match.py 2605_4              # 기본: OCR + 수동 매칭
python scripts/match.py 2605_4 --no-ocr     # 파일명 힌트만 사용 (빠름)
python scripts/match.py 2605_4 --dry-run    # 실제 복사하지 않고 결과만 미리보기
python scripts/match.py 2605_4 --no-interactive  # 자동 매칭만, 실패는 스킵
```

## 새 대리점 추가

새로운 대리점이 생기면 `data/agencies.json`에 추가하세요:

```json
{
  "full_name": "(주)신규대리점",
  "aliases": ["신규대리점", "신규"]
}
```

`aliases`는 이미지 안에 등장할 가능성이 있는 모든 표기를 적어두면 OCR 매칭률이 올라갑니다.

## 자주 묻는 문제

**Q. OCR이 너무 느려요.**
- 첫 실행 시 EasyOCR이 한국어 모델(~100MB)을 다운로드해서 1-2분 걸립니다. 두 번째부터는 빠릅니다.
- 파일명을 이미 한글로 저장해두면 `--no-ocr` 옵션으로 훨씬 빠르게 처리할 수 있습니다.

**Q. 매칭이 잘못된 대리점으로 됐어요.**
- 해당 파일을 `organized/` 폴더에서 직접 이름 변경하거나 삭제하면 됩니다.
- 자주 틀리는 패턴이 있으면 `data/filename_hints.json`에 명시적으로 매핑을 추가하세요.

**Q. Streamlit 앱에 새 데이터가 안 보여요.**
- 앱 좌측 상단의 "🔄 새로고침" 버튼을 누르거나, 브라우저를 새로고침하세요.
- GitHub 푸시 후 Streamlit Cloud 반영까지 1-2분 걸립니다.
