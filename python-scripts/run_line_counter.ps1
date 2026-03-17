param(
  [string]$Url,
  [string]$Video,
  [switch]$Post,
  [switch]$Display,
  [double]$LineFraction = 0.45,
  [int]$MinArea = 500,
  [int]$MatchDistance = 60,
  [string]$Backend = "http://localhost:3001/api/entries"
)

if ($Url) { $env:RTSP_URL = $Url }

$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (!(Test-Path $pythonExe)) {
  Write-Error "Missing local virtual environment at $pythonExe"
  Write-Host "Create it with: python -m venv .venv"
  exit 1
}

$argsList = @()
if ($Video) { $argsList += "--video"; $argsList += "`"$Video`"" }
if ($Post) { $argsList += "--post"; $argsList += "--backend"; $argsList += "`"$Backend`"" }
if ($Display) { $argsList += "--display" }
$argsList += "--line-fraction"; $argsList += $LineFraction
$argsList += "--min-area"; $argsList += $MinArea
$argsList += "--match-distance"; $argsList += $MatchDistance

$cmd = '"' + $pythonExe + '" line_counter.py ' + ($argsList -join ' ')
Write-Host "Running: $cmd"
pushd $PSScriptRoot
Invoke-Expression $cmd
popd
