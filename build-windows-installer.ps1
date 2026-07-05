param(
    [ValidateSet("Targeted", "Full")]
    [string]$TestMode = "Targeted",

    [switch]$SkipTests,
    [switch]$SkipBuild,
    [switch]$CleanDist,
    [switch]$CheckOnly,
    [switch]$AllowDirty,
    [switch]$InstallMissing,
    [switch]$Yes,
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

$OriginalPath = $env:Path
$UvExe = ""
$IsccExe = ""
$ResolvedVulkanSdk = ""
$GitBashPath = ""

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
  -InstallMissing      Try to install selected missing tools with winget.
  -Yes                 Do not prompt before -InstallMissing actions.
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
  .\build-windows-installer.ps1 -CheckOnly -InstallMissing
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
        "C:\Program Files\Inno Setup 6",
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6")
    )
}

function Find-Executable {
    param(
        [string]$ExplicitPath,
        [string]$CommandName
    )

    if ($ExplicitPath) {
        if (Test-Path -LiteralPath $ExplicitPath) {
            return (Resolve-Path -LiteralPath $ExplicitPath).Path
        }
        return ""
    }

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return ""
}

function Get-ToolVersion {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @("--version")
    )

    if (-not $FilePath) {
        return ""
    }

    try {
        $output = & $FilePath @Arguments 2>$null | Select-Object -First 1
        if ($output) {
            return ([string]$output).Trim()
        }
    } catch {
        return ""
    }

    return ""
}

