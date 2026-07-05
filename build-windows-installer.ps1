param(
    [ValidateSet("Targeted", "Full")]
    [string]$TestMode = "Targeted",

    [switch]$SkipTests,
    [switch]$SkipBuild,
    [switch]$CleanDist,
    [switch]$CheckOnly,
    [switch]$AllowDirty,
    [switch]$Help,

    [string]$UvPath = "",
    [string]$VulkanSdk = "",
    [string]$GitBin = "C:\Program Files\Git\bin",
    [string]$GitUsrBin = "C:\Program Files\Git\usr\bin",
    [string]$InnoSetupBin = "",
    [string]$BuildInfoPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$GitSafeDirectory = $RepoRoot.Replace("\", "/")
Set-Location $RepoRoot

function Show-Usage {
    Write-Host @"
Buzz Windows installer build script

Usage:
  .\build-windows-installer.ps1 [options]

Common options:
  -TestMode Targeted   Run the focused Windows GUI/OpenAI workflow tests.
  -TestMode Full       Run pytest without an explicit test list.
  -CleanDist           Remove dist before building.
  -CheckOnly           Check tools and source metadata, then exit.
  -SkipTests           Build without running pytest.
  -SkipBuild           Run checks and tests without building the installer.
  -AllowDirty          Allow tracked source changes during the build.
  -Help                Show this help.

Tool path overrides:
  -UvPath <path>
  -VulkanSdk <path>
  -GitBin <path>
  -GitUsrBin <path>
  -InnoSetupBin <path>
  -BuildInfoPath <path>

Examples:
  .\build-windows-installer.ps1
  .\build-windows-installer.ps1 -TestMode Full -CleanDist
  .\build-windows-installer.ps1 -CheckOnly
"@
}

if ($Help) {
    Show-Usage
    exit 0
}

function Get-FirstExistingPath {
    param([string[]]$Paths)

    foreach ($path in $Paths) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    return ""
}

function Resolve-Executable {
    param(
        [string]$ExplicitPath,
        [string]$CommandName,
        [string]$InstallHint
    )

    if ($ExplicitPath) {
        if (Test-Path -LiteralPath $ExplicitPath) {
            return (Resolve-Path -LiteralPath $ExplicitPath).Path
        }
        throw "$CommandName not found at '$ExplicitPath'. $InstallHint"
    }

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "$CommandName not found in PATH. $InstallHint"
}

function Resolve-VulkanSdk {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        return $ExplicitPath
    }
    if ($env:VULKAN_SDK) {
        return $env:VULKAN_SDK
    }

    $vulkanRoot = "C:\VulkanSDK"
    if (Test-Path -LiteralPath $vulkanRoot) {
        $latest = Get-ChildItem -LiteralPath $vulkanRoot -Directory |
            Sort-Object -Property Name -Descending |
            Select-Object -First 1
        if ($latest) {
            return $latest.FullName
        }
    }

    return ""
}

function Resolve-InnoSetupBin {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        return $ExplicitPath
    }

    return Get-FirstExistingPath @(
        "C:\Program Files (x86)\Inno Setup 6",
        "C:\Program Files\Inno Setup 6"
    )
}

function Invoke-Git {
    param([string[]]$Arguments)

    & git -c "safe.directory=$GitSafeDirectory" @Arguments
    return $LASTEXITCODE
}

function Get-GitOutput {
    param([string[]]$Arguments)

    $output = & git -c "safe.directory=$GitSafeDirectory" @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        return ""
    }
    return ($output -join "`n").Trim()
}

function Test-GitRepository {
    return Test-Path -LiteralPath (Join-Path $RepoRoot ".git")
}

function Get-SourceMetadata {
    $metadata = [ordered]@{
        Branch = "unknown"
        Commit = "unknown"
    }

    if ((Test-GitRepository) -and (Get-Command "git.exe" -ErrorAction SilentlyContinue)) {
        $branch = Get-GitOutput @("branch", "--show-current")
        $commit = Get-GitOutput @("rev-parse", "--short", "HEAD")
        if ($branch) {
            $metadata.Branch = $branch
        }
        if ($commit) {
            $metadata.Commit = $commit
        }
    }

    return $metadata
}

