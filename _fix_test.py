import re

p = "common/tests/test_ui_overhaul_console_avatars.py"
s = open(p, encoding="utf-8", newline="").read()
pattern = re.compile(r'        block = re\.search\(r"COLLECT = \\\(\(\.\*\?\)\?\r?\n\\\)", EXE_BUILDER, re\.S\)\.group\(1\)')
assert pattern.search(s), "pattern not found"
new = '        block = re.search(r"COLLECT = \\((.*?)\\n\\)", EXE_BUILDER.replace("\\r\\n", "\\n"), re.S).group(1)'
s = pattern.sub(lambda m: new, s)
open(p, "w", encoding="utf-8", newline="").write(s)
print("fixed")
