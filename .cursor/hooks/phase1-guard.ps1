$ErrorActionPreference = 'Stop'

function Deny([string]$reason) {
  [Console]::Error.WriteLine("PHASE1_BLOCKED: $reason")
  exit 1
}

$sandboxValue = $env:TIER1_GUARD_SANDBOX_ROOT
if ([string]::IsNullOrWhiteSpace($sandboxValue)) { Deny 'active sandbox is not configured' }
$sandbox = [IO.Path]::GetFullPath($sandboxValue)
if (-not (Test-Path -LiteralPath $sandbox -PathType Container)) { Deny 'active sandbox does not exist' }

$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { Deny 'hook input is missing' }
try { $event = $raw | ConvertFrom-Json } catch { Deny 'hook input is invalid JSON' }

$hookName = [string]$event.hook
if ($hookName -eq 'beforeMCPExecution') {
  $server = [string]($event.server ?? $event.serverName ?? $event.name)
  if ($server -ne 'tier1' -and $server -ne 'rayclaude-wiki') { Deny 'only the Tier-1 MCP server is allowed' }
  exit 0
}

if ($hookName -eq 'beforeShellExecution') {
  $command = [string]$event.command
  if ($command -match '(?i)(^|\s)(git\s+(commit|push)|rm\s+-rf|python\s+-c|node\s+-e)(\s|$)|>>?|\|\s*(sh|bash)') {
    Deny 'unsafe shell command is blocked'
  }
  $cwd = [string]$event.cwd
  if ([string]::IsNullOrWhiteSpace($cwd) -or -not ([IO.Path]::GetFullPath($cwd).StartsWith($sandbox, [StringComparison]::OrdinalIgnoreCase))) {
    Deny 'shell cwd is outside the active sandbox'
  }
  exit 0
}

$path = [string]($event.path ?? $event.filePath ?? $event.target)
if ([string]::IsNullOrWhiteSpace($path)) { Deny 'write target is missing' }
$candidate = if ([IO.Path]::IsPathRooted($path)) { [IO.Path]::GetFullPath($path) } else { [IO.Path]::GetFullPath((Join-Path $sandbox $path)) }
if (-not $candidate.StartsWith($sandbox, [StringComparison]::OrdinalIgnoreCase)) { Deny 'write target escapes the active sandbox' }
if ($candidate -match '(?i)(\\|/)(\.git|\.cursor)(\\|/)|(^|[\\/])\.env($|[\\/])') { Deny 'protected path is blocked' }
exit 0
