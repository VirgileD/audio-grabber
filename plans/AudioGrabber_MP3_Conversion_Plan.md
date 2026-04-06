# AudioGrabber MP3 Conversion Plan

## Overview

This plan outlines the changes needed to convert AudioGrabber from outputting WAV files to MP3 files. The application currently uses NAudio's [`WaveFileWriter`](AudioGrabber/Services/AudioRecorderService.cs:92) to save recordings in uncompressed WAV format. We'll switch to MP3 encoding to reduce file sizes while maintaining good audio quality.

## Current State Analysis

### Current Implementation
- **Audio Format**: WAV (IEEE Float 32-bit, system sample rate, stereo)
- **Writer Class**: [`WaveFileWriter`](AudioGrabber/Services/AudioRecorderService.cs:92)
- **File Extension**: `.wav` (hardcoded in [`AppSettings.FileNamePattern`](AudioGrabber/Models/AppSettings.cs:16))
- **Audio Pipeline**: 
  - System audio captured via WASAPI Loopback (32-bit float)
  - Microphone captured via WaveInEvent (16-bit PCM)
  - Real-time mixing in [`MixAudioData()`](AudioGrabber/Services/AudioRecorderService.cs:246)
  - Direct write to WAV file

### Key Files to Modify
1. [`AudioGrabber/AudioGrabber.csproj`](AudioGrabber/AudioGrabber.csproj) - Add MP3 encoder dependency
2. [`AudioGrabber/Models/AppSettings.cs`](AudioGrabber/Models/AppSettings.cs) - Update default file pattern
3. [`AudioGrabber/Services/AudioRecorderService.cs`](AudioGrabber/Services/AudioRecorderService.cs) - Replace WAV writer with MP3 writer

## Technical Approach

### MP3 Encoding Options

NAudio supports MP3 encoding through several methods:

1. **NAudio.Lame** (Recommended)
   - Uses LAME MP3 encoder (industry standard)
   - Provides `LameMP3FileWriter` class
   - High quality, configurable bitrate
   - Native .NET wrapper around LAME
   - NuGet package: `NAudio.Lame`

2. **MediaFoundationEncoder**
   - Built into Windows
   - Requires Windows Media Foundation
   - Less control over encoding parameters
   - May not be available on all systems

3. **External Process**
   - Call external encoder (ffmpeg, lame.exe)
   - More complex, requires external dependencies
   - Not recommended for this use case

**Decision**: Use NAudio.Lame for best quality, reliability, and ease of integration.

### MP3 Encoding Parameters

Recommended settings for high-quality audio recording:
- **Bitrate**: 192 kbps (good balance of quality and file size)
- **Sample Rate**: Match system audio (typically 44100 or 48000 Hz)
- **Channels**: Stereo (2 channels)
- **Quality**: High (LAME preset: STANDARD or EXTREME)

Alternative options:
- **128 kbps**: Acceptable quality, smaller files (good for voice-heavy content)
- **256 kbps**: Near-transparent quality, larger files
- **320 kbps**: Maximum MP3 quality

## Implementation Steps

### 1. Add NAudio.Lame Dependency

**File**: [`AudioGrabber/AudioGrabber.csproj`](AudioGrabber/AudioGrabber.csproj)

Add the NAudio.Lame package reference:
```xml
<ItemGroup>
  <PackageReference Include="NAudio" Version="2.3.0" />
  <PackageReference Include="NAudio.Lame" Version="2.1.0" />
</ItemGroup>
```

**Note**: NAudio.Lame includes the LAME encoder DLL which will be copied to the output directory automatically.

### 2. Update Default File Pattern

**File**: [`AudioGrabber/Models/AppSettings.cs`](AudioGrabber/Models/AppSettings.cs:16)

Change the default file extension from `.wav` to `.mp3`:
```csharp
public string FileNamePattern { get; set; } = "Recording_{0:yyyy-MM-dd_HHmmss}.mp3";
```

**Impact**: 
- New installations will default to MP3
- Existing users with custom patterns will need to manually update (or we can add migration logic)
- Settings UI already allows users to customize this pattern

### 3. Modify AudioRecorderService

**File**: [`AudioGrabber/Services/AudioRecorderService.cs`](AudioGrabber/Services/AudioRecorderService.cs)

#### 3.1 Add Using Statement
```csharp
using NAudio.Lame;
```

#### 3.2 Replace Writer Field
Change from:
```csharp
private WaveFileWriter? _writer;
```

To:
```csharp
private LameMP3FileWriter? _writer;
```

#### 3.3 Update StartRecording Method

Replace the writer initialization (line 92):
```csharp
// OLD:
_writer = new WaveFileWriter(outputPath, loopbackFormat);

// NEW:
_writer = new LameMP3FileWriter(
    outputPath, 
    loopbackFormat, 
    LAMEPreset.STANDARD  // or 192 for explicit bitrate
);
```

**Considerations**:
- `LameMP3FileWriter` accepts the same `WaveFormat` parameter
- The mixing logic remains unchanged (still works with 32-bit float samples)
- LAME handles the conversion from float to MP3 internally

#### 3.4 Verify Compatibility

The existing audio pipeline should work without changes:
- [`OnLoopbackDataAvailable()`](AudioGrabber/Services/AudioRecorderService.cs:192) - No changes needed
- [`OnMicrophoneDataAvailable()`](AudioGrabber/Services/AudioRecorderService.cs:231) - No changes needed
- [`MixAudioData()`](AudioGrabber/Services/AudioRecorderService.cs:246) - No changes needed
- [`Cleanup()`](AudioGrabber/Services/AudioRecorderService.cs:320) - No changes needed (Dispose works the same)

