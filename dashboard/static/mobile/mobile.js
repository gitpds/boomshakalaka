/**
 * BOOMSHAKALAKA MOBILE
 * Navigation, gestures, and utilities
 */

// =============================================
// NAVIGATION CONTROLLER
// =============================================
const MobileNav = {
    init() {
        this.updateActiveNav();
        window.addEventListener('popstate', () => this.updateActiveNav());
        document.querySelector('.mobile-content')?.classList.add('page-enter');
    },

    updateActiveNav() {
        const path = window.location.pathname;
        document.querySelectorAll('.nav-item').forEach(item => {
            const href = item.getAttribute('href');
            if (href === path || (href !== '/m' && path.startsWith(href))) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }
};

// =============================================
// TOUCH GESTURES
// =============================================
const TouchGestures = {
    init(element, options = {}) {
        const config = {
            onSwipeLeft: null,
            onSwipeRight: null,
            onLongPress: null,
            threshold: 50,
            longPressDelay: 500,
            ...options
        };

        let startX = 0, startY = 0, startTime = 0, longPressTimer = null;

        element.addEventListener('touchstart', (e) => {
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
            startTime = Date.now();

            if (config.onLongPress) {
                longPressTimer = setTimeout(() => config.onLongPress(e), config.longPressDelay);
            }
        }, { passive: true });

        element.addEventListener('touchmove', () => {
            if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
        }, { passive: true });

        element.addEventListener('touchend', (e) => {
            if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }

            const endX = e.changedTouches[0].clientX;
            const diffX = endX - startX;
            const elapsed = Date.now() - startTime;

            if (elapsed > 300) return;

            if (diffX > config.threshold && config.onSwipeRight) {
                config.onSwipeRight(e);
            } else if (diffX < -config.threshold && config.onSwipeLeft) {
                config.onSwipeLeft(e);
            }
        }, { passive: true });

        return config;
    }
};

// =============================================
// PULL TO REFRESH
// =============================================
const PullToRefresh = {
    indicator: null,
    onRefresh: null,
    threshold: 80,

    init(options = {}) {
        this.onRefresh = options.onRefresh || (() => window.location.reload());
        this.threshold = options.threshold || 80;

        this.indicator = document.createElement('div');
        this.indicator.className = 'pull-indicator';
        this.indicator.innerHTML = '<div class="loading-spinner"></div>';
        this.indicator.style.cssText = `
            position: fixed; top: 70px; left: 50%; transform: translateX(-50%) translateY(-60px);
            width: 40px; height: 40px; background: var(--glass-bg); border: 1px solid var(--glass-border);
            border-radius: 50%; display: flex; align-items: center; justify-content: center;
            transition: transform 0.25s; z-index: 40;
        `;
        document.body.appendChild(this.indicator);

        const content = document.querySelector('.mobile-content');
        if (!content) return;

        let enabled = false, startY = 0, currentY = 0;

        content.addEventListener('touchstart', (e) => {
            if (content.scrollTop === 0) { enabled = true; startY = e.touches[0].clientY; }
        }, { passive: true });

        content.addEventListener('touchmove', (e) => {
            if (!enabled) return;
            currentY = e.touches[0].clientY;
            const diff = currentY - startY;
            if (diff > 0) {
                this.indicator.style.transform = `translateX(-50%) translateY(${diff - 60}px)`;
            }
        }, { passive: true });

        content.addEventListener('touchend', () => {
            if (enabled && (currentY - startY) > this.threshold) {
                this.onRefresh();
            }
            this.indicator.style.transform = 'translateX(-50%) translateY(-60px)';
            enabled = false; startY = 0; currentY = 0;
        }, { passive: true });
    },

    complete() {
        this.indicator.style.transform = 'translateX(-50%) translateY(-60px)';
    }
};

// =============================================
// BOTTOM SHEET
// =============================================
const BottomSheet = {
    overlay: null,
    sheet: null,

    init() {
        if (!document.querySelector('.bottom-sheet-overlay')) {
            this.overlay = document.createElement('div');
            this.overlay.className = 'bottom-sheet-overlay';
            document.body.appendChild(this.overlay);
            this.overlay.addEventListener('click', () => this.close());
        } else {
            this.overlay = document.querySelector('.bottom-sheet-overlay');
        }
    },

    open(sheetId) {
        this.init();
        this.sheet = document.getElementById(sheetId);
        if (!this.sheet) return;

        this.overlay.classList.add('active');
        this.sheet.classList.add('active');
        document.body.style.overflow = 'hidden';
    },

    close() {
        if (this.overlay) this.overlay.classList.remove('active');
        if (this.sheet) this.sheet.classList.remove('active');
        document.body.style.overflow = '';
    }
};

// =============================================
// TOAST NOTIFICATIONS
// =============================================
const Toast = {
    container: null,

    init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    },

    show(message, type = 'info', duration = 3000) {
        this.init();
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const span = document.createElement('span');
        span.textContent = message;
        toast.appendChild(span);
        this.container.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('show'));
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
        return toast;
    },

    success(message, duration) { return this.show(message, 'success', duration); },
    warning(message, duration) { return this.show(message, 'warning', duration); },
    error(message, duration) { return this.show(message, 'error', duration); },
    info(message, duration) { return this.show(message, 'info', duration); }
};

