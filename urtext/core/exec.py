import os
import re
from io import StringIO
import sys

if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../sublime.txt')):
	from Urtext.urtext.utils import force_list, get_id_from_link
else:
	from urtext.utils import force_list, get_id_from_link

python_code_regex = re.compile(r'(%%Python)(.*?)(%%)', re.DOTALL)

class Exec:

	name = ["EXEC"]
	phase = 350

	def dynamic_output(self, input_contents):
		node_to_exec = get_id_from_link(self.argument_string)
		if node_to_exec in self.project.nodes:
			contents = self.project.nodes[node_to_exec].full_contents
			python_embed = python_code_regex.search(contents)
			if python_embed:
				python_code = python_embed.group(2)
				old_stdout = sys.stdout
				sys.stdout = mystdout = StringIO()
				localsParameter = {'ThisProject' : self.project }
				try:
					exec(python_code, {}, localsParameter)
					sys.stdout = old_stdout
					message = mystdout.getvalue()
					return message
				except Exception as e:
					sys.stdout = old_stdout
					return str(e)

		return '(no Python code found)'

urtext_directives=[Exec]
