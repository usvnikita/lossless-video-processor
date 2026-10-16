@echo off
cd /d "%~dp0"
setlocal EnableDelayedExpansion
title Ultimate Video Factory

:main_menu
cls
echo =======================================================
echo               ULTIMATE VIDEO FACTORY
echo =======================================================
echo.
echo [1] FULL PIPELINE (Heavy Smart Cut and Extras)
echo [2] PREPARE EXTRAS (1-Click Auto-mode for edited videos)
echo [3] VIDEO UTILITIES (Custom tool combinations)
echo.
echo Type 'b' at any prompt to return to this menu.
echo.
set /p MAIN_CHOICE="Select [1, 2 or 3]: "
if /I "!MAIN_CHOICE!"=="b" goto main_menu
if "!MAIN_CHOICE!"=="1" goto setup_full
if "!MAIN_CHOICE!"=="2" goto setup_extras
if "!MAIN_CHOICE!"=="3" goto setup_utils
goto main_menu

:setup_utils
cls
echo =======================================================
echo                  VIDEO UTILITIES
echo =======================================================
echo.
echo [1] Trim Start/End of video (Lossless)
echo [2] Split video exactly in half (Lossless)
echo [3] Smart Cut (Motion Speed, Area, White UI)
echo [4] Generate Images (Screenlists and Screenshots)
echo [5] Generate Hyperlapse Preview
echo [6] Rename files by Mask
echo [7] Wipe metadata from videos (In-place)
echo [-] Add vertical cuts? (Coming soon)
echo.
echo Enter numbers together to run multiple tools (e.g. 145)
echo.
set /p UTIL_CHOICE="Your choice: "
if /I "!UTIL_CHOICE!"=="b" goto main_menu
if "!UTIL_CHOICE!"=="-" (
    echo.
    echo [i] This feature is currently in development!
    timeout /t 2 >nul
    goto setup_utils
)
if "!UTIL_CHOICE!"=="" set UTIL_CHOICE=4

:: Сброс флагов (каждая команда строго на своей строке для безопасности)
set DO_TRIM=0
set DO_SPLIT=0
set DO_CUT=0
set DO_IMG=0
set DO_PREV=0
set DO_RENAME=0
set DO_WIPE=0

if not "!UTIL_CHOICE!"=="" (
    echo !UTIL_CHOICE! | findstr "1" >nul && set DO_TRIM=1
    echo !UTIL_CHOICE! | findstr "2" >nul && set DO_SPLIT=1
    echo !UTIL_CHOICE! | findstr "3" >nul && set DO_CUT=1
    echo !UTIL_CHOICE! | findstr "4" >nul && set DO_IMG=1
    echo !UTIL_CHOICE! | findstr "5" >nul && set DO_PREV=1
    echo !UTIL_CHOICE! | findstr "6" >nul && set DO_RENAME=1
    echo !UTIL_CHOICE! | findstr "7" >nul && set DO_WIPE=1
)

