"""
This file is part of Urtext for Sublime Text.

Urtext is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Urtext is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Urtext.  If not, see <https://www.gnu.org/licenses/>.

"""
import sublime
import sublime_plugin
import os
import re
import datetime
import time
import concurrent.futures
import subprocess
import webbrowser
from urtext.project_list import ProjectList
from sublime_plugin import EventListener
from urtext.project import soft_match_compact_node

_SublimeUrtextWindows = {}
_UrtextProjectList = None
urtext_initiated = False
quick_panel_waiting = False
quick_panel_active  = False
quick_panel_id = 0

class UrtextTextCommand(sublime_plugin.TextCommand):

    def __init__(self, view):
        self.view = view
        self.window = view.window()

def refresh_project_text_command(import_project=False):
    """ 
    Determine which project we are in based on the Sublime window.
    Used as a decorator in every command class.
    """    
    def middle(function):

        def wrapper(*args, **kwargs):

            global urtext_initiated
            urtext_initiated = True
            
            view = args[0].view
            edit = args[1]

            _UrtextProjectList = initialize_project_list(view)
            if not _UrtextProjectList:
                return None

            window = sublime.active_window()
            if not window:
                print('NO WINDOW')
                print(function) # debugging
                return

            view = window.active_view()
            window_id = window.id()

            # get the current project first from the view
            if view.file_name():
                current_path = os.path.dirname(view.file_name())
                _UrtextProjectList.set_current_project(current_path)
                if import_project :
                    _UrtextProjectList.import_project(current_path)
            
            # then try the window
            elif window_id in _SublimeUrtextWindows:
                current_path = _SublimeUrtextWindows[window_id]
                _UrtextProjectList.set_current_project(current_path)
                if import_project :
                    _UrtextProjectList.import_project(current_path)

            # otherwise assign the current window to the current project
            elif _UrtextProjectList.current_project:
                _SublimeUrtextWindows[window_id] = _UrtextProjectList.current_project.path
                
            # If there is a current project, return it
            if _UrtextProjectList.current_project:
                args[0].edit = edit
                args[0]._UrtextProjectList = _UrtextProjectList
                view.set_status('urtext_project', 'Urtext Project: '+_UrtextProjectList.current_project.title)
                return function(args[0])

            elif import_project:
                current_paths = window.folders()
                for path in current_paths:
                    _UrtextProjectList.import_project(path)

            return None

        return wrapper

    return middle

def refresh_project_event_listener(function):

    def wrapper(*args):
        view = args[1]

        #  only run if Urtext project list is initialized
        if not _UrtextProjectList:
            return None
        
        window = sublime.active_window()
        if not window:
            return
        
        view = window.active_view()
        window_id = window.id()

        if view and view.file_name():
            current_path = os.path.dirname(view.file_name())
            _UrtextProjectList.set_current_project(current_path)
            args[0]._UrtextProjectList = _UrtextProjectList
            return function(args[0], view)

        if window_id in _SublimeUrtextWindows:
            current_path = _SublimeUrtextWindows[window_id]
            _UrtextProjectList.set_current_project(current_path)
            args[0]._UrtextProjectList = _UrtextProjectList
            return function(args[0], view)

        if _UrtextProjectList.current_project:
            _SublimeUrtextWindows[window_id] = _UrtextProjectList.current_project.path
            args[0]._UrtextProjectList = _UrtextProjectList
            return function(args[0], view)

        return None

    return wrapper


def initialize_project_list(view, 
    init_project=False, 
    reload_projects=False):

    global _UrtextProjectList

    if reload_projects:
        _UrtextProjectList = None        

    if _UrtextProjectList == None:
        folders = view.window().folders()       
        if not folders:
            return None
        current_path = folders[0]
        _UrtextProjectList = ProjectList(current_path)

    return _UrtextProjectList

