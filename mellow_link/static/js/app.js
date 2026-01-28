// =========================
// Application Bootstrap
// =========================

/**
 * 모드 토글
 */
function toggleMode() {
    const btn = document.getElementById('modeToggle');
    const icon = document.getElementById('modeIcon');
    const text = document.getElementById('modeText');

    if (CURRENT_MODE === "auto") {
        CURRENT_MODE = "fast";
        icon.className = "fas fa-bolt"; text.textContent = "Fast";
        btn.style.background = "linear-gradient(135deg, #f59e0b 0%, #f97316 100%)";
        btn.style.borderColor = "#f97316";
    } else if (CURRENT_MODE === "fast") {
        CURRENT_MODE = "thinking";
        icon.className = "fas fa-brain"; text.textContent = "Thinking";
        btn.style.background = "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)";
        btn.style.borderColor = "#8b5cf6";
    } else if (CURRENT_MODE === "thinking") {
        if (IS_GUEST_MODE) {
            CURRENT_MODE = "auto";
            icon.className = "fas fa-robot"; text.textContent = "Auto";
            btn.style.background = "linear-gradient(135deg, #10b981 0%, #059669 100%)";
            btn.style.borderColor = "#059669";
            const st = document.getElementById('statusText');
            st.textContent = "⚠️ Research mode requires login";
            st.classList.add('text-yellow-400');
            setTimeout(() => { st.textContent = 'Ready'; st.classList.remove('text-yellow-400'); }, 2000);
        } else {
            CURRENT_MODE = "research";
            icon.className = "fas fa-microscope"; text.textContent = "Research";
            btn.style.background = "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)";
            btn.style.borderColor = "#2563eb";
        }
    } else {
        CURRENT_MODE = "auto";
        icon.className = "fas fa-robot"; text.textContent = "Auto";
        btn.style.background = "linear-gradient(135deg, #10b981 0%, #059669 100%)";
        btn.style.borderColor = "#059669";
    }
}

/**
 * 파일 업로드 핸들러 (최종 수정본: 세션 ID 강제 발급)
 */
async function handleFileUpload(input) {
    const f = input.files[0]; 
    if (!f) return;

    const fd = new FormData(); 
    fd.append('file', f);

    // [UI] 상태 요소 확보
    const preview = document.getElementById('uploadPreview');
    const spinner = document.getElementById('uploadSpinner');
    const successIcon = document.getElementById('uploadSuccessIcon');
    const statusText = document.getElementById('uploadStatusText');

    // [State: Uploading]
    if (preview) preview.classList.remove('hidden');
    if (spinner) spinner.classList.remove('hidden');
    if (successIcon) successIcon.classList.add('hidden');
    if (statusText) statusText.textContent = '⏳ Uploading...'; 

    // [Logic] URL 설정
    // 혹시 API_BASE가 없을 경우를 대비해 기본값 처리
    const baseUrl = (typeof API_BASE !== 'undefined') ? API_BASE : '';
    const url = `${baseUrl}/chat/upload-temp`;

    // -----------------------------------------------------------
    // 🔑 [Critical Fix] 세션 ID 없으면 즉석 발급 (Deadlock 해결)
    // -----------------------------------------------------------
    let activeSessionId = null;
    
    // 1. 현재 폴더 세션 확인
    if (typeof CURRENT_SESSION_ID !== 'undefined' && CURRENT_SESSION_ID) {
        activeSessionId = CURRENT_SESSION_ID;
    } 
    // 2. 임시 세션 확인
    else if (typeof TEMP_SESSION_ID !== 'undefined' && TEMP_SESSION_ID) {
        activeSessionId = TEMP_SESSION_ID;
    }

    // 3. 둘 다 없으면? -> 여기서 만듦! (타임스탬프 + 난수)
    if (!activeSessionId) {
        activeSessionId = 'temp_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        // 전역 변수에 저장해서 계속 쓰게 만듦
        TEMP_SESSION_ID = activeSessionId;
        window.TEMP_SESSION_ID = activeSessionId;
        console.log("[Upload] 임시 세션 ID 신규 발급:", activeSessionId);
    }

    // 이제 무조건 ID가 있으니 안심하고 첨부
    fd.append('session_id', activeSessionId);
    // -----------------------------------------------------------

    try {
        console.log(`[Upload] Sending to ${url} with session ${activeSessionId}`);
        
        const res = await fetch(url, { method: 'POST', body: fd });

        if (res.ok) { 
            const d = await res.json(); 
            console.log("[Upload] Success:", d);
            // ----------------------------------------------------------------
            // ✅ [FIX] 영수증 동기화: "방금 업로드한 세션이 곧 현재 세션이다"
            // ----------------------------------------------------------------
            if (typeof TEMP_SESSION_ID !== 'undefined') {
                // 서버가 확정해준 ID(d.session_id)가 있으면 쓰고, 없으면 우리가 보낸 거(activeSessionId) 씀
                const usedSessionId = d.session_id || activeSessionId;
                
                TEMP_SESSION_ID = usedSessionId;       // 내부 변수 갱신
                window.TEMP_SESSION_ID = usedSessionId; // 전역 변수(Window) 갱신 (chat.js가 볼 수 있게)
                
                console.log(`[Upload] Temp Session synced to: ${usedSessionId}`);
            }
            // ----------------------------------------------------------------

            // [State: Done]
            if (spinner) spinner.classList.add('hidden');
            if (successIcon) successIcon.classList.remove('hidden');
            if (statusText) statusText.textContent = '✅ Done!'; 
            
        } else {
            // 에러 내용을 확인하기 위해 텍스트로 읽어봄
            const errText = await res.text();
            console.error(`[Upload Error] Status: ${res.status}, Msg: ${errText}`);
            throw new Error(`Server Error: ${res.status}`);
        }
    } catch (e) {
        // [State: Failed]
        console.error(e);
        if (spinner) spinner.classList.add('hidden');
        if (successIcon) successIcon.classList.add('hidden');
        if (statusText) statusText.textContent = '❌ Failed'; 
    }
}

