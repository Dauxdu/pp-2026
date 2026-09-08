project(pp-2026-labs LANGUAGES CXX)

find_package(nlohmann_json CONFIG REQUIRED)

add_library(core INTERFACE)
target_include_directories(core INTERFACE ${CMAKE_SOURCE_DIR}/)

target_link_libraries(core
    INTERFACE
    nlohmann_json::nlohmann_json
)

add_subdirectory("backends/seq")
add_subdirectory("backends/openmp")
#add_subdirectory("backends/mpi")
#add_subdirectory("backends/cuda")
