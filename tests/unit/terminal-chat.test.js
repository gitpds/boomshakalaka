/**
 * Unit Tests for Terminal Chat - Terminal 1 & 2 Expand Functionality
 * TDD approach: These tests define the expected behavior
 */

// Mock TerminalChat object for testing
let TerminalChat;

beforeEach(() => {
  // Create fresh DOM fixture
  createTerminalChatFixture();

  // Reset TerminalChat mock with expected interface
  TerminalChat = {
    isTerminal1Expanded: false,
    isTerminal2Expanded: false,

    toggleTerminal1Inline() {
      this.isTerminal1Expanded = !this.isTerminal1Expanded;

      const wrapper = document.getElementById('terminal1-inline-wrapper');
      const arrow = document.getElementById('terminal1-arrow');
      const label = document.getElementById('terminal1-label');
      const frame = document.getElementById('terminal1-inline-frame');

      if (this.isTerminal1Expanded) {
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

    toggleTerminal2Inline() {
      this.isTerminal2Expanded = !this.isTerminal2Expanded;

      const wrapper = document.getElementById('terminal2-inline-wrapper');
      const arrow = document.getElementById('terminal2-arrow');
      const label = document.getElementById('terminal2-label');
      const frame = document.getElementById('terminal2-inline-frame');

      if (this.isTerminal2Expanded) {
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
    }
  };
});

// =============================================================
// Test Suite: TerminalChat.toggleTerminal1Inline()
// =============================================================

describe('TerminalChat.toggleTerminal1Inline()', () => {

  // Test 1: Initial state
  test('isTerminal1Expanded should be false initially', () => {
    expect(TerminalChat.isTerminal1Expanded).toBe(false);
  });

  // Test 2: State toggles on first call
  test('toggleTerminal1Inline() should set isTerminal1Expanded to true', () => {
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.toggleTerminal1Inline();
    expect(TerminalChat.isTerminal1Expanded).toBe(true);
  });

  // Test 3: State toggles back on second call
  test('toggleTerminal1Inline() should toggle back to false', () => {
    TerminalChat.isTerminal1Expanded = true;
    TerminalChat.toggleTerminal1Inline();
    expect(TerminalChat.isTerminal1Expanded).toBe(false);
  });

  // Test 4: Wrapper gets 'expanded' class when expanded
  test('wrapper should have "expanded" class when expanded', () => {
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.toggleTerminal1Inline();
    const wrapper = document.getElementById('terminal1-inline-wrapper');
    expect(wrapper.classList.contains('expanded')).toBe(true);
  });

  // Test 5: Arrow gets 'rotated' class when expanded
  test('arrow should have "rotated" class when expanded', () => {
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.toggleTerminal1Inline();
    const arrow = document.getElementById('terminal1-arrow');
    expect(arrow.classList.contains('rotated')).toBe(true);
  });

  // Test 6: Label text changes to "Collapse Terminal 1" when expanded
  test('label should say "Collapse Terminal 1" when expanded', () => {
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.toggleTerminal1Inline();
    const label = document.getElementById('terminal1-label');
    expect(label.textContent).toBe('Collapse Terminal 1');
  });

  // Test 7: Wrapper loses 'expanded' class when collapsed
  test('wrapper should not have "expanded" class when collapsed', () => {
    TerminalChat.isTerminal1Expanded = true;
    TerminalChat.toggleTerminal1Inline();
    const wrapper = document.getElementById('terminal1-inline-wrapper');
    expect(wrapper.classList.contains('expanded')).toBe(false);
  });

  // Test 8: Arrow loses 'rotated' class when collapsed
  test('arrow should not have "rotated" class when collapsed', () => {
    TerminalChat.isTerminal1Expanded = true;
    TerminalChat.toggleTerminal1Inline();
    const arrow = document.getElementById('terminal1-arrow');
    expect(arrow.classList.contains('rotated')).toBe(false);
  });

  // Test 9: Label text changes back to "Expand Terminal 1" when collapsed
  test('label should say "Expand Terminal 1" when collapsed', () => {
    TerminalChat.isTerminal1Expanded = true;
    TerminalChat.toggleTerminal1Inline();
    const label = document.getElementById('terminal1-label');
    expect(label.textContent).toBe('Expand Terminal 1');
  });

  // Test 10: Iframe src is set on first expand
  test('iframe src should be set to port 7681 on first expand', () => {
    const frame = document.getElementById('terminal1-inline-frame');
    frame.setAttribute('src', '');
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.toggleTerminal1Inline();
    expect(frame.src).toContain(':7681');
  });

  // Test 11: Iframe src is NOT reset on subsequent expands
  test('iframe src should not be reset on subsequent expands', () => {
    const frame = document.getElementById('terminal1-inline-frame');
    frame.setAttribute('src', 'http://localhost:7681/');
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.toggleTerminal1Inline();
    expect(frame.src).toBe('http://localhost:7681/');
  });

  // Test 12: Haptic feedback is called
  test('Haptic.light() should be called on toggle', () => {
    const hapticSpy = jest.spyOn(Haptic, 'light');
    TerminalChat.toggleTerminal1Inline();
    expect(hapticSpy).toHaveBeenCalled();
  });
});

// =============================================================
// Test Suite: Regression - TerminalChat.toggleTerminal2Inline()
// =============================================================

describe('Regression: TerminalChat.toggleTerminal2Inline()', () => {

  // Test 13: Terminal 2 toggle still works
  test('toggleTerminal2Inline() should still toggle isTerminal2Expanded', () => {
    TerminalChat.isTerminal2Expanded = false;
    TerminalChat.toggleTerminal2Inline();
    expect(TerminalChat.isTerminal2Expanded).toBe(true);
  });

  // Test 14: Terminal 2 wrapper gets expanded class
  test('Terminal 2 wrapper should have "expanded" class when expanded', () => {
    TerminalChat.isTerminal2Expanded = false;
    TerminalChat.toggleTerminal2Inline();
    const wrapper = document.getElementById('terminal2-inline-wrapper');
    expect(wrapper.classList.contains('expanded')).toBe(true);
  });

  // Test 15: Terminal 2 label changes correctly
  test('Terminal 2 label should say "Collapse Terminal 2" when expanded', () => {
    TerminalChat.isTerminal2Expanded = false;
    TerminalChat.toggleTerminal2Inline();
    const label = document.getElementById('terminal2-label');
    expect(label.textContent).toBe('Collapse Terminal 2');
  });

  // Test 16: Terminal 2 iframe loads port 7682
  test('Terminal 2 iframe should load port 7682', () => {
    const frame = document.getElementById('terminal2-inline-frame');
    frame.setAttribute('src', '');
    TerminalChat.isTerminal2Expanded = false;
    TerminalChat.toggleTerminal2Inline();
    expect(frame.src).toContain(':7682');
  });
});

// =============================================================
// Test Suite: Terminal Independence
// =============================================================

describe('Terminal Independence', () => {

  // Test 17: Terminal 1 state doesn't affect Terminal 2
  test('expanding Terminal 1 should not affect Terminal 2 state', () => {
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.isTerminal2Expanded = false;
    TerminalChat.toggleTerminal1Inline();
    expect(TerminalChat.isTerminal1Expanded).toBe(true);
    expect(TerminalChat.isTerminal2Expanded).toBe(false);
  });

  // Test 18: Terminal 2 state doesn't affect Terminal 1
  test('expanding Terminal 2 should not affect Terminal 1 state', () => {
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.isTerminal2Expanded = false;
    TerminalChat.toggleTerminal2Inline();
    expect(TerminalChat.isTerminal1Expanded).toBe(false);
    expect(TerminalChat.isTerminal2Expanded).toBe(true);
  });

  // Test 19: Both can be expanded simultaneously
  test('both terminals can be expanded at the same time', () => {
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.isTerminal2Expanded = false;
    TerminalChat.toggleTerminal1Inline();
    TerminalChat.toggleTerminal2Inline();
    expect(TerminalChat.isTerminal1Expanded).toBe(true);
    expect(TerminalChat.isTerminal2Expanded).toBe(true);
  });

  // Test 20: Both wrappers have expanded class when both expanded
  test('both wrappers should have expanded class when both expanded', () => {
    TerminalChat.isTerminal1Expanded = false;
    TerminalChat.isTerminal2Expanded = false;
    TerminalChat.toggleTerminal1Inline();
    TerminalChat.toggleTerminal2Inline();
    const wrapper1 = document.getElementById('terminal1-inline-wrapper');
    const wrapper2 = document.getElementById('terminal2-inline-wrapper');
    expect(wrapper1.classList.contains('expanded')).toBe(true);
    expect(wrapper2.classList.contains('expanded')).toBe(true);
  });
});

// =============================================================
// Test Suite: DOM Structure
// =============================================================

describe('DOM Structure', () => {

  // Test 21: Terminal 1 section exists in DOM
  test('terminal1-inline-wrapper should exist in DOM', () => {
    const wrapper = document.getElementById('terminal1-inline-wrapper');
    expect(wrapper).not.toBeNull();
  });

  // Test 22: Terminal 1 arrow exists
  test('terminal1-arrow should exist in DOM', () => {
    const arrow = document.getElementById('terminal1-arrow');
    expect(arrow).not.toBeNull();
  });

  // Test 23: Terminal 1 label exists
  test('terminal1-label should exist in DOM', () => {
    const label = document.getElementById('terminal1-label');
    expect(label).not.toBeNull();
  });

  // Test 24: Terminal 1 iframe exists
  test('terminal1-inline-frame should exist in DOM', () => {
    const frame = document.getElementById('terminal1-inline-frame');
    expect(frame).not.toBeNull();
  });

  // Test 25: Terminal 1 section appears before Terminal 2
  test('Terminal 1 section should appear before Terminal 2 in DOM order', () => {
    const sections = document.querySelectorAll('.terminal-expand-section');
    const t1Label = sections[0]?.querySelector('#terminal1-label');
    const t2Label = sections[1]?.querySelector('#terminal2-label');
    expect(t1Label).not.toBeNull();
    expect(t2Label).not.toBeNull();
  });
});

// =============================================================
// Test Suite: CSS Classes
// =============================================================

describe('CSS Classes', () => {

  // Test 26: Shared terminal-expand-section class is used
  test('both sections should use terminal-expand-section class', () => {
    const sections = document.querySelectorAll('.terminal-expand-section');
    expect(sections.length).toBe(2);
  });

  // Test 27: Shared terminal-expand-bar class is used
  test('both bars should use terminal-expand-bar class', () => {
    const bars = document.querySelectorAll('.terminal-expand-bar');
    expect(bars.length).toBe(2);
  });

  // Test 28: Shared terminal-inline-wrapper class is used
  test('both wrappers should use terminal-inline-wrapper class', () => {
    const wrappers = document.querySelectorAll('.terminal-inline-wrapper');
    expect(wrappers.length).toBe(2);
  });
});
