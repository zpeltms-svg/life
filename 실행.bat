@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 local_preview.py
  if errorlevel 1 pause
  goto :eof
)
where python >nul 2>&1
if %errorlevel%==0 (
  python local_preview.py
  if errorlevel 1 pause
  goto :eof
)
echo Python 3가 설치되어 있지 않습니다.
echo https://www.python.org/downloads/ 에서 Python 3를 설치한 뒤 다시 실행해 주세요.
pause
