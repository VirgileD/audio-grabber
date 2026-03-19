using AudioGrabber.Models;
using AudioGrabber.Services;
using System.Windows.Forms;

namespace AudioGrabber.Forms;

/// <summary>
/// Settings dialog for application configuration
/// </summary>
public partial class SettingsForm : Form
{
    private readonly ConfigurationManager _configManager;
    private AppSettings _workingSettings;
    
    // UI Controls
    private GroupBox _recordingGroupBox = null!;
    private Label _outputFolderLabel = null!;
    private TextBox _outputFolderTextBox = null!;
    private Button _browseButton = null!;
    private Label _fileNamePatternLabel = null!;
    private TextBox _fileNamePatternTextBox = null!;
    private Label _previewLabel = null!;
    private Button _openFolderButton = null!;
    
    private GroupBox _hotkeyGroupBox = null!;
    private Label _hotkeyLabel = null!;
    private TextBox _hotkeyTextBox = null!;
    private Label _hotkeyInstructionsLabel = null!;
    
    private GroupBox _generalGroupBox = null!;
    private CheckBox _showNotificationsCheckBox = null!;
    private CheckBox _startWithWindowsCheckBox = null!;
    
    private Button _saveButton = null!;
    private Button _cancelButton = null!;
    private Button _resetButton = null!;
    
    private bool _capturingHotkey = false;
    private Keys _capturedKey = Keys.None;
    private KeyModifiers _capturedModifiers = KeyModifiers.None;
    
    public SettingsForm(ConfigurationManager configManager)
    {
        _configManager = configManager;
        _workingSettings = CloneSettings(_configManager.Settings);
        InitializeComponent();
        LoadSettings();
    }
    
    private void InitializeComponent()
    {
        // Form properties
        Text = "AudioGrabber Settings";
        Size = new Size(550, 520);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        
        // Recording Settings Group
        _recordingGroupBox = new GroupBox
        {
            Text = "Recording Settings",
            Location = new Point(12, 12),
            Size = new Size(510, 150)
        };
        
        _outputFolderLabel = new Label
        {
            Text = "Output Folder:",
            Location = new Point(10, 25),
            Size = new Size(100, 20)
        };
        
        _outputFolderTextBox = new TextBox
        {
            Location = new Point(10, 48),
            Size = new Size(400, 23),
            ReadOnly = true
        };
        
        _browseButton = new Button
        {
            Text = "Browse...",
            Location = new Point(415, 47),
            Size = new Size(80, 25)
        };
        _browseButton.Click += OnBrowseFolder;
        
        _fileNamePatternLabel = new Label
        {
            Text = "File Name Pattern:",
            Location = new Point(10, 80),
            Size = new Size(120, 20)
        };
        
        _fileNamePatternTextBox = new TextBox
        {
            Location = new Point(10, 103),
            Size = new Size(485, 23)
        };
        _fileNamePatternTextBox.TextChanged += OnFileNamePatternChanged;
        
        _previewLabel = new Label
        {
            Text = "Preview: Recording_2026-03-19_150230.wav",
            Location = new Point(10, 128),
            Size = new Size(485, 20),
            ForeColor = Color.Gray
        };
        
        _openFolderButton = new Button
        {
            Text = "Open Recordings Folder",
            Location = new Point(10, 155),
            Size = new Size(160, 25)
        };
        _openFolderButton.Click += OnOpenFolder;
        
        _recordingGroupBox.Controls.AddRange(new Control[]
        {
            _outputFolderLabel,
            _outputFolderTextBox,
            _browseButton,
            _fileNamePatternLabel,
            _fileNamePatternTextBox,
            _previewLabel
        });
        
        // Hotkey Settings Group
        _hotkeyGroupBox = new GroupBox
        {
            Text = "Hotkey Settings",
            Location = new Point(12, 195),
            Size = new Size(510, 100)
        };
        
        _hotkeyLabel = new Label
        {
            Text = "Recording Hotkey:",
            Location = new Point(10, 25),
            Size = new Size(120, 20)
        };
        
        _hotkeyTextBox = new TextBox
        {
            Location = new Point(10, 48),
            Size = new Size(200, 23),
            ReadOnly = true
        };
        _hotkeyTextBox.KeyDown += OnHotkeyKeyDown;
        _hotkeyTextBox.Enter += OnHotkeyEnter;
        _hotkeyTextBox.Leave += OnHotkeyLeave;
        
        _hotkeyInstructionsLabel = new Label
        {
            Text = "Click in the box and press the desired key combination",
            Location = new Point(220, 48),
            Size = new Size(280, 40),
            ForeColor = Color.Gray
        };
        
        _hotkeyGroupBox.Controls.AddRange(new Control[]
        {
            _hotkeyLabel,
            _hotkeyTextBox,
            _hotkeyInstructionsLabel
        });
        
        // General Settings Group
        _generalGroupBox = new GroupBox
        {
            Text = "General Settings",
            Location = new Point(12, 305),
            Size = new Size(510, 80)
        };
        
        _showNotificationsCheckBox = new CheckBox
        {
            Text = "Show error notifications",
            Location = new Point(10, 25),
            Size = new Size(200, 20)
        };
        
        _startWithWindowsCheckBox = new CheckBox
        {
            Text = "Start with Windows",
            Location = new Point(10, 50),
            Size = new Size(200, 20)
        };
        
        _generalGroupBox.Controls.AddRange(new Control[]
        {
            _showNotificationsCheckBox,
            _startWithWindowsCheckBox
        });
        
        // Buttons
        _saveButton = new Button
        {
            Text = "Save",
            Location = new Point(280, 400),
            Size = new Size(75, 30),
            DialogResult = DialogResult.OK
        };
        _saveButton.Click += OnSave;
        
        _cancelButton = new Button
        {
            Text = "Cancel",
            Location = new Point(365, 400),
            Size = new Size(75, 30),
            DialogResult = DialogResult.Cancel
        };
        
        _resetButton = new Button
        {
            Text = "Reset to Defaults",
            Location = new Point(12, 400),
            Size = new Size(130, 30)
        };
        _resetButton.Click += OnReset;
        
        // Add all controls to form
        Controls.AddRange(new Control[]
        {
            _recordingGroupBox,
            _openFolderButton,
            _hotkeyGroupBox,
            _generalGroupBox,
            _saveButton,
            _cancelButton,
            _resetButton
        });
        
        AcceptButton = _saveButton;
        CancelButton = _cancelButton;
    }
    
