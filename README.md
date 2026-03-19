# AudioGrabber

A lightweight Windows system tray application for capturing system audio (and microphone) with a global hotkey.

## Overview

AudioGrabber is a .NET 8 Windows Forms application that runs in the system tray and captures all system audio plus microphone input when activated via a global hotkey. The application provides a simple, efficient way to record both system audio output and microphone input simultaneously, perfect for recording video calls, gaming sessions, or any scenario where you need to capture both your voice and system sounds.

## Features

### Core Features
- **System Tray Operation**: Runs quietly in the background with minimal UI
- **Global Hotkey**: Toggle recording on/off with Ctrl+R (fully configurable)
- **Dual Audio Capture**: Simultaneously captures system audio output AND microphone input
- **Real-Time Mixing**: Combines both audio sources into a single recording
- **High Quality Audio**: Records in WAV format (IEEE Float 32-bit, system sample rate, stereo)
- **Automatic Naming**: Timestamp-based file naming with collision prevention
- **Visual Feedback**: Custom icons indicate recording state (idle/recording/error)
- **Audio Feedback**: Simple beep sounds when starting/stopping recording
- **Comprehensive Logging**: Each recording session generates a detailed log file

### User Interface
- **Settings Dialog**: Full-featured settings UI with all configuration options
- **Output Folder Selection**: Browse and select custom output folder
- **File Name Pattern**: Customizable with real-time preview
- **Hotkey Capture**: Interactive hotkey configuration (supports Ctrl, Alt, Shift, Win modifiers)
- **General Settings**: Toggle error notifications and startup with Windows

### Advanced Features
- **Single Instance**: Prevents multiple copies from running simultaneously
- **Start with Windows**: Optional automatic startup (configurable)
- **Remove All Settings**: Clean uninstall option that removes all settings and registry entries
- **Disk Space Check**: Validates sufficient disk space before recording (100MB minimum)
- **Corrupt Settings Recovery**: Automatically backs up and recovers from corrupt configuration files
- **Atomic Settings Save**: Prevents settings corruption on power loss or crash
- **Edge Case Handling**: Comprehensive error handling for 10+ edge cases

## System Requirements

- **Operating System**: Windows 10/11 (x64)
- **.NET Runtime**: .NET 8 Desktop Runtime (required)
- **Audio Devices**: At least one audio output device (microphone optional)
- **Disk Space**: Minimum 100MB free space for recordings

## Technology Stack

- **Framework**: .NET 8
- **UI Framework**: Windows Forms
- **Audio Capture**: NAudio library v2.3.0 (WASAPI Loopback + WaveInEvent)
- **Configuration**: System.Text.Json (built-in)
- **Global Hotkeys**: Windows API (user32.dll P/Invoke)

## Project Structure

```
AudioGrabber/
├── AudioGrabber.sln
├── AudioGrabber/
│   ├── AudioGrabber.csproj
│   ├── Program.cs                    # Application entry point, single instance check
│   ├── ApplicationContext.cs         # Main application controller, system tray
│   ├── Services/
│   │   ├── AudioRecorderService.cs   # Dual audio capture and mixing
│   │   ├── GlobalHotkeyManager.cs    # Global hotkey handling
│   │   ├── ConfigurationManager.cs   # Settings persistence
│   │   └── RecordingLogger.cs        # Session logging
│   ├── Forms/
│   │   └── SettingsForm.cs           # Settings dialog UI
│   ├── Models/
│   │   └── AppSettings.cs            # Configuration model
│   ├── Resources/
│   │   ├── IconGenerator.cs          # Runtime icon generation
│   │   └── README.md                 # Icon documentation
│   └── app.manifest                  # DPI awareness configuration
├── plans/
│   ├── AudioGrabber_Implementation_Plan.md
│   └── AudioGrabber_MicrophoneMixing_Plan.md
├── PHASE1_IMPLEMENTATION.md          # Phase 1 documentation
├── PHASE2_IMPLEMENTATION.md          # Phase 2 documentation
├── PHASE2.5_IMPLEMENTATION.md        # Microphone mixing documentation
├── PHASE3_IMPLEMENTATION.md          # UI implementation documentation
├── PHASE4_IMPLEMENTATION.md          # Integration and polish documentation
├── README.md                         # This file
└── .gitignore
```

## Building the Project

### Prerequisites
- .NET 8 SDK installed
- Windows 10/11 (x64)

### Build Commands

