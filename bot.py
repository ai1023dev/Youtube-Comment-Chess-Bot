import os
import re
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import chess
import chess.engine
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── 설정 ──────────────────────────────────────────────────────────────────────

# https://www.youtube.com/watch?v=?????? 에서 ?기 VIDEO ID입니다.
VIDEO_ID    = "ABCD1234"

load_dotenv(dotenv_path=Path(__file__).parent / ".env")
API_KEY     = os.getenv("COMMENT_API_KEY", "")
TOKEN_FILE  = Path(__file__).parent / "token.json"
SECRET_FILE = Path(__file__).parent / "client_secret.json"
SCOPES       = ["https://www.googleapis.com/auth/youtube.force-ssl"]
RECORD_FILE  = Path(__file__).parent / "win_loss_record.json"

if not API_KEY:
    raise ValueError("COMMENT_API_KEY 없음 — .env 파일을 확인하세요")

# ── 체스 상태 ──────────────────────────────────────────────────────────────────

game_board = chess.Board()
engine     = chess.engine.SimpleEngine.popen_uci("./stockfish")

# ── 전적 기록 ──────────────────────────────────────────────────────────────────

def load_record() -> dict:
    if RECORD_FILE.exists():
        return json.loads(RECORD_FILE.read_text(encoding="utf-8"))
    return {"white": 0, "black": 0, "draw": 0}

def save_record(record: dict):
    RECORD_FILE.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

def record_line(record: dict) -> str:
    return f"백 승: {record['white']}  흑 승: {record['black']}  무승부: {record['draw']}"

# ── YouTube 클라이언트 (캐싱) ──────────────────────────────────────────────────

_read_client = None
_auth_client = None

def get_read_client():
    global _read_client
    if _read_client is None:
        _read_client = build("youtube", "v3", developerKey=API_KEY)
    return _read_client

