Set-StrictMode -Version Latest

function Write-AssistantInfo {
    param([string]$Message)

    Write-Host ("[assistant] " + $Message)
}

function Write-AssistantWarning {
    param([string]$Message)

    Write-Warning ("[assistant] " + $Message)
}

function Write-AssistantError {
    param([string]$Message)

    Write-Host ("[assistant][error] " + $Message)
}

function Write-AssistantSuccess {
    param([string]$Message)

    Write-Host ("[assistant][ok] " + $Message)
}

function Invoke-AssistantStep {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-AssistantInfo ($Name + "...")
    & $Action
    Write-AssistantSuccess ($Name + " complete.")
}

function Resolve-BackendDirectory {
    param([string]$Root)

    $candidates = @(
        (Join-Path $Root "local-backend"),
        (Join-Path $Root "backend"),
        (Join-Path $Root "backend\local-backend")
    )

    foreach ($candidate in $candidates) {
        if ((Test-Path (Join-Path $candidate "requirements.txt")) -and (Test-Path (Join-Path $candidate "run_local.py"))) {
            return $candidate
        }
    }

    throw "Backend folder not found. Checked: $($candidates -join ', ')"
}

function Assert-PathMatchesType {
    param(
        [string]$Path,
        [ValidateSet("Any", "File", "Directory")]
        [string]$ExpectedType = "Any",
        [string]$Description = "Path"
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw ($Description + " cannot be empty.")
    }

    if (-not (Test-Path $Path)) {
        throw ($Description + " does not exist: " + $Path)
    }

    $item = Get-Item $Path -ErrorAction Stop
    if ($ExpectedType -eq "File" -and $item.PSIsContainer) {
        throw ($Description + " must be a file, but got a directory: " + $Path)
    }

    if ($ExpectedType -eq "Directory" -and -not $item.PSIsContainer) {
        throw ($Description + " must be a directory, but got a file: " + $Path)
    }

    return $item
}

function Assert-SafeOutputDirectory {
    param(
        [string]$Root,
        [string]$OutputDir
    )

    if ([string]::IsNullOrWhiteSpace($OutputDir)) {
        throw "Output directory cannot be empty."
    }

    $resolvedRoot = (Resolve-Path $Root).Path.TrimEnd("\")
    $resolvedOutput = [System.IO.Path]::GetFullPath($OutputDir).TrimEnd("\")

    if ($resolvedOutput.Length -lt 4) {
        throw "Refusing to operate on an unsafe output directory: $resolvedOutput"
    }

    if ($resolvedOutput -eq $resolvedRoot) {
        throw "Refusing to use the repo root as a release output directory: $resolvedOutput"
    }

    $parent = Split-Path -Parent $resolvedOutput
    if ([string]::IsNullOrWhiteSpace($parent)) {
        throw "Refusing to use a drive root as a release output directory: $resolvedOutput"
    }
}

function Resolve-ClientExecutable {
    param(
        [string]$Root,
        [string]$ExplicitPath
    )

    if ($ExplicitPath) {
        $explicitItem = Assert-PathMatchesType -Path $ExplicitPath -ExpectedType File -Description "Unity executable"
        return $explicitItem.FullName
    }

    $clientDir = Join-Path $Root "client"
    if (-not (Test-Path $clientDir)) {
        return $null
    }

    $candidates = @(
        Get-ChildItem -Path $clientDir -Filter "*.exe" -File -Recurse |
            Where-Object { $_.Name -ne "UnityCrashHandler64.exe" } |
            Sort-Object FullName
    )

    if ($candidates.Count -eq 0) {
        return $null
    }

    if ($candidates.Count -gt 1) {
        Write-AssistantWarning ("Multiple client executables found. Starting the first one: " + $candidates[0].FullName)
    }

    return $candidates[0].FullName
}

function Read-AssistantConfig {
    param([string]$BackendDirectory)

    $config = @{}
    $envFile = Join-Path $BackendDirectory ".env"

    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            $trimmed = $line.Trim()
            if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
                continue
            }

            $parts = $trimmed -split "=", 2
            if ($parts.Count -eq 2) {
                $config[$parts[0].Trim()] = $parts[1].Trim()
            }
        }
    }

    foreach ($entry in Get-ChildItem Env:assistant_* -ErrorAction SilentlyContinue) {
        $config[$entry.Name] = $entry.Value
    }

    return $config
}

