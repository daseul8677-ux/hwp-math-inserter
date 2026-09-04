@echo off
title 한글 자동화 등록
cd /d "%~dp0"

rem 관리자 권한이 아니면 스스로 승인을 요청한다 (파일 이름은 영문이어야 경로가 안 깨진다)
net session >nul 2>&1
if not errorlevel 1 goto ADMIN
echo.
echo  관리자 권한을 요청합니다.
echo  잠시 뒤 뜨는 승인 창에서 [예] 를 눌러 주세요.
echo.
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" >nul 2>&1
if errorlevel 1 (
  echo  [!] 승인 창을 띄우지 못했습니다.
  echo      이 파일을 우클릭 - [관리자 권한으로 실행] 해 주세요.
  echo.
  pause
)
exit /b

:ADMIN
color 0F
echo.
echo  ===================================================
echo    아래한글 자동화 등록  (관리자 권한 확인됨)
echo  ===================================================
echo.

echo  [1/3] 아래한글을 찾는 중...
set "HWORD="
for /f "delims=" %%F in ('dir /b /s "%ProgramFiles(x86)%\Hnc\Hword.exe" 2^>nul') do if not defined HWORD set "HWORD=%%F"
if not defined HWORD for /f "delims=" %%F in ('dir /b /s "%ProgramFiles%\Hnc\Hword.exe" 2^>nul') do if not defined HWORD set "HWORD=%%F"

if not defined HWORD (
  echo      [실패] 아래한글을 찾지 못했습니다.
  echo             한컴오피스가 설치돼 있는지 확인해 주세요.
  echo.
  pause
  exit /b 1
)
echo         찾음: %HWORD%
echo.

echo  [2/3] 등록하는 중...
taskkill /f /im Hword.exe >nul 2>&1
"%HWORD%" /regserver
timeout /t 4 /nobreak >nul
echo         완료
echo.

echo  [3/3] 확인 중...
reg query "HKLM\SOFTWARE\Classes\HWPFrame.HwpObject\CLSID" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ***  아직 등록되지 않았습니다.  ***
  echo.
  echo  제어판 - 프로그램 - 한컴오피스 2024 - 변경 에서
  echo  복구 / 수리 를 실행해 보세요.
) else (
  echo.
  echo  ***  등록 성공!  ***
  echo.
  echo  아래한글을 열고 문서를 하나 띄운 뒤,
  echo  삽입기 앱에서 [새로고침] 을 눌러 주세요.
)
echo.
pause
