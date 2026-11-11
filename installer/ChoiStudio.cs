// Choi Studio 설치·업데이트·실행을 하나로 — ChoiStudio.exe
// 처음: 설치 폴더를 고르면 GitHub main 을 받아 풀고 setup_windows.bat 을 자동 모드로 돌린다.
// 다음부터: 새 커밋이 있으면 업데이트를 물어 덮어쓰고(key·user·projects·.venv·models 는 zip 에 없어 그대로), run_studio.bat 으로 실행.
// 빌드는 installer/README.md (Windows 기본 .NET Framework 의 csc — C# 5 문법만).
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Windows.Forms;
using Microsoft.Win32;

static class ChoiStudio
{
    const string Repo = "CHIDdesign/Choi-Explains-Design";
    const string Branch = "main";
    const string Title = "Choi Studio";
    const string RegKey = @"Software\ChoiStudio";

    [STAThread]
    static int Main(string[] args)
    {
        ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
        try { return Run(args); }
        catch (Exception e)
        {
            MessageBox.Show("오류가 났습니다:\n\n" + e.Message, Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static int Run(string[] args)
    {
        string dir = ArgValue(args, "--dir");
        string self = Application.ExecutablePath;
        if (dir == null && IsInstall(Path.GetDirectoryName(self))) dir = Path.GetDirectoryName(self);
        if (dir == null)
        {
            string saved = Registry.CurrentUser.OpenSubKey(RegKey) == null ? null
                : Registry.CurrentUser.OpenSubKey(RegKey).GetValue("InstallDir") as string;
            if (saved != null && IsInstall(saved)) dir = saved;
        }
        if (dir == null) dir = PickFolder();
        if (dir == null) return 0;
        dir = Path.GetFullPath(dir);

        bool fresh = !IsInstall(dir);
        string sha = LatestSha();
        string verFile = Path.Combine(dir, ".choi_version");
        string cur = File.Exists(verFile) ? File.ReadAllText(verFile).Trim() : null;

        if (fresh && sha == null)
            throw new Exception("GitHub 에 연결하지 못해 설치할 수 없습니다. 인터넷 연결을 확인하세요.");
        if (sha != null && sha != cur && (fresh || MessageBox.Show(
                "새 버전이 있습니다. 지금 업데이트할까요?\n(API 키·설정·작업 폴더는 그대로 둡니다)",
                Title, MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes))
        {
            Install(sha, dir);
            File.WriteAllText(verFile, sha);
        }

        string target = Path.Combine(dir, "ChoiStudio.exe");
        if (!string.Equals(Path.GetFullPath(self), target, StringComparison.OrdinalIgnoreCase))
            File.Copy(self, target, true);  // 설치 폴더의 exe 가 다음부터 실행·업데이트를 맡는다
        Registry.CurrentUser.CreateSubKey(RegKey).SetValue("InstallDir", dir);

        if (fresh || !File.Exists(Path.Combine(dir, @".venv\Scripts\python.exe")))
        {
            int code = RunBat(dir, "setup_windows.bat", true);
            if (code != 0)
                throw new Exception("설치 스크립트가 실패했습니다(종료 코드 " + code + "). 설치 창의 메시지를 확인한 뒤 ChoiStudio.exe 를 다시 실행하세요.");
        }
        if (!HasFlag(args, "--no-launch")) RunBat(dir, "run_studio.bat", false);
        return 0;
    }

    static bool IsInstall(string d)
    {
        return d != null && File.Exists(Path.Combine(d, "run_studio.bat")) && Directory.Exists(Path.Combine(d, "studio"));
    }

    static string PickFolder()
    {
        using (var f = new FolderBrowserDialog())
        {
            f.Description = "Choi Studio 를 설치할 위치를 고르세요 (그 안에 ChoiStudio 폴더를 만듭니다)";
            f.SelectedPath = Directory.Exists(@"D:\") ? @"D:\" : @"C:\";
            if (f.ShowDialog() != DialogResult.OK) return null;
            string p = f.SelectedPath;
            bool named = Path.GetFileName(p.TrimEnd('\\')).Equals("ChoiStudio", StringComparison.OrdinalIgnoreCase);
            return named || IsInstall(p) ? p : Path.Combine(p, "ChoiStudio");
        }
    }

    static WebClient Web()
    {
        var w = new WebClient();
        w.Headers[HttpRequestHeader.UserAgent] = "ChoiStudio-Installer";
        return w;
    }

    static string LatestSha()
    {
        try
        {
            using (var w = Web())
            {
                w.Headers[HttpRequestHeader.Accept] = "application/vnd.github.sha";
                string s = w.DownloadString("https://api.github.com/repos/" + Repo + "/commits/" + Branch).Trim();
                return s.Length == 40 ? s : null;
            }
        }
        catch (WebException) { return null; }
    }

    static void Install(string sha, string dir)
    {
        string zip = Path.Combine(Path.GetTempPath(), "choi_studio_" + sha + ".zip");
        using (var w = Web()) w.DownloadFile("https://codeload.github.com/" + Repo + "/zip/" + sha, zip);
        string root = Path.GetFullPath(dir).TrimEnd('\\') + "\\";
        using (var z = ZipFile.OpenRead(zip))
        {
            foreach (var e in z.Entries)
            {
                int cut = e.FullName.IndexOf('/');  // zip 맨 위 '저장소-커밋/' 폴더를 벗긴다
                string rel = cut < 0 ? "" : e.FullName.Substring(cut + 1);
                if (rel.Length == 0 || rel.EndsWith("/")) continue;
                string dest = Path.GetFullPath(Path.Combine(root, rel.Replace('/', '\\')));
                if (!dest.StartsWith(root, StringComparison.OrdinalIgnoreCase)) continue;  // 폴더 밖으로 나가는 항목 거부
                Directory.CreateDirectory(Path.GetDirectoryName(dest));
                e.ExtractToFile(dest, true);
            }
        }
        File.Delete(zip);
    }

    static int RunBat(string dir, string bat, bool wait)
    {
        var psi = new ProcessStartInfo("cmd.exe", "/c \"\"" + Path.Combine(dir, bat) + "\" --elevated\"");
        psi.WorkingDirectory = dir;
        psi.UseShellExecute = false;           // 환경 변수를 넘기려면 false
        psi.EnvironmentVariables["CHOI_SETUP_AUTO"] = "1";
        var p = Process.Start(psi);
        if (!wait) return 0;
        p.WaitForExit();
        return p.ExitCode;
    }

    static string ArgValue(string[] a, string name)
    {
        for (int i = 0; i < a.Length - 1; i++) if (a[i] == name) return a[i + 1];
        return null;
    }

    static bool HasFlag(string[] a, string name) { return Array.IndexOf(a, name) >= 0; }
}
