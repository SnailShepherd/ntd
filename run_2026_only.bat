\
        @echo off
        cd /d %~dp0
        py -3 ntd.py --input-dir data\tables --years 2026 --from-date 2026-01-01 --out out\ntd_2026.html
        echo.
        echo Готово: out\ntd_2026.html
        pause
