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
import pprint
import logging
import sys
import concurrent.futures
from urtext.metadata import NodeMetadata
from urtext.project_list import ProjectList
from urtext.project import node_id_regex

from sublime_plugin import EventListener
import webbrowser

_SublimeUrtextWindows = {}
_UrtextProjectList = None

class UrtextTextCommand(sublime_plugin.TextCommand):

    def __init__(self, view):
        self.view = view
        self.window = view.window()

def refresh_project_text_command(function, init_project=False):
    """ 
    Determine which project we are in based on the Sublime window.
    Used as a decorator in every command class.
    """
    def wrapper(*args, **kwargs):
        view = args[0].view
        edit = args[1]

        _UrtextProjectList = initialize_project_list(view)
        if not _UrtextProjectList:
            return None

        window = sublime.active_window()
        if not window:
            print('NO WINDOW')
            print(function)
            return
        
        window_id = window.id()
        if window_id in _SublimeUrtextWindows:
            current_path = _SublimeUrtextWindows[window_id]
            _UrtextProjectList.set_current_project_from_path(current_path)
            args[0]._UrtextProjectList = _UrtextProjectList
            args[0].edit = edit
            return function(args[0])

        if _UrtextProjectList.current_project:
            _SublimeUrtextWindows[window_id] = _UrtextProjectList.current_project.path
            args[0].edit = edit
            args[0]._UrtextProjectList = _UrtextProjectList
            return function(args[0])

        if init_project:
            
            return _UrtextProjectList
        
        return None

    return wrapper

def initialize_project_list(view, init_project=False, reload_projects=False):

    global _UrtextProjectList

    if reload_projects:
        _UrtextProjectList = None        

    if _UrtextProjectList == None:
        current_path = get_path(view)
        _UrtextProjectList = ProjectList(current_path)

    if not _UrtextProjectList.current_project and not init_project:
        return None
        
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
    
    @refresh_project_text_command
    def run(self):
        show_panel(
            self.window, 
            self._UrtextProjectList.project_titles(), 
            self.set_window_project)

    def set_window_project(self, title):
        self._UrtextProjectList.set_current_project_by_title(title)
        _SublimeUrtextWindows[self.view.window().id()] = self._UrtextProjectList.current_project.path
        
def refresh_project_event_listener(function):

    def wrapper(*args):
        view = args[1]
        
        if initialize_project_list(view) == None:
            return None

        window = sublime.active_window()
        if not window:
            print('NO WINDOW')
            print(function)
            return

        window_id = window.id()
        if window_id in _SublimeUrtextWindows:
            current_path = _SublimeUrtextWindows[window_id]
            _UrtextProjectList.set_current_project_from_path(current_path)
            args[0]._UrtextProjectList = _UrtextProjectList
            return function(args[0], view)

        if _UrtextProjectList.current_project:
            _SublimeUrtextWindows[window_id] = _UrtextProjectList.current_project.path
            args[0]._UrtextProjectList = _UrtextProjectList

            return function(args[0], view)
        return None

    return wrapper

class UrtextSaveListener(EventListener):

    def __init__(self):
        
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def on_query_completions(self, view, prefix, locations):

        if _UrtextProjectList.current_project == None:
            return

        completions = []
        for tag in _UrtextProjectList.current_project.tagnames['tags']:
            completions.append([tag, '/-- tags:'+tag+' --/'])

        return completions

    @refresh_project_event_listener
    def on_post_save(self, view):
        print('seen')
        print(view.file_name())

        future = self._UrtextProjectList.current_project.on_modified(view.file_name())
        print(future.result())
        self.executor.submit(refresh_open_file, future, view)

class UrtextDynamicNodeEditListener(EventListener):

    @refresh_project_event_listener
    def on_modified(self, view):
        filename = view.file_name()
        position = view.sel()[0].a
        source_id, position = self._UrtextProjectList.current_project.get_source_node(filename, position)
        if not source_id:
            return        
        open_urtext_node(view, source_id, position)

