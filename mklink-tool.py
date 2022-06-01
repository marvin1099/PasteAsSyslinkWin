from ahk import AHK

import subprocess
import pyperclip
import ctypes
import time
import sys
import os

def Waitexit():
    #time.sleep(5)
    exit()

def QuickArgs(Def=""):
    Args = list(sys.argv)
    #Args += ["Test"] #Line to add quick test Arguments
    Script = Args[0]
    Args.pop(0)
    return Script, Args

def IsAdmin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def RunAsAdmin(Script,Args):
    Executable = sys.executable
    if sys.executable[-4:] != ".exe":
        print("Warning this script was made for Windows this probably won't work")
    if sys.executable != Script:
        Args = [Script] + Args
    NewArgs = ""
    for i in Args:
        NewArgs += ' "' + i + '"'
    if not IsAdmin(): # Re-run the program with admin rights if not admin
        ctypes.windll.shell32.ShellExecuteW(None, "runas", Executable, NewArgs, None, 1)
        exit()

def GetClip():
    ahk = AHK() #Make autohotkey ready
    ahk_clip_script = "FileAppend, %clipboard%, *" #Command to get clipboard contents
    ahkclret = ahk.run_script(ahk_clip_script) #Get clipboard contents
    ahkstr = str(ahkclret)
    ahkarr = ahkstr.split('\r\n').copy()
    ahkfull = []
    for i in ahkarr:
        if ((i[1:3] == ":\\" or i[0:2] == "\\\\") and os.path.exists(i)):
            ahkfull.append(i)
    return ahkfull

def GetExplorer():
    ahk = AHK()
    ahk_explorer_script = """
    WinActivate, ahk_class CabinetWClass
    WinGetClass, class, A
    if (class = "CabinetWClass") {
    	explorerHwnd := WinActive("ahk_class CabinetWClass")
    	if (explorerHwnd)
    		for window in ComObjCreate("Shell.Application").Windows
    			if (window.hwnd==explorerHwnd)
    				FileAppend,% window.Document.Folder.Self.Path, *
    }
    """ #Command to get open explorer dir
    ahkexvret = ""
    ahkexret = ahk.run_script(ahk_explorer_script)
    if ahkexret != "":
        ahkexret = os.path.abspath(ahkexret)
        if (ahkexret[1:3] == ":\\" or ahkexret[0:2] == "\\\\") and os.path.isdir(ahkexret):
            ahkexvret = ahkexret
    return ahkexret

def Argparse(Args):
    #Args += ["E:\\Recordings\\OBS\\Bugsnax\\Done\\Bugsnax #27.mp4"] #Test Arguments
    help = False
    heexit = True
    AllOper = ["/J ","","F"]
    ReadOpp = ["The diretory opperration was set to junction system link","The file opperration was set to normal system link"]
    Files = []
    UnArg = []
    for i in Args:
        Upperi = i.upper() + ""
        if "/D" == Upperi:
            AllOper[2] = "D"
            AllOper[0] = "/D "
            ReadOpp[0] = "The diretory opperration was set to normal system link"
        elif "/F" == Upperi:
            AllOper[2] = "F"
            AllOper[1] = ""
            ReadOpp[1] = "The file opperration was set to normal system link"
        elif "/J" == Upperi:
            AllOper[2] = "J"
            AllOper[0] = "/J "
            ReadOpp[0] = "The diretory opperration was set to junction system link"
        elif "/H" == Upperi:
            if AllOper[2] == "F":
                AllOper[1] = "/H "
                ReadOpp[1] = "The file opperration was set to hard system link"
            elif AllOper[2] == "D":
                AllOper[0] = "/D /H "
                ReadOpp[0] = "The diretory opperration was set to hard system link"
        elif "/N" == Upperi:
            heexit = False
        elif (i[1:3] == ":\\" or i[0:2] == "\\\\") and os.path.exists(i):
            Files.append(i)
        elif (len(i) == 4 and i[0:5].lower() == "help") or (len(i) == 5 and i[1:6].lower() == "help"):
            help = True
        else:
            UnArg.append(i)
    if help:
        help = """
Arguments:
- \"/help\": To show this message
- \"/N\": To stop the progamm from exitting when displaying the help message
- \"/F\": To change the file sylink options (Default for Files is a normal syslink)
- \"/D\": To change the dir sylink options
- \"/J\": To change the dir syslink options to Junction (Default for Diretorys)
- \"/H\": To add the hardlink option to the selected sylink type (\"/D\" (Diretory) or \"/F\" (File))
- Add any files and folders as an argument, to define the what to link and the link paste location
  (The last path argument given wil be the paste location. This can't be a file. If it is it will be ignored)

Info:
- {filein}
- {dirin}{pasfiles}{unkon}
        """
        pssa = ["",""]
        if len(Files) > 0:
            pssa[0] = "\n- The passed in files where:\n  - " + str("\n  - ").join(Files)
        if len(UnArg) > 0:
            pssa[1] = "\n- The following auguments where unknown:\n  - " + str("\n  - ").join(UnArg)
        print(help.format(dirin=ReadOpp[0],filein=ReadOpp[1],pasfiles=pssa[0],unkon=pssa[1]))
        if heexit:
            exit()
    return list([AllOper[0],AllOper[1]] + Files)

