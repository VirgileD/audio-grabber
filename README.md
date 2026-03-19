# AudioGrabber

A lightweight Windows system tray application for capturing system audio with a global hotkey.

## Overview

AudioGrabber is a .NET 8 Windows Forms application that runs in the system tray and captures all system audio (exactly as heard through headphones) when activated via a global hotkey. The application provides a simple, efficient way to record audio output from your computer.

## Features

- **System Tray Operation**: Runs quietly in the background with minimal UI
- **Global Hotkey**: Toggle recording on/off with Ctrl+R (configurable)
- **Loopback Recording**: Captures system audio output using WASAPI
- **High Quality Audio**: Records in WAV format (44.1kHz, 16-bit stereo)
- **Automatic Naming**: Timestamp-based file naming
- **Visual Feedback**: Icon color changes to indicate recording state
- **Audio Feedback**: Simple beep sounds when starting/stopping recording
- **Comprehensive Logging**: Each recording session generates a detailed log file
- **Configurable**: Settings for output folder, hotkey, and more

## System Requirements

- Windows 10/11 (x64)
- .NET 8 Runtime

## Technology Stack

- **Framework**: .NET 8
- **UI**: Windows Forms
- **Audio Capture**: NAudio library (WASAPI Loopback)
- **Configuration**: System.Text.Json

## Project Structure

```
AudioGrabber/
├── AudioGrabber.sln
├── AudioGrabber/
│   ├── AudioGrabber.csproj
│   ├── Program.cs                    # Application entry point
│   ├── ApplicationContext.cs         # Main application controller
│   ├── Services/
│   │   ├── AudioRecorderService.cs   # Audio recording logic
│   │   ├── GlobalHotkeyManager.cs    # Global hotkey handling
│   │   ├── ConfigurationManager.cs   # Settings management
│   │   └── RecordingLogger.cs        # Session logging
│   ├── Forms/
│   │   └── SettingsForm.cs           # Settings dialog (Phase 3)
│   ├── Models/
│   │   └── AppSettings.cs            # Configuration model
│   ├── Resources/
│   │   └── README.md                 # Icons placeholder
│   └── app.manifest                  # DPI awareness config
├── README.md
└── .gitignore
```

## Building the Project

```bash
# Restore dependencies
dotnet restore

# Build the project
dotnet build

# Run the application
dotnet run --project AudioGrabber/AudioGrabber.csproj
```

## Usage

1. Launch AudioGrabber - it will appear in the system tray
2. Press **Ctrl+R** to start recording
3. Press **Ctrl+R** again to stop recording
4. Recordings are saved to `Documents\AudioGrabber` by default
5. Right-click the tray icon for additional options:
   - Settings (Phase 3)
   - Open Recordings Folder
   - Remove All Settings
   - Exit

## Recording Logs

Each recording session generates a detailed log file alongside the WAV file with information about:
- Recording start/end times
- Audio format details
- System information
- Audio device information
- Any warnings or errors

## Default Settings

- **Output Folder**: `%USERPROFILE%\Documents\AudioGrabber`
- **File Pattern**: `Recording_YYYY-MM-DD_HHMMSS.wav`
- **Sample Rate**: 44100 Hz
- **Bit Depth**: 16-bit
- **Channels**: Stereo (2)
- **Hotkey**: Ctrl+R
- **Start with Windows**: Enabled

## Development Status

### Phase 1: Project Setup ✅ COMPLETED
- [x] Create .NET 8 Windows Forms solution
- [x] Install NAudio package
- [x] Create project structure
- [x] Implement core services
- [x] Implement application context
- [x] Configure build settings

### Phase 2: Core Services Implementation (Planned)
- [ ] Full ConfigurationManager implementation
- [ ] RecordingLogger enhancements
- [ ] AudioRecorderService testing
- [ ] GlobalHotkeyManager testing

### Phase 3: UI Implementation (Planned)
- [ ] Complete SettingsForm
- [ ] Create custom icons
- [ ] Implement icon switching
- [ ] Add registry integration for startup

### Phase 4: Integration and Polish (Planned)
- [ ] End-to-end testing
- [ ] Error handling improvements
- [ ] Performance optimization
- [ ] Documentation

## License

This project is for educational and personal use.

## Author

Created as part of the AudioGrabber implementation plan.
