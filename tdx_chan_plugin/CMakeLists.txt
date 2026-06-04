cmake_minimum_required(VERSION 3.20)
project (TDXChanPlugin)
set (TDXChanPlugin_VERSION_MAJOR 1)
set (TDXChanPlugin_VERSION_MINOR 0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 静态链接 CRT (/MT, /MTd)，避免依赖外部 msvcp140.dll/vcruntime140.dll
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# 明确列出源文件，避免包含Main_Simple.cpp
set(SRCS
    ChanAnalyzer.cpp
    Main.cpp
)

add_library(TDXChanPlugin SHARED ${SRCS})
