cmake_minimum_required(VERSION 3.20)
project (TDXChanPlugin)
set (TDXChanPlugin_VERSION_MAJOR 1)
set (TDXChanPlugin_VERSION_MINOR 0)

# 明确列出源文件，避免包含Main_Simple.cpp
set(SRCS
    ChanAnalyzer.cpp
    Main.cpp
)

add_library(TDXChanPlugin SHARED ${SRCS})