// =============================================
// HAPTIC FEEDBACK
// =============================================
const Haptic = {
    light() { if ('vibrate' in navigator) navigator.vibrate(10); },
    medium() { if ('vibrate' in navigator) navigator.vibrate(20); },
    heavy() { if ('vibrate' in navigator) navigator.vibrate([30, 10, 30]); }
};

// =============================================
// UTILITIES
// =============================================
const Utils = {
    formatTime(date) {
        if (typeof date === 'string') date = new Date(date);
        return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    },

    formatDate(date) {
        if (typeof date === 'string') date = new Date(date);
        return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    },

    timeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diff = Math.floor((now - date) / 1000);
        if (diff < 60) return 'just now';
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
        return this.formatDate(date);
    },

    debounce(func, wait) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func(...args), wait);
        };
    },

    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) { func(...args); inThrottle = true; setTimeout(() => inThrottle = false, limit); }
        };
    },

    store: {
        get(key, defaultValue = null) {
            try { const item = localStorage.getItem(`mobile_${key}`); return item ? JSON.parse(item) : defaultValue; }
            catch { return defaultValue; }
        },
        set(key, value) {
            try { localStorage.setItem(`mobile_${key}`, JSON.stringify(value)); return true; }
            catch { return false; }
        }
    }
};

// =============================================
// SWIPEABLE LIST
// =============================================
const SwipeableList = {
    init(container, options = {}) {
        const config = { threshold: 80, onSwipeLeft: null, onSwipeRight: null, ...options };
        const items = container.querySelectorAll('.swipe-container');

        items.forEach(item => {
            const content = item.querySelector('.swipe-content');
            if (!content) return;

            let startX = 0, currentX = 0;

            content.addEventListener('touchstart', (e) => {
                startX = e.touches[0].clientX;
                content.style.transition = 'none';
            });

            content.addEventListener('touchmove', (e) => {
                currentX = e.touches[0].clientX;
                const diff = Math.max(-100, Math.min(100, currentX - startX));
                content.style.transform = `translateX(${diff}px)`;
            });

            content.addEventListener('touchend', () => {
                content.style.transition = '';
                const diff = currentX - startX;
                if (diff > config.threshold && config.onSwipeRight) { config.onSwipeRight(item); Haptic.medium(); }
                else if (diff < -config.threshold && config.onSwipeLeft) { config.onSwipeLeft(item); Haptic.medium(); }
                content.style.transform = '';
                startX = 0; currentX = 0;
            });
        });
    }
};

