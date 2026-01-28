// =========================
// API Module
// =========================

const API_BASE = window.location.origin; //✅ [P0] API 기본 URL (state.js에서 참조)

// =========================
// AbortController Lifecycle
// =========================

/**
 * 새 AbortController 생성
 */
function createAbort() {
    abortController = new AbortController();
    return abortController;
}

/**
 * 현재 활성 요청 중단
 */
function abortActive() {
    if (abortController) {
        abortController.abort();
        abortController = null;
    }
}

/**
 * 중단 후 상태 초기화
 */
function stopGeneration() {
    abortActive();
    isGenerating = false;
    updateSendButtonState(false);
    document.getElementById('statusText').textContent = 'Stopped';
}

// =========================
// API Fetch Wrappers
// =========================

/**
 * Authorization 헤더 자동 추가 fetch
 */
async function apiFetch(path, options = {}) {
    const headers = { ...options.headers };
    if (AUTH_TOKEN) {
        headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
    }

    return fetch(`${API_BASE}${path}`, {
        ...options,
        headers
    });
}

/**
 * SSE 스트리밍 요청
 * @param {string} path - API 경로
 * @param {object} payload - 요청 body
 * @param {function} onDataLine - 데이터 라인 콜백 (line) => void
 * @param {AbortSignal} signal - abort signal
 */
async function apiStreamAsk(path, payload, onDataLine, signal) {
    const headers = {
        'Content-Type': 'application/json'
    };
    if (AUTH_TOKEN) {
        headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
    }

    const response = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        signal
    });

    if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (line.trim()) {
                onDataLine(line);
            }
        }
    }
}

// =========================
// VRAM Monitoring API
// =========================

/**
 * VRAM 상태 조회
 */
async function fetchVRAMStatus() {
    try {
        const res = await apiFetch('/vram-status');
        if (res.ok) {
            const data = await res.json();
            window.VRAM_STATUS = {
                used: data.used || 0,
                total: data.total || 0,
                percent: data.percent || 0,
                lastUpdate: new Date()
            };
            updateVRAMWidget();
            return data;
        }
    } catch (e) {
        console.warn('[VRAM] Status fetch failed:', e);
    }
    return null;
}

/**
 * VRAM 폴링 시작 (5초 간격)
 */
function startVRAMPolling() {
    if (window.VRAM_POLL_INTERVAL) {
        clearInterval(window.VRAM_POLL_INTERVAL);
    }

    // 즉시 1회 호출
    fetchVRAMStatus();

    // 5초마다 폴링
    window.VRAM_POLL_INTERVAL = setInterval(() => {
        fetchVRAMStatus();
    }, 5000);

    console.log('[VRAM] Polling started (5s interval)');
}

/**
 * VRAM 폴링 중지
 */
function stopVRAMPolling() {
    if (window.VRAM_POLL_INTERVAL) {
        clearInterval(window.VRAM_POLL_INTERVAL);
        window.VRAM_POLL_INTERVAL = null;
        console.log('[VRAM] Polling stopped');
    }
}
