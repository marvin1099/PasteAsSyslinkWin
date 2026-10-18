"""WScript launcher that starts a command hidden (no console window).

Task-scheduler elevation and the Apps & Features uninstall strings run
console executables; started directly, Windows creates a visible console
window first and the app can only hide it afterwards (flash). Running the
command from a VBScript with window style 0 creates it hidden from birth.
The script receives the command as quoted arguments (program first, then
its arguments), waits for it to finish, and sets the working directory so
relative paths resolve.
"""

import os

# Triple-single quotes: the VBScript itself is full of double quotes
# ("""" = a VBS string containing one quote character).
_TEMPLATE = '''\
Dim WShell
Set WShell = CreateObject("WScript.Shell")
Rem mklinktool hidden launcher: argument 0 is the program, the rest are its arguments.
WShell.CurrentDirectory = "{cwd}"
Dim cmd, i
cmd = """" & WScript.Arguments(0) & """"
For i = 1 To WScript.Arguments.Count - 1
    cmd = cmd & " " & """" & WScript.Arguments(i) & """"
Next
WShell.Run cmd, 0, True
Set WShell = Nothing
'''


def write_hidden_launcher(vbs_path: str, cwd: str) -> str:
    """Write the hidden-launcher VBScript at ``vbs_path``; returns the path.

    Window style 0 (hidden) plus wait flag: the caller (wscript itself a
    GUI process) never shows a console, and processes that wait on the
    launcher still observe the real command's completion.
    """
    if not cwd:
        cwd = os.getcwd()
    content = _TEMPLATE.format(cwd=cwd)
    with open(vbs_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(content)
    return vbs_path