```bash
# Navigate to project directory
cd AudioGrabber

# Restore dependencies
dotnet restore

# Build the project (Debug)
dotnet build

# Build the project (Release)
dotnet build --configuration Release

# Run the application (Debug)
dotnet run --project AudioGrabber/AudioGrabber.csproj

# Run the application (Release)
dotnet run --project AudioGrabber/AudioGrabber.csproj --configuration Release
```

## Usage

### First Launch
1. Launch AudioGrabber - it will appear in the system tray with a gray microphone icon
2. On first run, default settings are created automatically
3. The application will start with Windows by default (configurable in settings)

### Recording Audio
1. Press **Ctrl+R** (or your configured hotkey) to start recording
2. The tray icon turns **red** and you'll hear a beep sound
3. Both system audio and microphone are now being recorded
4. Press **Ctrl+R** again to stop recording
5. The tray icon returns to **gray** and you'll hear another beep sound
6. Recordings are saved to `Documents\AudioGrabber` by default

### System Tray Menu
Right-click the tray icon for options:
- **Settings...**: Open settings dialog
- **Open Recordings Folder**: Open output folder in Explorer
- **Remove All Settings**: Clean uninstall (removes settings and registry entries)
- **Exit**: Close the application

### Settings Dialog

#### Recording Settings
- **Output Folder**: Choose where recordings are saved (with Browse button)
- **File Name Pattern**: Customize filename format with date/time placeholders
  - Example: `Recording_{0:yyyy-MM-dd_HHmmss}.wav`
  - Real-time preview shows example filename
- **Open Recordings Folder**: Quick access button

#### Hotkey Settings
- **Recording Hotkey**: Click in the box and press your desired key combination
- Supports modifiers: Ctrl, Alt, Shift, Win
- Example combinations: Ctrl+R, Ctrl+Shift+F5, Alt+R, etc.

#### General Settings
- **Show error notifications**: Toggle error message popups (recommended: enabled)
- **Start with Windows**: Automatically launch on Windows startup

#### Action Buttons
- **Save**: Apply and save all changes
- **Cancel**: Discard changes and close
- **Reset to Defaults**: Restore all settings to default values

## Recording Logs

Each recording session generates a detailed log file alongside the WAV file:

**Log File Location**: Same folder as recording, with `.log` extension  
**Example**: `Recording_2026-03-19_150230.log`

**Log Contents**:
- Session start/end timestamps
- Recording duration
- Audio format details (sample rate, bit depth, channels)
- Audio device information
- Operating system information
- Application version
- Bytes recorded and file size
- Any warnings or errors during recording

**Example Log**:
```
================================================================================
AudioGrabber Recording Session Log
================================================================================
Recording File: Recording_2026-03-19_150230.wav
Session Started: 2026-03-19 15:02:30
--------------------------------------------------------------------------------

[15:02:30.123] INFO: Recording session started
[15:02:30.125] INFO: Audio Format: 48000 Hz, 32-bit Float, Stereo
[15:02:30.127] INFO: Audio Device: Speakers (Realtek High Definition Audio)
[15:02:30.128] INFO: Operating System: Windows 11 Pro (10.0.22621)
[15:02:30.130] INFO: Application Version: 1.0.0

[15:05:45.678] INFO: Recording session stopped
[15:05:45.680] INFO: Duration: 00:03:15.555
[15:05:45.682] INFO: Bytes Recorded: 51,891,200
[15:05:45.684] INFO: File Size: 51.89 MB

================================================================================
Session completed successfully
================================================================================
```

## Default Settings

- **Output Folder**: `%USERPROFILE%\Documents\AudioGrabber`
- **File Pattern**: `Recording_{0:yyyy-MM-dd_HHmmss}.wav`
- **Audio Format**: IEEE Float 32-bit, system sample rate, stereo
- **Hotkey**: Ctrl+R
- **Show Notifications**: Enabled (errors only)
- **Start with Windows**: Enabled

## Configuration Files

- **Settings File**: `%APPDATA%\AudioGrabber\settings.json`
- **Registry Entry**: `HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\AudioGrabber`

## Icon States

The system tray icon changes color to indicate application state:

- **Gray Microphone**: Idle (not recording)
- **Red Microphone with Sound Waves**: Recording active
- **Orange Microphone with Warning**: Error state

## Error Handling

AudioGrabber includes comprehensive error handling for:

