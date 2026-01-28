// =========================
// UI Rendering Module
// =========================

/**
 * 전송 버튼 상태 업데이트
 */
function updateSendButtonState(generating) {
    const btn = document.getElementById('sendBtn');
    const icon = document.getElementById('sendIcon');
    if(generating) {
        btn.classList.replace('bg-purple-600', 'bg-red-600');
        btn.classList.replace('hover:bg-purple-700', 'hover:bg-red-700');
        icon.classList.replace('fa-paper-plane', 'fa-stop');
    } else {
        btn.classList.replace('bg-red-600', 'bg-purple-600');
        btn.classList.replace('hover:bg-red-700', 'hover:bg-purple-700');
        icon.classList.replace('fa-stop', 'fa-paper-plane');
    }
}

// ✅ [Edit] 옵션 B: 수정 모드 경고 바 표시/숨김
function showEditWarningBar({ text, onCancel }) {
    const bar = document.getElementById('editWarningBar');
    if (!bar) return;
  
    bar.innerHTML = `
      <div class="edit-warning-text">${escapeHtml(text)}</div>
      <button id="editCancelBtn" class="edit-warning-cancel">수정 취소</button>
    `;
    bar.style.display = 'flex';
  
    const btn = document.getElementById('editCancelBtn');
    btn.onclick = onCancel;
  }
  
  function hideEditWarningBar() {
    const bar = document.getElementById('editWarningBar');
    if (!bar) return;
    bar.style.display = 'none';
    bar.innerHTML = '';
  }

