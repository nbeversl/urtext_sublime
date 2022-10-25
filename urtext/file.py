# -*- coding: utf-8 -*-
"""
This file is part of Urtext.

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
import os
import re
import concurrent.futures

if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sublime.txt')):
    from .node import UrtextNode
    from .utils import strip_backtick_escape
    from .syntax import compiled_symbols, error_messages, node_pointer_regex
else:
    from urtext.node import UrtextNode
    from urtext.utils import strip_backtick_escape
    from urtext.syntax import compiled_symbols, error_messages, node_pointer_regex

class UrtextBuffer:

    urtext_node = UrtextNode

    def __init__(self, contents, project):
        
        self.nodes = {}
        self.root_nodes = []
        self.alias_nodes = []           
        self.parsed_items = {}
        self.strict = False
        self.messages = []        
        self.errors = False
        self.contents = contents
        self.filename = 'yyyyyyyyyyy'
        self.basename = 'yyyyyyyyyyy'
        self.project = project
        self.could_import = False        
        self.file_length = len(contents)
        self.lex(contents)
        self.parse(contents)
        # self.obj = {}
            
    def lex(self, contents):
       
        self.symbols = {}

        contents = strip_backtick_escape(contents)
        for symbol, symbol_type in compiled_symbols.items():
            for match in symbol.finditer(contents):
                self.symbols[match.span()[0]] = {}
                self.symbols[match.span()[0]]['type'] = symbol_type
                self.symbols[match.span()[0]]['length'] = len(match.group())                
                if symbol_type == 'pointer':
                    self.symbols[match.span()[0]]['contents'] = match.group(1)
                if symbol_type == 'compact_node':
                    self.symbols[match.span()[0]]['contents'] = match.group(2)

        self.positions = sorted([position for position in self.symbols if position != -1])
        
        ## Filter out Syntax Push and delete wrapper elements between them.
        push_syntax = 0
        to_remove = []
        for p in self.positions:
            
            if self.symbols[p]['type'] == 'push_syntax' :
                to_remove.append(p)
                push_syntax += 1
                continue
            
            if self.symbols[p]['type'] == 'pop_syntax':
                to_remove.append(p)
                push_syntax -= 1
                continue

            if push_syntax > 0:
                to_remove.append(p)

        for s in to_remove:
            del self.symbols[s]
            self.positions.remove(s)

        self.positions.append(len(contents))
        self.symbols[len(contents)] = { 'type': 'EOF', 'length' : 0}

    def parse(self, contents):
 
        nested = 0  #  depth of node nesting
        nested_levels = {} # store node nesting into layers
        last_position = 0  # most recently parsed position in file
        compact_node_open = False

        first_wrapper = 0
        while first_wrapper < len(self.positions) - 1 and self.symbols[self.positions[first_wrapper]]['type'] == 'pointer':
            first_wrapper += 1

        nested_levels[0] = [ 
            [0, self.positions[first_wrapper] + self.symbols[self.positions[first_wrapper]]['length'] ] 
            ]

        unstripped_contents = contents
        contents = strip_backtick_escape(contents)

        for position in self.positions:

            last_position = position + self.symbols[position]['length']

            # Allow node nesting arbitrarily deep
            nested_levels[nested] = [] if nested not in nested_levels else nested_levels[nested]
            
            if self.symbols[position]['type'] == 'opening_wrapper':

                if [last_position, position + 1] not in nested_levels[nested]:
                    nested_levels[nested].append([last_position, position + 1])

                nested += 1 
                continue

            if self.symbols[position]['type'] == 'compact_node': 
                self.add_node( 
                    [[ position, position + len(self.symbols[position]['contents']) ]], 
                    unstripped_contents, 
                    position, 
                    root=False,
                    compact=True)
                continue    

            if self.symbols[position]['type'] in ['closing_wrapper', 'EOF']:  # pop
                
                root = False
                
                if [last_position, position] not in nested_levels[nested]: # avoid duplicates
                    nested_levels[nested].append([last_position, position ])
                
                if nested == 0 or self.symbols[position]['type'] == 'EOF':
                    if self.strict and nested != 0:
                        #TODO -- if a compact node closes the file, this error will be thrown.
                        self.log_error('Missing closing wrapper', position)
                        return None

                    root = True

                self.add_node(
                    nested_levels[nested], 
                    unstripped_contents, 
                    position, 
                    root=root)

                del nested_levels[nested]

                if self.symbols[position] == 'EOF' and compact:
                    # handle closing of file
                    nested -=1
                    root=True

                    success = self.add_node(
                        nested_levels[nested], 
                        unstripped_contents,
                        position,
                        root=root)

                # last_position = position + symbol_length[self.symbols[position]]

                # reduce the nesting level only for compact, inline nodes
                if not root:
                    nested -= 1                       

                if nested < 0:
                    message = 'Stray closing wrapper at %s' % str(position)
                    if self.strict:
                        return self.log_error(message, position)  
                    else:
                        self.messages.append(message) 

        if nested > 0:
            message = 'Un-closed node at %s' % str(position) + ' in ' + self.filename
            if self.strict:
                return self.log_error(message, position)  
            else:
                self.messages.append(message) 

        if len(self.root_nodes) == 0:
            message = 'No root nodes found'
            if self.strict: 
                return self.log_error(message, 0)
            else: 
                self.messages.append(message)

    def add_node(self, 
        ranges, 
        contents,
        position,
        root=None,
        compact=None):

        # Build the node contents and construct the node
        
        node_contents = ''.join([contents[r[0]:r[1]]  for r in ranges])

        new_node = self.urtext_node(
            self.filename, 
            node_contents,
            self.project,
            root=root,
            compact=compact)
        
        new_node.get_file_contents = self._get_file_contents
        new_node.set_file_contents = self._set_file_contents
        self.nodes[new_node.id] = new_node
        self.nodes[new_node.id].ranges = ranges
        if new_node.root_node:
            self.root_nodes.append(new_node.id) 
        self.parsed_items[ranges[0][0]] = new_node.id
            
    def _get_file_contents(self):
          return self.contents 
          
    def _set_file_contents(self, contents):
          return
          
    def get_node_id_from_position(self, position):
        for node_id in self.nodes:
            for r in self.nodes[node_id].ranges:
                if position in range(r[0],r[1]+1): # +1 in case the cursor is in the last position of the node.
                    return node_id
        return None

    def clear_errors(self, contents):
        cleared_contents = re.sub(error_messages, '', contents, flags=re.DOTALL)
        if cleared_contents != contents:
            self._set_file_contents(cleared_contents)
        self.errors = False
        return cleared_contents

    def write_errors(self, settings, messages=None):
        if not messages and not self.messages:
            return False
        if messages:
            self.messages = messages
        
        if self.nodes == {}:
            self.could_import = True
            return

        contents = self._get_file_contents()

        messages = ''.join([ 
            '<!!\n',
            '\n'.join(self.messages),
            '\n!!>\n',
            ])

        message_length = len(messages)
        
        for n in re.finditer('position \d{1,10}', messages):
            old_n = int(n.group().strip('position '))
            new_n = old_n + message_length
            messages = messages.replace(str(old_n), str(new_n))

        if len(messages) != message_length:
            pass
             
        new_contents = ''.join([
            messages,
            contents,
            ])

        self._set_file_contents(new_contents, compare=False)
        self.nodes = {}
        self.root_nodes = []
        self.parsed_items = {}
        self.messages = []
        self.parse(new_contents)
        self.errors = True
        for n in self.nodes:
            self.nodes[n].errors = True

    def get_ordered_nodes(self):
        return sorted( 
            list(self.nodes.keys()),
            key=lambda node_id :  self.nodes[node_id].ranges[0][0])

    def log_error(self, message, position):

        self.nodes = {}
        self.parsed_items = {}
        self.root_nodes = []
        self.file_length = 0
        self.messages.append(message +' at position '+ str(position))

        print(''.join([ 
                message, ' in >f', self.filename, ' at position ',
            str(position)]))

class UrtextFile(UrtextBuffer):
   
    def __init__(self, filename, project):
        self.basename = os.path.basename(filename)
        self.nodes = {}
        self.root_nodes = []
        self.alias_nodes = []           
        self.parsed_items = {}
        self.strict = False
        self.messages = []        
        self.errors = False
        self.project = project
        
        self.filename = os.path.join(project.path, os.path.basename(filename))
        contents = self._get_file_contents()
        self.could_import = False        
        self.file_length = len(contents)        
        self.clear_errors(contents)
        self.lex(contents)
        self.parse(contents)
        self.write_errors(project.settings)
      
    def _get_file_contents(self):
        
        """ returns the file contents, filtering out Unicode Errors, directories, other errors """
        try:
            with open(self.filename, 'r', encoding='utf-8',) as theFile:
                full_file_contents = theFile.read()
        except IsADirectoryError:
            return None
        except UnicodeDecodeError:
            self.log_error('UnicodeDecode Error: f>' + self.filename)
            return None
        return full_file_contents.encode('utf-8').decode('utf-8')

    def _set_file_contents(self, new_contents, compare=True): 

        new_contents = "\n".join(new_contents.splitlines())
        if compare:
            existing_contents = self._get_file_contents()
            existing_contents = "\n".join(existing_contents.splitlines())
            if not existing_contents:
                return False
            if existing_contents == new_contents:
                return False
        with open(self.filename, 'w', encoding='utf-8') as theFile:
            theFile.write(new_contents)
        return True

