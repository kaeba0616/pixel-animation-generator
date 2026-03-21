# WebSocket 기반 웹 완결형 UI 설계

## Context

현재 파이프라인은 CLI(대화) + 브라우저(이미지 미리보기)를 왔다갔다 해야 한다.
모든 상호작용을 브라우저 하나에서 처리하고, WebSocket으로 실시간 통신하도록 전환한다.

## 설계 결정

- **레이아웃**: 상하 분할 (위 이미지 / 아래 채팅), 상태에 따라 패널 비율 동적 변경
- **이미지 선택**: 그리드에서 클릭 선택 + 하단 채팅으로 피드백 (Midjourney 스타일)
- **통신**: Flask-SocketIO (WebSocket 양방향)
- **Async 전략**: `async_mode='threading'` — eventlet/gevent 미사용. google-genai SDK가 gRPC를 사용하므로 monkey-patching 호환성 문제 회피. API 호출은 `socketio.start_background_task()`로 백그라운드 스레드 실행.
- **단일 유저**: 로컬 도구이므로 동시 접속은 고려하지 않음. 단일 SessionContext 유지.
- **진입점**: `python3 app.py` 한 번으로 서버 시작 → 브라우저에서 전부 처리

## 화면 상태 전환

```
CHATTING → GENERATING → PREVIEWING ←→ REFINING → GENERATING (루프)
    ↓                       ↓               ↓
   DONE                 ANIMATING → DONE
                                      ↓
                                   CHATTING (리셋)
```

### State 1: CHATTING
- 채팅이 전체 화면 차지 (이미지 패널 숨김)
- 사용자 메시지 → WebSocket `chat` → 서버 Gemini 호출 (백그라운드 스레드) → `response` 이벤트로 응답 표시
- 트리거 키워드 ("생성해줘" 등) 감지 시 캐릭터 추출 → GENERATING 전환
- "종료" 입력 시 DONE 전환

### State 2: GENERATING
- 상단에 이미지 패널 나타남 (애니메이션 슬라이드)
- Grok API로 4장 생성 (백그라운드 스레드), 완성될 때마다 `image_ready` 이벤트 → 1장씩 실시간 표시
- 진행률 표시: "2/4 생성 중..."
- `cancel` 이벤트 수신 시 생성 중단, PREVIEWING (이미 생성된 것이 있으면) 또는 CHATTING으로 복귀
- 전부 완료 시 PREVIEWING 전환
- **에러 발생 시**: `error` 이벤트 + CHATTING으로 복귀

### State 3: PREVIEWING
- 상단: 이미지 4장 그리드 (클릭 선택 → 초록 테두리, 더블클릭 → 확대 모달)
- 하단: 채팅 영역 (피드백 입력 가능)
- "수정 요청" 버튼 (선택 + 피드백) → REFINING
- "이걸로 진행" 버튼 → ANIMATING

### State 4: REFINING
- 선택 이미지 + 피드백 텍스트 → 서버 Gemini 멀티모달 호출 (백그라운드 스레드)
- 프롬프트 개선 결과를 채팅에 표시 ("변경사항: 팔 포즈를 위로 수정")
- 자동으로 GENERATING 전환 (재생성)
- **에러 발생 시**: `error` 이벤트 + PREVIEWING으로 복귀

### State 5: ANIMATING
- 확정된 캐릭터로 애니메이션 프레임 생성 + 후처리 + GIF 조립 (백그라운드 스레드)
- `progress` 이벤트로 진행률 표시
- 완료 시 `animation_done` + GIF 미리보기 + 다운로드 버튼
- `cancel` 이벤트 수신 시 PREVIEWING으로 복귀
- **에러 발생 시**: `error` 이벤트 + PREVIEWING으로 복귀

### State 6: DONE
- GIF 표시 + 다운로드 링크
- "새 캐릭터 만들기" 버튼 → `reset` 이벤트 → CHATTING으로 리셋 (SessionContext 초기화)

## 아키텍처

### app.py — 핵심 설계

`app.py`는 WebSocket 이벤트를 받아 `session.py`의 함수를 직접 호출하는 얇은 레이어.

```python
# 구조 개요
socketio = SocketIO(app, async_mode='threading')
ctx = SessionContext()  # 단일 세션

@socketio.on('chat')
def handle_chat(data):
    # 백그라운드 스레드에서 Gemini 호출
    socketio.start_background_task(process_chat, data['message'])

@socketio.on('refine')
def handle_refine(data):
    socketio.start_background_task(process_refine, data['index'], data['feedback'])

@socketio.on('approve')
def handle_approve(data):
    socketio.start_background_task(process_animate, data['index'])

@socketio.on('cancel')
def handle_cancel():
    ctx.cancel_requested = True

@socketio.on('reset')
def handle_reset():
    ctx.reset()
    emit('state_change', {'state': 'CHATTING'})
```

