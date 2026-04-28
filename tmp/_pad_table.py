lines = open(".cursor/project-instructions.md", encoding="utf-8").read().splitlines()
ref = lines[13]  # skills row, 143 chars
first_sep = ref.index("|", 1) + 1
first_col = ref[:first_sep]  # includes first |
# rebuild first col for agents: same width as ref's cell1+delimiter
cell1_ref = ref[1:first_sep - 1]  # content between | and |
# ref cell1 is " `skills/*/SKILL.md`   "
agents_cell = " `agents/*.md`" + " " * (len(cell1_ref) - len(" `agents/*.md`"))
first_col_new = "|" + agents_cell + "|"
assert len(first_col_new) == len(ref[: first_sep + 1]) - 1  # hmm
# actually first_sep points to index of second | in row
# ref[:first_sep+1] is from start through second |
prefix = ref[: ref.index("|", 1) + 1]
#   prefix = '| `skills/*/SKILL.md`   |'
want_len = len(prefix)
agents_prefix = "| `agents/*.md`" + " " * (want_len - len("| `agents/*.md`") - 1) + "|"
print("ref prefix", repr(prefix), len(prefix))
print("new prefix", repr(agents_prefix), len(agents_prefix))
suffix = ref[ref.index("|", 1) + 1 :]  # second column + final |
# replace second column text keeping same total length
new_text = "Subagentes; `/nome` no Agent; doc em cursor.com/docs/subagents.md."
# suffix format: ' Workflows...                                                   |'
inner_width = len(suffix) - 2  # minus leading space and trailing |
# suffix starts with space, ends with |
old_inner = suffix[1:-1]
padding = len(old_inner) - len(new_text)
if padding < 1:
    raise SystemExit("text too long", len(old_inner), new_text)
new_suffix = " " + new_text + " " * padding + "|"
line_new = agents_prefix + new_suffix
print("line_new len", len(line_new), repr(line_new))
print("ref len", len(ref))
assert len(line_new) == len(ref)
