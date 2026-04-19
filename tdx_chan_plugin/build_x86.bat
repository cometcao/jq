@echo off
setlocal

echo Building 32-bit TDXChanPlugin.dll with Visual Studio...
echo Using TDXPlugin_FinalMatch.cpp for correct export order...

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

REM 编译选项 - 使用静态链接运行时库 (/MT)
set CFLAGS=/nologo /EHsc /c /W3 /O2 /D WIN32 /D _WINDOWS /D TDXCHAN_EXPORTS /D _CRT_SECURE_NO_WARNINGS /MT
set LDFLAGS=/nologo /DLL /SUBSYSTEM:WINDOWS /MACHINE:X86 /OPT:REF /DEF:TDXChanPlugin_FinalMatch.def

echo Compiling ChanAnalyzer.cpp...
cl %CFLAGS% ChanAnalyzer.cpp /FoChanAnalyzer.obj
if errorlevel 1 (
    echo Failed to compile ChanAnalyzer.cpp
    pause
    exit /b 1
)

echo Compiling TDXPlugin_FinalMatch.cpp...
cl %CFLAGS% TDXPlugin_FinalMatch.cpp /FoTDXPlugin_FinalMatch.obj
if errorlevel 1 (
    echo Failed to compile TDXPlugin_FinalMatch.cpp
    pause
    exit /b 1
)

echo Linking DLL with DEF file...
link %LDFLAGS% ^
    ChanAnalyzer.obj ^
    TDXPlugin_FinalMatch.obj ^
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
    echo Checking exports...
    dumpbin /exports TDXChanPlugin32.dll | findstr "Plugin2 CalcN RegisterTdxFunc"
) else (
    echo DLL file not created!
    pause
    exit /b 1
)

echo.
echo Build completed successfully!
echo Copy TDXChanPlugin32.dll to TDX\dlls\ directory

endlocal