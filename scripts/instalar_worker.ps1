# Instala as tarefas agendadas do Windows que mantem os leads completos com
# os dados da Receita:
#   TurboVenda-Receita        a cada 15 min: confere leads novos no indice
#   TurboVenda-Receita-Mensal todo dia 03:30: se saiu base nova da Receita,
#                             baixa e remonta o indice (sai em segundos se nao)
#
# Por que agendador e nao um processo fixo: se cair (reboot, erro, falta de
# rede), o agendador simplesmente roda de novo no proximo ciclo. Processo
# fixo precisaria de supervisao propria.
#
# Uso (PowerShell na pasta do projeto; nao precisa ser Administrador):
#   .\scripts\instalar_worker.ps1 -DatabaseUrl 'postgresql://...'
# Reinstalar depois (a senha do banco ja fica salva):
#   .\scripts\instalar_worker.ps1
#
# Para remover:
#   Unregister-ScheduledTask -TaskName 'TurboVenda-Receita' -Confirm:$false
#   Unregister-ScheduledTask -TaskName 'TurboVenda-Receita-Mensal' -Confirm:$false

param(
    [string]$DatabaseUrl = '',
    [string]$Indice = 'C:\cnpj\indice.sqlite',
    [string]$Zips = 'D:\cnpj',
    [int]$MinutosIntervalo = 15
)

$ErrorActionPreference = 'Stop'
$projeto = Split-Path -Parent $PSScriptRoot
$script = Join-Path $projeto 'scripts\enriquecer_local.py'
$atualizador = Join-Path $projeto 'scripts\atualizar_receita.py'
$python = (Get-Command python).Source
$log = Join-Path $projeto 'worker_receita.log'
$logMensal = Join-Path $projeto 'atualizar_receita.log'

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
if ($DatabaseUrl) {
    [System.IO.File]::WriteAllText($dsnArquivo, $DatabaseUrl)
    icacls $dsnArquivo /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null
} elseif (-not (Test-Path $dsnArquivo)) {
    throw "Primeira instalacao: passe -DatabaseUrl 'postgresql://...' (DATABASE_URL do Railway)"
}

# Notebook: o padrao do Windows nao roda tarefa na bateria
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

$acao = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "`"$script`" --indice `"$Indice`" --dsn-arquivo `"$dsnArquivo`" --log `"$log`"" `
    -WorkingDirectory $projeto
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $MinutosIntervalo)
Register-ScheduledTask -TaskName 'TurboVenda-Receita' -Action $acao `
    -Trigger $gatilho -Settings $config `
    -Description 'Completa os leads com CNPJ, razao social e socio da Receita Federal' `
    -Force | Out-Null

# Mensal: baixar 9 GB e montar leva umas 2 h; de madrugada e com prioridade
# baixa para nao pesar no PC. Se o PC estava desligado as 03:30, roda quando
# ligar (StartWhenAvailable).
$configMensal = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 8) `
    -MultipleInstances IgnoreNew -Priority 7
$acaoMensal = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "`"$atualizador`" --indice `"$Indice`" --zips `"$Zips`" --log `"$logMensal`"" `
    -WorkingDirectory $projeto
$gatilhoMensal = New-ScheduledTaskTrigger -Daily -At '03:30'
Register-ScheduledTask -TaskName 'TurboVenda-Receita-Mensal' -Action $acaoMensal `
    -Trigger $gatilhoMensal -Settings $configMensal `
    -Description 'Atualiza o indice local da Receita quando sai a base do mes' `
    -Force | Out-Null

Write-Host ''
Write-Host 'Tarefas instaladas.' -ForegroundColor Green
Write-Host "  TurboVenda-Receita        a cada $MinutosIntervalo min   log: $log"
Write-Host "  TurboVenda-Receita-Mensal todo dia 03:30  log: $logMensal"
Write-Host "  indice : $Indice"
Write-Host "  zips   : $Zips"
Write-Host ''
Write-Host 'Rodar agora sem esperar:  Start-ScheduledTask -TaskName TurboVenda-Receita'
Write-Host 'Ver ultima execucao    :  Get-ScheduledTaskInfo -TaskName TurboVenda-Receita'