function Get-AssistantConfigValue {
    param(
        [hashtable]$Config,
        [string]$Key,
        [string]$Default = ""
    )

    if ($Config.ContainsKey($Key) -and -not [string]::IsNullOrWhiteSpace([string]$Config[$Key])) {
        $value = [string]$Config[$Key]
        $trimmedValue = $value.Trim()
        if ($trimmedValue.Length -ge 2) {
            $first = $trimmedValue.Substring(0, 1)
            $last = $trimmedValue.Substring($trimmedValue.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                return $trimmedValue.Substring(1, $trimmedValue.Length - 2)
            }
        }

        return $trimmedValue
    }

    return $Default
}

function Assert-CommandAvailable {
    param(
        [string]$Command,
        [string]$Label = "Command"
    )

    $resolved = Resolve-CommandPath -Value $Command
    if (-not $resolved) {
        throw ($Label + " was not found: " + $Command)
    }

    return $resolved
}

function Get-ConfigBooleanState {
    param(
        [hashtable]$Config,
        [string]$Key,
        [bool]$Default = $false
    )

    $rawValue = Get-AssistantConfigValue -Config $Config -Key $Key
    if ([string]::IsNullOrWhiteSpace($rawValue)) {
        return [PSCustomObject]@{
            Success = $true
            Value = $Default
            Raw = $null
        }
    }

    switch ($rawValue.Trim().ToLowerInvariant()) {
        "1" { return [PSCustomObject]@{ Success = $true; Value = $true; Raw = $rawValue } }
        "true" { return [PSCustomObject]@{ Success = $true; Value = $true; Raw = $rawValue } }
        "yes" { return [PSCustomObject]@{ Success = $true; Value = $true; Raw = $rawValue } }
        "on" { return [PSCustomObject]@{ Success = $true; Value = $true; Raw = $rawValue } }
        "0" { return [PSCustomObject]@{ Success = $true; Value = $false; Raw = $rawValue } }
        "false" { return [PSCustomObject]@{ Success = $true; Value = $false; Raw = $rawValue } }
        "no" { return [PSCustomObject]@{ Success = $true; Value = $false; Raw = $rawValue } }
        "off" { return [PSCustomObject]@{ Success = $true; Value = $false; Raw = $rawValue } }
        default {
            return [PSCustomObject]@{
                Success = $false
                Value = $Default
                Raw = $rawValue
            }
        }
    }
}

