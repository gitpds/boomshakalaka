// Mock Haptic API
global.Haptic = {
  light: jest.fn()
};

// Helper to create DOM fixture for terminal chat
global.createTerminalChatFixture = () => {
  document.body.innerHTML = `
    <div class="terminal-expand-section">
      <div class="terminal-expand-bar">
        <span class="terminal-expand-arrow" id="terminal1-arrow"></span>
        <span id="terminal1-label">Expand Terminal 1</span>
      </div>
      <div class="terminal-inline-wrapper" id="terminal1-inline-wrapper">
        <iframe id="terminal1-inline-frame" src="" frameborder="0"></iframe>
      </div>
    </div>
    <div class="terminal-expand-section">
      <div class="terminal-expand-bar">
        <span class="terminal-expand-arrow" id="terminal2-arrow"></span>
        <span id="terminal2-label">Expand Terminal 2</span>
      </div>
      <div class="terminal-inline-wrapper" id="terminal2-inline-wrapper">
        <iframe id="terminal2-inline-frame" src="" frameborder="0"></iframe>
      </div>
    </div>
  `;
};

// Reset state before each test
beforeEach(() => {
  jest.clearAllMocks();
});
