// =========================
// Authentication Module
// =========================

// =========================
// Guest Access Gate
// =========================

/**
 * Check if user has valid access and show gate if not
 * Called on page load before any UI is shown
 */
async function checkAccessGate() {
    const token = localStorage.getItem('auth_token');

    if (!token) {
        // No token - show access gate
        showGuestAccessModal();
        return false;
    }

    // Token exists - verify it's still valid
    try {
        const res = await fetch(`${API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (res.ok) {
            // Token valid - hide gate and continue
            hideGuestAccessModal();
            return true;
        } else {
            // Token invalid/expired - show access gate
            localStorage.removeItem('auth_token');
            AUTH_TOKEN = null;
            showGuestAccessModal();
            return false;
        }
    } catch (e) {
        console.error('Auth check failed:', e);
        // Network error - show access gate
        showGuestAccessModal();
        return false;
    }
}

/**
 * Show the guest access modal (non-closable)
 */
function showGuestAccessModal() {
    document.getElementById('guestAccessModal').style.display = 'flex';
    document.getElementById('guestAccessCode').focus();
    // Hide error on show
    document.getElementById('guestAccessError').classList.add('hidden');
}

/**
 * Hide the guest access modal
 */
function hideGuestAccessModal() {
    document.getElementById('guestAccessModal').style.display = 'none';
}

/**
 * Submit guest access code
 */
// ✅ auth.js 내의 submitGuestAccess 함수를 이걸로 교체하게
async function submitGuestAccess() {
    // 1. HTML에 정의된 정확한 ID인 'guestAccessCode'를 사용해야 하네!
    const codeInput = document.getElementById('guestAccessCode'); 
    const errorDiv = document.getElementById('guestAccessError');
    const btn = document.getElementById('guestAccessBtn');

    if (!codeInput) {
        console.error("ID가 'guestAccessCode'인 요소를 찾을 수 없군!");
        return;
    }

    const accessCode = codeInput.value.trim();

    if (!accessCode) {
        showNotification("코드를 입력해야 판에 낄 수 있지, 파트너.", "error");
        return;
    }

    // 로딩 상태 표시
    btn.disabled = true;
    
    try {
        const res = await fetch(`/auth/guest-login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ access_code: accessCode })
        });

        if (res.ok) {
            const data = await res.json();
            localStorage.setItem('auth_token', data.access_token);
            window.location.reload(); // ✅ 성공 시 리로드해서 입장!
        } else {
            // 서버에서 반환한 detail 메시지 추출
            let errorMessage = "유효하지 않은 초대권입니다";
            try {
                const errorData = await res.json();
                if (errorData.detail) {
                    errorMessage = errorData.detail;
                }
            } catch (jsonErr) {
                console.warn('Could not parse error response:', jsonErr);
            }

            // 에러 메시지 표시
            showNotification(errorMessage, "error");
            // errorDiv에도 표시
            if (errorDiv) {
                errorDiv.textContent = errorMessage;
                errorDiv.classList.remove('hidden');
            }
            codeInput.value = '';
            codeInput.focus();
        }
    } catch (e) {
        console.error('Guest login error:', e);
        showNotification("네트워크 오류가 발생했습니다", "error");
    } finally {
        btn.disabled = false;
    }
}

/**
 * Switch from guest modal to login modal
 */
function showLoginFromGuestModal() {
    hideGuestAccessModal();
    showLoginModal();
}

// =========================
// Standard Authentication
// =========================

/**
 * 인증 확인 및 UI 업데이트
 */
async function checkAuth() {
  try {
      const res = await fetch(`${API_BASE}/auth/me`, {headers:{'Authorization':`Bearer ${AUTH_TOKEN}`}});
      if(res.ok) {
          CURRENT_USER = await res.json();
          IS_GUEST_MODE = false;
          document.getElementById('authButtons').style.display='none';
          document.getElementById('userInfo').style.display='flex';
          document.getElementById('username').textContent=CURRENT_USER.username;
          document.getElementById('guestBadge').style.display='none';
          document.getElementById('foldersSection').style.display='block';
          document.getElementById('uncategorizedSection').style.display='block';
          loadFolders(); loadUncategorizedSessions();
          
          // Mellow-Link 초기화 (Admin 체크 포함)
          if (typeof initMellowLink === 'function') {
              await initMellowLink();
          }
      } else softAuthExpireToGuest();
  } catch { softAuthExpireToGuest(); }
}


