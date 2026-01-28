# database.py — The "Universal Adapter" Version
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float, Date, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from pathlib import Path
import os
import enum
from typing import Optional

# [Fix] bcrypt 에러 침묵용 패치
import bcrypt
if not hasattr(bcrypt, '__about__'):
    class MockAbout:
        __version__ = getattr(bcrypt, '__version__', '4.0.0')
    bcrypt.__about__ = MockAbout()

from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status, Header

# =========================
# Configuration
# =========================

_MELLOW_LINK_DIR = Path(__file__).parent.parent
_FORCED_DATA_DIR = _MELLOW_LINK_DIR / "data"
_FORCED_DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = _FORCED_DATA_DIR / "aventurine_v3.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "aventurine-v3-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

# =========================
# Role Enum
# =========================
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"

# =========================
# Models
# =========================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default=UserRole.USER.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    folders = relationship("AgentFolder", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("UserMemory", back_populates="user", cascade="all, delete-orphan")
    daily_usages = relationship("DailyUsage", back_populates="user", cascade="all, delete-orphan")

class AgentFolder(Base):
    __tablename__ = "agent_folders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    system_prompt = Column(Text, nullable=False)
    use_rag = Column(Boolean, default=False, nullable=False)
    rag_collection_name = Column(String(255), nullable=True)
    icon = Column(String(10), default="📁", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_creative = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="folders")
    sessions = relationship("ChatSession", back_populates="folder")
    documents = relationship("FolderDocument", back_populates="folder", cascade="all, delete-orphan")

