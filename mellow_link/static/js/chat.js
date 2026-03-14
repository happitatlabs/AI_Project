// =========================
// Chat & Message Module
// =========================

// ---------- Progress panel (plan_created / todos from /runs/{run_id}/events) ----------
let progressRunEventSource = null;
let progressRunId = null;
let progressLastEventId = null;
let progressTodosState = [];
let progressRunStatus = null;
const PROGRESS_LOG_MAX = 50;

// ---------- In-chat TaskBlock (User View: todos + progress inside message bubble) ----------
const taskBlockEventSourceByRunId = {};
let currentTaskBlockRunId = null;
let currentTaskBlockState = null;
let currentTaskBlockBubbleRef = null;
let taskBlockLastRenderedSnapshot = '';

function closeTaskBlockEventSource(runId) {
    if (!runId) return;
    const es = taskBlockEventSourceByRunId[runId];
    if (es) {
        es.close();
        delete taskBlockEventSourceByRunId[runId];
    }
}

function closeAllTaskBlockEventSources() {
    Object.keys(taskBlockEventSourceByRunId).forEach(runId => closeTaskBlockEventSource(runId));
}

function taskBlockStateSnapshot(state) {
    if (!state) return '';
    return JSON.stringify({
        runId: state.runId,
        todos: (state.todos || []).map(t => ({ id: t.id || t.todo_id, title: t.title, status: t.status })),
        currentTodoId: state.currentTodoId,
        progress: state.progress,
        status: state.status,
        summary: state.summary
    });
}

function buildTaskBlockHTML(state) {
    if (!state) return '';
    const title = state.title || '작업 계획';
    const todos = state.todos || [];
    const progress = state.progress || { done: 0, total: 0 };
    const total = progress.total || todos.length || 0;
    const done = Math.min(progress.done, total);
    const status = state.status || 'running';
    const summary = state.summary || '';
    const currentId = state.currentTodoId || '';

    const statusLine = status === 'running' ? '진행 중...' : status === 'finished' ? '완료' : status === 'error' ? (summary ? `오류 (${summary.slice(0, 40)}${summary.length > 40 ? '…' : ''})` : '오류') : '';

    const listHtml = todos.length
        ? todos.map(t => {
            const id = t.id || t.todo_id;
            const st = (t.status || '').toString().toLowerCase();
            const isDone = st === 'completed' || st === 'done';
            const isDoing = st === 'in_progress' || st === 'doing' || id === currentId;
            const icon = isDone ? '✅' : isDoing ? '⏳' : '○';
            const nowLabel = isDoing ? ' (NOW)' : '';
            const cls = isDone ? 'text-gray-500 line-through' : isDoing ? 'text-purple-300' : 'text-gray-400';
            return `<li class="flex items-center gap-2 text-sm ${cls}">${icon} ${escapeHtmlProgress(t.title || id)}${nowLabel}</li>`;
        }).join('')
        : '<li class="text-gray-500 text-sm">할 일 없음</li>';

    const runId = state.runId || '';
    const operatorLink = (typeof window !== 'undefined' && (window.isAdmin === true)) && runId
        ? `<a href="/operator-console?run_id=${encodeURIComponent(runId)}" target="_blank" rel="noopener" class="text-xs text-purple-400 hover:text-purple-300 mt-1 inline-block">운영자 보기</a>`
        : '';

    return `<div class="task-block-container mt-3 p-3 rounded-lg border border-gray-600 bg-gray-800/50">
        <div class="text-xs font-semibold text-gray-400 mb-1">${escapeHtmlProgress(title)}</div>
        <div class="text-xs text-gray-500 mb-2">${done}/${total} 완료</div>
        <div class="h-1.5 bg-gray-700 rounded overflow-hidden mb-2 task-block-progress"><div class="h-full bg-purple-500 rounded transition-all duration-300" style="width:${total ? (done/total*100) : 0}%"></div></div>
        <ul class="space-y-0.5 list-none pl-0">${listHtml}</ul>
        <div class="text-xs text-gray-500 mt-2">${statusLine}</div>
        ${operatorLink}
    </div>`;
}

function renderTaskBlockInBubble(bubble, state) {
    if (!bubble || !document.contains(bubble)) return;
    const container = bubble.querySelector('.task-block-container');
    if (!container) return;
    const snapshot = taskBlockStateSnapshot(state);
    if (snapshot === taskBlockLastRenderedSnapshot) return;
    taskBlockLastRenderedSnapshot = snapshot;
    container.outerHTML = buildTaskBlockHTML(state);
}

function handleTaskBlockRunEvent(runId, eventData) {
    if (currentTaskBlockRunId !== runId || !currentTaskBlockState) return;
    const type = eventData.type;
    const payload = eventData.payload || {};
    const s = currentTaskBlockState;

    if (type === 'plan_created') {
        const list = payload.todos || [];
        s.todos = list.map(t => ({
            id: t.todo_id || t.id,
            title: t.title || t.todo_id || '',
            status: (t.status || 'todo').toString().toLowerCase() === 'completed' ? 'done' : (t.status || 'todo').toString().toLowerCase() === 'in_progress' ? 'doing' : 'todo'
        }));
        s.progress = { done: 0, total: list.length };
        if (window._currentRunPlanOnly && currentTaskBlockBubbleRef && document.contains(currentTaskBlockBubbleRef)) {
            injectPlanCardIntoBubble(currentTaskBlockBubbleRef, list);
        }
    } else if (type === 'todo_started') {
        s.currentTodoId = payload.todo_id || payload.id || '';
        const t = s.todos.find(x => (x.id || x.todo_id) === s.currentTodoId);
        if (t) t.status = 'doing';
    } else if (type === 'todo_done') {
        const tid = payload.todo_id || payload.id;
        const t = s.todos.find(x => (x.id || x.todo_id) === tid);
        if (t) t.status = 'done';
        s.progress = { ...s.progress, done: (s.progress.done || 0) + 1, total: s.progress.total || s.todos.length };
    } else if (type === 'run_finished') {
        s.status = payload.success !== false ? 'finished' : 'error';
        s.summary = (payload.summary || (payload.success !== false ? '완료' : '실패')).toString().slice(0, 80);
        closeTaskBlockEventSource(runId);
    } else if (type === 'error') {
        s.status = 'error';
        s.summary = (payload.message || '오류').toString().slice(0, 80);
        closeTaskBlockEventSource(runId);
    }

    renderTaskBlockInBubble(currentTaskBlockBubbleRef, currentTaskBlockState);
}

function subscribeToTaskBlockRunEvents(runId, lastEventId) {
    closeTaskBlockEventSource(runId);
    const url = `${State.getApiBase()}/runs/${runId}/events` + (lastEventId ? `?last_event_id=${lastEventId}` : '');
    const es = new EventSource(url);
    taskBlockEventSourceByRunId[runId] = es;
    es.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            if (data.type === 'timeout') return;
            handleTaskBlockRunEvent(runId, data);
        } catch (err) {
            console.warn('[TaskBlock] parse event error', err);
        }
    };
    es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) return;
    };
}

function buildPlanCardHTML(todos) {
    const listHtml = (todos || []).map(t => {
        const title = (t.title || t.todo_id || t.id || '').toString();
        return '<li class="flex items-center gap-2 text-sm text-slate-300">○ ' + escapeHtmlProgress(title) + '</li>';
    }).join('');
    return '<div class="plan-approval-card mt-3 p-4 rounded-xl border border-blue-500/30 bg-blue-900/10 shadow-lg">' +
        '<div class="text-xs font-semibold text-blue-400 mb-2 flex items-center gap-2">📋 계획</div>' +
        '<ul class="space-y-1 list-none pl-0 mb-4">' + listHtml + '</ul>' +
        '<button type="button" class="plan-execute-btn px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors">진행하기</button>' +
        '</div>';
}

function injectPlanCardIntoBubble(bubble, todos) {
    if (!bubble || !document.contains(bubble)) return;
    if (bubble.querySelector('.plan-approval-card')) return;
    const wrap = document.createElement('div');
    wrap.className = 'plan-approval-card-wrap';
    wrap.innerHTML = buildPlanCardHTML(todos || []);
    const btn = wrap.querySelector('.plan-execute-btn');
    if (btn) {
        btn.onclick = function () {
            const userInput = (window._planOnlyUserInput || '').trim();
            if (!userInput) return;
            btn.disabled = true;
            btn.textContent = '실행 중...';
            if (typeof sendMessage === 'function') {
                sendMessage(userInput, { plan_approved: true, skipAddUserMessage: true });
            }
        };
    }
    bubble.appendChild(wrap);
}

function injectTaskBlockIntoBubble(bubble) {
    if (!bubble) return;
    if (bubble.querySelector('.task-block-container')) return;
    const wrap = document.createElement('div');
    wrap.className = 'task-block-container';
    wrap.innerHTML = buildTaskBlockHTML(currentTaskBlockState);
    const typingIndicator = bubble.querySelector('.typing-indicator');
    if (typingIndicator && typingIndicator.parentNode === bubble) {
        bubble.insertBefore(wrap, typingIndicator);
    } else {
        bubble.appendChild(wrap);
    }
}

function handleRunMetaForTaskBlock(data, streamDiv) {
    const runId = data.run_id;
    if (!runId || !streamDiv) {
        if (typeof console !== 'undefined' && console.warn) console.warn('[TaskBlock] skip: runId=', runId, 'streamDiv=', !!streamDiv);
        return;
    }
    if (!streamDiv.isConnected) {
        if (typeof console !== 'undefined' && console.warn) console.warn('[TaskBlock] skip: streamDiv not in DOM');
        return;
    }
    closeTaskBlockEventSource(currentTaskBlockRunId);
    currentTaskBlockRunId = runId;
    currentTaskBlockState = {
        runId,
        title: '작업 계획',
        todos: [],
        currentTodoId: null,
        progress: { done: 0, total: 0 },
        status: 'running',
        summary: null
    };
    currentTaskBlockBubbleRef = streamDiv.querySelector('.message-assistant');
    taskBlockLastRenderedSnapshot = '';
    injectTaskBlockIntoBubble(currentTaskBlockBubbleRef);
    if (typeof console !== 'undefined' && console.log) console.log('[TaskBlock] injected runId=', runId);
    // ✅ 즉시 구독해 plan_created 등 이벤트 누락 방지 (스냅샷 fetch 이후 구독 시 이미 발송된 plan_created를 놓침)
    subscribeToTaskBlockRunEvents(runId, null);
    (async () => {
        try {
            const res = await fetch(`${State.getApiBase()}/runs/${runId}`, { headers: State.getAuthToken() ? { 'Authorization': 'Bearer ' + State.getAuthToken() } : {} });
            if (res.ok) {
                const snap = await res.json();
                const list = (snap.todos_view && snap.todos_view.length > 0) ? snap.todos_view : (snap.todos || []);
                if (list.length) {
                    currentTaskBlockState.todos = list.map(t => ({
                        id: t.todo_id || t.id,
                        title: t.title || t.todo_id || '',
                        status: (t.status || 'todo').toString().toLowerCase() === 'completed' ? 'done' : (t.status || 'todo').toString().toLowerCase() === 'in_progress' ? 'doing' : 'todo'
                    }));
                    const done = currentTaskBlockState.todos.filter(t => t.status === 'done').length;
                    currentTaskBlockState.progress = { done, total: list.length };
                    renderTaskBlockInBubble(currentTaskBlockBubbleRef, currentTaskBlockState);
                    if (window._currentRunPlanOnly && currentTaskBlockBubbleRef && document.contains(currentTaskBlockBubbleRef)) {
                        injectPlanCardIntoBubble(currentTaskBlockBubbleRef, list);
                    }
                }
            }
        } catch (_) {}
    })();
}

window.buildTaskBlockHTML = buildTaskBlockHTML;

function closeProgressEventSource() {
    if (progressRunEventSource) {
        progressRunEventSource.close();
        progressRunEventSource = null;
    }
}

function updateProgressTodos(todos) {
    const el = document.getElementById('progressTodos');
    const summaryEl = document.getElementById('progressSummary');
    if (!el) return;
    if (!todos || todos.length === 0) {
        el.innerHTML = '<li class="text-gray-500">작업 목록 없음</li>';
        if (summaryEl) summaryEl.textContent = 'Progress';
        return;
    }
    el.innerHTML = todos.map(t => {
        const st = (t.status || '').toString().toLowerCase();
        const done = st === 'completed';
        const label = t.title || t.todo_id || t.id || '';
        return `<li class="flex items-center gap-2 ${done ? 'text-gray-500 line-through' : ''}"><i class="fas fa-${done ? 'check-circle text-green-500' : 'circle'}"></i> ${escapeHtmlProgress(label)}</li>`;
    }).join('');
    if (summaryEl) summaryEl.textContent = `Progress (${todos.length}개)`;
}