class KeepPosition(EventListener):

    @refresh_project_event_listener
    def on_modified(self, view):
        position = view.sel()

        def restore_position(view, position):
            if not view.is_loading():
                view.show(position)
            else:
                sublime.set_timeout(lambda: restore_position(view, position), 10)

        restore_position(view, position)

class NodeBrowserCommand(UrtextTextCommand):
    
    @refresh_project_text_command
    def run(self):
        self.menu = NodeBrowserMenu(self._UrtextProjectList.current_project.indexed_nodes(), self._UrtextProjectList)
        self.menu.add(self._UrtextProjectList.current_project.unindexed_nodes())
        show_panel(self.window, self.menu.display_menu, self.open_the_file)

    def open_the_file(self, selected_option):
        title = self.menu.get_values_from_index(selected_option).title
        
        new_view = self.window.open_file(
            os.path.join(
                _UrtextProjectList.current_project.path,
                self.menu.get_values_from_index(selected_option).filename))

        _UrtextProjectList.current_project.nav_new(
            self.menu.get_values_from_index(selected_option).node_id)

        self.locate_node(
            self.menu.get_values_from_index(selected_option).position,
            new_view, title)

    def locate_node(self, position, view, title):
        position = int(position)
        if not view.is_loading():
            view.sel().clear()
            view.show_at_center(position)
            view.sel().add(sublime.Region(position))
        else:
            sublime.set_timeout(
                lambda: self.locate_node(position, view, title), 10)

def size_to_groups(groups, view):
    panel_size = 1 / groups
    cols = [0]
    cells = [[0, 0, 1, 1]]
    for index in range(1, groups):
        cols.append(cols[index - 1] + panel_size)
        cells.append([index, 0, index + 1, 1])
    cols.append(1)
    view.window().set_layout({"cols": cols, "rows": [0, 1], "cells": cells})

class TagNodeCommand(UrtextTextCommand):  #under construction
    
    @refresh_project_text_command
    def run(self):
        self.tagnames = [value for value in self._UrtextProjectList.current_project.tagnames]
        self.view.window().show_quick_panel(self.tagnames, self.list_values)

    def list_values(self, index):
        if index == -1:
            return
        self.selected_tag = self.tagnames[index]
        self.values = [
            value for value in self._UrtextProjectList.current_project.tagnames[self.selected_tag]
        ]
        self.view.window().show_quick_panel(self.values, self.insert_tag)

    def insert_tag(self, index):
        if index == -1:
            return
        self.selected_value = self.values[index]
        timestamp = self.timestamp(datetime.datetime.now())
        tag = '/-- ' + self.selected_tag + ': ' + self.selected_value + ' ' + timestamp + ' --/'
        self.view.run_command("insert_snippet", {"contents": tag})

    def locate_from_in_node(self, index):  # useful in the future.
        selected_tag = self.values[index]
        max_size = self.view.size()
        region = self.view.sel()[0]
        subnode_regexp = re.compile(r'{{(?!.*{{)(?:(?!}}).)*}}', re.DOTALL)
        selection = self.view.substr(region)
        while not subnode_regexp.search(selection):
            a = region.a
            b = region.b
            if selection[:2] != '{{':
                a -= 1
            if selection[-2:] != '}}':
                b += 1
            region = sublime.Region(a, b)
            if a == 0 or b == max_size:  # entire file
                break
            selection = self.view.substr(region)

        metadata = urtext.metadata.NodeMetadata(selection[2:-2])
        # this all successfully identifies which node the cursor is in.
        # from here this should probably be done in the metadata class, not here.
        # get the metadata string out, probably using regex
        # find a place where the tag is

        if selected_tag not in metadata.get_tag(self.selected_tag):
            print('ADD IT')  # DEBUGGING


