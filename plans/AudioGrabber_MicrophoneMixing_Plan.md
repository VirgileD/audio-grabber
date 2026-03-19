# AudioGrabber - Microphone Mixing Implementation Plan

## Issue Identified

During Phase 2 testing, it was discovered that the current implementation only captures system audio output (loopback) but does not capture microphone input. For complete audio recording (calls, meetings, gaming), both system audio and microphone input need to be mixed together.

## Requirements

Based on user feedback:

1. **Always mix microphone + system audio** - No option to disable
2. **Use current system volumes** - No separate volume controls needed
3. **General-purpose solution** - Works for calls, gaming, narration, etc.
4. **Keep it simple** - Minimal configuration, just works

## Technical Approach

### Current Implementation (Phase 1)

Currently, [`AudioRecorderService.cs`](../AudioGrabber/Services/AudioRecorderService.cs) uses:
- **WasapiLoopbackCapture**: Captures system audio output only
- **Single audio stream**: Only loopback audio is recorded

### Proposed Solution: Dual Capture with Mixing

We need to implement a dual-capture system that:

1. **Captures two audio streams simultaneously**:
   - System audio output (WasapiLoopbackCapture)
   - Microphone input (WasapiCapture)

2. **Mixes the two streams in real-time**:
   - Combine both audio streams into a single output
   - Maintain synchronization between streams
   - Handle different sample rates if necessary

3. **Writes mixed audio to WAV file**:
   - Single output file with mixed audio
   - Same format: 44.1kHz, 16-bit, stereo

## Implementation Architecture

### Option 1: NAudio MixingSampleProvider (Recommended)

**Approach**: Use NAudio's built-in mixing capabilities

```
┌─────────────────────────────────────────────────────────────┐
│                    AudioRecorderService                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────┐      ┌──────────────────────┐   │
│  │ WasapiLoopbackCapture│      │   WasapiCapture      │   │
│  │  (System Audio)      │      │   (Microphone)       │   │
│  └──────────┬───────────┘      └──────────┬───────────┘   │
│             │                               │               │
│             │  DataAvailable                │  DataAvailable│
│             ▼                               ▼               │
│  ┌──────────────────────┐      ┌──────────────────────┐   │
│  │ BufferedWaveProvider │      │ BufferedWaveProvider │   │
│  │   (System Buffer)    │      │   (Mic Buffer)       │   │
│  └──────────┬───────────┘      └──────────┬───────────┘   │
│             │                               │               │
│             └───────────┬───────────────────┘               │
│                         ▼                                   │
│              ┌─────────────────────┐                        │
│              │ MixingSampleProvider│                        │
│              │  (Combines streams) │                        │
│              └──────────┬──────────┘                        │
│                         ▼                                   │
│              ┌─────────────────────┐                        │
│              │   WaveFileWriter    │                        │
│              │   (Output WAV)      │                        │
│              └─────────────────────┘                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Advantages**:
- Uses NAudio's built-in mixing (tested and reliable)
- Handles sample rate conversion automatically
- Simpler implementation
- Better performance

**Implementation Steps**:
1. Create two capture devices (loopback + microphone)
2. Create BufferedWaveProvider for each stream
3. Use MixingSampleProvider to combine streams
4. Write mixed output to WAV file

### Option 2: Manual Mixing (Alternative)

**Approach**: Manually mix audio samples

**Advantages**:
- More control over mixing algorithm
- Can add custom processing

**Disadvantages**:
- More complex implementation
- Need to handle synchronization manually
- More prone to bugs

**Recommendation**: Use Option 1 (MixingSampleProvider) for simplicity and reliability.

## Code Changes Required

### 1. Modify AudioRecorderService.cs

**Current Structure**:
```csharp
private WasapiLoopbackCapture? _capture;
private WaveFileWriter? _writer;
```

**New Structure**:
```csharp
private WasapiLoopbackCapture? _loopbackCapture;  // System audio
private WasapiCapture? _microphoneCapture;        // Microphone
private BufferedWaveProvider? _loopbackBuffer;
private BufferedWaveProvider? _microphoneBuffer;
private MixingSampleProvider? _mixer;
private WaveFileWriter? _writer;
private Thread? _mixingThread;                    // Background mixing thread
```

### 2. Key Methods to Modify

#### StartRecording()
```csharp
public void StartRecording(string outputPath)
{
    // 1. Initialize loopback capture (system audio)
    _loopbackCapture = new WasapiLoopbackCapture();
    
    // 2. Initialize microphone capture (default microphone)
    _microphoneCapture = new WasapiCapture();
    
    // 3. Create buffers for both streams
    _loopbackBuffer = new BufferedWaveProvider(_loopbackCapture.WaveFormat);
    _microphoneBuffer = new BufferedWaveProvider(_microphoneCapture.WaveFormat);
    
    // 4. Create mixer
    var loopbackSample = _loopbackBuffer.ToSampleProvider();
    var microphoneSample = _microphoneBuffer.ToSampleProvider();
    _mixer = new MixingSampleProvider(new[] { loopbackSample, microphoneSample });
    
    // 5. Set up data available handlers
    _loopbackCapture.DataAvailable += OnLoopbackDataAvailable;
    _microphoneCapture.DataAvailable += OnMicrophoneDataAvailable;
    
    // 6. Create WAV writer
    _writer = new WaveFileWriter(outputPath, _mixer.WaveFormat);
    
    // 7. Start mixing thread
    _mixingThread = new Thread(MixingLoop);
    _mixingThread.Start();
    
    // 8. Start both captures
    _loopbackCapture.StartRecording();
    _microphoneCapture.StartRecording();
    
    // 9. Create and start logger
    _logger = new RecordingLogger(outputPath);
    _logger.StartSession(outputPath, _mixer.WaveFormat);
}
```

#### Data Available Handlers
```csharp
private void OnLoopbackDataAvailable(object? sender, WaveInEventArgs e)
{
    if (_loopbackBuffer != null && e.BytesRecorded > 0)
    {
        _loopbackBuffer.AddSamples(e.Buffer, 0, e.BytesRecorded);
    }
}

