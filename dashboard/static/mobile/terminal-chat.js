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
    showOnlySummaries: false, // Filter mode: show only summaries

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
            workingElapsed: document.querySelector('.working-elapsed')
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

        // Summary filter button
        const filterBtn = document.getElementById('summary-filter-btn');
        if (filterBtn) {
            filterBtn.addEventListener('click', () => this.toggleSummaryFilter());
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

        // Filter messages if summary mode is active
        let messagesToRender = this.messages;
        if (this.showOnlySummaries) {
            messagesToRender = this.messages.filter(msg =>
                msg.type === 'summary' || msg.type === 'user' || msg.type === 'error'
            );
        }

        if (messagesToRender.length === 0) {
            this.elements.messages.innerHTML = `
                <div class="chat-messages-empty">
                    <div class="chat-messages-empty-icon">🗺️</div>
                    <div class="chat-messages-empty-text">
                        ${this.showOnlySummaries ? 'No summaries yet.<br>Send a message to begin.' : 'No conversation yet.<br>Send a message to begin.'}
                    </div>
                </div>
            `;
            return;
        }

        const html = messagesToRender.map((msg, idx) => this.renderMessage(msg, idx)).join('');
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

            case 'summary':
                return `
                    <div class="chat-message summary">
                        <div class="summary-bubble">
                            <div class="summary-icon">●</div>
                            <div class="summary-content">${this.formatSummaryMessage(msg.content)}</div>
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
     * Format summary message with basic markdown and table support
     */
    formatSummaryMessage(content) {
        if (!content) return '';

        let text = this.escapeHtml(content);

        // Preserve ASCII tables (box-drawing characters)
        if (text.includes('┌') || text.includes('│') || text.includes('└') ||
            text.includes('╭') || text.includes('╰')) {
            return `<pre class="summary-table">${text}</pre>`;
        }

        // Convert inline code
        text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Convert bold
        text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Convert bullet points
        text = text.replace(/^- (.+)$/gm, '<li>$1</li>');
        if (text.includes('<li>')) {
            text = text.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
        }

        // Convert double newlines to paragraphs
        text = text.replace(/\n\n/g, '</p><p>');
        if (!text.startsWith('<p>') && !text.startsWith('<ul>') && !text.startsWith('<pre>')) {
            text = '<p>' + text + '</p>';
        }

        return text;
    },

    /**
     * Toggle summary filter mode
     */
    toggleSummaryFilter() {
        this.showOnlySummaries = !this.showOnlySummaries;
        this.renderMessages();

        const filterBtn = document.getElementById('summary-filter-btn');
        if (filterBtn) {
            filterBtn.classList.toggle('active', this.showOnlySummaries);
        }

        if (typeof Haptic !== 'undefined') {
            Haptic.light();
        }
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

    // Inline Terminal states
    isTerminal1Expanded: false,
    isTerminal2Expanded: false,

    /**
     * Toggle inline Terminal 1 visibility
     */
    toggleTerminal1Inline() {
        this.isTerminal1Expanded = !this.isTerminal1Expanded;

        const wrapper = document.getElementById('terminal1-inline-wrapper');
        const arrow = document.getElementById('terminal1-arrow');
        const label = document.getElementById('terminal1-label');
        const frame = document.getElementById('terminal1-inline-frame');

        if (this.isTerminal1Expanded) {
            // Load iframe if needed (check attribute, not property)
            const currentSrc = frame.getAttribute('src');
            if (!currentSrc) {
                frame.src = location.protocol + '//' + location.hostname + ':7681/';
            }
            wrapper.classList.add('expanded');
            arrow.classList.add('rotated');
            label.textContent = 'Collapse Terminal 1';
        } else {
            wrapper.classList.remove('expanded');
            arrow.classList.remove('rotated');
            label.textContent = 'Expand Terminal 1';
        }

        if (typeof Haptic !== 'undefined') {
            Haptic.light();
        }
    },

    /**
     * Toggle inline Terminal 2 visibility
     */
    toggleTerminal2Inline() {
        this.isTerminal2Expanded = !this.isTerminal2Expanded;

        const wrapper = document.getElementById('terminal2-inline-wrapper');
        const arrow = document.getElementById('terminal2-arrow');
        const label = document.getElementById('terminal2-label');
        const frame = document.getElementById('terminal2-inline-frame');

        if (this.isTerminal2Expanded) {
            // Load iframe if needed (check attribute, not property)
            const currentSrc = frame.getAttribute('src');
            if (!currentSrc) {
                frame.src = location.protocol + '//' + location.hostname + ':7682/';
            }
            wrapper.classList.add('expanded');
            arrow.classList.add('rotated');
            label.textContent = 'Collapse Terminal 2';
        } else {
            wrapper.classList.remove('expanded');
            arrow.classList.remove('rotated');
            label.textContent = 'Expand Terminal 2';
        }

        if (typeof Haptic !== 'undefined') {
            Haptic.light();
        }
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
