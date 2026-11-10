using NAudio.CoreAudioApi;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;
using NAudio.Lame;

namespace AudioGrabber.Services;

/// <summary>
/// Event arguments for recording state changes
/// </summary>
public class RecordingStateChangedEventArgs : EventArgs
{
    public bool IsRecording { get; set; }
    public string? FilePath { get; set; }
}

/// <summary>
/// Event arguments for recording errors
/// </summary>
public class RecordingErrorEventArgs : EventArgs
{
    public string Message { get; set; } = string.Empty;
    public Exception? Exception { get; set; }
}

/// <summary>
/// Handles all audio recording operations with dual-capture (system audio + microphone)
/// </summary>
public class AudioRecorderService : IDisposable
{
    private WasapiLoopbackCapture? _loopbackCapture;  // System audio
    private WaveInEvent? _microphoneCapture;          // Microphone
    private MMDevice? _renderDevice;                  // Output device being captured
    private WasapiOut? _silencePlayer;                // Keeps loopback flowing (see StartSilencePlayer)
    private BufferedWaveProvider? _loopbackBuffer;
    private BufferedWaveProvider? _microphoneBuffer;
    private WaveFormat? _microphoneFormat;

    // Microphone jitter buffer (see ReadMicrophoneSamples)
    private const int MicTargetLatencyMs = 120;
    private const int MicDriftToleranceMs = 40;
    private bool _micPrimed;
    private int _micUnderruns;
    private LameMP3FileWriter? _writer;
    private RecordingLogger? _logger;
    private DateTime _recordingStartTime;
    private long _bytesRecorded;
    private bool _microphoneAvailable;
    private readonly object _lockObject = new object();
    
    public event EventHandler<RecordingStateChangedEventArgs>? StateChanged;
    public event EventHandler<RecordingErrorEventArgs>? ErrorOccurred;
    
    public bool IsRecording { get; private set; }
    public string? CurrentRecordingPath { get; private set; }
    
