$listenerPids = @(
    Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction Ignore |
        Select-Object -ExpandProperty OwningProcess -Unique
)

foreach ($processId in $listenerPids) {
    Write-Host "Stopping Vite on :5173 (PID $processId)"
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}
