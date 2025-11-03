# app/main.py
import os
import openai
import redis
from fastapi import FastAPI, Request, HTTPException, status
from pydantic import BaseModel
from typing import Any, Dict, List
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import json
import asyncio

load_dotenv()

# 환경 변수 로드
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MYSQL_URL = os.getenv("MYSQL_URL", "mysql+pymysql://root:password@localhost:3306/chatbot_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

if not OPENAI_API_KEY:
    raise RuntimeError("환경변수 OPENAI_API_KEY가 설정되어야 합니다")

openai.api_key = OPENAI_API_KEY

# FastAPI 앱 생성
app = FastAPI(title="Kakao Skill + OpenAI 챗봇 서버 with DB & Redis")

# -----------------------------
# MySQL 설정
# -----------------------------
Base = declarative_base()
engine = create_engine(MYSQL_URL, echo=False, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class User(Base):
    __tablename__ = "users"
    id = Column(String(100), primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    business_size = Column(String(50), nullable=False)


Base.metadata.create_all(bind=engine)


# -----------------------------
# Redis 설정
# -----------------------------
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# -----------------------------
# Kakao 스킬 요청 모델
# -----------------------------
class SkillRequest(BaseModel):
    intent: Dict[str, Any] = None
    userRequest: Dict[str, Any]
    action: Dict[str, Any] = None
    bot: Dict[str, Any] = None


# -----------------------------
# 응답 생성 함수
# -----------------------------
def make_kakao_skill_response(text: str) -> Dict[str, Any]:
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }


# -----------------------------
# Redis 캐시 도우미 함수
# -----------------------------
def get_user_context(user_id: str) -> List[Dict[str, str]]:
    key = f"context:{user_id}"
    context_json = redis_client.get(key)
    if context_json:
        return json.loads(context_json)
    return []


def save_user_context(user_id: str, context: List[Dict[str, str]]):
    key = f"context:{user_id}"
    redis_client.setex(key, 1800, json.dumps(context))  # 30분 TTL


# -----------------------------
# OpenAI API 호출
# -----------------------------
async def call_openai_chat(user_id: str, user_name: str, user_input: str, user_info: Dict[str, Any]) -> str:
    context = get_user_context(user_id)

    # 시스템 프롬프트 구성
    system_prompt = "당신은 친절한 고객응대 챗봇입니다."
    if user_info:
        system_prompt += f"\n이 사용자는 이름이 {user_info['name']}이고, 사업 규모는 {user_info['business_size']}입니다."

    messages = [{"role": "system", "content": system_prompt}]
    messages += context
    messages.append({"role": "user", "content": user_input})

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            n=1,
            temperature=0.7,
        )
        answer = response.choices[0].message.content.strip()

        # context 저장
        context.append({"role": "user", "content": user_input})
        context.append({"role": "assistant", "content": answer})
        save_user_context(user_id, context)

        return answer
    except Exception as e:
        raise RuntimeError(f"OpenAI API 호출 중 오류 발생: {e}")


# -----------------------------
# 사용자 등록 및 정보 확인
# -----------------------------
def get_or_create_user(user_id: str, user_input: str, db):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # 캐시된 등록 진행상태 확인
        reg_state_key = f"register:{user_id}"
        reg_state = redis_client.get(reg_state_key)

        if not reg_state:
            redis_client.setex(reg_state_key, 300, "ask_name")
            return None, "처음 뵙네요! 이름을 알려주세요 😊"

        elif reg_state == "ask_name":
            redis_client.setex(f"temp_name:{user_id}", 300, user_input)
            redis_client.setex(reg_state_key, 300, "ask_business")
            return None, "좋아요! 사업 규모는 어떻게 되시나요? (예: 소상공인, 중소기업 등)"

        elif reg_state == "ask_business":
            temp_name = redis_client.get(f"temp_name:{user_id}")
            if temp_name:
                new_user = User(id=user_id, name=temp_name, business_size=user_input)
                db.add(new_user)
                db.commit()
                redis_client.delete(reg_state_key)
                redis_client.delete(f"temp_name:{user_id}")
                return new_user, f"{temp_name}님, 가입이 완료되었습니다! 😊"
            else:
                redis_client.delete(reg_state_key)
                return None, "다시 시도해주세요."

    return user, None


# -----------------------------
# 메인 스킬 핸들러
# -----------------------------
@app.post("/skill")
async def skill_handler(req: SkillRequest):
    db = SessionLocal()
    try:
        user_id = req.userRequest.get("user", {}).get("id", "unknown_id")
        user_name = req.userRequest.get("user", {}).get("profile", {}).get("nickname", "박현")
        user_utterance = req.userRequest.get("utterance", "")

        if not user_utterance:
            return make_kakao_skill_response(f"{user_name}님, 무엇을 도와드릴까요?")

        user, register_message = get_or_create_user(user_id, user_utterance, db)

        if register_message:
            return make_kakao_skill_response(register_message)

        user_info = {"name": user.name, "business_size": user.business_size}

        reply = await call_openai_chat(user_id, user_name, user_utterance, user_info)

        return make_kakao_skill_response(f"{user_name}님, {reply}")

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    finally:
        db.close()


@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Kakao Skill 서버가 정상 작동 중입니다."}
