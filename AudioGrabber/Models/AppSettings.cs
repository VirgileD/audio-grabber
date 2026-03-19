using System.Windows.Forms;

namespace AudioGrabber.Models;

/// <summary>
/// Application configuration settings
/// </summary>
public class AppSettings
{
    // Recording Settings
    public string OutputFolder { get; set; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
        "AudioGrabber"
    );
    
    public string FileNamePattern { get; set; } = "Recording_{0:yyyy-MM-dd_HHmmss}.wav";
    public int SampleRate { get; set; } = 44100;
    public int BitsPerSample { get; set; } = 16;
    public int Channels { get; set; } = 2;
    
    // Hotkey Settings
    public Keys HotkeyKey { get; set; } = Keys.R;
    public KeyModifiers HotkeyModifiers { get; set; } = KeyModifiers.Control;
    
    // UI Settings
    public bool ShowNotifications { get; set; } = true; // For error notifications only
    public bool StartWithWindows { get; set; } = true;
    public bool MinimizeToTray { get; set; } = true;
}

[Flags]
public enum KeyModifiers
{
    None = 0,
    Alt = 1,
    Control = 2,
    Shift = 4,
    Win = 8
}
