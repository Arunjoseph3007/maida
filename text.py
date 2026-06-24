from maida import *
from dataclasses import dataclass
from typing import List
from contextlib import contextmanager
from io import StringIO
import base64
import pathlib
import re
import os
import sys

Buffer = List[str]


def dir_entry_sort(k: os.DirEntry[str]):
    if k.is_dir():
        return "0" + k.name
    return "1" + k.name


class Anchor:
    def __init__(self):
        self.cx = 0
        self.cy = 0

    def pair(self):
        return self.cx, self.cy

    def cursor_regulate(self, lines):
        if self.cx > len(lines[self.cy]):
            self.cx = len(lines[self.cy])

    def left(self, lines):
        self.cursor_regulate(lines)

        if self.cx > 0:
            self.cx -= 1
        elif self.cy > 0:
            self.cy -= 1
            self.cx = len(lines[self.cy])

    def right(self, lines):
        self.cursor_regulate(lines)
        if self.cx < len(lines[self.cy]):
            self.cx += 1
        elif self.cy < len(lines):
            self.cy += 1
            self.cx = 0

    def up(self, lines):
        if self.cy > 0:
            self.cy -= 1
        else:
            self.cx = 0

    def down(self, lines):
        if self.cy < len(lines) - 1:
            self.cy += 1

    def __eq__(self, value: Anchor):
        if type(self) != type(value):
            raise Exception(f"Cant compare {type(value)} with {type(self)}")

        return self.cx == value.cx and self.cy == value.cy

    def __lt__(self, value: Anchor):
        if type(self) != type(value):
            raise Exception(f"Cant compare {type(value)} with {type(self)}")

        if self.cy != value.cy:
            return self.cy < value.cy
        return self.cx < value.cx

    def __gt__(self, value: Anchor):
        if type(self) != type(value):
            raise Exception(f"Cant compare {type(value)} with {type(self)}")

        if self.cy != value.cy:
            return self.cy > value.cy
        return self.cx > value.cx

    def __str__(self):
        return f"Anchor(cx={self.cx}, cy={self.cy})"


class Cursor:
    def __init__(self):
        self.start = Anchor()
        self.end = Anchor()

    def __str__(self):
        if self.is_selection():
            return f"Cursor({self.start}, {self.end})"
        return f"Cursor({self.start})"

    def is_selection(self):
        return self.start != self.end

    def is_within_selection(self, x, y):
        if not self.is_selection():
            return False

        sx, sy = self.sel_start
        ex, ey = self.sel_end
        if sy == ey:
            return sy == y and sx <= x < ex
        if sy < y < ey:
            return True
        if y == sy:
            return x >= sx
        if y == ey:
            return x < ex
        return False

    def get_selection_text(self, lines):
        if not self.is_selection():
            return ""

        sx, sy = self.sel_start
        ex, ey = self.sel_end
        if sy == ey:
            return lines[sy][sx:ex]
        else:
            text = lines[sy][sx:] + "\n"
            for i in range(sy + 1, ey):
                text += lines[i] + "\n"
            return text + lines[ey][:ex]

    def empty_selection(self, lines: list):
        if not self.is_selection():
            return
        if self.start.cy == self.end.cy:
            y = self.start.cy
            minx = min(self.start.cx, self.end.cx)
            maxx = max(self.start.cx, self.end.cx)
            lines[y] = lines[y][:minx] + lines[y][maxx:]
        else:
            ssx, ssy = self.sel_start
            sex, sey = self.sel_end
            pre = lines[ssy][:ssx]
            post = lines[sey][sex:]

            new_lines = lines[:ssy] + [pre + post] + lines[sey + 1 :]
            lines.clear()
            lines.extend(new_lines)
        self.collapse_to_selstart()

    @property
    def sel_start(self):
        if self.start < self.end:
            return self.start.cx, self.start.cy
        return self.end.cx, self.end.cy

    @property
    def sel_end(self):
        if self.start > self.end:
            return self.start.cx, self.start.cy
        return self.end.cx, self.end.cy

    def collapse_to_selstart(self):
        ssx, ssy = self.sel_start
        self.start.cx = ssx
        self.end.cx = ssx
        self.start.cy = ssy
        self.end.cy = ssy

    def collapse_to_selend(self):
        sex, sey = self.sel_end
        self.start.cx = sex
        self.end.cx = sex
        self.start.cy = sey
        self.end.cy = sey

    def up(self, lines):
        if self.is_selection():
            self.collapse_to_selstart()
        else:
            self.start.up(lines)
            self.end.up(lines)

    def down(self, lines):
        if self.is_selection():
            self.collapse_to_selend()
        else:
            self.start.down(lines)
            self.end.down(lines)

    def left(self, lines):
        if self.is_selection():
            self.collapse_to_selstart()
        else:
            self.start.left(lines)
            self.end.left(lines)

    def right(self, lines):
        if self.is_selection():
            self.collapse_to_selend()
        else:
            self.start.right(lines)
            self.end.right(lines)

    def copy(self):
        c = Cursor()
        c.start.cx = self.start.cx
        c.start.cy = self.start.cy
        c.end.cx = self.end.cx
        c.end.cy = self.end.cy
        return c