function Resolve-CommandPath {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    if (Test-Path $Value) {
        $item = Get-Item $Value -ErrorAction SilentlyContinue
        if ($null -eq $item -or $item.PSIsContainer) {
            return $null
        }

        return $item.FullName
    }

    return (Get-Command $Value -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
}

function Test-PythonModuleAvailable {
    param(
        [string]$PythonCommand,
        [string[]]$Modules
    )

    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    $scriptFile = [System.IO.Path]::GetTempFileName() + ".py"
    try {
        @'
import importlib.util
import json
import sys

modules = sys.argv[1:]
missing = [name for name in modules if importlib.util.find_spec(name) is None]
print(json.dumps({"missing": missing}))
sys.exit(1 if missing else 0)
'@ | Set-Content -Path $scriptFile -Encoding ASCII

        $argumentList = @($scriptFile) + $Modules
        $process = Start-Process -FilePath $PythonCommand -ArgumentList $argumentList -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        $output = @()
        if (Test-Path $stdoutFile) {
            $output += Get-Content $stdoutFile
        }
        if (Test-Path $stderrFile) {
            $stderr = Get-Content $stderrFile
            if ($stderr) {
                $output += $stderr
            }
        }

        $payload = $output | Select-Object -Last 1
        $parsed = $null
        try {
            $parsed = $payload | ConvertFrom-Json
        }
        catch {
        }

        $missing = @()
        if ($null -ne $parsed) {
            $missing = @($parsed.missing)
        }

        return [PSCustomObject]@{
            Success = ($process.ExitCode -eq 0)
            Missing = $missing
            Output = @($output)
        }
    }
    finally {
        Remove-Item $stdoutFile, $stderrFile, $scriptFile -Force -ErrorAction SilentlyContinue
    }
}

function Assert-BackendPythonReady {
    param(
        [string]$PythonCommand,
        [string[]]$Modules = @("fastapi", "uvicorn", "websockets", "pydantic_settings", "httpx")
    )

    $resolvedPython = Assert-CommandAvailable -Command $PythonCommand -Label "Backend Python command"
    $result = Test-PythonModuleAvailable -PythonCommand $resolvedPython -Modules $Modules
    if ($result.Success) {
        return
    }

    if ($result.Missing.Count -gt 0) {
        throw ("Missing Python modules: " + ($result.Missing -join ", ") + ". Run `python -m pip install -r requirements.txt` in local-backend.")
    }

    throw ("Python dependency preflight failed. Output: " + ($result.Output -join " "))
}

function Get-RuntimeDiagnostics {
    param(
        [string]$BackendDirectory,
        [string]$PythonCommand = "python"
    )

    $config = Read-AssistantConfig -BackendDirectory $BackendDirectory
    $warnings = New-Object System.Collections.Generic.List[string]
    $errors = New-Object System.Collections.Generic.List[string]

    $ttsProvider = (Get-AssistantConfigValue -Config $config -Key "assistant_tts_provider" -Default "piper").ToLowerInvariant()
    $sttProvider = (Get-AssistantConfigValue -Config $config -Key "assistant_stt_provider" -Default "faster_whisper").ToLowerInvariant()
    $llmProvider = (Get-AssistantConfigValue -Config $config -Key "assistant_llm_provider" -Default "hybrid").ToLowerInvariant()
    $ollamaEnabledState = Get-ConfigBooleanState -Config $config -Key "assistant_enable_ollama" -Default $false
    $groqApiKey = Get-AssistantConfigValue -Config $config -Key "assistant_groq_api_key"
    $geminiApiKey = Get-AssistantConfigValue -Config $config -Key "assistant_gemini_api_key"
    $resolvedPythonCommand = $null

    try {
        $resolvedPythonCommand = Assert-CommandAvailable -Command $PythonCommand -Label "Backend Python command"
    }
    catch {
        $errors.Add($_.Exception.Message)
    }

    if (-not $ollamaEnabledState.Success) {
        $warnings.Add("assistant_enable_ollama has an invalid boolean value: " + $ollamaEnabledState.Raw + ". Expected true/false.")
    }

    if ($ttsProvider -notin @("piper", "chattts")) {
        $errors.Add("assistant_tts_provider must be either 'piper' or 'chattts', but got: " + $ttsProvider)
    }

    if ($ttsProvider -eq "piper") {
        $piperCommand = Get-AssistantConfigValue -Config $config -Key "assistant_piper_command"
        $piperModelPath = Get-AssistantConfigValue -Config $config -Key "assistant_piper_model_path"
        if ([string]::IsNullOrWhiteSpace($piperCommand)) {
            $warnings.Add("TTS provider is piper but assistant_piper_command is not configured. The backend may start in partial mode without speech output.")
        }
        elseif (-not (Resolve-CommandPath $piperCommand)) {
            $errors.Add("assistant_piper_command is configured but not found as an executable file: $piperCommand")
        }
        if ([string]::IsNullOrWhiteSpace($piperModelPath)) {
            $warnings.Add("TTS provider is piper but assistant_piper_model_path is not configured. The backend may start in partial mode without speech output.")
        }
        else {
            try {
                Assert-PathMatchesType -Path $piperModelPath -ExpectedType File -Description "assistant_piper_model_path" | Out-Null
            }
            catch {
                $errors.Add($_.Exception.Message)
            }
        }
    }
    elseif ($ttsProvider -eq "chattts") {
        if ($null -ne $resolvedPythonCommand) {
            $chatTtsModules = Test-PythonModuleAvailable -PythonCommand $resolvedPythonCommand -Modules @("ChatTTS", "numpy")
            if (-not $chatTtsModules.Success) {
                $warnings.Add("TTS provider is chattts but required Python modules are missing: " + ($chatTtsModules.Missing -join ", "))
            }
        }
    }

    if ($sttProvider -notin @("faster_whisper", "whisper_cpp")) {
        $errors.Add("assistant_stt_provider must be either 'faster_whisper' or 'whisper_cpp', but got: " + $sttProvider)
    }

    if ($sttProvider -eq "whisper_cpp") {
        $whisperCommand = Get-AssistantConfigValue -Config $config -Key "assistant_whisper_command"
        $whisperModelPath = Get-AssistantConfigValue -Config $config -Key "assistant_whisper_model_path"
        if ([string]::IsNullOrWhiteSpace($whisperCommand)) {
            $warnings.Add("STT provider is whisper_cpp but assistant_whisper_command is not configured. The backend may start in partial mode without local speech-to-text.")
        }
        elseif (-not (Resolve-CommandPath $whisperCommand)) {
            $errors.Add("assistant_whisper_command is configured but not found as an executable file: $whisperCommand")
        }
        if ([string]::IsNullOrWhiteSpace($whisperModelPath)) {
            $warnings.Add("STT provider is whisper_cpp but assistant_whisper_model_path is not configured. The backend may start in partial mode without local speech-to-text.")
        }
        else {
            try {
                Assert-PathMatchesType -Path $whisperModelPath -ExpectedType File -Description "assistant_whisper_model_path" | Out-Null
            }
            catch {
                $errors.Add($_.Exception.Message)
            }
        }
    }
    elseif ($sttProvider -eq "faster_whisper") {
        $modelPath = Get-AssistantConfigValue -Config $config -Key "assistant_faster_whisper_model_path"
        if ($null -ne $resolvedPythonCommand) {
            $fasterWhisperModules = Test-PythonModuleAvailable -PythonCommand $resolvedPythonCommand -Modules @("faster_whisper")
            if (-not $fasterWhisperModules.Success) {
                $warnings.Add("STT provider is faster_whisper but required Python modules are missing: " + ($fasterWhisperModules.Missing -join ", "))
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($modelPath) -and -not (Test-Path $modelPath)) {
            $errors.Add("assistant_faster_whisper_model_path does not exist: $modelPath")
        }
    }

    $ollamaBaseUrl = Get-AssistantConfigValue -Config $config -Key "assistant_ollama_base_url" -Default "http://127.0.0.1:11434"
    $ollamaModel = Get-AssistantConfigValue -Config $config -Key "assistant_ollama_model" -Default "llama3.1:8b"
    $shouldProbeOllama = ($llmProvider -eq "ollama") -or $ollamaEnabledState.Value
    if ($shouldProbeOllama) {
        if ([string]::IsNullOrWhiteSpace($ollamaBaseUrl)) {
            $errors.Add("assistant_ollama_base_url cannot be empty when Ollama is enabled.")
        }
        else {
            try {
                $tagsUrl = $ollamaBaseUrl.TrimEnd("/") + "/api/tags"
                $tags = Invoke-RestMethod -Uri $tagsUrl -TimeoutSec 2
                if (-not [string]::IsNullOrWhiteSpace($ollamaModel)) {
                    $modelNames = @($tags.models | ForEach-Object { $_.name } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
                    if ($modelNames.Count -gt 0 -and $modelNames -notcontains $ollamaModel) {
                        $message = "Ollama responded at $ollamaBaseUrl but model '$ollamaModel' is not listed by /api/tags."
                        if ($llmProvider -eq "ollama") {
                            $errors.Add($message)
                        }
                        else {
                            $warnings.Add($message)
                        }
                    }
                }
            }
            catch {
                $message = "Ollama endpoint did not respond at $ollamaBaseUrl during preflight."
                if ($llmProvider -eq "ollama") {
                    $errors.Add($message)
                }
                else {
                    $warnings.Add($message)
                }
            }
        }
    }

    if ($llmProvider -eq "groq" -and [string]::IsNullOrWhiteSpace($groqApiKey)) {
        $warnings.Add("LLM provider is groq but assistant_groq_api_key is not configured. The backend will start in partial mode without API-backed replies.")
    }
    elseif ($llmProvider -eq "gemini" -and [string]::IsNullOrWhiteSpace($geminiApiKey)) {
        $warnings.Add("LLM provider is gemini but assistant_gemini_api_key is not configured. The backend will start in partial mode without API-backed replies.")
    }
    elseif ($llmProvider -eq "hybrid") {
        if ([string]::IsNullOrWhiteSpace($groqApiKey)) {
            $warnings.Add("Hybrid routing expects assistant_groq_api_key for the fast path. The backend may start in partial mode without fast API replies.")
        }
        if ([string]::IsNullOrWhiteSpace($geminiApiKey)) {
            $warnings.Add("Hybrid routing expects assistant_gemini_api_key for the deep path. The backend may start in partial mode without deep API replies.")
        }
    }

    return [PSCustomObject]@{
        Config = $config
        TtsProvider = $ttsProvider
        SttProvider = $sttProvider
        LlmProvider = $llmProvider
        Errors = @($errors)
        Warnings = @($warnings)
    }
}

function Write-RuntimeDiagnostics {
    param([pscustomobject]$Diagnostics)

    Write-AssistantInfo ("Configured LLM provider: " + $Diagnostics.LlmProvider)
    Write-AssistantInfo ("Configured STT provider: " + $Diagnostics.SttProvider)
    Write-AssistantInfo ("Configured TTS provider: " + $Diagnostics.TtsProvider)
    foreach ($error in $Diagnostics.Errors) {
        Write-Host ("[assistant][error] " + $error)
    }
    foreach ($warning in $Diagnostics.Warnings) {
        Write-AssistantWarning $warning
    }
}

function Assert-RuntimeDiagnosticsHealthy {
    param([pscustomobject]$Diagnostics)

    if ($Diagnostics.Errors.Count -gt 0) {
        throw ("Runtime preflight failed: " + ($Diagnostics.Errors -join " | "))
    }
}

function Assert-ReleaseLayout {
    param(
        [string]$OutputDir,
        [bool]$RequireClient = $false
    )

    $requiredFiles = @(
        (Join-Path $OutputDir "backend\requirements.txt"),
        (Join-Path $OutputDir "backend\run_local.py"),
        (Join-Path $OutputDir "backend\app\main.py"),
        (Join-Path $OutputDir "backend\app\api\routes.py"),
        (Join-Path $OutputDir "scripts\run_all.ps1"),
        (Join-Path $OutputDir "scripts\setup_windows.ps1"),
        (Join-Path $OutputDir "scripts\assistant_common.ps1"),
        (Join-Path $OutputDir "scripts\smoke_backend.py"),
        (Join-Path $OutputDir "scripts\fake_piper.py"),
        (Join-Path $OutputDir "scripts\fake_piper.cmd"),
        (Join-Path $OutputDir "scripts\fake_piper_model.onnx")
    )

    foreach ($path in $requiredFiles) {
        Assert-PathMatchesType -Path $path -ExpectedType File -Description "Release package required file" | Out-Null
    }

    $requiredDirectories = @(
        (Join-Path $OutputDir "backend"),
        (Join-Path $OutputDir "backend\app"),
        (Join-Path $OutputDir "backend\app\api"),
        (Join-Path $OutputDir "scripts")
    )

    foreach ($path in $requiredDirectories) {
        Assert-PathMatchesType -Path $path -ExpectedType Directory -Description "Release package required directory" | Out-Null
    }

    if ($RequireClient) {
        $clientDir = Join-Path $OutputDir "client"
        if (-not (Test-Path $clientDir)) {
            throw "Release package expected a client folder but none was copied."
        }

        $clientExecutables = @(
            Get-ChildItem -Path $clientDir -Filter "*.exe" -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -ne "UnityCrashHandler64.exe" }
        )
        if ($clientExecutables.Count -eq 0) {
            throw "Release package expected at least one client executable under $clientDir."
        }
    }
}

function Stop-ProcessSafe {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return
    }

    try {
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
    }
}

function Get-ChildProcessIds {
    param([int]$ProcessId)

    $results = @()
    try {
        $cimCommand = Get-Command Get-CimInstance -ErrorAction SilentlyContinue
        if ($null -ne $cimCommand) {
            $results = @(Get-CimInstance Win32_Process -Filter ("ParentProcessId = " + $ProcessId) -ErrorAction Stop |
                Select-Object -ExpandProperty ProcessId)
            return @($results)
        }
    }
    catch {
    }

    try {
        $wmiCommand = Get-Command Get-WmiObject -ErrorAction SilentlyContinue
        if ($null -ne $wmiCommand) {
            $results = @(Get-WmiObject Win32_Process -Filter ("ParentProcessId = " + $ProcessId) -ErrorAction Stop |
                Select-Object -ExpandProperty ProcessId)
        }
    }
    catch {
    }

    return @($results)
}

function Get-DescendantProcessIds {
    param(
        [int]$ProcessId,
        [hashtable]$Visited = $null
    )

    if ($null -eq $Visited) {
        $Visited = @{}
    }

    $ordered = New-Object System.Collections.Generic.List[int]
    foreach ($childProcessId in @(Get-ChildProcessIds -ProcessId $ProcessId)) {
        if ($Visited.ContainsKey($childProcessId)) {
            continue
        }

        $Visited[$childProcessId] = $true
        foreach ($descendantProcessId in @(Get-DescendantProcessIds -ProcessId $childProcessId -Visited $Visited)) {
            $ordered.Add($descendantProcessId)
        }
        $ordered.Add([int]$childProcessId)
    }

    return @($ordered)
}

function Stop-ProcessTreeSafe {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return
    }

    try {
        $processId = $Process.Id
    }
    catch {
        return
    }

    foreach ($childProcessId in @(Get-DescendantProcessIds -ProcessId $processId)) {
        try {
            $childProcess = Get-Process -Id $childProcessId -ErrorAction Stop
            if (-not $childProcess.HasExited) {
                Stop-Process -Id $childProcessId -Force -ErrorAction SilentlyContinue
            }
        }
        catch {
        }
    }

    Stop-ProcessSafe -Process $Process
}

function Get-ListeningTcpProcessId {
    param([int]$Port)

    $connectionCommand = Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue
    if ($null -ne $connectionCommand) {
        try {
            $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1
            if ($null -ne $connection) {
                return [int]$connection.OwningProcess
            }
        }
        catch {
        }
    }

    try {
        $netstatMatches = netstat -ano -p tcp | Select-String -Pattern (":{0}\s" -f $Port)
        foreach ($match in $netstatMatches) {
            $line = $match.ToString().Trim()
            if ($line -match ("^\s*TCP\s+\S+:{0}\s+\S+\s+LISTENING\s+(\d+)\s*$" -f $Port)) {
                return [int]$Matches[1]
            }
        }
    }
    catch {
    }

    return $null
}

function Get-ProcessSummary {
    param([int]$ProcessId)

    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
        return ($process.ProcessName + " (PID " + $process.Id + ")")
    }
    catch {
        return ("PID " + $ProcessId)
    }
}

function Read-AssistantLogTail {
    param(
        [string]$Path,
        [int]$LineCount = 20
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path $Path)) {
        return @()
    }

    try {
        return @(Get-Content -Path $Path -Tail $LineCount)
    }
    catch {
        return @()
    }
}