class ShowTreeFromNode(UrtextTextCommand):
    
    @refresh_project_text_command
    def run(self):

        def render_tree(view, tree_render):
            if not view.is_loading():
                view.run_command("insert_snippet", {"contents": tree_render})
            else:
                sublime.set_timeout(lambda: render_tree(view, tree_render), 10)

        filename = self.view.file_name()
        position = self.view.sel()[0].a
        node_id = self._UrtextProjectList.current_project.get_node_id_from_position(filename, position)
        tree_render = self._UrtextProjectList.current_project.show_tree_from(node_id)
        tree_view = target_tree_view(self.view)
        tree_view.erase(edit, sublime.Region(0, tree_view.size()))
        render_tree(tree_view, tree_render)

class ShowTreeFromRootCommand(UrtextTextCommand):
    
    @refresh_project_text_command
    def run(self, _UrtextProjectList):

        def render_tree(view, tree_render):
            if not view.is_loading():
                view.run_command("insert_snippet", {"contents": tree_render})
            else:
                sublime.set_timeout(lambda: render_tree(view, tree_render), 10)

        filename = os.path.basename(self.view.file_name())
        position = self.view.sel()[0].a
        node_id = self._UrtextProjectList.current_project.get_node_id_from_position(filename, position)
        tree_render = self._UrtextProjectList.current_project.show_tree_from(node_id, from_root_of=True)
        tree_view = target_tree_view(self.view)
        tree_view.erase(edit, sublime.Region(0, tree_view.size()))
        render_tree(tree_view, tree_render)

def target_tree_view(view):

    filename = view.file_name()
    if filename == None:
        return

    def locate_view(view, name):
        all_views = view.window().views()
        for view in all_views:
            if view.name() == name:
                return view
        return None

    tree_name = filename + 'TREE'  # Make a name for the view
    tree_view = locate_view(view, tree_name)
    if tree_view == None:
        tree_view = view.window().new_file()
        tree_view.set_name(filename + 'TREE')
        tree_view.set_scratch(True)

    # copied from traverse. Should refactor
    groups = view.window().num_groups()  
    
    active_group = view.window().active_group()  # 0-indexed
    if active_group == 0 or view.window().get_view_index(
            tree_view)[0] != active_group - 1:
        if groups > 1 and view.window().active_view_in_group(
                active_group - 1).file_name() == None:
            view.window().set_view_index(tree_view, active_group - 1, 0)
        else:
            groups += 1
            panel_size = 1 / groups
            cols = [0]
            cells = [[0, 0, 1, 1]]
            for index in range(1, groups):
                cols.append(cols[index - 1] + panel_size)
                cells.append([index, 0, index + 1, 1])
            cols.append(1)
            view.window().set_layout({
                "cols": cols,
                "rows": [0, 1],
                "cells": cells
            })
            view.settings().set("word_wrap", False)

            sheets = tree_view.window().sheets_in_group(active_group)
            index = 0
            for sheet in sheets:
                tree_view.window().set_sheet_index(
                    sheet,
                    groups - 1,  # 0-indexed from 1-indexed value
                    index)
                index += 1
            view.window().set_view_index(tree_view, active_group, 0)
            view.window().focus_group(active_group)
    return tree_view

class InsertInterlinksCommand(UrtextTextCommand):
    
    @refresh_project_text_command
    def run(self):
        position = self.view.sel()[0].a
        filename = self.view.file_name()
        node_id = self._UrtextProjectList.current_project.get_node_id_from_position(filename, position)
        insertion =  self._UrtextProjectList.current_project.insert_interlinks(node_id)
        self.view.run_command("insert_snippet",
                          {"contents": insertion}) 

class InsertNodeCommand(sublime_plugin.TextCommand):
    """ inline only, does not make a new file """
    @refresh_project_text_command
    def run(self):
        add_inline_node(self.view, one_line=False)

