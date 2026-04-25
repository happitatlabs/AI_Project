(function (global) {
    'use strict';

    const markerMap = {
        '[RISK_PERSON_CANDIDATE]': '[PERSON]',
        '[RISK_ORG_CANDIDATE]': '[ORG]',
        '[WARNING_PROJECT_CANDIDATE]': '[PROJECT]',
        '[RISK_PROJECT_CANDIDATE]': '[PROJECT]',
        '[WARNING_BUSINESS_CANDIDATE]': '[BUSINESS]',
        '[RISK_BUSINESS_CANDIDATE]': '[BUSINESS]',
        '[WARNING_CONTRACT_CANDIDATE]': '[CONTRACT]',
        '[RISK_CONTRACT_CANDIDATE]': '[CONTRACT]',
        '[LOW_CONF_TERM_CANDIDATE]': '[TERM]',
    };
    const tokenPatterns = [
        { pattern: /(?<![A-Za-z0-9_])CLIENT_\d+(?!\d)/g, replacement: '[CLIENT]' },
        { pattern: /(?<![A-Za-z0-9_])PROJECT_\d+(?!\d)/g, replacement: '[PROJECT]' },
        { pattern: /(?<![A-Za-z0-9_])PERSON_\d+(?!\d)/g, replacement: '[PERSON]' },
        { pattern: /(?<![A-Za-z0-9_])ORG_\d+(?!\d)/g, replacement: '[ORG]' },
        { pattern: /(?<![A-Za-z0-9_])EMAIL_\d+(?!\d)/g, replacement: '[EMAIL]' },
        { pattern: /(?<![A-Za-z0-9_])PHONE_\d+(?!\d)/g, replacement: '[PHONE]' },
        { pattern: /(?<![A-Za-z0-9_])ADDRESS_\d+(?!\d)/g, replacement: '[ADDRESS]' },
        { pattern: /(?<![A-Za-z0-9_])BUSINESS_\d+(?!\d)/g, replacement: '[BUSINESS]' },
        { pattern: /(?<![A-Za-z0-9_])CONTRACT_\d+(?!\d)/g, replacement: '[CONTRACT]' },
        { pattern: /(?<![A-Za-z0-9_])COMPANY_\d+(?!\d)/g, replacement: '[COMPANY]' },
        { pattern: /(?<![A-Za-z0-9_])DEPT_\d+(?!\d)/g, replacement: '[DEPARTMENT]' },
    ];
    const markerDescriptions = {
        '[PERSON]': '익명 처리된 인명',
        '[ORG]': '익명 처리된 기관/회사명',
        '[PROJECT]': '익명 처리된 프로젝트명',
        '[BUSINESS]': '익명 처리된 사업명',
        '[CONTRACT]': '익명 처리된 계약명',
        '[CLIENT]': '익명 처리된 고객사명',
        '[EMAIL]': '익명 처리된 이메일',
        '[PHONE]': '익명 처리된 전화번호',
        '[ADDRESS]': '익명 처리된 주소',
        '[TERM]': '민감정보 가능성이 있어 표시용으로 숨긴 후보',
    };
    const displayNotice = '표시 안내: [PERSON], [ORG], [PROJECT], [TERM] 등은 익명 처리된 민감정보입니다.';

    function toDisplayText(value) {
        let text = String(value == null ? '' : value);
        Object.keys(markerMap).forEach(function (source) {
            text = text.split(source).join(markerMap[source]);
        });
        tokenPatterns.forEach(function (entry) {
            text = text.replace(entry.pattern, entry.replacement);
        });
        return text;
    }

    function applyToElement(root) {
        if (!root || !global.document || typeof document.createTreeWalker !== 'function') {
            return;
        }
        const nodeFilter = global.NodeFilter || { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2 };
        const walker = document.createTreeWalker(
            root,
            nodeFilter.SHOW_TEXT,
            {
                acceptNode: function (node) {
                    const parent = node && node.parentNode ? node.parentNode.nodeName : '';
                    if (!node || !node.nodeValue || !String(node.nodeValue).trim()) {
                        return nodeFilter.FILTER_REJECT;
                    }
                    if (parent === 'SCRIPT' || parent === 'STYLE') {
                        return nodeFilter.FILTER_REJECT;
                    }
                    return nodeFilter.FILTER_ACCEPT;
                },
            }
        );
        const nodes = [];
        while (walker.nextNode()) {
            nodes.push(walker.currentNode);
        }
        nodes.forEach(function (node) {
            const next = toDisplayText(node.nodeValue || '');
            if (next !== node.nodeValue) {
                node.nodeValue = next;
            }
        });
    }

    global.AnonymizationDisplay = {
        toDisplayText: toDisplayText,
        applyToElement: applyToElement,
        displayNoticeText: function () { return displayNotice; },
        markerDescriptions: markerDescriptions,
    };
}(window));
