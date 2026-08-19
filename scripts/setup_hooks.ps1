# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

$ErrorActionPreference = 'Stop'

$HookFile = '.git/hooks/pre-push'

# Git on Windows runs hooks via Git Bash / sh.
$HookBody = @'
#!/bin/sh
# Pre-push: sweep recent Antigravity / Gemini / OpenCode prompts, then submit.
if [ -f "scripts/_pyrun.cmd" ]; then
    scripts/_pyrun.cmd scripts/log_antigravity.py --auto 2>/dev/null || true
    scripts/_pyrun.cmd scripts/log_opencode.py --auto 2>/dev/null || true
    scripts/_pyrun.cmd scripts/submit_log.py 2>/dev/null || true
else
    sh scripts/_pyrun.sh scripts/log_antigravity.py --auto 2>/dev/null || true
    sh scripts/_pyrun.sh scripts/log_opencode.py --auto 2>/dev/null || true
    sh scripts/_pyrun.sh scripts/submit_log.py 2>/dev/null || true
fi
exit 0
'@

Set-Content -Path $HookFile -Value $HookBody -Encoding UTF8 -NoNewline
Write-Host "[ai-log] Git pre-push hook installed."

if (-not (Test-Path .ai-log)) { New-Item -ItemType Directory -Path .ai-log | Out-Null }
if (-not (Test-Path .ai-log/.gitkeep)) { New-Item -ItemType File -Path .ai-log/.gitkeep | Out-Null }

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