class InsertNodeSingleLineCommand(sublime_plugin.TextCommand):
    """ inline only, does not make a new file """
    def run(self, edit):
        add_inline_node(self.view, one_line=True, include_timestamp=False)    


def add_inline_node(view, one_line=False, include_timestamp=True):
    region = view.sel()[0]
    selection = view.substr(region)
    new_node_contents = _UrtextProjectList.current_project.add_inline_node(
        metadata={},
        contents=selection,
        one_line=one_line,
        include_timestamp=include_timestamp)[0]
    view.run_command("insert_snippet",
                          {"contents": new_node_contents})  # (whitespace)
    view.sel().clear()
    new_cursor_position = sublime.Region(region.a + 3, region.a + 3 ) 
    view.sel().add(new_cursor_position) 


class RenameFileCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self, edit):
        old_filename = self.view.file_name()
        new_filenames = self._UrtextProjectList.current_project.rename_file_nodes(old_filename)
        self.view.retarget(
            os.path.join(self._UrtextProjectList.current_project.path,
                         new_filenames[os.path.basename(old_filename)]))


class NodeBrowserMenu():
    """ custom class to store more information on menu items than is displayed """

    def __init__(self, node_ids, _UrtextProjectList):
        self.full_menu = make_node_menu(node_ids, _UrtextProjectList)
        self.display_menu = sort_menu(self.full_menu)
        self._UrtextProjectList = _UrtextProjectList

    def get_values_from_index(self, selected_option):
        index = self.display_menu.index(selected_option)
        return self.full_menu[index]

    def add(self, node_ids):
        self.full_menu.extend(
            make_node_menu(self._UrtextProjectList.current_project.unindexed_nodes(), _UrtextProjectList))
        self.display_menu = sort_menu(self.full_menu)

class NodeInfo():
    def __init__(self, node_id, _UrtextProjectList):
        self.title = _UrtextProjectList.current_project.nodes[node_id].title
        if self.title.strip() == '':
            self.title = '(no title)'
        self.date = _UrtextProjectList.current_project.nodes[node_id].date
        self.filename = _UrtextProjectList.current_project.nodes[node_id].filename
        self.position = _UrtextProjectList.current_project.nodes[node_id].ranges[0][0]
        self.title = _UrtextProjectList.current_project.nodes[node_id].title
        self.node_id = _UrtextProjectList.current_project.nodes[node_id].id


def make_node_menu(node_ids, _UrtextProjectList):
    menu = []
    for node_id in node_ids:
        item = NodeInfo(node_id, _UrtextProjectList)
        menu.append(item)
    return menu


def sort_menu(menu):
    display_menu = []
    for item in menu:  # there is probably a better way to copy this list.
        item.position = str(item.position)
        new_item = [
            item.title,
            item.date.strftime('<%a., %b. %d, %Y, %I:%M %p>')
        ]
        display_menu.append(new_item)
    return display_menu


class LinkToNodeCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        self.menu = NodeBrowserMenu(self._UrtextProjectList.current_project.nodes, self._UrtextProjectList)
        show_panel(self.window, self.menu.display_menu, self.link_to_the_file)

    def link_to_the_file(self, selected_option):
        view = self.window.active_view()
        node_id = self.menu.get_values_from_index(selected_option).node_id
        title = self.menu.get_values_from_index(selected_option).title
        view.run_command("insert", {"characters": '| '+title + ' >' + node_id})


class LinkNodeFromCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        self.current_file = os.path.basename(
            self.window.active_view().file_name())
        self.position = self.window.active_view().sel()[0].a
        self.menu = NodeBrowserMenu(self._UrtextProjectList.current_project.nodes, self._UrtextProjectList)
        show_panel(self.window, self.menu.display_menu,
                   self.link_from_the_file)

    def link_from_the_file(self, selected_option):
        new_view = self.window.open_file(
            self.menu.get_values_from_index(selected_option).filename)
        self.show_tip(new_view)

    def show_tip(self, view):
        if not view.is_loading():
            node_id = self._UrtextProjectList.current_project.get_node_id_from_position(
                self.current_file, self.position)

            title = self._UrtextProjectList.current_project.nodes[node_id].title
            link = title + ' >' + node_id
            sublime.set_clipboard(link)
            view.show_popup('Link to ' + link + ' copied to the clipboard')
        else:
            sublime.set_timeout(lambda: self.show_tip(view), 10)


