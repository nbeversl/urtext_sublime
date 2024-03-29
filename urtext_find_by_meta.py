from .sublime_urtext import show_panel, UrtextTextCommand, refresh_project_text_command, NodeBrowserMenu

class FindByMetaCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        if not self._UrtextProjectList.current_project.has_meta_browser_key():
            self.tagnames = self._UrtextProjectList.current_project.get_all_keys()
            self.view.window().show_quick_panel(
                self.tagnames, 
                self.list_values)
        else:
            self.tagnames = [self._UrtextProjectList.current_project.settings['meta_browser_key']]
            self.list_values(0)

    def list_values(self, index):
        self.selected_tag = self.tagnames[index]
        self.values = self._UrtextProjectList.current_project.get_all_values_for_key(
            self.selected_tag)
        self.view.window().show_quick_panel(
            self.values,
            self.display_files)

    def display_files(self, index):
        if self.values:
            selected_value = self.values[index]
            nodes = self._UrtextProjectList.current_project.get_by_meta(
                self.selected_tag, 
                selected_value, 
                '=',
                as_nodes=True)
            sorted_nodes = self._UrtextProjectList.current_project.sort_for_meta_browser(
                nodes,
                as_nodes=True)

            self.menu = NodeBrowserMenu(
                self._UrtextProjectList,
                nodes=sorted_nodes)

            show_panel(self.view.window(),
                self.menu.display_menu,
                self.open_the_node)

    def open_the_node(self, selected_option):
        if selected_option == -1:
            return
        node_id = self.menu.menu[selected_option].id
        self._UrtextProjectList.current_project.open_node(node_id)
