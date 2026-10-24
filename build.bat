@echo off
rem Builds dist\ClaudePet.exe (needs: pip install -r requirements.txt pyinstaller)
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ClaudePet --icon icon.ico pet.pyw || exit /b 1
rem The exe loads an editable animations.py from its own folder if present
copy /y animations.py dist\animations.py >nul
echo Done: dist\ClaudePet.exe
