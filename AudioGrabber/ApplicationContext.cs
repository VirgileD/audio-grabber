using AudioGrabber.Services;
using AudioGrabber.Forms;
using AudioGrabber.Resources;
using System.Media;

namespace AudioGrabber;

/// <summary>
/// Main application controller managing lifetime and components
/// </summary>
public class AudioGrabberApplicationContext : ApplicationContext
{
    private readonly NotifyIcon _trayIcon;
    private readonly ConfigurationManager _configManager;
    private readonly AudioRecorderService _audioRecorder;
    private readonly GlobalHotkeyManager _hotkeyManager;
    
    // Icons for different states
    private readonly Icon _idleIcon;
    private readonly Icon _recordingIcon;
    private readonly Icon _errorIcon;
    
    // Context menu items
    private readonly ToolStripMenuItem _settingsMenuItem;
    private readonly ToolStripMenuItem _openFolderMenuItem;
    private readonly ToolStripMenuItem _removeSettingsMenuItem;
    private readonly ToolStripMenuItem _exitMenuItem;
    
    public AudioGrabberApplicationContext()
    {
        // Initialize services
        _configManager = new ConfigurationManager();
        _configManager.LoadSettings();
        
        _audioRecorder = new AudioRecorderService();
        _hotkeyManager = new GlobalHotkeyManager();
        
        // Generate icons for different states
        _idleIcon = IconGenerator.CreateIdleIcon();
        _recordingIcon = IconGenerator.CreateRecordingIcon();
        _errorIcon = IconGenerator.CreateErrorIcon();
        
        // Create tray icon
        _trayIcon = new NotifyIcon
        {
            Text = "AudioGrabber - Idle",
            Visible = true,
            Icon = _idleIcon
        };
        
        // Create context menu
        _settingsMenuItem = new ToolStripMenuItem("Settings...", null, OnSettings);
        _openFolderMenuItem = new ToolStripMenuItem("Open Recordings Folder", null, OnOpenFolder);
        _removeSettingsMenuItem = new ToolStripMenuItem("Remove All Settings", null, OnRemoveSettings);
        _exitMenuItem = new ToolStripMenuItem("Exit", null, OnExit);
        
        var contextMenu = new ContextMenuStrip();
        contextMenu.Items.Add(_settingsMenuItem);
        contextMenu.Items.Add(_openFolderMenuItem);
        contextMenu.Items.Add(new ToolStripSeparator());
        contextMenu.Items.Add(_removeSettingsMenuItem);
        contextMenu.Items.Add(new ToolStripSeparator());
        contextMenu.Items.Add(_exitMenuItem);
        
        _trayIcon.ContextMenuStrip = contextMenu;
        
        // Wire up events
        _audioRecorder.StateChanged += OnRecordingStateChanged;
        _audioRecorder.ErrorOccurred += OnRecordingError;
        _hotkeyManager.HotkeyPressed += OnHotkeyPressed;
        
        // Register hotkey
        RegisterHotkey();
        
        // Apply startup settings
        ApplyStartupSettings();
    }
    
    private void RegisterHotkey()
    {
        var settings = _configManager.Settings;
        if (!_hotkeyManager.RegisterHotkey(settings.HotkeyKey, settings.HotkeyModifiers))
        {
            MessageBox.Show(
                "Failed to register hotkey. It may already be in use by another application.",
                "AudioGrabber",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning
            );
        }
    }
    
    private void ApplyStartupSettings()
    {
        // Ensure registry entry matches StartWithWindows setting
        var settings = _configManager.Settings;
        SetStartWithWindows(settings.StartWithWindows);
    }
    
