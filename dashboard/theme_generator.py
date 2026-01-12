"""
Theme Generator Module

Generates dashboard color themes from natural language prompts using Claude API.
"""

import os
import json
import re
from pathlib import Path

# Try to import anthropic, handle if not installed
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Load API key from various possible locations
def get_api_key():
    """Find ANTHROPIC_API_KEY from environment or .env files."""
    # Check environment first
    if os.getenv('ANTHROPIC_API_KEY'):
        return os.getenv('ANTHROPIC_API_KEY')

    # Check common .env file locations
    env_paths = [
        Path('/home/pds/boomshakalaka/.env'),
        Path('/home/pds/mcp_servers/mcp_frontend/.env'),
        Path('/home/pds/millcityai/Tabitha/.env'),
        Path.home() / '.env',
    ]

    for env_path in env_paths:
        if env_path.exists():
            try:
                with open(env_path) as f:
                    for line in f:
                        if line.startswith('ANTHROPIC_API_KEY='):
                            return line.strip().split('=', 1)[1]
            except Exception:
                continue

    return None


THEME_PROMPT = """Generate a color palette for a dark-mode dashboard theme based on this description:

"{user_prompt}"

Return a JSON object with these exact keys and hex color values:
{{
  "name": "Theme Name (2-3 words)",
  "bg_primary": "#hex",
  "bg_secondary": "#hex",
  "bg_tertiary": "#hex",
  "bg_card": "#hex",
  "bg_hover": "#hex",
  "bg_input": "#hex",
  "border_color": "#hex",
  "border_light": "#hex",
  "text_primary": "#hex",
  "text_secondary": "#hex",
  "text_muted": "#hex",
  "accent": "#hex",
  "accent_hover": "#hex",
  "accent_muted": "#hex"
}}

Color guidelines:
- bg_primary: Darkest background (main page)
- bg_secondary: Slightly lighter (sidebar, header)
- bg_tertiary: Elevated surfaces (cards hover, inputs)
- bg_card: Card backgrounds (between primary and tertiary)
- bg_hover: Hover state backgrounds
- bg_input: Input field backgrounds (usually darkest)
- border_color: Primary borders (subtle)
- border_light: Lighter borders for emphasis
- text_primary: Main text (high contrast, usually white/near-white)
- text_secondary: Secondary text (slightly muted)
- text_muted: Disabled/hint text (low contrast)
- accent: Primary accent color (buttons, links, highlights)
- accent_hover: Lighter accent for hover states
- accent_muted: Darker accent for subtle elements

Requirements:
- Ensure WCAG AA contrast between text and backgrounds
- Keep all backgrounds dark (luminance < 30%)
- Make accent colors vibrant and saturated
- Return ONLY valid JSON, no explanation or markdown"""


def generate_theme_from_prompt(prompt: str) -> dict:
    """
    Generate a theme color palette from a natural language prompt.

    Args:
        prompt: Natural language description of desired theme

    Returns:
        Dictionary with theme colors and metadata
    """
    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not found in environment or .env files")

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": THEME_PROMPT.format(user_prompt=prompt)
            }
        ]
    )

    # Extract JSON from response
    response_text = message.content[0].text.strip()

    # Try to parse JSON directly
    try:
        colors = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            colors = json.loads(json_match.group(1))
        else:
            # Try to find JSON object in text
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                colors = json.loads(json_match.group(0))
            else:
                raise ValueError(f"Could not parse theme JSON from response: {response_text[:200]}")

    return colors


def colors_to_css_variables(colors: dict) -> dict:
    """
    Convert color dictionary to CSS variable format.

    Args:
        colors: Dictionary with color values

    Returns:
        Dictionary with CSS variable names as keys
    """
    # Map from API response keys to CSS variable names
    mapping = {
        'bg_primary': '--bg-primary',
        'bg_secondary': '--bg-secondary',
        'bg_tertiary': '--bg-tertiary',
        'bg_card': '--bg-card',
        'bg_hover': '--bg-hover',
        'bg_input': '--bg-input',
        'border_color': '--border-color',
        'border_light': '--border-light',
        'text_primary': '--text-primary',
        'text_secondary': '--text-secondary',
        'text_muted': '--text-muted',
        'accent': '--accent',
        'accent_hover': '--accent-hover',
        'accent_muted': '--accent-muted',
    }

    css_vars = {}
    for key, css_name in mapping.items():
        if key in colors:
            css_vars[css_name] = colors[key]

    # Generate derived variables
    if '--accent' in css_vars:
        accent = css_vars['--accent']
        # Create accent-bg with transparency
        css_vars['--accent-bg'] = f"rgba({hex_to_rgb(accent)}, 0.1)"
        css_vars['--accent-glow'] = f"rgba({hex_to_rgb(accent)}, 0.4)"
        # Create gradient
        accent_muted = css_vars.get('--accent-muted', accent)
        css_vars['--gradient-accent'] = f"linear-gradient(135deg, {accent} 0%, {accent_muted} 100%)"

    # Border focus should match accent
    if '--accent' in css_vars:
        css_vars['--border-focus'] = css_vars['--accent']

    return css_vars


