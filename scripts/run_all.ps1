param(
    [string]$UnityExecutablePath = "",
    [string]$BackendPython = "python",
    [switch]$ShutdownBackendOnExit
)

$ErrorActionPreference = "Stop"

$commonPath = Join-Path $PSScriptRoot "assistant_common.ps1"
. $commonPath

$root = Split-Path -Parent $PSScriptRoot
$healthUrl = "http://127.0.0.1:8096/v1/health"
$backendPort = 8096
$exitCode = 1
$resolvedBackendPython = $null
$backendStdoutLog = $null
$backendStderrLog = $null

function Test-PortReady {
    param([string]$Url)
    try {
        Invoke-RestMethod -Uri $Url -TimeoutSec 5 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Wait-PortReady {
    param(
        [string]$Url,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortReady -Url $Url) {
            return $true
        }

        if ($null -ne $Process) {
            try {
                if ($Process.HasExited) {
                    throw ("Backend process exited before health became ready. Exit code: " + $Process.ExitCode)
                }
            }
            catch {
                throw
            }
        }

        Start-Sleep -Milliseconds 500
    }

    return $false
}

$backendProcess = $null
try {
    $backend = Resolve-BackendDirectory -Root $root
    $clientExecutable = Resolve-ClientExecutable -Root $root -ExplicitPath $UnityExecutablePath

    Write-AssistantInfo ("Resolved backend path: " + $backend)
    $exitCode = 20
    Invoke-AssistantStep -Name "Resolve backend Python runtime" -Action {
        $script:resolvedBackendPython = Assert-CommandAvailable -Command $BackendPython -Label "Backend Python command"
        Write-AssistantInfo ("Using Python at: " + $script:resolvedBackendPython)
    }
    $exitCode = 21
    Invoke-AssistantStep -Name "Verify backend Python dependencies" -Action {
        Assert-BackendPythonReady -PythonCommand $resolvedBackendPython
    }
    $exitCode = 22
    Invoke-AssistantStep -Name "Run runtime preflight diagnostics" -Action {
        $diagnostics = Get-RuntimeDiagnostics -BackendDirectory $backend -PythonCommand $resolvedBackendPython
        Write-RuntimeDiagnostics -Diagnostics $diagnostics
        Assert-RuntimeDiagnosticsHealthy -Diagnostics $diagnostics
    }

    $exitCode = 23
    Invoke-AssistantStep -Name ("Verify backend port " + $backendPort + " is available") -Action {
        $owningProcessId = Get-ListeningTcpProcessId -Port $backendPort
        if ($null -ne $owningProcessId) {
            throw ("Port " + $backendPort + " is already in use by " + (Get-ProcessSummary -ProcessId $owningProcessId) + ". Stop that process or change the backend port before running startup.")
        }
    }

    $backendStdoutLog = [System.IO.Path]::GetTempFileName()
    $backendStderrLog = [System.IO.Path]::GetTempFileName()
    $exitCode = 24
    Invoke-AssistantStep -Name "Start local backend process" -Action {
        $script:backendProcess = Start-Process -FilePath $resolvedBackendPython -PassThru -WorkingDirectory $backend -ArgumentList @("run_local.py") -RedirectStandardOutput $backendStdoutLog -RedirectStandardError $backendStderrLog
        Write-AssistantInfo ("Backend process PID: " + $script:backendProcess.Id)
        Write-AssistantInfo ("Backend stdout log: " + $backendStdoutLog)
        Write-AssistantInfo ("Backend stderr log: " + $backendStderrLog)
    }

    $exitCode = 25
    Invoke-AssistantStep -Name ("Wait for backend health at " + $healthUrl) -Action {
        if (-not (Wait-PortReady -Url $healthUrl -Process $backendProcess)) {
            throw ("Backend health endpoint did not become ready yet. Check logs: " + $backendStdoutLog + " and " + $backendStderrLog)
        }
    }

    $exitCode = 26
    $health = Invoke-RestMethod -Uri $healthUrl
    Write-AssistantInfo ("Backend health: " + $health.status)
    if ($null -ne $health.runtimes -and $null -ne $health.runtimes.llm) {
        $provider = if ([string]::IsNullOrWhiteSpace($health.runtimes.llm.provider)) { "llm" } else { $health.runtimes.llm.provider }
        $model = if ([string]::IsNullOrWhiteSpace($health.runtimes.llm.model)) { "n/a" } else { $health.runtimes.llm.model }
        Write-AssistantInfo ("LLM provider: " + $provider + " | model: " + $model + " | ready: " + $health.runtimes.llm.available)
    }
    if ($health.status -eq "error") {
        throw "Backend health reported error. Resolve the health diagnostics before continuing."
    }
    if ($health.status -eq "partial") {
        Write-AssistantWarning "Backend started in partial mode. Some optional runtimes are degraded."
        foreach ($action in @($health.recovery_actions)) {
            Write-AssistantWarning $action
        }
    }

    if ($clientExecutable) {
        $exitCode = 27
        Invoke-AssistantStep -Name "Start Unity client build" -Action {
            Write-AssistantInfo ("Resolved client path: " + $clientExecutable)
            Start-Process -FilePath $clientExecutable | Out-Null
        }
    }
    else {
        Write-AssistantInfo "No packaged client executable found. Open the Unity project from 'unity-client/' or pass -UnityExecutablePath."
    }

    if ($ShutdownBackendOnExit) {
        $exitCode = 28
        Invoke-AssistantStep -Name "Stop backend process after startup validation" -Action {
            Stop-ProcessTreeSafe -Process $backendProcess
            $script:backendProcess = $null
        }
    }
    elseif ($null -ne $backendProcess) {
        Write-AssistantInfo ("Backend is still running as " + (Get-ProcessSummary -ProcessId $backendProcess.Id) + ". Rerun with -ShutdownBackendOnExit if you only want setup validation without leaving the backend running.")
    }

    Write-AssistantSuccess "Startup flow completed."
    exit 0
}
catch {
    Stop-ProcessTreeSafe -Process $backendProcess
    if (-not [string]::IsNullOrWhiteSpace($backendStdoutLog)) {
        $stdoutTail = Read-AssistantLogTail -Path $backendStdoutLog -LineCount 10
        foreach ($line in $stdoutTail) {
            Write-AssistantInfo ("backend stdout> " + $line)
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($backendStderrLog)) {
        $stderrTail = Read-AssistantLogTail -Path $backendStderrLog -LineCount 10
        foreach ($line in $stderrTail) {
            Write-AssistantError ("backend stderr> " + $line)
        }
    }
    Write-AssistantError $_.Exception.Message
    exit $exitCode
}
