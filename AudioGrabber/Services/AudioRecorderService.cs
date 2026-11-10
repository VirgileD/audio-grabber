using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using NAudio.CoreAudioApi;
using NAudio.Wave;
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
    private BufferedWaveProvider? _microphoneBuffer;
    private WaveFormat? _microphoneFormat;

    // Microphone jitter buffer (see ReadMicrophoneSamples)
    private const int MicTargetLatencyMs = 120;
    private const int MicDriftToleranceMs = 40;
    private bool _micPrimed;
    private int _micUnderruns;

    // Scratch buffers reused across audio callbacks (only touched under _lockObject)
    private float[] _micSamples = Array.Empty<float>();
    private byte[] _micRaw = Array.Empty<byte>();

    // MP3 encoding and disk writes happen on a dedicated thread, so a slow encode,
    // a GC pause or a disk stall never blocks the audio capture callback (which
    // would make Windows drop audio).
    private LameMP3FileWriter? _writer;
    private BlockingCollection<byte[]>? _writeQueue;
    private Thread? _writerThread;

    private RecordingLogger? _logger;
    private SynchronizationContext? _syncContext;
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

            // Events are raised back on the caller's (UI) thread
            _syncContext = SynchronizationContext.Current;

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

            // Create MP3 file writer with loopback format (128 kbps), fed by the writer thread
            var writer = new LameMP3FileWriter(outputPath, loopbackFormat, 128);
            var writeQueue = new BlockingCollection<byte[]>();
            _writer = writer;
            _writeQueue = writeQueue;
            _writerThread = new Thread(() => WriterLoop(writeQueue, writer))
            {
                Name = "AudioGrabber MP3 writer",
                IsBackground = true
            };
            _writerThread.Start();

            // Start logger session
            _logger.StartSession(outputPath, loopbackFormat);

            // Log audio sources
            _logger.LogInfo($"System Audio Device: {_loopbackCapture.GetType().Name}");
            if (_microphoneAvailable && _microphoneCapture != null)
            {
                _logger.LogInfo($"Microphone Device: {_microphoneCapture.GetType().Name}");
                _logger.LogInfo("Mixing Mode: System Audio + Microphone");

                // Create buffer for microphone (will be mixed with loopback)
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

            RaiseError("Failed to start recording", ex);

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
            RaiseError("Error stopping recording", ex);
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

    /// <summary>
    /// Capture callback: mix and hand the chunk to the writer thread. Must stay
    /// fast - no encoding or disk I/O here.
    /// </summary>
    private void OnLoopbackDataAvailable(object? sender, WaveInEventArgs e)
    {
        try
        {
            if (e.BytesRecorded <= 0)
            {
                return;
            }

            lock (_lockObject)
            {
                if (_writeQueue == null || _writeQueue.IsAddingCompleted)
                {
                    return;
                }

                // NAudio reuses e.Buffer, so the queued chunk must be a copy
                byte[] chunk = new byte[e.BytesRecorded];
                if (_microphoneAvailable && _microphoneBuffer != null)
                {
                    MixAudioData(e.Buffer.AsSpan(0, e.BytesRecorded), chunk);
                }
                else
                {
                    Buffer.BlockCopy(e.Buffer, 0, chunk, 0, e.BytesRecorded);
                }

                _writeQueue.Add(chunk);
                _bytesRecorded += chunk.Length;
            }
        }
        catch (Exception ex)
        {
            _logger?.LogError("Error processing audio data", ex);
            RaiseError("Error processing audio data", ex);
            StopRecording();
        }
    }

    /// <summary>
    /// Writer thread: encodes queued chunks to MP3 until the queue is completed.
    /// </summary>
    private void WriterLoop(BlockingCollection<byte[]> queue, LameMP3FileWriter writer)
    {
        try
        {
            foreach (var chunk in queue.GetConsumingEnumerable())
            {
                writer.Write(chunk, 0, chunk.Length);
            }
        }
        catch (Exception ex)
        {
            _logger?.LogError("Error writing audio data", ex);
            RaiseError("Error writing audio data", ex);
            // Stop accepting audio; stopping the captures must happen on the UI thread
            lock (_lockObject)
            {
                if (!queue.IsAddingCompleted)
                {
                    queue.CompleteAdding();
                }
            }
            PostToUi(StopRecording);
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

    /// <summary>
    /// Mix a chunk of loopback audio (32-bit float) with the microphone into output.
    /// </summary>
    private void MixAudioData(ReadOnlySpan<byte> loopbackData, Span<byte> output)
    {
        var loopbackSamples = MemoryMarshal.Cast<byte, float>(loopbackData);
        var outputSamples = MemoryMarshal.Cast<byte, float>(output);
        int sampleCount = loopbackSamples.Length;

        if (_micSamples.Length < sampleCount)
        {
            _micSamples = new float[sampleCount];
        }
        var micSamples = _micSamples.AsSpan(0, sampleCount);
        ReadMicrophoneSamples(micSamples);

        for (int i = 0; i < sampleCount; i++)
        {
            // Mix samples (average to prevent clipping)
            float mixedSample = (loopbackSamples[i] + micSamples[i]) * 0.5f;

            // Clamp to prevent clipping
            outputSamples[i] = Math.Clamp(mixedSample, -1.0f, 1.0f);
        }
    }

    /// <summary>
    /// Read microphone audio through a jitter buffer, as floats (-1.0 to 1.0).
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
    private void ReadMicrophoneSamples(Span<float> samples)
    {
        samples.Clear();
        var buffer = _microphoneBuffer;
        var format = _microphoneFormat;
        if (buffer == null || format == null)
        {
            return;
        }

        int channels = format.Channels;
        int bytesPerFrame = format.BlockAlign;
        int frames = samples.Length / channels;
        if (frames == 0)
        {
            return;
        }

        int bufferedFrames = buffer.BufferedBytes / bytesPerFrame;
        int targetFrames = format.SampleRate * MicTargetLatencyMs / 1000;
        int toleranceFrames = format.SampleRate * MicDriftToleranceMs / 1000;

        if (!_micPrimed)
        {
            if (bufferedFrames < targetFrames)
            {
                return; // still filling the jitter buffer: mic contributes silence
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

        int rawLength = framesToRead * bytesPerFrame;
        if (_micRaw.Length < rawLength)
        {
            _micRaw = new byte[rawLength];
        }
        int framesRead = buffer.Read(_micRaw, 0, rawLength) / bytesPerFrame;
        if (framesRead < framesToRead)
        {
            // Mic stopped delivering: the missing part stays silent; wait for the
            // buffer to refill before using the mic again.
            _micPrimed = false;
            _micUnderruns++;
        }

        var micPcm = MemoryMarshal.Cast<byte, short>(_micRaw.AsSpan(0, framesRead * bytesPerFrame));

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
                samples[frame * channels + ch] = micPcm[sourceFrame * channels + ch] / 32768f;
            }
        }
    }

    private void OnRecordingStopped(object? sender, StoppedEventArgs e)
    {
        var duration = DateTime.Now - _recordingStartTime;

        if (e.Exception != null)
        {
            _logger?.LogError("Recording stopped due to error", e.Exception);
            RaiseError("Recording stopped due to error", e.Exception);
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

    /// <summary>
    /// Raise ErrorOccurred on the UI thread. Handlers show message boxes, which
    /// must never block an audio or writer thread.
    /// </summary>
    private void RaiseError(string message, Exception? ex)
    {
        PostToUi(() => ErrorOccurred?.Invoke(this, new RecordingErrorEventArgs
        {
            Message = message,
            Exception = ex
        }));
    }

    private void PostToUi(Action action)
    {
        var context = _syncContext;
        if (context == null || SynchronizationContext.Current == context)
        {
            action();
        }
        else
        {
            context.Post(_ => action(), null);
        }
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

        // Stop accepting audio, let the writer thread drain the queue, then close
        // the MP3 file. The lock guarantees no capture callback is mid-enqueue.
        BlockingCollection<byte[]>? writeQueue;
        lock (_lockObject)
        {
            writeQueue = _writeQueue;
            _writeQueue = null;
            if (writeQueue != null && !writeQueue.IsAddingCompleted)
            {
                writeQueue.CompleteAdding();
            }
        }
        if (_writerThread != null && _writerThread != Thread.CurrentThread)
        {
            _writerThread.Join();
        }
        _writerThread = null;
        writeQueue?.Dispose();
        try
        {
            _writer?.Dispose(); // flushes the last MP3 frames
        }
        catch (Exception ex)
        {
            _logger?.LogError("Error finalizing MP3 file", ex);
        }
        _writer = null;

        // Dispose buffers
        _microphoneBuffer = null;
        _microphoneFormat = null;

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
