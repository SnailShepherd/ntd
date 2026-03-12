\
        @echo off
        cd /d %~dp0
        py -3 ntd.py --input-dir data\tables --max 20 --out out\ntd_test_max20.html
        echo.
        echo Готово: out\ntd_test_max20.html
        pause
