@echo off
setlocal

REM 切换到脚本所在目录
cd /d "%~dp0"

echo Building 32-bit TDXChanPlugin.dll with Visual Studio...
echo Using Main.cpp as main source file...

REM 设置Visual Studio 2022环境变量
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat"
if errorlevel 1 (
    echo Failed to set up Visual Studio environment
    pause
    exit /b 1
)

REM 清理旧文件
del /q *.obj 2>nul
del /q *.dll 2>nul
del /q *.lib 2>nul

REM 编译选项 - 使用静态链接运行时库 (/MT) 并添加必要的预处理器定义
set CFLAGS=/nologo /EHsc /c /W3 /O2 /D WIN32 /D _WINDOWS /D _CRT_SECURE_NO_WARNINGS /MT /D _CRT_SECURE_NO_DEPRECATE /D _USE_MATH_DEFINES
set LDFLAGS=/nologo /DLL /SUBSYSTEM:WINDOWS /MACHINE:X86 /OPT:REF

echo Compiling Main.cpp...
cl %CFLAGS% Main.cpp /FoMain.obj
if errorlevel 1 (
    echo Failed to compile Main.cpp
    pause
    exit /b 1
)

echo Compiling ChanAnalyzer.cpp...
cl %CFLAGS% ChanAnalyzer.cpp /FoChanAnalyzer.obj
if errorlevel 1 (
    echo Failed to compile ChanAnalyzer.cpp
    pause
    exit /b 1
)

echo Linking DLL...
link %LDFLAGS% ^
    Main.obj ^
    ChanAnalyzer.obj ^
    /OUT:TDXChanPlugin32.dll ^
    /IMPLIB:TDXChanPlugin32.lib

if errorlevel 1 (
    echo Failed to link DLL
    pause
    exit /b 1
)

if exist TDXChanPlugin32.dll (
    echo DLL built successfully: TDXChanPlugin32.dll
    echo File size: 
    for %%i in (TDXChanPlugin32.dll) do echo   %%~zi bytes
    
    echo.
    echo Checking dependencies...
    dumpbin /dependents TDXChanPlugin32.dll | findstr ".dll"
    
    echo.
    echo Checking exports (should see RegisterTdxFunc and Func1-9)...
    dumpbin /exports TDXChanPlugin32.dll | findstr "RegisterTdxFunc\|Func[1-9]"
) else (
    echo DLL file not created!
    pause
    exit /b 1
)

echo.
echo Build completed successfully!
echo Copy TDXChanPlugin32.dll to TDX\dlls\ directory
echo In TDX formula use: TDXDLL1(1,H,L,0) for Func1, TDXDLL1(2,H,L,0) for Func2, etc.

endlocal
