"""Unit Tests for Claude Parser - Summary Message Detection"""
import pytest
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dashboard.claude_parser import parse_buffer, MessageType, TOOL_INVOCATION_PATTERN


class TestToolInvocationPattern:
    """Test the regex pattern that distinguishes tool invocations from summaries"""

    def test_matches_bash_tool(self):
        """Bash(command) should match as tool invocation"""
        match = TOOL_INVOCATION_PATTERN.match('Bash(git push)')
        assert match is not None
        assert match.group(1) == 'Bash'

    def test_matches_read_tool(self):
        """Read(file.txt) should match as tool invocation"""
        match = TOOL_INVOCATION_PATTERN.match('Read(file.txt)')
        assert match is not None
        assert match.group(1) == 'Read'

    def test_matches_write_tool(self):
        """Write(file.txt) should match as tool invocation"""
        match = TOOL_INVOCATION_PATTERN.match('Write(path/to/file.py)')
        assert match is not None
        assert match.group(1) == 'Write'

    def test_matches_edit_tool(self):
        """Edit(file.txt) should match as tool invocation"""
        match = TOOL_INVOCATION_PATTERN.match('Edit(/home/user/file.js)')
        assert match is not None
        assert match.group(1) == 'Edit'

    def test_no_match_with_space_before_paren(self):
        """Tool with space before ( should NOT match (tool names have no space)"""
        assert TOOL_INVOCATION_PATTERN.match('Bash (git status)') is None

    def test_no_match_prose_done(self):
        """'Done. Committed' is prose, not a tool invocation"""
        assert TOOL_INVOCATION_PATTERN.match('Done. Committed') is None

    def test_no_match_prose_exclamation(self):
        """'Deployment successful!' is prose, not a tool invocation"""
        assert TOOL_INVOCATION_PATTERN.match('Deployment successful!') is None

    def test_no_match_prose_sentence(self):
        """Plain sentences should not match"""
        assert TOOL_INVOCATION_PATTERN.match('I have completed the task.') is None

    def test_no_match_starting_with_number(self):
        """Numbers don't match - tools must start with capital letter"""
        assert TOOL_INVOCATION_PATTERN.match('123(test)') is None

    def test_no_match_lowercase_start(self):
        """Lowercase start doesn't match - tools are PascalCase"""
        assert TOOL_INVOCATION_PATTERN.match('bash(git)') is None

    def test_no_match_empty_string(self):
        """Empty string should not match"""
        assert TOOL_INVOCATION_PATTERN.match('') is None


class TestParseSummaryMessages:
    """Test parsing of summary messages (bullet without tool invocation pattern)"""

    def test_simple_summary(self):
        """Simple summary message should be type SUMMARY"""
        buffer = "● Done. Committed and pushed."
        messages, _ = parse_buffer(buffer)
        assert len(messages) == 1
        assert messages[0].type == MessageType.SUMMARY.value
        assert messages[0].collapsed is False
        assert "Done. Committed and pushed." in messages[0].content

    def test_summary_not_collapsed(self):
        """Summary messages should not be collapsed by default"""
        buffer = "● Changes applied successfully."
        messages, _ = parse_buffer(buffer)
        assert messages[0].collapsed is False

    def test_summary_with_continuation(self):
        """Summary with continuation lines should capture all content"""
        buffer = """● Done. Committed and pushed.
⎿  Commit 24d7ebe: Add feature
⎿  - Change 1
⎿  - Change 2"""
        messages, _ = parse_buffer(buffer)
        assert len(messages) == 1
        assert messages[0].type == MessageType.SUMMARY.value
        assert "Commit 24d7ebe" in messages[0].content
        assert "Change 1" in messages[0].content

    def test_summary_with_plain_text_continuation(self):
        """Summary followed by plain text lines continues the summary"""
        buffer = """● Deployment complete!

URL: https://example.com
Status: Running"""
        messages, _ = parse_buffer(buffer)
        # Should have one summary message with all content
        assert any(m.type == MessageType.SUMMARY.value for m in messages)
        summary = next(m for m in messages if m.type == MessageType.SUMMARY.value)
        assert "Deployment complete!" in summary.content

    def test_summary_with_table(self):
        """Summary with ASCII table should capture table content"""
        buffer = """● Deployment successful!
⎿  ┌────────┬─────────┐
⎿  │ Status │ Details │
⎿  └────────┴─────────┘"""
        messages, _ = parse_buffer(buffer)
        assert messages[0].type == MessageType.SUMMARY.value
        assert "┌" in messages[0].content
        assert "Status" in messages[0].content

    def test_multiple_summaries(self):
        """Multiple consecutive summaries should be separate messages"""
        buffer = """● First task complete.
● Second task complete.
● All done!"""
        messages, _ = parse_buffer(buffer)
        assert len(messages) == 3
        assert all(m.type == MessageType.SUMMARY.value for m in messages)