/**
 * 리포트 모달
 */
function showReportModal() {
    document.getElementById('reportModal').style.display = 'flex';
    // 입력 필드 초기화
    document.getElementById('reportCategory').value = 'bug';
    document.getElementById('reportSummary').value = '';
    document.getElementById('reportDetails').value = '';
}


async function submitReport() {
    const category = document.getElementById('reportCategory').value;
    const summary = document.getElementById('reportSummary').value.trim();
    const details = document.getElementById('reportDetails').value.trim();

    // 입력 검증
    if (!summary) {
        alert('Please enter a summary');
        return;
    }

    if (!details) {
        alert('Please enter details');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/chat/report`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(AUTH_TOKEN ? {'Authorization': `Bearer ${AUTH_TOKEN}`} : {})
            },
            body: JSON.stringify({
                category: category,
                summary: summary,
                details: details,
                session_id: CURRENT_SESSION_ID,
                message_id: null  // 필요시 마지막 메시지 ID 추가 가능
            })
        });

        if (response.ok) {
            const result = await response.json();
            alert('✅ Report submitted successfully! Thank you for your feedback.');
            closeModal('reportModal');
        } else {
            const error = await response.json();
            alert(`❌ Failed to submit report: ${error.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Report submission error:', error);
        alert('❌ Network error. Please try again.');
    }
}

// =========================
// Mellow-Link Functions
// =========================

/**
 * Toggle Mellow-Link section expanded/collapsed
 */
function toggleMellowLink() {
    const content = document.getElementById('mellowLinkContent');
    const icon = document.getElementById('mellowLinkIcon');

    MELLOW_LINK_EXPANDED = !MELLOW_LINK_EXPANDED;

    if (MELLOW_LINK_EXPANDED) {
        content.style.display = 'block';
        icon.style.transform = 'rotate(0deg)';
    } else {
        content.style.display = 'none';
        icon.style.transform = 'rotate(-90deg)';
    }
}

/**
 * Refresh avatar status from server
 */
async function refreshAvatarStatus() {
    try {
        const res = await fetch(`${API_BASE}/avatar/status`);
        if (res.ok) {
            const data = await res.json();
            updateAvatarStatusUI(data);
        }
    } catch (e) {
        console.error('[MellowLink] Failed to refresh avatar status:', e);
    }
}

/**
 * Update avatar status UI elements
 */
function updateAvatarStatusUI(data) {
    const dot = document.getElementById('avatarStatusDot');
    const text = document.getElementById('avatarStatusText');
    const launchBtn = document.getElementById('launchAvatarBtn');

    if (!dot || !text) return;

    const isConnected = data?.avatar_service?.port_active || data?.relay?.connected;
    const status = data?.avatar_service?.status || 'not_running';

    AVATAR_STATUS = {
        connected: isConnected,
        port_active: data?.avatar_service?.port_active || false,
        relay_connected: data?.relay?.connected || false,
        last_check: new Date()
    };

    // Update status dot color
    if (isConnected) {
        dot.className = 'w-2 h-2 rounded-full bg-green-500';
        dot.title = 'Avatar connected';
        text.textContent = 'Connected';
        text.className = 'text-green-400';
        if (launchBtn) launchBtn.style.display = 'none';
    } else if (status === 'starting') {
        dot.className = 'w-2 h-2 rounded-full bg-yellow-500 animate-pulse';
        dot.title = 'Avatar starting';
        text.textContent = 'Starting...';
        text.className = 'text-yellow-400';
    } else {
        dot.className = 'w-2 h-2 rounded-full bg-gray-500';
        dot.title = 'Avatar disconnected';
        text.textContent = 'Offline';
        text.className = 'text-gray-500';
        if (launchBtn) launchBtn.style.display = 'flex';
    }
}

/**
 * Launch avatar service (admin only)
 */
async function launchAvatar() {
    // 권한 체크
    if (!IS_ADMIN) {
        showNotification('Admin 권한이 필요합니다.', 'error');
        return;
    }

    if (!AUTH_TOKEN) {
        showNotification('로그인이 필요합니다.', 'error');
        return;
    }

    const btn = document.getElementById('launchAvatarBtn');
    const originalContent = btn ? btn.innerHTML : '';
    let isLaunching = true;

    // 버튼 비활성화 및 로딩 상태 표시
    if (btn) {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Launching...';
        btn.disabled = true;
        btn.classList.add('opacity-50', 'cursor-not-allowed');
    }

    try {
        const response = await fetch(`${API_BASE}/admin/launch_avatar`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AUTH_TOKEN}`
            }
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // 성공 메시지
            showNotification(
                data.message || 'VTuber 아바타가 성공적으로 실행되었습니다.',
                'success',
                5000
            );

            // 상세 정보 로그
            console.log('[MellowLink] Avatar launched:', {
                pid: data.pid,
                server_ready: data.server_ready,
                electron_launched: data.electron_launched
            });

            // 상태 새로고침 (약간의 지연 후)
            setTimeout(async () => {
                await refreshAvatarStatus();
            }, 2000);
        } else {
            // 실패 메시지
            const errorMsg = data.detail || data.message || '아바타 실행에 실패했습니다.';
            
            if (response.status === 403) {
                showNotification('Admin 권한이 필요합니다.', 'error');
            } else if (response.status === 401) {
                showNotification('인증이 필요합니다. 다시 로그인해주세요.', 'error');
            } else {
                showNotification(errorMsg, 'error', 6000);
            }
        }
    } catch (error) {
        console.error('[MellowLink] Failed to launch avatar:', error);
        showNotification(
            '네트워크 오류가 발생했습니다. 다시 시도해주세요.',
            'error'
        );
    } finally {
        // 버튼 상태 복원
        isLaunching = false;
        if (btn) {
            btn.innerHTML = originalContent;
            btn.disabled = false;
            btn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
}

/**
 * Select Secretary folder (admin only)
 */
function selectSecretaryFolder() {
    if (!SECRETARY_FOLDER_ID) {
        console.warn('[MellowLink] Secretary folder ID not set');
        return;
    }
    selectFolder(SECRETARY_FOLDER_ID);
}

/**
 * Initialize Mellow-Link UI based on user role
 */
async function initMellowLink() {
    const mellowLinkSection = document.getElementById('mellowLinkSection');
    
    // 게스트 모드이거나 토큰이 없으면 숨김
    if (!AUTH_TOKEN || IS_GUEST_MODE) {
        if (mellowLinkSection) {
            mellowLinkSection.style.display = 'none';
        }
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/mellow-link/init`, {
            headers: { 'Authorization': `Bearer ${AUTH_TOKEN}` }
        });

        if (res.ok) {
            const data = await res.json();

            if (data.success) {
                // Update admin status
                IS_ADMIN = data.is_admin || false;
                window.IS_ADMIN = IS_ADMIN; // 전역 변수에도 설정

                // Admin만 Mellow-Link 섹션 표시
                if (mellowLinkSection) {
                    if (IS_ADMIN) {
                        mellowLinkSection.style.display = 'block';
                    } else {
                        mellowLinkSection.style.display = 'none';
                    }
                }

                // Show Secretary folder for admin
                if (IS_ADMIN && data.folders) {
                    const secretaryFolder = data.folders.find(f => f.name.includes('Secretary'));
                    if (secretaryFolder) {
                        SECRETARY_FOLDER_ID = secretaryFolder.id;
                        const secretaryFolderEl = document.getElementById('secretaryFolder');
                        if (secretaryFolderEl) {
                            secretaryFolderEl.classList.remove('hidden');
                        }
                    }
                } else {
                    // Admin이 아니면 Secretary 폴더 숨김
                    const secretaryFolderEl = document.getElementById('secretaryFolder');
                    if (secretaryFolderEl) {
                        secretaryFolderEl.classList.add('hidden');
                    }
                }

                // Update avatar status
                if (data.avatar_status) {
                    updateAvatarStatusUI(data.avatar_status);
                }

                // [Admin Auto-Refresh] Electron이 백그라운드로 실행되므로 몇 초 후 상태 재확인
                if (IS_ADMIN) {
                    console.log('[MellowLink] Admin detected - scheduling avatar status refresh...');
                    // 3초 후 첫 번째 체크
                    setTimeout(() => {
                        console.log('[MellowLink] Auto-refreshing avatar status (3s)...');
                        refreshAvatarStatus();
                    }, 3000);
                    // 6초 후 두 번째 체크 (Electron 실행 완료 대기)
                    setTimeout(() => {
                        console.log('[MellowLink] Auto-refreshing avatar status (6s)...');
                        refreshAvatarStatus();
                    }, 6000);
                }

                console.log('[MellowLink] Initialized:', { is_admin: IS_ADMIN, secretary_id: SECRETARY_FOLDER_ID });
            } else {
                // 실패 시 섹션 숨김
                if (mellowLinkSection) {
                    mellowLinkSection.style.display = 'none';
                }
            }
        } else {
            // API 실패 시 섹션 숨김
            if (mellowLinkSection) {
                mellowLinkSection.style.display = 'none';
            }
        }
    } catch (e) {
        console.error('[MellowLink] Init failed:', e);
        // 에러 시 섹션 숨김
        if (mellowLinkSection) {
            mellowLinkSection.style.display = 'none';
        }
    }
}