// =============================================
// DRAG AND DROP (for Kanban)
// =============================================
const DragDrop = {
    dragging: null,
    placeholder: null,

    init(container, options = {}) {
        const config = { itemSelector: '.kanban-card', containerSelector: '.kanban-cards', onDrop: null, ...options };
        const items = container.querySelectorAll(config.itemSelector);

        items.forEach(item => {
            let startY = 0, startX = 0, offsetY = 0, offsetX = 0, longPressTimer = null, isDragging = false;

            item.addEventListener('touchstart', (e) => {
                startX = e.touches[0].clientX;
                startY = e.touches[0].clientY;

                longPressTimer = setTimeout(() => {
                    isDragging = true;
                    this.dragging = item;
                    const rect = item.getBoundingClientRect();
                    offsetX = startX - rect.left;
                    offsetY = startY - rect.top;
                    item.classList.add('dragging');
                    item.style.cssText = `position:fixed;width:${rect.width}px;z-index:1000;left:${rect.left}px;top:${rect.top}px;`;

                    this.placeholder = document.createElement('div');
                    this.placeholder.style.cssText = `height:${rect.height}px;background:var(--gold-dim);border-radius:var(--radius-md);border:2px dashed var(--gold);`;
                    item.parentNode.insertBefore(this.placeholder, item);
                    Haptic.heavy();
                }, 300);
            });

            item.addEventListener('touchmove', (e) => {
                if (!isDragging) { clearTimeout(longPressTimer); return; }
                e.preventDefault();
                const touch = e.touches[0];
                item.style.left = `${touch.clientX - offsetX}px`;
                item.style.top = `${touch.clientY - offsetY}px`;

                container.querySelectorAll(config.containerSelector).forEach(target => {
                    const rect = target.getBoundingClientRect();
                    if (touch.clientX >= rect.left && touch.clientX <= rect.right &&
                        touch.clientY >= rect.top && touch.clientY <= rect.bottom) {
                        if (this.placeholder.parentNode !== target) target.appendChild(this.placeholder);
                    }
                });
            }, { passive: false });

            item.addEventListener('touchend', () => {
                clearTimeout(longPressTimer);
                if (!isDragging) return;
                isDragging = false;

                if (this.placeholder && this.placeholder.parentNode) {
                    this.placeholder.parentNode.insertBefore(item, this.placeholder);
                    this.placeholder.remove();
                    if (config.onDrop) config.onDrop(item, item.parentNode);
                    Haptic.medium();
                }

                item.classList.remove('dragging');
                item.style.cssText = '';
                this.dragging = null;
                this.placeholder = null;
            });
        });
    }
};

