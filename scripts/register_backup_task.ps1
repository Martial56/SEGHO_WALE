<#
.SYNOPSIS
    Enregistre une tache planifiee Windows qui sauvegarde chaque nuit la base
    de donnees SEGHO-WALE et le dossier media/.

.DESCRIPTION
    Ce script NE S'EXECUTE PAS AUTOMATIQUEMENT - il doit etre lance une seule
    fois, manuellement, pour creer la tache planifiee. Il ne fait qu'appeler
    schtasks.exe ; il ne modifie aucun fichier du projet.

    Par defaut, la sauvegarde est ecrite dans .\backups (sur le meme disque
    que le projet). Il est fortement recommande d'utiliser -BackupDest pour
    pointer vers un disque externe ou un partage reseau, afin qu'une panne
    disque ou un ransomware ne detruise pas aussi les sauvegardes.

.PARAMETER BackupDest
    Dossier de destination des sauvegardes (ex: "D:\Sauvegardes\SEGHO-WALE").
    Par defaut : <racine du projet>\backups

.PARAMETER Time
    Heure d'execution quotidienne, format HH:mm (defaut 02:00).

.EXAMPLE
    .\register_backup_task.ps1 -BackupDest "D:\Sauvegardes\SEGHO-WALE" -Time "02:30"
#>

param(
    [string]$BackupDest = "",
    [string]$Time = "02:00"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$ManagePy = Join-Path $ProjectDir "manage.py"

if (-not (Test-Path $ManagePy)) {
    throw "manage.py introuvable dans $ProjectDir - lance ce script depuis le dossier scripts\ du projet."
}

$PythonExe = (& py -c "import sys; print(sys.executable)").Trim()
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    throw "Impossible de localiser python.exe via le lanceur 'py'."
}

if (-not $BackupDest) {
    $BackupDest = Join-Path $ProjectDir "backups"
    Write-Warning "Aucun -BackupDest fourni : les sauvegardes resteront sur ce disque ($BackupDest)."
    Write-Warning "Recommande : relancer avec -BackupDest pointant vers un disque externe ou un partage reseau."
}

if (-not (Test-Path $BackupDest)) {
    New-Item -ItemType Directory -Force -Path $BackupDest | Out-Null
}

$TaskName = "SEGHO-WALE Backup Quotidien"
$Arguments = "`"$ManagePy`" backup_db --dest `"$BackupDest`" --keep-days 30"

schtasks /Create `
    /TN $TaskName `
    /TR "`"$PythonExe`" $Arguments" `
    /SC DAILY `
    /ST $Time `
    /RU $env:USERNAME `
    /RL LIMITED `
    /F

Write-Host ""
Write-Host "Tache planifiee '$TaskName' creee : execution quotidienne a $Time." -ForegroundColor Green
Write-Host "Destination des sauvegardes : $BackupDest" -ForegroundColor Green
Write-Host ""
Write-Host "Pour tester immediatement : schtasks /Run /TN `"$TaskName`""
Write-Host "Pour supprimer la tache   : schtasks /Delete /TN `"$TaskName`" /F"