function showAuthWarning(msg) {
  // 너네 UI 구조에 맞춰 최소 침습: statusText 있으면 거기 찍고,
  // 없으면 alert 말고 상단바/토스트로 나중에 교체 가능
  const el = document.getElementById('statusText');
  if (el) {
    el.textContent = `⚠️ ${msg}`;
    el.classList.add('text-yellow-400');
    setTimeout(() => {
      el.textContent = 'Ready';
      el.classList.remove('text-yellow-400');
    }, 5000);
  }
}

function switchToGuestUI() {
  // "토큰 삭제" 같은 폭력 금지. UI만 게스트로.
  IS_GUEST_MODE = true;
  CURRENT_USER = null;

  document.getElementById('authButtons').style.display = 'flex';
  document.getElementById('userInfo').style.display = 'none';
  document.getElementById('guestBadge').style.display = 'inline-block';
  document.getElementById('foldersSection').style.display = 'none';
  document.getElementById('uncategorizedSection').style.display = 'none';
}

function softAuthExpireToGuest(msg) {
  // ✅ 자동 로그아웃 체감 방지 포인트:
  // - localStorage auth_token은 지우지 않는다 (사용자 의사 없이 삭제 금지)
  // - 런타임 AUTH_TOKEN은 null로 만들어서 이후 API 폭탄(401 연쇄)만 막는다
  AUTH_TOKEN = null;

  switchToGuestUI();
  showAuthWarning(msg || '세션이 만료되어 게스트로 전환했어. 다시 로그인하면 돼.');
}

/**
 * 모달 열기/닫기
 */
function showLoginModal() {
    document.getElementById('loginModal').style.display = 'flex';
}

function showRegisterModal() {
    document.getElementById('registerModal').style.display = 'flex';
}

// 확실하게 판을 갈아주는 '스위칭' 함수일세
function switchToRegister() {
    console.log("Switching to Register...");
    
    // 1. 로그인 창을 먼저 확실히 닫고
    const loginM = document.getElementById('loginModal');
    if (loginM) loginM.style.display = 'none';
    
    // 2. 아주 찰나의 시간(50ms) 뒤에 회원가입 창을 띄우게나
    setTimeout(() => {
        const regM = document.getElementById('registerModal');
        if (regM) {
            regM.style.display = 'flex';
            console.log("Register Modal opened!");
        } else {
            console.error("registerModal을 찾을 수 없네, 파트너!");
        }
    }, 50);
}

// ✅ 기존 기능을 보강한 모달 닫기 로직
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }

    // 🎲 로그인/회원가입 창을 닫았는데 인증되지 않았다면 → 게스트 액세스 모달로 복귀
    // AUTH_TOKEN 체크 (state.isAuthenticated는 존재하지 않음)
    const isAuthenticated = !!AUTH_TOKEN || !!localStorage.getItem('auth_token');

    if ((modalId === 'loginModal' || modalId === 'registerModal') && !isAuthenticated) {
        console.log('[Auth] Modal closed without authentication, showing guest access gate');
        showGuestAccessModal();
    }
}

/**
 * 로그인
 */
