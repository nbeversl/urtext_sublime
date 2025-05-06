import sublime
import sublime_plugin
import webbrowser

def plugin_loaded():
    sublime.message_dialog(
        "🚨 Urtext Sublime has moved!\n\n"    
        "See this link for install information:\n\n"
        "https://urtext.co/urtext-sublime-install-notice/\n\n"
    )
    webbrowser.open("https://urtext.co/urtext-sublime-install-notice/")
    raise RuntimeError("Urtext (Package Control version) is deprecated.")