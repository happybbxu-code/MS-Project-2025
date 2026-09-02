' Medical Screening Assistant - detached launcher (survives the launching shell)
Option Explicit
Dim sh, env
Set sh = CreateObject("WScript.Shell")
Set env = sh.Environment("PROCESS")
env.Item("PYTHONIOENCODING") = "utf-8"
env.Item("VIRTUAL_ENV") = "D:\VSCode-Workspace\MS-Project-2025\venv"
sh.CurrentDirectory = "D:\VSCode-Workspace\MS-Project-2025"
sh.Run "D:\VSCode-Workspace\MS-Project-2025\venv\Scripts\python.exe app.py", 0, False
