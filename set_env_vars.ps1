# PowerShell Script zum Setzen der Umgebungsvariablen für die Prepper App

# Funktion zum Generieren eines JWT Secret Keys
function Generate-JWTSecretKey {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RNGCryptoServiceProvider]::Create().GetBytes($bytes)
    return [System.Convert]::ToBase64String($bytes) -replace '[+/=]', ''
}

# Generiere einen neuen JWT-Secret-Key
$JWT_SECRET_KEY = Generate-JWTSecretKey

Write-Host "Setting environment variables for Prepper App..." -ForegroundColor Green

# Setze Umgebungsvariablen für die aktuelle Sitzung
$env:JWT_SECRET_KEY = $JWT_SECRET_KEY
$env:FRONTEND_URL = "http://localhost:3000"
$env:REACT_APP_API_URL = "http://localhost:4000"
$env:SEARCH_API_KEY = "55e046050074193ef6db1800b3e79e530ab22b4f47c55bb626b952beb2e42610"
$env:ADMIN_USERNAME = "Psychoorc"
$env:ADMIN_PASSWORD = "P422w0rd4Schottel23"
$env:ADMIN_EMAIL = "Psychoorc@gmx.net"
$env:DEFAULT_USERNAME = "DefaultUser"
$env:DEFAULT_PASSWORD = "5H8FDcII@_rv@N6a8@AP"
$env:DEFAULT_EMAIL = "default@example.com"
$env:MAIL_DEFAULT_SENDER = "webmaster@meinedevpath.de"
$env:MAIL_SERVER = "smtp.strato.de"
$env:MAIL_PORT = "465"
$env:MAIL_USERNAME = "webmaster@meinedevpath.de"
$env:MAIL_PASSWORD = "KzERNZu#cQ_pSw2"

Write-Host "Environment variables set for current session!" -ForegroundColor Green
Write-Host "JWT_SECRET_KEY generated: $JWT_SECRET_KEY" -ForegroundColor Yellow

# Optional: Permanent setzen (erfordert Admin-Rechte)
$setPermanent = Read-Host "Möchten Sie die Variablen permanent setzen? (y/N)"
if ($setPermanent -eq "y" -or $setPermanent -eq "Y") {
    try {
        [Environment]::SetEnvironmentVariable("JWT_SECRET_KEY", $JWT_SECRET_KEY, "User")
        [Environment]::SetEnvironmentVariable("FRONTEND_URL", "http://localhost:3000", "User")
        [Environment]::SetEnvironmentVariable("REACT_APP_API_URL", "http://localhost:4000", "User")
        [Environment]::SetEnvironmentVariable("SEARCH_API_KEY", "55e046050074193ef6db1800b3e79e530ab22b4f47c55bb626b952beb2e42610", "User")
        [Environment]::SetEnvironmentVariable("ADMIN_USERNAME", "Psychoorc", "User")
        [Environment]::SetEnvironmentVariable("ADMIN_PASSWORD", "P422w0rd4Schottel23", "User")
        [Environment]::SetEnvironmentVariable("ADMIN_EMAIL", "Psychoorc@gmx.net", "User")
        [Environment]::SetEnvironmentVariable("DEFAULT_USERNAME", "DefaultUser", "User")
        [Environment]::SetEnvironmentVariable("DEFAULT_PASSWORD", "5H8FDcII@_rv@N6a8@AP", "User")
        [Environment]::SetEnvironmentVariable("DEFAULT_EMAIL", "default@example.com", "User")
        [Environment]::SetEnvironmentVariable("MAIL_DEFAULT_SENDER", "webmaster@meinedevpath.de", "User")
        [Environment]::SetEnvironmentVariable("MAIL_SERVER", "smtp.strato.de", "User")
        [Environment]::SetEnvironmentVariable("MAIL_PORT", "465", "User")
        [Environment]::SetEnvironmentVariable("MAIL_USERNAME", "webmaster@meinedevpath.de", "User")
        [Environment]::SetEnvironmentVariable("MAIL_PASSWORD", "KzERNZu#cQ_pSw2", "User")
        
        Write-Host "Environment variables set permanently!" -ForegroundColor Green
        Write-Host "Sie müssen PowerShell neu starten, damit die permanenten Variablen wirksam werden." -ForegroundColor Yellow
    }
    catch {
        Write-Host "Fehler beim permanenten Setzen der Variablen: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Versuchen Sie PowerShell als Administrator auszuführen." -ForegroundColor Yellow
    }
}

Write-Host "Fertig! Sie können jetzt Ihre Python-App starten." -ForegroundColor Green