class TestParseToolInvocations:
    """Test parsing of tool invocation messages"""

    def test_tool_invocation(self):
        """Tool invocation should be type TOOL"""
        buffer = "● Bash(git push)"
        messages, _ = parse_buffer(buffer)
        assert len(messages) == 1
        assert messages[0].type == MessageType.TOOL.value
        assert messages[0].tool_name == "Bash"
        assert messages[0].collapsed is True

    def test_tool_with_output(self):
        """Tool with output continuation should capture output"""
        buffer = """● Bash(git push)
⎿  To https://github.com/user/repo.git
⎿     abc1234..def5678  main -> main"""
        messages, _ = parse_buffer(buffer)
        assert len(messages) == 1
        assert messages[0].type == MessageType.TOOL.value
        assert "github.com" in messages[0].content

    def test_read_tool(self):
        """Read tool should be parsed correctly"""
        buffer = "● Read(src/main.py)"
        messages, _ = parse_buffer(buffer)
        assert messages[0].type == MessageType.TOOL.value
        assert messages[0].tool_name == "Read"

    def test_write_tool(self):
        """Write tool should be parsed correctly"""
        buffer = "● Write(output.txt)"
        messages, _ = parse_buffer(buffer)
        assert messages[0].type == MessageType.TOOL.value
        assert messages[0].tool_name == "Write"


class TestMixedContent:
    """Test parsing of mixed tool invocations and summaries"""

    def test_tool_then_summary(self):
        """Tool followed by summary should be two separate messages"""
        buffer = """● Bash(git push)
⎿  dev -> dev

● Done. Committed and pushed."""
        messages, _ = parse_buffer(buffer)
        assert len(messages) == 2
        assert messages[0].type == MessageType.TOOL.value
        assert messages[1].type == MessageType.SUMMARY.value

    def test_user_tool_summary(self):
        """User message, tool, then summary should all be parsed"""
        buffer = """❯ commit and push

● Bash(git add && git commit && git push)
⎿  [dev abc123] feat: add feature

● Done. Changes committed."""
        messages, _ = parse_buffer(buffer)
        assert len(messages) == 3
        assert messages[0].type == MessageType.USER.value
        assert messages[1].type == MessageType.TOOL.value
        assert messages[2].type == MessageType.SUMMARY.value

    def test_multiple_tools_then_summary(self):
        """Multiple tools followed by summary"""
        buffer = """● Read(file1.py)
⎿  content of file1

● Read(file2.py)
⎿  content of file2

● I've reviewed both files."""
        messages, _ = parse_buffer(buffer)
        tool_count = sum(1 for m in messages if m.type == MessageType.TOOL.value)
        summary_count = sum(1 for m in messages if m.type == MessageType.SUMMARY.value)
        assert tool_count == 2
        assert summary_count == 1

    def test_summary_between_tools(self):
        """Summary can appear between tool invocations"""
        buffer = """● Bash(npm install)
⎿  added 100 packages

● Dependencies installed successfully.

● Bash(npm test)
⎿  All tests passed"""
        messages, _ = parse_buffer(buffer)
        types = [m.type for m in messages]
        assert types.count(MessageType.TOOL.value) == 2
        assert types.count(MessageType.SUMMARY.value) == 1


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_buffer(self):
        """Empty buffer should return empty list"""
        messages, _ = parse_buffer("")
        assert messages == []

    def test_only_whitespace(self):
        """Whitespace-only buffer should return empty list"""
        messages, _ = parse_buffer("   \n\n   \t\t  ")
        assert messages == []

    def test_tool_no_args(self):
        """Tool with empty parentheses"""
        buffer = "● Task()"
        messages, _ = parse_buffer(buffer)
        assert messages[0].type == MessageType.TOOL.value
        assert messages[0].tool_name == "Task"

    def test_summary_with_parentheses_in_text(self):
        """Summary containing parentheses (but not at start) should still be summary"""
        buffer = "● Done (all 5 files updated)."
        messages, _ = parse_buffer(buffer)
        assert messages[0].type == MessageType.SUMMARY.value

    def test_summary_starting_with_lowercase(self):
        """Lowercase start should be summary (tools are PascalCase)"""
        buffer = "● done with the task"
        messages, _ = parse_buffer(buffer)
        # 'done' doesn't match Word( pattern, so should be summary
        assert messages[0].type == MessageType.SUMMARY.value

    def test_user_prompt_alone(self):
        """User prompt without text after should not create message"""
        buffer = "❯"
        messages, _ = parse_buffer(buffer)
        assert messages == []

    def test_error_message(self):
        """Error messages should be parsed as ERROR type"""
        buffer = "✘ Command failed with exit code 1"
        messages, _ = parse_buffer(buffer)
        assert len(messages) == 1
        assert messages[0].type == MessageType.ERROR.value

    def test_task_complete_message(self):
        """Task complete messages should be parsed as TASK type"""
        buffer = "✔ Build completed"
        messages, _ = parse_buffer(buffer)
        assert len(messages) == 1
        assert messages[0].type == MessageType.TASK.value