function addProgressLog(level, message) {
    const el = document.getElementById('progressLog');
    if (!el) return;
    const entry = document.createElement('div');
    entry.className = level === 'error' ? 'text-red-400' : level === 'success' ? 'text-green-400' : 'text-gray-500';
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    el.appendChild(entry);
    while (el.children.length > PROGRESS_LOG_MAX) el.removeChild(el.firstChild);
    el.scrollTop = el.scrollHeight;
}

function escapeHtmlProgress(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function handleRunEvent(eventData) {
    const type = eventData.type;
    const payload = eventData.payload || {};
    if (type === 'plan_created') {
        progressTodosState = payload.todos || [];
        updateProgressTodos(progressTodosState);
        addProgressLog('info', `계획 생성: ${progressTodosState.length}개 작업`);
    } else if (type === 'todo_started') {
        const tid = payload.todo_id;
        const t = progressTodosState.find(x => x && x.todo_id === tid);
        if (t) t.status = 'in_progress';
        updateProgressTodos(progressTodosState);
        addProgressLog('info', `시작: ${payload.title || tid}`);
    } else if (type === 'todo_done') {
        const tid = payload.todo_id;
        const t = progressTodosState.find(x => x && x.todo_id === tid);
        if (t) t.status = payload.status || 'completed';
        updateProgressTodos(progressTodosState);
        addProgressLog('success', `완료: ${payload.title || tid}`);
    } else if (type === 'tool_started') {
        addProgressLog('info', `도구: ${payload.tool_name || ''}`);
    } else if (type === 'tool_done') {
        addProgressLog('info', `도구 완료: ${payload.tool_name || ''}`);
    } else if (type === 'run_finished') {
        progressRunStatus = (payload.success !== false) ? 'completed' : 'failed';
        addProgressLog('success', '실행 완료');
        closeProgressEventSource();
    } else if (type === 'error') {
        progressRunStatus = 'failed';
        addProgressLog('error', payload.message || '오류');
    }
    if (eventData.id) progressLastEventId = eventData.id;
}

function subscribeToRunEvents(runId, lastEventId) {
    closeProgressEventSource();
    progressRunId = runId;
    progressLastEventId = lastEventId || null;
    const url = `${State.getApiBase()}/runs/${runId}/events` + (progressLastEventId ? `?last_event_id=${progressLastEventId}` : '');
    console.log('[PROGRESS_UI] subscribing /runs/' + runId + '/events ...');
    const es = new EventSource(url);
    progressRunEventSource = es;
    es.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            handleRunEvent(data);
        } catch (err) {
            console.warn('[PROGRESS_UI] parse event error', err);
        }
    };
    es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) return;
        if (progressRunStatus === 'completed' || progressRunStatus === 'failed') {
            closeProgressEventSource();
            return;
        }
        addProgressLog('error', '연결 끊김');
    };
}

async function handleRunMeta(data) {
    const runId = data.run_id;
    if (!runId) return;
    console.log('[PROGRESS_UI] run_meta received run_id=' + runId);
    progressRunId = runId;
    const panel = document.getElementById('progressPanel');
    const details = document.getElementById('progressDetails');
    if (panel) {
        panel.classList.remove('hidden');
        if (details && !details.open) details.open = true;
    }
    try {
        const res = await fetch(`${State.getApiBase()}/runs/${runId}`, { headers: State.getAuthToken() ? { 'Authorization': 'Bearer ' + State.getAuthToken() } : {} });
        if (res.ok) {
            const snapshot = await res.json();
            const todosView = snapshot.todos_view && snapshot.todos_view.length > 0 ? snapshot.todos_view : [];
            const todos = todosView.length ? todosView : (snapshot.todos || []);
            progressTodosState = todos;
            progressRunStatus = (snapshot.status || '').toLowerCase();
            if (todos.length) {
                updateProgressTodos(todos);
                addProgressLog('info', todosView.length ? '할 일 3단계 로드됨' : ('할 일 ' + todos.length + '개 로드됨'));
            } else {
                updateProgressTodos([]);
                addProgressLog('info', '스냅샷 로드 (할 일 대기 중)');
            }
            progressLastEventId = snapshot.last_event_id || null;
        } else {
            addProgressLog('error', '스냅샷 조회 실패: ' + res.status);
        }
    } catch (e) {
        console.warn('[PROGRESS_UI] snapshot fetch failed', e);
        addProgressLog('error', '스냅샷 로드 실패');
    }
    subscribeToRunEvents(runId, progressLastEventId);
}

/**
 * [DEBUG Ver] 편집 백업 스냅샷 생성
 * - 실패 원인을 콘솔에 상세히 출력하도록 보강
 */
/**
 * [DEBUG Ver] 편집 백업 스냅샷 생성
 */
async function createEditBackup(originMessageId) {
    const sessionId = State.getCurrentSessionId();
    console.log(`📦 [Backup] Start for msg=${originMessageId}, session=${sessionId}`);

    if (!sessionId) {
        console.error('❌ [Backup] No Session ID');
        return;
    }

    try {
        const res = await fetch(`${State.getApiBase()}/chat/sessions/${sessionId}/messages`, {
            headers: State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {}
        });
        if (!res.ok) throw new Error('Failed to load session messages');
        
        const messages = await res.json();
        const idx = messages.findIndex(m => String(m.id) === String(originMessageId));
        
        if (idx < 0) {
            console.error(`❌ [Backup] Origin message ${originMessageId} NOT FOUND in list.`);
            throw new Error('Origin message not found');
        }

        const backupMessages = messages.slice(idx);

        State.getEditContext().backupMessages = backupMessages;
        State.getEditContext().backupSessionId = sessionId;
        State.getEditContext().backupFolderId = State.getCurrentFolderId();
        State.getEditContext().backupCreatedAt = new Date().toISOString();
        State.getEditContext().canRestore = false; 

        console.log(`✅ [Backup] Success! Snapshot size: ${backupMessages.length}`);
    } catch (e) {
        console.error('❌ [Backup] Error:', e);
    }
}
// 실제 버튼 부착 로직 분리
function attachBtnToBubble(bubble, mid) {
    // 2. 이미 버튼이 있으면 제거
    const existingBtn = bubble.querySelector('.btn-inline-restore');
    if (existingBtn) existingBtn.remove();

    // 3. relative 포지션 확인
    if (getComputedStyle(bubble).position === 'static') {
        bubble.classList.add('relative');
    }

    // 4. 버튼 생성 (위치: 안쪽 우측 하단)
    const restoreBtn = document.createElement('button');
    // z-index 높이고, 위치를 확실하게 안쪽으로 잡음
    restoreBtn.className = 'btn-inline-restore absolute -bottom-7 right-0 text-xs px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded-md shadow-sm transition-colors duration-200 flex items-center gap-1';
    restoreBtn.innerHTML = '<i class="fas fa-undo"></i> <span>복원</span>';
    restoreBtn.title = '이전 대화로 되돌리기';

    restoreBtn.onclick = (e) => {
        e.stopPropagation(); // 버블 클릭 이벤트 전파 방지
        console.log('🖱️ [UI] Restore button clicked');
        restoreFromBackup();
    };

    bubble.appendChild(restoreBtn);
    console.log(`✅ [UI] Button attached successfully to`, bubble);
}
/**
 * 메시지 전송 (간소화 버전)
 */
