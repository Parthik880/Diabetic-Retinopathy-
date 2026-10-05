param(
    [string]$Executable = (Join-Path $PSScriptRoot '..\build\ninja\RetinaGram.exe'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\build\validation\model-modularity')
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$checkpoints = Join-Path $project 'src\checkpoints'
$configuration = Get-Content -LiteralPath (Join-Path $project 'config\models.json') -Raw | ConvertFrom-Json
$name = 'grade_replacement_test_' + [guid]::NewGuid().ToString('N') + '.pt'
$copy = Join-Path $checkpoints $name
$configFile = Join-Path $OutputDirectory 'replacement-config.json'
$hashBefore = (Get-FileHash -LiteralPath $Executable).Hash
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
try {
    Copy-Item -LiteralPath (Join-Path $checkpoints $configuration.grading.model) -Destination $copy
    $configuration.grading.model = $name
    $configuration.checkpoints_directory = $checkpoints # Temporary test-only override.
    [System.IO.File]::WriteAllText($configFile, ($configuration | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
    $infoFile = Join-Path $OutputDirectory 'replacement-info.txt'
    $process = Start-Process -FilePath $Executable -ArgumentList @('--model-info','--model-config',('"'+$configFile+'"')) -WorkingDirectory $project -WindowStyle Hidden -RedirectStandardOutput $infoFile -RedirectStandardError (Join-Path $OutputDirectory 'replacement-info.err') -PassThru -Wait
    if ($process.ExitCode -ne 0 -or -not (Get-Content -LiteralPath $infoFile -Raw).Contains($name)) { throw 'Replacement config did not select the renamed artifact.' }
    $process = Start-Process -FilePath $Executable -ArgumentList @('--validate-models','--model-config',('"'+$configFile+'"')) -WorkingDirectory $project -WindowStyle Hidden -RedirectStandardOutput (Join-Path $OutputDirectory 'replacement-validation.txt') -RedirectStandardError (Join-Path $OutputDirectory 'replacement-validation.err') -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw 'Renamed compatible model failed validation.' }
    if ($hashBefore -ne (Get-FileHash -LiteralPath $Executable).Hash) { throw 'Executable changed during the replacement test.' }
    'Renamed compatible grading model initialized successfully; executable SHA256 unchanged.'
} finally {
    if (Test-Path -LiteralPath $copy) { Remove-Item -LiteralPath $copy }
}
