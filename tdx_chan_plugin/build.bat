@echo off
REM 构建通达信缠论插件DLL
REM 使用Visual Studio 2022 (Community或BuildTools)

setlocal

REM 尝试多个可能的VS路径
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" (
    call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x86
) else if exist "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" (
    call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x86
) else if exist "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat" (
    call "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat" x86
) else (
    echo Error: Visual Studio 2022 not found.
    exit /b 1
)

if errorlevel 1 (
    echo Failed to set up Visual Studio environment
    exit /b 1
)

where cl >nul 2>&1
if errorlevel 1 (
    echo cl.exe not found in PATH
    exit /b 1
)

echo Compiler: cl.exe ready

REM 编译选项
REM /EHsc - 启用C++异常处理
REM /W3 - 警告级别3
REM /O2 - 最大优化
REM /MT - 静态链接运行时库 (不依赖MSVCP140.DLL等)
REM /utf-8 - UTF-8编码
set CXX_FLAGS=/nologo /EHsc /W3 /O2 /MT /utf-8 /D "NDEBUG" /D "WIN32" /D "_WINDOWS" /D "_CRT_SECURE_NO_WARNINGS" /D "NOMINMAX" /D "WIN32_LEAN_AND_MEAN"

REM 链接选项
set LINK_FLAGS=/nologo /DLL /MACHINE:X86 /OPT:REF /OPT:ICF

REM 输出目录
set OUT_DIR=build
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo.
echo ========================================
echo Building TDX Chan Plugin (32-bit DLL)
echo ========================================
echo.

echo [1/3] Compiling ChanAnalyzer.cpp...
cl %CXX_FLAGS% /c ChanAnalyzer.cpp /Fo"%OUT_DIR%\ChanAnalyzer.obj"
if errorlevel 1 (
    echo ERROR: Failed to compile ChanAnalyzer.cpp
    exit /b 1
)

echo [2/3] Compiling TDXPlugin.cpp...
cl %CXX_FLAGS% /c TDXPlugin.cpp /Fo"%OUT_DIR%\TDXPlugin.obj"
if errorlevel 1 (
    echo ERROR: Failed to compile TDXPlugin.cpp
    exit /b 1
)

echo [3/3] Linking TDXChanPlugin.dll...
link %LINK_FLAGS% ^
    "%OUT_DIR%\ChanAnalyzer.obj" ^
    "%OUT_DIR%\TDXPlugin.obj" ^
    gdi32.lib user32.lib ^
    /OUT:"%OUT_DIR%\TDXChanPlugin.dll" ^
    /IMPLIB:"%OUT_DIR%\TDXChanPlugin.lib" ^
    /PDB:"%OUT_DIR%\TDXChanPlugin.pdb" ^
    /DEF:TDXChanPlugin.def

if errorlevel 1 (
    echo ERROR: Failed to link DLL
    exit /b 1
)

echo.
echo ========================================
echo Build Success!
echo ========================================
echo Output: %OUT_DIR%\TDXChanPlugin.dll
echo Architecture: 32-bit (x86)
echo CRT: Static (/MT) - no external runtime dependencies
echo.

REM 清理中间文件
echo Cleaning up...
del /q "%OUT_DIR%\*.obj" 2>nul
del /q "%OUT_DIR%\*.exp" 2>nul

echo Done.
endlocal