# Run as administrator on the disposable VM, including through encrypted WinRM.
$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ne 'WIN-10VM-ASUS') { throw 'Wrong disposable VM.' }
$key='Registry::HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}'
foreach ($name in @('cpus_logon','cpus_unlock','cpus_credui')) {
    Set-ItemProperty -Path $key -Name $name -Value '3d'
}
'Prototype MFA enforcement disabled. Engine and test account remain installed.'
