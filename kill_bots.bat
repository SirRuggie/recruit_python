@echo off
echo Killing all Python processes running main.py...
for /f "tokens=2" %%i in ('wmic process where "name='python.exe' and commandline like '%%main.py%%'" get processid ^| findstr /r "[0-9]"') do (
    echo Killing process %%i
    taskkill /PID %%i /F
)
echo Done!