async function sendMessage(prompt = null, options = {}) {
    if (State.getIsGenerating()) return;
    const input = document.getElementById('messageInput');
    // ✅ [FIX] 인자로 받은 prompt 우선 사용 (Regenerate용)
    const question = prompt !== null ? prompt : input.value.trim();
    if(!question) return;

    // ✅ 편집 모드면: 적용 후 재전송
    if (prompt === null && State.getEditContext()?.active) {
        // 사용자가 입력창에서 수정한 텍스트로 확정
        await applyEditAndResend(question);
        return;
    }
    // ✅ [A안] options 기본값 설정
    const {
        skipAddUserMessage = false, // 기본값 false로 변경 (일반 전송 시 표시)
        isRegenerate = false,
        regenerateTargetMid = null,
        preserveRestore = false,
        plan_approved = false
    } = options;

    // ✅ [Regenerate] 사용자 메시지 전송 시작 → 이전 regenerate 버튼 모두 숨김
    if (!skipAddUserMessage) {
        updateRegenerateVisibility({ hideAll: true });
    }

    State.setIsGenerating(true); updateSendButtonState(true);
    State.setAbortController(new AbortController());

    // 새 요청 시 이전 run EventSource 정리 (새 run_meta 도착 시 재구독)
    closeProgressEventSource();
    closeTaskBlockEventSource(currentTaskBlockRunId);

    // ✅ [P0-2] 사용자 메시지 중복 생성 방지
    if (!skipAddUserMessage) {
        addMessageToUI('user', question);
    }

    // ✅ [FIX] 인자로 받은 경우 입력창 비우지 않음 (수동 입력만 비움)
    if(prompt === null) {
        input.value = '';
    }

    document.getElementById('statusText').textContent = 'Generating...';

    // ✅ [P0] 루프 감지 버퍼 초기화
    loopDetectionBuffer = "";

    requestStartTime = Date.now(); // 시간 측정 시작

    // 실시간 업데이트를 위한 메시지 컨테이너 생성 (생각 영역 분리)
    const container = document.getElementById('chatMessages');
    const streamDiv = document.createElement('div');
    streamDiv.className = 'flex justify-start mb-4';
    streamDiv.innerHTML = `
        <div class="max-w-[85%] rounded-xl px-4 py-3 message-assistant text-gray-100 shadow-lg relative">
            <details class="thought-accordion mb-3 opacity-60 text-xs border-b border-gray-700 pb-2" style="display:none;">
                <summary class="cursor-pointer hover:text-purple-400 flex items-center gap-2">
                    <i class="fas fa-brain text-purple-400"></i>
                    <span class="thought-status">🤔 생각 중...</span>
                    <span class="thought-length text-gray-500 ml-2"></span>
                </summary>
                <div class="thought-content p-3 mt-2 bg-black bg-opacity-40 rounded italic whitespace-pre-wrap max-h-64 overflow-y-auto"></div>
            </details>

            <div class="streaming-content whitespace-pre-wrap"></div>

            <div class="typing-indicator mt-2">
                <span class="inline-block w-2 h-2 bg-purple-400 rounded-full animate-bounce"></span>
                <span class="inline-block w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 0.1s"></span>
                <span class="inline-block w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></span>
            </div>
        </div>
    `;

    // ✅ [A안] dataset.originMid 태깅 (Regenerate 추적용)
    if (isRegenerate && regenerateTargetMid) {
        const bubbleEl = streamDiv.querySelector('.message-assistant');
        if (bubbleEl) {
            bubbleEl.dataset.originMid = String(regenerateTargetMid);
        }
    }

    // ✅ [HOT-SWAP] Regenerate 모드일 때 기존 버블 숨기기 (깜빡임 방지)
    let existingBubble = null;
    if (isRegenerate && regenerateTargetMid) {
        existingBubble = findBubbleByOriginMid(String(regenerateTargetMid));
        if (existingBubble) {
            existingBubble.style.opacity = '0.3';  // 반투명 처리 (생성 중 표시)
        }
    }

    container.appendChild(streamDiv);
    container.scrollTop = container.scrollHeight;

    let fullAnswer = "";
    let fullThought = "";  // 생각 내용 누적
    let isThinking = false;  // 현재 생각 중인지 여부
    let messageMetadata = {};

    try {
        const headers = { 'Content-Type': 'application/json' };
        if(State.getAuthToken()) headers['Authorization'] = `Bearer ${State.getAuthToken()}`;

        const res = await fetch(`${State.getApiBase()}/chat/ask`, {
            method: 'POST', headers,
            body: JSON.stringify({
                question, session_id: State.getCurrentSessionId(),
                folder_id: State.getCurrentFolderId(),
                temp_session_id: State.getTempSessionId() || null,
                mode: CURRENT_MODE,
                skip_user_message: skipAddUserMessage,
                plan_approved: plan_approved
            }),
            signal: State.getAbortController().signal
        });

        if(!res.ok) {
            if (res.status === 409) {
                const data = await res.json().catch(() => ({}));
                const msg = (typeof data.detail === 'string' ? data.detail : '이 세션에서 이미 요청을 처리 중입니다. 응답을 기다린 후 다시 시도해 주세요.');
                alert(msg);
            }
            throw new Error(`HTTP ${res.status}`);
        }

        // ✅ 스트리밍 응답 처리 (실시간 <think> 태그 분리)
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        const contentDiv = streamDiv.querySelector('.streaming-content');
        const thoughtAccordion = streamDiv.querySelector('.thought-accordion');
        const thoughtContent = streamDiv.querySelector('.thought-content');
        const thoughtStatus = streamDiv.querySelector('.thought-status');
        const thoughtLength = streamDiv.querySelector('.thought-length');

        let buffer = "";  // 청크 버퍼 (태그 경계 처리용)
        let sseEventType = null;  // run_meta 등 SSE event 타입 (다음 data: 라인에 적용)

        while(true) {
            const {done, value} = await reader.read();
            if(done) break;

            const chunk = decoder.decode(value, {stream: true});
            const lines = chunk.split('\n');

            for(const line of lines) {
                if (line.startsWith('event:')) {
                    sseEventType = line.slice(6).trim();
                    continue;
                }
                if(line.startsWith('data: ')) {
                    try {
                        // [JSON_PARSING_FIX] 빈 문자열이나 잘못된 형식 체크
                        const jsonStr = line.slice(6).trim();
                        if(!jsonStr || jsonStr.length === 0) {
                            sseEventType = null;
                            continue;  // 빈 라인은 무시
                        }
                        const jsonData = JSON.parse(jsonStr);

                        // run_meta: 첫 SSE 이벤트 → Progress 패널 표시 + 인채팅 TaskBlock 구독
                        const isRunMeta = sseEventType === 'run_meta' || (jsonData.run_id && jsonData.chunk === undefined && jsonData.done === undefined);
                        if (isRunMeta) {
                            if (typeof console !== 'undefined' && console.log) console.log('[TaskBlock] run_meta received run_id=', jsonData.run_id);
                            window._currentRunPlanOnly = !!jsonData.plan_only;
                            window._planOnlyUserInput = question;
                            handleRunMeta(jsonData);
                            handleRunMetaForTaskBlock(jsonData, streamDiv);
                            sseEventType = null;
                            continue;
                        }
                        sseEventType = null;

                        // 텍스트 청크 처리
                        if(jsonData.chunk) {
                            buffer += jsonData.chunk;

                            // ✅ <think> 태그 시작 감지
                            if(buffer.includes('<think>') && !isThinking) {
                                isThinking = true;
                                thoughtAccordion.style.display = 'block';  // 아코디언 표시

                                // <think> 앞부분은 일반 답변으로
                                const thinkStart = buffer.indexOf('<think>');
                                if(thinkStart > 0) {
                                    const beforeThink = buffer.substring(0, thinkStart);
                                    fullAnswer += beforeThink;
                                    contentDiv.textContent = fullAnswer;
                                }

                                // <think> 이후는 생각 영역으로
                                buffer = buffer.substring(buffer.indexOf('<think>') + 7);
                            }

                            // ✅ </think> 태그 종료 감지
                            if(buffer.includes('</think>') && isThinking) {
                                const thinkEnd = buffer.indexOf('</think>');
                                const thinkPart = buffer.substring(0, thinkEnd);
                                fullThought += thinkPart;
                                thoughtContent.textContent = fullThought;

                                // 생각 완료 표시
                                thoughtStatus.textContent = '✅ 생각 완료';
                                thoughtStatus.classList.remove('text-purple-400');
                                thoughtStatus.classList.add('text-green-400');
                                thoughtLength.textContent = `(${fullThought.length} chars)`;

                                // </think> 이후는 일반 답변으로
                                buffer = buffer.substring(thinkEnd + 8);
                                isThinking = false;

                                // 본론 시작 → 스크롤 조정
                                setTimeout(() => {
                                    contentDiv.scrollIntoView({behavior: 'smooth', block: 'nearest'});
                                }, 100);
                            }

                            // ✅ 현재 모드에 따라 텍스트 누적
                            if(isThinking) {
                                // 생각 중 → 생각 영역에 추가
                                fullThought += buffer;
                                thoughtContent.textContent = fullThought;
                                thoughtLength.textContent = `(${fullThought.length} chars)`;
                                buffer = "";
                            } else {
                                // 일반 답변 → 답변 영역에 추가
                                fullAnswer += buffer;
                                contentDiv.textContent = fullAnswer;

                                // ✅ [P0] 반복 루프 감지 및 자동 중단
                                if(detectRepetitionLoop(buffer)) {
                                    console.warn('⛔ [Auto-Stop] Repetition loop detected, aborting generation');
                                    State.getAbortController().abort();
                                    fullAnswer += '\n\n⛔ [자동 중단: 반복 루프 감지]';
                                    contentDiv.textContent = fullAnswer;
                                    break;  // 스트리밍 루프 탈출
                                }

                                buffer = "";
                                container.scrollTop = container.scrollHeight;
                            }
                        }

                        // 메타데이터 처리 (스트리밍 완료)
                        if(jsonData.done) {
                            messageMetadata = jsonData;
                            State.setCurrentSessionId(jsonData.session_id);
                            // 폴백: run_meta가 먼저 오지 않았을 때 done에 run_id 있으면 Progress 패널 표시 + 스냅샷 로드
                            if (jsonData.run_id) {
                                handleRunMeta({ run_id: jsonData.run_id });
                                if (!currentTaskBlockRunId) handleRunMetaForTaskBlock({ run_id: jsonData.run_id }, streamDiv);
                            }
                        }

                        // 에러 처리
                        if(jsonData.error) {
                            console.error('Streaming error:', jsonData.message);
                            const errorMsg = `\n\n⚠️ ${jsonData.message}`;
                            if(isThinking) {
                                fullThought += errorMsg;
                                thoughtContent.textContent = fullThought;
                            } else {
                                fullAnswer += errorMsg;
                                contentDiv.textContent = fullAnswer;
                            }
                        }
                    } catch(e) {
                        // [JSON_PARSING_FIX] JSON 파싱 오류를 더 자세히 로깅하고 안전하게 처리
                        if(e instanceof SyntaxError) {
                            console.warn(`[JSON Parse Error] Invalid JSON in SSE data: ${line.substring(0, 100)}...`, e);
                            // JSON 파싱 실패 시 해당 라인을 건너뛰고 계속 진행
                        } else {
                            console.warn('Failed to parse SSE data:', line.substring(0, 100), e);
                        }
                    }
                }
            }
        }

        // 타이핑 인디케이터 제거
        const typingIndicator = streamDiv.querySelector('.typing-indicator');
        if(typingIndicator) typingIndicator.remove();

        // 임시 스트림 div 제거하고 정식 메시지로 교체
        streamDiv.remove();

        // ✅ 최종 메시지 생성 (<think> 태그 포함하여 저장)
        const clientTimeTaken = (Date.now() - requestStartTime) / 1000;
        const finalTime = messageMetadata.processing_time || clientTimeTaken;

        // 생각 내용이 있으면 <think> 태그로 감싸서 전체 답변 구성
        let finalAnswerWithThought = fullAnswer;
        if(fullThought) {
            finalAnswerWithThought = `<think>${fullThought}</think>${fullAnswer}`;
        }

        // ✅ [A안] Regenerate 시 버전 저장 및 토글 UI 추가
        if (isRegenerate && regenerateTargetMid) {
            const originMid = String(regenerateTargetMid);

            if (!State.getAnswerVersions()[originMid]) {
                State.getAnswerVersions()[originMid] = { index: 0, items: [] };
            }

            State.getAnswerVersions()[originMid].items.push({
                content: finalAnswerWithThought,
                metadata: {
                    rag_used: messageMetadata.rag_used,
                    auto_selected: messageMetadata.auto_selected,
                    selected_mode: messageMetadata.selected_mode,
                    processing_time: finalTime
                },
                ts: Date.now()
            });

            State.getAnswerVersions()[originMid].index = State.getAnswerVersions()[originMid].items.length - 1;
        }

        const originKey = String(isRegenerate ? regenerateTargetMid : messageMetadata.message_id);

        // ✅ Evolution → Patch: 서버가 content_display(patch_report) + evolution_payload 보냈으면 그대로 표시
        const displayContent = (messageMetadata.content_display != null && messageMetadata.content_display !== '') ? messageMetadata.content_display : finalAnswerWithThought;
        const evolutionPayloadFromMeta = messageMetadata.evolution_payload || null;

        // ✅ plan_only run 종료 시 최종 버블에 계획 카드/진행하기 버튼 표시용 planCard
        let planCard = null;
        if (window._currentRunPlanOnly && currentTaskBlockRunId && currentTaskBlockState && Array.isArray(currentTaskBlockState.todos) && currentTaskBlockState.todos.length > 0) {
            const userInput = (window._planOnlyUserInput || question || '').trim();
            if (userInput) {
                planCard = {
                    run_id: currentTaskBlockRunId,
                    todos: currentTaskBlockState.todos,
                    user_input: userInput
                };
            }
        }

        // ✅ originKey가 유효할 때 prompt 스냅샷 저장
        if (originKey && originKey !== "null" && originKey !== "undefined") {
          if (!State.getAnswerVersions()[originKey]) State.getAnswerVersions()[originKey] = { index: 0, items: [], prompt: "" };
          if (!State.getAnswerVersions()[originKey].prompt) State.getAnswerVersions()[originKey].prompt = question; 
        }

        // ✅ [HOT-SWAP] Regenerate 시 기존 버블 업데이트 (새 버블 생성 안 함!)
        if (isRegenerate && regenerateTargetMid) {
            const originMid = String(regenerateTargetMid);
            const bubbleEl = findBubbleByOriginMid(originMid);

            if (bubbleEl) {
                // 1. 내용 업데이트 (텍스트 교체)
                let contentDiv = bubbleEl.querySelector('.actual-answer') || bubbleEl.querySelector('.whitespace-pre-wrap');

                // <think> 태그 처리
                if (finalAnswerWithThought.includes('<think>')) {
                    const parts = finalAnswerWithThought.split('</think>');
                    const thinkContent = parts[0].replace('<think>', '').trim();
                    const answerContent = parts[1] ? parts[1].trim() : '';

                    const thoughtDetails = bubbleEl.querySelector('details');
                    if (thoughtDetails) {
                        const thoughtContentDiv = thoughtDetails.querySelector('.thought-content');
                        if (thoughtContentDiv) thoughtContentDiv.textContent = thinkContent;
                    }
                    if (contentDiv) contentDiv.textContent = answerContent;
                } else {
                    if (contentDiv) contentDiv.textContent = finalAnswerWithThought;
                }

                // 2. 메타데이터 업데이트
                const timeSpan = bubbleEl.querySelector('span.font-mono');
                if (timeSpan && finalTime) {
                    timeSpan.textContent = `⏱️ ${parseFloat(finalTime).toFixed(2)}s`;
                }

                // 3. plan_only면 계획 카드/진행하기 버튼 주입 (재렌더 동기화)
                if (planCard && !bubbleEl.querySelector('.plan-approval-card')) {
                    const list = planCard.todos.map(t => ({ todo_id: t.id, id: t.id, title: t.title || t.id }));
                    injectPlanCardIntoBubble(bubbleEl, list);
                }

                // 4. 네비게이션 UI 업데이트
                setTimeout(() => {
                    attachOrUpdateVersionControls(bubbleEl, originMid);
                }, 100);

                // 5. 기존 버블 opacity 복원
                if (bubbleEl.style.opacity === '0.3') {
                    bubbleEl.style.opacity = '1';
                }

            } else {
                addMessageToUI('assistant', displayContent, messageMetadata.rag_used, messageMetadata.message_id, null, messageMetadata.auto_selected, messageMetadata.selected_mode, finalTime, originKey, currentTaskBlockState, planCard, evolutionPayloadFromMeta);
            }
        } else {
            // ✅ 일반 모드: 새 버블 생성 (planCard 넘기면 카드+진행하기 버튼 표시, evolution_payload면 접힌 상세)
            addMessageToUI('assistant', displayContent, messageMetadata.rag_used, messageMetadata.message_id, null, messageMetadata.auto_selected, messageMetadata.selected_mode, finalTime, originKey, currentTaskBlockState, planCard, evolutionPayloadFromMeta);
        }
        closeTaskBlockEventSource(currentTaskBlockRunId);
        currentTaskBlockRunId = null;
        currentTaskBlockState = null;
        currentTaskBlockBubbleRef = null;
        taskBlockLastRenderedSnapshot = '';

        document.getElementById('statusText').textContent = 'Ready';
        if(State.getAuthToken()) await loadUncategorizedSessions();

    } catch(e) {
        console.error('Streaming error:', e);

        // ✅ [FIX] Stop 버튼 클릭 시 응답 보존
        if(e.name === 'AbortError') {
            const typingIndicator = streamDiv.querySelector('.typing-indicator');
            if(typingIndicator) typingIndicator.remove();
            streamDiv.remove();

            let finalAnswerWithThought = fullAnswer;
            if(fullThought) {
                finalAnswerWithThought = `<think>${fullThought}</think>${fullAnswer}`;
            }
            const stoppedMessage = finalAnswerWithThought + (fullAnswer ? '\n\n' : '') + '⏸️ [사용자에 의해 중단되었습니다]';
            const fallbackOrigin = String(messageMetadata.message_id || `local_${Date.now()}`);
            
            addMessageToUI('assistant', stoppedMessage, messageMetadata.rag_used || false, messageMetadata.message_id || null, null, messageMetadata.auto_selected || false, messageMetadata.selected_mode || null, null, fallbackOrigin, currentTaskBlockState);
        } else {
            streamDiv.remove();
            addMessageToUI('assistant', `⚠️ 스트리밍 오류: ${e.message}`);
        }
        closeTaskBlockEventSource(currentTaskBlockRunId);
        currentTaskBlockRunId = null;
        currentTaskBlockState = null;
        currentTaskBlockBubbleRef = null;
        taskBlockLastRenderedSnapshot = '';
    } finally {
        State.setIsGenerating(false);
        State.setAbortController(null);
        updateSendButtonState(false);
        const statusText = document.getElementById('statusText');
        if (statusText) statusText.textContent = 'Ready';

        if (existingBubble && existingBubble.style.opacity === '0.3') {
            existingBubble.style.opacity = '1';
        }
        if (State.getEditContext()?.canRestore && !preserveRestore) { // 🆕 !preserveRestore 조건 추가
            State.getEditContext().canRestore = false;
            hideEditWarningBar();
        }
    }
}


