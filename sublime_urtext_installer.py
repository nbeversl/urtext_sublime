import sublime
import sublime_plugin
import threading
from package_control.package_tasks import PackageTaskRunner
from package_control.activity_indicator import ActivityIndicator
from package_control.package_manager import PackageManager

def plugin_loaded():
    installer = PackageTaskRunner()
    settings = sublime.load_settings('Package Control.sublime-settings')
    channels = settings.get('channels')
    url = "https://nbeversl.github.io/urtext-channel/channel.json"
    if not channels:
        channels = []
    if url not in channels:
        channels.append(url)
    settings.set('channels', channels)
    sublime.save_settings('Package Control.sublime-settings')
    tasks = installer.create_package_tasks(actions=(installer.INSTALL, installer.OVERWRITE))

    def install_worker(task):
        with ActivityIndicator('Installing URTEXT') as progress:
            installer.run_install_tasks([task], progress)

    for t in tasks:
        if t.package_name == "UrtextSublime":
            threading.Thread(target=worker, args=[t]).start()

    def remove_installer_worker():
        with ActivityIndicator() as progress:
            manager = PackageManager()
            remover = PackageTaskRunner(manager)
            remover.remove_packages({"Urtext"}, progress)

    threading.Thread(target=remove_installer_worker).start()

