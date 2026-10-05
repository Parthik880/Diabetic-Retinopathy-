cmake_minimum_required(VERSION 3.26)
project(RetinaGram VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Core Gui Widgets)
add_library(RetinaGramPaths STATIC src/core/AppPaths.cpp)
target_include_directories(RetinaGramPaths PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src/include")
target_link_libraries(RetinaGramPaths PUBLIC Qt6::Core)
find_package(Torch REQUIRED)
find_package(CUDAToolkit REQUIRED)

set(ONNXRUNTIME_ROOT "" CACHE PATH "Root of the ONNX Runtime native SDK")
find_path(ONNXRUNTIME_INCLUDE_DIR onnxruntime_cxx_api.h
  HINTS "${ONNXRUNTIME_ROOT}/include" "${ONNXRUNTIME_ROOT}/build/native/include"
        "${ONNXRUNTIME_ROOT}/buildTransitive/native/include")
find_library(ONNXRUNTIME_LIBRARY NAMES onnxruntime
  HINTS "${ONNXRUNTIME_ROOT}/lib" "${ONNXRUNTIME_ROOT}/runtimes/win-x64/native")
if(NOT ONNXRUNTIME_INCLUDE_DIR OR NOT ONNXRUNTIME_LIBRARY)
  message(FATAL_ERROR "ONNX Runtime C++ SDK was not found. Set ONNXRUNTIME_ROOT to its extracted root.")
endif()

set(RETINAGRAM_INFERENCE_SOURCES
  src/inference/ModelManager.cpp src/inference/ModelConfig.cpp
  src/inference/ModelFactory.cpp src/inference/Preprocessing.cpp
  src/inference/ResultSerialization.cpp
  src/inference/stages/RuntimeSupport.cpp src/inference/stages/OnnxModels.cpp
  src/inference/stages/TorchScriptGradingModel.cpp
  src/inference/stages/TorchScriptLesionModel.cpp
  src/inference/stages/LesionPostprocessor.cpp)
add_library(RetinaGramInference STATIC ${RETINAGRAM_INFERENCE_SOURCES})
target_include_directories(RetinaGramInference PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src/include" PRIVATE "${ONNXRUNTIME_INCLUDE_DIR}")
target_link_libraries(RetinaGramInference PUBLIC RetinaGramPaths Qt6::Core Qt6::Gui
  PRIVATE "${ONNXRUNTIME_LIBRARY}" ${TORCH_LIBRARIES} CUDA::cudart)
if(MSVC)
  target_compile_options(RetinaGramInference PRIVATE /W4 /permissive- /utf-8)
endif()

add_executable(RetinaGram WIN32
  src/main.cpp
  src/app/AnalysisController.cpp
  src/image/ImageDecoder.cpp
  src/reporting/ScreeningReport.cpp
  src/reporting/ReportBundle.cpp
  src/ui/ReportPage.cpp
  src/ui/MainWindow.cpp
  src/ui/AnalysisPage.cpp
  src/ui/BatchPage.cpp
  src/app/BatchDiscovery.cpp
  src/include/app/AnalysisController.h
  src/include/image/ImageDecoder.h
  src/include/image/EyeAssignment.h
  src/include/ui/MainWindow.h
  src/include/inference/ModelManager.h)
target_include_directories(RetinaGram PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/include" "${ONNXRUNTIME_INCLUDE_DIR}")
target_link_libraries(RetinaGram PRIVATE Qt6::Core Qt6::Gui Qt6::Widgets
  RetinaGramInference CUDA::cudart)
# Qt's `slots` keyword macro collides with identifiers in LibTorch headers.
set_source_files_properties(${RETINAGRAM_INFERENCE_SOURCES}
  PROPERTIES COMPILE_DEFINITIONS QT_NO_KEYWORDS)
if(MSVC)
  target_compile_options(RetinaGram PRIVATE /W4 /permissive- /utf-8)
endif()
if(WIN32)
  target_link_libraries(RetinaGram PRIVATE psapi ole32 windowscodecs)
endif()

# AppPaths dynamically discovers source/package roots using runtime markers.
# No source directory is embedded in runtime resource lookup.
set_target_properties(RetinaGram PROPERTIES OUTPUT_NAME "RetinaGram")

option(RETINAGRAM_BUILD_UI_TESTS "Build the isolated Qt UI regression runner" OFF)
if(RETINAGRAM_BUILD_UI_TESTS)
  find_package(Qt6 REQUIRED COMPONENTS Test)
  add_executable(RetinaGramUiSmoke
    tests/UiRegression.cpp src/reporting/ScreeningReport.cpp src/ui/ReportPage.cpp src/ui/MainWindow.cpp src/ui/AnalysisPage.cpp src/ui/BatchPage.cpp src/app/BatchDiscovery.cpp src/image/ImageDecoder.cpp
    src/include/ui/MainWindow.h)
  target_include_directories(RetinaGramUiSmoke PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/include")
  target_link_libraries(RetinaGramUiSmoke PRIVATE RetinaGramPaths Qt6::Widgets Qt6::Test ole32 windowscodecs)
  if(MSVC)
    target_compile_options(RetinaGramUiSmoke PRIVATE /utf-8)
  endif()
  add_executable(RetinaGramFunctionalSmoke tests/FunctionalSmoke.cpp
    src/reporting/ScreeningReport.cpp src/reporting/ReportBundle.cpp src/ui/ReportPage.cpp src/ui/MainWindow.cpp src/ui/AnalysisPage.cpp src/ui/BatchPage.cpp
    src/app/BatchDiscovery.cpp src/app/AnalysisController.cpp src/image/ImageDecoder.cpp
    src/include/ui/MainWindow.h src/include/app/AnalysisController.h)
  target_include_directories(RetinaGramFunctionalSmoke PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/include" "${ONNXRUNTIME_INCLUDE_DIR}")
  target_link_libraries(RetinaGramFunctionalSmoke PRIVATE RetinaGramPaths Qt6::Widgets Qt6::Test
    RetinaGramInference CUDA::cudart psapi ole32 windowscodecs)
  if(MSVC)
    target_compile_options(RetinaGramFunctionalSmoke PRIVATE /utf-8)
  endif()
  add_executable(RetinaGramReportBundleTests tests/ReportBundleTests.cpp
    src/reporting/ReportBundle.cpp src/reporting/ScreeningReport.cpp src/image/ImageDecoder.cpp)
  target_include_directories(RetinaGramReportBundleTests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/include")
  target_link_libraries(RetinaGramReportBundleTests PRIVATE RetinaGramPaths Qt6::Widgets Qt6::Test ole32 windowscodecs)
  if(MSVC)
    target_compile_options(RetinaGramReportBundleTests PRIVATE /utf-8)
  endif()
endif()

option(RETINAGRAM_BUILD_INFERENCE_TESTS "Build configuration and typed pipeline tests" OFF)
if(RETINAGRAM_BUILD_INFERENCE_TESTS)
  enable_testing()
  find_package(Qt6 REQUIRED COMPONENTS Test)
  add_executable(RetinaGramInferenceTests tests/InferenceTests.cpp src/image/ImageDecoder.cpp)
  target_link_libraries(RetinaGramInferenceTests PRIVATE RetinaGramInference Qt6::Test ole32 windowscodecs)
  if(MSVC)
    target_compile_options(RetinaGramInferenceTests PRIVATE /utf-8)
  endif()
  add_test(NAME RetinaGramInferenceTests COMMAND RetinaGramInferenceTests)
endif()
