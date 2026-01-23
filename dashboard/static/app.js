/* ============================================
   Boomshakalaka Dashboard - JavaScript
   ============================================ */

// ============================================
// Theme Management
// ============================================

function getStoredTheme() {
    return localStorage.getItem('theme') || 'dark';
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);

    // Apply the correct mode from dual-mode theme if available
    const dualMode = localStorage.getItem('customThemeDualMode');
    if (dualMode) {
        try {
            const themes = JSON.parse(dualMode);
            if (themes[theme]) {
                applyCustomThemeColors(themes[theme]);
                localStorage.setItem('customThemeCSS', JSON.stringify(themes[theme]));
            }
        } catch (e) {
            console.error('Error applying dual-mode theme:', e);
        }
    }
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
}

// Custom Theme Color Management
function loadCustomThemeColors() {
    // Check for dual-mode theme first
    const dualMode = localStorage.getItem('customThemeDualMode');
    if (dualMode) {
        try {
            const themes = JSON.parse(dualMode);
            const currentMode = document.documentElement.getAttribute('data-theme') || 'dark';
            if (themes[currentMode]) {
                applyCustomThemeColors(themes[currentMode]);
                return;
            }
        } catch (e) {
            console.error('Error loading dual-mode theme:', e);
        }
    }

    // Fall back to single-mode theme
    const storedCSS = localStorage.getItem('customThemeCSS');
    if (storedCSS) {
        try {
            const cssVars = JSON.parse(storedCSS);
            applyCustomThemeColors(cssVars);
        } catch (e) {
            console.error('Error loading custom theme colors:', e);
        }
    }
}

function applyCustomThemeColors(cssVars) {
    const root = document.documentElement;
    for (const [varName, value] of Object.entries(cssVars)) {
        root.style.setProperty(varName, value);
    }
}

function clearCustomThemeColors() {
    localStorage.removeItem('customThemeCSS');
    localStorage.removeItem('customThemeDualMode');
    // Remove inline styles to revert to CSS defaults
    const root = document.documentElement;
    const customVars = [
        '--bg-primary', '--bg-secondary', '--bg-tertiary', '--bg-card',
        '--bg-hover', '--bg-input', '--border-color', '--border-light',
        '--border-focus', '--text-primary', '--text-secondary', '--text-muted',
        '--accent', '--accent-hover', '--accent-muted', '--accent-bg',
        '--accent-glow', '--gradient-accent'
    ];
    customVars.forEach(varName => root.style.removeProperty(varName));
}

// Load active theme from server and apply it
async function loadActiveTheme() {
    try {
        const response = await fetch('/api/themes/active');
        const data = await response.json();

        if (data.theme && data.theme.css) {
            const css = data.theme.css;

            // Check if it's a dual-mode theme (has dark and light keys)
            if (css.dark && css.light) {
                localStorage.setItem('customThemeDualMode', JSON.stringify(css));
                const currentMode = document.documentElement.getAttribute('data-theme') || 'dark';
                applyCustomThemeColors(css[currentMode]);
                localStorage.setItem('customThemeCSS', JSON.stringify(css[currentMode]));
            } else {
                // Single-mode theme
                applyCustomThemeColors(css);
                localStorage.setItem('customThemeCSS', JSON.stringify(css));
            }
        }
    } catch (error) {
        // Silently fail - use localStorage backup or default theme
        console.debug('Could not load active theme from server:', error);
    }
}

// Initialize theme on page load
(function initTheme() {
    const savedTheme = getStoredTheme();
    setTheme(savedTheme);

    // Load custom theme colors from localStorage immediately for fast load
    loadCustomThemeColors();
})();

// ============================================
// Sidebar Collapse Toggle
// ============================================

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed');
        const isCollapsed = sidebar.classList.contains('collapsed');
        localStorage.setItem('sidebarCollapsed', isCollapsed);
    }
}

function restoreSidebarState() {
    const sidebar = document.getElementById('sidebar');
    const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (sidebar && isCollapsed) {
        sidebar.classList.add('collapsed');
    }
}

// ============================================
// Sidebar Category Toggle
// ============================================

