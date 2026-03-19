namespace AudioGrabber;

static class Program
{
    private const string MutexName = "AudioGrabber_SingleInstance_Mutex";
    
    /// <summary>
    ///  The main entry point for the application.
    /// </summary>
    [STAThread]
    static void Main()
    {
        // Single instance check
        using var mutex = new Mutex(true, MutexName, out bool createdNew);
        
        if (!createdNew)
        {
            MessageBox.Show(
                "AudioGrabber is already running. Check the system tray.",
                "AudioGrabber",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information
            );
            return;
        }
        
        // Set up unhandled exception handlers
        Application.ThreadException += OnThreadException;
        AppDomain.CurrentDomain.UnhandledException += OnUnhandledException;
        
        // Initialize application
        ApplicationConfiguration.Initialize();
        
        // Run application context (system tray app)
        Application.Run(new AudioGrabberApplicationContext());
        
        // Keep mutex alive until application exits
        GC.KeepAlive(mutex);
    }
    
    private static void OnThreadException(object sender, System.Threading.ThreadExceptionEventArgs e)
    {
        MessageBox.Show(
            $"An unexpected error occurred:\n{e.Exception.Message}",
            "AudioGrabber Error",
            MessageBoxButtons.OK,
            MessageBoxIcon.Error
        );
    }
    
    private static void OnUnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
        if (e.ExceptionObject is Exception ex)
        {
            MessageBox.Show(
                $"A fatal error occurred:\n{ex.Message}",
                "AudioGrabber Fatal Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
}