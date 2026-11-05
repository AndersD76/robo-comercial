# Instala o worker de enriquecimento como tarefa agendada do Windows.
#
# Por que agendador e nao um processo fixo: se cair (reboot, erro, falta de
# rede), o agendador simplesmente roda de novo no proximo ciclo. Processo
# fixo precisaria de supervisao propria.
#
# Uso (PowerShell na pasta do projeto; nao precisa ser Administrador):
#   .\scripts\instalar_worker.ps1 -DatabaseUrl 'postgresql://...' `
#       -Indice 'C:\cnpj\indice.sqlite'
#
# Para remover:
#   Unregister-ScheduledTask -TaskName 'TurboVenda-Receita' -Confirm:$false

param(
    [Parameter(Mandatory = $true)][string]$DatabaseUrl,
    [string]$Indice = 'E:\cnpj\indice.sqlite',
    [int]$MinutosIntervalo = 15
)

$ErrorActionPreference = 'Stop'
$projeto = Split-Path -Parent $PSScriptRoot
$script = Join-Path $projeto 'scripts\enriquecer_local.py'
$python = (Get-Command python).Source
$log = Join-Path $projeto 'worker_receita.log'

if (-not (Test-Path $script))  { throw "Nao achei $script" }
if (-not (Test-Path $Indice))  { throw "Indice nao encontrado em $Indice. Gere primeiro com cnpj_ingest.py --sqlite" }

# pythonw: sem console, entao nenhuma janela pisca na tela a cada execucao
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { throw "Nao achei $pythonw (vem junto com o Python oficial)" }

# A senha do banco fica num arquivo so do usuario, nao no comando da tarefa:
# assim nao aparece na listagem de processos nem na definicao da tarefa.
$pasta = Join-Path $env:LOCALAPPDATA 'TurboVenda'
New-Item -ItemType Directory -Force $pasta | Out-Null
$dsnArquivo = Join-Path $pasta 'database_url.txt'
[System.IO.File]::WriteAllText($dsnArquivo, $DatabaseUrl)
icacls $dsnArquivo /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null

$acao = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "`"$script`" --indice `"$Indice`" --dsn-arquivo `"$dsnArquivo`" --log `"$log`"" `
    -WorkingDirectory $projeto

$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $MinutosIntervalo)

# Notebook: o padrao do Windows nao roda tarefa na bateria
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName 'TurboVenda-Receita' -Action $acao `
    -Trigger $gatilho -Settings $config `
    -Description 'Completa os leads com CNPJ, razao social e socio da Receita Federal' `
    -Force | Out-Null

Write-Host ''
Write-Host 'Tarefa TurboVenda-Receita instalada.' -ForegroundColor Green
Write-Host "  roda a cada $MinutosIntervalo minutos"
Write-Host "  indice : $Indice"
Write-Host "  log    : $log"
Write-Host ''
Write-Host 'Rodar agora sem esperar:  Start-ScheduledTask -TaskName TurboVenda-Receita'
Write-Host 'Ver ultima execucao    :  Get-ScheduledTaskInfo -TaskName TurboVenda-Receita'