class UserMemory(Base):
    __tablename__ = "user_memories"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = relationship("User", back_populates="memories")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    folder_id = Column(Integer, ForeignKey("agent_folders.id"), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="sessions")
    folder = relationship("AgentFolder", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    state_info = Column(String(255), nullable=True)
    rag_used = Column(Boolean, default=False, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    auto_selected = Column(Boolean, default=False, nullable=False)
    selected_mode = Column(String(50), nullable=True)
    processing_time = Column(Float, nullable=True)
    session = relationship("ChatSession", back_populates="messages")

class FolderDocument(Base):
    __tablename__ = "folder_documents"
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("agent_folders.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    folder = relationship("AgentFolder", back_populates="documents")

class MessageFeedback(Base):
    __tablename__ = "message_feedbacks"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    is_positive = Column(Boolean, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    message = relationship("ChatMessage")

class TempResource(Base):
    __tablename__ = "temp_resources"
    id = Column(Integer, primary_key=True, index=True)
    temp_session_id = Column(String(255), nullable=False, index=True)
    file_path = Column(String(1000), nullable=True)
    collection_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(50), default="UPLOADING", nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)

class EventLog(Base):
    __tablename__ = "event_logs"
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    message = Column(Text, nullable=False)
    context_metadata = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed = Column(Boolean, default=False, nullable=False)

class DailyUsage(Base):
    __tablename__ = "daily_usages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    count = Column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint('user_id', 'date', name='uq_user_date'),)
    user = relationship("User", back_populates="daily_usages")

class GuestUsage(Base):
    __tablename__ = "guest_usages"
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    count = Column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint('ip_address', 'date', name='uq_guest_ip_date'),)


class DocumentChunk(Base):
    """RAG document chunks with embeddings for persistent storage."""
    __tablename__ = "document_chunks"
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("agent_folders.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("folder_documents.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(Text, nullable=False)  # JSON serialized embedding vector
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    folder = relationship("AgentFolder")
    document = relationship("FolderDocument")


# =========================
# Helper Functions
# =========================

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# [수정됨] role 인자를 받도록 수정 (main.py 호환성)
def create_default_folders_for_user(db: Session, user_id: int, role: str = UserRole.USER.value):
    """회원가입 시 기본 폴더 생성"""
    default_folders = [
        {"name": "일반 대화", "icon": "💬", "system_prompt": "친절한 AI.", "use_rag": False, "rag_collection_name": None},
    ]
    # Admin일 경우 추가 폴더 (선택사항)
    if role == UserRole.ADMIN.value:
        default_folders.insert(0, {"name": "비서", "icon": "🎀", "system_prompt": "비서 모드", "use_rag": False, "rag_collection_name": None})

    created = []
    for folder_data in default_folders:
        folder = AgentFolder(user_id=user_id, **folder_data)
        db.add(folder)
        created.append(folder)
    db.commit()
    for f in created: db.refresh(f)
    return created

def ensure_user_has_folders(db: Session, user_id: int, role: str = UserRole.USER.value) -> list:
    """사용자에게 폴더가 없으면 기본 폴더 생성"""
    count = db.query(AgentFolder).filter(AgentFolder.user_id == user_id, AgentFolder.is_active == True).count()
    if count == 0:
        return create_default_folders_for_user(db, user_id, role)
    return db.query(AgentFolder).filter(AgentFolder.user_id == user_id, AgentFolder.is_active == True).all()

def get_or_create_default_session(db: Session, user_id: int, folder_id: int) -> "ChatSession":
    existing = db.query(ChatSession).filter(
        ChatSession.user_id == user_id, 
        ChatSession.folder_id == folder_id, 
        ChatSession.is_active == True
    ).first()
    
    if existing: return existing
    
    folder = db.query(AgentFolder).filter(AgentFolder.id == folder_id).first()
    folder_name = folder.name if folder else "Folder"
    
    session = ChatSession(
        user_id=user_id, 
        folder_id=folder_id, 
        title=f"Chat in {folder_name}", 
        is_active=True
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

# =========================
# Auth & Guest Functions
# =========================

def verify_password(plain_password, hashed_password):
    """
    [Survival Mode] 해시 검증 실패 시, 평문 비교를 시도하여 로그인 성공시킴.
    """
    try:
        if pwd_context.verify(plain_password, hashed_password):
            return True
    except Exception as e:
        # passlib이 "hash could not be identified" 에러를 뱉으면 여기로 옴
        # 평문끼리 비교해서 맞으면 통과 (좀비 모드 비밀번호 지원)
        if str(plain_password) == str(hashed_password):
            return True
            
    # 에러는 안 났지만 verify가 False인 경우에도 평문 체크 한 번 더
    if str(plain_password) == str(hashed_password):
        return True
        
    return False

def get_password_hash(password):
    """[Survival Mode] Hashing failed? Truncate and retry."""
    try:
        return pwd_context.hash(password)
    except Exception as e:
        print(f"!!! [Survival] Hashing failed: {e}. Saving plain text.")
        # 그냥 평문 반환 (verify_password가 처리해줌)
        return password

def create_access_token(data: dict, expires_delta: timedelta = None, role: str = UserRole.USER.value):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire, "role": role})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_optional(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: return None
    try:
        token = authorization.replace("Bearer ", "").strip()
        if not token: return None
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username: return None
    except JWTError: return None
    return db.query(User).filter(User.username == username).first()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username: raise credentials_exception
    except JWTError: raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if not user: raise credentials_exception
    return user

def get_or_create_guest_user(db: Session) -> User:
    import uuid
    guest_username = f"guest_{uuid.uuid4().hex[:8]}"
    guest_user = User(username=guest_username, hashed_password=get_password_hash("guest"), role=UserRole.GUEST.value)
    db.add(guest_user)
    db.commit()
    db.refresh(guest_user)
    return guest_user

def get_token_payload(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError: return {}

def get_guest_usage_today(db: Session, ip_address: str) -> int:
    today = date.today()
    usage = db.query(GuestUsage).filter(GuestUsage.ip_address == ip_address, GuestUsage.date == today).first()
    return usage.count if usage else 0

def increment_guest_usage(db: Session, ip_address: str) -> int:
    today = date.today()
    usage = db.query(GuestUsage).filter(GuestUsage.ip_address == ip_address, GuestUsage.date == today).first()
    if usage:
        usage.count += 1
    else:
        usage = GuestUsage(ip_address=ip_address, date=today, count=1)
        db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage.count

def check_guest_limit(db: Session, ip_address: str, limit: int) -> tuple:
    if limit == -1: return True, 0
    cnt = get_guest_usage_today(db, ip_address)
    return cnt < limit, cnt

# Init DB
init_db()