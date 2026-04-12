# 🎬 AI 영상 자동화 프로젝트

> 주제 하나만 입력하면 AI가 대본을 쓰고, 영상을 찾고, 목소리까지 입혀서 완성된 영상을 만들어줍니다!

---

## 📺 어떻게 동작하나요?

```
여러분이 할 일: 주제 입력 (예: "경복궁의 역사")
                        ↓
  🤖 Gemini AI    →  장면별 대본 + 자막 자동 작성
                        ↓
  📹 Pexels       →  각 장면에 맞는 스톡 영상 자동 다운로드
                        ↓
  🗣️ Edge TTS     →  한국어 나레이션 음성 자동 생성
                        ↓
  🎞️ ffmpeg       →  영상 + 자막 + 나레이션 합치기
                        ↓
  완성된 MP4 영상 다운로드! 🎉
```

---

## 🛠️ 설치 방법 (처음 한 번만 하면 됩니다)

### ✅ 1단계 - Python 설치

1. https://www.python.org/downloads/ 접속
2. **"Download Python 3.11"** (또는 최신 버전) 클릭
3. 설치 시작할 때 **꼭! "Add Python to PATH" 체크박스를 체크**하세요
   ```
   ☑ Add Python to PATH  ← 이거 반드시 체크!
   ```
4. "Install Now" 클릭해서 설치 완료

> 설치 확인: 명령 프롬프트(cmd)에서 `python --version` 입력 → 버전 숫자가 나오면 성공!

---

### ✅ 2단계 - ffmpeg 설치

ffmpeg는 영상을 편집하는 핵심 프로그램입니다.

**방법 A - winget으로 설치 (추천, 쉬움):**
1. Windows 검색창에 "PowerShell" 검색 → 우클릭 → **"관리자 권한으로 실행"**
2. 아래 명령어 입력 후 Enter:
   ```
   winget install Gyan.FFmpeg
   ```
3. 설치 완료 후 PowerShell 창 닫고 **컴퓨터 재시작**

**방법 B - 직접 설치:**
1. https://ffmpeg.org/download.html 접속
2. Windows → "Windows builds from gyan.dev" 클릭
3. `ffmpeg-release-essentials.zip` 다운로드
4. 압축 해제 후 `bin` 폴더 안의 파일들을 `C:\ffmpeg\bin\` 에 복사
5. 시스템 환경변수 PATH에 `C:\ffmpeg\bin` 추가

> 설치 확인: cmd에서 `ffmpeg -version` 입력 → 버전 정보가 나오면 성공!

---

### ✅ 3단계 - 프로젝트 다운로드

**방법 A - ZIP 다운로드 (git 없을 때):**
1. 이 페이지 상단 초록색 **"Code"** 버튼 클릭
2. **"Download ZIP"** 클릭
3. 다운로드된 ZIP 압축 해제
4. 폴더 이름을 `ai-video-generator` 로 변경

**방법 B - git clone (git 있을 때):**
```bash
git clone https://github.com/Samuel-Jo/ai-video-generator.git
cd ai-video-generator
```

---

### ✅ 4단계 - API 키 발급 (무료!)

이 프로젝트는 2개의 무료 API 키가 필요합니다.

#### 🔑 Gemini API 키 (AI 대본 생성용)

1. https://aistudio.google.com 접속
2. Google 계정으로 로그인
3. 왼쪽 메뉴에서 **"Get API Key"** 클릭
4. **"Create API Key"** 클릭
5. 생성된 키 복사 (예: `AIzaSy...` 로 시작하는 긴 문자열)

> 💡 무료 한도: 하루 500번 요청 가능 (충분합니다!)

#### 🔑 Pexels API 키 (스톡 영상용)

1. https://www.pexels.com/api/ 접속
2. **"Get Started"** 클릭 → 회원가입 (무료)
3. 이메일 인증 완료
4. API 키 페이지에서 키 복사

> 💡 무료 한도: 월 200건 다운로드 (충분합니다!)

---

### ✅ 5단계 - 환경 설정 파일 만들기

1. 프로젝트 폴더에서 `.env.example` 파일을 찾습니다
2. 이 파일을 복사해서 이름을 `.env` 로 변경합니다

   **Windows 명령 프롬프트에서:**
   ```
   copy .env.example .env
   ```

3. `.env` 파일을 **메모장**으로 열기
   (파일이 안 보이면: 탐색기 → 보기 → "숨김 항목" 체크)

4. 아래 두 줄을 찾아서 발급받은 키로 교체:
   ```
   GEMINI_API_KEY=여기에_Gemini_API_키_입력
   PEXELS_API_KEY=여기에_Pexels_API_키_입력
   ```

   예시:
   ```
   GEMINI_API_KEY=AIzaSyABC123def456...
   PEXELS_API_KEY=hCjNeLeti...
   ```

5. 저장 (Ctrl+S)

---

### ✅ 6단계 - Python 패키지 설치

프로젝트 폴더에서 명령 프롬프트를 열고 입력:

```bash
pip install -r requirements.txt
```

> 💡 프로젝트 폴더에서 cmd 여는 방법: 탐색기에서 폴더를 열고 주소창에 `cmd` 입력 후 Enter

설치에 1~3분 정도 걸립니다. 완료되면 다음 단계로!

---

## 🚀 실행 방법

### 서버 시작

프로젝트 폴더에서 **`start_server.bat`** 파일을 더블클릭!

까만 터미널 창이 열리고 아래 메시지가 나오면 성공:
```
==================================================
  AI 영상 자동화 서버 시작
  로컬: http://localhost:8080