function Assert-TrackedSourcesReady {
    param([switch]$AllowDirtySources)

    if ($AllowDirtySources) {
        return
    }
    if (-not (Test-GitRepository)) {
        return
    }
    if (-not (Get-Command "git.exe" -ErrorAction SilentlyContinue)) {
        return
    }

    Invoke-Git @("diff", "--quiet", "--ignore-submodules=dirty", "--") | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Tracked source changes are present. Commit or stash them, or pass -AllowDirty."
    }

    Invoke-Git @("diff", "--cached", "--quiet", "--ignore-submodules=dirty", "--") | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Staged source changes are present. Commit or unstage them, or pass -AllowDirty."
    }
}

function Write-BuildInfo {
    param(
        [System.Collections.IEnumerable]$Artifacts,
        [hashtable]$SourceMetadata
    )

    $targetPath = $BuildInfoPath
    if (-not $targetPath) {
        $targetPath = Join-Path (Join-Path $RepoRoot "dist") "build-info.txt"
    }

    $lines = @(
        "Buzz Windows build",
        "GeneratedUtc: $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))",
        "Branch: $($SourceMetadata.Branch)",
        "Commit: $($SourceMetadata.Commit)",
        "TestMode: $TestMode",
        "TestsSkipped: $([bool]$SkipTests)",
        "BuildSkipped: $([bool]$SkipBuild)",
        "Artifacts:"
    )

    foreach ($artifact in $Artifacts) {
        $hash = Get-FileHash -LiteralPath $artifact.FullName -Algorithm SHA256
        $lines += "  $($artifact.Name) $($artifact.Length) bytes SHA256 $($hash.Hash)"
    }

    Set-Content -LiteralPath $targetPath -Value $lines -Encoding UTF8
    Write-Host "Build info: $targetPath"
}

function Assert-Command {
    param(
        [string]$CommandName,
        [string]$InstallHint
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "$CommandName not found in PATH. $InstallHint"
    }
}

function Invoke-Step {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$Arguments
    )

    Write-Host ""
    Write-Host "==> $Label"
    Write-Host "$FilePath $($Arguments -join ' ')"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

if (-not $UvPath) {
    $defaultUvPath = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path -LiteralPath $defaultUvPath) {
        $UvPath = $defaultUvPath
    }
}
$UvExe = Resolve-Executable $UvPath "uv.exe" "Install uv or pass -UvPath."

$VulkanSdk = Resolve-VulkanSdk $VulkanSdk
$InnoSetupBin = Resolve-InnoSetupBin $InnoSetupBin
$sourceMetadata = Get-SourceMetadata

Write-Host "Source: $($sourceMetadata.Branch) $($sourceMetadata.Commit)"
Assert-TrackedSourcesReady -AllowDirtySources:$AllowDirty

$extraPath = @()

if ($VulkanSdk -and (Test-Path -LiteralPath $VulkanSdk)) {
    $vulkanBin = Join-Path $VulkanSdk "Bin"
    if (Test-Path -LiteralPath $vulkanBin) {
        $env:VULKAN_SDK = $VulkanSdk
        $extraPath += $vulkanBin
    }
} elseif (-not $SkipBuild) {
    throw "Vulkan SDK not found. Install Vulkan SDK or pass -VulkanSdk."
}