    private void SetStartWithWindows(bool enable)
    {
        try
        {
            using var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(
                @"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", true);
            
            if (key != null)
            {
                if (enable)
                {
                    var exePath = Application.ExecutablePath;
                    key.SetValue("AudioGrabber", exePath);
                }
                else
                {
                    key.DeleteValue("AudioGrabber", false);
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error setting startup registry: {ex.Message}");
        }
    }
    
    private void OnHotkeyPressed(object? sender, EventArgs e)
    {
        ToggleRecording();
    }
    
    private void ToggleRecording()
    {
        try
        {
            if (_audioRecorder.IsRecording)
            {
                _audioRecorder.StopRecording();
            }
            else
            {
                var settings = _configManager.Settings;
                var fileName = string.Format(settings.FileNamePattern, DateTime.Now);
                var filePath = Path.Combine(settings.OutputFolder, fileName);
                
                _audioRecorder.StartRecording(filePath);
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                $"Error toggling recording: {ex.Message}",
                "AudioGrabber Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
    
    private void OnRecordingStateChanged(object? sender, RecordingStateChangedEventArgs e)
    {
        // Update icon and tooltip based on state
        if (e.IsRecording)
        {
            _trayIcon.Icon = _recordingIcon;
            _trayIcon.Text = "AudioGrabber - Recording";
            SystemSounds.Beep.Play();
        }
        else
        {
            _trayIcon.Icon = _idleIcon;
            _trayIcon.Text = "AudioGrabber - Idle";
            SystemSounds.Beep.Play();
        }
    }
    
    private void OnRecordingError(object? sender, RecordingErrorEventArgs e)
    {
        _trayIcon.Icon = _errorIcon;
        _trayIcon.Text = "AudioGrabber - Error";
        
        if (_configManager.Settings.ShowNotifications)
        {
            MessageBox.Show(
                e.Message,
                "AudioGrabber Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
    
    private void OnSettings(object? sender, EventArgs e)
    {
        using var settingsForm = new SettingsForm(_configManager);
        var result = settingsForm.ShowDialog();
        
        if (result == DialogResult.OK)
        {
            // Re-register hotkey with new settings
            _hotkeyManager.UnregisterHotkey();
            RegisterHotkey();
            
            // Update startup registry if changed
            SetStartWithWindows(_configManager.Settings.StartWithWindows);
        }
    }
    
    private void OnOpenFolder(object? sender, EventArgs e)
    {
        try
        {
            var folder = _configManager.Settings.OutputFolder;
            Directory.CreateDirectory(folder);
            System.Diagnostics.Process.Start("explorer.exe", folder);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                $"Error opening folder: {ex.Message}",
                "AudioGrabber Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
    
    private void OnRemoveSettings(object? sender, EventArgs e)
    {
        var result = MessageBox.Show(
            "This will remove all settings and registry entries. Continue?",
            "Remove All Settings",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Warning
        );
        
        if (result == DialogResult.Yes)
        {
            try
            {
                // Remove registry entry
                SetStartWithWindows(false);
                
                // Remove settings file
                var appDataPath = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "AudioGrabber"
                );
                
                if (Directory.Exists(appDataPath))
                {
                    Directory.Delete(appDataPath, true);
                }
                
                MessageBox.Show(
                    "All settings removed. Application will now exit.",
                    "AudioGrabber",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information
                );
                
                Application.Exit();
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    $"Error removing settings: {ex.Message}",
                    "AudioGrabber Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }
    }
    
    private void OnExit(object? sender, EventArgs e)
    {
        // Stop recording if active
        if (_audioRecorder.IsRecording)
        {
            _audioRecorder.StopRecording();
        }
        
        // Cleanup
        _hotkeyManager.Dispose();
        _audioRecorder.Dispose();
        _trayIcon.Visible = false;
        _trayIcon.Dispose();
        
        Application.Exit();
    }
    
    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _hotkeyManager?.Dispose();
            _audioRecorder?.Dispose();
            _trayIcon?.Dispose();
            _idleIcon?.Dispose();
            _recordingIcon?.Dispose();
            _errorIcon?.Dispose();
        }
        
        base.Dispose(disposing);
    }
}
