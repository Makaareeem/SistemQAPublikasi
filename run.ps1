if ($env:QA_PYTHON) {
    $pythonExe = $env:QA_PYTHON
} elseif ($env:CONDA_PREFIX -or $env:VIRTUAL_ENV) {
    $pythonExe = "python"
} elseif (Test-Path -LiteralPath "D:/Laptop/Anaconda/envs/rag-sistem/python.exe") {
    # Compatibility with the existing workstation; deployments use QA_PYTHON or an active environment.
    $pythonExe = "D:/Laptop/Anaconda/envs/rag-sistem/python.exe"
} else {
    $pythonExe = "python"
}
& $pythonExe @args
exit $LASTEXITCODE