$bashPath = Join-Path $GitBin "bash.exe"
if (Test-Path -LiteralPath $bashPath) {
    $env:SHELL = $bashPath.Replace("\", "/")
    $env:MAKESHELL = $env:SHELL
    $extraPath += $GitUsrBin
    $extraPath += $GitBin
} elseif (-not $SkipBuild) {
    throw "Git Bash not found at '$bashPath'. Install Git for Windows or pass -GitBin."
}

if (-not $SkipBuild) {
    $isccPath = Join-Path $InnoSetupBin "ISCC.exe"
    $IsccExe = Resolve-Executable $isccPath "iscc.exe" "Install Inno Setup 6 or pass -InnoSetupBin."
    $extraPath += (Split-Path -Parent $IsccExe)
}

if ($extraPath.Count -gt 0) {
    $env:Path = (($extraPath | Where-Object { $_ -and (Test-Path -LiteralPath $_) }) + $env:Path) -join [IO.Path]::PathSeparator
}

if (-not $SkipBuild) {
    Assert-Command "make.exe" "Install GNU Make and ensure it is in PATH."
    Assert-Command "cmake.exe" "Install CMake and ensure it is in PATH."
    Assert-Command "ffmpeg.exe" "Install ffmpeg and ensure it is in PATH."
    Assert-Command "ffprobe.exe" "Install ffmpeg and ensure ffprobe is in PATH."
    Assert-Command "iscc.exe" "Install Inno Setup 6 and ensure ISCC.exe is in PATH."
}

if ($CheckOnly) {
    Write-Host ""
    Write-Host "Check complete."
    Write-Host "uv: $UvExe"
    Write-Host "Vulkan SDK: $VulkanSdk"
    Write-Host "Git Bash: $bashPath"
    if ($InnoSetupBin) {
        Write-Host "Inno Setup: $InnoSetupBin"
    }
    exit 0
}

if ($CleanDist) {
    Write-Host ""
    Write-Host "==> Cleaning dist"
    if (Test-Path -LiteralPath (Join-Path $RepoRoot "dist")) {
        Remove-Item -LiteralPath (Join-Path $RepoRoot "dist") -Recurse -Force
    }
}

if (-not $SkipTests) {
    $pytestArgs = @("run", "pytest")
    if ($TestMode -eq "Targeted") {
        $pytestArgs += @(
            "tests\cost_estimation_test.py",
            "tests\widgets\file_transcriber_widget_test.py",
            "tests\widgets\main_window_test.py::TestMainWindow::test_open_file_transcriber_passes_plugin_manager",
            "tests\plugins\transcript_post_processing_test.py",
            "tests\plugins\transcript_post_processing_models_test.py",
            "tests\plugins\plugin_system_test.py"
        )
    }

    Invoke-Step "Run $TestMode tests" $UvExe $pytestArgs
}

if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "==> Copying dll_backup into buzz"
    Copy-Item -Path (Join-Path $RepoRoot "dll_backup") -Destination (Join-Path $RepoRoot "buzz") -Recurse -Force

    Invoke-Step "Build Windows installer" $UvExe @("run", "make", "bundle_windows")

    $artifacts = Get-ChildItem -Path (Join-Path $RepoRoot "dist") -File -Filter "Buzz*-windows*" -ErrorAction SilentlyContinue
    if (-not $artifacts) {
        throw "Build finished but no dist\Buzz*-windows* artifact was found."
    }

    Write-Host ""
    Write-Host "Windows installer artifacts:"
    foreach ($artifact in $artifacts) {
        Write-Host "  $($artifact.FullName)"
    }
    Write-BuildInfo -Artifacts $artifacts -SourceMetadata $sourceMetadata
    Write-Host ""
    Write-Host "If .bin files are listed, keep them next to the .exe installer."
}

<#
.SYNOPSIS
Runs the Windows verification set and builds the Buzz installer.

.DESCRIPTION
Prepares the local Windows build environment, runs pytest, builds the PyInstaller
bundle through the project Makefile, and creates the Inno Setup installer.

The default run is intended for release candidates from a clean committed source
tree. Use -CheckOnly to validate tools and source metadata without running tests
or building. Use -AllowDirty only when intentionally testing local edits.

.PARAMETER TestMode
Targeted runs the focused Windows GUI/OpenAI workflow tests. Full runs pytest
without an explicit test list.

.PARAMETER SkipTests
Build without running pytest.

.PARAMETER SkipBuild
Run checks and tests without building the installer.

.PARAMETER CleanDist
Remove the dist directory before building.

.PARAMETER CheckOnly
Check tools, source metadata, and environment setup, then exit.

.PARAMETER AllowDirty
Allow tracked source changes during the build.

.PARAMETER Help
Show built-in script usage.

.EXAMPLE
.\build-windows-installer.ps1

.EXAMPLE
.\build-windows-installer.ps1 -TestMode Full -CleanDist

.EXAMPLE
.\build-windows-installer.ps1 -CheckOnly
#>