/***
 * 사용자 메시지 수정 및 재전송
 */
// EDIT_CONTEXT는 state.js에서 초기화됨

/**
 * [FINAL] 수정 모드 진입 함수
 */
async function startEditMessage(btn) {
    console.log('🚀 [Logic] Start Edit Triggered');

    if (State.getIsGenerating()) {
        return alert("⚠️ AI가 답변을 생성 중입니다. 잠시만 기다려주세요.");
    }

    // 1. 버블 찾기 (message-user)
    const bubble = btn.closest('.message-user');
    if (!bubble) return console.error('❌ User bubble not found');

    const mid = bubble.dataset.messageId || bubble.getAttribute('data-message-id');

   // 2. 텍스트 영역 찾기
   const contentDiv = bubble.querySelector('.whitespace-pre-wrap') || bubble.querySelector('.prose');
   if (!contentDiv) return console.error('❌ Content div not found');

   if (contentDiv.querySelector('textarea')) return; // 중복 실행 방지

    // 3. 백업 및 컨텍스트 초기화
    const currentText = contentDiv.innerText.trim();
    const originalHtml = contentDiv.innerHTML;
    
    Object.assign(State.getEditContext(), {
        active: true,
        originMessageId: mid,
        originText: currentText,
        draftBeforeEdit: currentText,
        canRestore: false,
        backupMessages: []
    });

    // [FIX] 🧨 핵심: 서버에서 백업 데이터 가져오기 (이게 없어서 안 됐던 것임!)
    // (UI가 약간 늦게 떠도 데이터를 확실히 챙겨야 함)
    await createEditBackup(mid);

    // 4. UI 교체
    contentDiv.innerHTML = `
        <div class="edit-wrapper w-full mt-2">
            <textarea class="w-full p-3 bg-gray-800 text-gray-100 rounded-lg border border-gray-600 focus:outline-none focus:border-blue-500 resize-y" 
                      rows="3" style="min-height: 80px;">${currentText}</textarea>
            <div class="flex justify-end space-x-2 mt-2">
                <button class="cancel-btn px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-sm">Cancel</button>
                <button class="save-btn px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-bold">Save</button>
            </div>
        </div>
    `;

    const wrapper = contentDiv.querySelector('.edit-wrapper');
    const editInput = wrapper.querySelector('textarea');
    
    // 취소 버튼
    wrapper.querySelector('.cancel-btn').onclick = (e) => {
        e.stopPropagation();
        contentDiv.innerHTML = originalHtml;
        State.getEditContext().active = false;
    };

    // ----------------------------------------------------
    // [핵심] 저장 버튼 핸들러: DOM 구조 정확히 타겟팅하여 삭제
    // ----------------------------------------------------
    wrapper.querySelector('.save-btn').onclick = async (e) => {
        e.stopPropagation();
        const newText = wrapper.querySelector('textarea').value.trim();
        if (!newText) return;

        // 1. UI 즉시 반영 (편집창 닫기)
        contentDiv.innerHTML = newText.replace(/\n/g, '<br>');
        
        // 2. [PRUNING] 옛날 AI 답변 즉시 제거
        // .message-user는 .flex(Row) 안에 있음. 형제 요소는 .flex 레벨에서 찾아야 함.
        const messageRow = bubble.closest('.flex'); // 현재 질문의 줄(Row)
        
        if (messageRow) {
            console.log('✂️ [Pruning] Scanning for old AI responses...');
            let sibling = messageRow.nextElementSibling;
            
            while (sibling) {
                // 다음 형제가 AI 메시지인지 확인 (assistant 메시지도 .flex로 감싸져 있음)
                const isAssistant = sibling.querySelector('.message-assistant') || 
                                    sibling.querySelector('[data-role="assistant"]');
                
                // 만약 유저 메시지를 만나면 중단 (다음 턴이므로)
                const isUser = sibling.querySelector('.message-user') || 
                               sibling.querySelector('[data-role="user"]');
                
                if (isUser) break;

                if (isAssistant) {
                    const next = sibling.nextElementSibling;
                    sibling.remove(); // 💥 화면에서 삭제
                    console.log('🗑️ Removed old AI response');
                    sibling = next;
                } else {
                    sibling = sibling.nextElementSibling;
                }
            }
        }

        // 3. 수정 모드 종료
        State.getEditContext().active = false;

        // 4. 전송 (기존 UI를 수정했으므로 skipAddUserMessage: true로 전송)
        if (mid && typeof applyEditAndResend === 'function') {
            await applyEditAndResend(newText);
        } else {
            // ID가 없어도 화면은 이미 고쳤으니 스텔스 전송
            await sendMessage(newText, { skipAddUserMessage: true });
        }
    };
    
    if (editInput) {
        editInput.focus();
        editInput.setSelectionRange(editInput.value.length, editInput.value.length);
    }
}

async function applyEditAndResend(editedText) {
    const sessionId = State.getCurrentSessionId();
    const originId = State.getEditContext().originMessageId;
    if (!sessionId || !originId) return;

    try {
        // 1. 서버 데이터 정리 (삭제 기다림)
        const res = await fetch(`${State.getApiBase()}/chat/sessions/${sessionId}/messages`, {
            headers: State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {}
        });
        if (res.ok) {
            const messages = await res.json();
            const idx = messages.findIndex(m => String(m.id) === String(originId));
            if (idx >= 0) {
                const toDelete = messages.slice(idx).map(m => m.id);
                await Promise.all(toDelete.map(mid => 
                    fetch(`${State.getApiBase()}/chat/messages/${mid}`, {
                        method: 'DELETE',
                        headers: State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {}
                    })
                ));
            }
        }

        // 2. 구형 사용자 말풍선 UI 제거 (새로 보낼 것이므로)
        const oldBubble = document.querySelector(`[data-message-id="${originId}"]`);
        if(oldBubble && oldBubble.closest('.flex')) oldBubble.closest('.flex').remove();

        State.getEditContext().canRestore = true;

        // 3. 새 메시지 전송 (화면에 추가됨)
        document.getElementById('messageInput').value = '';
        await sendMessage(editedText, { 
            skipAddUserMessage: false, 
            preserveRestore: true 
        });

        // 4. 복원 버튼 달기
        setTimeout(() => {
            renderInlineRestoreBtn('last'); 
        }, 600);

    } catch (e) {
        console.error('❌ [Edit] applyEditAndResend failed:', e);
    }
}

  /**
   * 복원 경고바 표시
   */
  function showRestoreWarning() {
    const bar = document.getElementById('editWarningBar');
    if (!bar) return;

    bar.innerHTML = `
      <div class="edit-warning-text">✅ 수정 적용됨. 이전 대화로 되돌리기 가능합니다.</div>
      <button id="restoreBtn" class="edit-warning-cancel" style="background: #10b981;">복원</button>
    `;
    bar.style.display = 'flex';
    bar.style.background = 'linear-gradient(90deg, #10b981 0%, #059669 100%)'; // 녹색

    const btn = document.getElementById('restoreBtn');
    btn.onclick = restoreFromBackup;
  }

/**
 * [DEBUG Ver] 인라인 복원 버튼 렌더링
 * - 버튼 위치 강제 조정 및 찾기 실패 시 로그 출력
 */
function renderInlineRestoreBtn(messageId) {
    console.log(`🎨 [UI] Trying to attach button to msg=${messageId}`);

    let bubble = null;

    // 1. 타겟 버블 찾기
    if (messageId === 'last') {
        bubble = document.querySelector('.message-user:last-of-type');
        if (bubble) console.log('🔄 [UI] Targeted last user message directly');
    } else {
        bubble = document.querySelector(`.message-user[data-message-id="${messageId}"]`) || 
                 document.querySelector(`.message-user[data-mid="${messageId}"]`);
        
        if (!bubble) {
            bubble = document.querySelector('.message-user:last-of-type');
            if (bubble) console.log('🔄 [UI] Fallback to last user message (ID mismatch)');
        }
    }

    if (!bubble) {
        console.warn('⚠️ [UI] Target bubble not found');
        return;
    }

    const existingBtn = bubble.querySelector('.btn-inline-restore');
    if (existingBtn) existingBtn.remove();

    if (getComputedStyle(bubble).position === 'static') {
        bubble.classList.add('relative');
    }

    const restoreBtn = document.createElement('button');
    restoreBtn.className = 'btn-inline-restore absolute bottom-2 right-2 text-[10px] px-2 py-1 bg-black/40 hover:bg-emerald-600 text-white/70 hover:text-white rounded-md backdrop-blur-sm transition-all duration-200 flex items-center gap-1 z-10';
    restoreBtn.innerHTML = '<i class="fas fa-undo"></i> <span>복원</span>';
    restoreBtn.title = '이전 대화로 되돌리기';

    restoreBtn.onclick = (e) => {
        e.stopPropagation();
        console.log('🖱️ [UI] Restore button clicked');
        restoreFromBackup();
    };

    bubble.appendChild(restoreBtn);
    console.log(`✅ [UI] Button attached`);
}

/**
 * [NEW] ID 조용히 동기화 (화면 깜빡임/삭제 방지)
 */
async function syncMessageIds(sessionId) {
    if (!sessionId) return;
    try {
        // 화면을 지우지 않고 데이터만 가져옴
        const res = await fetch(`${State.getApiBase()}/chat/sessions/${sessionId}/messages`, {
            headers: State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {}
        });
        if (!res.ok) return;
        const messages = await res.json();

        // 1. 마지막 User 메시지 ID 업데이트
        const userMsgs = messages.filter(m => m.role === 'user');
        if (userMsgs.length > 0) {
            const lastDBMsg = userMsgs[userMsgs.length - 1];
            const domUserMsgs = document.querySelectorAll('.message-user');
            const lastDomMsg = domUserMsgs[domUserMsgs.length - 1];

            if (lastDomMsg && (!lastDomMsg.dataset.messageId || lastDomMsg.dataset.messageId === "null")) {
                lastDomMsg.dataset.messageId = lastDBMsg.id;
                lastDomMsg.dataset.mid = lastDBMsg.id;
                console.log(`🔄 [Sync] Updated User Message ID: ${lastDBMsg.id}`);
            }
        }
        
        // 2. 마지막 Assistant 메시지 ID 업데이트 (안전을 위해)
        const assistMsgs = messages.filter(m => m.role === 'assistant');
        if (assistMsgs.length > 0) {
            const lastDBMsg = assistMsgs[assistMsgs.length - 1];
            const domAssistMsgs = document.querySelectorAll('.message-assistant');
            const lastDomMsg = domAssistMsgs[domAssistMsgs.length - 1];

            if (lastDomMsg && (!lastDomMsg.dataset.messageId || lastDomMsg.dataset.messageId === "null")) {
                lastDomMsg.dataset.messageId = lastDBMsg.id;
                lastDomMsg.dataset.mid = lastDBMsg.id;
            }
        }
    } catch (e) {
        console.warn('Silent sync warning:', e);
    }
}

/**
 * 메시지 전송 (핵심 로직 - 수정됨)
 */
