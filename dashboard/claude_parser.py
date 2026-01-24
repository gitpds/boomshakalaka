"""
Claude Code Terminal Output Parser

Parses tmux terminal buffer output from Claude Code sessions into
structured message format for the mobile conversational interface.
"""

import re
import subprocess
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class MessageType(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    TOOL_OUTPUT = "tool_output"
    SUMMARY = "summary"       # Claude's human-friendly summary messages
    TASK = "task"
    ERROR = "error"
    SYSTEM = "system"


class TerminalState(Enum):
    IDLE = "idle"           # Prompt visible, waiting for input
    WORKING = "working"     # Tool in progress
    DONE = "done"           # Response complete


@dataclass
class ParsedMessage:
    type: str
    content: str
    tool_name: Optional[str] = None
    collapsed: bool = False
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


# ANSI escape code pattern
ANSI_ESCAPE = re.compile(r'''
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
''', re.VERBOSE)

# Additional control characters to strip
CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Claude Code markers
MARKERS = {
    'prompt': '❯',           # User input prompt
    'tool': '●',             # Tool invocation OR summary
    'tool_output': '⎿',      # Tool output / continuation
    'continuation': '…',     # Continuation marker
    'task_complete': '✔',    # Task completion
    'task_pending': '☐',     # Pending task
    'error': '✘',            # Error marker
}

# Working/thinking indicators (should be filtered from output)
WORKING_MARKERS = {'✽', '✶', '⋮', '◐', '◑', '◒', '◓'}

# Patterns to filter out (terminal noise)
NOISE_PATTERNS = [
    re.compile(r'^▐▛'),                   # ASCII logo line 1
    re.compile(r'^▝▜'),                   # ASCII logo line 2
    re.compile(r'^\s*▘▘\s*▝▝'),           # ASCII logo line 3
    re.compile(r'^(\([^)]+\)\s*)+\w+@\w+:'), # Shell prompt: (env) user@host: or (env) (env) user@host:
    re.compile(r'^\w+@\w+:'),             # Shell prompt without env: user@host:
    re.compile(r'^─+$'),                  # Box-drawing horizontal lines (separator)
    re.compile(r'^--\s*\w+\s*--'),        # Vim mode: -- INSERT -- (with optional trailing text)
    re.compile(r'^⏵'),                    # Permission hint arrows (Claude Code UI)
    re.compile(r'bypass permissions'),    # Permission bypass (anywhere in line)
    re.compile(r'^\(Esc to interrupt'),   # Thinking hint
    re.compile(r'^Tips for getting'),     # Tips header
    re.compile(r'^\s*$'),                 # Empty lines
]

# Pattern to detect tool invocations: Word immediately followed by (
# Matches: Bash(, Read(, Write(, etc.
# Does NOT match: Done., "Done (files updated)", prose sentences
# Key: NO space allowed between word and parenthesis
TOOL_INVOCATION_PATTERN = re.compile(r'^([A-Z][a-zA-Z]*)\(')

# Known Claude Code modes (used for validation)
KNOWN_MODES = {
    'bypass permissions on',
    'accept edits on',
    'plan mode',
}

# Mode detection pattern - captures mode text from hint lines
# Matches: ⏵⏵ bypass permissions on (shift+Tab to cycle)
MODE_HINT_PATTERN = re.compile(r'⏵⏵\s*(.+?)\s*\(shift\+Tab', re.IGNORECASE)

# ANSI codes for dim/faint text (auto-complete suggestions appear dim)
# Matches: ESC[2m or ESC[0;2m followed by optional color codes, then text
# The dim text may have color resets between the dim code and actual text
DIM_TEXT_ANSI = re.compile(r'\x1b\[(?:0;)?2m(?:\x1b\[[0-9;]*m)*([^\x1b]+)')


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes and control characters from text."""
    text = ANSI_ESCAPE.sub('', text)
    text = CONTROL_CHARS.sub('', text)
    return text


def extract_mode_and_suggestion(raw_buffer: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract mode and suggestion from raw buffer BEFORE ANSI stripping.

    Args:
        raw_buffer: Raw terminal buffer with ANSI codes

    Returns:
        Tuple of (mode, suggestion) - both may be None if not found
    """
    mode = None
    suggestion = None

    for line in reversed(raw_buffer.split('\n')):
        clean_line = strip_ansi(line).strip()

        # Find mode hint (e.g., "⏵⏵ bypass permissions on (shift+Tab...")
        # Only accept known Claude Code modes to avoid false positives
        if mode is None:
            mode_match = MODE_HINT_PATTERN.search(clean_line)
            if mode_match:
                candidate = mode_match.group(1).strip().lower()
                # Check if it's a known mode
                if candidate in KNOWN_MODES:
                    mode = candidate

        # Find auto-complete suggestion (dim text after prompt on same line)
        # Format: ❯ <typed_char><dim_completion>
        # Example: ❯ s[dim]how me the readme[/dim]
        if suggestion is None and '❯' in line:
            prompt_idx = line.find('❯')
            after_prompt = line[prompt_idx + 1:]
            # Look for dim text (ESC[2m or ESC[0;2m)
            dim_match = DIM_TEXT_ANSI.search(after_prompt)
            if dim_match:
                dim_text = dim_match.group(1).strip()
                # Get any typed text before the dim suggestion
                before_dim = after_prompt[:dim_match.start()]
                typed_text = strip_ansi(before_dim).strip()
                # Combine typed + completion for full suggestion
                if dim_text:
                    suggestion = (typed_text + dim_text).strip()

        if mode is not None and suggestion is not None:
            break

    return mode, suggestion


def is_noise_line(line: str) -> bool:
    """Check if line is terminal noise that should be filtered."""
    stripped = line.strip()
    if not stripped:
        return True
    # Check working markers
    if any(stripped.startswith(m) for m in WORKING_MARKERS):
        return True
    # Check noise patterns
    for pattern in NOISE_PATTERNS:
        if pattern.match(stripped):
            return True
    return False


def capture_tmux_buffer(session: str, lines: int = 500, include_ansi: bool = False) -> Optional[str]:
    """
    Capture terminal buffer from tmux session.

    Args:
        session: tmux session name (e.g., 'dashboard-top')
        lines: Number of lines to capture (default 500)
        include_ansi: Include ANSI escape codes in output (default False)

    Returns:
        Raw terminal buffer content or None on error
    """
    try:
        cmd = ['tmux', 'capture-pane', '-t', session, '-p', '-S', f'-{lines}']
        if include_ansi:
            cmd.append('-e')  # Include escape sequences
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return None


def send_to_tmux(session: str, text: str) -> bool:
    """
    Send input to tmux session via send-keys.

    Args:
        session: tmux session name
        text: Text to send (Enter will be appended)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Send the text first
        result = subprocess.run(
            ['tmux', 'send-keys', '-t', session, text],
            capture_output=True,
            timeout=5
        )
        if result.returncode != 0:
            return False

        # Send Enter separately (combining in one command doesn't work reliably)
        result = subprocess.run(
            ['tmux', 'send-keys', '-t', session, 'Enter'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def detect_state(lines: List[str]) -> TerminalState:
    """
    Detect terminal state by analyzing the last few lines.

    State detection logic (work backwards from buffer end):
    - Line ends with `❯` alone → idle
    - Line starts with working spinner (✽, ✶, etc.) → working
    - Line starts with `●` → working
    - Line starts with `⎿` or `…` → working (tool output continuing)
    - Plain text after tool outputs → done/response complete
    """
    if not lines:
        return TerminalState.IDLE

    # Look at the last 10 non-empty lines
    recent_lines = []
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            recent_lines.append(stripped)
            if len(recent_lines) >= 10:
                break

    if not recent_lines:
        return TerminalState.IDLE

    last_line = recent_lines[0]

    # Check for idle state - prompt visible
    if last_line.endswith(MARKERS['prompt']) or last_line == MARKERS['prompt']:
        return TerminalState.IDLE

    # Check for working spinners in recent lines (highest priority)
    for line in recent_lines[:5]:
        stripped = line.strip()
        # Check for working/thinking markers
        if any(stripped.startswith(m) for m in WORKING_MARKERS):
            return TerminalState.WORKING
        if 'thinking' in stripped.lower() or 'orchestrating' in stripped.lower():
            return TerminalState.WORKING

    # Check for working state - tool in progress
    for line in recent_lines[:5]:
        # Tool invocation without completion
        if line.startswith(MARKERS['tool']):
            # Check if there's a response after this
            idx = recent_lines.index(line)
            if idx == 0:
                return TerminalState.WORKING

        # Continuation markers indicate ongoing output
        if line.startswith(MARKERS['tool_output']) or line.startswith(MARKERS['continuation']):
            return TerminalState.WORKING

    # Check if we see tool activity followed by plain text (done)
    saw_tool = False
    saw_text_after_tool = False
    for line in recent_lines:
        if line.startswith(MARKERS['tool']) or line.startswith(MARKERS['tool_output']):
            saw_tool = True
        elif saw_tool and not line.startswith(MARKERS['prompt']):
            # Plain text after tool output
            if not any(line.startswith(m) for m in MARKERS.values()):
                saw_text_after_tool = True

    if saw_tool and saw_text_after_tool:
        return TerminalState.DONE

    # Default to idle
    return TerminalState.IDLE


def parse_buffer(raw_buffer: str) -> Tuple[List[ParsedMessage], TerminalState]:
    """
    Parse raw terminal buffer into structured messages.

    Args:
        raw_buffer: Raw tmux capture output

    Returns:
        Tuple of (list of ParsedMessage, TerminalState)
    """
    # Strip ANSI codes
    clean_buffer = strip_ansi(raw_buffer)

    # Split into lines
    lines = clean_buffer.split('\n')

    # Detect state
    state = detect_state(lines)

    # Parse messages
    messages = []
    current_message = None
    current_content = []

    for line in lines:
        stripped = line.strip()

        # Skip noise lines (terminal chrome, spinners, etc.)
        # But preserve empty lines for assistant message formatting
        if stripped and is_noise_line(stripped):
            continue

        if not stripped:
            # Empty line - might be paragraph break in assistant response
            if current_message and current_message.type == MessageType.ASSISTANT.value:
                current_content.append('')
            continue

        # Check for user input (prompt marker)
        if MARKERS['prompt'] in stripped:
            # Save previous message
            if current_message and current_content:
                current_message.content = '\n'.join(current_content).strip()
                if current_message.content:
                    messages.append(current_message)

            # Extract user input after prompt
            prompt_idx = stripped.find(MARKERS['prompt'])
            user_input = stripped[prompt_idx + len(MARKERS['prompt']):].strip()

            if user_input:
                current_message = ParsedMessage(
                    type=MessageType.USER.value,
                    content=user_input
                )
                messages.append(current_message)
                current_message = None
                current_content = []
            else:
                current_message = None
                current_content = []
            continue

        # Check for bullet marker (tool invocation OR summary)
        if stripped.startswith(MARKERS['tool']):
            # Save previous message
            if current_message and current_content:
                current_message.content = '\n'.join(current_content).strip()
                if current_message.content:
                    messages.append(current_message)

            # Extract text after bullet marker
            bullet_text = stripped[len(MARKERS['tool']):].strip()

            # Check if this is a tool invocation (Word followed by parenthesis)
            tool_match = TOOL_INVOCATION_PATTERN.match(bullet_text)

            if tool_match:
                # TOOL invocation (e.g., "Bash(git push)")
                tool_name = tool_match.group(1)
                current_message = ParsedMessage(
                    type=MessageType.TOOL.value,
                    content=bullet_text,
                    tool_name=tool_name,
                    collapsed=True
                )
            else:
                # SUMMARY message (e.g., "Done. Committed and pushed.")
                current_message = ParsedMessage(
                    type=MessageType.SUMMARY.value,
                    content=bullet_text,
                    tool_name=None,
                    collapsed=False
                )
            current_content = [bullet_text]
            continue

        # Check for tool output
        if stripped.startswith(MARKERS['tool_output']) or stripped.startswith(MARKERS['continuation']):
            output_text = stripped[1:].strip() if stripped else ''

            if current_message and current_message.type == MessageType.TOOL.value:
                # Append to current tool
                current_content.append(output_text)
            elif current_message and current_message.type == MessageType.SUMMARY.value:
                # Append to current summary (continuation lines)
                current_content.append(output_text)
            else:
                # Save previous and start tool output
                if current_message and current_content:
                    current_message.content = '\n'.join(current_content).strip()
                    if current_message.content:
                        messages.append(current_message)

                current_message = ParsedMessage(
                    type=MessageType.TOOL_OUTPUT.value,
                    content=output_text,
                    collapsed=True
                )
                current_content = [output_text]
            continue

        # Check for task completion
        if stripped.startswith(MARKERS['task_complete']):
            if current_message and current_content:
                current_message.content = '\n'.join(current_content).strip()
                if current_message.content:
                    messages.append(current_message)

            task_text = stripped[len(MARKERS['task_complete']):].strip()
            messages.append(ParsedMessage(
                type=MessageType.TASK.value,
                content=task_text,
                collapsed=True
            ))
            current_message = None
            current_content = []
            continue

        # Check for error marker
        if stripped.startswith(MARKERS['error']):
            if current_message and current_content:
                current_message.content = '\n'.join(current_content).strip()
                if current_message.content:
                    messages.append(current_message)

            error_text = stripped[len(MARKERS['error']):].strip()
            messages.append(ParsedMessage(
                type=MessageType.ERROR.value,
                content=error_text
            ))
            current_message = None
            current_content = []
            continue

        # Plain text - assistant response or summary continuation
        if current_message and current_message.type == MessageType.SUMMARY.value:
            # Continue summary message (multi-line summaries)
            current_content.append(stripped)
        elif current_message and current_message.type == MessageType.TOOL.value:
            # End of tool, start assistant response
            current_message.content = '\n'.join(current_content).strip()
            if current_message.content:
                messages.append(current_message)

            current_message = ParsedMessage(
                type=MessageType.ASSISTANT.value,
                content=''
            )
            current_content = [stripped]
        elif current_message and current_message.type == MessageType.ASSISTANT.value:
            # Continue assistant response
            current_content.append(stripped)
        elif current_message and current_message.type == MessageType.TOOL_OUTPUT.value:
            # End of tool output, start assistant response
            current_message.content = '\n'.join(current_content).strip()
            if current_message.content:
                messages.append(current_message)

            current_message = ParsedMessage(
                type=MessageType.ASSISTANT.value,
                content=''
            )
            current_content = [stripped]
        else:
            # Start new assistant message
            if current_message and current_content:
                current_message.content = '\n'.join(current_content).strip()
                if current_message.content:
                    messages.append(current_message)

            current_message = ParsedMessage(
                type=MessageType.ASSISTANT.value,
                content=''
            )
            current_content = [stripped]

    # Don't forget the last message
    if current_message and current_content:
        current_message.content = '\n'.join(current_content).strip()
        if current_message.content:
            messages.append(current_message)

    # Merge consecutive assistant messages
    merged_messages = []
    for msg in messages:
        if (merged_messages and
            msg.type == MessageType.ASSISTANT.value and
            merged_messages[-1].type == MessageType.ASSISTANT.value):
            # Merge with previous
            merged_messages[-1].content += '\n\n' + msg.content
        else:
            merged_messages.append(msg)

    return merged_messages, state


def get_chat_buffer(session: str, lines: int = 500) -> Dict:
    """
    Main API function: capture and parse terminal buffer.

    Args:
        session: tmux session name
        lines: Number of lines to capture

    Returns:
        Dict with 'messages', 'state', 'error', 'raw_has_prompt', 'mode', 'suggestion' fields
    """
    # Capture with ANSI codes for mode/suggestion detection
    raw_buffer_ansi = capture_tmux_buffer(session, lines, include_ansi=True)

    if raw_buffer_ansi is None:
        return {
            'messages': [],
            'state': TerminalState.IDLE.value,
            'error': f'Failed to capture buffer from session: {session}',
            'raw_has_prompt': False,
            'mode': None,
            'suggestion': None
        }

    # Extract mode and suggestion from ANSI buffer
    mode, suggestion = extract_mode_and_suggestion(raw_buffer_ansi)

    # Use stripped buffer for message parsing
    raw_buffer = strip_ansi(raw_buffer_ansi)

    messages, state = parse_buffer(raw_buffer)

    # Check if Claude prompt marker is visible in buffer
    has_prompt = MARKERS['prompt'] in raw_buffer

    return {
        'messages': [m.to_dict() for m in messages],
        'state': state.value,
        'error': None,
        'raw_has_prompt': has_prompt,
        'mode': mode,
        'suggestion': suggestion
    }


def get_terminal_state(session: str) -> Dict:
    """
    Lightweight state check - only captures recent lines.

    Args:
        session: tmux session name

    Returns:
        Dict with 'state' and 'error' fields
    """
    raw_buffer = capture_tmux_buffer(session, lines=20)

    if raw_buffer is None:
        return {
            'state': TerminalState.IDLE.value,
            'error': f'Failed to capture buffer from session: {session}'
        }

    clean_buffer = strip_ansi(raw_buffer)
    lines = clean_buffer.split('\n')
    state = detect_state(lines)

    return {
        'state': state.value,
        'error': None
    }
