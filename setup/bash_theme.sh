# ============================================
# Midnight Command Theme - Indiana Jones aesthetic
# Matches Boomshakalaka dashboard colors
# ============================================
# Add to ~/.bashrc: source /path/to/bash_theme.sh

# Custom prompt: orange user@host, gold path, orange $
# Colors: 208=orange (#ff8700), 178=gold (#d7af00), 166=dark orange
PS1='\[\e[38;5;208m\]\u@\h\[\e[0m\]:\[\e[38;5;178m\]\w\[\e[38;5;208m\]\$\[\e[0m\] '

# Add conda env prefix if active (preserve conda display)
if [ -n "$CONDA_DEFAULT_ENV" ]; then
    PS1='(\[\e[38;5;178m\]$CONDA_DEFAULT_ENV\[\e[0m\]) '$PS1
fi

# LS_COLORS: Indiana Jones gold/orange theme
# di=directories, ex=executables, ln=symlinks, fi=files
# 178=gold, 208=orange, 166=dark orange, 136=dark gold, 223=tan
export LS_COLORS='di=38;5;178:ln=38;5;223:so=38;5;208:pi=38;5;136:ex=38;5;208:bd=38;5;166:cd=38;5;166:su=38;5;208:sg=38;5;208:tw=38;5;178:ow=38;5;178:*.tar=38;5;136:*.tgz=38;5;136:*.zip=38;5;136:*.gz=38;5;136:*.bz2=38;5;136:*.xz=38;5;136:*.jpg=38;5;223:*.jpeg=38;5;223:*.png=38;5;223:*.gif=38;5;223:*.pdf=38;5;223:*.md=38;5;250:*.txt=38;5;250:*.py=38;5;208:*.js=38;5;178:*.ts=38;5;178:*.json=38;5;136:*.yaml=38;5;136:*.yml=38;5;136:*.sh=38;5;208:*.conf=38;5;250'
