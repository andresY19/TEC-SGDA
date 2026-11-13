using System;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

internal static class Setup
{
    [STAThread]
    private static int Main(string[] args)
    {
        bool verify = args.Length == 2 && args[0] == "--verify-install";
        if (args.Length != 0 && !verify) return 2;
        try
        {
            string folder = verify ? Path.GetFullPath(args[1]) :
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "TEC-SGDEA");
            Directory.CreateDirectory(folder);
            string application = Path.Combine(folder, "TEC-SGDEA.exe");
            string staging = Path.Combine(folder, Guid.NewGuid().ToString("N") + ".tmp");
            try
            {
                using (Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("client.exe"))
                using (FileStream output = new FileStream(staging, FileMode.CreateNew))
                {
                    payload.CopyTo(output);
                    output.Flush(true);
                }
                if (File.Exists(application))
                    File.Replace(staging, application, null);
                else
                    File.Move(staging, application);
            }
            finally
            {
                if (File.Exists(staging)) File.Delete(staging);
            }
            if (!verify)
            {
                string shortcut = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "TEC-SGDEA.lnk");
                dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
                dynamic link = shell.CreateShortcut(shortcut);
                link.TargetPath = application;
                link.WorkingDirectory = folder;
                link.Save();
                MessageBox.Show("TEC-SGDEA está disponible en el menú Inicio.", "TEC-SGDEA");
            }
            return 0;
        }
        catch (Exception error)
        {
            if (!verify) MessageBox.Show(error.Message, "TEC-SGDEA");
            return 1;
        }
    }
}
