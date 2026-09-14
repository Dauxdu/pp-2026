project(cuda LANGUAGES CXX CUDA)

add_executable(${PROJECT_NAME})
target_sources(${PROJECT_NAME} PRIVATE main.cu)

if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
    set_target_properties(${PROJECT_NAME} PROPERTIES CUDA_ARCHITECTURES "native")
endif()

target_link_libraries(${PROJECT_NAME}
    PRIVATE
    core
)
