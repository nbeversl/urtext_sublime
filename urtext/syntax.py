import re

# Units

pattern_break =                         r'($|(?=[\\s|\r|]))'

# Base Patterns

action =                                r'>>>([A-Z_\-\+]+)\((.*)\)'
bullet =                                r'^([^\S\n]*?)•'
closing_wrapper =                       r'(?<!\\)}'
dynamic_def =                           r'(?:\[\[)([^\]]*?)(?:\]\])'
editor_file_link =                      r'(f>{1,2})([^;]+)'
embedded_syntax_open =                  r'(%%-[A-Z-]+?)'
embedded_syntax_full =                  r'(%%-[A-Z-]+?)'
embedded_syntax_close =                 r'%%-[A-Z-]+?-END'
error_messages =                        r'<!{1,2}.*?!{1,2}>\n?'
flag =                                  r'((^|\s)(-[\w|_]+)|((^|\s)\*))(?=\s|$)'
# flag =                                r'(^|\s)-[\w|_]+(?=\s|$)' ???
function =                              r'([A-Z_\-\+]+)\((.*?)\)'
format_key =                            r'\$_?[\.A-Za-z0-9_-]*'
hash_key =                              r'#'
metadata_assigner =                     r'::'
metadata_end_marker =                   r';'
metadata_entry =                        r'[+]?\*{0,2}\w+\:\:[^\n;]+[\n;]?'
metadata_separator =                    r'\s-\s|$'
metadata_tag_self =                     r'\+'
metadata_tag_desc =                     r'\*'
opening_wrapper =                       r'(?<!\\){'
pop_syntax =                            r'%%-[A-Z]*-END'
preformat =                             r'\`.*?\`'
push_syntax =                           r'%%-[A-Z]*'+pattern_break
sub_node =                              r'(?<!\\){(?!.*(?<!\\){)(?:(?!}).)*}'
timestamp =                             r'<([^-/<\s][^=<]+?)>'
title_pattern =                         r"(([^>\n\r_])|(?<!\s)_)+"
url =                                   r'http[s]?:\/\/(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

# Composite patterns

compact_node =                          bullet + r'([^\r\n]*)(\n|$)'
hash_meta =                             r'(?:^|\s)'+ hash_key + r'[A-Z,a-z].*?\b'
node_link =                             r'(\|\s)(' + title_pattern + ')\s>(?!>)'
node_link_or_pointer =                  r'(\|\s)(' + title_pattern + ')\s>{1,2}(?!>)'
node_pointer =                          r'(\|\s)(' + title_pattern + ')\s>>(?!>)'
node_title =                            r'^'+ title_pattern +r'(?= _)'

# Compiled Patterns

action_c =                      re.compile(action, re.DOTALL)
bullet_c =                      re.compile(bullet)
compact_node_c =                re.compile(compact_node, re.MULTILINE)
closing_wrapper_c =             re.compile(closing_wrapper)
dynamic_def_c =                 re.compile(dynamic_def, re.DOTALL)
editor_file_link_c =            re.compile(editor_file_link)
embedded_syntax_open_c =        re.compile(embedded_syntax_open, flags=re.DOTALL)
embedded_syntax_c =             re.compile(embedded_syntax_full, flags=re.DOTALL)
embedded_syntax_close_c =       re.compile(embedded_syntax_close, flags=re.DOTALL)
error_messages_c =              re.compile(error_messages, flags=re.DOTALL)
flag_c =                        re.compile(flag)
format_key_c =                  re.compile(format_key, re.DOTALL)
function_c =                    re.compile(function, re.DOTALL)
hash_key_c =                    re.compile(hash_key)
hash_meta_c =                   re.compile(hash_meta)
metadata_entry_c =              re.compile(metadata_entry, re.DOTALL)
metadata_separator_c =          re.compile(metadata_separator)
metadata_tag_self_c =           re.compile(metadata_tag_self)
metadata_tag_desc_c =           re.compile(metadata_tag_desc)
node_title_c =                  re.compile(node_title, re.MULTILINE)
metadata_assigner_c =           re.compile(metadata_assigner)
node_link_c =                   re.compile(node_link)
node_link_or_pointer_c =        re.compile(node_link_or_pointer)
opening_wrapper_c =             re.compile(opening_wrapper)
preformat_c =                   re.compile(preformat, flags=re.DOTALL)
subnode_regexp_c =              re.compile(sub_node, re.DOTALL)
timestamp_c =                   re.compile(timestamp)
title_regex_c =                 re.compile(title_pattern)
url_c =                         re.compile(url)                       

metadata_replacements = re.compile("|".join([
    r'(?:<)([^-/<\s`][^=<]+?)(?:>)',        # timestamp
    r'\*{2}\w+\:\:([^\n};]+);?',            # inline_meta
    r'(?:^|\s)#[A-Z,a-z].*?(\b|$)',         # shorthand_meta
    ]))

compiled_symbols = {
    opening_wrapper_c :                 'opening_wrapper',
    closing_wrapper_c :                 'closing_wrapper',
    re.compile(node_pointer) :          'pointer',
    re.compile(push_syntax) :           'push_syntax', 
    re.compile(pop_syntax) :            'pop_syntax',
    compact_node_c :                    'compact_node'
    }

