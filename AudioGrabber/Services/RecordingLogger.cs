using NAudio.Wave;

namespace AudioGrabber.Services;

/// <summary>
/// Manages comprehensive logging for each recording session
/// </summary>
public class RecordingLogger : IDisposable
{
    private StreamWriter? _writer;
    private string? _logFilePath;
    private DateTime _sessionStartTime;
    
    /// <summary>
    /// Start a new recording session log
    /// </summary>
    public void StartSession(string recordingPath, WaveFormat format)
    {
        try
        {
            _sessionStartTime = DateTime.Now;
            _logFilePath = Path.ChangeExtension(recordingPath, ".log");
            
            _writer = new StreamWriter(_logFilePath, false)
            {
                AutoFlush = true
            };
            
            // Write header
            _writer.WriteLine("================================================================================");
            _writer.WriteLine("AudioGrabber Recording Session Log");
            _writer.WriteLine("================================================================================");
            _writer.WriteLine($"Recording File: {Path.GetFileName(recordingPath)}");
            _writer.WriteLine($"Session Started: {_sessionStartTime:yyyy-MM-dd HH:mm:ss}");
            _writer.WriteLine("--------------------------------------------------------------------------------");
            _writer.WriteLine();
            
            // Log session start
            LogInfo("Recording session started");
            LogInfo($"Audio Format: {format.SampleRate} Hz, {format.BitsPerSample}-bit, {(format.Channels == 2 ? "Stereo" : "Mono")}");
            LogInfo($"Operating System: {Environment.OSVersion}");
            LogInfo($"Application Version: 1.0.0");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error starting log session: {ex.Message}");
        }
    }
    
    /// <summary>
    /// Log an informational message
    /// </summary>
    public void LogInfo(string message)
    {
        WriteLog("INFO", message);
    }
    
    /// <summary>
    /// Log a warning message
    /// </summary>
    public void LogWarning(string message)
    {
        WriteLog("WARNING", message);
    }
    
    /// <summary>
    /// Log an error message
    /// </summary>
    public void LogError(string message, Exception? ex = null)
    {
        WriteLog("ERROR", message);
        if (ex != null)
        {
            WriteLog("ERROR", $"Exception: {ex.Message}");
            WriteLog("ERROR", $"Stack Trace: {ex.StackTrace}");
        }
    }
    
    /// <summary>
    /// End the recording session
    /// </summary>
    public void EndSession(long bytesRecorded, TimeSpan duration)
    {
        try
        {
            if (_writer == null) return;
            
            _writer.WriteLine();
            LogInfo("Recording session stopped");
            LogInfo($"Duration: {duration:hh\\:mm\\:ss\\.fff}");
            LogInfo($"Bytes Recorded: {bytesRecorded:N0}");
            LogInfo($"File Size: {bytesRecorded / 1024.0 / 1024.0:F2} MB");
            
            _writer.WriteLine();
            _writer.WriteLine("================================================================================");
            _writer.WriteLine("Session completed successfully");
            _writer.WriteLine("================================================================================");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error ending log session: {ex.Message}");
        }
    }
    
    private void WriteLog(string level, string message)
    {
        try
        {
            if (_writer != null)
            {
                var timestamp = DateTime.Now.ToString("HH:mm:ss.fff");
                _writer.WriteLine($"[{timestamp}] {level}: {message}");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error writing to log: {ex.Message}");
        }
    }
    
    public void Dispose()
    {
        _writer?.Dispose();
        _writer = null;
    }
}