// [중요] 메시지 렌더링 (시간 표시 & 재생성 & 스마트 카피 복구 & 사용자 메시지 수정)
function addMessageToUI(role, content, ragUsed=false, messageId=null, feedbackPositive=null, autoSelected=false, selectedMode=null, timeTaken=null, originMid=null) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = `flex ${role==='user'?'justify-end':'justify-start'} mb-4`;

    let processed = content;
    if(role==='assistant' && content.includes('<think>')) {
        const parts = content.split('</think>');
        // ✅ [P0] DOM 구조 안정성: thought-content 클래스 추가 (switchVersion에서 사용)
        processed = `<details class="mb-3 opacity-60 text-xs border-b border-gray-700 pb-2 w-full"><summary class="cursor-pointer hover:text-purple-400">🤔 생각 과정</summary><div class="thought-content p-3 mt-2 bg-black bg-opacity-40 rounded italic whitespace-pre-wrap">${escapeHtml(parts[0].replace('<think>','').trim())}</div></details><div class="actual-answer whitespace-pre-wrap">${escapeHtml(parts[1]?parts[1].trim():"")}</div>`;
    } else {
        // ✅ [P0] DOM 구조 안정성: assistant 메시지에 actual-answer 클래스 보장
        processed = role === 'assistant'
            ? `<div class="actual-answer whitespace-pre-wrap">${escapeHtml(content)}</div>`
            : `<div class="whitespace-pre-wrap">${escapeHtml(content)}</div>`;
    }

    // ✅ [A안] dataset.originMid 속성 추가 (선행 공백 포함하여 속성 분리 보장)
    const originMidAttr = (role === 'assistant' && originMid) ? ` data-origin-mid="${String(originMid)}"` : '';
    // ✅ [Edit] dataset.messageId 속성 추가 (서버 동기화용)
    const messageIdAttr = messageId ? ` data-message-id="${messageId}"` : '';
    // ✅ [FIX-1A] data-mid, data-role 추가 (Abort 메시지 Regenerate 지원)
    const midAttr = messageId !== null ? ` data-mid="${messageId}"` : ' data-mid="null"';
    const roleAttr = ` data-role="${role}"`;
    let html = `<div class="max-w-[85%] rounded-xl px-4 py-3 ${role==='user'?'message-user text-white':'message-assistant text-gray-100 shadow-lg'} relative group"${originMidAttr}${messageIdAttr}${midAttr}${roleAttr}>`;

    // ========================================
    // [NEW] 사용자 메시지: 수정 버튼 추가 (좌측 상단으로 이동)
    // ========================================
    if (role === 'user') {
        html += `
            <button onclick="startEditMessage(this)"
                    class="absolute top-2 -left-7 opacity-0 group-hover:opacity-100 transition-opacity p-1.5 bg-black bg-opacity-30 hover:bg-opacity-50 rounded-lg text-white shadow-lg"
                    title="Edit Message">
                <i class="fas fa-edit text-sm"></i>
            </button>
        `;
    }

    html += processed;

    // ========================================
    // Assistant 메시지: 기존 피드백 버튼 유지
    // ========================================
    if(role==='assistant') {
        html += `<div class="mt-2 flex flex-wrap gap-2 items-center">`;
        // [복구] 시간 표시 (서버 시간 또는 클라이언트 계산 시간)
        if(timeTaken) html += `<span class="py-1 px-2 bg-gray-800 bg-opacity-50 rounded text-[10px] text-gray-400 border border-gray-600 font-mono">⏱️ ${parseFloat(timeTaken).toFixed(2)}s</span>`;
        if(selectedMode) html += `<span class="py-1 px-2 bg-gray-700 bg-opacity-50 rounded text-[10px] border">🤖 ${autoSelected?"Auto→":""}${selectedMode.toUpperCase()}</span>`;
        if(ragUsed) html += `<span class="py-1 px-2 bg-purple-900 bg-opacity-50 rounded text-[10px] text-purple-200 border border-purple-700">📚 RAG</span>`;
        html += `</div>`;

        // 버튼들
        const upColor = feedbackPositive===true?'text-green-400':'text-gray-500';
        const downColor = feedbackPositive===false?'text-red-400':'text-gray-500';
        html += `<div class="flex items-center gap-3 mt-3 pt-2 border-t border-gray-700/50"><button onclick="copyToClipboard(this)" class="text-xs text-gray-500 hover:text-white" title="Copy Text"><i class="fas fa-copy"></i></button>`;
        if(messageId) html += `<div class="flex gap-2 border-l border-gray-700 pl-3"><button onclick="submitFeedback(${messageId},true,this)" class="text-xs ${upColor} hover:text-green-400"><i class="fas fa-thumbs-up"></i></button><button onclick="submitFeedback(${messageId},false,this)" class="text-xs ${downColor} hover:text-red-400"><i class="fas fa-thumbs-down"></i></button></div>`;
        // ... (위쪽 코드: 복사 버튼, 피드백 버튼 등) ...
        
        // 1. 💎 버튼을 담을 '우측 정렬 그릇' (하나만 만든다!)
        html += `<div class="ml-auto flex gap-2">`;

        // 🔒 2. Regenerate 버튼: 소설방(is_creative) VIP 전용
        // (불필요한 div 태그 제거하고 button만 깔끔하게 넣음)
        if (CURRENT_FOLDER && CURRENT_FOLDER.is_creative) {
             html += `<button onclick="regenerateResponse(${messageId}, this)" class="btn-regenerate text-xs text-gray-500 hover:text-purple-400" title="Regenerate" style="display:none;"><i class="fas fa-sync-alt"></i></button>`;
        }
        // 🌍 3. Continue 버튼: 누구나 사용 가능 (조건 없음)
        html += `<button onclick="continueResponse(${messageId}, this)" class="btn-continue text-xs text-gray-500 hover:text-blue-400" title="Continue" style="display:none;"><i class="fas fa-arrow-right"></i></button>`;
        // 4. 그릇 닫기
        html += `</div>`;
    }
    html += `</div>`;
    div.innerHTML = html;
    container.appendChild(div);

    // ✅ [Regenerate] assistant 메시지 추가 후 버튼 가시성 업데이트
    if (role === 'assistant') {
        setTimeout(() => updateRegenerateVisibility({ showOnly: div }), 0);
    }
}

/**
 * Regenerate 버튼 가시성 제어
 * @param {Object} options - { hideAll: boolean, showOnly: HTMLElement }
 */
function updateRegenerateVisibility(options = {}) {
    const { hideAll = false, showOnly = null } = options;

    // 모든 버튼 찾기
    const allRegenerateButtons = document.querySelectorAll('.btn-regenerate');
    const allContinueButtons = document.querySelectorAll('.btn-continue');

    if (hideAll) {
        // 모두 숨김
        allRegenerateButtons.forEach(btn => btn.style.display = 'none');
        allContinueButtons.forEach(btn => btn.style.display = 'none');
        return;
    }

    if (showOnly) {
        // 1. 모든 버튼 숨김
        allRegenerateButtons.forEach(btn => btn.style.display = 'none');
        allContinueButtons.forEach(btn => btn.style.display = 'none');

        // 2. 지정된 버블의 regenerate 버튼만 표시
        const targetButton = showOnly.querySelector('.btn-regenerate');
        if (targetButton) {
            targetButton.style.display = 'inline-block';
        }
        const targetContinueBtn = showOnly.querySelector('.btn-continue');
        if (targetContinueBtn) {
            targetContinueBtn.style.display = 'inline-block';
        }
    }
}