async function sendMessage(prompt = null, options = {}) {
    const input = document.getElementById('messageInput');
    const question = prompt !== null ? prompt : input.value.trim();
    if(!question) return;

    if (prompt === null && State.getEditContext()?.active) {
        await applyEditAndResend(question);
        return;
    }
    
    const {
        skipAddUserMessage = false, 
        isRegenerate = false,
        regenerateTargetMid = null,
        preserveRestore = false,
        plan_approved = false
    } = options;

    if (!skipAddUserMessage) {
        updateRegenerateVisibility({ hideAll: true });
    }

    State.setIsGenerating(true); updateSendButtonState(true);
    State.setAbortController(new AbortController());

    if (!skipAddUserMessage) {
        addMessageToUI('user', question);
    }

    if(prompt === null) {
        input.value = '';
    }

    document.getElementById('statusText').textContent = 'Generating...';
    loopDetectionBuffer = "";
    requestStartTime = Date.now();

    const container = document.getElementById('chatMessages');
    const streamDiv = document.createElement('div');
    streamDiv.className = 'flex justify-start mb-4';
    streamDiv.innerHTML = `
        <div class="max-w-[85%] rounded-xl px-4 py-3 message-assistant text-gray-100 shadow-lg relative">
            <details class="thought-accordion mb-3 opacity-60 text-xs border-b border-gray-700 pb-2" style="display:none;">
                <summary class="cursor-pointer hover:text-purple-400 flex items-center gap-2">
                    <i class="fas fa-brain text-purple-400"></i>
                    <span class="thought-status">🤔 생각 중...</span>
                    <span class="thought-length text-gray-500 ml-2"></span>
                </summary>
                <div class="thought-content p-3 mt-2 bg-black bg-opacity-40 rounded italic whitespace-pre-wrap max-h-64 overflow-y-auto"></div>
            </details>
            <div class="streaming-content whitespace-pre-wrap"></div>
            <div class="typing-indicator mt-2">
                <span class="inline-block w-2 h-2 bg-purple-400 rounded-full animate-bounce"></span>
                <span class="inline-block w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 0.1s"></span>
                <span class="inline-block w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></span>
            </div>
        </div>
    `;

    if (isRegenerate && regenerateTargetMid) {
        const bubbleEl = streamDiv.querySelector('.message-assistant');
        if (bubbleEl) bubbleEl.dataset.originMid = String(regenerateTargetMid);
    }

    let existingBubble = null;
    if (isRegenerate && regenerateTargetMid) {
        existingBubble = findBubbleByOriginMid(String(regenerateTargetMid));
        if (existingBubble) existingBubble.style.opacity = '0.3';
    }

    container.appendChild(streamDiv);
    container.scrollTop = container.scrollHeight;

    let fullAnswer = "";
    let fullThought = "";
    let isThinking = false;
    let messageMetadata = {};

    try {
        const headers = { 'Content-Type': 'application/json' };
        if(State.getAuthToken()) headers['Authorization'] = `Bearer ${State.getAuthToken()}`;

        const res = await fetch(`${State.getApiBase()}/chat/ask`, {
            method: 'POST', headers,
            body: JSON.stringify({
                question, session_id: State.getCurrentSessionId(),
                folder_id: State.getCurrentFolderId(),
                temp_session_id: State.getTempSessionId() || null,
                mode: CURRENT_MODE,
                skip_user_message: skipAddUserMessage,
                plan_approved: plan_approved
            }),
            signal: State.getAbortController().signal
        });

        if(!res.ok) throw new Error(`HTTP ${res.status}`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        const contentDiv = streamDiv.querySelector('.streaming-content');
        const thoughtAccordion = streamDiv.querySelector('.thought-accordion');
        const thoughtContent = streamDiv.querySelector('.thought-content');
        const thoughtStatus = streamDiv.querySelector('.thought-status');
        const thoughtLength = streamDiv.querySelector('.thought-length');

        let buffer = "";
        let sseEventType = null;

        while(true) {
            const {done, value} = await reader.read();
            if(done) break;

            const chunk = decoder.decode(value, {stream: true});
            const lines = chunk.split('\n');

            for(const line of lines) {
                if (line.startsWith('event:')) {
                    sseEventType = line.slice(6).trim();
                    continue;
                }
                if(line.startsWith('data: ')) {
                    try {
                        // [JSON_PARSING_FIX] 빈 문자열이나 잘못된 형식 체크
                        const jsonStr = line.slice(6).trim();
                        if(!jsonStr || jsonStr.length === 0) {
                            sseEventType = null;
                            continue;  // 빈 라인은 무시
                        }
                        const jsonData = JSON.parse(jsonStr);

                        const isRunMeta = sseEventType === 'run_meta' || (jsonData.run_id && jsonData.chunk === undefined && jsonData.done === undefined);
                        if (isRunMeta) {
                            if (typeof console !== 'undefined' && console.log) console.log('[TaskBlock] run_meta received run_id=', jsonData.run_id);
                            window._currentRunPlanOnly = !!jsonData.plan_only;
                            window._planOnlyUserInput = question;
                            handleRunMeta(jsonData);
                            handleRunMetaForTaskBlock(jsonData, streamDiv);
                            sseEventType = null;
                            continue;
                        }
                        sseEventType = null;

                        if(jsonData.chunk) {
                            buffer += jsonData.chunk;

                            if(buffer.includes('<think>') && !isThinking) {
                                isThinking = true;
                                thoughtAccordion.style.display = 'block';
                                const thinkStart = buffer.indexOf('<think>');
                                if(thinkStart > 0) {
                                    fullAnswer += buffer.substring(0, thinkStart);
                                    contentDiv.textContent = fullAnswer;
                                }
                                buffer = buffer.substring(buffer.indexOf('<think>') + 7);
                            }

                            if(buffer.includes('</think>') && isThinking) {
                                const thinkEnd = buffer.indexOf('</think>');
                                fullThought += buffer.substring(0, thinkEnd);
                                thoughtContent.textContent = fullThought;
                                thoughtStatus.textContent = '✅ 생각 완료';
                                thoughtStatus.classList.replace('text-purple-400', 'text-green-400');
                                thoughtLength.textContent = `(${fullThought.length} chars)`;
                                buffer = buffer.substring(thinkEnd + 8);
                                isThinking = false;
                                setTimeout(() => contentDiv.scrollIntoView({behavior: 'smooth', block: 'nearest'}), 100);
                            }

                            if(isThinking) {
                                fullThought += buffer;
                                thoughtContent.textContent = fullThought;
                                thoughtLength.textContent = `(${fullThought.length} chars)`;
                                buffer = "";
                            } else {
                                fullAnswer += buffer;
                                contentDiv.textContent = fullAnswer;
                                if(detectRepetitionLoop(buffer)) {
                                    State.getAbortController().abort();
                                    fullAnswer += '\n\n⛔ [자동 중단: 반복 루프 감지]';
                                    contentDiv.textContent = fullAnswer;
                                    break;
                                }
                                buffer = "";
                                container.scrollTop = container.scrollHeight;
                            }
                        }

                        if(jsonData.done) {
                            messageMetadata = jsonData;
                            State.setCurrentSessionId(jsonData.session_id);
                            if (jsonData.run_id) {
                                handleRunMeta({ run_id: jsonData.run_id });
                                if (!currentTaskBlockRunId) handleRunMetaForTaskBlock({ run_id: jsonData.run_id }, streamDiv);
                            }
                        }
                    } catch(e) {
                        // [JSON_PARSING_FIX] JSON 파싱 오류를 더 자세히 로깅하고 안전하게 처리
                        if(e instanceof SyntaxError) {
                            console.warn(`[JSON Parse Error] Invalid JSON in SSE data: ${line.substring(0, 100)}...`, e);
                            // JSON 파싱 실패 시 해당 라인을 건너뛰고 계속 진행
                        } else {
                            console.warn('Failed to parse SSE data:', line.substring(0, 100), e);
                        }
                    }
                }
            }
        }

        const typingIndicator = streamDiv.querySelector('.typing-indicator');
        if(typingIndicator) typingIndicator.remove();
        streamDiv.remove();

        const clientTimeTaken = (Date.now() - requestStartTime) / 1000;
        const finalTime = messageMetadata.processing_time || clientTimeTaken;
        let finalAnswerWithThought = fullThought ? `<think>${fullThought}</think>${fullAnswer}` : fullAnswer;

        // Versioning Logic
        const originKey = String(isRegenerate ? regenerateTargetMid : messageMetadata.message_id);
        if (originKey && originKey !== "null") {
            if (!State.getAnswerVersions()[originKey]) State.getAnswerVersions()[originKey] = { index: 0, items: [], prompt: "" };
            if (!State.getAnswerVersions()[originKey].prompt) State.getAnswerVersions()[originKey].prompt = question; 
        }

        if (isRegenerate && regenerateTargetMid) {
            const originMid = String(regenerateTargetMid);
            if (!State.getAnswerVersions()[originMid]) State.getAnswerVersions()[originMid] = { index: 0, items: [] };
            State.getAnswerVersions()[originMid].items.push({
                content: finalAnswerWithThought,
                metadata: { ...messageMetadata, processing_time: finalTime },
                ts: Date.now()
            });
            State.getAnswerVersions()[originMid].index = State.getAnswerVersions()[originMid].items.length - 1;

            const bubbleEl = findBubbleByOriginMid(String(regenerateTargetMid));
            if (bubbleEl) {
                let contentDiv = bubbleEl.querySelector('.actual-answer') || bubbleEl.querySelector('.whitespace-pre-wrap');
                if (fullThought) {
                    const tContent = bubbleEl.querySelector('.thought-content');
                    if(tContent) tContent.textContent = fullThought;
                    if(contentDiv) contentDiv.textContent = fullAnswer;
                } else {
                    if(contentDiv) contentDiv.textContent = finalAnswerWithThought;
                }
                const timeSpan = bubbleEl.querySelector('span.font-mono');
                if(timeSpan) timeSpan.textContent = `⏱️ ${parseFloat(finalTime).toFixed(2)}s`;
                setTimeout(() => attachOrUpdateVersionControls(bubbleEl, String(regenerateTargetMid)), 100);
                if(bubbleEl.style.opacity === '0.3') bubbleEl.style.opacity = '1';
            } else {
                addMessageToUI('assistant', finalAnswerWithThought, messageMetadata.rag_used, messageMetadata.message_id, null, messageMetadata.auto_selected, messageMetadata.selected_mode, finalTime, originKey, currentTaskBlockState);
            }
        } else {
            addMessageToUI('assistant', finalAnswerWithThought, messageMetadata.rag_used, messageMetadata.message_id, null, messageMetadata.auto_selected, messageMetadata.selected_mode, finalTime, originKey, currentTaskBlockState);
        }
        closeTaskBlockEventSource(currentTaskBlockRunId);
        currentTaskBlockRunId = null;
        currentTaskBlockState = null;
        currentTaskBlockBubbleRef = null;
        taskBlockLastRenderedSnapshot = '';

        document.getElementById('statusText').textContent = 'Ready';
        
        // 💎 [CRITICAL FIX] loadSession 대신 조용한 ID 동기화 호출
        // 이제 화면이 사라지거나 깜빡이지 않습니다.
        if (State.getAuthToken() && State.getCurrentSessionId() && !isRegenerate) {
            await syncMessageIds(State.getCurrentSessionId());
        } else {
            await loadUncategorizedSessions(); // 사이드바 목록만 갱신
        }

    } catch(e) {
        console.error('Streaming error:', e);
        if(e.name === 'AbortError') {
            streamDiv.remove();
            let msg = (fullThought ? `<think>${fullThought}</think>` : '') + fullAnswer + (fullAnswer ? '\n\n' : '') + '⏸️ [중단됨]';
            addMessageToUI('assistant', msg, false, null, null, false, null, null, null, currentTaskBlockState);
        } else {
            streamDiv.remove();
            addMessageToUI('assistant', `⚠️ 오류: ${e.message}`);
        }
        closeTaskBlockEventSource(currentTaskBlockRunId);
        currentTaskBlockRunId = null;
        currentTaskBlockState = null;
        currentTaskBlockBubbleRef = null;
        taskBlockLastRenderedSnapshot = '';
    } finally {
        State.setIsGenerating(false);
        State.setAbortController(null);
        updateSendButtonState(false);
        if (existingBubble && existingBubble.style.opacity === '0.3') existingBubble.style.opacity = '1';
        
        if (State.getEditContext()?.canRestore && !preserveRestore) {
            State.getEditContext().canRestore = false;
        }
    }
}

/**
 * [FINAL] 수정 모드 진입
 */
async function startEditMessage(btn) {
    if (State.getIsGenerating()) return alert("⚠️ 생성 중입니다.");

    const bubble = btn.closest('.message-user');
    if (!bubble) return;

    const mid = bubble.dataset.messageId || bubble.getAttribute('data-message-id');
    if (!mid) {
        alert("⚠️ 아직 저장되지 않은 메시지입니다. 잠시 후 다시 시도해주세요.");
        // 여기서도 sync 한 번 시도해주면 좋음
        if(State.getCurrentSessionId()) await syncMessageIds(State.getCurrentSessionId());
        return;
    }

    const contentDiv = bubble.querySelector('.whitespace-pre-wrap') || bubble.querySelector('.prose');
    if (!contentDiv || contentDiv.querySelector('textarea')) return;

    const currentText = contentDiv.innerText.trim();
    const originalHtml = contentDiv.innerHTML;
    Object.assign(State.getEditContext(), {
        active: true,
        originMessageId: mid,
        originText: currentText,
        draftBeforeEdit: currentText,
        canRestore: false,
        backupMessages: []
    });
    await createEditBackup(mid);

    contentDiv.innerHTML = `
        <div class="edit-wrapper w-full mt-2">
            <textarea class="w-full p-3 bg-gray-800 text-gray-100 rounded-lg border border-gray-600 focus:outline-none focus:border-blue-500 resize-y" rows="3">${currentText}</textarea>
            <div class="flex justify-end space-x-2 mt-2">
                <button class="cancel-btn px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-sm">Cancel</button>
                <button class="save-btn px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-bold">Save</button>
            </div>
        </div>
    `;

    const wrapper = contentDiv.querySelector('.edit-wrapper');
    const editInput = wrapper.querySelector('textarea');
    
    wrapper.querySelector('.cancel-btn').onclick = (e) => {
        e.stopPropagation();
        contentDiv.innerHTML = originalHtml;
        State.getEditContext().active = false;
    };

    wrapper.querySelector('.save-btn').onclick = async (e) => {
        e.stopPropagation();
        const newText = wrapper.querySelector('textarea').value.trim();
        if (!newText) return;

        // 1. UI 반영 & 구형 AI 답변 제거 (Pruning)
        contentDiv.innerHTML = newText.replace(/\n/g, '<br>');
        
        const messageRow = bubble.closest('.flex'); 
        if (messageRow) {
            let sibling = messageRow.nextElementSibling;
            while (sibling) {
                const isAssistant = sibling.querySelector('.message-assistant') || sibling.querySelector('[data-role="assistant"]');
                const isUser = sibling.querySelector('.message-user');
                if (isUser) break;
                if (isAssistant) {
                    const next = sibling.nextElementSibling;
                    sibling.remove(); 
                    sibling = next;
                } else sibling = sibling.nextElementSibling;
            }
        }

        State.getEditContext().active = false;

        // 2. 전송
        await applyEditAndResend(newText);
    };
    
    if (editInput) {
        editInput.focus();
        editInput.setSelectionRange(editInput.value.length, editInput.value.length);
    }
}

  /**
   * 백업에서 복원
   */
  async function restoreFromBackup() {
    if (State.getIsGenerating()) return alert('생성 중에는 복원할 수 없습니다.');
    if (!State.getEditContext()?.canRestore) return alert('복원 가능한 백업이 없습니다.');

    const sessionId = State.getEditContext().backupSessionId;
    const backupMessages = State.getEditContext().backupMessages;

    if (!sessionId || !backupMessages?.length) return alert('백업 데이터가 없습니다.');
    if (!confirm(`${backupMessages.length}개 메시지를 복원하시겠습니까?`)) return;

    try {
        document.getElementById('statusText').textContent = '복원 중...';

        // 1. 현재 세션 메시지 전체 삭제
        const currentRes = await fetch(`${State.getApiBase()}/chat/sessions/${sessionId}/messages`, {
            headers: State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {}
        });
        if (currentRes.ok) {
            const currentMessages = await currentRes.json();
            for (const msg of currentMessages) {
                await fetch(`${State.getApiBase()}/chat/messages/${msg.id}`, {
                    method: 'DELETE',
                    headers: State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {}
                });
            }
        }

        // 2. 백업 메시지 복원
        const restorePayload = {
            messages: backupMessages.map(m => ({
                role: m.role,
                content: m.content,
                rag_used: m.rag_used || false,
                auto_selected: m.auto_selected || false,
                selected_mode: m.selected_mode || null,
                processing_time: m.processing_time || null,
                timestamp: m.timestamp || new Date().toISOString()
            }))
        };

        const restoreRes = await fetch(`${State.getApiBase()}/chat/sessions/${sessionId}/restore_messages`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {})
            },
            body: JSON.stringify(restorePayload)
        });

        if (!restoreRes.ok) throw new Error(await restoreRes.text());

        // 3. 화면 갱신 (복원 시에는 전체 리로드가 맞음)
        await loadSession(sessionId, State.getEditContext().backupFolderId);

        State.getEditContext().canRestore = false;
        document.getElementById('statusText').textContent = 'Ready';
        alert('✅ 복원 완료');

    } catch (e) {
        console.error('❌ [Restore] Error:', e);
        alert(`복원 실패: ${e.message}`);
        document.getElementById('statusText').textContent = 'Ready';
    }
}

