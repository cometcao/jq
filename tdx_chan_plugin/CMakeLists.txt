# CMakeLists.txt for TDX Chan Plugin
# 通达信缠论插件构建配置
# 通达信是32位应用，需要编译为32位DLL

cmake_minimum_required(VERSION 3.10)
project(TDXChanPlugin VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 设置输出目录
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

# Windows特定设置
if(WIN32)
    # 定义NOMINMAX防止min/max宏冲突
    add_definitions(-DNOMINMAX -DWIN32_LEAN_AND_MEAN)
    
    # 禁用一些警告
    add_compile_options(/wd4251 /wd4275 /wd4996)
    
    # 设置静态链接（减少运行时依赖）
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

# 头文件目录
include_directories(${CMAKE_CURRENT_SOURCE_DIR})

# 源文件
set(SOURCES
    ChanPlugin.h
    ChanAnalyzer.cpp
    TDXPlugin.cpp
)

# 创建DLL目标
add_library(TDXChanPlugin SHARED ${SOURCES})

# Windows链接库
if(WIN32)
    target_link_libraries(TDXChanPlugin
        gdi32
        user32
    )
    
    # 设置DLL输出名称
    set_target_properties(TDXChanPlugin PROPERTIES
        OUTPUT_NAME "TDXChanPlugin"
        PREFIX ""
        SUFFIX ".dll"
    )
    
    # 添加版本信息资源文件
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/version.rc")
        target_sources(TDXChanPlugin PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/version.rc")
    endif()
endif()

# 安装规则
install(TARGETS TDXChanPlugin
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)

# 可选：创建测试可执行文件（仅用于测试算法）
option(BUILD_TEST "Build test executable" OFF)
if(BUILD_TEST)
    add_executable(chan_test test_main.cpp)
    # 测试程序不需要是DLL，链接静态库即可
    target_link_libraries(chan_test 
        # 由于是SHARED库，直接链接DLL的import lib
        TDXChanPlugin
    )
endif()
