// =========================
// Global State Variables
// =========================

// Authentication
let AUTH_TOKEN = localStorage.getItem('auth_token') || null; //✅ [P0] 인증 토큰
let CURRENT_USER = null; //✅ [P0] 현재 사용자 정보
let IS_GUEST_MODE = false; //✅ [P0] 게스트 모드 상태

// Session & Folder
let CURRENT_SESSION_ID = null; //✅ [P0] 현재 세션 ID
let CURRENT_FOLDER_ID = null; //✅ [P0] 현재 폴더 ID
let CURRENT_FOLDER = null; //✅ [P0] 현재 폴더 정보
let TEMP_SESSION_ID = null; //✅ [P0] 임시 세션 ID
let FOLDERS = []; //✅ [P0] 폴더 목록

// UI State
let SIDEBAR_COLLAPSED = false; //✅ [P0] 사이드바 상태
let CURRENT_MODE = "auto"; //✅ [P0] 현재 모드

// Generation State
let abortController = null;  //✅ [P0] 중단 컨트롤러 (Managed by api.js)
let isGenerating = false; //✅ [P0] 생성 중복 클릭 방지
let isRegenerating = false; //✅ [P0] Regenerate 중복 클릭 방지
let requestStartTime = 0; //✅ [P0] 전송 시작 시간 기록용 (서버가 시간 안 줄 경우 대비)

// Edit State
let EDIT_STATE = { active: false, targetMessageId: null, originalText: "" }; //✅ [P0] 편집 상태
let isEditMode = false; //✅ [P0] 편집 모드 상태
let editWarningBar = null; //✅ [P0] 편집 경고 바

// Answer Management
let answerArchive = {};  // ✅ [P0] 답변 아카이브 { messageId: { content, metadata, timestamp } }
let answerVersions = {}; //✅ [P0] 답변 버전 관리 { originMid: { index: 0, items: [...], prompt: "원본 user 질문" } }

// Loop Detection
let loopDetectionBuffer = ""; //✅ [P0] 반복 감지 버퍼
let loopDetectionThreshold = 50; //✅ [P0] 반복 감지 임계값

// state.js
window.AUTH_TOKEN = localStorage.getItem('auth_token') || null; //✅ [P0] 인증 토큰 저장
window.CURRENT_USER = null; //✅ [P0] 현재 사용자 정보
window.CURRENT_SESSION_ID = null; //✅ [P0] 현재 세션 ID
window.CURRENT_FOLDER_ID = null; //✅ [P0] 현재 폴더 ID
window.CURRENT_FOLDER = null; //✅ [P0] 현재 폴더 정보
window.TEMP_SESSION_ID = null; //✅ [P0] 임시 세션 ID
window.FOLDERS = []; //✅ [P0] 폴더 목록
window.IS_GUEST_MODE = false; //✅ [P0] 게스트 모드 상태
window.SIDEBAR_COLLAPSED = false; //✅ [P0] 사이드바 상태
window.CURRENT_MODE = "auto"; //✅ [P0] 현재 모드
window.abortController = null; //✅ [P0] 중단 컨트롤러
window.isGenerating = false; //✅ [P0] 생성 중복 클릭 방지
window.isRegenerating = false; //✅ [P0] Regenerate 중복 클릭 방지
window.requestStartTime = 0; //✅ [P0] 요청 시작 시간 추적
window.answerArchive = {}; //✅ [P0] 답변 아카이브
window.answerVersions = {}; //✅ [P0] 답변 버전 관리
window.loopDetectionBuffer = ""; //✅ [P0] 반복 감지 버퍼
window.loopDetectionThreshold = 3; //✅ [P0] 반복 감지 임계값 (동일 문구 3회 반복 시 중단)
// ✅ [강제 초기화] EDIT_CONTEXT 완전 구조 보장
if (!window.EDIT_CONTEXT || typeof window.EDIT_CONTEXT !== 'object') {
  window.EDIT_CONTEXT = {};
}
window.EDIT_CONTEXT = Object.assign({
    active: false,
    originMessageId: null,     // 수정 대상(유저 메시지 id)
    originText: "",            // 수정 시작 시 원문
    draftBeforeEdit: "",       // 수정 시작 직전 입력창에 쓰던 내용(원복용)
    // ✅ [복원 기능] 백업 스냅샷 (편집 확정 후 복원용)
    backupMessages: [],        // 삭제된 메시지 백업 (서버 형식 그대로)
    backupSessionId: null,     // 백업 시점 세션 ID
    backupFolderId: null,      // 백업 시점 폴더 ID
    backupCreatedAt: null,     // 백업 생성 시각
    canRestore: false          // 복원 가능 여부
  }, window.EDIT_CONTEXT || {});
window.isEditMode = false; //✅ [P0] 편집 모드 상태
window.editWarningBar = null; //✅ [P0] 편집 경고 바
window.API_BASE = window.location.origin; //✅ [P0] API 기본 URL

// =========================
// VRAM Monitoring State
// =========================
window.VRAM_STATUS = {
    used: 0,
    total: 0,
    percent: 0,
    lastUpdate: null
};
window.VRAM_POLL_INTERVAL = null; // 5초 간격 폴링 타이머

// =========================
// Image Generation State
// =========================
window.IMAGE_GENERATION_PENDING = false; // 이미지 생성 대기 상태

// =========================
// Mellow-Link State
// =========================
window.MELLOW_LINK_EXPANDED = true; // Mellow-Link section expanded state
window.AVATAR_STATUS = {
    connected: false,
    port_active: false,
    relay_connected: false,
    last_check: null
};
window.SECRETARY_FOLDER_ID = null; // Secretary folder ID for admin users
window.IS_ADMIN = false; // Admin status
