Запуск (Windows / PowerShell / cmd):
  cd c:\normacs\ntd
  py -3 ntd.py --input-dir data/tables --why --out out/YYYYMMDD.html

По умолчанию:
  • from-date = 2025-09-01
  • years     = 2025,2026

После успешного завершения (если НЕ указан --dry и НЕ указан --no-move-done)
скрипт автоматически переносит обработанные *.html из input-dir в:
  • data/done  (по умолчанию для input-dir = data/tables)
или в папку, указанную через --done-dir

Полезные режимы:
  • Сухой прогон + причины отбора:
      py -3 ntd.py --input-dir data/tables --dry --why

  • Только 2026:
      py -3 ntd.py --input-dir data/tables --years 2026 --from-date 2026-01-01 --out out/ntd_2026.html

  • Отключить перенос в done:
      py -3 ntd.py --input-dir data/tables --no-move-done --out out/ntd.html