/**
 * 앱 초기화
 */
window.onload = async () => {
    console.log('🚀 App loading...');

    // ============================================
    // [STEP 1] Access Gate Check (MUST PASS FIRST)
    // ============================================
    const hasAccess = await checkAccessGate();
    if (!hasAccess) {
        console.log('🔒 Access gate active - waiting for authentication');
        // Don't initialize rest of app until authenticated
        // The page will reload after successful login
        return;
    }

    // ============================================
    // [STEP 2] Normal App Initialization
    // ============================================
    document.getElementById('tempSlider').addEventListener('input', updateTempDisplay);

    // 인증 상태 확인 및 UI 업데이트
    if (AUTH_TOKEN) {
        await checkAuth();
    } else {
        switchToGuestUI();
    }

    // 온도 슬라이더 초기화
    updateTempDisplay();

    // ✅ [VRAM] VRAM 모니터링 시작
    startVRAMPolling();

    // ✅ [MELLOW-LINK] Initialize Mellow-Link UI
    await initMellowLink();

    // ✅ [SESSION PERSISTENCE] URL 파라미터 자동 로드 (새로고침 유지)
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session_id');

    if (sessionId) {
        console.log(`🔗 [URL] Found session_id=${sessionId}, auto-loading...`);

        // 세션 자동 로드 (약간의 지연으로 UI 초기화 완료 대기)
        setTimeout(async () => {
            try {
                await loadSession(parseInt(sessionId));
                console.log(`✅ [URL] Auto-loaded session ${sessionId}`);
            } catch (e) {
                console.error(`❌ [URL] Failed to auto-load session ${sessionId}:`, e);
                // 실패 시 URL 파라미터 제거
                history.replaceState(null, '', window.location.pathname);
            }
        }, 300);  // 300ms 지연 (폴더/세션 목록 로드 대기)
    }

    console.log('✅ App ready');
};