각 `process_*` 함수는 `session.py`의 로직을 호출하고, 결과를 `socketio.emit()`으로 클라이언트에 전달.

### session.py 리팩토링

CLI `input()` 의존성을 완전히 제거. 각 `handle_*` 함수가:
- 인자로 데이터를 받음 (WebSocket 이벤트에서)
- 결과를 반환 (dict) — `app.py`가 emit으로 전달
- `ctx.cancel_requested` 플래그 체크하여 중단 가능

`PreviewState` 의존성 제거 (preview_server.py 삭제에 따라).

### 이미지 서빙

생성된 이미지는 디스크에 저장하고 HTTP로 서빙 (WebSocket으로 base64 전송하지 않음):
- `GET /image/<filename>` — output 디렉토리에서 이미지 파일 서빙
- `image_ready` 이벤트에 URL 경로만 포함: `{index: 0, url: "/image/candidate_00.png"}`
- GIF도 동일: `animation_done` 이벤트에 `{gif_url: "/image/idle.gif"}`

### Socket.IO 클라이언트

CDN에서 로드: `<script src="https://cdn.socket.io/4.x/socket.io.min.js">`

## WebSocket 이벤트 프로토콜

### 클라이언트 → 서버
| 이벤트 | 데이터 | 설명 |
|--------|--------|------|
| `chat` | `{message: str}` | 사용자 채팅 메시지 |
| `refine` | `{index: int, feedback: str}` | 선택 이미지 + 피드백 → 프롬프트 개선 + 재생성 |
| `approve` | `{index: int}` | 이미지 확정 → 애니메이션 생성 시작 |
| `cancel` | `{}` | 현재 진행 중인 생성/애니메이션 중단 |
| `reset` | `{}` | 세션 초기화 → CHATTING으로 복귀 |

### 서버 → 클라이언트
| 이벤트 | 데이터 | 설명 |
|--------|--------|------|
| `response` | `{text: str}` | Gemini 채팅 응답 |
| `state_change` | `{state: str}` | UI 상태 전환 지시 |
| `image_ready` | `{index: int, url: str}` | 생성된 이미지 1장 URL (실시간) |
| `progress` | `{current: int, total: int, label: str}` | 진행률 |
| `character` | CharacterSpec.to_dict() 전체 | 추출된 캐릭터 정보 |
| `refine_result` | `{summary: str, prompt: str}` | 프롬프트 개선 결과 |
| `animation_done` | `{gif_url: str}` | GIF 완성 + 다운로드 URL |
| `error` | `{message: str, fallback_state: str}` | 에러 + 복귀할 상태 |

## 재접속 처리

페이지 새로고침 또는 재접속 시:
- `connect` 이벤트에서 서버가 현재 SessionContext 상태를 전송
- `state_change` + 현재 상태에 맞는 데이터 (후보 이미지 URL, 캐릭터 정보 등)
- 클라이언트가 해당 상태의 UI를 즉시 복원

## 의존성 변경

### requirements.txt
- 유지: `flask>=3.0.0` (Flask-SocketIO 별도 패키지)
- 추가: `flask-socketio>=5.3.0`
- **eventlet/gevent 불필요** (`async_mode='threading'` 사용)

## 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `app.py` | **신규** — Flask-SocketIO 메인 서버 |
| `templates/index.html` | **신규** — 웹 완결형 UI (채팅 + 이미지 + 상태 전환) |
| `preview_server.py` | **삭제** — app.py로 대체 |
| `templates/preview.html` | **삭제** — index.html로 대체 |
| `session.py` | **수정** — CLI 의존성 제거, WebSocket용 함수 인터페이스로 전환, PreviewState 제거 |
| `chat.py` | **수정** — --cli 플래그로 CLI 모드 유지, 기본은 app.py 안내 |
| `config.py` | **수정** — SECRET_KEY 추가 |
| `requirements.txt` | **수정** — flask-socketio 추가 |
| `tests/test_e2e.py` | **수정** — SocketIO test_client 기반 테스트 추가 |

변경 없는 파일: `prompt_generator.py`, `pixel_cleaner.py`, `grok_client.py`, `story_engine.py`, `models.py`, `aseprite_runner.py`

## 검증 방법

1. `python3 app.py` 실행 → 브라우저에서 `http://localhost:5050` 접속
2. 채팅으로 캐릭터 설명 → "생성해줘" → 이미지 4장 실시간 표시 확인
3. 이미지 클릭 선택 → 피드백 입력 → "수정 요청" → 재생성 확인
4. "이걸로 진행" → GIF 생성 → 다운로드 확인
5. 페이지 새로고침 → 상태 복원 확인
6. 생성 중 "취소" → 복귀 확인
7. E2E 테스트: `python3 tests/test_e2e.py --offline` — Flask-SocketIO test_client로 이벤트 프로토콜 검증 (Grok/Gemini API 모킹)
