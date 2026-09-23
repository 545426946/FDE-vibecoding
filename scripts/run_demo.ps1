$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path "config.yaml")) {
    Copy-Item "config.example.yaml" "config.yaml"
}

py -3.12 -m pip install -r requirements.txt
docker compose up -d --wait --pull never
docker start mx-ymatrix 2>$null
docker exec mx-ymatrix bash /opt/start_ymatrix.sh

py -3.12 -m src.cli run-all --config config.yaml --results-dir results/pass
if ($LASTEXITCODE -ne 0) { throw "正常迁移校验未通过" }

py -3.12 -m src.cli inject-mismatch --config config.yaml --results-dir results/mismatch
py -3.12 -m src.cli validate --config config.yaml --results-dir results/mismatch
if ($LASTEXITCODE -eq 0) { throw "脏数据场景应当校验失败" }

py -3.12 -m src.cli demo-conn-fail --config config.yaml --port 1 --results-dir results/conn-fail

Write-Host "Demo 完成。正常结果在 results/pass，脏数据结果在 results/mismatch"