def colors_to_ttyd_theme(colors: dict) -> dict:
    """
    Convert color dictionary to ttyd theme JSON format.

    Args:
        colors: Dictionary with color values

    Returns:
        Dictionary for ttyd -t theme option
    """
    accent = colors.get('accent', '#f0cb09')

    return {
        'background': colors.get('bg_primary', '#122637'),
        'foreground': colors.get('text_primary', '#ffffff'),
        'cursor': accent,
        'cursorAccent': colors.get('bg_primary', '#122637'),
        'selectionBackground': f"rgba({hex_to_rgb(accent)}, 0.3)"
    }


def hex_to_rgb(hex_color: str) -> str:
    """Convert hex color to RGB values string."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"{r}, {g}, {b}"


def generate_ttyd_service_command(ttyd_theme: dict) -> str:
    """
    Generate the command to update ttyd service with new theme.

    Args:
        ttyd_theme: Dictionary with ttyd theme values

    Returns:
        Shell command string
    """
    theme_json = json.dumps(ttyd_theme)

    service_content = f'''[Unit]
Description=ttyd - Terminal in browser
After=network.target

[Service]
Type=simple
User=pds
WorkingDirectory=/home/pds
Environment="HOME=/home/pds"
Environment="TERM=xterm-256color"
# Theme generated by dashboard theme customizer
ExecStart=/usr/local/bin/ttyd -p 7681 -W -t 'theme={theme_json}' bash --login
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
'''

    # Return command to update and restart
    return f'''# Update ttyd service with new theme
cat > /tmp/ttyd.service << 'SERVICEEOF'
{service_content}SERVICEEOF

sudo cp /tmp/ttyd.service /etc/systemd/system/ttyd.service
sudo systemctl daemon-reload
sudo systemctl restart ttyd'''


def create_full_theme(prompt: str) -> dict:
    """
    Generate a complete theme package from a prompt.

    Args:
        prompt: Natural language description

    Returns:
        Dictionary with name, css, ttyd, and command
    """
    # Generate colors from Claude
    colors = generate_theme_from_prompt(prompt)

    # Convert to different formats
    css_vars = colors_to_css_variables(colors)
    ttyd_theme = colors_to_ttyd_theme(colors)
    ttyd_command = generate_ttyd_service_command(ttyd_theme)

    return {
        'name': colors.get('name', 'Custom Theme'),
        'prompt': prompt,
        'css': css_vars,
        'ttyd': ttyd_theme,
        'ttyd_command': ttyd_command
    }


# Default theme (current teal/gold)
DEFAULT_THEME = {
    'name': 'Teal Gold',
    'prompt': 'Dark teal background with gold accents',
    'css': {
        '--bg-primary': '#122637',
        '--bg-secondary': '#0a1820',
        '--bg-tertiary': '#1e3a4c',
        '--bg-card': '#0f1d2a',
        '--bg-hover': '#1a3040',
        '--bg-input': '#0a1520',
        '--border-color': '#1e3a4c',
        '--border-light': '#2a4a5c',
        '--border-focus': '#f0cb09',
        '--text-primary': '#ffffff',
        '--text-secondary': '#b8d4e8',
        '--text-muted': '#7a9bb3',
        '--accent': '#f0cb09',
        '--accent-hover': '#f5d63d',
        '--accent-muted': '#d4b308',
        '--accent-bg': 'rgba(240, 203, 9, 0.1)',
        '--accent-glow': 'rgba(240, 203, 9, 0.4)',
        '--gradient-accent': 'linear-gradient(135deg, #f0cb09 0%, #d4b308 100%)'
    },
    'ttyd': {
        'background': '#122637',
        'foreground': '#ffffff',
        'cursor': '#f0cb09',
        'cursorAccent': '#122637',
        'selectionBackground': 'rgba(240, 203, 9, 0.3)'
    }
}