function Resolve-MSBuild {
    $command = Get-Command "MSBuild.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @()
    if (${env:ProgramFiles(x86)}) {
        $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
        if (Test-Path -LiteralPath $vswhere) {
            $found = & $vswhere -latest -products "*" -requires "Microsoft.Component.MSBuild" -find "MSBuild\**\Bin\MSBuild.exe" 2>$null
            if ($found) {
                $candidates += $found
            }
        }

        $candidates += @(
            (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\amd64\MSBuild.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\amd64\MSBuild.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\amd64\MSBuild.exe")
        )
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return ""
}

function New-PrerequisiteResult {
    param(
        [string]$Name,
        [string]$RequiredFor,
        [bool]$Required,
        [bool]$Found,
        [string]$Path = "",
        [string]$Version = "",
        [string]$InstallHint = "",
        [string]$WingetId = "",
        [bool]$AutoInstall = $false
    )

    return [PSCustomObject]@{
        Name = $Name
        RequiredFor = $RequiredFor
        Required = $Required
        Found = $Found
        Path = $Path
        Version = $Version
        InstallHint = $InstallHint
        WingetId = $WingetId
        AutoInstall = $AutoInstall
    }
}

function Write-PrerequisiteReport {
    param([object[]]$Prerequisites)

    Write-Host ""
    Write-Host "Build prerequisite check:"

    foreach ($item in $Prerequisites) {
        if ($item.Found) {
            $status = "OK"
        } elseif ($item.Required) {
            $status = "MISSING"
        } else {
            $status = "SKIPPED"
        }

        Write-Host "  [$status] $($item.Name) - $($item.RequiredFor)"
        if ($item.Path) {
            Write-Host "      Path: $($item.Path)"
        }
        if ($item.Version) {
            Write-Host "      Version: $($item.Version)"
        }
        if ((-not $item.Found) -and $item.Required -and $item.InstallHint) {
            Write-Host "      Install: $($item.InstallHint)"
        }
    }
}

function Invoke-MissingPrerequisiteInstall {
    param([object[]]$MissingPrerequisites)

    $installable = @($MissingPrerequisites | Where-Object { $_.AutoInstall -and $_.WingetId })
    if ($installable.Count -eq 0) {
        return
    }

    $winget = Find-Executable "" "winget.exe"
    if (-not $winget) {
        Write-Host ""
        Write-Host "winget.exe was not found. Install the missing prerequisites manually."
        return
    }

    Write-Host ""
    Write-Host "The script can try to install these prerequisites with winget:"
    foreach ($item in $installable) {
        Write-Host "  $($item.Name) ($($item.WingetId))"
    }

    if (-not $Yes) {
        $answer = Read-Host "Install now? [y/N]"
        if ($answer -notin @("y", "Y", "yes", "YES")) {
            Write-Host "Automatic installation skipped."
            return
        }
    }

    foreach ($item in $installable) {
        Write-Host ""
        Write-Host "==> Installing $($item.Name)"
        & $winget install --id $item.WingetId -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to install $($item.Name) with winget. Install it manually."
        }
    }
}

function Test-BuildPrerequisites {
    $requiresBuildTools = -not $SkipBuild
    $results = @()
    $extraPath = @()

    if (-not $UvPath) {
        $defaultUvPath = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
        if (Test-Path -LiteralPath $defaultUvPath) {
            $script:UvExe = Find-Executable $defaultUvPath "uv.exe"
        } else {
            $script:UvExe = Find-Executable "" "uv.exe"
        }
    } else {
        $script:UvExe = Find-Executable $UvPath "uv.exe"
    }
    $results += New-PrerequisiteResult `
        -Name "uv" `
        -RequiredFor "Python environment, tests, and project commands" `
        -Required $true `
        -Found ([bool]$script:UvExe) `
        -Path $script:UvExe `
        -Version (Get-ToolVersion $script:UvExe @("--version")) `
        -InstallHint "Install uv from https://docs.astral.sh/uv/getting-started/installation/ or run: winget install --id astral-sh.uv -e" `
        -WingetId "astral-sh.uv" `
        -AutoInstall $true

    $venvScripts = Join-Path $RepoRoot ".venv\Scripts"
    if (Test-Path -LiteralPath $venvScripts) {
        $extraPath += $venvScripts
    }

    $script:ResolvedVulkanSdk = Resolve-VulkanSdk $VulkanSdk
    $vulkanFound = $script:ResolvedVulkanSdk -and (Test-Path -LiteralPath $script:ResolvedVulkanSdk)
    if ($vulkanFound) {
        $vulkanBin = Join-Path $script:ResolvedVulkanSdk "Bin"
        if (Test-Path -LiteralPath $vulkanBin) {
            $env:VULKAN_SDK = $script:ResolvedVulkanSdk
            $extraPath += $vulkanBin
        }
    }
    $results += New-PrerequisiteResult `
        -Name "Vulkan SDK" `
        -RequiredFor "whisper.cpp Vulkan build" `
        -Required $requiresBuildTools `
        -Found ([bool]$vulkanFound) `
        -Path $script:ResolvedVulkanSdk `
        -InstallHint "Install Vulkan SDK and ensure VULKAN_SDK is set, or pass -VulkanSdk."

    $script:GitBashPath = Join-Path $GitBin "bash.exe"
    $gitBashFound = Test-Path -LiteralPath $script:GitBashPath
    if ($gitBashFound) {
        $env:SHELL = $script:GitBashPath.Replace("\", "/")
        $env:MAKESHELL = $env:SHELL
        $extraPath += $GitUsrBin
        $extraPath += $GitBin
    }
    $results += New-PrerequisiteResult `
        -Name "Git Bash" `
        -RequiredFor "Makefile shell commands on Windows" `
        -Required $requiresBuildTools `
        -Found ([bool]$gitBashFound) `
        -Path $script:GitBashPath `
        -InstallHint "Install Git for Windows or pass -GitBin and -GitUsrBin."

    $gitExplicitPath = Join-Path $GitBin "git.exe"
    if (-not (Test-Path -LiteralPath $gitExplicitPath)) {
        $gitExplicitPath = ""
    }
    $gitExe = Find-Executable $gitExplicitPath "git.exe"
    $results += New-PrerequisiteResult `
        -Name "Git" `
        -RequiredFor "source metadata and source readiness checks" `
        -Required (Test-GitRepository) `
        -Found ([bool]$gitExe) `
        -Path $gitExe `
        -Version (Get-ToolVersion $gitExe @("--version")) `
        -InstallHint "Install Git for Windows or ensure git.exe is in PATH."

    $script:InnoSetupBin = Resolve-InnoSetupBin $InnoSetupBin
    if ($script:InnoSetupBin) {
        $extraPath += $script:InnoSetupBin
    }

    $existingExtraPath = @($extraPath | Where-Object { $_ -and (Test-Path -LiteralPath $_) })
    if ($existingExtraPath.Count -gt 0) {
        $env:Path = ($existingExtraPath + $OriginalPath) -join [IO.Path]::PathSeparator
    }

    $makeExe = Find-Executable "" "make.exe"
    $results += New-PrerequisiteResult `
        -Name "GNU Make" `
        -RequiredFor "project bundle_windows target" `
        -Required $requiresBuildTools `
        -Found ([bool]$makeExe) `
        -Path $makeExe `
        -Version (Get-ToolVersion $makeExe @("--version")) `
        -InstallHint "Install Git for Windows with Unix tools, or pass -GitUsrBin."

    $ffmpegExe = Find-Executable "" "ffmpeg.exe"
    $results += New-PrerequisiteResult `
        -Name "ffmpeg" `
        -RequiredFor "runtime media processing bundled with the app" `
        -Required $requiresBuildTools `
        -Found ([bool]$ffmpegExe) `
        -Path $ffmpegExe `
        -Version (Get-ToolVersion $ffmpegExe @("-version")) `
        -InstallHint "Install ffmpeg and ensure ffmpeg.exe is in PATH."

    $ffprobeExe = Find-Executable "" "ffprobe.exe"
    $results += New-PrerequisiteResult `
        -Name "ffprobe" `
        -RequiredFor "runtime media metadata probing bundled with the app" `
        -Required $requiresBuildTools `
        -Found ([bool]$ffprobeExe) `
        -Path $ffprobeExe `
        -Version (Get-ToolVersion $ffprobeExe @("-version")) `
        -InstallHint "Install ffmpeg and ensure ffprobe.exe is in PATH."

    $script:IsccExe = Find-Executable "" "iscc.exe"
    $results += New-PrerequisiteResult `
        -Name "Inno Setup 6" `
        -RequiredFor "Windows installer creation" `
        -Required $requiresBuildTools `
        -Found ([bool]$script:IsccExe) `
        -Path $script:IsccExe `
        -Version (Get-ToolVersion $script:IsccExe @("/?")) `
        -InstallHint "Install Inno Setup 6 or pass -InnoSetupBin." `
        -WingetId "JRSoftware.InnoSetup" `
        -AutoInstall $true

    $msBuild = Resolve-MSBuild
    $results += New-PrerequisiteResult `
        -Name "MSBuild / Visual C++ Build Tools" `
        -RequiredFor "native whisper.cpp build" `
        -Required $requiresBuildTools `
        -Found ([bool]$msBuild) `
        -Path $msBuild `
        -Version (Get-ToolVersion $msBuild @("-version")) `
        -InstallHint "Install Visual Studio 2022 Build Tools with the C++ workload."

    $glslc = ""
    if ($vulkanFound) {
        $glslc = Find-Executable (Join-Path (Join-Path $script:ResolvedVulkanSdk "Bin") "glslc.exe") "glslc.exe"
    }
    $results += New-PrerequisiteResult `
        -Name "Vulkan shader compiler" `
        -RequiredFor "whisper.cpp Vulkan shaders" `
        -Required $requiresBuildTools `
        -Found ([bool]$glslc) `
        -Path $glslc `
        -Version (Get-ToolVersion $glslc @("--version")) `
        -InstallHint "Install Vulkan SDK or pass -VulkanSdk."

    return $results
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

$preflight = Test-BuildPrerequisites
Write-PrerequisiteReport $preflight

$missingPrerequisites = @($preflight | Where-Object { $_.Required -and (-not $_.Found) })
if (($missingPrerequisites.Count -gt 0) -and $InstallMissing) {
    Invoke-MissingPrerequisiteInstall $missingPrerequisites
    $preflight = Test-BuildPrerequisites
    Write-PrerequisiteReport $preflight
    $missingPrerequisites = @($preflight | Where-Object { $_.Required -and (-not $_.Found) })
}

if ($missingPrerequisites.Count -gt 0) {
    $missingNames = ($missingPrerequisites | ForEach-Object { $_.Name }) -join ", "
    throw "Missing required prerequisites: $missingNames. Install them manually or rerun with -InstallMissing for supported tools."
}

$sourceMetadata = Get-SourceMetadata

Write-Host ""
Write-Host "Source: $($sourceMetadata.Branch) $($sourceMetadata.Commit)"
Assert-TrackedSourcesReady -AllowDirtySources:$AllowDirty

if ($CheckOnly) {
    Write-Host ""
    Write-Host "Check complete. Environment is ready for the selected mode."
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
Checks the local Windows build environment, runs pytest, builds the PyInstaller
bundle through the project Makefile, and creates the Inno Setup installer.

The default run is intended for release candidates from a clean committed source
tree. Use -CheckOnly to validate tools and source metadata without running tests
or building. Missing system tools are reported with install hints. Use
-InstallMissing only when you explicitly want the script to try installing
supported tools with winget. Use -AllowDirty only when intentionally testing
local edits.

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

.PARAMETER InstallMissing
Try to install selected missing prerequisites with winget. Heavy toolchain
components such as Visual Studio Build Tools and Vulkan SDK are reported but not
installed automatically.

.PARAMETER Yes
Skip the confirmation prompt when using -InstallMissing.

.PARAMETER Help
Show built-in script usage.

.EXAMPLE
.\build-windows-installer.ps1

.EXAMPLE
.\build-windows-installer.ps1 -TestMode Full -CleanDist

.EXAMPLE
.\build-windows-installer.ps1 -CheckOnly
#>
