using System.Text.Json.Serialization;
using System.Windows.Forms;

namespace AudioGrabber.Models;

/// <summary>
/// Application configuration settings
/// </summary>
public class AppSettings
{
    // Recording Settings
    // Absolute path, or a path relative to the folder containing AudioGrabber.exe:
    // "./" (the default) records next to the executable, wherever it is.
    // Avoid OneDrive-synced folders (like Documents): syncing can stall file writes.
    public string OutputFolder { get; set; } = "./";

    /// <summary>
    /// Full path of OutputFolder. Use this, never OutputFolder, to access the disk.
    /// </summary>
    [JsonIgnore]
    public string ResolvedOutputFolder => ResolveFolder(OutputFolder);

    /// <summary>
    /// Resolve a folder setting: relative paths are relative to the executable's
    /// folder, not the working directory (which is C:\Windows\System32 when the app
    /// is started at Windows sign-in).
    /// </summary>
    public static string ResolveFolder(string folder) =>
        Path.GetFullPath(folder, AppContext.BaseDirectory);
    
    public string FileNamePattern { get; set; } = "Recording_{0:yyyy-MM-dd_HHmmss}.mp3";
    
    // Hotkey Settings
    // Stored in settings.json as readable text ("Hotkey": "Ctrl+R"), see HotkeyText.
    [JsonIgnore]
    public Keys HotkeyKey { get; set; } = Keys.R;
    [JsonIgnore]
    public KeyModifiers HotkeyModifiers { get; set; } = KeyModifiers.Control;

    /// <summary>
    /// The hotkey as text, e.g. "Ctrl+R" or "Ctrl+Shift+F9". An invalid value is
    /// ignored (the hotkey keeps its previous/default value).
    /// </summary>
    public string Hotkey
    {
        get => HotkeyText.Format(HotkeyKey, HotkeyModifiers);
        set
        {
            if (HotkeyText.TryParse(value, out var key, out var modifiers))
            {
                HotkeyKey = key;
                HotkeyModifiers = modifiers;
            }
            else
            {
                Console.WriteLine($"Warning: Invalid hotkey '{value}' in settings, using {Hotkey}");
            }
        }
    }

    // UI Settings
    public bool ShowNotifications { get; set; } = true; // For error notifications only
    public bool StartWithWindows { get; set; } = true;
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
