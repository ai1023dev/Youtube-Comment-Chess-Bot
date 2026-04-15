# ♟️ YouTube 체스 봇

YouTube 라이브 영상의 고정 댓글을 체스판으로 활용하는 봇입니다.
시청자가 대댓글로 기보를 입력하면 좋아요 수 기준으로 수를 채택하고, Stockfish AI가 흑으로 응수합니다.
매 10분마다 자동으로 댓글을 갱신합니다.

---

## 동작 방식

1. 고정 댓글의 대댓글을 최대 6,000개까지 수집합니다.
2. 최근 10분 이내에 작성된 `[e4]`, `[Nf3]` 형식의 대댓글만 후보로 추립니다.
3. 좋아요 수(동점 시 최신순)가 가장 높은 합법적인 수를 채택합니다.
4. Stockfish가 흑으로 0.1초 내에 응수합니다.
5. 결과 체스판과 전적을 고정 댓글에 자동으로 업데이트합니다.
6. 게임이 종료되면 승패를 기록하고 새 게임을 시작합니다.

```
시청자 대댓글 → 좋아요 투표 → 봇이 수 채택 → Stockfish 응수 → 댓글 갱신
```

---

## 설치

Stockfish 바이너리를 프로젝트 루트에 배치합니다. (용량 제한 때문에 안 올라가져서 [Stockfish](https://stockfishchess.org/download/)에서 직접 다운받으세요.)

```
your-repo/
├── bot.py
├── stockfish          # Stockfish 실행 파일
├── client_secret.json # Google OAuth2 자격증명
├── .env
└── README.md
```

---

## 환경 설정

### `.env` 파일 (직접 생성 하셔야 합니다.)

```env
COMMENT_API_KEY=여기에_YouTube_Data_API_키_입력
```

### `bot.py` 내 VIDEO_ID 설정

```python
VIDEO_ID = "여기에_YouTube_영상_ID_입력"
```

### Google OAuth2 설정

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 생성합니다.
2. YouTube Data API v3를 활성화합니다.
3. OAuth2 클라이언트 ID를 생성하고 `client_secret.json`으로 저장합니다.
4. 최초 실행 시 브라우저 인증 화면이 열리며, 이후 `token.json`이 자동 생성됩니다.

X. 무료로 사용하려면 댓글을 읽는 API키와 댓글 수정용 client_secret.json는 다른 계정으로 발급 받으세요.

---

## 실행

```bash
python bot.py
```

최초 실행 시 OAuth2 브라우저 인증이 요청됩니다. 이후에는 `token.json`을 통해 자동 갱신됩니다.

---

## 생성 파일

| 파일 | 설명 |
|------|------|
| `token.json` | Google OAuth2 액세스 토큰 (자동 생성) |
| `win_loss_record.json` | 백/흑/무승부 전적 기록 |

---

## 기보 입력 형식

시청자는 고정 댓글의 대댓글로 **SAN 표기법**을 대괄호로 감싸 입력합니다.

| 입력 예시 | 의미 |
|-----------|------|
| `[e4]` | 폰을 e4로 전진 |
| `[Nf3]` | 나이트를 f3으로 이동 |
| `[O-O]` | 킹사이드 캐슬링 |
| `[Qxd5]` | 퀸으로 d5 기물 잡기 |

---

## 주의 사항

- 댓글 수정은 **본인(봇 계정) 댓글에만** 가능합니다. 고정 댓글이 봇 계정으로 작성되어 있어야 합니다.
- YouTube Data API는 일일 할당량 제한이 있습니다. 대댓글이 매우 많은 경우 할당량에 주의하세요. (대댓글이 6000개가 넘을시 고정댓글을 교체해 주세요.)

---

## 라이선스

MIT
