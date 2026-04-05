import sys
import os
from sqlalchemy import create_engine, text
from pathlib import Path

# 1. DB 파일 위치 찾기 (자네가 보여준 코드 로직 반영)
# 현재 폴더(D:\AI_Project)를 기준으로 DB 파일을 찾는다.
current_dir = Path(os.getcwd())

# 예상되는 DB 파일 경로들 (루트 혹은 data 폴더)
candidates = [
    current_dir / "aventurine_v3.db",
    current_dir / "data" / "runtime" / "aventurine_v3.db",
    current_dir / "data" / "aventurine_v3.db",
    current_dir / "core" / "mellow_link" / "data" / "aventurine_v3.db",
    current_dir / "mellow_link" / "data" / "aventurine_v3.db",
]

db_path = None
for path in candidates:
    if path.exists():
        db_path = path
        break

if not db_path:
    print("❌ 'aventurine_v3.db' 파일을 찾을 수 없습니다!")
    print(f"   검색한 경로: {[str(p) for p in candidates]}")
    # 혹시 모르니 강제로 생성할지 묻지 않고 종료 (안전제일)
    sys.exit(1)

print(f"✅ 데이터베이스 파일 발견: {db_path}")

# 2. 엔진 수동 가동 (설정 파일 필요 없음)
# SQLite URL 생성
database_url = f"sqlite:///{db_path}"
engine = create_engine(database_url)

def promote_user(username):
    print(f"\n🔍 사용자 '{username}' 조회 중...")
    
    with engine.connect() as connection:
        # 1. 유저 확인
        # (SQLAlchemy 버전에 따라 text() 사용 필수)
        result = connection.execute(text("SELECT id, role FROM users WHERE username = :name"), {"name": username}).fetchone()
        
        if not result:
            print(f"❌ 사용자 '{username}'이(가) DB에 없습니다.")
            return

        user_id, current_role = result
        print(f"   - 현재 등급: {current_role}")

        # 2. 승격
        if current_role != "admin":
            print(f"⚡ 등급 변경 시도: '{username}' -> 'admin'")
            connection.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": user_id})
            connection.commit()
            print("✅ 승격 성공! 이제 런처를 재시동하고 로그인해보세요.")
        else:
            print("ℹ️  이미 관리자(Admin)입니다.")

if __name__ == "__main__":
    target_user = input("관리자로 만들 아이디 입력: ").strip()
    if target_user:
        promote_user(target_user)
    else:
        print("❌ 아이디를 입력해주세요.")