echo.
if !DO_TRIM!==1 (
    echo --- TRIM SETTINGS ---
    set /p TRIM_START="Cut from START in seconds (0=Off) [default 0]: "
    if /I "!TRIM_START!"=="b" goto main_menu
    if "!TRIM_START!"=="" set TRIM_START=0
    
    set /p TRIM_END="Cut from END in seconds (0=Off) [default 0]: "
    if /I "!TRIM_END!"=="b" goto main_menu
    if "!TRIM_END!"=="" set TRIM_END=0
    echo.
)
if !DO_CUT!==1 (
    echo --- CUT SETTINGS ---
    set /p SENS="Motion SPEED sensitivity (0-100, 0=Off) [default 30]: "
    if /I "!SENS!"=="b" goto main_menu
    if "!SENS!"=="" set SENS=30
    
    set /p AREA_LIMIT="Active AREA threshold %% (0-100, 0=Off) [default 5]: "
    if /I "!AREA_LIMIT!"=="b" goto main_menu
    if "!AREA_LIMIT!"=="" set AREA_LIMIT=5
    
    set /p UI_LIMIT="WHITE UI threshold %% (0-100, 0=Off) [default 50]: "
    if /I "!UI_LIMIT!"=="b" goto main_menu
    if "!UI_LIMIT!"=="" set UI_LIMIT=50
    
    set /p SIZE_LIMIT="Max Size in GB (0=No limit) [default 0]: "
    if /I "!SIZE_LIMIT!"=="b" goto main_menu
    if "!SIZE_LIMIT!"=="" set SIZE_LIMIT=0
    echo.
)
if !DO_IMG!==1 (
    echo --- IMAGE SETTINGS ---
    set /p GRID_COUNT="Screenlist count (e.g. 16, 25) [default 16]: "
    if /I "!GRID_COUNT!"=="b" goto main_menu
    if "!GRID_COUNT!"=="" set GRID_COUNT=16
    
    set /p SCREENS_COUNT="Random screenshots count [default 2]: "
    if /I "!SCREENS_COUNT!"=="b" goto main_menu
    if "!SCREENS_COUNT!"=="" set SCREENS_COUNT=2
    
    set /p BLUR_AMT="Blur intensity (0=Clean only, 180=Extreme) [default 180]: "
    if /I "!BLUR_AMT!"=="b" goto main_menu
    if "!BLUR_AMT!"=="" set BLUR_AMT=180
    echo.
)
if !DO_PREV!==1 (
    echo --- PREVIEW SETTINGS ---
    set /p PREV_SEC="Preview duration in sec [default 5]: "
    if /I "!PREV_SEC!"=="b" goto main_menu
    if "!PREV_SEC!"=="" set PREV_SEC=5
    echo.
)
if !DO_RENAME!==1 (
    echo --- MASK RENAMING ---
    echo Format: [ID]_[Genre]_[Resolution]_[FPS]_[Models]_[Duration].mp4
    set /p GENRE="Enter Genre (e.g. face, body): "
    if /I "!GENRE!"=="b" goto main_menu
    if "!GENRE!"=="" set GENRE=video
    
    set /p MODELS="Enter Models count (e.g. 1m, 2m): "
    if /I "!MODELS!"=="b" goto main_menu
    if "!MODELS!"=="" set MODELS=1m
    echo.
)
goto target_setup


:setup_extras
cls
echo =======================================================
echo     PREPARE EXTRAS (1-Click Auto-mode)
echo =======================================================
echo Using your presets: Split 1.9GB, Prev 5s, Grid 16, Screens 1, Blur 180.
echo.

set DO_TRIM=0
set DO_SPLIT=0
set DO_CUT=0
set DO_IMG=1
set DO_PREV=1
set DO_WIPE=0

set TRIM_START=0
set TRIM_END=0
set SENS=0
set AREA_LIMIT=0
set UI_LIMIT=0

set SIZE_LIMIT=1.9
set PREV_SEC=5
set GRID_COUNT=16
set SCREENS_COUNT=1
set BLUR_AMT=180

set USE_MASK=n
set DO_RENAME=0
set GENRE=none
set MODELS=none

goto target_setup


:setup_full
cls
echo =======================================================
echo          FULL PIPELINE (All-in-one setup)
echo =======================================================
echo Type 'b' at any prompt to return to Main Menu.
echo.

set DO_TRIM=0
set DO_SPLIT=0
set DO_CUT=1
set DO_IMG=1
set DO_PREV=1
set DO_WIPE=0
set TRIM_START=0
set TRIM_END=0

set /p SENS="[1] Motion SPEED sensitivity (0-100) [default 30]: "
if /I "!SENS!"=="b" goto main_menu
if "!SENS!"=="" set SENS=30

set /p AREA_LIMIT="[2] Active AREA threshold %% (0-100) [default 5]: "
if /I "!AREA_LIMIT!"=="b" goto main_menu
if "!AREA_LIMIT!"=="" set AREA_LIMIT=5

set /p UI_LIMIT="[3] WHITE UI threshold %% (0-100) [default 50]: "
if /I "!UI_LIMIT!"=="b" goto main_menu
if "!UI_LIMIT!"=="" set UI_LIMIT=50

