@echo off
cd /d "%~dp0"
py -m pip install --quiet Pillow
py media_date_sorter.py
if errorlevel 1 (
  echo.
  echo The app could not start. Make sure Python 3 is installed and added to PATH.
  pause
)