    private void LoadSettings()
    {
        _outputFolderTextBox.Text = _workingSettings.OutputFolder;
        _fileNamePatternTextBox.Text = _workingSettings.FileNamePattern;
        _showNotificationsCheckBox.Checked = _workingSettings.ShowNotifications;
        _startWithWindowsCheckBox.Checked = _workingSettings.StartWithWindows;
        
        UpdateHotkeyDisplay();
        UpdateFileNamePreview();
    }
    
    private void UpdateHotkeyDisplay()
    {
        var modifiers = new List<string>();
        
        if ((_workingSettings.HotkeyModifiers & KeyModifiers.Control) != 0)
            modifiers.Add("Ctrl");
        if ((_workingSettings.HotkeyModifiers & KeyModifiers.Alt) != 0)
            modifiers.Add("Alt");
        if ((_workingSettings.HotkeyModifiers & KeyModifiers.Shift) != 0)
            modifiers.Add("Shift");
        if ((_workingSettings.HotkeyModifiers & KeyModifiers.Win) != 0)
            modifiers.Add("Win");
        
        var hotkeyText = modifiers.Count > 0
            ? $"{string.Join("+", modifiers)}+{_workingSettings.HotkeyKey}"
            : _workingSettings.HotkeyKey.ToString();
        
        _hotkeyTextBox.Text = hotkeyText;
    }
    
    private void UpdateFileNamePreview()
    {
        try
        {
            var preview = string.Format(_fileNamePatternTextBox.Text, DateTime.Now);
            _previewLabel.Text = $"Preview: {preview}";
            _previewLabel.ForeColor = Color.Gray;
        }
        catch
        {
            _previewLabel.Text = "Preview: Invalid pattern";
            _previewLabel.ForeColor = Color.Red;
        }
    }
    
