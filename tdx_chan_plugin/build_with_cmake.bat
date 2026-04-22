@echo off
setlocal

REM 切换到脚本所在目录
cd /d "%~dp0"
set ROOT_DIR=%cd%

echo Building TDXChanPlugin.dll with CMake...
echo Using CMake build system...

REM 清理旧的构建目录
if exist build (
    echo Removing old build directory...
    rmdir /s /q build
)

REM 清理根目录下可能残留的构建输出
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

REM 创建构建目录
mkdir build
cd build

REM 运行CMake配置（Win32平台）
echo Configuring with CMake...
cmake -A Win32 "%ROOT_DIR%"
if errorlevel 1 (
    echo CMake configuration failed
    pause
    exit /b 1
)

REM 构建项目（Release配置）
echo Building with CMake...
cmake --build . --config Release
if errorlevel 1 (
    echo CMake build failed
    pause
    exit /b 1
)

REM DLL 可能在 build/Release 或 %ROOT_DIR%/Release 下
set DLL_FOUND=0
if exist "%ROOT_DIR%\build\Release\TDXChanPlugin.dll" (
    set DLL_FOUND=1
    echo DLL found in build\Release\ directory
    copy /y "%ROOT_DIR%\build\Release\TDXChanPlugin.dll" "%ROOT_DIR%\TDXChanPlugin32.dll"
)
if exist "%ROOT_DIR%\Release\TDXChanPlugin.dll" (
    set DLL_FOUND=1
    echo DLL found in root Release\ directory
    copy /y "%ROOT_DIR%\Release\TDXChanPlugin.dll" "%ROOT_DIR%\TDXChanPlugin32.dll"
    rmdir /s /q "%ROOT_DIR%\Release"
)

if %DLL_FOUND%==1 (
    echo.
    echo Checking file size...
    for %%i in ("%ROOT_DIR%\TDXChanPlugin32.dll") do echo   %%~zi bytes
    
    echo.
    echo Checking exports...
    "%ROOT_DIR%\build\Release\TDXChanPlugin.dll" 2>nul || "%ROOT_DIR%\TDXChanPlugin32.dll" 2>nul
    dumpbin /exports "%ROOT_DIR%\TDXChanPlugin32.dll" 2>nul | findstr "RegisterTdxFunc\|Func[1-9]"
    
    echo.
    echo ============================================================
    echo Build completed successfully!
    echo Output DLL: %ROOT_DIR%\TDXChanPlugin32.dll
    echo.
    echo In TDX formula use:
    echo   TDXDLL1(1,H,L,0) for Func1 (简笔端点)
    echo   TDXDLL1(2,H,L,0) for Func2 (标准笔端点 - ChanAnalyzer)
    echo   TDXDLL1(3,BI_ARRAY,H,L) for Func3 (段端点-标准画法)
    echo   TDXDLL1(4,BI_ARRAY,H,L) for Func4 (段端点-1+1终结)
    echo   TDXDLL1(5,H,L,0) for Func5 (线段端点 - ChanAnalyzer)
    echo ============================================================
) else (
    echo DLL file not found!
    echo Checking for output files...
    dir /s "%ROOT_DIR%\TDXChanPlugin*.dll" 2>nul
    pause
    exit /b 1
)

endlocal
