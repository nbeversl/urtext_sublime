import os
import re
from io import StringIO
import sys

if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../sublime.txt')):
	from Urtext.urtext.directive import UrtextDirective
	from Urtext.urtext.action import UrtextAction
	from Urtext.urtext.extension import UrtextExtension
else:
	from urtext.directive import UrtextDirective
	from urtext.action import UrtextAction
	from urtext.extension import UrtextExtension

python_code_regex = re.compile(r'(%%Python)(.*?)(%%)', re.DOTALL)

class Exec(UrtextDirective):

	name = ["EXEC"]
	phase = 350

	def dynamic_output(self, input_contents):
		if self.argument_string in self.project.nodes:
			contents = self.project.nodes[self.argument_string].contents(do_strip_embedded_syntaxes=False)
			python_embed = python_code_regex.search(contents)
			if python_embed:
				python_code = python_embed.group(2)
				old_stdout = sys.stdout
				sys.stdout = mystdout = StringIO()
				localsParameter = {
					'ThisProject' : self.project,
					'UrtextDirective' : UrtextDirective,
					'UrtextAction' : UrtextAction,
					'UrtextExtension' : UrtextExtension,
				}
				try:
					exec(python_code, {}, localsParameter)
					sys.stdout = old_stdout
					message = mystdout.getvalue()
					self.project._collect_extensions_directives_actions()
					return message
				except Exception as e:
					sys.stdout = old_stdout
					return str(e)

		return '(no Python code found)'

