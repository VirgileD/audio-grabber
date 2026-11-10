using System.Text.Encodings.Web;
using System.Text.Json;
using System.Windows.Forms;
using AudioGrabber.Models;

namespace AudioGrabber.Services;

/// <summary>
/// Manages application settings persistence
/// </summary>
public class ConfigurationManager
{
    private readonly string _settingsPath;
    
    public AppSettings Settings { get; private set; }
    
    public ConfigurationManager()
    {
        var appDataPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "AudioGrabber"
        );
        
        Directory.CreateDirectory(appDataPath);
        _settingsPath = Path.Combine(appDataPath, "settings.json");
        
        Settings = new AppSettings();
    }
    
    /// <summary>
    /// Older settings files stored the hotkey as numbers ("HotkeyKey": 82,
    /// "HotkeyModifiers": 2). Carry such a hotkey over when there is no "Hotkey"
    /// text yet; it is written back in the new format on the next save.
    /// </summary>
    private static void MigrateNumericHotkey(string json, AppSettings settings)
    {
        try
        {
            using var document = JsonDocument.Parse(json);
            var root = document.RootElement;
            if (root.TryGetProperty("Hotkey", out _)
                || !root.TryGetProperty("HotkeyKey", out var keyElement)
                || !keyElement.TryGetInt32(out var keyValue))
            {
                return;
            }

            var modifiers = KeyModifiers.None;
            if (root.TryGetProperty("HotkeyModifiers", out var modifiersElement)
                && modifiersElement.TryGetInt32(out var modifiersValue))
            {
                modifiers = (KeyModifiers)modifiersValue;
            }

            var text = HotkeyText.Format((Keys)keyValue, modifiers);
            if (HotkeyText.TryParse(text, out _, out _))
            {
                settings.Hotkey = text;
            }
        }
        catch (JsonException)
        {
            // Unreadable file: handled by the normal loading path
        }
    }

    /// <summary>
    /// Load settings from JSON file
    /// </summary>
    public void LoadSettings()
    {
        try
        {
            if (File.Exists(_settingsPath))
            {
                var json = File.ReadAllText(_settingsPath);
                var loadedSettings = JsonSerializer.Deserialize<AppSettings>(json);
                
                if (loadedSettings != null)
                {
                    MigrateNumericHotkey(json, loadedSettings);

                    // Validate loaded settings
                    if (string.IsNullOrWhiteSpace(loadedSettings.OutputFolder))
                    {
                        Console.WriteLine("Warning: Invalid output folder in settings, using default");
                        loadedSettings.OutputFolder = new AppSettings().OutputFolder;
                    }
                    
                    if (string.IsNullOrWhiteSpace(loadedSettings.FileNamePattern))
                    {
                        Console.WriteLine("Warning: Invalid file name pattern in settings, using default");
                        loadedSettings.FileNamePattern = new AppSettings().FileNamePattern;
                    }
                    
                    Settings = loadedSettings;
                }
                else
                {
                    Console.WriteLine("Warning: Could not deserialize settings, using defaults");
                    Settings = new AppSettings();
                }
            }
            else
            {
                Settings = new AppSettings();
                SaveSettings(); // Create default settings file
            }
        }
        catch (JsonException ex)
        {
            // JSON parsing error - corrupt settings file
            Console.WriteLine($"Error parsing settings file (corrupt JSON): {ex.Message}");
            Console.WriteLine("Using default settings and backing up corrupt file");
            
            // Backup corrupt file
            try
            {
                if (File.Exists(_settingsPath))
                {
                    var backupPath = _settingsPath + ".corrupt." + DateTime.Now.ToString("yyyyMMddHHmmss");
                    File.Copy(_settingsPath, backupPath);
                    Console.WriteLine($"Corrupt settings backed up to: {backupPath}");
                }
            }
            catch (Exception backupEx)
            {
                Console.WriteLine($"Could not backup corrupt settings: {backupEx.Message}");
            }
            
            Settings = new AppSettings();
            SaveSettings(); // Overwrite with defaults
        }
        catch (Exception ex)
        {
            // Other error - use default settings
            Console.WriteLine($"Error loading settings: {ex.Message}");
            Settings = new AppSettings();
        }
    }
    
    /// <summary>
    /// Save settings to JSON file
    /// </summary>
    public void SaveSettings()
    {
        try
        {
            // Validate settings before saving
            if (string.IsNullOrWhiteSpace(Settings.OutputFolder))
            {
                throw new InvalidOperationException("Output folder cannot be empty");
            }
            
            if (string.IsNullOrWhiteSpace(Settings.FileNamePattern))
            {
                throw new InvalidOperationException("File name pattern cannot be empty");
            }
            
            var options = new JsonSerializerOptions
            {
                WriteIndented = true,
                // Keep the file readable: write "Ctrl+R", not "Ctrl+R"
                Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            };
            
            var json = JsonSerializer.Serialize(Settings, options);
            
            // Write to temporary file first
            var tempPath = _settingsPath + ".tmp";
            File.WriteAllText(tempPath, json);
            
            // Backup existing file if it exists
            if (File.Exists(_settingsPath))
            {
                var backupPath = _settingsPath + ".bak";
                File.Copy(_settingsPath, backupPath, true);
            }
            
            // Move temp file to actual location
            File.Move(tempPath, _settingsPath, true);
            
            // Clean up backup after successful save
            var backup = _settingsPath + ".bak";
            if (File.Exists(backup))
            {
                try
                {
                    File.Delete(backup);
                }
                catch
                {
                    // Ignore backup deletion errors
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error saving settings: {ex.Message}");
            throw new InvalidOperationException($"Failed to save settings: {ex.Message}", ex);
        }
    }
    
    /// <summary>
    /// Reset settings to defaults
    /// </summary>
    public void ResetToDefaults()
    {
        Settings = new AppSettings();
        SaveSettings();
    }
}
