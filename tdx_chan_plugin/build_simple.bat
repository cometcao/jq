@echo off
setlocal enabledelayedexpansion

echo Building TDXChanPlugin.dll with static runtime...

REM 设置Visual Studio环境变量
set VCVARS="C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if not exist %VCVARS% (
    echo Error: vcvarsall.bat not found
    exit /b 1
)

echo Calling vcvarsall.bat...
call %VCVARS% x86

if errorlevel 1 (
    echo Failed to set up Visual Studio environment
    exit /b 1
)

echo Environment set up successfully

REM 检查编译器
where cl >nul 2>&1
if errorlevel 1 (
    echo cl.exe not found in PATH
    exit /b 1
)

echo Compiler found: cl.exe

REM 创建输出目录
set OUT_DIR=..\build_static
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

REM 编译选项 - 使用静态链接运行时库 (/MT)
set CFLAGS=/nologo /EHsc /c /W3 /O2 /D WIN32 /D _WINDOWS /D TDXCHAN_EXPORTS /D _CRT_SECURE_NO_WARNINGS /MT
set LDFLAGS=/nologo /DLL /SUBSYSTEM:WINDOWS /MACHINE:X86 /OPT:REF

echo Compiling ChanAnalyzer.cpp...
cl %CFLAGS% ChanAnalyzer.cpp /Fo"%OUT_DIR%\ChanAnalyzer.obj"
if errorlevel 1 (
    echo Failed to compile ChanAnalyzer.cpp
    exit /b 1
)

echo Compiling TDXPlugin.cpp...
cl %CFLAGS% TDXPlugin.cpp /Fo"%OUT_DIR%\TDXPlugin.obj"
if errorlevel 1 (
    echo Failed to compile TDXPlugin.cpp
    exit /b 1
)

echo Linking DLL...
link %LDFLAGS% ^
    "%OUT_DIR%\ChanAnalyzer.obj" ^
    "%OUT_DIR%\TDXPlugin.obj" ^
    gdi32.lib user32.lib ^
    /OUT:"%OUT_DIR%\TDXChanPlugin.dll" ^
    /IMPLIB:"%OUT_DIR%\TDXChanPlugin.lib"

if errorlevel 1 (
    echo Failed to link DLL
    exit /b 1
)

echo DLL built successfully: %OUT_DIR%\TDXChanPlugin.dll

echo Checking dependencies...
dumpbin /dependents "%OUT_DIR%\TDXChanPlugin.dll" | findstr ".dll"

echo Build completed
endlocal