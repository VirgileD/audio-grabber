using System.Windows.Forms;

namespace AudioGrabber.Models;

/// <summary>
/// Converts a hotkey to and from readable text such as "Ctrl+R" or "Ctrl+Shift+F9".
/// Modifiers: Ctrl (or Control), Alt, Shift, Win; the key is a Keys name (R, F9, D1, ...).
/// </summary>
public static class HotkeyText
{
    public static string Format(Keys key, KeyModifiers modifiers)
    {
        var parts = new List<string>();
        if ((modifiers & KeyModifiers.Control) != 0) parts.Add("Ctrl");
        if ((modifiers & KeyModifiers.Alt) != 0) parts.Add("Alt");
        if ((modifiers & KeyModifiers.Shift) != 0) parts.Add("Shift");
        if ((modifiers & KeyModifiers.Win) != 0) parts.Add("Win");
        parts.Add(key.ToString());
        return string.Join("+", parts);
    }

    public static bool TryParse(string? text, out Keys key, out KeyModifiers modifiers)
    {
        key = Keys.None;
        modifiers = KeyModifiers.None;
        if (string.IsNullOrWhiteSpace(text))
        {
            return false;
        }

        var parts = text.Split('+', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0)
        {
            return false;
        }

        // Everything before the last part is a modifier
        foreach (var part in parts[..^1])
        {
            switch (part.ToLowerInvariant())
            {
                case "ctrl":
                case "control":
                    modifiers |= KeyModifiers.Control;
                    break;
                case "alt":
                    modifiers |= KeyModifiers.Alt;
                    break;
                case "shift":
                    modifiers |= KeyModifiers.Shift;
                    break;
                case "win":
                case "windows":
                    modifiers |= KeyModifiers.Win;
                    break;
                default:
                    return false;
            }
        }

        // The last part is the key itself: a named key, not a number or a modifier
        var keyName = parts[^1];
        if (keyName.All(char.IsDigit)
            || !Enum.TryParse(keyName, ignoreCase: true, out key)
            || key == Keys.None
            || (key & Keys.Modifiers) != 0
            || key is Keys.ControlKey or Keys.ShiftKey or Keys.Menu or Keys.LWin or Keys.RWin)
        {
            key = Keys.None;
            modifiers = KeyModifiers.None;
            return false;
        }

        return true;
    }
}
