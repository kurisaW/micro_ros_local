include(CMakeForceCompiler)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR cortex-m4)

set(CMAKE_CROSSCOMPILING 1)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

if(WIN32)
    set(TARGET "D:/toolschain/gcc-arm-none-eabi-10-2020-q4-major-win32/bin/")
    set(CMAKE_C_COMPILER "${TARGET}arm-none-eabi-gcc.exe")
    set(CMAKE_CXX_COMPILER "${TARGET}arm-none-eabi-g++.exe")
    set(CMAKE_AR "${TARGET}arm-none-eabi-ar.exe")
else()
    set(CMAKE_C_COMPILER "arm-none-eabi-gcc")
    set(CMAKE_CXX_COMPILER "arm-none-eabi-g++")
    set(CMAKE_AR "arm-none-eabi-ar")
endif()


set(CMAKE_C_FLAGS_INIT " -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -ffunction-sections -fdata-sections -Dgcc -Wall -O0 -gdwarf-2 -g")
set(CMAKE_CXX_FLAGS_INIT " -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -ffunction-sections -fdata-sections -Dgcc -Wall -O0 -gdwarf-2 -g")

get_filename_component(script_path "${CMAKE_CURRENT_LIST_FILE}" ABSOLUTE)

message("################################ Toolchain include ######################################")
string(REGEX MATCH "^(.*project)" BSP_ROOT_DIR "${script_path}")
message("BSP_ROOT_DIR Path: ${BSP_ROOT_DIR}")

include_directories(
    ${BSP_ROOT_DIR}/rt-thread/include              # kernel include
    ${BSP_ROOT_DIR}/rt-thread/components/finsh     # finsh include
    ${BSP_ROOT_DIR}/rt-thread/components/net/sal/include                      # #include <netdb.h>
    ${BSP_ROOT_DIR}/rt-thread/components/net/sal/include/socket               
    ${BSP_ROOT_DIR}/rt-thread/components/net/sal/include/socket/sys_socket    # #include <sys/socket.h>
    ${BSP_ROOT_DIR}/rt-thread/components/net/netdev/include
    ${BSP_ROOT_DIR}/rt-thread/components/net/netdev/include/arpa              # #include <arpa/inet.h>
    ${BSP_ROOT_DIR}                                                           # rtconfig.h
)

set(__BIG_ENDIAN__ 0)
