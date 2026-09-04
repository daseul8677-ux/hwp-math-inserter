# 새 버전 내기
#   .\release.ps1 1.1.0 "무엇이 바뀌었는지 한 줄"
#
# 하는 일: 판 번호 올리기 -> exe 만들기 -> GitHub 릴리스에 올리기 -> latest.json 갱신 -> 밀어넣기
# 이걸 실행하면 모든 노트북의 앱이 다음 실행 때 새 버전을 알아차린다.

param(
  [Parameter(Mandatory=$true)][string]$Version,
  [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$gh = "C:\Program Files\GitHub CLI\gh.exe"
if (-not (Test-Path $gh)) {
  $cmd = Get-Command gh -ErrorAction SilentlyContinue
  if ($cmd) { $gh = $cmd.Source } else { throw "gh(GitHub CLI) 를 찾지 못했습니다." }
}

$repo = (& $gh repo view --json nameWithOwner -q .nameWithOwner)
if (-not $repo) { throw "GitHub 저장소를 찾지 못했습니다." }
Write-Host "저장소: $repo"

# 1) 판 번호 올리기
$verFile = @"
# -*- coding: utf-8 -*-
"""프로그램 판 번호. 새 버전을 낼 때 이 숫자를 올린다."""

VERSION = "$Version"
"@
Set-Content -Path "hwpmath\version.py" -Encoding utf8 -Value $verFile
Write-Host "판 번호 -> $Version"

# 2) exe 만들기
Get-Process "문제캡쳐한글삽입기" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name "문제캡쳐한글삽입기" --add-data "hwpmath/web;web" `
  --hidden-import win32timezone run.py | Out-Null
$exe = "dist\문제캡쳐한글삽입기.exe"
if (-not (Test-Path $exe)) { throw "exe 를 만들지 못했습니다." }
Write-Host "exe 완성: $([math]::Round((Get-Item $exe).Length/1MB,1)) MB"

# GitHub 은 파일명에 한글이 있으면 이름을 바꿔 버린다 -> 영문 이름으로 올린다
$asset = "dist\HwpMathInserter.exe"
Copy-Item $exe $asset -Force

# 3) GitHub 릴리스에 올리기
$tag = "v$Version"
$noteText = if ($Notes) { $Notes } else { "새 버전" }
& $gh release create $tag $asset --title "v$Version" --notes $noteText 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "릴리스가 이미 있어 파일만 덮어씁니다."
  & $gh release upload $tag $asset --clobber
}

# 4) latest.json 갱신 (앱이 이 파일을 보고 새 버전을 알아챈다)
$dl = "https://github.com/$repo/releases/download/$tag/HwpMathInserter.exe"
$json = [ordered]@{ version = $Version; url = $dl; notes = $noteText } | ConvertTo-Json
# BOM 없이 저장해야 앱이 읽을 수 있다
[System.IO.File]::WriteAllText(
  (Join-Path $PSScriptRoot "latest.json"), $json, (New-Object Text.UTF8Encoding($false)))
Write-Host "latest.json 갱신"

# 5) 밀어넣기
git add -A
$msg = "v$Version"
if ($Notes) { $msg = "v${Version}: $Notes" }
git commit -m $msg | Out-Null
git push
Write-Host ""
Write-Host "끝났습니다. 모든 노트북의 앱이 다음 실행 때 v$Version 을 알립니다."
