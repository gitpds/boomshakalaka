/**
 * Terminal Chat - Mobile Conversational Interface for Claude Code
 *
 * Provides a chat-like interface that displays parsed Claude Code output
 * from tmux terminal sessions.
 */

const TerminalChat = {
    // State
    messages: [],
    currentState: 'idle', // 'idle', 'working', 'done'
    selectedWindowId: null, // Active tmux window id
    windows: [], // Terminal windows from API

    // Polling
    pollInterval: null,
    pollRate: 3000, // Base poll rate (idle)
    fastPollRate: 500, // Fast poll rate (working)
    isPolling: false,

    // Working timer
    workingStartTime: null,
    workingTimerInterval: null,

    // DOM elements (cached)
    elements: {},

    // Last buffer hash to detect changes
    lastBufferHash: '',

    /**
     * Initialize the chat component
     */
    init() {
        // Cache DOM elements
        this.elements = {
            container: document.getElementById('terminal-chat-view'),
            messages: document.getElementById('chat-messages'),
            input: document.getElementById('chat-input'),
            sendBtn: document.getElementById('send-btn'),
            windowSelector: document.getElementById('window-selector'),
            workingIndicator: document.getElementById('working-indicator'),
            workingElapsed: document.querySelector('.working-elapsed'),
            rawTerminalOverlay: document.getElementById('raw-terminal-overlay'),
            rawTerminalFrame: document.getElementById('raw-terminal-frame')
        };

        // Validate required elements
        if (!this.elements.container || !this.elements.messages) {
            console.warn('TerminalChat: Required elements not found');
            return;
        }

        // Set up event listeners
        this.setupEventListeners();

        // Load available terminal windows
        this.loadWindows();

        // Start polling
        this.startPolling();

        // Handle page visibility
        this.setupVisibilityHandler();

        console.log('TerminalChat initialized');
    },

    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Send button click
        if (this.elements.sendBtn) {
            this.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        }

        // Input field enter key
        if (this.elements.input) {
            this.elements.input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });

            // Auto-resize textarea
            this.elements.input.addEventListener('input', () => {
                this.elements.input.style.height = 'auto';
                this.elements.input.style.height = Math.min(this.elements.input.scrollHeight, 120) + 'px';
            });
        }

        // Window selector change - switch tmux window (syncs both sessions)
        if (this.elements.windowSelector) {
            this.elements.windowSelector.addEventListener('change', (e) => {
                this.selectWindow(e.target.value);
            });
        }
    },

    /**
     * Handle page visibility changes to pause/resume polling
     */
    setupVisibilityHandler() {
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopPolling();
            } else {
                this.startPolling();
                this.fetchBuffer(); // Immediate fetch on resume
            }
        });
    },

    /**
     * Load available terminal windows from API
     */
    async loadWindows() {
        try {
            const response = await fetch('/api/terminal/windows');
            if (response.ok) {
                const data = await response.json();
                this.windows = data.windows || [];

                // Find the active window or default to first
                const activeWindow = this.windows.find(w => w.active) || this.windows[0];
                if (activeWindow) {
                    this.selectedWindowId = activeWindow.id;
                }

                this.updateWindowSelector();
                this.fetchBuffer(); // Initial fetch after windows loaded
            }
        } catch (error) {
            console.error('Failed to load terminal windows:', error);
        }
    },

    /**
     * Update window selector dropdown with actual terminal windows
     */
    updateWindowSelector() {
        if (!this.elements.windowSelector) return;

        if (this.windows.length === 0) {
            this.elements.windowSelector.innerHTML = '<option value="">No terminals</option>';
            return;
        }

        const html = this.windows.map(w =>
            `<option value="${w.id}" ${w.id === this.selectedWindowId ? 'selected' : ''}>${w.name}</option>`
        ).join('');

        this.elements.windowSelector.innerHTML = html;
    },

    /**
     * Select a terminal window - switches both dashboard-top and dashboard-bottom
     */
    async selectWindow(windowId) {
        try {
            const response = await fetch(`/api/terminal/windows/${windowId}/select`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                this.selectedWindowId = windowId;

                // Update active state in local windows array
                this.windows.forEach(w => w.active = (w.id === windowId));
                this.updateWindowSelector();

                // Clear and refresh messages for new window
                this.messages = [];
                this.lastBufferHash = '';
                this.renderMessages();
                this.fetchBuffer();

                // Haptic feedback
                if (typeof Haptic !== 'undefined') {
                    Haptic.light();
                }
            }
        } catch (error) {
            console.error('Failed to select window:', error);
            if (typeof Toast !== 'undefined') {
                Toast.error('Failed to switch terminal');
            }
        }
    },

    /**
     * Start polling for updates
     */
    startPolling() {
        if (this.isPolling) return;

        this.isPolling = true;
        this.poll();
    },

    /**
     * Stop polling
     */
    stopPolling() {
        this.isPolling = false;
        if (this.pollInterval) {
            clearTimeout(this.pollInterval);
            this.pollInterval = null;
        }
    },

    /**
     * Polling loop with adaptive rate
     */
    poll() {
        if (!this.isPolling) return;

        // Check state first (lightweight)
        this.checkState().then(() => {
            // Schedule next poll based on state
            const rate = this.currentState === 'working' ? this.fastPollRate : this.pollRate;
            this.pollInterval = setTimeout(() => this.poll(), rate);
        });
    },

    /**
     * Check terminal state (lightweight endpoint)
     * Always uses dashboard-top session - window switching is handled separately
     */
    async checkState() {
        try {
            const response = await fetch('/api/terminal/chat/state?session=dashboard-top');
            if (!response.ok) return;

            const data = await response.json();
            const newState = data.state;

            // State changed
            if (newState !== this.currentState) {
                this.currentState = newState;
                this.updateWorkingIndicator();

                // Fetch full buffer on state change
                await this.fetchBuffer();
            } else if (newState === 'working') {
                // Still working, fetch buffer to get updates
                await this.fetchBuffer();
            }
        } catch (error) {
            console.error('State check failed:', error);
        }
    },

    /**
     * Fetch and parse terminal buffer
     * Always uses dashboard-top session - window switching is handled separately
     */
    async fetchBuffer() {
        try {
            const response = await fetch(
                '/api/terminal/chat/buffer?session=dashboard-top&lines=500'
            );

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.error) {
                console.error('Buffer error:', data.error);
                return;
            }

            // Check if buffer changed
            const bufferHash = this.hashMessages(data.messages);
            if (bufferHash === this.lastBufferHash) {
                return; // No changes
            }

            this.lastBufferHash = bufferHash;
            this.messages = data.messages;
            this.currentState = data.state;

            this.renderMessages();
            this.updateWorkingIndicator();

        } catch (error) {
            console.error('Buffer fetch failed:', error);
        }
    },

    /**
     * Generate simple hash for change detection
     */
    hashMessages(messages) {
        return messages.length + ':' + messages.slice(-5).map(m => m.content?.slice(0, 50)).join('|');
    },

    /**
     * Send user message to terminal
     */
    async sendMessage() {
        const text = this.elements.input?.value?.trim();
        if (!text) return;

        // Clear input
        this.elements.input.value = '';
        this.elements.input.style.height = 'auto';

        // Disable send button temporarily
        if (this.elements.sendBtn) {
            this.elements.sendBtn.disabled = true;
        }

        // Haptic feedback
        if (typeof Haptic !== 'undefined') {
            Haptic.light();
        }

        try {
            // Always send to dashboard-top - window switching is handled separately
            const response = await fetch('/api/terminal/chat/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    session: 'dashboard-top'
                })
            });

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error || 'Send failed');
            }

            // Immediately show working state
            this.currentState = 'working';
            this.updateWorkingIndicator();

            // Immediate fetch, then fast polling
            setTimeout(() => this.fetchBuffer(), 100);

        } catch (error) {
            console.error('Send failed:', error);
            if (typeof Toast !== 'undefined') {
                Toast.error('Failed to send message');
            }
        } finally {
            if (this.elements.sendBtn) {
                this.elements.sendBtn.disabled = false;
            }
        }
    },

    /**
     * Render messages to the chat view
     */
    renderMessages() {
        if (!this.elements.messages) return;

        if (this.messages.length === 0) {
            this.elements.messages.innerHTML = `
                <div class="chat-messages-empty">
                    <div class="chat-messages-empty-icon">🗺️</div>
                    <div class="chat-messages-empty-text">
                        No conversation yet.<br>
                        Send a message to begin.
                    </div>
                </div>
            `;
            return;
        }

        const html = this.messages.map((msg, idx) => this.renderMessage(msg, idx)).join('');
        this.elements.messages.innerHTML = html;

        // Scroll to bottom
        this.scrollToBottom();

        // Attach tool toggle listeners
        this.attachToolToggles();
    },

    /**
     * Render a single message
     */
    renderMessage(msg, idx) {
        const type = msg.type || 'assistant';

        switch (type) {
            case 'user':
                return `
                    <div class="chat-message user">
                        <div class="message-bubble">${this.escapeHtml(msg.content)}</div>
                    </div>
                `;

            case 'assistant':
                return `
                    <div class="chat-message assistant">
                        <div class="message-bubble">${this.formatAssistantMessage(msg.content)}</div>
                    </div>
                `;

            case 'tool':
                return `
                    <div class="chat-message tool">
                        <div class="tool-bubble" data-tool-idx="${idx}">
                            <div class="tool-header">
                                <span class="tool-name">
                                    <span class="tool-icon">●</span>
                                    ${this.escapeHtml(msg.tool_name || 'Tool')}
                                </span>
                                <span class="tool-chevron">▼</span>
                            </div>
                            <div class="tool-content">${this.escapeHtml(msg.content)}</div>
                        </div>
                    </div>
                `;

            case 'tool_output':
                return `
                    <div class="chat-message tool_output">
                        <div class="tool-bubble" data-tool-idx="${idx}">
                            <div class="tool-header">
                                <span class="tool-name">
                                    <span class="tool-icon">⎿</span>
                                    Output
                                </span>
                                <span class="tool-chevron">▼</span>
                            </div>
                            <div class="tool-content">${this.escapeHtml(msg.content)}</div>
                        </div>
                    </div>
                `;

            case 'task':
                return `
                    <div class="chat-message task">
                        <div class="task-bubble">
                            <span class="task-icon">✔</span>
                            <span>${this.escapeHtml(msg.content)}</span>
                        </div>
                    </div>
                `;

            case 'error':
                return `
                    <div class="chat-message error">
                        <div class="error-bubble">
                            <span class="error-icon">✘</span>
                            <span>${this.escapeHtml(msg.content)}</span>
                        </div>
                    </div>
                `;

            default:
                return `
                    <div class="chat-message assistant">
                        <div class="message-bubble">${this.escapeHtml(msg.content)}</div>
                    </div>
                `;
        }
    },

    /**
     * Format assistant message with basic markdown
     */
    formatAssistantMessage(content) {
        if (!content) return '';

        let text = this.escapeHtml(content);

        // Convert code blocks
        text = text.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

        // Convert inline code
        text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Convert bold
        text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Convert paragraphs (double newlines)
        text = text.replace(/\n\n/g, '</p><p>');

        // Wrap in paragraph
        if (!text.startsWith('<p>')) {
            text = '<p>' + text + '</p>';
        }

        return text;
    },

    /**
     * Escape HTML special characters
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    /**
     * Attach click handlers for tool collapsibles
     */
    attachToolToggles() {
        const toolBubbles = this.elements.messages.querySelectorAll('.tool-bubble');
        toolBubbles.forEach(bubble => {
            const header = bubble.querySelector('.tool-header');
            if (header) {
                header.addEventListener('click', () => {
                    bubble.classList.toggle('expanded');
                    if (typeof Haptic !== 'undefined') {
                        Haptic.light();
                    }
                });
            }
        });
    },

    /**
     * Scroll chat to bottom
     */
    scrollToBottom() {
        if (this.elements.messages) {
            this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
        }
    },

    /**
     * Update working indicator visibility and timer
     */
    updateWorkingIndicator() {
        if (!this.elements.workingIndicator) return;

        if (this.currentState === 'working') {
            this.elements.workingIndicator.classList.remove('hidden');

            // Start timer
            if (!this.workingStartTime) {
                this.workingStartTime = Date.now();
                this.startWorkingTimer();
            }
        } else {
            this.elements.workingIndicator.classList.add('hidden');

            // Stop timer
            this.workingStartTime = null;
            this.stopWorkingTimer();
        }
    },

    /**
     * Start the working elapsed time display
     */
    startWorkingTimer() {
        if (this.workingTimerInterval) return;

        this.workingTimerInterval = setInterval(() => {
            if (this.workingStartTime && this.elements.workingElapsed) {
                const elapsed = Math.floor((Date.now() - this.workingStartTime) / 1000);
                this.elements.workingElapsed.textContent = `${elapsed}s`;
            }
        }, 1000);
    },

    /**
     * Stop the working timer
     */
    stopWorkingTimer() {
        if (this.workingTimerInterval) {
            clearInterval(this.workingTimerInterval);
            this.workingTimerInterval = null;
        }
        if (this.elements.workingElapsed) {
            this.elements.workingElapsed.textContent = '0s';
        }
    },

    // Raw terminal state
    isTerminal2Expanded: false,

    /**
     * Toggle raw terminal overlay
     */
    toggleRawTerminal() {
        if (!this.elements.rawTerminalOverlay) {
            // Create overlay if it doesn't exist
            this.createRawTerminalOverlay();
        }

        const overlay = this.elements.rawTerminalOverlay;
        const isVisible = overlay.classList.contains('visible');

        if (isVisible) {
            overlay.classList.remove('visible');
        } else {
            overlay.classList.add('visible');
            // Load terminal 1 iframe if needed
            const frame1 = overlay.querySelector('#raw-terminal-frame-1');
            if (frame1 && !frame1.src) {
                const baseUrl = window.location.protocol + '//' + window.location.hostname;
                frame1.src = baseUrl + ':7681/';
            }
        }

        if (typeof Haptic !== 'undefined') {
            Haptic.medium();
        }
    },

    /**
     * Toggle Terminal 2 visibility in raw terminal overlay
     */
    toggleTerminal2() {
        this.isTerminal2Expanded = !this.isTerminal2Expanded;

        const wrapper = document.getElementById('raw-terminal-2-wrapper');
        const arrow = document.getElementById('raw-toggle-arrow');
        const label = document.getElementById('raw-toggle-label');

        if (this.isTerminal2Expanded) {
            // Load Terminal 2 iframe if needed
            const frame2 = document.getElementById('raw-terminal-frame-2');
            if (frame2 && !frame2.src) {
                const baseUrl = window.location.protocol + '//' + window.location.hostname;
                frame2.src = baseUrl + ':7682/';
            }
            wrapper.classList.add('expanded');
            arrow.classList.add('rotated');
            label.textContent = 'Hide Terminal 2';
        } else {
            wrapper.classList.remove('expanded');
            arrow.classList.remove('rotated');
            label.textContent = 'Show Terminal 2';
        }

        if (typeof Haptic !== 'undefined') {
            Haptic.light();
        }
    },

    /**
     * Create raw terminal overlay with both terminals
     */
    createRawTerminalOverlay() {
        const overlay = document.createElement('div');
        overlay.id = 'raw-terminal-overlay';
        overlay.className = 'raw-terminal-overlay';
        overlay.innerHTML = `
            <div class="raw-terminal-header">
                <span class="raw-terminal-title">Raw Terminal</span>
                <button class="raw-terminal-close" onclick="TerminalChat.toggleRawTerminal()">✕</button>
            </div>
            <div class="raw-terminal-body">
                <iframe id="raw-terminal-frame-1" class="raw-terminal-frame" src="" frameborder="0"></iframe>
                <div id="raw-terminal-2-wrapper" class="raw-terminal-2-wrapper">
                    <iframe id="raw-terminal-frame-2" class="raw-terminal-frame" src="" frameborder="0"></iframe>
                </div>
            </div>
            <div class="raw-terminal-toggle" onclick="TerminalChat.toggleTerminal2()">
                <span class="raw-toggle-arrow" id="raw-toggle-arrow">▲</span>
                <span id="raw-toggle-label">Show Terminal 2</span>
            </div>
        `;

        document.body.appendChild(overlay);

        this.elements.rawTerminalOverlay = overlay;
    },

    /**
     * Clean up on destroy
     */
    destroy() {
        this.stopPolling();
        this.stopWorkingTimer();
    }
};

// Export for global access
window.TerminalChat = TerminalChat;
