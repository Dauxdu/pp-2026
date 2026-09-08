project(openmp LANGUAGES CXX)

find_package(OpenMP REQUIRED)

add_executable(${PROJECT_NAME})
target_sources(${PROJECT_NAME} PRIVATE main.cpp)

target_link_libraries(${PROJECT_NAME}
    PRIVATE
    core
    OpenMP::OpenMP_CXX
)
