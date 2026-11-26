<#
.SYNOPSIS
  Coleta as pastas e programas que mais ocupam espaço em cada drive local do Windows.

.DESCRIPTION
  Por quê: o Zabbix Agent 2 não possui item nativo que gere um ranking das pastas
  e programas mais pesados por unidade (`C:`, `D:`, ...).
  Para quê: executado periodicamente via `UserParameter=custom.disk.top_usage`
  (intervalo sugerido de 30-60 min no template Zabbix), retornando JSON compacto
  consumido pelo Zabbix Dashboard no detalhamento da VM.
#>
param(
  [int]$TopCount = 10,
  [int]$MaxDepth = 2
)

$ErrorActionPreference = 'SilentlyContinue'

function Get-DirectoryBytes {
  param([string]$Path, [int]$Depth)
  if (-not (Test-Path -LiteralPath $Path)) { return 0 }
  try {
    # Evita seguir reparse points/junctions (ex.: "Documents and Settings") para não duplicar bytes.
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { return 0 }
  } catch {
    return 0
  }
  $sum = 0L
  try {
    Get-ChildItem -LiteralPath $Path -File -Force | ForEach-Object { $sum += $_.Length }
    if ($Depth -gt 0) {
      Get-ChildItem -LiteralPath $Path -Directory -Force | ForEach-Object {
        if (-not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
          $sum += Get-DirectoryBytes -Path $_.FullName -Depth ($Depth - 1)
        }
      }
    }
  } catch {}
  return $sum
}

$drives = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | Select-Object -ExpandProperty DeviceID
$uninstallKeys = @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$installedApps = Get-ItemProperty $uninstallKeys | Where-Object { $_.DisplayName }

$result = @{}
foreach ($drive in $drives) {
  $root = "$drive\"
  $dirs = @()
  Get-ChildItem -LiteralPath $root -Directory -Force | ForEach-Object {
    if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) { return }
    if ($_.Name -in @('$Recycle.Bin', 'System Volume Information')) { return }
    $size = Get-DirectoryBytes -Path $_.FullName -Depth $MaxDepth
    if ($size -gt 0) {
      $dirs += [PSCustomObject]@{ path = $_.FullName; bytes = [int64]$size }
    }
  }

  $apps = @()
  foreach ($app in $installedApps) {
    $loc = [string]$app.InstallLocation
    $bytes = $null
    if ($loc -and $loc.StartsWith($drive, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $loc)) {
      $bytes = Get-DirectoryBytes -Path $loc -Depth 2
    } elseif ($app.EstimatedSize -and $drive -eq 'C:' -and -not $loc) {
      $bytes = [int64]$app.EstimatedSize * 1024
    }
    if ($bytes -and $bytes -gt 0) {
      $apps += [PSCustomObject]@{
        name  = [string]$app.DisplayName
        path  = $loc
        bytes = [int64]$bytes
      }
    }
  }

  $result[$drive] = [PSCustomObject]@{
    top_dirs = @($dirs | Sort-Object bytes -Descending | Select-Object -First $TopCount)
    top_apps = @($apps | Sort-Object bytes -Descending | Select-Object -First $TopCount)
  }
}

$result | ConvertTo-Json -Depth 5 -Compress