def get_path(view):
    """ 
    given a view or None, establishes the current active path,
    either from the view or from the current active window.
    """

    current_path = None
    if view and view.file_name():
        return os.path.dirname(view.file_name())
    window = sublime.active_window()
    if not window:
        print('No active window')
        return None
    window_variables = window.extract_variables()
    if 'folder' in window_variables:
        return window.extract_variables()['folder']
    return None
  
class ListProjectsCommand(UrtextTextCommand):
    
    @refresh_project_text_command()
    def run(self):
        show_panel(
            self.view.window(), 
            self._UrtextProjectList.project_titles(), 
            self.set_window_project)

    def set_window_project(self, title):
        self._UrtextProjectList.set_current_project(title)
        self.view.set_status('urtext_project', 'Urtext Project: '+_UrtextProjectList.current_project.title)
        _SublimeUrtextWindows[self.view.window().id()] = self._UrtextProjectList.current_project.path
        node_id = self._UrtextProjectList.nav_current()
        self._UrtextProjectList.nav_new(node_id)
        open_urtext_node(self.view, node_id)

class MoveFileToAnotherProjectCommand(UrtextTextCommand):
    
    @refresh_project_text_command()
    def run(self):
        show_panel(
            self.window,
            self._UrtextProjectList.project_titles(), 
            self.move_file)

    def move_file(self, new_project_title):
                
        replace_links = sublime.yes_no_cancel_dialog(
            'Do you want to also rewrite links to nodes in this file as links to the new project?')
        replace_links = True if replace_links == sublime.DIALOG_YES else False
        filename = self.view.file_name()

        success = self._UrtextProjectList.move_file(
            filename, 
            new_project_title,
            replace_links=replace_links)

        self.view.window().run_command('close_file')

        last_node = _UrtextProjectList.nav_reverse()
        if last_node:
            open_urtext_node(self.view, last_node)

        # temporary.
        if not success:
            sublime.message_dialog('File was moved but error occured. Check the console.')
        else:
            sublime.message_dialog('File was moved')


class UrtextCompletions(EventListener):

    def on_query_completions(self, view, prefix, locations):
        if not _UrtextProjectList or not _UrtextProjectList.current_project:
            return
        
        current_path = os.path.dirname(view.file_name())

        if _UrtextProjectList.get_project(current_path):
            subl_completions = []
            for k in _UrtextProjectList.get_all_for_hash():
                subl_completions.append([k,'#'+k])
            proj_completions = _UrtextProjectList.get_all_meta_pairs()
            for c in proj_completions:
                t = c.split('::')
                if len(t) > 1:
                    subl_completions.append([t[1]+'\t'+c, c])
            for t in _UrtextProjectList.current_project.title_completions():
                subl_completions.append([t[0],t[1]])
            
            completions = (subl_completions, sublime.INHIBIT_WORD_COMPLETIONS)

            return completions
        return []

class UrtextSaveListener(EventListener):

    def __init__(self):   
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
     
    @refresh_project_event_listener
    def on_post_save_async(self, view):

        if not view.file_name():
            return
        window = view.window()
        open_files = [view.file_name()]
        open_files.extend([f.file_name() for f in window.views() if f.file_name() not in [None, view.file_name()]])
        result = self._UrtextProjectList.on_modified(open_files)
        if self._UrtextProjectList.current_project.is_async:
            if result:
                renamed_file = result.result()
                if renamed_file and renamed_file != filename:
                    view.set_scratch(True) # already saved
                    view.close()
                    new_view = view.window().open_file(renamed_file)
                else:
                    self.executor.submit(refresh_open_file, filename, view)
        else:
            if result:
                for f in open_files:
                    if f in result:
                        window = view.window()
                        view.set_scratch(True) # already saved
                        view.close()
                        new_view = window.open_file(f)
                    else:
                        self.executor.submit(refresh_open_file, f, view)