@dataclass
class Edit:
    start: int
    plus: Buffer
    minus: Buffer
    start_cursor: Cursor = None
    end_cursor: Cursor = None

    @staticmethod
    def from_diff(a: Buffer, b: Buffer):
        if a == b:
            return Edit(start=0, plus=[], minus=[])

        start = 0
        while start < len(a) and start < len(b) and a[start] == b[start]:
            start += 1

        endA = len(a)
        endB = len(b)
        while endA > start and endB > start and a[endA - 1] == b[endB - 1]:
            endA -= 1
            endB -= 1

        return Edit(start=start, plus=b[start:endB], minus=a[start:endA])

    def undo(self, buffer: Buffer):
        for _ in self.plus:
            buffer.pop(self.start)

        for i, l in enumerate(self.minus):
            buffer.insert(self.start + i, l)

    def redo(self, buffer: Buffer):
        for _ in self.minus:
            buffer.pop(self.start)

        for i, l in enumerate(self.plus):
            buffer.insert(self.start + i, l)

    def __str__(self):
        return f"Edit(st={self.start}, p={self.plus and self.plus[0]}, m={self.minus and self.minus[0]})"


Histroy = List[Edit]
MAX_UNDO_HISTORY_SIZE = 100


class TokenTypes(enum.StrEnum):
    WHITESPACE = enum.auto()
    COMMENT = enum.auto()
    CONTROL = enum.auto()
    DECLARATION = enum.auto()
    CONTEXT = enum.auto()
    LITERAL = enum.auto()
    STRING = enum.auto()
    NUMERIC = enum.auto()
    OPERATOR = enum.auto()
    VARIABLE = enum.auto()
    PUNCTUATION = enum.auto()


@dataclass
class GrammarRule:
    name: TokenTypes
    start_match: str
    end_match: str | None = None

    def is_region_based(self):
        return self.end_match is not None


@dataclass
class GrammarMatch:
    start: int
    end: int
    line: int
    matched_class: TokenTypes


class Grammar:
    patterns: List[GrammarRule]
    name: str

    def __init__(self, name: str):
        self.patterns = []
        self.name = name

    def add_rule(self, name, start, end=None):
        self.patterns.append(GrammarRule(name, start, end))

    def parse_text_buffer(self, tb: list[str]) -> list[GrammarMatch]:
        result = []
        line_no = 0

        while line_no < len(tb):
            i = 0
            while i < len(tb[line_no]):
                c = tb[line_no][i]

                # Ignore whitespace
                if c in (" ", "\r", "\t"):
                    result.append(GrammarMatch(start=i, end=i + 1, matched_class=TokenTypes.WHITESPACE, line=line_no))
                    i += 1
                    continue

                found = False
                for rule in self.patterns:

                    # Region-based matching
                    if rule.is_region_based():
                        start_m = re.match(rule.start_match, tb[line_no][i:])
                        if start_m:
                            found = True
                            start = i
                            i += len(start_m.group(0))

                            end_m = re.search(rule.end_match, tb[line_no][i:])
                            if end_m:
                                # End found on the same line
                                end = i + end_m.end()
                                result.append(GrammarMatch(start=start, end=end, matched_class=rule.name, line=line_no))
                                i = end
                            else:
                                # End not on the same line — span across lines
                                result.append(
                                    GrammarMatch(start=start, end=len(tb[line_no]), matched_class=rule.name, line=line_no)
                                )
                                line_no += 1

                                while line_no < len(tb):
                                    end_m = re.search(rule.end_match, tb[line_no])
                                    if end_m:
                                        break
                                    result.append(
                                        GrammarMatch(start=0, end=len(tb[line_no]), matched_class=rule.name, line=line_no)
                                    )
                                    line_no += 1

                                if line_no < len(tb):
                                    end = end_m.end()
                                    result.append(GrammarMatch(start=0, end=end, matched_class=rule.name, line=line_no))
                                    i = end

                            break

                    # Token-based matching
                    else:
                        match = re.match(rule.start_match, tb[line_no][i:])
                        if match:
                            found = True
                            end = i + len(match.group(0))
                            result.append(GrammarMatch(start=i, end=end, matched_class=rule.name, line=line_no))
                            i = end
                            break

                if not found:
                    i += 1

            line_no += 1

        return result