//응답 재생성
// [SBMA][INTENT] regenerate 시작: /events intent=regenerate 전송 (originMid 포함)
async function regenerateResponse(mid, btnEl = null) {
    // ✅ [P0] 중복 클릭 방지
    if (State.getIsRegenerating()) {
        console.warn('⚠️ [Regenerate] Already in progress, ignoring duplicate click');
        return;
    }

    // ✅ [P0] 상태 제어 시작 (팝업 없음, 즉시 진입)
    State.setIsRegenerating(true);
    State.setIsGenerating(true);
    updateSendButtonState(true);
    document.getElementById('statusText').textContent = 'Regenerating...';

    try {
        // ✅ [FIX-1B] Abort된 메시지(mid=null) Fallback 로직
        if (mid === null || mid === 'null' || !mid) {
            console.warn('⚠️ [Regenerate Fallback] No message ID, searching for previous user message');

            if (!btnEl) {
                alert('Regenerate 실패: 버튼 엘리먼트가 없습니다.');
                return;
            }

            // 현재 assistant 버블 찾기
            const currentBubble = btnEl.closest('[data-mid]') || btnEl.closest('[data-message-id]') || btnEl.closest('.message-assistant');
            if (!currentBubble) {
                alert('Regenerate 실패: 메시지 버블을 찾을 수 없습니다.');
                return;
            }

            // 이전 user 메시지 찾기 (역순 탐색)
            let prevElement = currentBubble.closest('.flex')?.previousElementSibling;
            while (prevElement) {
                const userBubble = prevElement.querySelector('[data-role="user"]');
                if (userBubble) {
                    const textDiv = userBubble.querySelector('.whitespace-pre-wrap');
                    const userPrompt = textDiv ? textDiv.innerText : null;
                    if (userPrompt) {
                        console.log(`🔄 [Regenerate Fallback] Found user prompt: "${userPrompt.substring(0, 50)}..."`);

                        // ✅ [HOT-SWAP] 기존 버블의 originMid 찾기
                        const fallbackOriginMid = currentBubble.dataset.originMid ||
                                                  currentBubble.dataset.messageId ||
                                                  currentBubble.querySelector('[data-origin-mid]')?.dataset.originMid;

                        console.log(`🔄 [Regenerate Fallback] Using originMid for Hot-Swap: ${fallbackOriginMid}`);

                        // ✅ [HOT-SWAP] 버블 제거하지 않음 (내용만 교체될 것)
                        // sendMessage가 Hot-Swap 모드로 기존 버블 업데이트

                        // sendMessage로 재생성 (Hot-Swap 모드)
                        await sendMessage(userPrompt, {
                            skipAddUserMessage: false,
                            isRegenerate: true,
                            regenerateTargetMid: fallbackOriginMid || null
                        });

                        console.log('✅ [Regenerate Fallback] Completed successfully');
                        return;
                    }
                }
                prevElement = prevElement.previousElementSibling;
            }

            alert('Regenerate 실패: 이전 유저 메시지를 찾을 수 없습니다.');
            return;
        }

        // ✅ [P0] 세션 ID 고정 (타이밍 이슈 방지)
        const sessionId = State.getCurrentSessionId();
        if (!sessionId) {
            alert('No session found');
            return;
        }

        console.log(`🔄 [Regenerate] Starting for message ${mid} in session ${sessionId}`);

        // 1. 세션 메시지 목록 가져오기
        const messagesRes = await fetch(`${State.getApiBase()}/chat/sessions/${sessionId}/messages`, {
            headers: State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {}
        });

        if (!messagesRes.ok) {
            alert('Failed to load messages');
            return;
        }

        const messages = await messagesRes.json();

        // ✅ [P1] 이전 답변 아카이빙 (삭제 전 저장)
        const targetMessage = messages.find(m => m.id === mid);
        if (targetMessage && targetMessage.role === 'assistant') {
            var answerArchive = State.getAnswerArchive();
            answerArchive[mid] = {
                content: targetMessage.content,
                metadata: {
                    rag_used: targetMessage.rag_used,
                    auto_selected: targetMessage.auto_selected,
                    selected_mode: targetMessage.selected_mode,
                    processing_time: targetMessage.processing_time
                },
                timestamp: new Date().toISOString(),
                archived_at: Date.now()
            };
            console.log(`📦 [Archive] Previous answer stored (messageId=${mid}, chars=${targetMessage.content.length})`);

            // ✅ [A안] 이전 답변을 첫 버전으로 저장
            const originMid = String(mid);
            if (!State.getAnswerVersions()[originMid]) {
                State.getAnswerVersions()[originMid] = { index: 0, items: [], prompt: "" };
            }

            // 첫 번째 버전으로 추가 (이미 있으면 스킵)
            if (State.getAnswerVersions()[originMid].items.length === 0) {
                State.getAnswerVersions()[originMid].items.push({
                    content: targetMessage.content,
                    metadata: {
                        rag_used: targetMessage.rag_used,
                        auto_selected: targetMessage.auto_selected,
                        selected_mode: targetMessage.selected_mode,
                        processing_time: targetMessage.processing_time
                    },
                    ts: Date.now()
                });
                console.log(`📝 [Version] Initialized first version for originMid=${originMid}`);
            }
        }

        // ✅ [P0] originMid 기반 prompt 스냅샷 우선 사용
        let userPromptSnapshot = State.getAnswerVersions()[String(mid)]?.prompt || null;

        // 2. 사용자 질문 추출 및 하위 메시지 목록 식별
        let messagesToDelete = [mid];

        // ✅ 스냅샷이 없을 때만 서버 스캔
        if (!userPromptSnapshot) {
            for (let i = 0; i < messages.length; i++) {
                if (messages[i].id === mid) {
                    // mid 이전의 가장 가까운 user 메시지
                    for (let j = i - 1; j >= 0; j--) {
                        if (messages[j].role === 'user') {
                            userPromptSnapshot = messages[j].content;
                            break;
                        }
                    }
                    // mid 이후 메시지들(assistant/user 포함)을 같이 제거하고 싶다면 여기 포함
                    for (let k = i + 1; k < messages.length; k++) {
                        messagesToDelete.push(messages[k].id);
                    }
                    break;
                }
            }
        }

        if (!userPromptSnapshot) {
            alert('Regenerate 실패: 원본 질문 스냅샷이 없고 서버에서도 user 메시지를 찾지 못했습니다.');
            return;
        }

        // ✅ [HOT-SWAP] UI에서 기존 버블 유지 (제거하지 않음!)
        // sendMessage가 Hot-Swap 모드로 기존 버블의 내용만 교체할 것임
        console.log(`🔄 [Regenerate] Keeping existing bubble for Hot-Swap update (originMid=${mid})`);

        // ✅ 원본 질문으로 재생성 (사용자 메시지 중복 생성 방지)
        console.log(`🔄 [Regenerate] Starting new generation with prompt: "${userPromptSnapshot.substring(0, 50)}..."`);
        await sendMessage(userPromptSnapshot, {
            skipAddUserMessage: true,
            isRegenerate: true,
            regenerateTargetMid: mid
        });

        console.log(`✅ [Regenerate] Completed for mid=${mid}`);

    } catch (e) {
        console.error('❌ [Regenerate] Error:', e);
        alert(`Regenerate 오류: ${e.message || e}`);
    } finally {
        // ✅ [P0] 종료 경로 통일
        State.setIsRegenerating(false);
        State.setIsGenerating(false);
        updateSendButtonState(false);
        document.getElementById('statusText').textContent = 'Ready';
    }
}

/**
 * Continue 응답 (AI가 이어서 작성)
 */
