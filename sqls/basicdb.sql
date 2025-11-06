-- 데이터베이스 생성
CREATE DATABASE policyharbor;
-- 데이터베이스 사용
USE policyharbor;

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(100) PRIMARY KEY COMMENT '카카오 user_id 등 사용자 고유 식별자',
    name VARCHAR(50) NOT NULL COMMENT '사용자 이름',
    business_size VARCHAR(50) NOT NULL COMMENT '사업 규모 (예: 소상공인, 중소기업 등)',
    context_summary TEXT NULL COMMENT '누적된 대화의 요약 내용',
    flag BOOLEAN NOT NULL DEFAULT FALSE COMMENT '범용 boolean',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '레코드 생성 시각',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '최근 수정 시각'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