def Fileselect(Sel=0,Title=None):
    ahk = AHK() #Make autohotkey ready
    Filez = [["2","2","2"],["Use-The-Folder-That-You-Are-In","Use-The-Folder-That-You-Are-In-Or-Select-File","Select-File"],["Select Folder","Select File or Folder","Select File"],["Folder","Folder Or File; *","*"]]
    if Title == None:
        Title = Filez[2][Sel]
    ahk_file_script = "FileSelectFile, SelectedFile, " + Filez[0][Sel] + ", " + Filez[1][Sel] + ", " + Title + ", " + Filez[3][Sel] + "\nFileAppend, %SelectedFile%, *" #Command to get file or folder dir
    ahkfileret = ahk.run_script(ahk_file_script) #Get file or folder
    return ahkfileret

def Start(Command):
    print(Command)
    os.system(Command)

def ArgManage(Exp,Arg):
    Drg = Arg.pop(0)
    Frg = Arg.pop(0)
    WherePlaceLinks = Exp.pop(0)
    if WherePlaceLinks == "" and len(Arg) > 0 and os.path.isdir(Arg[0]):
        WherePlaceLinks = Arg.pop(0)
    AllPaths = Exp + Arg
    File = ""
    if len(AllPaths) < 1:
        whiletimer = 3
        while not os.path.exists(File):
            if whiletimer < 1:
                print("The user didn't enter a valid path to many times\nThe script will not exit")
                Waitexit()
            File = os.path.split(Fileselect(1,"Select file or folder to use as link"))
            if os.path.exists(File[0] + File[1]):
                File = File[0] + File[1]
            else:
                File = File[0]
            if not os.path.exists(File):
                print("File or Folder dosn't exist, asking again")
            whiletimer -= 1
        AllPaths.append(File)
    whiletimer = 3
    if WherePlaceLinks == "":
        while not os.path.isdir(WherePlaceLinks):
            if whiletimer < 1:
                print("The user didn't enter a valid path to many times\nThe script will not exit")
                Waitexit()
            WherePlaceLinks = os.path.split(Fileselect(0,"Select folder to paste the links"))[0]
            if not os.path.isdir(WherePlaceLinks):
                print("Folder dosn't exist, asking again")
            whiletimer -= 1
    for i in AllPaths:
        if os.path.isdir(i):
            if i ==  WherePlaceLinks + "\\" + os.path.split(i)[1]:
                Start("mklink " + Drg + "\"" + WherePlaceLinks + "\\" + os.path.split(i)[1] + "-link\" \"" + i + "\"")
            else:
                Start("mklink " + Drg + "\"" + WherePlaceLinks + "\\" + os.path.split(i)[1] + "\" \"" + i + "\"")
        else:
            if i ==  WherePlaceLinks + "\\" + os.path.split(i)[1]:
                Start("mklink " + Frg + "\"" + WherePlaceLinks + "\\" + os.path.split(i)[1] + "-link\" \"" + i + "\"")
            else:
                Start("mklink " + Frg + "\"" + WherePlaceLinks + "\\" + os.path.split(i)[1] + "\" \"" + i + "\"")
    Waitexit()

def main():
    Script, Args = QuickArgs()
    RunAsAdmin(Script, Args) #Uncoment when done to enable elavation
    ArgFiles = Argparse(Args)
    ExpClip = [GetExplorer()] + GetClip()
    ArgManage(ExpClip,ArgFiles)

# retu = subprocess.run(InputFile, stdout=subprocess.PIPE, timeout=Timeout)
# subprocess.run(FullCmd, stdout=subprocess.PIPE)
# creationflags=DETACHED_PROCESS
# os.spawnl(os.P_DETACH, Cmd, Args)



if __name__ == "__main__": #Start ForceAudioDevice if not imported
    main()
else:
    pass #print("to start use:\n" + __name__ + ".main()")