async function continueResponse(mid, btnEl = null) {
    // 중복 클릭 방지
    if (State.getIsGenerating()) {
        console.warn('⚠️ [Continue] Generation already in progress, ignoring');
        return;
    }

    State.setIsGenerating(true);
    updateSendButtonState(true);
    document.getElementById('statusText').textContent = 'Continuing...';
    State.setAbortController(new AbortController());

    try {
        // 1. 기존 메시지 버블 찾기
        const bubbleEl = btnEl ? btnEl.closest('.message-assistant') : findBubbleByOriginMid(String(mid));
        if (!bubbleEl) {
            alert('Continue 실패: 메시지 버블을 찾을 수 없습니다.');
            return;
        }

        // 2. 기존 메시지 내용 추출
        const contentDiv = bubbleEl.querySelector('.actual-answer') || bubbleEl.querySelector('.whitespace-pre-wrap');
        if (!contentDiv) {
            alert('Continue 실패: 메시지 내용을 찾을 수 없습니다.');
            return;
        }

        const existingContent = contentDiv.textContent || '';

        // 3. 생각 과정도 추출 (있으면)
        let existingThought = '';
        const thoughtDiv = bubbleEl.querySelector('.thought-content');
        if (thoughtDiv) {
            existingThought = thoughtDiv.textContent || '';
        }

        console.log(`🔄 [Continue] Extending message ${mid} (${existingContent.length} chars)`);

        // 4. Continue 프롬프트 생성 (간결하게)
        // ✅ [FIX] 시스템 명령어 제거 - 모델이 자연스럽게 이어쓰도록
        const continuePrompt = `[Continue]`;

        // 5. 타이핑 인디케이터 추가
        const typingDiv = document.createElement('div');
        typingDiv.className = 'typing-indicator mt-2';
        typingDiv.innerHTML = `
            <span class="inline-block w-2 h-2 bg-blue-400 rounded-full animate-bounce"></span>
            <span class="inline-block w-2 h-2 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 0.1s"></span>
            <span class="inline-block w-2 h-2 bg-blue-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></span>
        `;
        bubbleEl.appendChild(typingDiv);

        // 6. API 호출 (스트리밍)
        const headers = { 'Content-Type': 'application/json' };
        if(State.getAuthToken()) headers['Authorization'] = `Bearer ${State.getAuthToken()}`;

        const res = await fetch(`${State.getApiBase()}/chat/ask`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                question: continuePrompt,
                session_id: State.getCurrentSessionId(),
                folder_id: State.getCurrentFolderId(),
                mode: CURRENT_MODE,
                skip_user_message: true  // ✅ [FIX] Continue는 user 메시지 저장 안 함
            }),
            signal: State.getAbortController().signal
        });

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        // 7. 스트리밍 응답 처리
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        // ✅ [FIX] 여기서 줄바꿈(\n\n)을 미리 넣고 시작!
        let continuedText = '\n\n'; 
        
        // ✅ [FIX] UI에도 줄바꿈을 즉시 반영 (사용자가 바로 알 수 있게)
        contentDiv.textContent = existingContent + continuedText;
        let messageMetadata = {};

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, {stream: true});
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        // [JSON_PARSING_FIX] 빈 문자열이나 잘못된 형식 체크
                        const jsonStr = line.slice(6).trim();
                        if(!jsonStr || jsonStr.length === 0) {
                            continue;  // 빈 라인은 무시
                        }
                        const jsonData = JSON.parse(jsonStr);

                        if (jsonData.chunk) {
                            continuedText += jsonData.chunk;
                            // 기존 내용 + 새 내용 표시
                            contentDiv.textContent = existingContent + continuedText;
                        }

                        if (jsonData.done) {
                            messageMetadata = jsonData;
                        }

                        if (jsonData.error) {
                            console.error('Streaming error:', jsonData.message);
                            continuedText += `\n\n⚠️ ${jsonData.message}`;
                            contentDiv.textContent = existingContent + continuedText;
                        }
                    } catch (e) {
                        // [JSON_PARSING_FIX] JSON 파싱 오류를 더 자세히 로깅하고 안전하게 처리
                        if(e instanceof SyntaxError) {
                            console.warn(`[JSON Parse Error] Invalid JSON in SSE data: ${line.substring(0, 100)}...`, e);
                            // JSON 파싱 실패 시 해당 라인을 건너뛰고 계속 진행
                        } else {
                            console.warn('Failed to parse SSE data:', line.substring(0, 100), e);
                        }
                    }
                }
            }
        }

        // 8. 타이핑 인디케이터 제거
        typingDiv.remove();

        // 9. 전체 내용 (기존 + 새로 추가된 내용) 생성
        const fullContent = existingThought
            ? `<think>${existingThought}</think>${existingContent}${continuedText}`
            : existingContent + continuedText;

        // ✅ [FIX] 10. 서버의 새 메시지 삭제 후 원본 메시지 업데이트
        if (messageMetadata.message_id) {
            try {
                // 10-1. 서버가 생성한 새 메시지 삭제
                await fetch(`${State.getApiBase()}/chat/messages/${messageMetadata.message_id}`, {
                    method: 'DELETE',
                    headers: State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {}
                });

                // 10-2. 원본 메시지 업데이트 (전체 내용으로)
                await fetch(`${State.getApiBase()}/chat/messages/${mid}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(State.getAuthToken() ? { 'Authorization': `Bearer ${State.getAuthToken()}` } : {})
                    },
                    body: JSON.stringify({
                        content: fullContent,
                        processing_time: messageMetadata.processing_time || null
                    })
                });

                console.log(`✅ [Continue] Updated original message ${mid} with full content (${fullContent.length} chars)`);
            } catch (e) {
                console.error('⚠️ [Continue] Failed to update server message:', e);
            }
        }

        // 11. 버전 관리 시스템에 저장
        const originMid = String(mid);
        if (!State.getAnswerVersions()[originMid]) {
            State.getAnswerVersions()[originMid] = { index: 0, items: [], prompt: "" };
        }

        // 새 버전 추가
        State.getAnswerVersions()[originMid].items.push({
            content: fullContent,
            metadata: {
                rag_used: messageMetadata.rag_used || false,
                auto_selected: messageMetadata.auto_selected || false,
                selected_mode: messageMetadata.selected_mode || CURRENT_MODE,
                processing_time: messageMetadata.processing_time || null
            },
            ts: Date.now()
        });

        // 최신 버전으로 인덱스 설정
        State.getAnswerVersions()[originMid].index = State.getAnswerVersions()[originMid].items.length - 1;

        console.log(`✅ [Continue] Added ${continuedText.length} chars to message ${mid}`);

        // 12. 버전 토글 UI 업데이트
        setTimeout(() => {
            // 1. 화면에 있는 '가장 마지막 AI 말풍선'을 찾는다
            const lastAssistantMsg = document.querySelector('.message-assistant:last-of-type');
            
            if (lastAssistantMsg) {
                // 2. 그 녀석에게만 "버튼 보여줘(Show Only)" 명령을 내린다
                // (이 함수가 Regenerate와 Continue 버튼을 둘 다 켜줄 거야)
                updateRegenerateVisibility({ showOnly: lastAssistantMsg });
                console.log('✨ [UI] Buttons activated for last message');
            } else {
                // 3. AI 메시지가 하나도 없으면 싹 다 숨겨
                updateRegenerateVisibility({ hideAll: true });
            }
        }, 100); // 0.1초 딜레이 (DOM이 다 그려질 때까지 안전하게 대기)

        document.getElementById('statusText').textContent = 'Ready';

    } catch (e) {
        console.error('❌ [Continue] Error:', e);

        if (e.name === 'AbortError') {
            console.log('⏸️ [Continue] Aborted by user');
        } else {
            alert(`Continue 오류: ${e.message || e}`);
        }
    } finally {
        State.setIsGenerating(false);
        updateSendButtonState(false);
        document.getElementById('statusText').textContent = 'Ready';
        State.setAbortController(null);
    }
}

/**
 * 세션 로드
 */
async function loadSession(id, folderId = null) {
    // ============================================================
    // ✅ [CLEANUP] 세션 이동 시, 이전 세션의 흔적을 완벽히 지운다.
    // ============================================================
    
    // 1. 진행 중인 생성 중단
    if (State.getIsGenerating() && State.getAbortController()) {
        stopGeneration();
    }

    Object.assign(State.getEditContext(), {
        active: false,
        originMessageId: null,
        originText: "",
        draftBeforeEdit: "",
        backupMessages: [],
        backupSessionId: null,
        backupFolderId: null,
        backupCreatedAt: null,
        canRestore: false
    });

    // 3. UI에 남아있는 인라인 복원 버튼 제거
    document.querySelectorAll('.btn-inline-restore').forEach(btn => btn.remove());
    
    // 4. 입력창 초기화
    const input = document.getElementById('messageInput');
    if(input) input.value = '';
    
    // ✅ [SESSION PERSISTENCE] URL 파라미터 업데이트 (새로고침 유지)
    history.pushState(null, '', `?session_id=${id}`);
    console.log(`🔗 [URL] Updated to session_id=${id}`);

    const res=await fetch(`${State.getApiBase()}/chat/sessions/${id}/messages`,{headers:State.getAuthToken()?{'Authorization':`Bearer ${State.getAuthToken()}`}:{}});
    if(res.ok) {
        const m=await res.json();
        State.setCurrentSessionId(id);

        // ✅ [FIX] CURRENT_FOLDER 설정하여 Regenerate 버튼 표시 보장
        if (folderId !== null) {
            State.setCurrentFolderId(folderId);
            State.setCurrentFolder(State.getFolders().find(f => f.id === folderId));
        } else {
            // folder_id가 없으면 초기화 (Uncategorized)
            State.setCurrentFolderId(null);
            State.setCurrentFolder(null);
        }

        // ✅ [P0] 컨테이너 초기화 (중간 재생성 시 순서 꼬임 방지)
        document.getElementById('chatMessages').innerHTML='';

        // ✅ [P0] 메시지 정렬 (timestamp 또는 id 기준 오름차순)
        m.sort((a, b) => {
            // timestamp가 있고 유효하면 timestamp 우선
            const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
            const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
            if (ta && tb && ta !== tb) return ta - tb;
            // timestamp가 같거나 없으면 id 기준
            return (a.id ?? 0) - (b.id ?? 0);
        });

        // ✅ [VERSION SYSTEM] 메시지 그룹핑 (같은 질문에 대한 여러 답변)
        const groups = [];
        let currentGroup = null;

        for (let i = 0; i < m.length; i++) {
            const msg = m[i];

            if (msg.role === 'user') {
                // 이전 그룹 종료
                if (currentGroup && currentGroup.assistants.length > 0) {
                    groups.push(currentGroup);
                }

                // 유저 메시지 렌더링
                addMessageToUI(
                    'user',
                    msg.content,
                    msg.rag_used,
                    msg.id,
                    msg.feedback_positive,
                    msg.auto_selected || false,
                    msg.selected_mode || null,
                    msg.processing_time || null
                );

                // 새 그룹 시작
                currentGroup = {
                    userMsg: msg,
                    assistants: []
                };
            } else if (msg.role === 'assistant') {
                // assistant 메시지는 그룹에 추가
                if (currentGroup) {
                    currentGroup.assistants.push(msg);
                } else {
                    // user 없이 assistant만 있는 경우 (예외 처리)
                    addMessageToUI(
                        'assistant',
                        msg.content,
                        msg.rag_used,
                        msg.id,
                        msg.feedback_positive,
                        msg.auto_selected || false,
                        msg.selected_mode || null,
                        msg.processing_time || null
                    );
                }
            }
        }

        // 마지막 그룹 처리
        if (currentGroup && currentGroup.assistants.length > 0) {
            groups.push(currentGroup);
        }

        // ✅ [Plan Card 복원] 세션의 run 목록 조회 후 각 그룹별 run_id·todos 확보
        let runsAsc = [];
        try {
            const runsRes = await fetch(`${State.getApiBase()}/runs?session_id=${id}&limit=100`, { headers: State.getAuthToken() ? { 'Authorization': 'Bearer ' + State.getAuthToken() } : {} });
            if (runsRes.ok) {
                const runsData = await runsRes.json();
                const runsList = runsData.runs || [];
                runsAsc = [...runsList].reverse();
            }
        } catch (e) { console.warn('[loadSession] runs fetch failed', e); }

        const runIdsByGroupIndex = [];
        for (let i = 0; i < groups.length; i++) {
            const group = groups[i];
            if (group.assistants.length === 0) { runIdsByGroupIndex.push(null); continue; }
            const lastMsg = group.assistants[group.assistants.length - 1];
            let runId = null;
            if (lastMsg.state_info) {
                try {
                    const si = JSON.parse(lastMsg.state_info);
                    if (si.plan_only && si.run_id) runId = si.run_id;
                } catch (err) {}
            }
            if (!runId && runsAsc[i]) runId = runsAsc[i].run_id || null;
            runIdsByGroupIndex.push(runId);
        }

        const snapshots = await Promise.all(
            runIdsByGroupIndex.map(rid =>
                rid ? fetch(`${State.getApiBase()}/runs/${encodeURIComponent(rid)}`, { headers: State.getAuthToken() ? { 'Authorization': 'Bearer ' + State.getAuthToken() } : {} }).then(r => r.ok ? r.json() : null).catch(() => null)
                    : Promise.resolve(null)
            )
        );

        const planCardForGroup = snapshots.map((snap, i) => {
            const runId = runIdsByGroupIndex[i];
            const group = groups[i];
            if (!runId || !group || !group.assistants.length) return null;
            const todos = (snap && snap.todos) ? snap.todos : [];
            if (todos.length === 0) return null;
            const userInput = (group.userMsg && group.userMsg.content) ? String(group.userMsg.content).trim() : '';
            if (!userInput) return null;
            return { run_id: runId, todos: todos, user_input: userInput };
        });

        // ✅ [VERSION SYSTEM] 각 그룹의 assistant 메시지 처리
        groups.forEach((group, idx) => {
            if (group.assistants.length === 0) return;

            const originMid = String(group.assistants[0].id);

            // ✅ 버전 저장소 무조건 초기화 (새로고침 시 깨끗한 상태)
            State.getAnswerVersions()[originMid] = {
                index: group.assistants.length - 1,  // 최신 버전 인덱스
                items: [],
                prompt: group.userMsg.content
            };

            // 모든 버전 저장 (DB에서 가져온 순서대로)
            group.assistants.forEach(msg => {
                State.getAnswerVersions()[originMid].items.push({
                    content: msg.content,
                    metadata: {
                        rag_used: msg.rag_used,
                        auto_selected: msg.auto_selected,
                        selected_mode: msg.selected_mode,
                        processing_time: msg.processing_time
                    },
                    ts: msg.timestamp ? new Date(msg.timestamp).getTime() : Date.now()
                });
            });

            // ✅ 최신 버전만 렌더링 (화면에 1개만 표시) + planCard 복원 + evolution_payload (접힌 상세)
            const lastMsg = group.assistants[group.assistants.length - 1];
            const planCard = planCardForGroup[idx] || null;
            const evolutionPayload = lastMsg.evolution_payload || null;
            addMessageToUI(
                'assistant',
                lastMsg.content,
                lastMsg.rag_used,
                lastMsg.id,
                lastMsg.feedback_positive,
                lastMsg.auto_selected || false,
                lastMsg.selected_mode || null,
                lastMsg.processing_time || null,
                originMid,  // ✅ originMid 전달 (버전 추적용)
                null,       // taskBlockState
                planCard,   // ✅ 세션 로드 시 계획 카드 복원
                evolutionPayload  // ✅ patch_report 시 접힌 상세에 Evolution 원문
            );

            // ✅ 버전이 2개 이상이면 < 1/3 > 네비게이션 표시
            if (group.assistants.length > 1) {
                setTimeout(() => {
                    const lastAssistantMsg = document.querySelector('.message-assistant:last-of-type');
                    
                    if (lastAssistantMsg) {
                        // 이 함수가 이제 Continue 버튼도 같이 켜줄 거야 (범인 1을 잡았으니까)
                        updateRegenerateVisibility({ showOnly: lastAssistantMsg });
                        console.log('✨ [UI] Buttons activated for last message');
                    } else {
                        updateRegenerateVisibility({ hideAll: true });
                    }
                }, 100);
            }
        });

        console.log(`✅ [loadSession] Loaded ${m.length} messages, ${groups.length} answer groups`);
    }// 여기가 loadSession 끝나는 괄호
}

// ============================================================
// ✅ Background message polling (Autopilot reports)
// - 백그라운드 태스크가 DB에 삽입한 assistant 메시지를 채팅창에 표시
// ============================================================
let _bgPollTimer = null;

function _getMaxRenderedMessageId() {
    let maxId = 0;
    try {
        document.querySelectorAll('[data-message-id],[data-mid]').forEach(el => {
            const raw = el.getAttribute('data-message-id') || el.getAttribute('data-mid') || '';
            const n = parseInt(String(raw), 10);
            if (!isNaN(n) && n > maxId) maxId = n;
        });
    } catch(e) {}
    return maxId;
}

async function _pollBackgroundMessages() {
    try {
        if (!State.getAuthToken() || !State.getCurrentSessionId()) return;
        if (State.getIsGenerating()) return; // 생성 중엔 UI 꼬임 방지

        const maxRendered = _getMaxRenderedMessageId();
        const res = await fetch(`${State.getApiBase()}/chat/sessions/${State.getCurrentSessionId()}/messages`, {
            headers: { 'Authorization': `Bearer ${State.getAuthToken()}` }
        });
        if (!res.ok) return;
        const messages = await res.json();
        if (!Array.isArray(messages) || messages.length === 0) return;

        const newOnes = messages
            .filter(m => m && m.id && Number(m.id) > maxRendered)
            .sort((a, b) => (a.id ?? 0) - (b.id ?? 0));

        // user 메시지는 UI에서 이미 입력으로 생성되는 경우가 많으니 assistant만 추가
        for (const msg of newOnes) {
            if (msg.role !== 'assistant') continue;
            addMessageToUI('assistant', msg.content || '', false, msg.id, null, false, null, null, null, null, null, msg.evolution_payload || null);
        }
    } catch(e) {
        // 조용히 실패(네트워크/권한/세션 전환 중)
    }
}

function startBackgroundMessagePolling() {
    try {
        if (_bgPollTimer) clearInterval(_bgPollTimer);
        _bgPollTimer = setInterval(_pollBackgroundMessages, 2500);
    } catch(e) {}
}

// 페이지 로드 시 1회 시작 (세션 선택 이후에도 계속 돌며 State.getCurrentSessionId() 기준으로 표시)
try { startBackgroundMessagePolling(); } catch(e) {}

/**
 * Chat 액션 핸들러
 */
function handleChatAction() {
    if (State.getIsGenerating()) {
        stopGeneration();
    } else {
        sendMessage();
    }
}

/**
 * 리서치 관련 (간소화)
 */
// Research Logic
function addSearchApprovalCard(plan, sid, mid) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'flex justify-start mb-4';
    div.id = `approval-${mid}`;
    div.dataset.plan = JSON.stringify(plan);
    div.dataset.sid = String(sid);
    div.dataset.mid = String(mid);
    const keywords = plan.keywords.map(k=>`<span class="bg-blue-900 px-2 py-1 rounded text-xs text-blue-200">${escapeHtml(k)}</span>`).join(' ');
    const adminOk = (typeof isAdmin !== 'undefined' && isAdmin) || (typeof window !== 'undefined' && window.isAdmin);
    const approveBtnHtml = adminOk
        ? `<button class="search-approve-btn flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded text-sm">승인</button>`
        : `<button class="search-approve-btn flex-1 bg-gray-600 text-gray-400 py-2 rounded text-sm cursor-not-allowed" disabled title="Admin 전용">승인 (Admin 전용)</button>`;
    div.innerHTML = `<div class="max-w-[85%] rounded-xl p-4 bg-gray-800 border border-blue-500 shadow-lg"><h3 class="text-blue-400 font-bold mb-2">🌐 웹 검색 계획</h3><div class="mb-3 text-sm text-gray-300">${escapeHtml(plan.purpose)}</div><div class="flex gap-2 mb-4 flex-wrap">${keywords}</div><div class="flex gap-2">${approveBtnHtml}<button onclick="document.getElementById('approval-${mid}').remove()" class="px-4 bg-gray-700 hover:bg-gray-600 text-white rounded text-sm">취소</button></div></div>`;
    container.prepend(div);
    const approveBtn = div.querySelector('.search-approve-btn');
    if (approveBtn) {
        if (adminOk) {
            approveBtn.onclick = () => executeResearch(sid, mid, plan);
        } else {
            approveBtn.onclick = () => typeof showAdminOnlyWarning === 'function' && showAdminOnlyWarning();
            approveBtn.removeAttribute('disabled');
            approveBtn.classList.remove('cursor-not-allowed');
        }
    }
}

async function executeResearch(sid, mid, plan) {
    const adminOk = (typeof isAdmin !== 'undefined' && isAdmin) || (typeof window !== 'undefined' && window.isAdmin);
    if (!adminOk) {
        if (typeof showAdminOnlyWarning === 'function') showAdminOnlyWarning();
        return;
    }
    const approvalEl = document.getElementById(`approval-${mid}`);
    if (approvalEl) approvalEl.remove();

    // ✅ [P0-1 FIX] 로딩 메시지를 추적 가능한 ID로 저장
    const loadingMessageId = `research-loading-${mid}`;
    const chatContainer = document.getElementById('chatMessages');
    const loadingDiv = document.createElement('div');
    loadingDiv.id = loadingMessageId;
    loadingDiv.className = 'flex justify-start mb-4';
    loadingDiv.innerHTML = `<div class="max-w-[85%] rounded-xl px-4 py-3 message-assistant text-gray-100 shadow-lg relative group">
        <div class="whitespace-pre-wrap">🔍 웹 검색 중...</div>
    </div>`;
    chatContainer.appendChild(loadingDiv);

    requestStartTime = Date.now(); // 검색 시간 측정 시작

    try {
        const res = await fetch(`${State.getApiBase()}/chat/research/execute`, {
            method:'POST', headers:{'Content-Type':'application/json', ...(State.getAuthToken()?{'Authorization':`Bearer ${State.getAuthToken()}`}:{})},
            body:JSON.stringify({session_id:sid, message_id:mid, search_plan:plan})
        });
        if(res.ok) {
            const data = await res.json();
            const clientTimeTaken = (Date.now() - requestStartTime) / 1000;
            const finalTime = data.processing_time || clientTimeTaken;

            // ✅ [P0-1 FIX] ID로 정확한 로딩 메시지만 제거
            const loadingElement = document.getElementById(loadingMessageId);
            if (loadingElement) loadingElement.remove();

            addMessageToUI('assistant', data.answer, true, data.message_id, null, false, 'research', finalTime);
        }
    } catch(error) {
        console.error('Research error:', error);
        const loadingElement = document.getElementById(loadingMessageId);
        if (loadingElement) loadingElement.remove();
        addMessageToUI('assistant', '⚠️ Search Failed');
    }
}

async function submitFeedback(mid, pos, btn) {
    // ✅ [P1-1] 이전 상태 저장 (롤백용)
    const parent = btn.closest('.flex');
    const thumbUpBtn = parent.querySelector('.fa-thumbs-up')?.parentElement;
    const thumbDownBtn = parent.querySelector('.fa-thumbs-down')?.parentElement;
    let previousUpColor, previousDownColor;

    try {
        // 1. 즉각적인 UI 피드백 (서버 응답 전에 색상 변경)
        if (thumbUpBtn && thumbDownBtn) {
            // ✅ [P1-1] 이전 색상 저장 (롤백용)
            previousUpColor = thumbUpBtn.className.includes('text-green-400') ? 'text-green-400' : 'text-gray-500';
            previousDownColor = thumbDownBtn.className.includes('text-red-400') ? 'text-red-400' : 'text-gray-500';

            // 두 버튼 모두 기본 색상으로 초기화
            thumbUpBtn.className = thumbUpBtn.className.replace('text-green-400', 'text-gray-500');
            thumbDownBtn.className = thumbDownBtn.className.replace('text-red-400', 'text-gray-500');

            // 클릭한 버튼만 강조 색상으로 변경
            if (pos) {
                thumbUpBtn.className = thumbUpBtn.className.replace('text-gray-500', 'text-green-400');
            } else {
                thumbDownBtn.className = thumbDownBtn.className.replace('text-gray-500', 'text-red-400');
            }
        }

        // 2. 서버에 피드백 전송
        const response = await fetch(`${State.getApiBase()}/chat/messages/${mid}/feedback`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(State.getAuthToken() ? {'Authorization': `Bearer ${State.getAuthToken()}`} : {})
            },
            body: JSON.stringify({is_positive: pos})
        });

        // ✅ [P1-1] 서버 응답 검증
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        console.log(`✅ [Feedback] Message ${mid} marked as ${pos ? 'positive' : 'negative'}`);

    } catch (e) {
        console.error('❌ [Feedback] Error:', e);

        // ✅ [P1-1] 실패 시 UI 롤백
        if (thumbUpBtn && thumbDownBtn && previousUpColor !== undefined && previousDownColor !== undefined) {
            thumbUpBtn.className = thumbUpBtn.className
                .replace('text-green-400', 'text-gray-500')
                .replace('text-gray-500', previousUpColor);
            thumbDownBtn.className = thumbDownBtn.className
                .replace('text-red-400', 'text-gray-500')
                .replace('text-gray-500', previousDownColor);
        }

        alert('피드백 전송에 실패했습니다. 다시 시도해주세요.');
    }
}
