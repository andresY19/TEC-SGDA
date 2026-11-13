$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$source = Join-Path $workspace 'expedidos\respaldo_sintetico_9b'
$manifest = Get-Content -LiteralPath (Join-Path $workspace 'phase9b-protection.json') -Raw | ConvertFrom-Json
$names = @('postgres-local.dump','deposito-sintetico.zip','postgres-catalog.txt')
$required = ($names | ForEach-Object { (Get-Item -LiteralPath (Join-Path $source $_)).Length } | Measure-Object -Sum).Sum
$disk = Get-PSDrive -Name C
if ($disk.Free -le ($required * 2)) { throw 'Insufficient C: capacity for copy and verification.' }
foreach ($name in $names) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $source $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $manifest.files.$name.sha256) { throw "Source backup hash mismatch: $name" }
}
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$unique = [guid]::NewGuid().ToString('N').Substring(0,8)
$base = Join-Path $env:USERPROFILE 'GEOLOGY_Backups'
$destination = Join-Path $base "geology-local-20261106-57a99a\9d-$stamp-$unique"
if (Test-Path -LiteralPath $destination) { throw 'Destination already exists; no overwrite allowed.' }
[void][System.IO.Directory]::CreateDirectory($destination)
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$acl = [System.Security.AccessControl.DirectorySecurity]::new()
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true,$false)
foreach ($principal in @($sid,$system)) {
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new($principal,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit',
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow)
    [void]$acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $destination -AclObject $acl
$records = @()
foreach ($name in $names) {
    $src = Join-Path $source $name
    $dst = Join-Path $destination $name
    [System.IO.File]::Copy($src,$dst,$false)
    $before = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant()
    $after = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($before -ne $after -or $before -ne $manifest.files.$name.sha256) { throw "Copy verification failed: $name" }
    $records += [ordered]@{name=$name;bytes=(Get-Item -LiteralPath $dst).Length;source_sha256=$before;copy_sha256=$after}
}
$allowed = @($sid.Value,$system.Value)
$permissionEvidence = @()
foreach ($item in @((Get-Item -LiteralPath $destination)) + @(Get-ChildItem -LiteralPath $destination -File)) {
    $current = Get-Acl -LiteralPath $item.FullName
    $entries = @($current.Access | ForEach-Object {
        $id = $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        if ($id -notin $allowed -or $_.AccessControlType -ne 'Allow') { throw 'Unexpected backup access rule.' }
        [ordered]@{sid=$id;rights=$_.FileSystemRights.ToString();inherited=$_.IsInherited}
    })
    if ($entries.Count -ne 2) { throw 'Unexpected backup access rule count.' }
    $permissionEvidence += [ordered]@{path=$item.FullName;inheritance_protected=$current.AreAccessRulesProtected;rules=$entries}
}
$result = [ordered]@{destination=$destination;source=$source;C_free_before_bytes=$disk.Free;
    copied_bytes=$required;files=$records;permissions=$permissionEvidence;allowed_principals=@('current user','SYSTEM');
    inherited_permissions_removed_on_new_directory=$true;originals_unchanged=$true;env_files_copied=$false;
    note='Exact existing database backup copied; account password hashes inside the database dump are protected by these ACLs. No .env, application session key or provider keys included.'}
$json = $result | ConvertTo-Json -Depth 9
[System.IO.File]::WriteAllText((Join-Path $workspace 'phase9d-backup-copy.json'),$json,[System.Text.UTF8Encoding]::new($false))
Write-Output ([ordered]@{destination=$destination;copied_bytes=$required;hashes='PASS';permissions='current user and SYSTEM only'} | ConvertTo-Json)
