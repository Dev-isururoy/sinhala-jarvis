$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCommand) { $ollamaExe = $ollamaCommand.Source }
else { $ollamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe' }
if (-not (Test-Path -LiteralPath $ollamaExe)) {
    throw 'Install Ollama for Windows from https://ollama.com/download/windows then rerun this script.'
}
try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' }
catch {
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden
    Start-Sleep -Seconds 4
}
$jarvisConfig = Get-Content -LiteralPath config.json -Raw | ConvertFrom-Json
& $ollamaExe pull $jarvisConfig.model
if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
& '.\.venv\Scripts\python.exe' -c "import json; from faster_whisper import WhisperModel; c=json.load(open('config.json')); WhisperModel(c['whisper_model'], device='cpu', compute_type='int8'); print('Speech model ready')"
if ($LASTEXITCODE -ne 0) { throw 'Speech model download failed.' }