async function login() {
    const u = document.getElementById('loginUsername').value.trim();
    const p = document.getElementById('loginPassword').value;
    const errorDiv = document.getElementById('loginError');
    const btn = document.querySelector('#loginModal button[type="submit"], #loginModal .btn-primary');

    // 에러 표시 헬퍼 함수
    const showLoginError = (msg) => {
        showNotification(msg, "error");
        if (errorDiv) {
            errorDiv.textContent = msg;
            errorDiv.classList.remove('hidden');
        }
    };

    // 입력값 검증
    if (!u || !p) {
        showLoginError('사용자명과 비밀번호를 모두 입력해주세요.');
        return;
    }

    // 버튼 비활성화
    if (btn) btn.disabled = true;

    try {
        const fd = new FormData();
        fd.append('username', u);
        fd.append('password', p);

        const res = await fetch(`${API_BASE}/auth/token`, {
            method: 'POST',
            body: fd
        });

        if (res.ok) {
            const d = await res.json();
            AUTH_TOKEN = d.access_token;
            localStorage.setItem('auth_token', AUTH_TOKEN);
            closeModal('loginModal');
            hideGuestAccessModal(); // Hide guest modal if open
            // Reload to ensure clean state
            window.location.reload();
        } else {
            // 서버에서 반환한 detail 메시지 추출
            let errorMessage = 'ID 또는 비밀번호가 올바르지 않습니다.';
            try {
                const errorData = await res.json();
                if (errorData.detail) {
                    errorMessage = errorData.detail;
                } else if (errorData.message) {
                    errorMessage = errorData.message;
                }
            } catch (jsonErr) {
                console.warn('Could not parse error response:', jsonErr);
            }
            showLoginError(errorMessage);
            // 비밀번호 입력란 초기화
            document.getElementById('loginPassword').value = '';
            document.getElementById('loginPassword').focus();
        }
    } catch (error) {
        console.error('Login error:', error);
        showLoginError('네트워크 오류가 발생했습니다. 다시 시도해주세요.');
    } finally {
        if (btn) btn.disabled = false;
    }
}

/**
 * 회원가입
 */
async function register() {
    const u = document.getElementById('registerUsername').value.trim();
    const p = document.getElementById('registerPassword').value;
    const errorDiv = document.getElementById('registerError');
    const btn = document.querySelector('#registerModal button[type="submit"], #registerModal .btn-primary');

    // 에러 표시 헬퍼 함수
    const showRegisterError = (msg) => {
        showNotification(msg, "error");
        if (errorDiv) {
            errorDiv.textContent = msg;
            errorDiv.classList.remove('hidden');
        }
    };

    // 입력값 검증
    if (!u || !p) {
        showRegisterError('사용자명과 비밀번호를 모두 입력해주세요.');
        return;
    }

    // 비밀번호 길이 검증 (bcrypt 72바이트 제한)
    if (p.length > 72) {
        showRegisterError('비밀번호가 너무 깁니다 (최대 72자)');
        return;
    }

    // 버튼 비활성화
    if (btn) btn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: u, password: p })
        });

        if (res.ok) {
            const d = await res.json();
            AUTH_TOKEN = d.access_token;
            localStorage.setItem('auth_token', AUTH_TOKEN);
            closeModal('registerModal');
            hideGuestAccessModal(); // Hide guest modal if open
            // Reload to ensure clean state
            window.location.reload();
        } else {
            // 서버에서 반환한 detail 메시지 추출
            let errorMessage = '회원가입에 실패했습니다.';
            try {
                const errorData = await res.json();
                if (errorData.detail) {
                    errorMessage = errorData.detail;
                } else if (errorData.message) {
                    errorMessage = errorData.message;
                }
            } catch (jsonErr) {
                console.warn('Could not parse error response:', jsonErr);
            }
            showRegisterError(errorMessage);
        }
    } catch (error) {
        console.error('Register error:', error);
        showRegisterError('네트워크 오류가 발생했습니다. 다시 시도해주세요.');
    } finally {
        if (btn) btn.disabled = false;
    }
}

/**
 * 로그아웃
 */
function logout() {
    console.log('👋 [Logout] Cashing out and leaving...');

    // 1. 보안 토큰 파기 (가장 중요)
    AUTH_TOKEN = null;
    localStorage.removeItem('auth_token');

    // 2. 세션 변수 초기화 (혹시 모를 잔여 데이터 제거)
    CURRENT_SESSION_ID = null;
    CURRENT_FOLDER_ID = null;

    // 3. 💎 [핵심] 입구로 강제 이동 (Redirect)
    // ✅ 경로 통일: /ui (FastAPI 엔드포인트와 일치)
    // window.location.replace를 사용하여 뒤로가기로 복귀 방지
    window.location.replace('/ui');
}
