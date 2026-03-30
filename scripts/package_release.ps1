param(
    [string]$OutputDir = "",
    [string]$UnityBuildPath = ""
)

$ErrorActionPreference = "Stop"

$commonPath = Join-Path $PSScriptRoot "assistant_common.ps1"
. $commonPath

$exitCode = 1
$releaseFolderPrepared = $false

function Copy-DirectoryContents {
    param(
        [string]$Source,
        [string]$Destination
    )

    Get-ChildItem -Path $Source -Force | ForEach-Object {
        Copy-Item -Recurse -Force $_.FullName $Destination
    }
}

function Test-PathWithin {
    param(
        [string]$ParentPath,
        [string]$ChildPath
    )

    $resolvedParent = [System.IO.Path]::GetFullPath($ParentPath).TrimEnd("\")
    $resolvedChild = [System.IO.Path]::GetFullPath($ChildPath).TrimEnd("\")
    if ($resolvedChild.Length -le $resolvedParent.Length) {
        return $false
    }

    return $resolvedChild.StartsWith($resolvedParent + "\", [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-PackagingInputsReady {
    param(
        [string]$Root,
        [string]$OutputDir,
        [string]$UnityBuildPath
    )

    $backendSource = Resolve-BackendDirectory -Root $Root
    $requiredSourceFiles = @(
        (Join-Path $backendSource "requirements.txt"),
        (Join-Path $backendSource "run_local.py"),
        (Join-Path $backendSource "app\main.py"),
        (Join-Path $backendSource "app\api\routes.py"),
        (Join-Path $Root "scripts\run_all.ps1"),
        (Join-Path $Root "scripts\setup_windows.ps1"),
        (Join-Path $Root "scripts\assistant_common.ps1"),
        (Join-Path $Root "scripts\smoke_backend.py"),
        (Join-Path $Root "scripts\fake_piper.py"),
        (Join-Path $Root "scripts\fake_piper.cmd"),
        (Join-Path $Root "scripts\fake_piper_model.onnx")
    )

    foreach ($path in $requiredSourceFiles) {
        Assert-PathMatchesType -Path $path -ExpectedType File -Description "Packaging input required file" | Out-Null
    }

    $requiredSourceDirectories = @(
        $backendSource,
        (Join-Path $backendSource "app"),
        (Join-Path $backendSource "app\api"),
        (Join-Path $Root "scripts")
    )

    foreach ($path in $requiredSourceDirectories) {
        Assert-PathMatchesType -Path $path -ExpectedType Directory -Description "Packaging input required directory" | Out-Null
    }

    if (Test-PathWithin -ParentPath $backendSource -ChildPath $OutputDir) {
        throw "OutputDir cannot be inside the backend source folder: $OutputDir"
    }

    if (-not [string]::IsNullOrWhiteSpace($UnityBuildPath)) {
        if (-not (Test-Path $UnityBuildPath)) {
            throw "Unity build path not found: $UnityBuildPath"
        }

        $unityBuildItem = Get-Item $UnityBuildPath
        if (-not $unityBuildItem.PSIsContainer) {
            throw "UnityBuildPath must point to the built client directory, not a single file."
        }

        $unityExecutables = @(
            Get-ChildItem -Path $unityBuildItem.FullName -Filter "*.exe" -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -ne "UnityCrashHandler64.exe" }
        )
        if ($unityExecutables.Count -eq 0) {
            throw "UnityBuildPath must contain at least one client executable."
        }

        $resolvedUnityBuildPath = [System.IO.Path]::GetFullPath($UnityBuildPath).TrimEnd("\")
        $resolvedOutputDir = [System.IO.Path]::GetFullPath($OutputDir).TrimEnd("\")
        if ($resolvedUnityBuildPath -ieq $resolvedOutputDir) {
            throw "OutputDir cannot be the same directory as UnityBuildPath."
        }

        if (Test-PathWithin -ParentPath $UnityBuildPath -ChildPath $OutputDir) {
            throw "OutputDir cannot be created inside UnityBuildPath because packaging would copy into itself."
        }
    }
}

$root = Split-Path -Parent $PSScriptRoot
try {
    if (-not $OutputDir) {
        $OutputDir = Join-Path $root "release"
    }

    $exitCode = 30
    Assert-SafeOutputDirectory -Root $root -OutputDir $OutputDir
    Assert-PackagingInputsReady -Root $root -OutputDir $OutputDir -UnityBuildPath $UnityBuildPath
    Write-AssistantInfo ("Resolved release output path: " + ([System.IO.Path]::GetFullPath($OutputDir)))

    $exitCode = 31
    Invoke-AssistantStep -Name "Prepare clean release folder" -Action {
        if (Test-Path $OutputDir) {
            Write-AssistantInfo ("Removing existing release folder: " + $OutputDir)
            Remove-Item -Recurse -Force $OutputDir
        }

        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $OutputDir "backend") | Out-Null
        New-Item -ItemType Directory -Force -Path (Join-Path $OutputDir "scripts") | Out-Null
        $script:releaseFolderPrepared = $true
    }

    $backendOutput = Join-Path $OutputDir "backend"
    $exitCode = 32
    Invoke-AssistantStep -Name "Copy backend and script assets" -Action {
        Write-AssistantInfo ("Packaging backend into " + $backendOutput)
        Copy-DirectoryContents -Source (Join-Path $root "local-backend") -Destination $backendOutput
        Copy-Item -Force (Join-Path $root "scripts\run_all.ps1") (Join-Path $OutputDir "scripts\run_all.ps1")
        Copy-Item -Force (Join-Path $root "scripts\setup_windows.ps1") (Join-Path $OutputDir "scripts\setup_windows.ps1")
        Copy-Item -Force (Join-Path $root "scripts\assistant_common.ps1") (Join-Path $OutputDir "scripts\assistant_common.ps1")
        Copy-Item -Force (Join-Path $root "scripts\smoke_backend.py") (Join-Path $OutputDir "scripts\smoke_backend.py")
        Copy-Item -Force (Join-Path $root "scripts\fake_piper.py") (Join-Path $OutputDir "scripts\fake_piper.py")
        Copy-Item -Force (Join-Path $root "scripts\fake_piper.cmd") (Join-Path $OutputDir "scripts\fake_piper.cmd")
        Copy-Item -Force (Join-Path $root "scripts\fake_piper_model.onnx") (Join-Path $OutputDir "scripts\fake_piper_model.onnx")
    }

    if ($UnityBuildPath) {
        $exitCode = 33
        Invoke-AssistantStep -Name "Copy Unity client build" -Action {
            $clientOutput = Join-Path $OutputDir "client"
            New-Item -ItemType Directory -Force -Path $clientOutput | Out-Null

            $unityBuildItem = Get-Item $UnityBuildPath
            Copy-DirectoryContents -Source $unityBuildItem.FullName -Destination $clientOutput
        }
    }

    $requireClient = -not [string]::IsNullOrWhiteSpace($UnityBuildPath)
    $exitCode = 34
    Invoke-AssistantStep -Name "Validate packaged release layout" -Action {
        Assert-ReleaseLayout -OutputDir $OutputDir -RequireClient $requireClient
    }
    Write-AssistantSuccess "Release package prepared successfully."
    Write-AssistantInfo ("Release package path: " + $OutputDir)
    exit 0
}
catch {
    if ($releaseFolderPrepared -and (Test-Path $OutputDir)) {
        try {
            Write-AssistantWarning ("Cleaning up incomplete release folder: " + $OutputDir)
            Remove-Item -Recurse -Force $OutputDir
        }
        catch {
            Write-AssistantWarning ("Could not remove incomplete release folder: " + $OutputDir)
        }
    }
    Write-AssistantError $_.Exception.Message
    exit $exitCode
}
