using System.Text.Json.Serialization;
using System.Windows.Forms;

namespace AudioGrabber.Models;

/// <summary>
/// Application configuration settings
/// </summary>
public class AppSettings
{
    // Recording Settings
    // Default to a local, non-synced folder: OneDrive-synced folders (like Documents)
    // can stall file writes while recording. Falls back to Documents if there is no D: drive.
    public string OutputFolder { get; set; } = Directory.Exists(@"D:\")
        ? @"D:\Projects\audio-grabber"
        : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "AudioGrabber");
    
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
