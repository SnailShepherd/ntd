\
        @echo off
        cd /d %~dp0
        py -3 ntd.py --input-dir data\tables --dry --why
        pause