function toggleCategory(button) {
    const category = button.closest('.nav-category');
    if (category) {
        category.classList.toggle('expanded');

        // Save state to localStorage
        const categoryName = button.querySelector('.nav-text')?.textContent?.trim();
        if (categoryName) {
            const expandedCategories = JSON.parse(localStorage.getItem('expandedCategories') || '{}');
            expandedCategories[categoryName] = category.classList.contains('expanded');
            localStorage.setItem('expandedCategories', JSON.stringify(expandedCategories));
        }
    }
}

// Toggle nested subcategories (e.g., Betting -> Monitor/Analysis)
function toggleSubcategory(button) {
    const subcategory = button.closest('.nav-subcategory');
    if (subcategory) {
        subcategory.classList.toggle('expanded');
    }
}

// Restore expanded categories on page load
function restoreExpandedCategories() {
    const expandedCategories = JSON.parse(localStorage.getItem('expandedCategories') || '{}');

    document.querySelectorAll('.nav-category').forEach(category => {
        const categoryName = category.querySelector('.nav-text')?.textContent?.trim();
        if (categoryName && expandedCategories[categoryName]) {
            category.classList.add('expanded');
        }
    });
}

// ============================================
// Utility Functions
// ============================================

function formatTime(date) {
    return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function formatDate(date) {
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function timeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

// ============================================
// API Health Check
// ============================================

async function checkApiHealth() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Health check failed:', error);
        return null;
    }
}

async function updateHealthDisplay() {
    const data = await checkApiHealth();
    if (!data) return;

    // Update Odds API status
    const oddsStatus = document.getElementById('odds-api-status');
    const oddsMessage = document.getElementById('odds-api-message');
    const oddsDot = document.getElementById('odds-api-dot');

    if (oddsStatus && data.odds_api) {
        oddsStatus.textContent = data.odds_api.status === 'healthy' ? 'Healthy' : 'Error';
        oddsStatus.className = `api-status-badge ${data.odds_api.status}`;
        if (oddsMessage) oddsMessage.textContent = data.odds_api.message;
        if (oddsDot) oddsDot.className = `job-status ${data.odds_api.status === 'healthy' ? 'running' : 'error'}`;
    }

    // Update Polymarket API status
    const pmStatus = document.getElementById('polymarket-api-status');
    const pmMessage = document.getElementById('polymarket-api-message');
    const pmDot = document.getElementById('pm-api-dot');

    if (pmStatus && data.polymarket_api) {
        pmStatus.textContent = data.polymarket_api.status === 'healthy' ? 'Healthy' : 'Error';
        pmStatus.className = `api-status-badge ${data.polymarket_api.status}`;
        if (pmMessage) pmMessage.textContent = data.polymarket_api.message;
        if (pmDot) pmDot.className = `job-status ${data.polymarket_api.status === 'healthy' ? 'running' : 'error'}`;
    }

    // Update system status in sidebar
    updateSystemStatus(data);

    return data;
}

function updateSystemStatus(data) {
    const statusDot = document.querySelector('.sidebar-footer .status-dot');
    const statusText = document.querySelector('.sidebar-footer .status-text');

    if (!statusDot || !statusText) return;

    const allHealthy = data?.odds_api?.status === 'healthy' && data?.polymarket_api?.status === 'healthy';

    statusDot.className = `status-dot ${allHealthy ? 'online' : 'warning'}`;
    statusText.textContent = allHealthy ? 'System Online' : 'Issues Detected';
    statusText.style.color = allHealthy ? 'var(--success)' : 'var(--warning)';
}

// ============================================
// Log Management
// ============================================

function highlightLogs() {
    document.querySelectorAll('.log-content').forEach(el => {
        let html = el.innerHTML;

        // Timestamps
        html = html.replace(/\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]/g,
            '<span class="log-timestamp">[$1]</span>');

        // Errors
        html = html.replace(/\b(Error|ERROR|error|Exception|EXCEPTION|Failed|FAILED)\b/g,
            '<span class="log-error">$1</span>');

        // Success indicators
        html = html.replace(/\b(Success|SUCCESS|success|OK|ok|completed|COMPLETED)\b/g,
            '<span class="log-success">$1</span>');

        // Warnings
        html = html.replace(/\b(Warning|WARNING|warning|WARN)\b/g,
            '<span class="log-warning">$1</span>');

        // Special keywords
        html = html.replace(/\b(BLOWOUT|ALERT|Alert)\b/g,
            '<span class="log-warning" style="font-weight:bold">$1</span>');

        // URLs
        html = html.replace(/(https?:\/\/[^\s<]+)/g,
            '<a href="$1" target="_blank" style="color:var(--accent)">$1</a>');

        el.innerHTML = html;
    });
}

