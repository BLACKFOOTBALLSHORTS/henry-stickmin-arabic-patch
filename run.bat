@echo off
color 0B
echo ====================================================
echo    Henry Stickmin - Font Test
echo ====================================================
echo.

python make_labels.py --sheet labels.txt --ref original_assets --font DINNextLTArabic-Bold.ttf --out arabic_assets
echo.
pause