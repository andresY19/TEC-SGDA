param([Parameter(Mandatory)][string]$Artifacts, [Parameter(Mandatory)][string]$Pilot,
      [string]$ClientHash = '7B94CE0D3458E59FFB85946CA78468B97D05D41CB6EEFF171648E0C39944C5B8',
      [string]$PreviousHash = $ClientHash)
$ErrorActionPreference = 'Stop'
$program = Join-Path $env:LOCALAPPDATA 'Programs/TEC-SGDEA-Demostracion'
$exe = Join-Path $program 'TEC-SGDEA.exe'
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'TEC-SGDEA Demostración/TEC-SGDEA.lnk'
$registration = 'HKCU:/Software/TEC-SGDEA/DemoMSI'
$testRoot = Join-Path $Artifacts 'prueba-instalacion'
$testLocal = Join-Path $testRoot 'local'
$vault = Join-Path $testLocal 'TEC-SGDEA-Consolidado/workspace.sqlite3'
$msi = Join-Path $Artifacts 'TEC-SGDEA.msi'
$pre = Join-Path $Artifacts 'preupgrade.msi'
$python = Join-Path $Pilot 'package-env/Scripts/python.exe'
$fixture = Join-Path $Artifacts 'fixture'
$code = (Get-Content "$fixture/result.json" -Raw | ConvertFrom-Json).code
$oldVault = Join-Path $env:LOCALAPPDATA 'TEC-SGDEA/workspace.sqlite3'
$oldHash = if (Test-Path $oldVault) { (Get-FileHash -LiteralPath $oldVault).Hash }

if ((Test-Path $program) -or (Test-Path $shortcut) -or (Test-Path $registration) -or (Test-Path $testRoot)) {
    throw 'Se requiere un destino limpio para el ensayo MSI.'
}
New-Item $testLocal -ItemType Directory | Out-Null
$env:TEC_SGDEA_TEST_URL = 'http://127.0.0.1:18099'
$env:TEC_SGDEA_TEST_WORKSPACE = $vault
$steps = [ordered]@{}

function Invoke-Msi([string]$action, [string]$package, [string]$step) {
    $log = Join-Path $testRoot "$step.log"
    $arguments = '{0} "{1}" /qn /norestart /l*v "{2}"' -f $action, $package, $log
    $p = Start-Process "$env:WINDIR/System32/msiexec.exe" -WindowStyle Hidden -Wait -PassThru -ArgumentList $arguments
    if ($p.ExitCode -ne 0) { throw "Windows Installer devolvió $($p.ExitCode) en $step" }
    $steps[$step] = $true
}

function Assert-Installed([string]$ExpectedHash = $ClientHash) {
    if (!(Test-Path $shortcut) -or (Get-FileHash -LiteralPath $exe).Hash -ne $ExpectedHash) {
        throw 'El binario o el acceso directo instalado no coincide.'
    }
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcut)
    if ($link.TargetPath -ne $exe) { throw 'Destino incorrecto del acceso directo.' }
}

function Open-And-Close {
    $proc = Start-Process $exe -WindowStyle Hidden -PassThru -Environment @{LOCALAPPDATA=$testLocal}
    $deadline = (Get-Date).AddSeconds(25)
    do {
        $window = Get-Process 'TEC-SGDEA' -ErrorAction SilentlyContinue | Where-Object {
            $_.Path -eq $exe -and $_.MainWindowTitle -eq 'TEC-SGDEA | Escritorio'
        } | Select-Object -First 1
        if (!$window) { Start-Sleep -Milliseconds 250 }
    } until ($window -or (Get-Date) -gt $deadline)
    if (!$window -or !$window.CloseMainWindow() -or !$proc.WaitForExit(8000)) {
        throw 'No se verificó la apertura y cierre normal.'
    }
}

function Invoke-WorkspacePhase([string]$phase) {
    & $python -B "$PSScriptRoot/work_e2e.py" $Pilot $fixture $testRoot $code $phase
    if ($LASTEXITCODE) { throw "Falló la fase $phase" }
    $steps["offline_$phase"] = $true
}

Invoke-Msi /i $pre 'instalacion_limpia'
Assert-Installed $PreviousHash
Open-And-Close
$steps.apertura_cierre = $true
foreach ($phase in ('cache','edit','expiry','stale')) { Invoke-WorkspacePhase $phase }
$before = (Get-FileHash -LiteralPath $vault).Hash
Open-And-Close
Invoke-WorkspacePhase expiry
if ((Get-FileHash -LiteralPath $vault).Hash -ne $before) { throw 'Cambió el almacén durante la reapertura.' }

Invoke-Msi /i $msi 'actualizacion'
Assert-Installed
if ((Get-FileHash -LiteralPath $vault).Hash -ne $before) { throw 'La actualización modificó el almacén.' }
Invoke-Msi /x $msi 'desinstalacion'
if ((Test-Path $exe) -or (Test-Path $shortcut) -or (Get-ItemProperty $registration -Name Client -ErrorAction SilentlyContinue)) {
    throw 'Quedaron componentes del instalador.'
}
if ((Get-FileHash -LiteralPath $vault).Hash -ne $before) { throw 'La desinstalación modificó el almacén.' }
$steps.almacen_intacto_tras_actualizar_y_desinstalar = $true

Invoke-Msi /i $msi 'reinstalacion'
Assert-Installed
Open-And-Close
foreach ($phase in ('interrupt','sync','conflict')) { Invoke-WorkspacePhase $phase }
$after = (Get-FileHash -LiteralPath $vault).Hash
Invoke-Msi /x $msi 'desinstalacion_final'
if ((Test-Path $exe) -or (Test-Path $shortcut) -or (Get-FileHash -LiteralPath $vault).Hash -ne $after) {
    throw 'La limpieza del instalador o la conservación del almacén falló.'
}
if ($oldHash -and (Get-FileHash -LiteralPath $oldVault).Hash -ne $oldHash) {
    throw 'Cambió el almacén original.'
}
$steps.almacen_original_intacto = $true
[ordered]@{
    expediente_sintetico = $code
    aislamiento = 'Destino MSI limpio y almacén separado, mismo usuario Windows para DPAPI'
    desconexion_simulada_horas = @(23,25)
    sha256_msi = (Get-FileHash -LiteralPath $msi).Hash
    sha256_ejecutable = $ClientHash
    resultados = $steps
} | ConvertTo-Json -Depth 4 | Set-Content "$Artifacts/verificacion.json" -Encoding utf8