def jsGrammar():
    js = Grammar("js")

    js.add_rule(TokenTypes.COMMENT, r"\/\/.*")
    js.add_rule(TokenTypes.COMMENT, r"\/\*", r"\*\/")

    js.add_rule(
        TokenTypes.CONTROL,
        r"\b(break|case|catch|continue|default|do|else|finally|for|if|return|switch|throw|try|while|with)\b",
    )
    js.add_rule(TokenTypes.DECLARATION, r"\b(var|let|const|function|class)\b")
    js.add_rule(TokenTypes.CONTEXT, r"\b(this|super|new|delete|typeof|void|yield|await|import|export)\b")
    js.add_rule(TokenTypes.LITERAL, r"\b(true|false|null)\b")

    js.add_rule(TokenTypes.STRING, r"\"", r"\"")
    js.add_rule(TokenTypes.STRING, r"'", r"'")
    js.add_rule(TokenTypes.STRING, r"`", r"`")

    js.add_rule(
        TokenTypes.NUMERIC,
        r"\b(?:0[bB][01]+|0[oO][0-7]+|0[xX][\dA-Fa-f]+|\d+(\.\d+)?([eE][+-]?\d+)?|\.\d+([eE][+-]?\d+)?)\b",
    )
    js.add_rule(
        TokenTypes.OPERATOR,
        r"(\+\+|--|===|==|!==|!=|<=|>=|<|>|\+=|-=|\*=|\/=|%=|\*\*|&&|\|\||!|=|\+|-|\*|\/|%|\*\*=|&=|\|=|\^=|<<=|>>=|>>>=|&|\||\^|~|<<|>>|>>>|\?|:|=>)",
    )
    js.add_rule(TokenTypes.VARIABLE, r"\b[a-zA-Z_$][a-zA-Z0-9_$]*\b")
    js.add_rule(TokenTypes.PUNCTUATION, r"[.,;()[\]{}]")

    return js


