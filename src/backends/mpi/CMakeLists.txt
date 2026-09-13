project(mpi LANGUAGES CXX)

find_package(MPI REQUIRED)

add_executable(${PROJECT_NAME})
target_sources(${PROJECT_NAME} PRIVATE main.cpp)

target_link_libraries(${PROJECT_NAME}
    PRIVATE
    core
    MPI::MPI_CXX
)