set /p SIZE_LIMIT="[4] Max Output Size in GB (0=No limit) [default 0]: "
if /I "!SIZE_LIMIT!"=="b" goto main_menu
if "!SIZE_LIMIT!"=="" set SIZE_LIMIT=0

set /p PREV_SEC="[5] Preview Duration in sec (0=Off) [default 10]: "
if /I "!PREV_SEC!"=="b" goto main_menu
if "!PREV_SEC!"=="" set PREV_SEC=10
if "!PREV_SEC!"=="0" set DO_PREV=0

set /p GRID_COUNT="[6] Screenlist grid count (0=Off) [default 16]: "
if /I "!GRID_COUNT!"=="b" goto main_menu
if "!GRID_COUNT!"=="" set GRID_COUNT=16

set /p SCREENS_COUNT="[7] Random screenshots count (0=Off) [default 2]: "
if /I "!SCREENS_COUNT!"=="b" goto main_menu
if "!SCREENS_COUNT!"=="" set SCREENS_COUNT=2
if "!GRID_COUNT!"=="0" if "!SCREENS_COUNT!"=="0" set DO_IMG=0

set /p BLUR_AMT="[8] Blur for Images (0=Clean only, 180=Extreme) [default 180]: "
if /I "!BLUR_AMT!"=="b" goto main_menu
if "!BLUR_AMT!"=="" set BLUR_AMT=180

:naming_setup
echo.
echo --- OUTPUT NAMING ---
echo Format: [ID]_[Genre]_[Resolution]_[FPS]_[Models]_[Duration].mp4
set /p USE_MASK="Enable Mask renaming? (y/n) [default n]: "
if /I "!USE_MASK!"=="b" goto main_menu
if /I "!USE_MASK!"=="y" (
    set /p GENRE="  Enter Genre (e.g. face, body): "
    if /I "!GENRE!"=="b" goto main_menu
    if "!GENRE!"=="" set GENRE=video
    set /p MODELS="  Enter Models count (e.g. 1m, 2m): "
    if /I "!MODELS!"=="b" goto main_menu
    if "!MODELS!"=="" set MODELS=1m
    set DO_RENAME=1
) else (
    set DO_RENAME=0
    set GENRE=none
    set MODELS=none
)

:target_setup
echo.
echo =======================================================
echo Select target:
echo   1 - Single video
echo   2 - Batch (all videos in folder)
set /p MODE_NUM="Choose 1 or 2: "
if /I "!MODE_NUM!"=="b" goto main_menu
if "!MODE_NUM!"=="1" (set MODE=single) else (set MODE=batch)

echo.
if "!MODE!"=="single" (
    set /p TARGET="Drag and drop video here or paste path: "
) else (
    set /p TARGET="Drag and drop FOLDER here (or press ENTER for current): "
)
if /I "!TARGET!"=="b" goto main_menu

:: Очистка пути (удаляем кавычки и висячие слеши)
if "!TARGET!"=="" set TARGET=!CD!
set TARGET=!TARGET:"=!
if "!TARGET:~-1!"=="\" set TARGET=!TARGET:~0,-1!

echo.
echo Working... Please wait.
echo.

py lossless_cutter.py --do_trim !DO_TRIM! --t_start !TRIM_START! --t_end !TRIM_END! --do_split !DO_SPLIT! --do_cut !DO_CUT! --sens !SENS! --area !AREA_LIMIT! --ui !UI_LIMIT! --size !SIZE_LIMIT! --do_img !DO_IMG! --grid !GRID_COUNT! --screens !SCREENS_COUNT! --blur !BLUR_AMT! --do_prev !DO_PREV! --prev !PREV_SEC! --do_rename !DO_RENAME! --genre "!GENRE!" --models "!MODELS!" --do_wipe !DO_WIPE! --mode "!MODE!" --target "!TARGET!"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Скрипт завершился с ошибкой. Проверьте логи выше.
)
echo.
echo =======================================================
echo                     ALL DONE!
echo =======================================================
echo.
echo [1] Process another video/folder
echo [2] Exit program
set /p END_CHOICE="Select: "
if "!END_CHOICE!"=="2" exit
goto main_menu