- **No Audio Devices**: Clear error message if no audio devices available
- **Disk Full**: Checks for 100MB free space before recording
- **Corrupt Settings**: Automatically backs up and recovers from corrupt configuration
- **Invalid Settings**: Validates all settings, falls back to defaults
- **File Collisions**: Adds unique suffix if filename already exists
- **Folder Creation Failure**: Clear error message with instructions
- **Multiple Instances**: Prevents running multiple copies
- **Hotkey Conflicts**: Warns if hotkey is already in use
- **Settings Save Failure**: Atomic save prevents corruption
- **Unhandled Exceptions**: Global handlers prevent silent crashes

## Development Status

### ✅ Phase 1: Project Setup - COMPLETED
- [x] Create .NET 8 Windows Forms solution
- [x] Install NAudio package
- [x] Create project structure
- [x] Implement all core services
- [x] Implement application context
- [x] Configure build settings
- [x] Single instance check
- [x] Unhandled exception handlers

### ✅ Phase 2: Core Services Testing - COMPLETED
- [x] ConfigurationManager testing
- [x] RecordingLogger testing
- [x] AudioRecorderService testing
- [x] GlobalHotkeyManager testing
- [x] End-to-end workflow testing
- [x] Settings persistence verification

### ✅ Phase 2.5: Microphone Mixing - COMPLETED
- [x] Dual audio capture (system + microphone)
- [x] Real-time audio mixing
- [x] IEEE Float 32-bit format
- [x] Comprehensive testing
- [x] Documentation

### ✅ Phase 3: UI Implementation - COMPLETED
- [x] Complete SettingsForm with all controls
- [x] Custom icon generation system
- [x] Icon state management
- [x] Settings dialog integration
- [x] Hotkey capture control
- [x] Registry integration for startup

### ✅ Phase 4: Integration and Polish - COMPLETED
- [x] Component integration verification
- [x] Enhanced error handling
- [x] Edge case management (10+ cases)
- [x] Disk space checking
- [x] File collision prevention
- [x] Corrupt settings recovery
- [x] Atomic settings save
- [x] Production-ready quality

### 📋 Phase 5: Testing and Deployment - READY
- [ ] Comprehensive manual testing
- [ ] Clean Windows installation testing
- [ ] Performance testing
- [ ] User acceptance testing
- [ ] Optional: Create installer

## Troubleshooting

### Application Won't Start
- Ensure .NET 8 Desktop Runtime is installed
- Check if another instance is already running (check system tray)
- Try running as administrator

### Recording Not Working
- Check if audio devices are connected and enabled
- Verify output folder exists and is writable
- Check disk space (minimum 100MB required)
- Review log files for error details

### Hotkey Not Working
- Check if hotkey is already in use by another application
- Try a different key combination in settings
- Restart the application after changing hotkey

### No Microphone Audio
- Ensure microphone is connected and enabled in Windows
- Check microphone privacy settings in Windows
- Verify microphone is set as default recording device

### Settings Not Saving
- Check if `%APPDATA%\AudioGrabber` folder is writable
- Try running as administrator
- Use "Reset to Defaults" if settings are corrupt

### Application Not Starting with Windows
- Enable "Start with Windows" in settings
- Check registry entry exists: `HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\AudioGrabber`
- Try disabling and re-enabling the option

## Creating a Release Build

### Build Release Version

```bash
# Navigate to project directory
cd AudioGrabber

# Build release version
dotnet build --configuration Release

# Output location
# AudioGrabber\bin\Release\net8.0-windows\AudioGrabber.exe
```

### Publish Self-Contained Application (Optional)

To create a standalone executable that doesn't require .NET Runtime:

```bash
# Publish self-contained for Windows x64
dotnet publish --configuration Release --runtime win-x64 --self-contained true -p:PublishSingleFile=true

# Output location
# AudioGrabber\bin\Release\net8.0-windows\win-x64\publish\AudioGrabber.exe
```

**Note**: Self-contained builds are larger (~150MB) but don't require .NET Runtime installation.

### Publish Framework-Dependent Application (Recommended)

To create a smaller executable that requires .NET Runtime:

```bash
# Publish framework-dependent for Windows x64
dotnet publish --configuration Release --runtime win-x64 --self-contained false -p:PublishSingleFile=true

# Output location
# AudioGrabber\bin\Release\net8.0-windows\win-x64\publish\AudioGrabber.exe
```

**Note**: Framework-dependent builds are smaller (~5MB) but require .NET 8 Desktop Runtime.

## Deploying to a New Windows Host

### Prerequisites

The target Windows machine must have:
- **Windows 10 or Windows 11** (x64)
- **.NET 8 Desktop Runtime** (if using framework-dependent build)