    /// <summary>
    /// Start recording audio (system audio + microphone)
    /// </summary>
    public void StartRecording(string outputPath)
    {
        try
        {
            if (IsRecording)
            {
                throw new InvalidOperationException("Recording is already in progress");
            }
            
            // Ensure output directory exists
            var directory = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(directory))
            {
                Directory.CreateDirectory(directory);
            }
            
            // Initialize logger first
            _logger = new RecordingLogger();
            
            // Initialize loopback capture (system audio)
            _renderDevice = WasapiLoopbackCapture.GetDefaultLoopbackCaptureDevice();
            _loopbackCapture = new WasapiLoopbackCapture(_renderDevice);
            var loopbackFormat = _loopbackCapture.WaveFormat;
            
            // Try to initialize microphone capture
            _microphoneAvailable = false;
            try
            {
                _microphoneCapture = new WaveInEvent
                {
                    WaveFormat = new WaveFormat(loopbackFormat.SampleRate, 16, loopbackFormat.Channels),
                    BufferMilliseconds = 50,
                    NumberOfBuffers = 3
                };
                _microphoneAvailable = true;
                _logger.LogInfo("Microphone device detected and initialized");
            }
            catch (Exception ex)
            {
                _logger.LogWarning($"Microphone not available: {ex.Message}");
                _logger.LogInfo("Falling back to system audio only");
                _microphoneCapture = null;
            }
            
            // Create MP3 file writer with loopback format (128 kbps)
            _writer = new LameMP3FileWriter(outputPath, loopbackFormat, 128);
            
            // Start logger session
            _logger.StartSession(outputPath, loopbackFormat);
            
            // Log audio sources
            _logger.LogInfo($"System Audio Device: {_loopbackCapture.GetType().Name}");
            if (_microphoneAvailable && _microphoneCapture != null)
            {
                _logger.LogInfo($"Microphone Device: {_microphoneCapture.GetType().Name}");
                _logger.LogInfo("Mixing Mode: System Audio + Microphone");
                
                // Create buffer for microphone (will be resampled/mixed with loopback)
                _microphoneFormat = _microphoneCapture.WaveFormat;
                _microphoneBuffer = new BufferedWaveProvider(_microphoneFormat)
                {
                    BufferLength = _microphoneFormat.AverageBytesPerSecond * 5,
                    DiscardOnBufferOverflow = true,
                    // Return only real data; the jitter buffer handles shortfalls itself
                    ReadFully = false
                };
                _micPrimed = false;
                _micUnderruns = 0;
                
                // Wire up microphone data handler
                _microphoneCapture.DataAvailable += OnMicrophoneDataAvailable;
            }
            else
            {
                _logger.LogInfo("Mixing Mode: System Audio Only (Microphone not available)");
            }
            
            // Wire up loopback data available event
            _loopbackCapture.DataAvailable += OnLoopbackDataAvailable;
            _loopbackCapture.RecordingStopped += OnRecordingStopped;
            
            // Start recording
            CurrentRecordingPath = outputPath;
            _recordingStartTime = DateTime.Now;
            _bytesRecorded = 0;
            
            // Start both captures
            StartSilencePlayer(_renderDevice, loopbackFormat);
            _loopbackCapture.StartRecording();
            if (_microphoneAvailable && _microphoneCapture != null)
            {
                _microphoneCapture.StartRecording();
            }
            
            IsRecording = true;
            
            StateChanged?.Invoke(this, new RecordingStateChangedEventArgs
            {
                IsRecording = true,
                FilePath = outputPath
            });
        }
        catch (Exception ex)
        {
            _logger?.LogError("Failed to start recording", ex);
            _logger?.Dispose();
            _logger = null;
            
            ErrorOccurred?.Invoke(this, new RecordingErrorEventArgs
            {
                Message = "Failed to start recording",
                Exception = ex
            });
            
            Cleanup();
            throw;
        }
    }
    
    /// <summary>
    /// Stop recording audio
    /// </summary>
    public void StopRecording()
    {
        try
        {
            if (!IsRecording)
            {
                return;
            }
            
            // Stop captures
            _silencePlayer?.Stop();
            _loopbackCapture?.StopRecording();
            _microphoneCapture?.StopRecording();
            
            // Cleanup will be called in OnRecordingStopped event
        }
        catch (Exception ex)
        {
            _logger?.LogError("Error stopping recording", ex);
            
            ErrorOccurred?.Invoke(this, new RecordingErrorEventArgs
            {
                Message = "Error stopping recording",
                Exception = ex
            });
            
            Cleanup();
        }
    }
    
    /// <summary>
    /// Windows only delivers loopback audio while something is playing: during
    /// silence the capture simply produces no data. Since the recording is driven
    /// by loopback data, those silent stretches were dropped from the file (time
    /// jumps) and the mic audio during them was lost. Playing inaudible silence on
    /// the same device keeps the audio engine running, so loopback delivers a
    /// continuous stream.
    /// </summary>
    private void StartSilencePlayer(MMDevice device, WaveFormat format)
    {
        try
        {
            _silencePlayer = new WasapiOut(device, AudioClientShareMode.Shared, true, 100);
            _silencePlayer.Init(new SilenceProvider(format));
            _silencePlayer.Play();
            _logger?.LogInfo("Silence keep-alive started (continuous capture during silence)");
        }
        catch (Exception ex)
        {
            _logger?.LogWarning($"Could not start silence keep-alive, silent stretches may be skipped: {ex.Message}");
            _silencePlayer?.Dispose();
            _silencePlayer = null;
        }
    }

    private void OnLoopbackDataAvailable(object? sender, WaveInEventArgs e)
    {
        try
        {
            if (_writer != null && e.BytesRecorded > 0)
            {
                lock (_lockObject)
                {
                    // If microphone is available, mix it with loopback
                    if (_microphoneAvailable && _microphoneBuffer != null)
                    {
                        // Read microphone data and mix with loopback
                        var mixedBuffer = MixAudioData(e.Buffer, e.BytesRecorded);
                        _writer.Write(mixedBuffer, 0, mixedBuffer.Length);
                        _bytesRecorded += mixedBuffer.Length;
                    }
                    else
                    {
                        // No microphone, just write loopback data
                        _writer.Write(e.Buffer, 0, e.BytesRecorded);
                        _bytesRecorded += e.BytesRecorded;
                    }
                }
            }
        }
        catch (Exception ex)
        {
            _logger?.LogError("Error writing audio data", ex);
            
            ErrorOccurred?.Invoke(this, new RecordingErrorEventArgs
            {
                Message = "Error writing audio data",
                Exception = ex
            });
            
            StopRecording();
        }
    }
    
    private void OnMicrophoneDataAvailable(object? sender, WaveInEventArgs e)
    {
        try
        {
            if (_microphoneBuffer != null && e.BytesRecorded > 0)
            {
                _microphoneBuffer.AddSamples(e.Buffer, 0, e.BytesRecorded);
            }
        }
        catch (Exception ex)
        {
            _logger?.LogError("Error buffering microphone audio data", ex);
        }
    }
    
    private byte[] MixAudioData(byte[] loopbackData, int loopbackBytes)
    {
        // Get as many microphone samples as the loopback chunk holds. The mic is 16-bit
        // (2 bytes/sample) while loopback is 32-bit float (4 bytes/sample).
        var micSamples = ReadMicrophoneSamples(loopbackBytes / 4);

        // Mix the audio (simple addition with clipping prevention)
        var mixedData = new byte[loopbackBytes];

        // Assuming 32-bit float format from loopback
        for (int i = 0; i < loopbackBytes; i += 4)
        {
            if (i + 3 < loopbackBytes)
            {
                // Read loopback sample (32-bit float)
                float loopbackSample = BitConverter.ToSingle(loopbackData, i);

                // Microphone sample, already converted to float (-1.0 to 1.0)
                float micSample = micSamples[i / 4];

                // Mix samples (average to prevent clipping)
                float mixedSample = (loopbackSample + micSample) * 0.5f;
                
                // Clamp to prevent clipping
                mixedSample = Math.Max(-1.0f, Math.Min(1.0f, mixedSample));
                
                // Write mixed sample
                byte[] sampleBytes = BitConverter.GetBytes(mixedSample);
                Array.Copy(sampleBytes, 0, mixedData, i, 4);
            }
        }
        
        return mixedData;
    }

    /// <summary>
    /// Read microphone audio through a jitter buffer.
    ///
    /// The mic delivers audio in ~50 ms chunks, while loopback asks for ~10 ms at a
    /// time, and the two devices run on independent clocks. So instead of reading
    /// whatever happens to be buffered (and padding with silence = micro-cuts when a
    /// chunk is slightly late), we:
    ///  - wait until MicTargetLatencyMs of audio is buffered before using the mic;
    ///  - keep the buffer level near that target by dropping or repeating a single
    ///    sample frame per chunk when it drifts (inaudible, ~0.2% at most);
    ///  - only go silent (and re-prime) if the mic truly stops delivering.
    /// </summary>
    private float[] ReadMicrophoneSamples(int sampleCount)
    {
        var samples = new float[sampleCount];
        var buffer = _microphoneBuffer;
        var format = _microphoneFormat;
        if (buffer == null || format == null)
        {
            return samples;
        }

        int channels = format.Channels;
        int bytesPerFrame = format.BlockAlign;
        int frames = sampleCount / channels;
        if (frames == 0)
        {
            return samples;
        }

        int bufferedFrames = buffer.BufferedBytes / bytesPerFrame;
        int targetFrames = format.SampleRate * MicTargetLatencyMs / 1000;
        int toleranceFrames = format.SampleRate * MicDriftToleranceMs / 1000;

        if (!_micPrimed)
        {
            if (bufferedFrames < targetFrames)
            {
                return samples; // still filling the jitter buffer: mic contributes silence
            }
            _micPrimed = true;
        }

        // Drift correction: consume one frame more (buffer too full) or one frame
        // less (buffer running low) than we output.
        int framesToRead = frames;
        if (bufferedFrames > targetFrames + toleranceFrames)
        {
            framesToRead = frames + 1;
        }
        else if (bufferedFrames < targetFrames - toleranceFrames && frames > 1)
        {
            framesToRead = frames - 1;
        }

        var raw = new byte[framesToRead * bytesPerFrame];
        int framesRead = buffer.Read(raw, 0, raw.Length) / bytesPerFrame;
        if (framesRead < framesToRead)
        {
            // Mic stopped delivering: the missing part stays silent; wait for the
            // buffer to refill before using the mic again.
            _micPrimed = false;
            _micUnderruns++;
        }

        // Map output frames onto the frames read (nearest neighbour), which drops
        // or repeats exactly one frame when framesToRead differs from frames.
        for (int frame = 0; frame < frames; frame++)
        {
            int sourceFrame = (int)((long)frame * framesToRead / frames);
            if (sourceFrame >= framesRead)
            {
                break;
            }
            for (int ch = 0; ch < channels; ch++)
            {
                short value = BitConverter.ToInt16(raw, sourceFrame * bytesPerFrame + ch * 2);
                samples[frame * channels + ch] = value / 32768f;
            }
        }

        return samples;
    }

    private void OnRecordingStopped(object? sender, StoppedEventArgs e)
    {
        var duration = DateTime.Now - _recordingStartTime;
        
        if (e.Exception != null)
        {
            _logger?.LogError("Recording stopped due to error", e.Exception);
            
            ErrorOccurred?.Invoke(this, new RecordingErrorEventArgs
            {
                Message = "Recording stopped due to error",
                Exception = e.Exception
            });
        }
        else
        {
            if (_microphoneFormat != null)
            {
                _logger?.LogInfo($"Microphone underruns: {_micUnderruns}");
            }
            _logger?.EndSession(_bytesRecorded, duration);
        }
        
        Cleanup();
        
        StateChanged?.Invoke(this, new RecordingStateChangedEventArgs
        {
            IsRecording = false,
            FilePath = CurrentRecordingPath
        });
    }
    
    private void Cleanup()
    {
        IsRecording = false;
        
        // Dispose silence keep-alive
        _silencePlayer?.Dispose();
        _silencePlayer = null;

        // Dispose loopback capture
        if (_loopbackCapture != null)
        {
            _loopbackCapture.DataAvailable -= OnLoopbackDataAvailable;
            _loopbackCapture.RecordingStopped -= OnRecordingStopped;
            _loopbackCapture.Dispose();
            _loopbackCapture = null;
        }
        
        // Dispose microphone capture
        if (_microphoneCapture != null)
        {
            _microphoneCapture.DataAvailable -= OnMicrophoneDataAvailable;
            _microphoneCapture.Dispose();
            _microphoneCapture = null;
        }
        
        _renderDevice?.Dispose();
        _renderDevice = null;

        // Dispose buffers
        _microphoneBuffer = null;
        _microphoneFormat = null;

        // Dispose writer
        _writer?.Dispose();
        _writer = null;
        
        // Dispose logger
        _logger?.Dispose();
        _logger = null;
        
        CurrentRecordingPath = null;
        _microphoneAvailable = false;
    }
    
    public void Dispose()
    {
        if (IsRecording)
        {
            StopRecording();
        }
        
        Cleanup();
    }
}
