$ErrorActionPreference = 'Stop'

function Deny([string]$reason) {
  @{ permission = 'deny'; reason = $reason } | ConvertTo-Json -Compress
  exit 2
}

function Allow() {
  @{ permission = 'allow' } | ConvertTo-Json -Compress
  exit 0
}

$sandboxValue = $env:TIER1_GUARD_SANDBOX_ROOT
if ([string]::IsNullOrWhiteSpace($sandboxValue)) { Deny 'active sandbox is not configured' }
$sandbox = [IO.Path]::GetFullPath($sandboxValue)
if (-not (Test-Path -LiteralPath $sandbox -PathType Container)) { Deny 'active sandbox does not exist' }
$sandboxPrefix = $sandbox.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar

function IsInsideSandbox([string]$candidate) {
  $full = [IO.Path]::GetFullPath($candidate)
  return $full.Equals($sandbox, [StringComparison]::OrdinalIgnoreCase) -or $full.StartsWith($sandboxPrefix, [StringComparison]::OrdinalIgnoreCase)
}

$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { $raw = ($input | Out-String).Trim() }
if ([string]::IsNullOrWhiteSpace($raw)) { Deny 'hook input is missing' }
try { $event = $raw | ConvertFrom-Json } catch { Deny 'hook input is invalid JSON' }

$hookName = [string]$event.hook_event_name
if ($hookName -eq 'beforeMCPExecution') {
  $server = [string]$event.mcp_server_name
  if ($server -ne 'tier1' -and $server -ne 'rayclaude-wiki') { Deny 'only the Tier-1 MCP server is allowed' }
  Allow
}

if ($hookName -eq 'beforeShellExecution') {
  $command = [string]$event.command
  if ($command -match '(?i)(^|\s)(git\s+(commit|push)|rm\s+-rf|python\s+-c|node\s+-e)(\s|$)|>>?|\|\s*(sh|bash)') {
    Deny 'unsafe shell command is blocked'
  }
  $cwd = [string]$event.cwd
  if ([string]::IsNullOrWhiteSpace($cwd) -or -not (IsInsideSandbox $cwd)) {
    Deny 'shell cwd is outside the active sandbox'
  }
  Allow
}

$path = [string]$event.file_path
if ([string]::IsNullOrWhiteSpace($path)) { $path = [string]$event.path }
if ($hookName -eq 'preToolUse' -and $null -ne $event.tool_input) {
  $path = [string]$event.tool_input.file_path
  if ([string]::IsNullOrWhiteSpace($path)) { $path = [string]$event.tool_input.path }
} elseif ([string]::IsNullOrWhiteSpace($path) -and $null -ne $event.tool_input) {
  try {
    $toolInput = $event.tool_input | ConvertFrom-Json
    $path = [string]$toolInput.file_path
    if ([string]::IsNullOrWhiteSpace($path)) { $path = [string]$toolInput.path }
  } catch { Deny 'tool input is invalid JSON' }
}
if ([string]::IsNullOrWhiteSpace($path)) { Deny 'write target is missing' }
$candidate = if ([IO.Path]::IsPathRooted($path)) { [IO.Path]::GetFullPath($path) } else { [IO.Path]::GetFullPath((Join-Path $sandbox $path)) }
if (-not (IsInsideSandbox $candidate)) { Deny 'write target escapes the active sandbox' }
if ($candidate -match '(?i)(\\|/)(\.git|\.cursor)(\\|/)|(^|[\\/])\.env($|[\\/])') { Deny 'protected path is blocked' }
Allow