==================================================
```

### 영상 만들기

1. 브라우저(Chrome, Edge 등)에서 **http://localhost:8080** 접속
2. **"영상 주제"** 칸에 원하는 주제 입력
   - 예시: `경복궁의 역사`
   - 예시: `2026년 AI 기술 트렌드`
   - 예시: `건강한 아침 식사의 중요성`
3. **"목표 시간"** 설정 (기본값 180초 = 3분)
4. **"영상 생성 시작"** 버튼 클릭
5. 진행 상황을 실시간으로 확인 (3~10분 소요)
6. 완료되면 **"영상 다운로드"** 버튼 클릭!

---

## ❓ 자주 묻는 질문 & 문제 해결

### "ModuleNotFoundError: No module named 'xxx'" 오류가 나요

```bash
pip install -r requirements.txt
```
다시 실행해 보세요.

---

### "ffmpeg를 찾을 수 없습니다" 오류가 나요

cmd에서 `ffmpeg -version` 을 입력해 보세요.
- 버전 정보가 나오면 → 컴퓨터를 재시작 후 다시 시도
- "명령을 찾을 수 없습니다" 가 나오면 → 2단계로 돌아가서 ffmpeg 재설치

---

### 영상이 1~2개밖에 안 만들어져요

Pexels API 키를 확인하세요. `.env` 파일을 열어서 `PEXELS_API_KEY=` 뒤에 키가 제대로 입력되어 있는지 확인합니다.

---

### 나레이션 소리가 없어요

인터넷 연결을 확인하세요. Edge TTS는 인터넷이 필요합니다.

---

### 대본 생성이 실패해요

Gemini API 키를 확인하세요. `.env` 파일의 `GEMINI_API_KEY=` 값을 확인합니다.

---

### 서버가 이미 실행 중이라고 나와요

이미 실행 중인 서버가 있습니다. 작업 관리자(Ctrl+Shift+Esc)에서 `python.exe` 프로세스를 종료 후 다시 시도하세요.

---

## 📁 프로젝트 구조 (참고용)

```
ai-video-generator/
│
├── 📄 server.py              ← 웹 서버 (이걸 실행해요)
├── 📄 config.py              ← 설정값 모음
├── 📄 requirements.txt       ← 필요한 Python 패키지 목록
├── 📄 .env.example           ← 환경변수 템플릿 (→ .env로 복사)
├── 📄 start_server.bat       ← 서버 실행 버튼 (더블클릭!)
│
├── 📁 web/
│   └── index.html            ← 웹사이트 화면
│
└── 📁 pipeline/
    ├── script_gen.py         ← Gemini AI로 대본 생성
    ├── asset_collector.py    ← Pexels에서 영상 수집
    ├── tts_gen.py            ← Edge TTS로 나레이션 생성
    └── ffmpeg_renderer.py    ← ffmpeg로 최종 영상 완성
```

---

## 🆓 사용한 무료 서비스

| 서비스 | 용도 | 무료 한도 |
|--------|------|-----------|
| Google Gemini API | AI 대본 생성 | 하루 500회 |
| Pexels API | 스톡 영상 | 월 200건 |
| Microsoft Edge TTS | 한국어 나레이션 | 무제한 |
| ffmpeg | 영상 편집 | 무제한 |

---

## 📞 도움이 필요하면

문제가 해결되지 않으면 **Issues** 탭에 글을 남겨주세요!

---

*MIT License - 자유롭게 사용·수정·배포 가능합니다*