// [중요] 스마트 카피 기능 복구 (아이콘 변경 + 내용만 복사)
async function copyToClipboard(btn) {
    try {
        const messageBubble = btn.closest('[data-role="assistant"]') || btn.closest('.message-assistant'); if (!messageBubble) return;

        let txt = "";
        // 1. 답변만 추출 (생각 과정 제외)
        const actualAnswerDiv = messageBubble.querySelector('.actual-answer');
        if (actualAnswerDiv) txt = actualAnswerDiv.innerText;
        else {
            const simpleTextDiv = messageBubble.querySelector('.whitespace-pre-wrap');
            if(simpleTextDiv) txt = simpleTextDiv.innerText;
            else txt = messageBubble.innerText; // Fallback
        }

        await navigator.clipboard.writeText(txt);
        
        // 2. 아이콘 변경 애니메이션
        const icon = btn.querySelector('i');
        const originalClass = icon.className;
        icon.className = 'fas fa-check text-green-400';
        setTimeout(() => icon.className = originalClass, 2000);
    } catch(e) { console.error(e); alert('Copy failed'); }
}

/**
 * 버전 관리 (간소화)
 */
function findBubbleByOriginMid(originMid) {
    return document.querySelector(`[data-origin-mid="${originMid}"]`);
}

function attachOrUpdateVersionControls(bubbleEl, originMid) {
    if (!answerVersions[originMid] || answerVersions[originMid].items.length <= 1) {
        // 버전이 1개 이하면 토글 UI 숨김
        const existingControls = bubbleEl.querySelector('.version-controls');
        if (existingControls) existingControls.remove();
        return;
    }

    const versions = answerVersions[originMid];
    const currentIndex = versions.index;
    const totalCount = versions.items.length;

    // 기존 컨트롤 제거 (업데이트용)
    const existingControls = bubbleEl.querySelector('.version-controls');
    if (existingControls) existingControls.remove();

    // content div 찾기 (actual-answer 또는 whitespace-pre-wrap)
    const contentDiv = bubbleEl.querySelector('.actual-answer') || bubbleEl.querySelector('.whitespace-pre-wrap');
    if (!contentDiv) {
        console.warn(`⚠️ [Version] Could not find content div for originMid=${originMid}`);
        return;
    }

    // 버전 토글 UI 생성
    const controlsDiv = document.createElement('div');
    controlsDiv.className = 'version-controls mt-3 pt-3 border-t border-gray-700 flex items-center justify-between text-xs text-gray-400';
    controlsDiv.innerHTML = `
        <button class="version-prev px-2 py-1 rounded hover:bg-gray-700 transition ${currentIndex === 0 ? 'opacity-30 cursor-not-allowed' : ''}"
                ${currentIndex === 0 ? 'disabled' : ''}
                onclick="switchVersion('${originMid}', -1)">
            <i class="fas fa-chevron-left"></i>
        </button>
        <span class="version-counter font-mono">${currentIndex + 1} / ${totalCount}</span>
        <button class="version-next px-2 py-1 rounded hover:bg-gray-700 transition ${currentIndex === totalCount - 1 ? 'opacity-30 cursor-not-allowed' : ''}"
                ${currentIndex === totalCount - 1 ? 'disabled' : ''}
                onclick="switchVersion('${originMid}', 1)">
            <i class="fas fa-chevron-right"></i>
        </button>
    `;

    // 버블 끝에 추가
    bubbleEl.appendChild(controlsDiv);
    console.log(`🔁 [Version] Attached controls for originMid=${originMid} (${currentIndex + 1}/${totalCount})`);
}