function switchLogTab(tabElement, logName) {
    // Update tab active state
    document.querySelectorAll('.log-tab').forEach(tab => tab.classList.remove('active'));
    tabElement.classList.add('active');

    // Fetch and display log content
    fetch(`/api/logs/${encodeURIComponent(logName)}`)
        .then(response => response.json())
        .then(data => {
            const logContent = document.getElementById('log-content');
            if (logContent && data.content) {
                logContent.textContent = data.content;
                highlightLogs();
            }
        })
        .catch(error => {
            console.error('Failed to fetch log:', error);
        });
}

// Auto-refresh for logs
let autoRefreshInterval = null;
let currentLogName = null;

function toggleAutoRefresh(button) {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
        button.innerHTML = `<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg> Auto-refresh: Off`;
        button.classList.remove('btn-primary');
        button.classList.add('btn-secondary');
    } else {
        // Refresh immediately
        const activeTab = document.querySelector('.log-tab.active');
        if (activeTab) {
            currentLogName = activeTab.textContent.trim();
            switchLogTab(activeTab, currentLogName);
        }

        autoRefreshInterval = setInterval(() => {
            const activeTab = document.querySelector('.log-tab.active');
            if (activeTab) {
                switchLogTab(activeTab, activeTab.textContent.trim());
            }
        }, 10000);

        button.innerHTML = `<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg> Auto-refresh: On`;
        button.classList.remove('btn-secondary');
        button.classList.add('btn-primary');
    }
}

function downloadLog(logName) {
    fetch(`/api/logs/${encodeURIComponent(logName)}`)
        .then(response => response.json())
        .then(data => {
            const blob = new Blob([data.content], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${logName.toLowerCase().replace(/\s+/g, '_')}_${new Date().toISOString().split('T')[0]}.log`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        })
        .catch(error => {
            console.error('Failed to download log:', error);
        });
}

function downloadCurrentLog() {
    const activeTab = document.querySelector('.log-tab.active');
    if (activeTab) {
        downloadLog(activeTab.textContent.trim());
    }
}

// ============================================
// Settings Page
// ============================================

function toggleSetting(toggleElement, settingName) {
    toggleElement.classList.toggle('active');
    const isActive = toggleElement.classList.contains('active');

    // Save to localStorage
    localStorage.setItem(`setting_${settingName}`, isActive);

    // Handle specific settings
    if (settingName === 'darkMode') {
        setTheme(isActive ? 'dark' : 'light');
    }
}

function loadSettingsState() {
    document.querySelectorAll('.toggle[data-setting]').forEach(toggle => {
        const settingName = toggle.getAttribute('data-setting');
        const savedState = localStorage.getItem(`setting_${settingName}`);

        if (savedState === 'true') {
            toggle.classList.add('active');
        } else if (savedState === 'false') {
            toggle.classList.remove('active');
        }
    });
}

// ============================================
// Page Refresh
// ============================================

function refreshPage() {
    const btn = event?.target?.closest('.btn');
    if (btn) {
        btn.classList.add('loading');
        btn.disabled = true;
    }
    setTimeout(() => location.reload(), 300);
}

// ============================================
// Initialize
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    // Restore sidebar collapsed state
    restoreSidebarState();

    // Restore expanded categories
    restoreExpandedCategories();

    // Initial health check
    updateHealthDisplay();

    // Highlight logs
    highlightLogs();

    // Load settings state
    loadSettingsState();

    // Sync active page name to sidebar
    syncActivePageName();

    // Set up periodic health checks (every 60 seconds)
    setInterval(updateHealthDisplay, 60000);
});

// ============================================
// Active Page Name Sync (Midnight Command Theme)
// ============================================

function syncActivePageName() {
    const pageTitle = document.querySelector('.page-title');
    const activePageName = document.getElementById('active-page-name');

    if (pageTitle && activePageName) {
        activePageName.textContent = pageTitle.textContent;
    }
}