### 4. Configuration Options (Optional Enhancement)

Consider adding MP3 quality settings to [`AppSettings`](AudioGrabber/Models/AppSettings.cs):

```csharp
// Optional: Add MP3-specific settings
public int Mp3Bitrate { get; set; } = 192;  // kbps
public LAMEPreset Mp3Quality { get; set; } = LAMEPreset.STANDARD;
```

This would allow users to choose quality vs. file size trade-offs in the Settings UI.

### 5. Update Documentation

**Files to Update**:
- [`README.md`](README.md:16) - Change "WAV format" to "MP3 format"
- [`README.md`](README.md:49) - Update technology stack description
- Phase implementation docs (if needed)

Example changes:
```markdown
# OLD:
- **High Quality Audio**: Records in WAV format (IEEE Float 32-bit, system sample rate, stereo)

# NEW:
- **High Quality Audio**: Records in MP3 format (192 kbps, system sample rate, stereo)
```

## Migration Considerations

### Existing Users

Users who already have AudioGrabber installed will have:
- Existing settings with `.wav` file pattern
- Existing WAV recordings in their output folder

**Options**:
1. **No Migration** (Simplest)
   - Existing users keep their `.wav` pattern
   - They can manually change it in Settings if desired
   - New recordings will use whatever pattern is configured

2. **Automatic Migration** (More Complex)
   - On first run with new version, detect `.wav` in pattern
   - Prompt user to switch to `.mp3`
   - Update settings automatically if they agree

**Recommendation**: Option 1 (No Migration) - Keep it simple. Users can update manually if desired.

### File Size Impact

Expected file size reduction:
- **WAV**: ~10 MB per minute (32-bit float, 48kHz stereo)
- **MP3 (192 kbps)**: ~1.4 MB per minute
- **Compression ratio**: ~7:1

Example: A 10-minute recording
- WAV: ~100 MB
- MP3: ~14 MB

## Testing Strategy

### Test Cases

1. **Basic Recording**
   - Start recording with system audio only
   - Verify MP3 file is created
   - Verify file plays correctly
   - Check file size is reasonable

2. **Microphone Mixing**
   - Start recording with microphone enabled
   - Verify both audio sources are mixed
   - Verify MP3 quality is maintained

3. **Long Recording**
   - Record for 30+ minutes
   - Verify no memory leaks
   - Verify file integrity

4. **Error Handling**
   - Test with insufficient disk space
   - Test with invalid output path
   - Verify error messages are appropriate

5. **Settings Persistence**
   - Change file pattern to `.mp3`
   - Restart application
   - Verify pattern is preserved

6. **Backward Compatibility**
   - Test with existing settings file (`.wav` pattern)
   - Verify application still works
   - Verify user can manually change to `.mp3`

### Quality Verification

Compare audio quality:
1. Record same audio source in both WAV and MP3
2. Listen for artifacts or quality loss
3. Use audio analysis tools (if needed) to compare frequency response
4. Verify 192 kbps is sufficient for typical use cases

## Potential Issues and Solutions

### Issue 1: LAME DLL Not Found

**Problem**: `LameMP3FileWriter` throws exception if LAME DLL is missing.

**Solution**: NAudio.Lame package includes the DLL and copies it automatically. Verify in build output.

### Issue 2: Real-time Encoding Performance

**Problem**: MP3 encoding is more CPU-intensive than WAV writing.

**Solution**: 
- LAME is highly optimized and should handle real-time encoding easily
- Monitor CPU usage during testing
- If issues arise, consider buffering or async encoding

### Issue 3: Format Compatibility

**Problem**: Some audio players may not support certain MP3 variants.

**Solution**: LAME produces standard MP3 files compatible with all modern players.

### Issue 4: Existing Settings

**Problem**: Users with `.wav` in their file pattern will still create WAV files.

**Solution**: This is by design (no forced migration). Document in release notes that users should update their pattern manually.

## Release Notes Template

```markdown
## Version X.X.X - MP3 Support

### New Features
- **MP3 Output Format**: Recordings are now saved as MP3 files instead of WAV
  - Significantly smaller file sizes (~7x compression)
  - High quality audio (192 kbps)
  - Compatible with all media players

### Breaking Changes
- Default file extension changed from `.wav` to `.mp3`
- Existing users: Update your file name pattern in Settings if you want MP3 output

### Technical Details
- Added NAudio.Lame for MP3 encoding
- Uses LAME encoder (industry standard)
- All existing features work with MP3 format
```

## Summary

This conversion from WAV to MP3 is straightforward:
1. Add NAudio.Lame package
2. Replace `WaveFileWriter` with `LameMP3FileWriter`
3. Update default file extension
4. Test thoroughly

The existing audio capture and mixing logic remains unchanged. The only difference is the final encoding step, which LAME handles efficiently.

**Estimated Complexity**: Low to Medium
- Code changes are minimal and localized
- NAudio.Lame provides drop-in replacement for WaveFileWriter
- Main effort is in testing and documentation

**Benefits**:
- 7x smaller file sizes
- Faster file transfers and backups
- More practical for long recordings
- Industry-standard format

**Risks**:
- Minimal - MP3 encoding is well-established
- LAME is mature and reliable
- Existing functionality is preserved