def show_panel(window, menu, main_callback):
    def private_callback(index):
        if index == -1:
            return
        main_callback(menu[index])

    window.show_quick_panel(menu, private_callback)


def get_contents(view):
    if view != None:
        contents = view.substr(sublime.Region(0, view.size()))
        return contents
    return None

class ShowAllNodesCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        new_view = self.view.window().new_file()
        output = self._UrtextProjectList.current_project.list_nodes()
        new_view.run_command("insert", {"characters": output})

class NewNodeCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        path = self._UrtextProjectList.current_project.path
        new_node = self._UrtextProjectList.current_project.new_file_node()
        self._UrtextProjectList.current_project.nav_new(new_node['id'])        
        new_view = self.view.window().open_file(os.path.join(path, new_node['filename']))

class NewNodeWithLinkCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        path = self._UrtextProjectList.current_project.path
        new_node = self._UrtextProjectList.current_project.new_file_node()
        new_node_id = new_node['id']
        self.view.run_command("insert", {"characters":' >' + new_node_id})
        self.view.run_command("save")
        self._UrtextProjectList.current_project.nav_new(new_node_id)
        new_view = self.view.window().open_file(os.path.join(path, new_node['filename']))


class NewProjectCommand(UrtextTextCommand):

    def run(self, edit):
        global _UrtextProjectList        
        current_path = get_path(self.view)
        new_view = self.window.new_file()
        new_view.set_scratch(True)
        _UrtextProjectList.init_new_project(current_path)
        
class DeleteThisNodeCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        file_name = os.path.basename(self.view.file_name())
        if self.view.is_dirty():
            self.view.set_scratch(True)
        self.view.window().run_command('close_file')
        self._UrtextProjectList.current_project.delete_file(file_name) 

class InsertTimestampCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        datestamp = self._UrtextProjectList.current_project.timestamp(datetime.datetime.now())
        for s in self.view.sel():
            if s.empty():
                self.view.insert(self.edit, s.a, datestamp)
            else:
                self.view.replace(self.edit, s, datestamp)

class ConsolidateMetadataCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        self.view.run_command('save')  # TODO insert notification
        filename = os.path.basename(self.view.file_name())
        position = self.view.sel()[0].a
        node_id = self._UrtextProjectList.current_project.get_node_id_from_position(filename, position)
        self._UrtextProjectList.current_project.consolidate_metadata(node_id, one_line=True)


class InsertDynamicNodeDefinitionCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        now = datetime.datetime.now()
        node_id = self._UrtextProjectList.current_project.next_index()
        content = '[[ ID:' + node_id + '\n\n ]]'
        for s in self.view.sel():
            if s.empty():
                self.view.insert(self.edit, s.a, content)
            else:
                view.replace(self.edit, s, content)

class UrtextSearchProjectCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        caption = 'Search String: '
        self.view.window().show_input_panel(caption, '', self.search_project,
                                            None, None)

    def search_project(self, string):
        results = self._UrtextProjectList.current_project.search(string).split('\n')

        new_view = self.view.window().new_file()
        new_view.set_scratch(True)
        for line in results:
            new_view.run_command("insert_snippet", {"contents": line + '\n'})



class TagFromOtherNodeCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        # save the current file first
        full_line = self.view.substr(self.view.line(self.view.sel()[0]))
        links = re.findall(
            '(?:[^\|]*\s)?>(' + node_id_regex + ')(?:\s[^\|]*)?\|?', full_line)
        if len(links) == 0:
            return
        path = get_path(self.view)
        node_id = links[0]
        timestamp = self._UrtextProjectList.current_project.timestamp(datetime.datetime.now())

        # TODO move this into urtext, not Sublime
        tag = '/-- tags: done ' + timestamp + ' --/'
        _UrtextProjectList.current_project.tag_other_node(node_id, tag)

class GenerateTimelineCommand(UrtextTextCommand):

    @refresh_project_text_command
    def run(self):
        new_view = self.view.window().new_file()
        nodes = [
            self._UrtextProjectList.current_project.nodes[node_id] for node_id in self._UrtextProjectList.current_project.nodes
        ]
        timeline = self._UrtextProjectList.current_project.build_timeline(nodes)
        self.show_stuff(new_view, timeline)
        new_view.set_scratch(True)

    def show_stuff(self, view, timeline):
        if not view.is_loading():
            view.run_command("append", {"characters": timeline + '\n|'})
        else:
            sublime.set_timeout(lambda: self.show_stuff(view, timeline), 10)

class ShowLinkedRelationshipsCommand(sublime_plugin.TextCommand):
    """ Display a tree of all nodes connected to this one """

    # TODO: for files that link to the same place more than one time,
    # show how many times on one tree node, instead of showing multiple nodes
    # would this require building the tree after scanning all files?
    #
    # Also this command does not currently utilize the global array, it reads files manually.
    # Necessary to change it?

    @refresh_project_text_command
    def run(self):
        filename = os.path.basename(self.view.file_name())
        position = self.view.sel()[0].a
        node_id = self._UrtextProjectList.current_project.get_node_id_from_position(filename, position)
        render = self._UrtextProjectList.current_project.get_node_relationships(node_id)

        def draw_tree(view, render):
            if not view.is_loading():
                view.run_command("insert_snippet", {"contents": render})
                view.set_scratch(True)
            else:
                sublime.set_timeout(lambda: draw_tree(view, render), 10)

        window = self.view.window()
        window.focus_group(0)  # always show the tree on the leftmost focus'
        new_view = window.new_file()
        window.focus_view(new_view)
        draw_tree(new_view, render)

class ReIndexFilesCommand(sublime_plugin.TextCommand):
    
    @refresh_project_text_command
    def run(self):
        renamed_files = self._UrtextProjectList.current_project.reindex_files()
        for view in self.view.window().views():
            if view.file_name() == None:
                continue
            if os.path.basename(view.file_name()) in renamed_files:
                view.retarget(
                    os.path.join(
                        self._UrtextProjectList.current_project.path,
                        renamed_files[os.path.basename(view.file_name())]))

class AddNodeIdCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self):
        new_id = self._UrtextProjectList.current_project.next_index()
        self.view.run_command("insert_snippet",
                              {"contents": "/-- ID: " + new_id + " --/"})

class ImportProjectCommand(sublime_plugin.TextCommand):

    def run(self):
        self._UrtextProjectList.import_project(get_path(self.view))

class OpenUrtextLogCommand(sublime_plugin.TextCommand):
    def run(self):
        if refresh_project(self.view) == None:
            return
        file_view = self.view.window().open_file(
            os.path.join(_UrtextProjectList.current_project.path,
                         _UrtextProjectList.current_project.settings['logfile']))

        def go_to_end(view):
            if not view.is_loading():
                view.show_at_center(sublime.Region(view.size()))
                view.sel().add(sublime.Region(view.size()))
                view.show_at_center(sublime.Region(view.size()))
            else:
                sublime.set_timeout(lambda: go_to_end(view), 10)

        go_to_end(file_view)

class UrtextNodeListCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self):
        if 'zzz' in self._UrtextProjectList.current_project.nodes:
            self._UrtextProjectList.current_project.nav_new('zzz')
            open_urtext_node(self.view, 'zzz', 0)
        else:
            print('No zzz node')

