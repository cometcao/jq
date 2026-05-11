@echo off
setlocal

REM Change to script directory
cd /d "%~dp0"
set ROOT_DIR=%cd%

echo Building TDXChanPlugin.dll with CMake...
echo Using CMake build system...

REM Clean old build directory
if exist build (
    echo Removing old build directory...
    rmdir /s /q build
)

REM Clean residual build output in root
if exist "%ROOT_DIR%\Release" rmdir /s /q "%ROOT_DIR%\Release"
if exist "%ROOT_DIR%\Debug" rmdir /s /q "%ROOT_DIR%\Debug"
if exist "%ROOT_DIR%\TDXChanPlugin.dir" rmdir /s /q "%ROOT_DIR%\TDXChanPlugin.dir"
if exist "%ROOT_DIR%\ALL_BUILD.vcxproj" del "%ROOT_DIR%\ALL_BUILD.vcxproj" 2>nul
if exist "%ROOT_DIR%\ZERO_CHECK.vcxproj" del "%ROOT_DIR%\ZERO_CHECK.vcxproj" 2>nul
if exist "%ROOT_DIR%\TDXChanPlugin.vcxproj" del "%ROOT_DIR%\TDXChanPlugin.vcxproj" 2>nul
if exist "%ROOT_DIR%\TDXChanPlugin.sln" del "%ROOT_DIR%\TDXChanPlugin.sln" 2>nul
if exist "%ROOT_DIR%\cmake_install.cmake" del "%ROOT_DIR%\cmake_install.cmake" 2>nul
if exist "%ROOT_DIR%\CMakeCache.txt" del "%ROOT_DIR%\CMakeCache.txt" 2>nul
if exist "%ROOT_DIR%\CMakeFiles" rmdir /s /q "%ROOT_DIR%\CMakeFiles" 2>nul

REM Create build directory
mkdir build
cd build

REM Run CMake configuration (x64 platform)
echo Configuring with CMake...
cmake -A x64 "%ROOT_DIR%"
if errorlevel 1 (
    echo CMake configuration failed
    pause
    exit /b 1
)

REM Build project (Release configuration)
echo Building with CMake...
cmake --build . --config Release
if errorlevel 1 (
    echo CMake build failed
    pause
    exit /b 1
)

REM DLL might be under build/Release or %ROOT_DIR%/Release
set DLL_FOUND=0
if exist "%ROOT_DIR%\build\Release\TDXChanPlugin.dll" (
    set DLL_FOUND=1
    echo DLL found in build\Release\ directory
    copy /y "%ROOT_DIR%\build\Release\TDXChanPlugin.dll" "%ROOT_DIR%\TDXChanPlugin64.dll"
)
if exist "%ROOT_DIR%\Release\TDXChanPlugin.dll" (
    set DLL_FOUND=1
    echo DLL found in root Release\ directory
    copy /y "%ROOT_DIR%\Release\TDXChanPlugin.dll" "%ROOT_DIR%\TDXChanPlugin64.dll"
    rmdir /s /q "%ROOT_DIR%\Release"
)

if %DLL_FOUND%==1 (
    echo.
    echo Checking file size...
    for %%i in ("%ROOT_DIR%\TDXChanPlugin64.dll") do echo   %%~zi bytes
    
    echo.
    echo Checking exports...
    "%ROOT_DIR%\build\Release\TDXChanPlugin.dll" 2>nul || "%ROOT_DIR%\TDXChanPlugin64.dll" 2>nul
    dumpbin /exports "%ROOT_DIR%\TDXChanPlugin64.dll" 2>nul | findstr "RegisterTdxFunc\|Func[1-9]"
    
    echo.
    echo ============================================================
    echo Build completed successfully!
    echo Output DLL: %ROOT_DIR%\TDXChanPlugin64.dll
    echo.
    echo In TDX formula use:
    echo   TDXDLL1(1,H,L,0) for Func1
    echo   TDXDLL1(2,H,L,0) for Func2 - ChanAnalyzer
    echo   TDXDLL1(3,BI_ARRAY,H,L) for Func3
    echo   TDXDLL1(4,BI_ARRAY,H,L) for Func4
    echo   TDXDLL1(5,H,L,0) for Func5 - ChanAnalyzer
    echo ============================================================
) else (
    echo DLL file not found!
    echo Checking for output files...
    dir /s "%ROOT_DIR%\TDXChanPlugin*.dll" 2>nul
    pause
    exit /b 1
)

endlocal
