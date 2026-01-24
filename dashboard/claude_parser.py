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
    'tool': '●',             # Tool invocation
    'tool_output': '⎿',      # Tool output / continuation
    'continuation': '…',     # Continuation marker
    'task_complete': '✔',    # Task completion
    'task_pending': '☐',     # Pending task
    'error': '✘',            # Error marker
}


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes and control characters from text."""
    text = ANSI_ESCAPE.sub('', text)
    text = CONTROL_CHARS.sub('', text)
    return text


def capture_tmux_buffer(session: str, lines: int = 500) -> Optional[str]:
    """
    Capture terminal buffer from tmux session.

    Args:
        session: tmux session name (e.g., 'dashboard-top')
        lines: Number of lines to capture (default 500)

    Returns:
        Raw terminal buffer content or None on error
    """
    try:
        result = subprocess.run(
            ['tmux', 'capture-pane', '-t', session, '-p', '-S', f'-{lines}'],
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
        # Send the text followed by Enter
        result = subprocess.run(
            ['tmux', 'send-keys', '-t', session, text, 'Enter'],
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

        # Check for tool invocation
        if stripped.startswith(MARKERS['tool']):
            # Save previous message
            if current_message and current_content:
                current_message.content = '\n'.join(current_content).strip()
                if current_message.content:
                    messages.append(current_message)

            # Parse tool name and args
            tool_text = stripped[len(MARKERS['tool']):].strip()
            tool_name = None

            # Try to extract tool name (e.g., "Read(file.txt)")
            match = re.match(r'^(\w+)\s*(?:\(|$)', tool_text)
            if match:
                tool_name = match.group(1)

            current_message = ParsedMessage(
                type=MessageType.TOOL.value,
                content=tool_text,
                tool_name=tool_name,
                collapsed=True
            )
            current_content = [tool_text]
            continue

        # Check for tool output
        if stripped.startswith(MARKERS['tool_output']) or stripped.startswith(MARKERS['continuation']):
            output_text = stripped[1:].strip() if stripped else ''

            if current_message and current_message.type == MessageType.TOOL.value:
                # Append to current tool
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

        # Plain text - assistant response
        if current_message and current_message.type == MessageType.TOOL.value:
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
        Dict with 'messages', 'state', and 'error' fields
    """
    raw_buffer = capture_tmux_buffer(session, lines)

    if raw_buffer is None:
        return {
            'messages': [],
            'state': TerminalState.IDLE.value,
            'error': f'Failed to capture buffer from session: {session}'
        }

    messages, state = parse_buffer(raw_buffer)

    return {
        'messages': [m.to_dict() for m in messages],
        'state': state.value,
        'error': None
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
