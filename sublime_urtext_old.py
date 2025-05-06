import sublime
import sublime_plugin
import webbrowser

def plugin_loaded():
    sublime.message_dialog(
        "🚨 Due to issues with Package Control, Urtext has moved.\n\n"    
        "Clicking Ok will open new install instructions:\n\n"
        "https://urtext.co/urtext-sublime-install-notice/\n\n"
    )
    webbrowser.open("https://urtext.co/urtext-sublime-install-notice/")
    raise RuntimeError("Urtext (Package Control version) is deprecated.")