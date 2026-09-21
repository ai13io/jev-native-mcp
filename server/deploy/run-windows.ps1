param(
    [string]$HostAddress = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8765,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ServerDirectory = Split-Path -Parent $PSScriptRoot
$ServerScript = Join-Path $ServerDirectory "server.py"
$PythonExecutable = $Python
if (-not [IO.Path]::IsPathRooted($Python)) {
    $PythonCandidate = Join-Path (Get-Location).Path $Python
    if (Test-Path -LiteralPath $PythonCandidate -PathType Leaf) {
        $PythonExecutable = (Resolve-Path -LiteralPath $PythonCandidate).Path
    }
}
$SetTemporaryKey = $false
$SetTemporaryReceiptKey = $false
$PushedLocation = $false
$Bstr = [IntPtr]::Zero
$ReceiptBstr = [IntPtr]::Zero

try {
    if ([string]::IsNullOrWhiteSpace($env:TYPESAFE_API_KEY)) {
        $SecureKey = Read-Host "TypeSafe API key" -AsSecureString
        $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
        $env:TYPESAFE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
        $SetTemporaryKey = $true
    }
    if ([string]::IsNullOrWhiteSpace($env:JEV_RECEIPT_HMAC_KEY)) {
        $SecureReceiptKey = Read-Host "Receipt HMAC key (at least 32 UTF-8 bytes)" -AsSecureString
        $ReceiptBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureReceiptKey)
        $env:JEV_RECEIPT_HMAC_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ReceiptBstr)
        $SetTemporaryReceiptKey = $true
    }

    $env:JEV_MCP_HOST = $HostAddress
    $env:JEV_MCP_PORT = [string]$Port
    if ([string]::IsNullOrWhiteSpace($env:JEV_BUDGET_PATH)) {
        $env:JEV_BUDGET_PATH = Join-Path $ServerDirectory "runtime\usage.json"
    }
    if ([string]::IsNullOrWhiteSpace($env:JEV_RECEIPT_DIR)) {
        $env:JEV_RECEIPT_DIR = Join-Path $ServerDirectory "runtime\receipts-v2"
    }

    Push-Location $ServerDirectory
    $PushedLocation = $true
    & $PythonExecutable $ServerScript
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    if ($PushedLocation) {
        Pop-Location
    }
    if ($Bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
    if ($ReceiptBstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ReceiptBstr)
    }
    if ($SetTemporaryKey) {
        Remove-Item Env:TYPESAFE_API_KEY -ErrorAction SilentlyContinue
    }
    if ($SetTemporaryReceiptKey) {
        Remove-Item Env:JEV_RECEIPT_HMAC_KEY -ErrorAction SilentlyContinue
    }
}