function switchVersion(originMid, direction) {
    const versions = answerVersions[originMid];
    if (!versions) return;

    // 인덱스 변경
    const newIndex = versions.index + direction;
    if (newIndex < 0 || newIndex >= versions.items.length) return;

    versions.index = newIndex;
    const versionData = versions.items[newIndex];

    console.log(`🔁 [Version] originMid=${originMid} -> ${newIndex + 1}/${versions.items.length}`);

    // 버블 찾기
    const bubbleEl = findBubbleByOriginMid(originMid);
    if (!bubbleEl) {
        console.warn(`⚠️ [Version] Bubble not found for originMid=${originMid}`);
        return;
    }

    // content div 찾기
    const contentDiv = bubbleEl.querySelector('.actual-answer') || bubbleEl.querySelector('.whitespace-pre-wrap');
    if (!contentDiv) {
        console.warn(`⚠️ [Version] Content div not found for originMid=${originMid}`);
        return;
    }

    // <think> 태그 처리
    let displayContent = versionData.content;
    if (displayContent.includes('<think>')) {
        const parts = displayContent.split('</think>');
        const thinkContent = parts[0].replace('<think>', '').trim();
        const answerContent = parts[1] ? parts[1].trim() : '';

        // 부모 버블에서 details와 actual-answer를 모두 업데이트
        const thoughtDetails = bubbleEl.querySelector('details');
        if (thoughtDetails) {
            const thoughtContentDiv = thoughtDetails.querySelector('.thought-content');
            if (thoughtContentDiv) thoughtContentDiv.textContent = thinkContent;
        }
        contentDiv.textContent = answerContent;
    } else {
        contentDiv.textContent = displayContent;
    }

    // 토글 UI 업데이트
    attachOrUpdateVersionControls(bubbleEl, originMid);
}


/**
 * 사이드바 토글
 */
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebarToggleBtn');
    const toggleIcon = document.getElementById('toggleIcon');

    SIDEBAR_COLLAPSED = !SIDEBAR_COLLAPSED;

    if (SIDEBAR_COLLAPSED) {
        // Collapse sidebar
        sidebar.className = 'sidebar-collapsed bg-dark-card border-l border-dark-border transition-all duration-300 flex flex-col overflow-hidden';
        // Show floating toggle button
        if (toggleBtn) {
            toggleBtn.style.display = 'block';
            toggleBtn.innerHTML = '◀';
            toggleBtn.title = 'Open Chat History';
        }
    } else {
        // Expand sidebar
        sidebar.className = 'sidebar-expanded bg-dark-card border-l border-dark-border transition-all duration-300 flex flex-col overflow-hidden';
        // Hide floating toggle button
        if (toggleBtn) {
            toggleBtn.style.display = 'none';
        }
    }

    // Update icon inside sidebar header
    if (toggleIcon) {
        toggleIcon.textContent = SIDEBAR_COLLAPSED ? '‹' : '›';
    }
}

// =============================================================================
// Mission B: VRAM Monitoring Widget
// =============================================================================

/**
 * VRAM 위젯 업데이트
 */
function updateVRAMWidget() {
    const widget = document.getElementById('vramWidget');
    if (!widget) return;

    const { used, total, percent } = window.VRAM_STATUS;
    const usedGB = (used / 1024).toFixed(1);
    const totalGB = (total / 1024).toFixed(1);

    // 게이지 바 색상 결정 (80% 이상이면 경고색)
    let barColor = 'bg-purple-500';
    let textColor = 'text-purple-400';
    if (percent >= 80) {
        barColor = 'bg-red-500';
        textColor = 'text-red-400';
    } else if (percent >= 60) {
        barColor = 'bg-orange-500';
        textColor = 'text-orange-400';
    }

    widget.innerHTML = `
        <div class="flex items-center gap-2">
            <i class="fas fa-microchip ${textColor}"></i>
            <div class="flex flex-col">
                <div class="flex items-center gap-1">
                    <span class="text-xs text-gray-400">VRAM</span>
                    <span class="text-xs ${textColor} font-mono">${usedGB}/${totalGB}GB</span>
                </div>
                <div class="w-20 h-1.5 bg-dark-border rounded-full overflow-hidden">
                    <div class="${barColor} h-full transition-all duration-300 rounded-full" style="width: ${Math.min(percent, 100)}%"></div>
                </div>
            </div>
        </div>
    `;
}

// =============================================================================
// Mission A: Multimodal Image Rendering
// =============================================================================

/**
 * 이미지 생성 로딩 스피너 추가
 */
function addImageLoadingIndicator(container) {
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'imageGenerationLoading';
    loadingDiv.className = 'flex justify-start mb-4';
    loadingDiv.innerHTML = `
        <div class="max-w-[85%] rounded-xl px-4 py-4 message-assistant text-gray-100 shadow-lg">
            <div class="flex items-center gap-3">
                <div class="relative">
                    <div class="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
                    <i class="fas fa-image absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-purple-400 text-xs"></i>
                </div>
                <div>
                    <p class="text-sm font-medium text-purple-300">이미지 생성 중...</p>
                    <p class="text-xs text-gray-500">Flux 모델이 작업 중입니다</p>
                </div>
            </div>
            <div class="mt-3 w-full bg-dark-border rounded-full h-1.5 overflow-hidden">
                <div class="bg-gradient-to-r from-purple-500 to-pink-500 h-full animate-pulse" style="width: 60%"></div>
            </div>
        </div>
    `;
    container.appendChild(loadingDiv);
    container.scrollTop = container.scrollHeight;
    return loadingDiv;
}

