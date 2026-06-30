Option Explicit

Dim shell
Dim command
Dim exitCode
Dim scriptPath
Dim logPath

scriptPath = "C:\Users\Franky Kuo\Desktop\management_system\infra\backup\backup_postgres.ps1"
logPath = "C:\Users\Franky Kuo\Desktop\management_system\infra\backup\backup_postgres_scheduled.log"

Set shell = CreateObject("WScript.Shell")
command = "pwsh.exe -NoProfile -ExecutionPolicy Bypass -Command ""& { & '" & scriptPath & "' *>> '" & logPath & "' }"""
exitCode = shell.Run(command, 0, True)

WScript.Quit exitCode