// =============================================
// TERMINAL MODAL
// =============================================
const TerminalModal = {
    modal: null,
    terminal1: null,
    terminal2: null,
    wrapper2: null,
    toggleArrow: null,
    toggleLabel: null,
    isExpanded: false,

    // Tab management state
    tabs: [],
    selectedTabId: null,
    isTabPickerOpen: false,

    init() {
        this.loadTabs();
    },

    async loadTabs() {
        try {
            const response = await fetch('/api/terminal/windows');
            const data = await response.json();
            if (data.windows) {
                this.tabs = data.windows;
                // Select active tab or first tab
                const activeTab = this.tabs.find(t => t.active) || this.tabs[0];
                if (activeTab) {
                    this.selectedTabId = activeTab.id;
                }
                this.updateTabPickerUI();
                this.updateTerminalSubtitle();
            }
        } catch (e) {
            console.error('Failed to load terminal tabs:', e);
            // Default fallback
            this.tabs = [{ id: 1, name: 'Terminal 1', active: true }];
            this.selectedTabId = 1;
        }
    },

    async selectTab(id) {
        try {
            const response = await fetch(`/api/terminal/windows/${id}/select`, {
                method: 'POST'
            });
            const data = await response.json();
            if (data.success) {
                this.selectedTabId = id;
                // Update active state in local tabs array
                this.tabs.forEach(t => t.active = (t.id === id));
                this.updateTabPickerUI();
                this.updateModalHeader();
                this.updateTerminalSubtitle();
                // Reload terminal iframes to show selected tab
                this.reloadTerminals();
            }
        } catch (e) {
            console.error('Failed to select tab:', e);
            Toast.error('Failed to select terminal tab');
        }
    },

    async createTab() {
        try {
            const response = await fetch('/api/terminal/windows', {
                method: 'POST'
            });
            const data = await response.json();
            if (data.window) {
                this.tabs.push(data.window);
                // Select the new tab
                await this.selectTab(data.window.id);
                this.closeTabPicker();
                Toast.success(`Created ${data.window.name}`);
            }
        } catch (e) {
            console.error('Failed to create tab:', e);
            Toast.error('Failed to create terminal tab');
        }
    },

    reloadTerminals() {
        const baseUrl = window.location.protocol + '//' + window.location.hostname;
        if (this.terminal1) {
            this.terminal1.src = baseUrl + ':7681';
        }
        if (this.terminal2 && this.isExpanded) {
            this.terminal2.src = baseUrl + ':7682';
        }
    },

    toggleTabPicker() {
        // Legacy - no longer used since tabs are shown directly on page
        Haptic.light();
    },

    closeTabPicker() {
        // Legacy - no longer used
    },

    updateTabPickerUI() {
        // Update the main terminal tabs list on the workshop page
        const list = document.getElementById('terminal-tabs-list');
        if (!list) return;

        list.innerHTML = '';
        this.tabs.forEach(tab => {
            const item = document.createElement('div');
            item.className = 'terminal-tab-item' + (tab.id === this.selectedTabId ? ' active' : '');
            item.innerHTML = `
                <span class="terminal-tab-icon">&#128187;</span>
                <span class="terminal-tab-name">${tab.name || 'Terminal ' + tab.id}</span>
                ${tab.id === this.selectedTabId ? '<span class="terminal-tab-check">&#10003;</span>' : ''}
            `;
            item.onclick = () => {
                this.selectTab(tab.id);
                this.open();
            };
            list.appendChild(item);
        });
    },

    updateModalHeader() {
        const nameEl = document.getElementById('terminal-tab-name');
        if (nameEl) {
            const tab = this.tabs.find(t => t.id === this.selectedTabId);
            nameEl.textContent = tab ? (tab.name || 'Terminal ' + tab.id) : 'Terminal';
        }
    },

    updateTerminalSubtitle() {
        const subtitle = document.getElementById('terminal-subtitle');
        if (subtitle) {
            const tab = this.tabs.find(t => t.id === this.selectedTabId);
            subtitle.textContent = tab ? (tab.name || 'Terminal ' + tab.id) : 'Command Line';
        }
    },

    open() {
        this.modal = document.getElementById('terminal-modal');
        if (!this.modal) return;

        this.terminal1 = document.getElementById('terminal-1');
        this.terminal2 = document.getElementById('terminal-2');
        this.wrapper2 = document.getElementById('terminal-2-wrapper');
        this.toggleArrow = document.getElementById('toggle-arrow');
        this.toggleLabel = document.getElementById('toggle-label');

        // Load Terminal 1
        if (this.terminal1 && !this.terminal1.src) {
            this.terminal1.src = window.location.protocol + '//' + window.location.hostname + ':7681';
        }

        // Update modal header with current tab name
        this.updateModalHeader();

        // Show modal
        this.modal.classList.add('active');
        document.body.style.overflow = 'hidden';
        Haptic.medium();
    },

    close() {
        if (!this.modal) return;

        // Keep iframe connections alive - just hide the modal with CSS
        // (Previously cleared src which caused reconnect delays)

        // Reset expanded state
        if (this.wrapper2) this.wrapper2.classList.remove('expanded');
        if (this.toggleArrow) this.toggleArrow.classList.remove('rotated');
        if (this.toggleLabel) this.toggleLabel.textContent = 'Show Terminal 2';
        this.isExpanded = false;

        // Hide modal
        this.modal.classList.remove('active');
        document.body.style.overflow = '';
        Haptic.light();
    },

    toggleSecondTerminal() {
        if (!this.wrapper2 || !this.toggleArrow || !this.toggleLabel) return;

        this.isExpanded = !this.isExpanded;

        if (this.isExpanded) {
            // Load Terminal 2 if not loaded
            if (this.terminal2 && !this.terminal2.src) {
                this.terminal2.src = window.location.protocol + '//' + window.location.hostname + ':7682';
            }
            this.wrapper2.classList.add('expanded');
            this.toggleArrow.classList.add('rotated');
            this.toggleLabel.textContent = 'Hide Terminal 2';
        } else {
            this.wrapper2.classList.remove('expanded');
            this.toggleArrow.classList.remove('rotated');
            this.toggleLabel.textContent = 'Show Terminal 2';
        }

        Haptic.light();
    },

    uploadDir: '/home/pds/boomshakalaka/uploads',

    openUpload() {
        document.getElementById('mobile-file-input').click();
    },

    async handleFileSelect(event) {
        const files = event.target.files;
        if (!files.length) return;
        for (const file of files) {
            try {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('target_dir', this.uploadDir);
                const response = await fetch('/api/terminal/files/upload', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                if (result.success) {
                    this.showUploadSuccess(result.filename, result.path);
                } else {
                    Toast.show(`Failed: ${result.error}`, 'error');
                }
            } catch (e) {
                Toast.show(`Upload error: ${e.message}`, 'error');
            }
        }
        event.target.value = '';
    },

    showUploadSuccess(filename, fullPath) {
        const dir = fullPath.substring(0, fullPath.lastIndexOf('/'));
        const modal = document.createElement('div');
        modal.className = 'upload-success-modal';
        modal.innerHTML = `
            <div class="upload-success-content">
                <div class="upload-success-icon">&#10004;</div>
                <div class="upload-success-title">Upload Complete!</div>
                <div class="upload-success-file">${filename}</div>
                <div class="upload-success-path-label">Directory:</div>
                <div class="upload-success-path">${dir}</div>
                <button class="upload-copy-btn" onclick="navigator.clipboard.writeText('${dir}'); this.textContent='Copied!'; setTimeout(() => this.textContent='Copy Path', 1500)">Copy Path</button>
                <button class="upload-dismiss-btn" onclick="this.closest('.upload-success-modal').remove()">Done</button>
            </div>
        `;
        document.body.appendChild(modal);
        Haptic.medium();
    }
};

// =============================================
// INITIALIZE ON DOM READY
// =============================================
document.addEventListener('DOMContentLoaded', () => {
    MobileNav.init();
    BottomSheet.init();
    document.querySelectorAll('.adventure-card.interactive, .btn, .list-item').forEach(el => {
        el.addEventListener('touchstart', () => Haptic.light(), { passive: true });
    });

    // Initialize terminal tab management
    TerminalModal.init();

    // Eager load terminal iframes for instant display when modal opens
    const terminal1 = document.getElementById('terminal-1');
    const terminal2 = document.getElementById('terminal-2');
    const baseUrl = window.location.protocol + '//' + window.location.hostname;

    if (terminal1 && !terminal1.src) {
        terminal1.src = baseUrl + ':7681';
    }
    if (terminal2 && !terminal2.src) {
        terminal2.src = baseUrl + ':7682';
    }
});

// Export
window.MobileNav = MobileNav;
window.TouchGestures = TouchGestures;
window.PullToRefresh = PullToRefresh;
window.BottomSheet = BottomSheet;
window.Toast = Toast;
window.Haptic = Haptic;
window.Utils = Utils;
window.SwipeableList = SwipeableList;
window.DragDrop = DragDrop;
window.TerminalModal = TerminalModal;