# BOOKMARK
class KeywordsCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        window = self.view.window()
        keyphrases = list(self._UrtextProjectList.current_project.get_keywords())
        self.chosen_keyphrase = ''

        # BOOKMARK
        def multiple_selections(selection):

            open_urtext_node(self.view, 
                self.second_menu.full_menu[selection].node_id,
                position=self.second_menu.full_menu[selection].position,
                highlight=self.chosen_keyphrase)

        def result(i):
            self.chosen_keyphrase = keyphrases[i]
            result = self._UrtextProjectList.current_project.get_by_keyword(self.chosen_keyphrase)
            if len(result) == 1:
                open_urtext_node(
                    self.view,     
                    result[0],
                    position=self._UrtextProjectList.current_project.nodes[result[0]].position,
                    highlight=self.chosen_keyphrase)
            else:
                self.second_menu = NodeBrowserMenu(
                    self._UrtextProjectList, 
                    nodes=self._UrtextProjectList.current_project.get_by_keyword(self.chosen_keyphrase))
                show_panel(
                    window, 
                    self.second_menu.display_menu, 
                    multiple_selections,
                    return_index=True)
        
        window.show_quick_panel(keyphrases, result)

class UrtextHomeCommand(UrtextTextCommand):
    
    @refresh_project_text_command()
    def run(self):
        node_id = _UrtextProjectList.current_project.get_home()
        _UrtextProjectList.nav_new(node_id)
        open_urtext_node(self.view, node_id)

class NavigateBackwardCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        last_node = _UrtextProjectList.nav_reverse()
        if last_node:
            open_urtext_node(self.view, last_node)

class NavigateForwardCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        next_node = _UrtextProjectList.nav_advance()
        if next_node:
            open_urtext_node(self.view, next_node)

class OpenUrtextLinkCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        file_pos = self.view.sel()[0].a
        col_pos = self.view.rowcol(file_pos)[1]
        full_line = self.view.substr(self.view.line(self.view.sel()[0]))
        link = _UrtextProjectList.get_link_and_set_project(
            full_line, 
            self.view.file_name(), 
            col_pos=col_pos,
            file_pos=file_pos)

        if link == None:   
            if not _UrtextProjectList.current_project.compiled:
                   sublime.error_message("Project is still compiling")
            else:
                print('NO LINK') 
            return
        
        kind = link[0]
        
        if kind == 'SYSTEM':
            open_external_file(link[1])

        if kind == 'EDITOR_LINK':
            file_view = self.view.window().open_file(link[1])

        if kind == 'NODE':
            _UrtextProjectList.nav_new(link[1])   
            open_urtext_node(self.view, link[1], position=link[2])
        
        if kind == 'HTTP':
            success = webbrowser.get().open(link[1])
            if not success:
                self.log('Could not open tab using your "web_browser_path" setting')       

class NodeBrowserCommand(UrtextTextCommand):
    
    @refresh_project_text_command()
    def run(self):
        self.menu = NodeBrowserMenu(
            self._UrtextProjectList, 
            project=self._UrtextProjectList.current_project)

        show_panel(
            self.view.window(), 
            self.menu.display_menu, 
            self.open_the_file)

    def open_the_file(self, selected_option):        
        selected_item = self.menu.get_selection_from_index(selected_option)
        self._UrtextProjectList.set_current_project(selected_item.project_title)
        self._UrtextProjectList.nav_new(selected_item.node_id)   
        open_urtext_node(self.view, selected_item.node_id)

class BacklinksBrowser(NodeBrowserCommand):

    @refresh_project_text_command()
    def run(self):
        backlinks = self._UrtextProjectList.current_project.get_links_to(get_node_id(self.view))

        if backlinks:
            self.menu = NodeBrowserMenu(
                self._UrtextProjectList, 
                project=self._UrtextProjectList.current_project,
                nodes=backlinks)

            show_panel(
                self.view.window(), 
                self.menu.display_menu, 
                self.open_the_file)

class ForwardlinksBrowser(NodeBrowserCommand):

    @refresh_project_text_command()
    def run(self):
        forward_links = self._UrtextProjectList.current_project.get_links_from(get_node_id(self.view))
        self.menu = NodeBrowserMenu(
            self._UrtextProjectList, 
            project=self._UrtextProjectList.current_project,
            nodes=forward_links,
            )
        show_panel(
            self.view.window(), 
            self.menu.display_menu, 
            self.open_the_file)

