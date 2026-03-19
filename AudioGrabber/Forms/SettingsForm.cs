using AudioGrabber.Models;
using AudioGrabber.Services;

namespace AudioGrabber.Forms;

/// <summary>
/// Settings dialog for application configuration
/// </summary>
public partial class SettingsForm : Form
{
    private readonly ConfigurationManager _configManager;
    
    // UI Controls (to be implemented in Phase 3)
    private TextBox? _outputFolderTextBox;
    private Button? _browseButton;
    private TextBox? _fileNamePatternTextBox;
    private Label? _previewLabel;
    private TextBox? _hotkeyTextBox;
    private CheckBox? _showNotificationsCheckBox;
    private CheckBox? _startWithWindowsCheckBox;
    private Button? _saveButton;
    private Button? _cancelButton;
    private Button? _resetButton;
    
    public SettingsForm(ConfigurationManager configManager)
    {
        _configManager = configManager;
        InitializeComponent();
    }
    
    private void InitializeComponent()
    {
        // UI initialization will be implemented in Phase 3
        Text = "AudioGrabber Settings";
        Size = new Size(500, 400);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
    }
    
    // Event handlers and logic will be implemented in Phase 3
}
