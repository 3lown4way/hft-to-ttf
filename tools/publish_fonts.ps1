param(
    [string]$FontZip = "",
    [string]$ConverterZip = ""
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

function Select-ZipFile([string]$Title) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = $Title
    $dialog.Filter = 'ZIP files (*.zip)|*.zip|All files (*.*)|*.*'
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        return $dialog.FileName
    }
    return ''
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'git 명령을 찾을 수 없습니다. Git for Windows 또는 GitHub Desktop을 설치한 뒤 다시 실행하세요.'
}

if ([string]::IsNullOrWhiteSpace($FontZip)) {
    $FontZip = Select-ZipFile 'FONTS ZIP 파일을 선택하세요'
}
if ([string]::IsNullOrWhiteSpace($FontZip) -or -not (Test-Path -LiteralPath $FontZip)) {
    throw 'FONTS ZIP 파일이 선택되지 않았습니다.'
}

if ([string]::IsNullOrWhiteSpace($ConverterZip)) {
    $ConverterZip = Select-ZipFile 'KICE09_HFT_converter_v3_4 ZIP 파일을 선택하세요 (취소하면 생략)'
}

$repoUrl = 'https://github.com/3lown4way/hft-to-ttf.git'
$workRoot = Join-Path $env:TEMP ('hft-to-ttf-publish-' + [Guid]::NewGuid().ToString('N'))
$repoDir = Join-Path $workRoot 'repo'
$extractDir = Join-Path $workRoot 'fonts-extracted'

New-Item -ItemType Directory -Path $workRoot | Out-Null

try {
    Write-Host '1/7 Clone repository...'
    git clone $repoUrl $repoDir
    if ($LASTEXITCODE -ne 0) { throw 'git clone failed' }

    Write-Host '2/7 Extract source ZIP...'
    New-Item -ItemType Directory -Path $extractDir | Out-Null
    Expand-Archive -LiteralPath $FontZip -DestinationPath $extractDir -Force

    $fontFiles = Get-ChildItem -LiteralPath $extractDir -Recurse -File | Where-Object {
        $_.Extension -ieq '.HFT' -or $_.Extension -ieq '.TTF' -or $_.Extension -ieq '.INF'
    }

    $hftCount = @($fontFiles | Where-Object Extension -IEq '.HFT').Count
    $ttfCount = @($fontFiles | Where-Object Extension -IEq '.TTF').Count
    $infCount = @($fontFiles | Where-Object Extension -IEq '.INF').Count
    $totalCount = @($fontFiles).Count

    Write-Host "Inventory: total=$totalCount HFT=$hftCount TTF=$ttfCount INF=$infCount"
    if ($totalCount -ne 420 -or $hftCount -ne 387 -or $ttfCount -ne 32 -or $infCount -ne 1) {
        throw 'Expected inventory is 420 files = 387 HFT + 32 TTF + 1 INF. Aborting to avoid publishing the wrong archive.'
    }

    $duplicates = $fontFiles | Group-Object Name | Where-Object Count -gt 1
    if ($duplicates) {
        $names = ($duplicates | ForEach-Object Name) -join ', '
        throw "Duplicate file names found: $names"
    }

    $tooLarge = $fontFiles | Where-Object Length -ge 100MB
    if ($tooLarge) {
        throw ('GitHub 100 MB single-file limit exceeded: ' + (($tooLarge | ForEach-Object Name) -join ', '))
    }

    Write-Host '3/7 Copy 420 files into fonts/ as individual Git files...'
    $fontsDir = Join-Path $repoDir 'fonts'
    if (Test-Path $fontsDir) { Remove-Item $fontsDir -Recurse -Force }
    New-Item -ItemType Directory -Path $fontsDir | Out-Null
    foreach ($file in $fontFiles) {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $fontsDir $file.Name)
    }

    if (-not [string]::IsNullOrWhiteSpace($ConverterZip) -and (Test-Path -LiteralPath $ConverterZip)) {
        Write-Host '4/7 Copy converter v3.4 package...'
        $converterDir = Join-Path $repoDir 'converter'
        New-Item -ItemType Directory -Path $converterDir -Force | Out-Null
        Copy-Item -LiteralPath $ConverterZip -Destination (Join-Path $converterDir 'KICE09_HFT_converter_v3_4.zip') -Force
    } else {
        Write-Host '4/7 Converter ZIP skipped.'
    }

    Write-Host '5/7 Stage files...'
    Push-Location $repoDir
    try {
        git add fonts converter/KICE09_HFT_converter_v3_4.zip 2>$null
        git status --short

        git diff --cached --quiet
        if ($LASTEXITCODE -eq 0) {
            Write-Host 'No changes to commit.'
            return
        }

        Write-Host '6/7 Commit...'
        git commit -m 'data: add source HFT fonts and converter v3.4'
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed' }

        Write-Host '7/7 Push to main...'
        git push origin main
        if ($LASTEXITCODE -ne 0) { throw 'git push failed' }
    }
    finally {
        Pop-Location
    }

    Write-Host ''
    Write-Host 'DONE: fonts/ contains 420 individual files and converter v3.4 is published.'
}
finally {
    if (Test-Path $workRoot) {
        Remove-Item $workRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
