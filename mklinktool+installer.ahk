#NoEnv  ; Recommended for performance and compatibility with future AutoHotkey releases.
; #Warn  ; Enable warnings to assist with detecting common errors.
SendMode Input  ; Recommended for new scripts due to its superior speed and reliability.
SetWorkingDir %A_ScriptDir%  ; Ensures a consistent starting directory.
StartFolder := "C:\Windows\System32"
;StartFolder := "D:\Marvin\Documents\Autohotkey\Syslink\Testinstalldir"

DebugMessage(str)
{
 global h_stdout
 DebugConsoleInitialize()  ; start console window if not yet started
 str .= "`n" ; add line feed
 DllCall("WriteFile", "uint", h_Stdout, "uint", &str, "uint", StrLen(str), "uint*", BytesWritten, "uint", NULL) ; write into the console
 WinSet, Bottom,, ahk_id %h_stout%  ; keep console on bottom
}

DebugConsoleInitialize()
{
   global h_Stdout     ; Handle for console
   static is_open = 0  ; toogle whether opened before
   if (is_open = 1)     ; yes, so don't open again
     return
	 
   is_open := 1	
   ; two calls to open, no error check (it's debug, so you know what you are doing)
   DllCall("AttachConsole", int, -1, int)
   DllCall("AllocConsole", int)

   dllcall("SetConsoleTitle", "str","Paddy Debug Console")    ; Set the name. Example. Probably could use a_scriptname here 
   h_Stdout := DllCall("GetStdHandle", "int", -11) ; get the handle
   WinSet, Bottom,, ahk_id %h_stout%      ; make sure it's on the bottom
   WinActivate,Lightroom   ; Application specific; I need to make sure this application is running in the foreground. YMMV
   return
}

GoAdmin(Taskinfo,In:=True)
{
    full_command_line := DllCall("GetCommandLine", "str")
    if (A_IsAdmin and CheckTask(Taskinfo) = False)
        CreateTask(Taskinfo)
    if not (A_IsAdmin or RegExMatch(full_command_line, " /restart(?!\S)"))
    {
        try
        {
            if A_IsCompiled
    	    {
                Cmd := SubStr(full_command_line, StrLen("-" . A_ScriptFullPath . "- "))
                MsgBox, ok
                if CheckTask(Taskinfo,In) and (In != 2)
                    RunTask(Taskinfo)
                else
                    Run *RunAs "%A_ScriptFullPath%" /restart %Cmd%
            }
            else
            {
                Cmd := SubStr(full_command_line, StrLen("-" . A_AhkPath . "- "))
                if CheckTask(Taskinfo,In) and (In != 2)
                    RunTask(Taskinfo)
                else
                    Run *RunAs "%A_AhkPath%" /restart %Cmd%
            }
        }
        ExitApp
    }
}

FilterArray(FArr,f)
{
    if (f = "/e")
    {
        f := "/f"
        ex := [True,"",""]
    }
    folders := ["/d"]
    Loop % FArr.Length()
    {
        Item := FArr[A_Index]
        Types := ["/f","/d","/h","/j","/w","/m","/u","/r"]
        StringLower, Item, Item
        if (Item = Types[1])
        {
            if (files[1] = True and ex[1] = True)
                ex[2] := "/f"
            files := [True]
            if (f = "/f")
                f := "/u"
        }
        else if (Item = Types[2])
        {
            if (files[1] = False and ex[1] = True)
                ex[3] := "/d"
            folders := ["/d"]
            files[1] := False
        }
        else if (Item = Types[3])
        {
            if (files[1])
                files[2] := "/h"
            else
            {
                if (ex[1] = True)
                    if (folders[2] = "/j")
                        folders := ["/d","/h","/j"]
                    else
                        folders := ["/d","/h"]
                else
                    folders := ["/d","/h"]
            }
        }
        else if (Item = Types[4])
        {
                if (ex[1] = True)
                    if (folders[2] = "/h")
                        folders := ["/d","/h","/j"]
                    else
                        folders := ["/d","/j"]
                else
                    folders := ["/j"]
        }
        else if (Item = Types[5])
        {
                wild := True
        }
        else if (Item = Types[6])
        {
                wild := False
        }
        else if (Item = Types[7])
        {
                inst := True
        }
        else if (Item = Types[8])
        {
                inst := False
        }
    }
    if (folders[2] != "")
        folders[1] .= " " . folders[2]
    if (folders[3] != "")
        folders[1] .= " " . folders[3]
    if (f = "/u" and files[2] != "")
        files[2] := "/f " . files[2]
    else if (f = "/u")
        files[2] := "/f"
    if (ex[2] != "")
        files[2] := "/f " . files[2]
    if (ex[3] != "")
        folders[1] := "/d " . folders[1]
    ListT := files[2] . "`n" . folders[1] . "`n" . wild . "`n" . inst
    return ListT
}

FindAdmin(ArrF,ArrO,ArrFLA,ArrOLA,F,D)
{
    if (F = 1)
        if (ArrF.Length() = 1 and ArrF[1] = "/f" and ArrFLA[1] = "/f")
            return True
        else if (ArrF[2] = "/h" and (ArrFLA[1] = "/h" or ArrFLA[2] = "/h"))
            return True
    if (D = 1)
        if (ArrO.Length() = 1 and ArrO[1] = "/d" and ArrOLA[1] = "/d")
            return True
        else if (ArrO[2] = "/h" and (ArrOLA[1] = "/h" or ArrOLA[2] = "/h"))
            return True
        else if (ArrO[1] = "/j" and (ArrOLA[1] = "/j" or ArrOLA[2] = "/j" or ArrOLA[3] = "/j"))
            return True
    return False
}

Pathfinder(GArr,WildLoop)
{
    Loop % GArr.Length()
    {
        Path := GArr[A_Index]
        if (SubStr(Path, 0) = "\")
            Path := SubStr(Path, 1,-1)
        Loop, Files, %Path%, DF
        {
            Path := A_LoopFileFullPath
            TruePath := FileExist(Path)
            if TruePath
                if InStr(TruePath, "D")
                    Folders .= "`n" . Path
                else
                    Files .= Path . "`n"
            if not WildLoop
                break
        }
    } 
    if (Files = "")
        Files := "`n"
    if (Folders = "")
        Folders := "`n"
    Full := Files . Folders
    return Full
}

CheckTask(Taskinfo,In:=True) 
{
    if (Taskinfo = "" or In = False) 
        return False
    SplitPath, Taskinfo,,,, conf
    TaskName := conf . "elevationtask"
    Try
    {
        RunWait, schtasks /Query /TN "%TaskName%",,Hide
        if ErrorLevel
            ret := False
        else
            ret := True
    }
    Catch
        return ""
    return %ret%
}

RunTask(Taskinfo)
{
    if (Taskinfo = "") 
        return
    SplitPath, Taskinfo,,,, conf
    TaskName := conf . "elevationtask"
    TempArgfile := "C:\Users\" . A_UserName . "\AppData\Local\Temp" . "\" . conf . ".args.temp"
    if FileExist(TempArgfile)
        FileDelete, %TempArgfile%
    Loop, % A_Args.Length()
    {
        Item := A_Args[A_Index]
        if (Item != "")
            FileAppend, %Item%`n, %TempArgfile%
    }
    RunWait, schtasks /End /TN "%TaskName%",,Hide
    RunWait, schtasks /Run /TN "%TaskName%",,Hide
}

Uninstall(Script,Task)
{
    SplitPath, Script,Name,Dir,, conf
    TaskName := conf . "elevationtask"
    if (Task) 
        RunWait, schtasks /Delete /F /TN "%TaskName%",,Hide
    RegDelete, HKEY_CLASSES_ROOT\Directory\shell\SysLink
    RegDelete, HKEY_CLASSES_ROOT\Directory\Background\shell\SysLink
    FileDelete, %Dir%\%conf% Re Adder.lnk
    FileDelete, %Dir%\%conf% Uninstaller.lnk
    FileDelete, %Dir%\%conf%.conf
    FileDelete, %Dir%\%conf%.ico
    Script = "%Script%"
    Run %ComSpec% /c "timeout /t 1 /nobreak & del %Script%",,Hide
}

CreateTask(Taskinfo)
{
    if (Taskinfo = "") 
        return
    SplitPath, Taskinfo,,,, conf
    TaskName := conf . "elevationtask"
    RunWait, schtasks /Create /sc ONCE /st 00:00 /F /RL HIGHEST /TN "%TaskName%" /TR "%Taskinfo%",,Hide
}

AddReg(Script,Def)
{
    FDef := Def[1]
    DDef := Def[2]
    if (FDef != "" and DDef != "")
        FDef .= " " 
    SplitPath, Script,, OutDir,,OutName
    if A_IsCompiled
    {
        SCAH = "%Script%"
        ico = %Script%
    }
    else
    {
        SCAH = "%A_AhkPath%" "%Script%"
        ico = %OutDir%\%OutName%.ico
        if not FileExist(ico)
            UrlDownloadToFile,% "https://codeberg.org/marvin1099/Syslink-Creator-Windows/raw/commit/2c2929f56712b3b0bd5824afce9678d18aed4714/link.ico", %ico%
    }
    RegWrite, REG_SZ, HKEY_CLASSES_ROOT\Directory\shell\SysLink,, Create SysLinks Here
    RegWrite, REG_SZ, HKEY_CLASSES_ROOT\Directory\shell\SysLink, Icon, %ico%
    RegWrite, REG_SZ, HKEY_CLASSES_ROOT\Directory\shell\SysLink\command,, %SCAH% %FDef%%DDef% "`%V"
    RegWrite, REG_SZ, HKEY_CLASSES_ROOT\Directory\Background\shell\SysLink,, Create SysLinks Here
    RegWrite, REG_SZ, HKEY_CLASSES_ROOT\Directory\Background\shell\SysLink, Icon, %ico%
    RegWrite, REG_SZ, HKEY_CLASSES_ROOT\Directory\Background\shell\SysLink\command,, %SCAH% %FDef%%DDef% "`%V"
}

HasValue(haystack, needle)
{
    if(!isObject(haystack))
        return false
    if(haystack.Length()==0)
        return false
    for k,v in haystack
        if(v==needle)
            return true
    return false
}

JoinAr(JArr,sep:=" , ",RmSp:=False) 
{
    str := ""
    
    Loop,% JArr.Length()
    { 
        Item := JArr[A_Index] . " "
        if not (Item = " " and RmSp)
        {
            if (str = "")
                str .= JArr[A_Index]
            else
                str .= sep . JArr[A_Index]
        }
    }
    return str
}

;DebugMessage("`n Hello this is a test")

base := "\mklinktool"
if A_IsCompiled
    exe := ".exe"
else
    exe := ".ahk"
conf := base . ".conf"
instsname := base . exe
TempArgfile := "C:\Users\" . A_UserName . "\AppData\Local\Temp" . base . ".args.temp"


if !FileExist(A_ScriptDir . conf)
{
    FileSelectFile, InstallPath, 2, %StartFolder%\THIS FOLDER, Select Instalation Folder, Folder
    SplitPath, InstallPath,, InstallDir
    MsgBox, 4, MklinkTool, Use Task Scheduler
    IfMsgBox No
        TaskLit := "False"
    else
        TaskLit := "True"
    if (TaskLit = "True")
    {
        Taskinfo := InstallDir . instsname
        GoAdmin(Taskinfo,False)
    }
    FileAppend, test, %InstallDir%%conf%.temp
    if (ErrorLevel = 1)
        GoAdmin(Taskinfo,False)
    else
        FileDelete, %InstallDir%%conf%.temp
    MsgBox, 260, MklinkTool, Use Wildcard Loops
    IfMsgBox Yes
        WildLoop := "True"
    else
        WildLoop := "False"
    InputBox, UserIn, SysLinkTool, Enter the script defaults`nEnter /f to change file settings`n/d to change folder settings `n/h to use hard links `n/j to use junction links (folders only)`n/w will enable windcardloops /m will disable it`nNo options will use syslinks (eg. /f is file syslink),,,250,,,,, /f /d /j
    ArrN := StrSplit(UserIn, " ")
    List1 := StrSplit(FilterArray(ArrN,"/f"), "`n")
    MsgBox, 4, MklinkTool, Add Reg Entry
    IfMsgBox No
        RegSt := False
    else
    {
        RegSt := True
        GoAdmin(Taskinfo,False)
        InputBox, UserIn, SysLinkTool, Enter the context menu defauls`nEnter /f to change file settings`n/d to change folder settings `n/h to use hard links `n/j to use junction links (folders only)`n/w will enable windcardloops /m will disable it`nNo options will use syslinks (eg. /f is file syslink),,,250,,,,, /f /d /j
        ArrN := StrSplit(UserIn, " ")
        List2 := StrSplit(FilterArray(ArrN,"/f"), "`n")
        AddReg(InstallDir . instsname, List2)
    }
    InputBox, UserIn, SysLinkTool, Enter the admin required args`nEnter /f to select file settings (twice to mark as admin)`n/d to select folder settings (twice to mark as admin)`n/h to mark as admin for last selcted `n/j to mark junction as admin,,,250,,,,, /f /f /h /d /d /h
    ArrN := StrSplit(UserIn, " ")
    List3 := StrSplit(FilterArray(ArrN,"/e"), "`n")
    SDFO := List1[1]
    SDOO := List1[2]
    AdmFiOp := List3[1]
    AdmFoOp := List3[2]
    if FileExist(InstallDir . conf)
        FileDelete, %InstallDir%%conf%
    FileAppend, 
    (
Task = %TaskLit%
WildcardLoops = %WildLoop%
ScriptDefaultFileOptions = %SDFO%
ScriptDefaultFolderOptions = %SDOO%
AdminFileOptions = %AdmFiOp%
AdminFolderOptions = %AdmFoOp%

), %InstallDir%%conf%
    OnlyName := SubStr(instsname, 2)
    FileCreateShortcut, %InstallDir%%instsname%, %InstallDir%%base% Uninstaller.lnk, %InstallDir%, /U, Uninstall MklinkTool
    FileCreateShortcut, %InstallDir%%instsname%, %InstallDir%%base% Re Adder.lnk, %InstallDir%, /R, Re Add Key And Task
    if FileExist(TempArgfile)
        FileDelete, %TempArgfile%
    FileCopy, %A_ScriptFullPath%, %InstallDir%%instsname%, 1
    full_command_line := DllCall("GetCommandLine", "str")
    ano = "
    newfullcmd := StrReplace(full_command_line, ano . A_ScriptFullPath . ano, ano . InstallDir . instsname . ano,,1)
    ;Run, %newfullcmd%, %InstallDir%
    ExitApp
}
else
{
    InstallDir := A_ScriptDir
    Loop, Read, %InstallDir%%conf%
    {
        StringLower, LowReadLine, A_LoopReadLine
        Out := StrSplit(LowReadLine, "="," `r",2)
        if (Out[1] = "task" and (Out[2] = "false" or Out[2] = 0))
            Task := False
        else if (Out[1] = "task")
            Task := True
        else if (Out[1] = "wildcardloops" and (Out[2] = "true" or Out[2] = 1))
            WildLoop := True
        else if (Out[1] = "wildcardloops")
            WildLoop := False
        else if (Out[1] = "scriptdefaultfileoptions")
            Filds := Out[2]
        else if (Out[1] = "scriptdefaultfolderoptions")
            Folds := Out[2]
        else if (Out[1] = "adminfileoptions")
            AFO := Out[2]
        else if (Out[1] = "adminfolderoptions")
            AOO := Out[2]
    }
    if (Task = True)
        Taskinfo := InstallDir . instsname 
    if (A_ScriptName != SubStr(instsname, 2))
    {
        CuSCPaTem = "%A_ScriptFullPath%"
        NeSCPaTem = "%A_ScriptDir%%instsname%"
        OnlyName := SubStr(instsname, 2)
        OnlyName = "%OnlyName%" 
        ScriptName = "%A_ScriptName%"
        if A_IsCompiled
            NeSCPaTeb = NeSCPaTem
        else
            NeSCPaTeb = "%A_AhkPath%" %NeSCPaTem%
        FileAppend, test, %InstallDir%%conf%.temp
        if (ErrorLevel = 1)
            GoAdmin(Taskinfo,2)
        else
            FileDelete, %InstallDir%%conf%.temp
        Tesepsc = " " 
        cmd := JoinAr(A_Args,Tesepsc,True) 
        if (cmd != "")
            cmd = "%cmd%"
        Run %ComSpec% /c "timeout /t 1 /nobreak & cd /d %A_ScriptDir% & ren %ScriptName% %OnlyName% & %NeSCPaTeb% %cmd%",,Hide
        ExitApp
    }
    LitA := StrSplit(FilterArray(StrSplit(AFO . " " . AOO, " "),"/e"), "`n")
    ArrFLA := StrSplit(LitA[1], " ") 
    ArrOLA := StrSplit(LitA[2], " ")
    ArrFLA.RemoveAt(1)
    ArrOLA.RemoveAt(1)
    BArr := StrSplit(Filds, " ")
    NArr := StrSplit(Folds, " ")
    FArr := StrSplit(BArr[1] . "`n" . BArr[2] . "`n" . NArr[1] . "`n" . NArr[2] . "`n" . JoinAr(A_Args,sep:="`n",True), "`n")
    if FileExist(TempArgfile)
    {
        FileRead, TempCont, %TempArgfile%
        Loop, Parse, TempCont, `n, `r
        {
            if (A_LoopField != "")
                FArr.Push(A_LoopField)
        }
    }
    ReqListAd := StrSplit(FilterArray(FArr,"/f"), "`n")
    List := StrSplit(FilterArray(FArr,""), "`n")
    FList := List[1]
    DList := List[2]
    if (List[3] != "")
        WildLoop := List[3]
    Loop, Parse, clipboard, `n, `r
    {
        if (A_LoopField != "")
            FArr.Push(A_LoopField)
    }
    Paths := StrSplit(Pathfinder(FArr,WildLoop), "`n`n",, 2)
    FPaths := StrSplit(Paths[1],"`n"," `r")
    DPaths := StrSplit(Paths[2],"`n"," `r")
    if (DPaths.Length() < 1 or (FPaths.Length() < 1 and DPaths.Length() < 2)) and (List[4] = "")
    {
        MsgBox,, SysLinkTool, Error`nAt least 1 valid folder and 1 valid path is required`nto drop the selcted files into as syslinks`nand for the selcted files iteself`nExiting in 10 Secs, 10
        if FileExist(TempArgfile)
            FileDelete, %TempArgfile%
        ExitApp
    }
    DestPath := DPaths.RemoveAt(1)
    if (Task = True)
        Taskinfo := InstallDir . instsname 
    fa := FindAdmin(StrSplit(ReqListAd[1]," "),StrSplit(ReqListAd[2]," "),ArrFLA,ArrOLA,FPaths.Length()>0,DPaths.Length()>0)
    if (not A_IsAdmin and (fa = True or List[4] != ""))
        GoAdmin(Taskinfo) 
    if (List[4] != "")
    {
        if FileExist(TempArgfile)
            FileDelete, %TempArgfile%
        if (List[4] = True)
        {
            Uninstall(InstallDir . instsname,Task)
            ExitApp
        }
        if (List[4] = False)
        {
            CreateTask(Taskinfo)
            MsgBox, 4, MklinkTool, Add Reg Entry
            IfMsgBox No
                RegSt := False
            else
            {
                InputBox, UserIn, SysLinkTool, Enter the context menu defauls`nEnter /f to change file settings`n/d to change folder settings `n/h to use hard links `n/j to use junction links (folders only)`n/w will enable windcardloops /m will disable it`nNo options will use syslinks (eg. /f is file syslink),,,250,,,,, /f /d /j
                ArrN := StrSplit(UserIn, " ")
                List2 := StrSplit(FilterArray(ArrN,"/f"), "`n")
                RegSt := True
                AddReg(T, List2)
            }
            ico = %InstallDir%%base%.ico
            if not A_IsCompiled and not FileExist(ico)
                UrlDownloadToFile,% "https://codeberg.org/marvin1099/Syslink-Creator-Windows/raw/commit/2c2929f56712b3b0bd5824afce9678d18aed4714/link.ico", %ico%
            FileCreateShortcut, %InstallDir%%instsname%, %InstallDir%%base% Uninstaller.lnk, %InstallDir%, /U, Uninstall MklinkTool
            FileCreateShortcut, %InstallDir%%instsname%, %InstallDir%%base% Re Adder.lnk, %InstallDir%, /R, Re Add Key And Task
            ExitApp
        }
    }
    if FileExist(TempArgfile)
        FileDelete, %TempArgfile%
    Loop, % FPaths.Length()
    {
        ano = "
        Item := FPaths[A_Index]
        SplitPath, Item, OutName,,Ext,OnlyName
        CurDest := DestPath . "\" . OutName
        if (SubStr(Item,1,1) = "\")
            Item := ano . DestPath . Item . ano ;,,Hide
        else
            Item := ano . Item . ano
        ExiCurDest := CurDest
        while(InStr(FileExist(ExiCurDest), "A"))
        {
            ExiCurDest := DestPath . "\" . OnlyName . " (" . A_Index . ")." . Ext
        }
        CurDest := ano . ExiCurDest . ano
        RunWait, %ComSpec% /c "mklink %FList% %CurDest% %Item%",,Hide
    } 
    Loop, % DPaths.Length()
    {
        ano = "
        Item := DPaths[A_Index]
        SplitPath, Item, OutName,,Ext,OnlyName
        CurDest := DestPath . "\" . OutName
        if (SubStr(Item,1,1) = "\")
            Item := ano . DestPath . Item . ano
        else
            Item := ano . Item . ano
        ExiCurDest := CurDest
        while(InStr(FileExist(ExiCurDest), "D"))
        {
            ExiCurDest := DestPath . "\" . OnlyName . " (" . A_Index . ")"
        }
        CurDest := ano . ExiCurDest . ano
        RunWait, %ComSpec% /c "mklink %DList% %CurDest% %Item%",,Hide
    }  
}