/**
 * 이미지 생성 로딩 제거
 */
function removeImageLoadingIndicator() {
    const loading = document.getElementById('imageGenerationLoading');
    if (loading) loading.remove();
}

/**
 * 이미지 메시지 렌더링 (멀티모달)
 * @param {string} imageUrl - 생성된 이미지 URL
 * @param {string} textContent - 텍스트 응답 (있는 경우)
 * @param {object} metadata - 메타데이터 (intent, refined_prompt 등)
 */
function addImageMessageToUI(imageUrl, textContent = '', metadata = {}) {
    const container = document.getElementById('chatMessages');
    removeImageLoadingIndicator();

    const div = document.createElement('div');
    div.className = 'flex justify-start mb-4';

    const { intent, refined_prompt, processing_time, message_id } = metadata;

    // 인텐트 배지 생성
    const intentBadge = getIntentBadge(intent || 'image_request');

    // Prompt Details 아코디언 (refined_prompt가 있는 경우)
    let promptDetailsHtml = '';
    if (refined_prompt) {
        promptDetailsHtml = `
            <details class="mt-3 border border-gray-700 rounded-lg overflow-hidden">
                <summary class="cursor-pointer px-3 py-2 bg-dark-hover hover:bg-dark-border transition text-xs text-gray-400 flex items-center gap-2">
                    <i class="fas fa-magic text-purple-400"></i>
                    <span>Show Prompt Details</span>
                </summary>
                <div class="px-3 py-2 bg-black bg-opacity-30 text-xs text-gray-300 font-mono whitespace-pre-wrap">${escapeHtml(refined_prompt)}</div>
            </details>
        `;
    }

    // 시간 표시
    const timeHtml = processing_time
        ? `<span class="py-1 px-2 bg-gray-800 bg-opacity-50 rounded text-[10px] text-gray-400 border border-gray-600 font-mono">⏱️ ${parseFloat(processing_time).toFixed(2)}s</span>`
        : '';

    div.innerHTML = `
        <div class="max-w-[85%] rounded-xl px-4 py-3 message-assistant text-gray-100 shadow-lg relative group" data-message-id="${message_id || ''}">
            <!-- Intent Badge -->
            <div class="mb-2">${intentBadge}</div>

            <!-- Text Content (있는 경우) -->
            ${textContent ? `<div class="actual-answer whitespace-pre-wrap mb-3">${escapeHtml(textContent)}</div>` : ''}

            <!-- Generated Image -->
            <div class="generated-image-container rounded-lg overflow-hidden border border-gray-700 bg-black">
                <img src="${imageUrl}"
                     alt="Generated Image"
                     class="w-full max-w-lg object-contain cursor-pointer hover:opacity-90 transition"
                     style="max-height: 512px; aspect-ratio: auto;"
                     onclick="openImageModal('${imageUrl}')"
                     loading="lazy"
                />
            </div>

            <!-- Prompt Details Accordion -->
            ${promptDetailsHtml}

            <!-- Metadata Row -->
            <div class="mt-3 flex flex-wrap gap-2 items-center">
                ${timeHtml}
                <button onclick="downloadImage('${imageUrl}')" class="text-xs text-gray-500 hover:text-white px-2 py-1 bg-dark-hover rounded" title="Download">
                    <i class="fas fa-download"></i>
                </button>
                <button onclick="copyToClipboard(this)" class="text-xs text-gray-500 hover:text-white px-2 py-1 bg-dark-hover rounded" title="Copy Prompt">
                    <i class="fas fa-copy"></i>
                </button>
            </div>
        </div>
    `;

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

/**
 * 이미지 모달 열기 (고해상도 미리보기)
 */
function openImageModal(imageUrl) {
    // 기존 모달 제거
    const existingModal = document.getElementById('imagePreviewModal');
    if (existingModal) existingModal.remove();

    const modal = document.createElement('div');
    modal.id = 'imagePreviewModal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-90 flex items-center justify-center z-[100] cursor-pointer';
    modal.onclick = () => modal.remove();
    modal.innerHTML = `
        <div class="relative max-w-[90vw] max-h-[90vh]">
            <img src="${imageUrl}" alt="Preview" class="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl">
            <button onclick="event.stopPropagation(); document.getElementById('imagePreviewModal').remove()"
                    class="absolute top-2 right-2 w-10 h-10 bg-black bg-opacity-50 hover:bg-opacity-70 rounded-full flex items-center justify-center text-white transition">
                <i class="fas fa-times"></i>
            </button>
            <div class="absolute bottom-2 right-2 flex gap-2">
                <a href="${imageUrl}" download class="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-white text-sm transition" onclick="event.stopPropagation()">
                    <i class="fas fa-download mr-1"></i> Download
                </a>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

/**
 * 이미지 다운로드
 */
async function downloadImage(imageUrl) {
    try {
        const response = await fetch(imageUrl);
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `generated_${Date.now()}.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (e) {
        console.error('[Download] Failed:', e);
        // Fallback: 새 탭에서 열기
        window.open(imageUrl, '_blank');
    }
}

// =============================================================================
// Mission C: Intent Badges
// =============================================================================

/**
 * 인텐트에 따른 배지 HTML 생성
 * @param {string} intent - simple_chat, image_request, document_qa
 */
function getIntentBadge(intent) {
    const badges = {
        'image_request': `<span class="inline-flex items-center gap-1 px-2 py-0.5 bg-pink-900 bg-opacity-50 text-pink-300 text-[10px] rounded-full border border-pink-700"><i class="fas fa-palette"></i> Image</span>`,
        'document_qa': `<span class="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-900 bg-opacity-50 text-blue-300 text-[10px] rounded-full border border-blue-700"><i class="fas fa-book"></i> Document</span>`,
        'simple_chat': `<span class="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-700 bg-opacity-50 text-gray-300 text-[10px] rounded-full border border-gray-600"><i class="fas fa-comment"></i> Chat</span>`
    };
    return badges[intent] || badges['simple_chat'];
}

/**
 * 기존 addMessageToUI 확장 - 인텐트 배지 지원
 * (이 함수는 기존 addMessageToUI를 호출한 후 배지를 추가합니다)
 */
function addMessageWithIntent(role, content, metadata = {}) {
    const { intent, refined_prompt, image_url, target_service } = metadata;

    // 이미지 응답인 경우
    if (target_service === 'image' || image_url) {
        addImageMessageToUI(image_url, content, metadata);
        return;
    }

    // 일반 텍스트 응답 (기존 addMessageToUI 사용 후 배지 삽입)
    addMessageToUI(
        role,
        content,
        metadata.rag_used,
        metadata.message_id,
        metadata.feedback_positive,
        metadata.auto_selected,
        metadata.selected_mode,
        metadata.processing_time,
        metadata.origin_mid
    );

    // 인텐트 배지 삽입 (마지막 assistant 메시지에)
    if (role === 'assistant' && intent) {
        setTimeout(() => {
            const lastBubble = document.querySelector('.message-assistant:last-of-type');
            if (lastBubble) {
                const badgeHtml = getIntentBadge(intent);
                const existingBadge = lastBubble.querySelector('.intent-badge');
                if (!existingBadge) {
                    const badgeContainer = document.createElement('div');
                    badgeContainer.className = 'intent-badge mb-2';
                    badgeContainer.innerHTML = badgeHtml;
                    lastBubble.insertBefore(badgeContainer, lastBubble.firstChild);
                }

                // Prompt Details 추가 (이미지 아닌 경우에도 refined_prompt가 있으면)
                if (refined_prompt && !lastBubble.querySelector('.prompt-details')) {
                    const detailsHtml = `
                        <details class="prompt-details mt-3 border border-gray-700 rounded-lg overflow-hidden">
                            <summary class="cursor-pointer px-3 py-2 bg-dark-hover hover:bg-dark-border transition text-xs text-gray-400 flex items-center gap-2">
                                <i class="fas fa-magic text-purple-400"></i>
                                <span>Show Details</span>
                            </summary>
                            <div class="px-3 py-2 bg-black bg-opacity-30 text-xs text-gray-300 font-mono whitespace-pre-wrap">${escapeHtml(refined_prompt)}</div>
                        </details>
                    `;
                    const metaRow = lastBubble.querySelector('.flex.flex-wrap.gap-2');
                    if (metaRow) {
                        metaRow.insertAdjacentHTML('beforebegin', detailsHtml);
                    }
                }
            }
        }, 50);
    }
}
