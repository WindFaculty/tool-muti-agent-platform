param(
    [string]$BackendPython = "python"
)

$ErrorActionPreference = "Stop"

$commonPath = Join-Path $PSScriptRoot "assistant_common.ps1"
. $commonPath

$exitCode = 1

try {
    $root = Split-Path -Parent $PSScriptRoot
    $backend = Resolve-BackendDirectory -Root $root
    $resolvedBackendPython = $null

    Write-AssistantInfo ("Resolved backend path: " + $backend)
    $exitCode = 10
    Invoke-AssistantStep -Name "Resolve backend Python runtime" -Action {
        $script:resolvedBackendPython = Assert-CommandAvailable -Command $BackendPython -Label "Backend Python command"
        Write-AssistantInfo ("Using Python at: " + $script:resolvedBackendPython)
    }
    $exitCode = 11
    Invoke-AssistantStep -Name "Install local-backend Python dependencies" -Action {
        Push-Location $backend
        try {
            & $resolvedBackendPython -m pip install -r requirements.txt
            if ($LASTEXITCODE -ne 0) {
                throw "Python dependency install failed with exit code $LASTEXITCODE."
            }

            Assert-BackendPythonReady -PythonCommand $resolvedBackendPython
        }
        finally {
            Pop-Location
        }
    }

    $exitCode = 12
    Invoke-AssistantStep -Name "Run runtime preflight diagnostics" -Action {
        $diagnostics = Get-RuntimeDiagnostics -BackendDirectory $backend -PythonCommand $resolvedBackendPython
        Write-RuntimeDiagnostics -Diagnostics $diagnostics
        Assert-RuntimeDiagnosticsHealthy -Diagnostics $diagnostics
    }

    Write-Host ""
    Write-Host "Optional runtime environment variables:"
    Write-Host "  assistant_llm_provider=gemini"
    Write-Host "  assistant_gemini_api_key=<Gemini API key>"
    Write-Host "  assistant_gemini_model=gemini-2.5-flash"
    Write-Host "  assistant_gemini_base_url=https://generativelanguage.googleapis.com/v1beta/openai"
    Write-Host "  assistant_llm_provider=groq"
    Write-Host "  assistant_groq_api_key=<Groq API key>"
    Write-Host "  assistant_groq_model=llama-3.1-8b-instant"
    Write-Host "  assistant_groq_base_url=https://api.groq.com/openai/v1"
    Write-Host "  assistant_enable_ollama=true"
    Write-Host "  assistant_ollama_base_url=http://127.0.0.1:11434"
    Write-Host "  assistant_ollama_model=llama3.1:8b"
    Write-Host "  assistant_whisper_command=<path to whisper-cli.exe>"
    Write-Host "  assistant_whisper_model_path=<path to ggml model>"
    Write-Host "  assistant_tts_provider=chattts"
    Write-Host "  assistant_chattts_compile=false"
    Write-Host "  assistant_tts_provider=piper"
    Write-Host "  assistant_piper_command=<path to piper.exe>"
    Write-Host "  assistant_piper_model_path=<path to piper model>"
    Write-Host ""
    Write-AssistantSuccess "Backend setup complete."
    exit 0
}
catch {
    Write-AssistantError $_.Exception.Message
    exit $exitCode
}