    private void OnBrowseFolder(object? sender, EventArgs e)
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "Select output folder for recordings",
            SelectedPath = _outputFolderTextBox.Text,
            ShowNewFolderButton = true
        };
        
        if (dialog.ShowDialog() == DialogResult.OK)
        {
            _outputFolderTextBox.Text = dialog.SelectedPath;
            _workingSettings.OutputFolder = dialog.SelectedPath;
        }
    }
    
    private void OnOpenFolder(object? sender, EventArgs e)
    {
        try
        {
            var folder = _outputFolderTextBox.Text;
            Directory.CreateDirectory(folder);
            System.Diagnostics.Process.Start("explorer.exe", folder);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                $"Error opening folder: {ex.Message}",
                "Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
    
    private void OnFileNamePatternChanged(object? sender, EventArgs e)
    {
        UpdateFileNamePreview();
    }
    
    private void OnHotkeyEnter(object? sender, EventArgs e)
    {
        _capturingHotkey = true;
        _hotkeyTextBox.Text = "Press key combination...";
        _hotkeyTextBox.BackColor = Color.LightYellow;
    }
    
    private void OnHotkeyLeave(object? sender, EventArgs e)
    {
        _capturingHotkey = false;
        _hotkeyTextBox.BackColor = SystemColors.Window;
        UpdateHotkeyDisplay();
    }
    
    private void OnHotkeyKeyDown(object? sender, KeyEventArgs e)
    {
        if (!_capturingHotkey)
            return;
        
        e.SuppressKeyPress = true;
        e.Handled = true;
        
        // Ignore modifier keys by themselves
        if (e.KeyCode == Keys.ControlKey || e.KeyCode == Keys.ShiftKey ||
            e.KeyCode == Keys.Menu || e.KeyCode == Keys.LWin || e.KeyCode == Keys.RWin)
        {
            return;
        }
        
        // Capture the key and modifiers
        _capturedKey = e.KeyCode;
        _capturedModifiers = KeyModifiers.None;
        
        if (e.Control)
            _capturedModifiers |= KeyModifiers.Control;
        if (e.Alt)
            _capturedModifiers |= KeyModifiers.Alt;
        if (e.Shift)
            _capturedModifiers |= KeyModifiers.Shift;
        
        // Update working settings
        _workingSettings.HotkeyKey = _capturedKey;
        _workingSettings.HotkeyModifiers = _capturedModifiers;
        
        // Update display
        UpdateHotkeyDisplay();
        _hotkeyTextBox.BackColor = SystemColors.Window;
        _capturingHotkey = false;
    }
    
    private void OnSave(object? sender, EventArgs e)
    {
        // Validate settings
        if (string.IsNullOrWhiteSpace(_outputFolderTextBox.Text))
        {
            MessageBox.Show(
                "Output folder cannot be empty.",
                "Validation Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning
            );
            return;
        }
        
        if (string.IsNullOrWhiteSpace(_fileNamePatternTextBox.Text))
        {
            MessageBox.Show(
                "File name pattern cannot be empty.",
                "Validation Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning
            );
            return;
        }
        
        // Test file name pattern
        try
        {
            string.Format(_fileNamePatternTextBox.Text, DateTime.Now);
        }
        catch
        {
            MessageBox.Show(
                "Invalid file name pattern. Use {0:format} for date/time formatting.",
                "Validation Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning
            );
            return;
        }
        
        // Update settings
        _workingSettings.OutputFolder = _outputFolderTextBox.Text;
        _workingSettings.FileNamePattern = _fileNamePatternTextBox.Text;
        _workingSettings.ShowNotifications = _showNotificationsCheckBox.Checked;
        _workingSettings.StartWithWindows = _startWithWindowsCheckBox.Checked;
        
        // Copy working settings to actual settings
        _configManager.Settings.OutputFolder = _workingSettings.OutputFolder;
        _configManager.Settings.FileNamePattern = _workingSettings.FileNamePattern;
        _configManager.Settings.HotkeyKey = _workingSettings.HotkeyKey;
        _configManager.Settings.HotkeyModifiers = _workingSettings.HotkeyModifiers;
        _configManager.Settings.ShowNotifications = _workingSettings.ShowNotifications;
        _configManager.Settings.StartWithWindows = _workingSettings.StartWithWindows;
        
        // Save to file
        _configManager.SaveSettings();
        
        DialogResult = DialogResult.OK;
        Close();
    }
    
    private void OnReset(object? sender, EventArgs e)
    {
        var result = MessageBox.Show(
            "Reset all settings to default values?",
            "Reset Settings",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Question
        );
        
        if (result == DialogResult.Yes)
        {
            _configManager.ResetToDefaults();
            _workingSettings = CloneSettings(_configManager.Settings);
            LoadSettings();
        }
    }
    
    private AppSettings CloneSettings(AppSettings source)
    {
        return new AppSettings
        {
            OutputFolder = source.OutputFolder,
            FileNamePattern = source.FileNamePattern,
            SampleRate = source.SampleRate,
            BitsPerSample = source.BitsPerSample,
            Channels = source.Channels,
            HotkeyKey = source.HotkeyKey,
            HotkeyModifiers = source.HotkeyModifiers,
            ShowNotifications = source.ShowNotifications,
            StartWithWindows = source.StartWithWindows,
            MinimizeToTray = source.MinimizeToTray
        };
    }
}
