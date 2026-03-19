using System.Drawing;
using System.Drawing.Drawing2D;

namespace AudioGrabber.Resources;

/// <summary>
/// Generates application icons at runtime for different states
/// </summary>
public static class IconGenerator
{
    /// <summary>
    /// Creates an icon for the idle state (gray microphone)
    /// </summary>
    public static Icon CreateIdleIcon()
    {
        return CreateMicrophoneIcon(Color.Gray);
    }
    
    /// <summary>
    /// Creates an icon for the recording state (red microphone)
    /// </summary>
    public static Icon CreateRecordingIcon()
    {
        return CreateMicrophoneIcon(Color.Red);
    }
    
    /// <summary>
    /// Creates an icon for the error state (orange microphone with warning)
    /// </summary>
    public static Icon CreateErrorIcon()
    {
        return CreateMicrophoneIcon(Color.Orange, true);
    }
    
    private static Icon CreateMicrophoneIcon(Color color, bool showWarning = false)
    {
        // Create a 32x32 bitmap for the icon
        var bitmap = new Bitmap(32, 32);
        using (var g = Graphics.FromImage(bitmap))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.Clear(Color.Transparent);
            
            // Draw microphone body (rounded rectangle)
            using (var brush = new SolidBrush(color))
            {
                // Microphone capsule
                g.FillEllipse(brush, 10, 6, 12, 14);
                
                // Microphone handle
                g.FillRectangle(brush, 14, 20, 4, 6);
                
                // Microphone base
                g.FillRectangle(brush, 10, 26, 12, 2);
            }
            
            // Draw microphone outline
            using (var pen = new Pen(Color.FromArgb(200, color), 2))
            {
                g.DrawEllipse(pen, 10, 6, 12, 14);
                g.DrawLine(pen, 14, 20, 14, 26);
                g.DrawLine(pen, 18, 20, 18, 26);
                g.DrawLine(pen, 10, 26, 22, 26);
            }
            
            // Draw sound waves for recording state
            if (color == Color.Red)
            {
                using (var pen = new Pen(Color.FromArgb(180, Color.Red), 2))
                {
                    // Left waves
                    g.DrawArc(pen, 2, 8, 8, 10, 270, 180);
                    g.DrawArc(pen, 0, 6, 10, 14, 270, 180);
                    
                    // Right waves
                    g.DrawArc(pen, 22, 8, 8, 10, 90, 180);
                    g.DrawArc(pen, 22, 6, 10, 14, 90, 180);
                }
            }
            
            // Draw warning symbol for error state
            if (showWarning)
            {
                using (var brush = new SolidBrush(Color.White))
                using (var pen = new Pen(Color.DarkOrange, 2))
                {
                    // Warning triangle
                    Point[] triangle = new Point[]
                    {
                        new Point(26, 24),
                        new Point(30, 30),
                        new Point(22, 30)
                    };
                    g.FillPolygon(brush, triangle);
                    g.DrawPolygon(pen, triangle);
                    
                    // Exclamation mark
                    using (var exclamationPen = new Pen(Color.DarkOrange, 1.5f))
                    {
                        g.DrawLine(exclamationPen, 26, 26, 26, 28);
                        g.FillEllipse(new SolidBrush(Color.DarkOrange), 25.5f, 28.5f, 1, 1);
                    }
                }
            }
        }
        
        // Convert bitmap to icon
        IntPtr hIcon = bitmap.GetHicon();
        Icon icon = Icon.FromHandle(hIcon);
        
        // Create a copy of the icon to avoid handle issues
        Icon result = (Icon)icon.Clone();
        
        // Clean up
        DestroyIcon(hIcon);
        bitmap.Dispose();
        
        return result;
    }
    
    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Auto)]
    private static extern bool DestroyIcon(IntPtr handle);
}
