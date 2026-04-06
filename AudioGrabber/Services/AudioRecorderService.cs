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
    private BufferedWaveProvider? _loopbackBuffer;
    private BufferedWaveProvider? _microphoneBuffer;
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
            _loopbackCapture = new WasapiLoopbackCapture();
            var loopbackFormat = _loopbackCapture.WaveFormat;
            
            // Try to initialize microphone capture
            _microphoneAvailable = false;
            try
            {
                _microphoneCapture = new WaveInEvent
                {
                    WaveFormat = new WaveFormat(loopbackFormat.SampleRate, 16, loopbackFormat.Channels),
                    BufferMilliseconds = 50
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
                _microphoneBuffer = new BufferedWaveProvider(_microphoneCapture.WaveFormat)
                {
                    BufferLength = _microphoneCapture.WaveFormat.AverageBytesPerSecond * 5,
                    DiscardOnBufferOverflow = true
                };
                
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
        // Get microphone data
        var micBytes = loopbackBytes; // Same amount of data
        var micData = new byte[micBytes];
        
        int actualMicBytes = 0;
        if (_microphoneBuffer != null)
        {
            actualMicBytes = _microphoneBuffer.Read(micData, 0, micBytes);
        }
        
        // Mix the audio (simple addition with clipping prevention)
        var mixedData = new byte[loopbackBytes];
        
        // Assuming 32-bit float format from loopback
        for (int i = 0; i < loopbackBytes; i += 4)
        {
            if (i + 3 < loopbackBytes)
            {
                // Read loopback sample (32-bit float)
                float loopbackSample = BitConverter.ToSingle(loopbackData, i);
                
                // Read microphone sample (16-bit PCM) and convert to float
                float micSample = 0f;
                if (i < actualMicBytes - 1)
                {
                    short micShort = BitConverter.ToInt16(micData, i / 2); // 16-bit is half the size
                    micSample = micShort / 32768f; // Convert to float (-1.0 to 1.0)
                }
                
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
        
        // Dispose buffers
        _microphoneBuffer = null;
        
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
