using System.Runtime.InteropServices;
using AudioGrabber.Models;

namespace AudioGrabber.Services;

/// <summary>
/// Manages global keyboard shortcuts
/// </summary>
public class GlobalHotkeyManager : IDisposable
{
    private const int WM_HOTKEY = 0x0312;
    private const int HOTKEY_ID = 1;
    
    private HotkeyWindow? _window;
    private bool _isRegistered;
    
    public event EventHandler? HotkeyPressed;
    
    [DllImport("user32.dll")]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);
    
    [DllImport("user32.dll")]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);
    
    /// <summary>
    /// Register a global hotkey
    /// </summary>
    public bool RegisterHotkey(System.Windows.Forms.Keys key, KeyModifiers modifiers)
    {
        try
        {
            UnregisterHotkey();
            
            _window = new HotkeyWindow();
            _window.HotkeyPressed += (s, e) => HotkeyPressed?.Invoke(this, EventArgs.Empty);
            
            var result = RegisterHotKey(
                _window.Handle,
                HOTKEY_ID,
                (uint)modifiers,
                (uint)key
            );
            
            _isRegistered = result;
            return result;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error registering hotkey: {ex.Message}");
            return false;
        }
    }
    
    /// <summary>
    /// Unregister the global hotkey
    /// </summary>
    public void UnregisterHotkey()
    {
        if (_isRegistered && _window != null)
        {
            UnregisterHotKey(_window.Handle, HOTKEY_ID);
            _isRegistered = false;
        }
        
        if (_window != null)
        {
            _window.Dispose();
            _window = null;
        }
    }
    
    public void Dispose()
    {
        UnregisterHotkey();
    }
    
    /// <summary>
    /// Hidden window to receive hotkey messages
    /// </summary>
    private class HotkeyWindow : System.Windows.Forms.NativeWindow, IDisposable
    {
        public event EventHandler? HotkeyPressed;
        
        public HotkeyWindow()
        {
            CreateHandle(new System.Windows.Forms.CreateParams());
        }
        
        protected override void WndProc(ref System.Windows.Forms.Message m)
        {
            if (m.Msg == WM_HOTKEY)
            {
                HotkeyPressed?.Invoke(this, EventArgs.Empty);
            }
            
            base.WndProc(ref m);
        }
        
        public void Dispose()
        {
            DestroyHandle();
        }
    }
}