private void OnMicrophoneDataAvailable(object? sender, WaveInEventArgs e)
{
    if (_microphoneBuffer != null && e.BytesRecorded > 0)
    {
        _microphoneBuffer.AddSamples(e.Buffer, 0, e.BytesRecorded);
    }
}
```

#### Mixing Loop
```csharp
private void MixingLoop()
{
    var buffer = new float[_mixer.WaveFormat.SampleRate];
    
    while (IsRecording)
    {
        int samplesRead = _mixer.Read(buffer, 0, buffer.Length);
        if (samplesRead > 0)
        {
            // Convert float samples to bytes and write to file
            var byteBuffer = new byte[samplesRead * 2]; // 16-bit = 2 bytes per sample
            for (int i = 0; i < samplesRead; i++)
            {
                short sample = (short)(buffer[i] * short.MaxValue);
                BitConverter.GetBytes(sample).CopyTo(byteBuffer, i * 2);
            }
            _writer?.Write(byteBuffer, 0, byteBuffer.Length);
        }
        else
        {
            Thread.Sleep(10); // Wait for more data
        }
    }
}
```

#### StopRecording()
```csharp
public void StopRecording()
{
    IsRecording = false;
    
    // Stop captures
    _loopbackCapture?.StopRecording();
    _microphoneCapture?.StopRecording();
    
    // Wait for mixing thread to finish
    _mixingThread?.Join();
    
    // Dispose resources
    _loopbackCapture?.Dispose();
    _microphoneCapture?.Dispose();
    _writer?.Dispose();
    _logger?.EndSession(bytesRecorded, duration);
    _logger?.Dispose();
}
```

### 3. Error Handling Considerations

**Potential Issues**:
1. **No microphone available**: Handle gracefully, fall back to system audio only
2. **Different sample rates**: NAudio's MixingSampleProvider handles this
3. **Buffer overflow**: Monitor buffer sizes, adjust if needed
4. **Synchronization**: MixingSampleProvider handles timing

**Error Handling Strategy**:
```csharp
try
{
    _microphoneCapture = new WasapiCapture();
}
catch (Exception ex)
{
    _logger?.LogWarning($"Microphone not available: {ex.Message}");
    _logger?.LogInfo("Falling back to system audio only");
    // Continue with loopback only
}
```

### 4. Logging Updates

Update [`RecordingLogger.cs`](../AudioGrabber/Services/RecordingLogger.cs) to log:
- Both audio sources (system + microphone)
- Microphone device name
- Mixing status
- Any fallback scenarios

**Example Log Output**:
```
================================================================================
AudioGrabber Recording Session Log
================================================================================
Recording File: Recording_2026-03-19_154230.wav
Session Started: 2026-03-19 15:42:30
--------------------------------------------------------------------------------