class AllProjectsNodeBrowser(NodeBrowserCommand):
    
    @refresh_project_text_command()
    def run(self):
        self.menu = NodeBrowserMenu(
            self._UrtextProjectList, 
            project=None
            )
        show_panel(
            self.view.window(), 
            self.menu.display_menu, 
            self.open_the_file)



class InsertNodeCommand(sublime_plugin.TextCommand):
    """ inline only, does not make a new file """
    @refresh_project_text_command()
    def run(self):
        add_inline_node(self.view)

class InsertNodeSingleLineCommand(sublime_plugin.TextCommand):
    """ inline only, does not make a new file """
    @refresh_project_text_command()
    def run(self):
        add_inline_node(self.view, include_timestamp=False)    


def add_inline_node(view, 
    include_timestamp=True, 
    locate_inside=True):

    region = view.sel()[0]
    selection = view.substr(region)
    new_node = _UrtextProjectList.current_project.new_inline_node(
        metadata={},
        contents=selection)
    new_node_contents = new_node['contents']
    view.run_command("insert_snippet",
                          {"contents": new_node_contents})  # (whitespace)
    if locate_inside:
        view.sel().clear()
        new_cursor_position = sublime.Region(region.a + 3, region.a + 3 ) 
        view.sel().add(new_cursor_position) 
    return new_node['id'] # id

class RenameFileCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        old_filename = self.view.file_name()
        new_filenames = self._UrtextProjectList.current_project.rename_file_nodes(old_filename)
        self.view.retarget(
            os.path.join(self._UrtextProjectList.current_project.path,
                         new_filenames[old_filename]))

class NodeBrowserMenu:
    """ custom class to store more information on menu items than is displayed """

    def __init__(self, 
        project_list, 
        project=None, 
        nodes=None):

        self.full_menu = make_node_menu(
            project_list,
            project=project,
            nodes=nodes)

        self.display_menu = sort_menu(self.full_menu)

    def get_selection_from_index(self, selected_option):
        index = self.display_menu.index(selected_option)
        return self.full_menu[index]

class NodeInfo():

    def __init__(self, node_id, project_list, project=None):    
        if not project:
            project = project_list.current_project
        self.title =project.nodes[node_id].title
        if self.title.strip() == '':
            self.title = '(no title)'
        self.date =project.nodes[node_id].date
        self.filename = project.nodes[node_id].filename
        self.position = project.nodes[node_id].ranges[0][0]
        self.title = project.nodes[node_id].title
        self.node_id = project.nodes[node_id].id
        self.project_title = project.title
        self.display_meta = project.nodes[node_id].display_meta

def make_node_menu(
    project_list, 
    project=None, 
    nodes=None):

    menu = []

    projects = project_list.projects

    if project:
        projects = [project]

    if nodes != None:
        for node_id in nodes:
            menu.append(
                  NodeInfo(
                    node_id, 
                    project_list))
        return menu
    
    for single_project in projects:
        for node_id in single_project.all_nodes():
            menu.append(
                NodeInfo(
                    node_id, 
                    project_list, 
                    project=single_project))
    
    return menu

def sort_menu(menu):
    display_menu = []
    for item in menu:  # there is probably a better way to copy this list.
        item.position = str(item.position)
        display_meta = item.display_meta
        if display_meta:
            display_meta = ' - '+display_meta
        new_item = [
            item.title,
            item.project_title + display_meta,            
        ]
        display_menu.append(new_item)
    return display_menu

def show_panel(window, menu, main_callback, return_index=False):
    """ shows a quick panel with an option to cancel if -1 """
    def private_callback(index):
        if index == -1:
            return
        # otherwise return the main callback with the index of the selected item
        if return_index:
            return main_callback(index)
        main_callback(menu[index])
    window.show_quick_panel(menu, private_callback)

class LinkToNodeCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        self.menu = NodeBrowserMenu(self._UrtextProjectList, project=None)
        show_panel(self.view.window(), self.menu.display_menu, self.link_to_the_node)

    def link_to_the_node(self, selected_option):
        selected_option = self.menu.get_selection_from_index(selected_option)
        link = self._UrtextProjectList.build_contextual_link(
            selected_option.node_id,
            project_title=selected_option.project_title)    
        self.view.run_command("insert", {"characters": link})

class CopyLinkToHereCommand(UrtextTextCommand):
    """
    Copy a link to the node containing the cursor to the clipboard.
    Does not include project title.
    """
    @refresh_project_text_command()
    def run(self):

        if not self.window:
            self.window = self.view.window()

        link = self.get_link(get_node_id(self.window.active_view()))
        sublime.set_clipboard(link)        
        self.view.show_popup(link + '\ncopied to the clipboard', 
            max_width=1800, 
            max_height=1000 
                # max_height does not work correctly. 
                # workaround for now using max_width
                # FUTURE: Could also hard wrap.
                # https://github.com/sublimehq/sublime_text/issues/2854
                # https://github.com/SublimeLinter/SublimeLinter/pull/1609
                # https://github.com/SublimeLinter/SublimeLinter/issues/1601
            )

    def get_link(self, node_id):
        return self._UrtextProjectList.build_contextual_link(node_id)       

class CopyLinkToHereWithProjectCommand(CopyLinkToHereCommand):
    """
    Copy a link to the node containing the cursor to the clipboard.
    Does not include project title.
    """
    def get_link(self, node_id):
        return self._UrtextProjectList.build_contextual_link(
            node_id, 
            include_project=True)

class NewNodeCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        path = self._UrtextProjectList.current_project.path
        new_node = self._UrtextProjectList.current_project.new_file_node()
        self._UrtextProjectList.nav_new(new_node['id'])        
        new_view = self.view.window().open_file(os.path.join(path, new_node['filename']))

class InsertLinkToNewNodeCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        path = self._UrtextProjectList.current_project.path
        new_node = self._UrtextProjectList.current_project.new_file_node()
        self.view.run_command("insert", {"characters":'| >' + new_node['id']})

class NewProjectCommand(UrtextTextCommand):

    def run(self, view):
        global _UrtextProjectList        
        current_path = get_path(self.view)
        new_view = self.window.new_file()
        new_view.set_scratch(True)
        _UrtextProjectList.init_new_project(current_path)
        new_view.close()
        
class DeleteThisNodeCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        if self.view.file_name():
            open_files = [f.file_name() for f in self.view.window().views() if f.file_name() != self.view.file_name()]
            file_name = os.path.basename(self.view.file_name())
            if self.view.is_dirty():
                self.view.set_scratch(True)
            self.view.window().run_command('close_file')            
            self._UrtextProjectList.delete_file(file_name, open_files=open_files)

class InsertTimestampCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        datestamp = self._UrtextProjectList.current_project.timestamp(datetime.datetime.now())
        for s in self.view.sel():
            if s.empty():
                self.view.insert(self.edit, s.a, datestamp)
            else:
                self.view.replace(self.edit, s, datestamp)

class ConsolidateMetadataCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        self.view.run_command('save')  # TODO insert notification
        node_id = get_node_id(self.view)
        if node_id:
            self._UrtextProjectList.current_project.consolidate_metadata(node_id, one_line=True)
            return True    
        print('No Urtext node or no Urtext node with ID found here.')
        return False

class InsertDynamicNodeDefinitionCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        now = datetime.datetime.now()
        node_id = add_inline_node(
            self.view, 
            include_timestamp=False,
            locate_inside=False)
        # This should possibly be moved into Urtext as a utility method.
        position = self.view.sel()[0].a
        content = '\n\n[[ ID(>' + node_id + ')\n\n ]]'
        
        for s in self.view.sel():
            if s.empty():
                self.view.insert(self.edit, s.a, content)
            else:
                view.replace(self.edit, s, content)

        self.view.sel().clear()
        new_cursor_position = sublime.Region(position + 12, position + 12) 
        self.view.sel().add(new_cursor_position) 
        
class TagFromOtherNodeCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        # save the current file first
        full_line = self.view.substr(self.view.line(self.view.sel()[0]))
        link = _UrtextProjectList.get_link_and_set_project(
            full_line,
            self.view.file_name())
        if link[0] != 'NODE':
            return
        node_id = link[1]
        _UrtextProjectList.current_project.tag_other_node(node_id)

class ReIndexFilesCommand(UrtextTextCommand):
    
    @refresh_project_text_command()
    def run(self):

        renamed_files = self._UrtextProjectList.current_project.run_action("REINDEX",
            self.view.substr(self.view.line(self.view.sel()[0])),
            self.view.file_name()
            )
        if renamed_files:
            for view in self.view.window().views():
                if view.file_name() == None:
                    continue
                if os.path.join(self._UrtextProjectList.current_project.path, view.file_name()) in renamed_files:               
                    view.retarget(
                        os.path.join(
                            self._UrtextProjectList.current_project.path,
                            renamed_files[os.path.join(self._UrtextProjectList.current_project.path, view.file_name())])
                        )

class AddNodeIdCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        new_id = self._UrtextProjectList.current_project.next_index()
        self.view.run_command("insert_snippet",
                              {"contents": "@" + new_id})

class UrtextReloadProjectCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        if initialize_project_list(self.view, reload_projects=True) == None:
            print('No Urtext Project')
            return None

class CompactNodeCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        region = self.view.sel()[0]
        selection = self.view.substr(region)
        line_region = self.view.line(region) # get full line region
        line_contents = self.view.substr(line_region)

        if soft_match_compact_node(line_contents):
        # If it is already a compact node, make a new one on the next line down.
            replace = False
            contents = self._UrtextProjectList.current_project.add_compact_node()

        else:
            # If it is not a compact node, make it one and add an ID
            replace = True
            contents = self._UrtextProjectList.current_project.add_compact_node(contents=line_contents)

        if replace:
            self.view.erase(self.edit, line_region)
            self.view.run_command("insert_snippet",{"contents": contents})
            region = self.view.sel()[0]
            self.view.sel().clear()
            self.view.sel().add(sublime.Region(region.a-5, region.b-5))
        else:
            next_line_down = line_region.b    
            self.view.sel().clear()
            self.view.sel().add(next_line_down) 
            self.view.run_command("insert_snippet",{"contents": '\n'+contents})            
            new_cursor_position = sublime.Region(next_line_down + 3, next_line_down + 3) 
            self.view.sel().clear()
            self.view.sel().add(new_cursor_position) 


class PopNodeCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        file_pos = self.view.sel()[0].a
        self._UrtextProjectList.current_project.run_action('POP_NODE',
            self.view.substr(self.view.line(self.view.sel()[0])),
            self.view.file_name(),
            file_pos = file_pos,
            col_pos = self.view.rowcol(file_pos)[1]
            )

class PullNodeCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        file_pos = self.view.sel()[0].a
        self._UrtextProjectList.current_project.run_action('PULL_NODE',
            self.view.substr(self.view.line(self.view.sel()[0])),
            self.view.file_name(),
            file_pos = file_pos,
            col_pos = self.view.rowcol(file_pos)[1]
            )

class RandomNodeCommand(UrtextTextCommand):

    @refresh_project_text_command()
    def run(self):
        node_id = self._UrtextProjectList.current_project.random_node()
        self._UrtextProjectList.nav_new(node_id)
        open_urtext_node(self.view, node_id)

