@echo off
chcp 65001 > nul
cd /d "%~dp0"
python -c "import PIL, requests, win32com.client" 2>nul || (
  echo 처음 실행이라 필요한 것들을 설치합니다...
  python -m pip install -r requirements.txt
)
python run.py
