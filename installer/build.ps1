$ErrorActionPreference = "Stop"
$root  = Split-Path $PSScriptRoot -Parent
$build = Join-Path $root "build"
$stage = Join-Path $build "stage"
$py    = Join-Path $stage "python"
$app   = Join-Path $stage "app"
$ver   = (python -c "import platform; print(platform.python_version())").Trim()
$zip   = Join-Path $build "python-$ver-embed-amd64.zip"

New-Item -ItemType Directory -Force $build | Out-Null
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
if (-not (Test-Path $zip)) {
    Invoke-WebRequest "https://www.python.org/ftp/python/$ver/python-$ver-embed-amd64.zip" -OutFile $zip
}
Expand-Archive $zip $py

$pth = Get-ChildItem $py -Filter "python*._pth" | Select-Object -First 1
Set-Content $pth.FullName -Encoding ascii -Value @("$($pth.BaseName).zip", ".", "Lib\site-packages", "..\app", "import site")

python -m pip install --target "$py\Lib\site-packages" --only-binary=:all: --no-binary=proxy_tools --no-compile -r "$root\requirements.txt" -r "$root\requirements-desktop.txt"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

New-Item -ItemType Directory -Force $app | Out-Null
foreach ($item in "desktop", "hydrohomie", "monitor", "static", "templates") {
    robocopy "$root\$item" "$app\$item" /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
}
Copy-Item "$root\manage.py", "$root\serve.py" $app

$env:SECRET_KEY = "build-only-key"
$env:HYDROHOMIE_DATA_DIR = Join-Path $build "tmpdata"
New-Item -ItemType Directory -Force $env:HYDROHOMIE_DATA_DIR | Out-Null
& "$py\python.exe" "$app\manage.py" collectstatic --noinput
if ($LASTEXITCODE -ne 0) { throw "collectstatic failed" }
Remove-Item Env:SECRET_KEY, Env:HYDROHOMIE_DATA_DIR

& "$py\python.exe" -m compileall -q $app "$py\Lib\site-packages" | Out-Null
Write-Host "Runtime ready in $stage"