def get_auth_client():
    global _auth_client
    if _auth_client is not None:
        return _auth_client

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"client_secret.json 없음: {SECRET_FILE}\n"
                    "Google Cloud Console에서 OAuth2 자격증명을 다운로드하세요."
                )
            flow  = InstalledAppFlow.from_client_secrets_file(str(SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    _auth_client = build("youtube", "v3", credentials=creds)
    return _auth_client

# ── YouTube API ────────────────────────────────────────────────────────────────

def get_pinned_comment(video_id: str) -> dict | None:
    """영상의 첫 번째 댓글 스레드 정보를 반환합니다."""
    try:
        res = get_read_client().commentThreads().list(
            part="snippet", videoId=video_id, maxResults=1
        ).execute()
    except HttpError as e:
        print(f"[오류] get_pinned_comment ({e.status_code}): {e.reason}")
        return None

    items = res.get("items", [])
    if not items:
        return None

    item = items[0]
    return {
        "thread_id":   item["id"],
        "comment_id":  item["snippet"]["topLevelComment"]["id"],
        "reply_count": item["snippet"]["totalReplyCount"],
    }


def get_replies(thread_id: str) -> list[str]:
    """전체 대댓글을 최대 6000개까지 가져온 뒤 10분 이내 [기보] 형식만 반환합니다."""
    MAX_REPLIES  = 6000
    cutoff       = datetime.now(timezone.utc) - timedelta(minutes=10)
    bracket_move = re.compile(r'^\[[A-Za-z][A-Za-z0-9\-\+\#\=]*\]$')
    replies      = []
    page_token   = None
    fetched      = 0
 
    while fetched < MAX_REPLIES:
        try:
            req = get_read_client().comments().list(
                part="snippet", parentId=thread_id, maxResults=100,
                **( {"pageToken": page_token} if page_token else {} )
            )
            res = req.execute()
        except HttpError as e:
            print(f"[오류] get_replies ({e.status_code}): {e.reason}")
            break
 
        items = res.get("items", [])
        fetched += len(items)
 
        for item in items:
            snippet      = item["snippet"]
            text         = snippet["textDisplay"].strip()
            published_at = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
 
            if published_at < cutoff:
                continue
            if not bracket_move.match(text):
                continue
 
            replies.append({
                "text":         text,
                "like":         snippet["likeCount"],
                "published_at": published_at,
            })
 
        page_token = res.get("nextPageToken")
        if not page_token:
            break
 
    print(f"대댓글 {fetched}개 조회 완료 ({len(replies)}개 후보)")
    replies.sort(key=lambda x: (x["like"], x["published_at"]), reverse=True)
    return [r["text"] for r in replies]


def update_comment(comment_id: str, new_text: str) -> dict | None:
    """댓글을 수정합니다. (OAuth2 인증 필요, 본인 댓글만 가능)"""
    try:
        res = get_auth_client().comments().update(
            part="snippet",
            body={"id": comment_id, "snippet": {"textOriginal": new_text}},
        ).execute()
        snippet = res["snippet"]
        print(f"✅ 댓글 수정 완료 | 작성자: {snippet['authorDisplayName']} | 수정 시각: {snippet['updatedAt']}")
        return {"comment_id": res["id"], "new_text": snippet["textDisplay"]}
    except HttpError as e:
        print(f"[오류] update_comment ({e.status_code}): {e.reason}")
        print(json.dumps(json.loads(e.content.decode()), indent=2, ensure_ascii=False))
        return None

# ── 체스판 렌더링 ──────────────────────────────────────────────────────────────

PIECE_MAP = {
    "r": "💂🏿", "n": "🐴", "b": "🕵🏿‍♂", "q": "👸🏿", "k": "🤴🏿", "p": "🧑🏿‍🌾",
    "R": "💂‍♂",  "N": "🦄", "B": "🕵‍♂",  "Q": "👸🏻", "K": "🤴🏻", "P": "🧑🏻‍🌾",
}

def render_board(board: chess.Board) -> str:
    rows = ["/// a   b   c    d    e   f    g    h"]
    for rank in range(8, 0, -1):
        line = f"{rank} "
        for file in range(8):
            piece = board.piece_at(chess.square(file, rank - 1))
            line += PIECE_MAP[piece.symbol()] if piece else ("⬜" if (file + rank) % 2 == 0 else "⬛")
        rows.append(line)
    return "\n".join(rows)

# ── 체스 로직 ──────────────────────────────────────────────────────────────────

def apply_move(replies: list[str]) -> dict:
    """
    좋아요 순 대댓글에서 합법적인 첫 번째 수를 찾아 실행합니다.
    백 수 → 엔진(흑) 응수 순으로 진행합니다.
    """
    for raw in replies:
        move_str = raw.strip().strip("[]")
        try:
            move = game_board.parse_san(move_str)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            continue

        if move not in game_board.legal_moves:
            continue

        white_san = game_board.san(move)
        game_board.push(move)

        if game_board.is_game_over():
            return {"white": white_san, "black": None,
                    "result": game_board.result(), "reason": str(game_board.outcome().termination)}

        result    = engine.play(game_board, chess.engine.Limit(time=0.1))
        black_san = game_board.san(result.move)
        game_board.push(result.move)

        if game_board.is_game_over():
            return {"white": white_san, "black": black_san,
                    "result": game_board.result(), "reason": str(game_board.outcome().termination)}

        return {"white": white_san, "black": black_san, "result": None}

    return {"error": "no_legal_move"}

# ── 메인 작업 ──────────────────────────────────────────────────────────────────

def run_job(pinned: dict):
    print(f"\n==== 실행 ({datetime.now().strftime('%H:%M:%S')}) ====")

    replies = get_replies(pinned["thread_id"])
    print("후보:", replies)

    move = apply_move(replies)
    if "error" in move:
        print("합법적인 수 없음")
        return

    print(f"백: {move['white']}  |  흑: {move['black']}")

    record = load_record()

    if move.get("result"):
        result = move["result"]
        if result == "1-0":
            winner_label = "백(댓글)"
            record["white"] += 1
        elif result == "0-1":
            winner_label = "흑(AI)"
            record["black"] += 1
        else:
            winner_label = "무승부"
            record["draw"] += 1

        save_record(record)
        result_text = f"이전 판 결과: {winner_label} 승 ({move['reason']})"
        print(f"🎯 종료: {result_text}")

        game_board.reset()
        board_text = render_board(game_board)
        update_comment(pinned["comment_id"],
                       f"{result_text}\n새 게임 시작!\n\n{board_text}\n\n{record_line(record)}\n\n규칙과 기보법은 영상 설명란을 참조해 주세요.")
        return

    board_text = render_board(game_board)
    update_comment(pinned["comment_id"],
                   f"직전 수 - 백: {move['white']} | 흑: {move['black']}\n\n{board_text}\n\n{record_line(record)}\n\n규칙과 기보법은 영상 설명란을 참조해 주세요.")

# ── 진입점 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("체스 봇 시작")

    pinned = get_pinned_comment(VIDEO_ID)
    if not pinned:
        print("댓글 없음 — 종료")
        engine.quit()
        raise SystemExit(1)

    if pinned["reply_count"] == 0:
        print("대댓글 없음")

    record = load_record()
    update_comment(pinned["comment_id"],
                   f"{render_board(game_board)}\n\n{record_line(record)}")

    def seconds_to_next_10min() -> float:
        """다음 정각 10분 경계까지 남은 초를 반환합니다. (예: 1:03 → 1:10까지 420초)"""
        now = datetime.now()
        next_tick = now.replace(second=0, microsecond=0)
        next_tick += timedelta(minutes=10 - now.minute % 10)
        return (next_tick - now).total_seconds()

    try:
        while True:
            wait = seconds_to_next_10min()
            print(f"다음 실행까지 {wait:.0f}초 대기...")
            time.sleep(wait)
            run_job(pinned)
    except KeyboardInterrupt:
        print("\n봇 종료 중...")
        engine.quit()