### Installing .NET 8 Desktop Runtime

If you're using a framework-dependent build, the target machine needs .NET 8 Desktop Runtime:

1. **Download .NET 8 Desktop Runtime**:
   - Visit: https://dotnet.microsoft.com/download/dotnet/8.0
   - Download: ".NET Desktop Runtime 8.0.x" for Windows x64
   - File size: ~55MB

2. **Install the Runtime**:
   - Run the downloaded installer
   - Follow the installation wizard
   - No restart required

3. **Verify Installation**:
   ```bash
   dotnet --list-runtimes
   ```
   Should show: `Microsoft.WindowsDesktop.App 8.0.x`

### Deployment Steps

#### Option 1: Framework-Dependent (Recommended)

1. **Build the application** (on development machine):
   ```bash
   dotnet publish --configuration Release --runtime win-x64 --self-contained false -p:PublishSingleFile=true
   ```

2. **Copy files to target machine**:
   - Copy `AudioGrabber\bin\Release\net8.0-windows\win-x64\publish\AudioGrabber.exe`
   - File size: ~5MB

3. **Install .NET 8 Desktop Runtime** (if not already installed):
   - See "Installing .NET 8 Desktop Runtime" section above

4. **Run the application**:
   - Double-click `AudioGrabber.exe`
   - Application will appear in system tray

#### Option 2: Self-Contained (No Runtime Required)

1. **Build the application** (on development machine):
   ```bash
   dotnet publish --configuration Release --runtime win-x64 --self-contained true -p:PublishSingleFile=true
   ```

2. **Copy files to target machine**:
   - Copy `AudioGrabber\bin\Release\net8.0-windows\win-x64\publish\AudioGrabber.exe`
   - File size: ~150MB

3. **Run the application**:
   - Double-click `AudioGrabber.exe`
   - No .NET Runtime installation required
   - Application will appear in system tray

### First Run on New Machine

1. **Launch AudioGrabber**:
   - Double-click the executable
   - Application appears in system tray (gray microphone icon)

2. **Default Configuration**:
   - Settings file created at: `%APPDATA%\AudioGrabber\settings.json`
   - Output folder: `%USERPROFILE%\Documents\AudioGrabber`
   - Hotkey: Ctrl+R
   - Start with Windows: Enabled (registry entry created)

3. **Verify Functionality**:
   - Press Ctrl+R to start recording
   - Icon should turn red
   - Press Ctrl+R to stop recording
   - Check `Documents\AudioGrabber` for recording files

### Optional: Create Desktop Shortcut

1. Right-click `AudioGrabber.exe`
2. Select "Create shortcut"
3. Move shortcut to Desktop
4. Rename to "AudioGrabber"

### Optional: Pin to Taskbar

1. Right-click `AudioGrabber.exe`
2. Select "Pin to taskbar"

### Uninstallation

To completely remove AudioGrabber:

1. **Using the Application**:
   - Right-click system tray icon
   - Select "Remove All Settings"
   - Confirm removal
   - Application will exit and clean up all settings

2. **Manual Removal**:
   - Delete the executable file
   - Delete settings folder: `%APPDATA%\AudioGrabber`
   - Remove registry entry: `HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\AudioGrabber`

## Known Limitations

- Requires Windows 10/11 (x64) - not compatible with 32-bit Windows
- Cannot capture audio from DRM-protected content (by design)
- Microphone capture uses default recording device only
- Single hotkey for recording (cannot have separate start/stop hotkeys)
- No audio format conversion (always saves as WAV)

## Future Enhancements

Potential features for future versions:
- Audio format selection (MP3, FLAC, etc.)
- Multiple hotkey support
- Audio device selection in UI
- Recording scheduler
- Audio level meters
- Automatic file splitting for long recordings
- Cloud storage integration
- Installer package (WiX or Inno Setup)

## License

This project is for educational and personal use.

## Contributing

This is a personal project, but suggestions and feedback are welcome.

## Author

Created as part of the AudioGrabber implementation plan.

## Version History

- **v1.0.0** (2026-03-19): Initial release
  - System tray application
  - Dual audio capture (system + microphone)
  - Global hotkey support
  - Settings dialog
  - Comprehensive logging
  - Error handling and edge case management

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Review the log files in the recordings folder
3. Check the implementation documentation in the `PHASE*.md` files

## Acknowledgments

- **NAudio**: Excellent audio library for .NET
- **.NET Team**: For the robust .NET 8 framework
- **Windows Forms**: For the lightweight UI framework