[15:42:30.123] INFO: Recording session started
[15:42:30.125] INFO: Audio Format: 44100 Hz, 16-bit, Stereo
[15:42:30.127] INFO: System Audio Device: Speakers (Realtek High Definition Audio)
[15:42:30.129] INFO: Microphone Device: Microphone (Realtek High Definition Audio)
[15:42:30.130] INFO: Mixing Mode: System Audio + Microphone
[15:42:30.132] INFO: Operating System: Windows 11 Pro (10.0.22621)
[15:42:30.134] INFO: Application Version: 1.0.0

[15:45:45.678] INFO: Recording session stopped
[15:45:45.680] INFO: Duration: 00:03:15.555
[15:45:45.682] INFO: Bytes Recorded: 51,891,200
[15:45:45.684] INFO: File Size: 51.89 MB

================================================================================
Session completed successfully
================================================================================
```

## Testing Strategy

### Unit Tests
1. Test loopback capture alone
2. Test microphone capture alone
3. Test mixing with both sources
4. Test fallback when microphone unavailable
5. Test synchronization

### Integration Tests
1. Record with both sources active
2. Verify mixed audio in output file
3. Test with different microphone devices
4. Test with no microphone (fallback scenario)
5. Test long recordings (10+ minutes)

### Manual Tests
1. Record a call/meeting
2. Verify both voices are audible
3. Check audio quality
4. Test with different applications
5. Verify log file shows both sources

## Implementation Phases

### Phase 2.5: Microphone Mixing Implementation

**Tasks**:
1. ✅ Identify issue (completed)
2. ✅ Design solution (this document)
3. ⏳ Modify AudioRecorderService.cs
4. ⏳ Update RecordingLogger.cs
5. ⏳ Test with real microphone
6. ⏳ Update documentation
7. ⏳ Update Phase 2 implementation notes

**Estimated Effort**: 2-3 hours

## Configuration Changes

### AppSettings.cs

No changes needed initially. Future enhancements could add:
- Microphone device selection
- Microphone volume adjustment
- Enable/disable microphone option

But for now, keep it simple as requested.

## Documentation Updates

### Files to Update:
1. [`AudioGrabber_Implementation_Plan.md`](AudioGrabber_Implementation_Plan.md) - Update audio capture section
2. [`PHASE2_IMPLEMENTATION.md`](../PHASE2_IMPLEMENTATION.md) - Add microphone mixing notes
3. [`README.md`](../README.md) - Update features list

## Alternative Approaches Considered

### 1. Windows Audio Session API (WASAPI) Mixing
- **Pros**: Native Windows support
- **Cons**: More complex, lower-level API

### 2. Virtual Audio Cable
- **Pros**: System-level mixing
- **Cons**: Requires additional software installation

### 3. Application-Level Mixing (Chosen)
- **Pros**: No external dependencies, full control
- **Cons**: Slightly more complex than single-source capture

## Potential Future Enhancements

1. **Microphone Selection**: Let user choose which microphone to use
2. **Volume Controls**: Separate volume sliders for system audio and microphone
3. **Microphone Boost**: Amplify microphone signal
4. **Noise Suppression**: Filter background noise from microphone
5. **Echo Cancellation**: Remove echo/feedback
6. **Mono/Stereo Options**: Record microphone in mono, system in stereo
7. **Enable/Disable Toggle**: Option to disable microphone recording

## Conclusion

The microphone mixing feature requires modifying [`AudioRecorderService.cs`](../AudioGrabber/Services/AudioRecorderService.cs) to:
1. Capture two audio streams simultaneously
2. Mix them in real-time using NAudio's MixingSampleProvider
3. Write the mixed output to a single WAV file

This approach is:
- ✅ Simple to implement
- ✅ Uses proven NAudio components
- ✅ Maintains current audio quality
- ✅ Requires no additional dependencies
- ✅ Handles edge cases gracefully

**Next Step**: Implement the changes in [`AudioRecorderService.cs`](../AudioGrabber/Services/AudioRecorderService.cs) and test with real microphone input.
