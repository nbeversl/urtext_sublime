import os
import re

if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sublime.txt')):
    from .buffer import UrtextBuffer
    import Urtext.urtext.syntax as syntax 
else:
    from urtext.buffer import UrtextBuffer
    import urtext.syntax as syntax

class UrtextFile(UrtextBuffer):
   
    def __init__(self, filename, project):
        self.filename = filename
        self.contents = self._read_contents()
        super().__init__(project, self.contents)
        
        self.clear_messages_and_parse()
        for node in self.nodes:
            node.filename = filename
            node.file = self

    def _get_contents(self):            
        return self.contents

    def _read_contents(self):
        """ returns the file contents, filtering out Unicode Errors, directories, other errors """
        try:
            with open(self.filename, 'r', encoding='utf-8') as theFile:
                full_file_contents = theFile.read()
        except IsADirectoryError:
            return None
        except UnicodeDecodeError:
            self.log_error(''.join([
                'UnicodeDecode Error: ',
                syntax.file_link_opening_wrapper,
                self.filename,
                syntax.file_link_closing_wrapper]), 0)
            return None
        return full_file_contents

    def _insert_contents(self, inserted_contents, position):
        self._set_contents(''.join([
            self.contents[:position],
            inserted_contents,
            self.contents[position:],
            ]))

    def _replace_contents(self, inserted_contents, range):
        self._set_contents(''.join([
            self.contents[:range[0]],
            inserted_contents,
            self.contents[range[1]:],
            ]))

    def _set_contents(self, new_contents, compare=True): 
        new_contents = '\n'.join(new_contents.splitlines())
        if compare:
            existing_contents = self._get_contents()
            if existing_contents == new_contents:
                return False
        with open(self.filename, 'w', encoding='utf-8') as theFile:
            theFile.write(new_contents)
        self.contents = new_contents
        return True