def pythonGrammar():
    py = Grammar("python")

    py.add_rule(TokenTypes.COMMENT, r"#.*")

    py.add_rule(
        TokenTypes.CONTROL,
        r"\b(break|continue|elif|else|except|finally|for|if|pass|raise|return|try|while|with|yield)\b",
    )
    py.add_rule(TokenTypes.DECLARATION, r"\b(def|class|lambda|async|await)\b")
    py.add_rule(TokenTypes.CONTEXT, r"\b(self|cls|super|import|from|as|global|nonlocal|del|assert)\b")
    py.add_rule(TokenTypes.LITERAL, r"\b(True|False|None)\b")

    py.add_rule(TokenTypes.STRING, r'"""', r'"""')
    py.add_rule(TokenTypes.STRING, r"'''", r"'''")
    py.add_rule(TokenTypes.STRING, r'"', r'"')
    py.add_rule(TokenTypes.STRING, r"'", r"'")

    py.add_rule(
        TokenTypes.NUMERIC,
        r"\b(?:0[bB][01]+|0[oO][0-7]+|0[xX][\dA-Fa-f]+|\d+(\.\d+)?([eE][+-]?\d+)?|\.\d+([eE][+-]?\d+)?)[jJ]?\b",
    )
    py.add_rule(
        TokenTypes.OPERATOR,
        r"(//=|>>=|<<=|\*\*=|//|\*\*|<<|>>|==|!=|<=|>=|<|>|\+=|-=|\*=|/=|%=|&=|\|=|\^=|@=|->|:=|=|\+|-|\*|/|%|&|\||\^|~|@|\.\.\.|\bnot\b|\band\b|\bor\b|\bin\b|\bis\b)",
    )
    py.add_rule(TokenTypes.VARIABLE, r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")
    py.add_rule(TokenTypes.PUNCTUATION, r"[.,;:()[\]{}]")

    return py


js_grammar = jsGrammar()
py_grammar = pythonGrammar()
none_grammar = Grammar("none")
none_grammar.add_rule(TokenTypes.PUNCTUATION, r".*")

COLOR_SCHEME = {
    TokenTypes.CONTROL: rgb(94, 129, 172),  # Nord Blue (#5E81AC)
    TokenTypes.DECLARATION: rgb(191, 97, 106),  # Nord Red (#BF616A)
    TokenTypes.CONTEXT: rgb(136, 200, 140),  # Nord Light Green
    TokenTypes.LITERAL: rgb(208, 135, 112),  # Nord Orange (#D08770)
    TokenTypes.STRING: rgb(163, 190, 140),  # Nord Green (#A3BE8C)
    TokenTypes.NUMERIC: rgb(180, 142, 173),  # Nord Purple (#B48EAD)
    TokenTypes.OPERATOR: rgb(236, 239, 244),  # Nord Snow 2 (#ECEFF4)
    TokenTypes.COMMENT: rgb(106, 115, 117),  # Nord Blue Gray (#81A1C1)
    TokenTypes.VARIABLE: rgb(143, 188, 187),  # Nord Cyan (#8FBCBB)
    TokenTypes.PUNCTUATION: rgb(236, 239, 244),  # Nord Snow 2 (#ECEFF4)
}


class TUICSV(TUI):
    def __init__(self, name):
        super().__init__(fps=30, mouse_mode=MouseMode.ALL_SGR)
        self.lines: Buffer = [""]
        self.old_lines: Buffer = [""]
        self.tcursor = Cursor()
        self.old_tcursor = Cursor()
        self.scroll = 0
        self.box_height = 0
        self.undo_stack: Histroy = []
        self.redo_stack: Histroy = []
        self.transaction_ref_count = 0

        self.grammar = none_grammar
        self.token: List[GrammarMatch] = []
        path = pathlib.Path(name)
        self.load_path(path)

        self.commands = [
            {"name": "uppercase", "func": lambda: self.apply_on_selection(str.upper)},
            {"name": "lowercase", "func": lambda: self.apply_on_selection(str.lower)},
            {"name": "capitalize", "func": lambda: self.apply_on_selection(str.capitalize)},
            {"name": "swapcase", "func": lambda: self.apply_on_selection(str.swapcase)},
            {"name": "titlecase", "func": lambda: self.apply_on_selection(str.title)},
            {"name": "sort_lines", "func": lambda: self.sort_lines()},
            {"name": "sort_lines_desc", "func": lambda: self.sort_lines(reverse=True)},
            {"name": "eval_py", "func": lambda: self.eval_py()},
            {"name": "exec_py", "func": lambda: self.exec_py()},
        ]
        self.command_pallete_open = False
        self.command_inp = InputWG("command_query")
        self.command_sel_index = -1

        self.find_mode = False
        self.find_inp = InputWG("find_query")
        self.last_found = Anchor()

    def eval_py(self):
        if not self.tcursor.is_selection():
            return

        sx, sy = self.tcursor.sel_start
        ex, ey = self.tcursor.sel_end
        if sy != ey:
            return

        with self.transaction():
            expr = self.lines[self.cy][sx:ex]
            try:
                result = eval(expr)
                self.lines.insert(ey + 1, f"# RESULT: {repr(result)}")
            except Exception as e:
                self.lines.insert(ey + 1, f"# ERROR: {repr(e)}")

    def exec_py(self):
        if not self.tcursor.is_selection():
            return

        text = self.tcursor.get_selection_text(self.lines)
        _, ey = self.tcursor.sel_end
        with self.transaction():
            try:
                buffer = StringIO()
                old_stdout = sys.stdout
                sys.stdout = buffer
                exec(text)
                sys.stdout = old_stdout
                captured_output = buffer.getvalue()

                for i, l in enumerate(captured_output.splitlines()):
                    self.lines.insert(ey + 1 + i, f"# {l}")
            except Exception as e:
                self.lines.insert(ey + 1, f"# ERROR: {repr(e)}")

    def sort_lines(self, reverse=False):
        with self.transaction():
            if self.tcursor.is_selection():
                _, sy = self.tcursor.sel_start
                _, ey = self.tcursor.sel_end

                self.lines[sy : ey + 1] = sorted(self.lines[sy : ey + 1], reverse=reverse)
            else:
                self.lines.sort(reverse=reverse)

    def apply_on_selection(self, fn):
        if not self.tcursor.is_selection():
            return
        self.cursor_regulate()
        sx, sy = self.tcursor.sel_start
        ex, ey = self.tcursor.sel_end
        if sy == ey:
            self.lines[sy] = self.lines[sy][:sx] + fn(self.lines[sy][sx:ex]) + self.lines[sy][ex:]
        else:
            self.lines[sy] = self.lines[sy][:sx] + fn(self.lines[sy][sx:])
            self.lines[ey] = fn(self.lines[ey][:ex]) + self.lines[ey][ex:]
            for y in range(sy + 1, ey):
                self.lines[y] = fn(self.lines[y])

    def load_path(self, path: pathlib.Path):
        if not path.exists():
            self.lerror(f"Path {path} does not exist")
        elif path.is_dir():
            self.linfo(f"Directory {path} loaded")
            self.load_dir(path)
        elif path.is_file():
            self.linfo(f"File {path} loaded")
            self.load_file(path)

    def load_dir(self, path):
        self.dir = path
        self.file = None
        self.token = []

        exclusion = [".git"]  # not sure if we want this
        self.ftree = os.scandir(self.dir)
        self.ftree = [x for x in self.ftree if x.name not in exclusion]
        self.ftree.sort(key=dir_entry_sort)

    def load_file(self, path: pathlib.Path):
        self.dir = None
        self.file = path
        self.tcursor = Cursor()
        self.old_tcursor = Cursor()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.transaction_ref_count = 0
        self.lines = [""]
        self.old_lines = [""]

        extension = self.file.name.split(".")[-1]
        match extension:
            case "py":
                self.grammar = py_grammar
            case "js" | "json":
                self.grammar = js_grammar
            case _:
                self.grammar = none_grammar

        try:
            with open(self.file) as f:
                self.lines = f.read().splitlines()
            self.tokenize()
        except Exception:
            self.lwarn(f"Error when reading file {path}, File might be binary")

    def tokenize(self):
        self.token = self.grammar.parse_text_buffer(self.lines)

    @property
    def filtered_commands(self):
        return [x for x in self.commands if self.command_inp.value in x["name"]]

    def save(self):
        if not self.file:
            return
        with open(self.file, "w") as f:
            f.write("\n".join(self.lines))

    @property
    def nlines(self):
        return len(self.lines)

    @property
    def cx(self):
        return self.tcursor.end.cx

    @property
    def cy(self):
        return self.tcursor.end.cy

    @property
    def cline(self):
        return self.lines[self.tcursor.end.cy]

    def cursor_regulate(self):
        self.tcursor.start.cursor_regulate(self.lines)
        self.tcursor.end.cursor_regulate(self.lines)

    def start_transaction(self):
        if self.transaction_ref_count == 0:
            self.old_lines = self.lines.copy()
            self.old_tcursor = self.tcursor.copy()
        self.transaction_ref_count += 1

    def end_transaction(self):
        self.transaction_ref_count -= 1

        if self.transaction_ref_count > 0:
            return

        if self.lines == self.old_lines:
            return

        self.redo_stack.clear()

        ed = Edit.from_diff(self.old_lines, self.lines)
        ed.start_cursor = self.old_tcursor.copy()
        ed.end_cursor = self.tcursor.copy()
        self.undo_stack.append(ed)
        self.old_lines.clear()

        self.undo_stack = self.undo_stack[-MAX_UNDO_HISTORY_SIZE:]
        self.tokenize()

    def transaction(self):
        @contextmanager
        def with_transaction():
            self.start_transaction()
            yield
            self.end_transaction()

        return with_transaction()

    def undo(self):
        if len(self.undo_stack) == 0:
            return

        ed = self.undo_stack.pop()
        self.redo_stack.append(ed)

        ed.undo(self.lines)
        self.tcursor = ed.start_cursor
        self.tokenize()

    def redo(self):
        if len(self.redo_stack) == 0:
            return

        ed = self.redo_stack.pop()
        self.undo_stack.append(ed)

        ed.redo(self.lines)
        self.tcursor = ed.end_cursor
        self.tokenize()

    def backspace(self):
        self.cursor_regulate()
        if self.tcursor.is_selection():
            self.tcursor.empty_selection(self.lines)
        elif self.cx > 0:
            self.lines[self.cy] = self.lines[self.cy][: self.cx - 1] + self.lines[self.cy][self.cx :]
            self.tcursor.start.cx -= 1
            self.tcursor.end.cx -= 1
        elif self.cy > 0:
            self.tcursor.left(self.lines)
            self.lines[self.cy] += self.lines.pop(self.cy + 1)

    def delete(self):
        self.cursor_regulate()
        if self.tcursor.is_selection():
            self.tcursor.empty_selection(self.lines)
        elif self.cx < len(self.cline):
            self.lines[self.cy] = self.lines[self.cy][: self.cx] + self.lines[self.cy][self.cx + 1 :]
        elif self.cy < self.nlines - 1:
            self.lines[self.cy] += self.lines.pop(self.cy + 1)

    def scroll_to_cursor_end(self):
        if self.cy < self.scroll:
            self.scroll = self.cy
        elif self.cy > self.scroll + self.box_height - 1:
            self.scroll = self.cy - self.box_height + 1

    def render(self):
        ftree_box, box = self.box.left(30)
        self.draw_box(ftree_box)
        self.draw_box(box)
        self.box_height = box.pad(1).h

        # File tree
        with self.error_logging("file_tree"):
            rest = ftree_box.pad(top=1)

            fteb, rest = rest.top(1)
            if button(self, fteb, "  ..", align=TextAlign.LEFT):
                path = pathlib.Path(self.dir or self.file).parent
                self.load_path(path)

            if self.dir:
                for entry in self.ftree:
                    fteb, rest = rest.top(1)
                    label = "❯ " if entry.is_dir() else "  "
                    label += entry.name
                    if button(self, fteb, label, align=TextAlign.LEFT):
                        path = pathlib.Path(self.dir) / pathlib.Path(entry.name)
                        self.load_path(path)

        # editor
        with self.error_logging("editor"):
            line_no_space = len(str(self.nlines))

            cx, cy = self.tcursor.end.pair()
            cx = min(cx, len(self.cline))
            cy = cy - self.scroll
            cx, cy = box.at(cx, cy)
            self.cursor_loc = [cx + line_no_space + 2, cy + 1]

            lineno = self.scroll
            ti = 0
            while ti < len(self.token) and self.token[ti].line < lineno:
                ti += 1
            # TODO very slow implementation, I think
            for i in range(0, min(box.h - 2, self.nlines - self.scroll)):
                result = dim(str(lineno + 1).ljust(line_no_space + 1))
                while ti < len(self.token) and self.token[ti].line == lineno:
                    tok = self.token[ti]
                    style = COLOR_SCHEME.get(tok.matched_class, noop)
                    for x in range(tok.start, tok.end):
                        ch = style(self.lines[tok.line][x])
                        if self.tcursor.is_within_selection(x, lineno):
                            ch = gray_bg(ch)
                        result += ch
                    ti += 1

                self.blit_text_to_box(result, box, 1, 1 + i)
                lineno += 1

        # command pallete
        if self.command_pallete_open:
            with self.error_logging("pallete"):
                with self.withz(100):
                    palleteb = self.box.centered(80, 20)
                    self.clean_box(palleteb)
                    self.draw_box(palleteb)

                    ln = next_line(1)
                    self.add_line("Command Pallete", palleteb, next(ln), align=TextAlign.CENTER, effect=pale_yellow)

                    rest = palleteb.pad(top=2)
                    inputb, rest = rest.top(3)
                    self.mount(self.command_inp, inputb.pad(x=1))

                    for cmd_i, cmd in enumerate(self.filtered_commands):
                        b, rest = rest.top(1)
                        hovering = self.hovering(b)
                        clicking = self.clicking(b)
                        eff = self.command_sel_index == cmd_i and gray_bg
                        self.add_line(cmd["name"], b, 0, effect=eff)
                        if clicking:
                            with self.transaction():
                                cmd["func"]()
                            self.command_pallete_open = False
                        elif self.mouse.updated and hovering:
                            self.command_sel_index = cmd_i

        # find
        if self.find_mode:
            with self.error_logging("find"):
                with self.withz(100):
                    fb = self.box.bottom_right(50, 3)
                    self.mount(self.find_inp, fb)

        # diag
        if self.display_diagnostics:
            with self.error_logging("diag"):
                diag = box.bottom_right(30, 10)
                ln = next_line(1)
                self.draw_box(diag)
                self.add_line(f"is sel - {self.tcursor.is_selection()}", diag, next(ln))
                self.add_line(f"start - {self.tcursor.start}", diag, next(ln))
                self.add_line(f"end - {self.tcursor.end}", diag, next(ln))
                self.add_line(f"Undo len - {len(self.undo_stack)}", diag, next(ln))
                self.add_line(f"Redo len - {len(self.redo_stack)}", diag, next(ln))
                self.add_line(f"Grammar - {self.grammar.name}", diag, next(ln))

    def on_input(self, ch):
        if ch == CTRL + "q":
            self.shutdown()
            return

        if ch == CTRL + "l":
            self.command_pallete_open = not self.command_pallete_open
            if self.command_pallete_open:
                self.command_inp.focused = True
                self.command_inp.value = ""
                self.command_inp.curs = 0
                self.command_sel_index = -1
        if self.command_pallete_open:
            if ch == ESC:
                self.command_pallete_open = False
            elif ch == Keys.UP:
                self.command_sel_index -= 1
                if self.command_sel_index < 0:
                    self.command_sel_index = len(self.filtered_commands) - 1
            elif ch == Keys.DOWN:
                self.command_sel_index += 1
                if self.command_sel_index >= len(self.filtered_commands):
                    self.command_sel_index = 0
            elif ch == Keys.ENTER:
                with self.transaction():
                    self.filtered_commands[self.command_sel_index]["func"]()
                self.command_pallete_open = False
            elif ch.isprintable():
                self.command_sel_index = -1

            return

        if ch == CTRL + "f":
            self.find_mode = not self.find_mode
            if self.find_mode:
                self.find_inp.focused = True
                if self.tcursor.is_selection() and self.tcursor.start.cy == self.tcursor.end.cy:
                    sx = min(self.tcursor.start.cx, self.tcursor.end.cx)
                    ex = max(self.tcursor.start.cx, self.tcursor.end.cx)
                    self.find_inp.value = self.lines[self.cy][sx:ex]
                    self.find_inp.curs = ex - sx
        if self.find_mode:
            if ch == ESC:
                self.find_mode = False
            if ch == Keys.ENTER:
                i = self.last_found.cy
                for _ in range(self.nlines):
                    fidx = self.lines[i].find(self.find_inp.value, self.last_found.cx)
                    self.last_found.cx = 0
                    if fidx >= 0:
                        self.tcursor.start.cy = i
                        self.tcursor.end.cy = i
                        self.tcursor.start.cx = fidx
                        self.tcursor.end.cx = fidx + len(self.find_inp.value)

                        self.last_found.cx = self.tcursor.end.cx
                        self.last_found.cy = self.tcursor.end.cy
                        break
                    i = (i + 1) % self.nlines
            if ch == SHIFT + Keys.ENTER:
                i = self.last_found.cy
                for _ in range(self.nlines):
                    fidx = self.lines[i].find(self.find_inp.value, self.last_found.cx)
                    self.last_found.cx = 0
                    if fidx >= 0:
                        self.tcursor.start.cy = i
                        self.tcursor.end.cy = i
                        self.tcursor.start.cx = fidx
                        self.tcursor.end.cx = fidx + len(self.find_inp.value)

                        self.last_found.cx = self.tcursor.end.cx
                        self.last_found.cy = self.tcursor.end.cy
                        break
                    i = (i - 1) % self.nlines
            self.scroll_to_cursor_end()
            return

        if ch == CTRL + "s":
            self.save()
            return
        if ch == CTRL + "r":
            if self.file:
                self.load_file(self.file)
            if self.dir:
                self.load_dir(self.dir)
            return

        with self.error_logging("nav"):
            # arrow navigation
            if ch == Keys.UP:
                self.tcursor.up(self.lines)
            elif ch == Keys.DOWN:
                self.tcursor.down(self.lines)
            elif ch == Keys.LEFT:
                self.tcursor.left(self.lines)
            elif ch == Keys.RIGHT:
                self.tcursor.right(self.lines)
            elif ch == Keys.HOME:
                if self.tcursor.is_selection():
                    self.tcursor.collapse_to_selstart()
                self.tcursor.start.cx = 0
                self.tcursor.end.cx = 0
            elif ch == Keys.END:
                if self.tcursor.is_selection():
                    self.tcursor.collapse_to_selend()
                self.tcursor.start.cx = len(self.lines[self.cy])
                self.tcursor.end.cx = len(self.lines[self.cy])
            elif ch == CTRL + Keys.LEFT:
                self.cursor_regulate()
                self.tcursor.left(self.lines)
                if not self.tcursor.is_selection():
                    # TODO this logic is lacking
                    while self.cx > 0 and self.lines[self.cy][self.cx - 1].isalpha():
                        self.tcursor.left(self.lines)
            elif ch == CTRL + Keys.RIGHT:
                self.cursor_regulate()
                self.tcursor.right(self.lines)
                if not self.tcursor.is_selection():
                    while self.cx <= len(self.cline) and self.lines[self.cy][self.cx].isalpha():
                        self.tcursor.right(self.lines)
            elif ch == CTRL + SHIFT + Keys.LEFT:
                self.cursor_regulate()
                self.tcursor.end.left(self.lines)
                while self.cx > 0 and self.lines[self.cy][self.cx - 1].isalpha():
                    self.tcursor.end.left(self.lines)
            elif ch == CTRL + SHIFT + Keys.RIGHT:
                self.cursor_regulate()
                self.tcursor.end.right(self.lines)
                while self.cx <= len(self.cline) and self.lines[self.cy][self.cx].isalpha():
                    self.tcursor.end.right(self.lines)
            elif ch == SHIFT + Keys.END:
                self.cursor_regulate()
                self.tcursor.end.cx = len(self.lines[self.cy])
            elif ch == SHIFT + Keys.HOME:
                self.cursor_regulate()
                self.tcursor.end.cx = 0

            # selection changing
            elif ch == SHIFT + Keys.UP:
                self.tcursor.end.up(self.lines)
            elif ch == SHIFT + Keys.DOWN:
                self.tcursor.end.down(self.lines)
            elif ch == SHIFT + Keys.LEFT:
                self.tcursor.end.left(self.lines)
            elif ch == SHIFT + Keys.RIGHT:
                self.tcursor.end.right(self.lines)

        with self.transaction():
            with self.error_logging("editing"):
                # editing
                if ch == ALT + Keys.UP and not self.tcursor.is_selection() and self.tcursor.end.cy > 0:
                    x = self.tcursor.end.cy
                    self.lines[x], self.lines[x - 1] = self.lines[x - 1], self.lines[x]
                    self.tcursor.up(self.lines)
                elif ch == ALT + Keys.DOWN and not self.tcursor.is_selection() and self.tcursor.end.cy < self.nlines - 1:
                    x = self.tcursor.end.cy + 1
                    self.lines[x], self.lines[x - 1] = self.lines[x - 1], self.lines[x]
                    self.tcursor.down(self.lines)

                elif ch.isprintable():
                    self.cursor_regulate()
                    if self.tcursor.is_selection():
                        self.tcursor.empty_selection(self.lines)
                    self.lines[self.cy] = self.lines[self.cy][: self.cx] + ch.key + self.lines[self.cy][self.cx :]
                    self.tcursor.right(self.lines)
                elif ch == Keys.BACKSPACE:
                    self.backspace()
                elif ch == CTRL + Keys.BACKSPACE:
                    self.cursor_regulate()
                    self.backspace()
                    if not self.tcursor.is_selection():
                        while self.cx > 0 and self.lines[self.cy][self.cx - 1].isalpha():
                            self.backspace()
                elif ch == Keys.DEL:
                    self.delete()
                elif ch == CTRL + Keys.DEL:
                    self.cursor_regulate()
                    self.delete()
                    if not self.tcursor.is_selection():
                        while self.cx <= len(self.cline) and self.lines[self.cy][self.cx].isalpha():
                            self.delete()
                elif ch == Keys.ENTER:
                    self.cursor_regulate()
                    if self.tcursor.is_selection():
                        self.tcursor.empty_selection(self.lines)
                    pre = self.lines[self.cy][: self.cx]
                    post = self.lines[self.cy][self.cx :]
                    self.lines[self.cy] = pre
                    self.lines.insert(self.cy + 1, post)
                    self.tcursor.down(self.lines)
                elif ch == CTRL + "c":
                    if self.tcursor.is_selection():
                        text = self.tcursor.get_selection_text(self.lines)
                    else:
                        text = self.lines[self.cy]
                    text = text.encode()
                    encoded = base64.b64encode(text).decode()
                    sys.stdout.write(f"\x1b]52;c;{encoded}\007")
                    sys.stdout.flush()
                elif ch == CTRL + "x":
                    if self.tcursor.is_selection():
                        text = self.tcursor.get_selection_text(self.lines)
                        self.tcursor.empty_selection(self.lines)
                    else:
                        text = self.lines[self.cy]
                        if len(self.lines) > 0:
                            self.lines.pop(self.cy)
                        else:
                            self.lines = [""]

                        if self.cy >= self.nlines:
                            self.tcursor.up(self.lines)
                    text = text.encode()
                    encoded = base64.b64encode(text).decode()
                    sys.stdout.write(f"\x1b]52;c;{encoded}\007")
                    sys.stdout.flush()
                elif ch == ALT + SHIFT + Keys.UP and not self.tcursor.is_selection():
                    self.lines.insert(self.cy, self.lines[self.cy])
                elif ch == ALT + SHIFT + Keys.DOWN and not self.tcursor.is_selection():
                    self.lines.insert(self.cy, self.lines[self.cy])
                    self.tcursor.down(self.lines)
                elif ch == CTRL + "a":
                    self.tcursor.start.cy = 0
                    self.tcursor.start.cx = 0
                    self.tcursor.end.cy = len(self.lines) - 1
                    self.tcursor.end.cx = len(self.lines[-1])

        if ch == CTRL + "g":
            self.undo()
        if ch == CTRL + "y":
            self.redo()

        self.scroll_to_cursor_end()


app = TUICSV(".")
if __name__ == "__main__":
    name = "."
    if len(sys.argv) == 2:
        name = sys.argv[1]

    app = TUICSV(name)
    app.mainLoop()
