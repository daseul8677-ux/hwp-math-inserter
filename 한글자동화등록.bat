@echo off
title 한글 자동화 등록
color 0F
echo.
echo  ===================================================
echo    아래한글 자동화 등록
echo  ===================================================
echo.
echo  이 창이 "관리자: ..." 로 시작하지 않으면 닫고
echo  파일을 우클릭해서 [관리자 권한으로 실행] 해 주세요.
echo.

net session >nul 2>&1
if errorlevel 1 (
  echo  [!] 관리자 권한이 아닙니다.
  echo      이 파일을 우클릭 - [관리자 권한으로 실행] 을 눌러 주세요.
  echo.
  pause
  exit /b 1
)

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
timeout /t 3 /nobreak >nul
echo         완료
echo.

echo  [3/3] 확인 중...
reg query "HKLM\SOFTWARE\Classes\HWPFrame.HwpObject\CLSID" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ***  등록되지 않았습니다.  ***
  echo.
  echo  제어판 - 프로그램 - 한컴오피스 2024 - 변경 에서
  echo  복구 / 수리 를 실행해 보세요.
) else (
  echo.
  echo  ***  등록 성공!  ***
  echo.
  echo  이제 아래한글을 열고 문서를 하나 띄운 뒤,
  echo  삽입기 앱에서 [새로고침] 을 눌러 주세요.
)
echo.
pause
