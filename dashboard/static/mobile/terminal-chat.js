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
    selectedSession: 'dashboard-top',
    sessions: [],

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
            sessionSelector: document.getElementById('session-selector'),
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

        // Load available sessions
        this.loadSessions();

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

        // Session selector change
        if (this.elements.sessionSelector) {
            this.elements.sessionSelector.addEventListener('change', (e) => {
                this.selectedSession = e.target.value;
                this.messages = [];
                this.lastBufferHash = '';
                this.renderMessages();
                this.fetchBuffer();
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
     * Load available terminal sessions
     */
    async loadSessions() {
        try {
            const response = await fetch('/api/terminal/windows');
            if (response.ok) {
                const data = await response.json();
                this.sessions = data.windows || [];
                this.updateSessionSelector();
            }
        } catch (error) {
            console.error('Failed to load sessions:', error);
        }
    },

    /**
     * Update session selector dropdown
     */
    updateSessionSelector() {
        if (!this.elements.sessionSelector) return;

        // Always include default sessions
        const defaultSessions = [
            { id: 'dashboard-top', name: 'Terminal 1' },
            { id: 'dashboard-bottom', name: 'Terminal 2' }
        ];

        const html = defaultSessions.map(s =>
            `<option value="${s.id}" ${s.id === this.selectedSession ? 'selected' : ''}>${s.name}</option>`
        ).join('');

        this.elements.sessionSelector.innerHTML = html;
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
     */
    async checkState() {
        try {
            const response = await fetch(`/api/terminal/chat/state?session=${encodeURIComponent(this.selectedSession)}`);
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
     */
    async fetchBuffer() {
        try {
            const response = await fetch(
                `/api/terminal/chat/buffer?session=${encodeURIComponent(this.selectedSession)}&lines=500`
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
            const response = await fetch('/api/terminal/chat/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    session: this.selectedSession
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
            // Load terminal iframe if needed
            if (this.elements.rawTerminalFrame && !this.elements.rawTerminalFrame.src) {
                this.elements.rawTerminalFrame.src = 'http://localhost:7681/';
            }
        }

        if (typeof Haptic !== 'undefined') {
            Haptic.medium();
        }
    },

    /**
     * Create raw terminal overlay
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
                <iframe id="raw-terminal-frame" src="" frameborder="0"></iframe>
            </div>
        `;

        document.body.appendChild(overlay);

        this.elements.rawTerminalOverlay = overlay;
        this.elements.rawTerminalFrame = overlay.querySelector('#raw-terminal-frame');
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
