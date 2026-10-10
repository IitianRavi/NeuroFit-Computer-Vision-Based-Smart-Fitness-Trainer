$ErrorActionPreference = "Stop"

$appDirectory = Join-Path $PSScriptRoot "Main App"
$venvPython = Join-Path $appDirectory ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment not found at '$venvPython'. Create it with: py -3.12 -m venv `"$appDirectory\.venv`""
}

Push-Location $appDirectory
try {
    & $venvPython -m streamlit run main.py
}
finally {
    Pop-Location
}
