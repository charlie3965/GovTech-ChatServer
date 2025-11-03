# app/main.py
import os
import openai
from fastapi import FastAPI, Request, HTTPException, status
from pydantic import BaseModel
from typing import Any, Dict
from dotenv import load_dotenv

load_dotenv()

# 환경변수에서 키 불러오기
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("환경변수 OPENAI_API_KEY가 설정되어야 합니다")

openai.api_key = OPENAI_API_KEY

app = FastAPI(title="Kakao Skill + OpenAI 챗봇 서버")

# 스킬 요청 payload 모델 (필요한 필드만 단순화)
class SkillRequest(BaseModel):
    intent: Dict[str, Any] = None
    userRequest: Dict[str, Any]
    action: Dict[str, Any] = None
    bot: Dict[str, Any] = None
    # 기타 필드(예: params, detailParams 등) 필요시 추가 가능

# 응답 생성 함수: 카카오 스킬 서버 응답 포맷
def make_kakao_skill_response(text: str) -> Dict[str, Any]:
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": text
                    }
                }
            ]
        }
    }

# OpenAI 채팅 호출 함수
async def call_openai_chat(user_name: str, user_input: str) -> str:
    # system 메시지 등으로 역할을 지정할 수 있음
    prompt_messages = [
        {"role": "system", "content": "당신은 친절한 고객응대 챗봇입니다."},
        {"role": "user", "content": f"{user_name}님이 질문하셨습니다: {user_input}"}
    ]
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=prompt_messages,
            max_tokens=500,
            n=1,
            temperature=0.7
        )
        answer = response.choices[0].message.content.strip()
        return answer
    except Exception as e:
        raise RuntimeError(f"OpenAI API 호출 중 오류 발생: {e}")

@app.post("/skill")
async def skill_handler(req: SkillRequest):
    # 사용자 이름 획득 시도: userRequest 내 profile 또는 user 정보 내
    user_name = None
    try:
        # 예시: userRequest.user.profile.nickname
        user_name = req.userRequest.get("user", {}).get("profile", {}).get("nickname")
        user_id = req.userRequest.get("user", {}).get("id", "unknown_id")
    except Exception:
        user_name = None

    if not user_name:
        # 기본 이름 설정
        user_name = "박현"

    # 사용자의 발화문
    try:
        user_utterance = req.userRequest.get("utterance")
        if not user_utterance:
            user_utterance = req.userRequest.get("user", {}).get("text", "")
    except Exception:
        user_utterance = ""

    if not user_utterance:
        # 빈 발화이면 단순 안내 메시지
        return make_kakao_skill_response(f"{user_name}님, 무엇을 도와드릴까요?")

    # OpenAI 호출해서 답변 얻기
    try:
        reply = await call_openai_chat(user_name, user_utterance)
    except RuntimeError as e:
        # 내부오류 시 사용자에게 안내
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 사용자 이름 포함해서 응답 문구 구성
    final_text = f"{user_id}님, {reply}"

    # 응답 생성 및 반환
    return make_kakao_skill_response(final_text)

@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Kakao Skill 서버가 정상 작동 중입니다."}
