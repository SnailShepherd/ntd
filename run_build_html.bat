\
        @echo off
        cd /d %~dp0
        if exist out\ntd.html del /q out\ntd.html >nul 2>nul
        py -3 ntd.py --input-dir data\tables --out out\ntd.html
        echo.
        echo Готово: out\ntd.html
        pause
