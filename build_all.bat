@echo off
chcp 65001 >nul
if not exist out mkdir out

for %%P in (btb etp std ita ftc ctm) do (
  if exist %%P_plain_ar.txt (
    python reshape_arabic.py %%P_plain_ar.txt out\%%P_english.txt --pad 2
  ) else (
    echo skipped %%P: %%P_plain_ar.txt not found
  )
)

echo.
echo Finished. Copy the files from the "out" folder into the game folder.
pause
