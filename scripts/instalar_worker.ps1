# Instala o worker de enriquecimento como tarefa agendada do Windows.
#
# Por que agendador e nao um processo fixo: se cair (reboot, erro, falta de
# rede), o agendador simplesmente roda de novo no proximo ciclo. Processo
# fixo precisaria de supervisao propria.
#
# Uso (PowerShell como Administrador, na pasta do projeto):
#   .\scripts\instalar_worker.ps1 -DatabaseUrl 'postgresql://...'
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

# A senha do banco fica na variavel da tarefa, nao no comando — assim nao
# aparece na listagem de processos de quem estiver no micro.
$cmd = "`$env:DATABASE_URL='$DatabaseUrl'; & '$python' '$script' --indice '$Indice' *>> '$log'"
$bytes = [System.Text.Encoding]::Unicode.GetBytes($cmd)
$encoded = [Convert]::ToBase64String($bytes)

$acao = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -EncodedCommand $encoded" `
    -WorkingDirectory $projeto

$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $MinutosIntervalo)

$config = New-ScheduledTaskSettingsSet -StartWhenAvailable `
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