class MouseOpenUrtextLinkCommand(sublime_plugin.TextCommand):

    def run(self, edit, **kwargs):
        if not _UrtextProjectList:
            return
    
        file_pos = self.view.sel()[0].a
        col_pos = self.view.rowcol(file_pos)[1]
        full_line = self.view.substr(self.view.line(self.view.sel()[0]))
        link = _UrtextProjectList.get_link_and_set_project(
            full_line, 
            self.view.file_name(), 
            col_pos=col_pos,
            file_pos=file_pos)

        if link == None:   
            if not _UrtextProjectList.current_project.compiled:
                   return sublime.error_message("Project is still compiling")
            else:
                return print('NO LINK') 
            return

        kind = link[0]
        if kind == 'EDITOR_LINK':
            file_view = self.view.window().open_file(link[1])
        if kind == 'NODE':
            _UrtextProjectList.nav_new(link[1])   
            open_urtext_node(self.view, link[1], position=link[2])
        if kind == 'HTTP':
            success = webbrowser.get().open(link[1])
            if not success:
                self.log('Could not open tab using your "web_browser_path" setting')       
        if kind == 'SYSTEM':
            open_external_file(link[1])

    def want_event(self):
        return True


"""
Utility functions
"""
def open_urtext_node(
    view, 
    node_id, 
    project=None, 
    position=0,
    highlight=''):
    
    if project:
        _UrtextProjectList.set_current_project(project.path)

    filename, node_position = _UrtextProjectList.current_project.get_file_and_position(node_id)
    _UrtextProjectList.current_project.refresh_file(filename)
    if filename and view.window():
        file_view = view.window().find_open_file(filename)
        if not file_view:
            file_view = view.window().open_file(filename)
        if not position:
            position = node_position
        position = int(position)

        def focus_position(focus_view, position):
            if not focus_view.is_loading():
                if view.window():
                    view.window().focus_view(focus_view)
                    center_node(focus_view, position)
            else:
                sublime.set_timeout(lambda: focus_position(focus_view, position), 50) 

        focus_position(file_view, position)

        return file_view
    return None
    """
    Note we do not involve this function with navigation, since it is
    use for purposes including forward/backward navigation and shouldn't
    duplicate/override any of the operations of the methods that call it.
    """

def size_to_groups(groups, view):
    panel_size = 1 / groups
    cols = [0]
    cells = [[0, 0, 1, 1]]
    for index in range(1, groups):
        cols.append(cols[index - 1] + panel_size)
        cells.append([index, 0, index + 1, 1])
    cols.append(1)
    view.window().set_layout({"cols": cols, "rows": [0, 1], "cells": cells})
    # view.window().set_layout({"cols": cols, "rows": [0, 1], "cells": cells})

def size_to_thirds(groups,view):
    # https://forum.sublimetext.com/t/set-layout-reference/5713
    # {'cells': [[0, 0, 1, 1], [1, 0, 2, 1]], 'rows': [0, 1], 'cols': [0, 0.5, 1]}
    view.window().set_layout({"cols": [0.0, 0.3333, 1], "rows": [0, 1], "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]})

def center_node(new_view, position): 
    new_view.sel().clear()
    # this has to be called both before and after:
    new_view.sel().add(sublime.Region(position, position))
    # this has to be called both before and after:
    new_view.show(sublime.Region(position, position))
    new_view.show_at_center(position)

def get_path(view):  ## makes the path persist as much as possible ##

    if view.file_name():
        return os.path.dirname(view.file_name())
    if view.window():
        return get_path_from_window(view.window())
    return None

def get_path_from_window(window):

    folders = window.folders()
    if folders:
        return folders[0]
    if window.project_data():
        return window.project_data()['folders'][0]['path']
    return None

def refresh_open_file(future, view):
    changed_files = future.result()
    open_files = view.window().views()
    for filename in open_files:
        if os.path.basename(filename) in changed_files:
            view.run_command('revert') # undocumented

def open_external_file(filepath):

    if sublime.platform() == "osx":
        subprocess.Popen(('open', filepath))
    elif sublime.platform() == "windows":
        os.startfile(filepath)
    elif sublime.platform() == "linux":
        subprocess.Popen(('xdg-open', filepath))

def get_node_id(view):
    global _UrtextProjectList
    if view.file_name():
        filename = os.path.basename(view.file_name())
        position = view.sel()[0].a
        return _UrtextProjectList.current_project.get_node_id_from_position(filename, position)
    