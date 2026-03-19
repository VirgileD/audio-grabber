using NAudio.Wave;

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
/// Handles all audio recording operations
/// </summary>
public class AudioRecorderService : IDisposable
{
    private WasapiLoopbackCapture? _capture;
    private WaveFileWriter? _writer;
    private RecordingLogger? _logger;
    private DateTime _recordingStartTime;
    private long _bytesRecorded;
    
    public event EventHandler<RecordingStateChangedEventArgs>? StateChanged;
    public event EventHandler<RecordingErrorEventArgs>? ErrorOccurred;
    
    public bool IsRecording { get; private set; }
    public string? CurrentRecordingPath { get; private set; }
    
    /// <summary>
    /// Start recording audio
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
            
            // Initialize capture device
            _capture = new WasapiLoopbackCapture();
            
            // Initialize logger
            _logger = new RecordingLogger();
            _logger.StartSession(outputPath, _capture.WaveFormat);
            
            // Initialize wave file writer
            _writer = new WaveFileWriter(outputPath, _capture.WaveFormat);
            
            // Wire up data available event
            _capture.DataAvailable += OnDataAvailable;
            _capture.RecordingStopped += OnRecordingStopped;
            
            // Start recording
            CurrentRecordingPath = outputPath;
            _recordingStartTime = DateTime.Now;
            _bytesRecorded = 0;
            
            _capture.StartRecording();
            IsRecording = true;
            
            _logger.LogInfo($"Audio Device: {_capture.GetType().Name}");
            
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
            
            _capture?.StopRecording();
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
    
    private void OnDataAvailable(object? sender, WaveInEventArgs e)
    {
        try
        {
            if (_writer != null && e.BytesRecorded > 0)
            {
                _writer.Write(e.Buffer, 0, e.BytesRecorded);
                _bytesRecorded += e.BytesRecorded;
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
        
        if (_capture != null)
        {
            _capture.DataAvailable -= OnDataAvailable;
            _capture.RecordingStopped -= OnRecordingStopped;
            _capture.Dispose();
            _capture = null;
        }
        
        _writer?.Dispose();
        _writer = null;
        
        _logger?.Dispose();
        _logger = null;
        
        CurrentRecordingPath = null;
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