class UrtextReloadProjectCommand(sublime_plugin.TextCommand):

    def run(self):
        if initialize_project_list(view, reload_projects=True) == None:
            print('No Urtext Project')
            return None

class ExportFromIdCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self):        
        filename = self.view.file_name()
        position = self.view.sel()[0].a
        node_id = self._UrtextProjectList.current_project.get_node_id_from_position(filename, position)
        print(node_id)
        exported = self._UrtextProjectList.current_project.export_from_root_node(node_id)
        new_view = self.view.window().new_file()
        new_view.run_command("insert_snippet", {
                "contents":
               exported
            })

class ExportFileAsHtmlCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self):        
        filename = self.view.file_name()
        self._UrtextProjectList.current_project.export(  filename, 
                                html_filename, 
                                kind='HTML',
                                single_file=True,
                                strip_urtext_syntax=False, 
                                style_titles=False)
        html_view = self.view.window().open_file(os.path.join(self._UrtextProjectList.current_project.path, html_filename))

class ExportProjectAsHtmlCommand(sublime_plugin.TextCommand):
    
    @refresh_project_text_command
    def run(self):        
        self._UrtextProjectList.current_project.export_project(jekyll=True, style_titles=False)

class CompactNodeCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self):
        add_compact_node(self.view)

class PopNodeCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self):
        filename = self.view.file_name()
        position = self.view.sel()[0].a
        new_position = self._UrtextProjectList.current_project.pop_node(filename=filename, position=position)
        if new_position:
            self.view.sel().clear()
            new_cursor_position = sublime.Region(new_position, new_position) 
            self.view.sel().add(new_cursor_position) 

class ToSourceNodeCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self):
        filename = self.view.file_name()
        position = self.view.sel()[0].a
        node_id = self._UrtextProjectList.current_project.get_node_id_from_position(filename, position)
        source_id, position = self._UrtextProjectList.current_project.get_source_node(filename, position)
        
        open_urtext_node(self.view, source_id, position)

class RebuildSearchIndexCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self, edit):
        self._UrtextProjectList.current_project.rebuild_search_index()


class SplitNodeCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self):
        node_id = self._UrtextProjectList.current_project.next_index()
        self.view.run_command("insert_snippet",
                          {"contents": '/-- id:'+node_id+' --/\n% '})

class RandomNodeCommand(sublime_plugin.TextCommand):

    @refresh_project_text_command
    def run(self):
        node_id = self._UrtextProjectList.current_project.random_node()
        open_urtext_node(self.view, node_id, self._UrtextProjectList.current_project.nodes[node_id].ranges[0][0])

"""
Utility functions
"""
def open_urtext_node(view, node_id, position):
    
    def center_node(new_view, position):  # copied from old OpenNode. Refactor
        if not new_view.is_loading():
            new_view.sel().clear()
            # this has to be called both before and after:
            new_view.show_at_center(position)
            new_view.sel().add(sublime.Region(position))
            # this has to be called both before and after:
            new_view.show_at_center(position)
        else:
            sublime.set_timeout(lambda: center_node(new_view, position), 20)

    filename = _UrtextProjectList.current_project.get_file_name(node_id)
    if filename == None:
        return
    file_view = view.window().open_file(
        os.path.join(_UrtextProjectList.current_project.path, filename))

    center_node(file_view, position)

def add_compact_node(view):
    
    region = view.sel()[0]
    
    selection = view.substr(region)
    new_node_contents = _UrtextProjectList.current_project.add_compact_node(contents=selection)
    view.run_command("insert_snippet",
                          {"contents": new_node_contents})
    view.sel().clear()
    new_cursor_position = sublime.Region(region.a + 2, region.a + 2) 
    view.sel().add(new_cursor_position) 

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
    filename = view.file_name()
    changed_files = future.result()
    if os.path.basename(filename) in changed_files:
        view.run_command('revert') # undocumented
