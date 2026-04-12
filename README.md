# 🎬 AI 영상 자동화

주제를 입력하면 **대본 작성 → 영상 수집 → 나레이션 생성 → 자동 편집**까지 AI가 처리합니다.

---

## 동작 방식

```
주제 입력
  ↓
Gemini AI → 대본(장면별 나레이션·자막) 생성
  ↓
Pexels → 장면별 스톡 영상 자동 다운로드
  ↓
Edge TTS → 한국어 나레이션 음성 생성
  ↓
ffmpeg → 영상 + 자막 + 나레이션 합성
  ↓
완성된 MP4 다운로드
```

---

## 설치 방법

### 1단계 - 필수 프로그램 설치

**Python 3.10 이상**
- https://www.python.org/downloads/
- 설치 시 **"Add Python to PATH"** 체크 필수

**ffmpeg**
- https://ffmpeg.org/download.html → Windows builds → 다운로드
- 압축 해제 후 `ffmpeg.exe` 경로를 시스템 PATH에 추가
- 또는 PowerShell에서: `winget install Gyan.FFmpeg`

### 2단계 - 프로젝트 다운로드

```bash
git clone https://github.com/aiautou/ai-video-generator.git
cd ai-video-generator
```

또는 GitHub에서 **Code → Download ZIP** 후 압축 해제

### 3단계 - Python 패키지 설치

```bash
pip install -r requirements.txt
```

### 4단계 - API 키 발급 (무료)

| 서비스 | 용도 | 발급 링크 |
|--------|------|-----------|
| **Gemini API** | AI 대본 생성 | https://aistudio.google.com → Get API Key |
| **Pexels API** | 스톡 영상 | https://www.pexels.com/api/ |

### 5단계 - 환경 설정

```bash
copy .env.example .env
```

`.env` 파일을 메모장으로 열어서 API 키 입력:

```
GEMINI_API_KEY=발급받은_키_붙여넣기
PEXELS_API_KEY=발급받은_키_붙여넣기
```

### 6단계 - 서버 실행

`start_server.bat` 더블클릭

브라우저에서 http://localhost:8080 접속

---

## 사용 방법

1. 브라우저에서 http://localhost:8080 접속
2. **영상 주제** 입력 (예: `경복궁의 역사`, `AI 기술 트렌드 2026`)
3. **목표 시간** 설정 (기본 180초)
4. **영상 생성 시작** 클릭
5. 진행률 확인 후 완료되면 **영상 다운로드**

---

## 문제 해결

| 증상 | 해결 방법 |
|------|-----------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` 재실행 |
| 영상이 0개 생성 | Pexels API 키 확인 |
| 대본 생성 실패 | Gemini API 키 확인 |
| 나레이션 없음 | 인터넷 연결 확인 (Edge TTS는 온라인 필요) |
| ffmpeg 오류 | ffmpeg PATH 등록 확인: `ffmpeg -version` |

---

## 파일 구조

```
ai-video-generator/
├── server.py              # 웹 서버 (FastAPI)
├── config.py              # 설정
├── requirements.txt       # Python 패키지 목록
├── .env.example           # 환경변수 템플릿
├── start_server.bat       # 서버 실행 (Windows)
├── web/
│   └── index.html         # 웹 UI
└── pipeline/
    ├── script_gen.py      # Gemini AI 대본 생성
    ├── asset_collector.py # Pexels 영상 수집
    ├── tts_gen.py         # Edge TTS 나레이션
    ├── ffmpeg_renderer.py # 영상 렌더링
    └── r2_storage.py      # Cloudflare R2 저장 (선택)
```

---

## 라이선스

MIT License - 자유롭게 사용·수정·배포 가능
