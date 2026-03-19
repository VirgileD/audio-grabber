using System.Text.Json;
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
    /// Load settings from JSON file
    /// </summary>
    public void LoadSettings()
    {
        try
        {
            if (File.Exists(_settingsPath))
            {
                var json = File.ReadAllText(_settingsPath);
                Settings = JsonSerializer.Deserialize<AppSettings>(json) ?? new AppSettings();
            }
            else
            {
                Settings = new AppSettings();
                SaveSettings(); // Create default settings file
            }
        }
        catch (Exception ex)
        {
            // Log error and use default settings
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
            var options = new JsonSerializerOptions
            {
                WriteIndented = true
            };
            
            var json = JsonSerializer.Serialize(Settings, options);
            File.WriteAllText(_settingsPath, json);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error saving settings: {ex.Message}");
            throw;
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
