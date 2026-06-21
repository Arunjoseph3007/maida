from maida import *
from dataclasses import dataclass
from typing import List
from contextlib import contextmanager
import base64
import pathlib
import os
import sys

# TODO ctrl backspace, del
# TODO syntax highlighting

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

        path = pathlib.Path(name)
        self.load_path(path)

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

        exclusion = [".git"]  # not sure if we want this
        self.ftree = os.scandir(self.dir)
        self.ftree = [x for x in self.ftree if x.name not in exclusion]
        self.ftree.sort(key=dir_entry_sort)

    def load_file(self, path):
        self.dir = None
        self.file = path
        self.tcursor = Cursor()
        self.old_tcursor = Cursor()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.transaction_ref_count = 0
        self.lines = [""]
        self.old_lines = [""]

        try:
            with open(self.file) as f:
                self.lines = f.read().splitlines()
        except Exception:
            self.lwarn(f"Error when reading file {path}, File might be binary")

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
        return self.lines[self.tcursor.start.cy]

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

    def redo(self):
        if len(self.redo_stack) == 0:
            return

        ed = self.redo_stack.pop()
        self.undo_stack.append(ed)

        ed.redo(self.lines)
        self.tcursor = ed.end_cursor

    def render(self):
        ftree_box, box = self.box.left(30)
        self.draw_box(ftree_box)
        self.draw_box(box)
        self.box_height = box.pad(1).h

        # File tree
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
        line_no_space = len(str(self.nlines))

        cx, cy = self.tcursor.end.pair()
        cx = min(cx, len(self.cline))
        cy = cy - self.scroll
        cx, cy = box.at(cx, cy)
        self.cursor_loc = [cx + line_no_space + 2, cy + 1]

        lineno = self.scroll
        for i, line in enumerate(self.lines[self.scroll :]):
            lnt = dim(str(lineno + 1).ljust(line_no_space))
            ltext = f"{lnt} {line}"
            sel_eff = lambda x: gray_bg(dim(x))
            if self.tcursor.is_selection():
                sx, sy = self.tcursor.sel_start
                ex, ey = self.tcursor.sel_end
                if sy == ey == lineno:
                    ltext = f"{lnt} {line[:sx]}{sel_eff(line[sx:ex])}{line[ex:]}"
                elif lineno == sy:
                    ltext = f"{lnt} {line[:sx]}{sel_eff(line[sx:])}"
                elif lineno == ey:
                    ltext = f"{lnt} {sel_eff(line[:ex])}{line[ex:]}"
                elif ey > lineno > sy:
                    ltext = f"{lnt} {sel_eff(line)}"

            self.blit_text_to_box(ltext, box, 1, 1 + i)
            lineno += 1

        if self.display_diagnostics:
            diag = box.bottom_right(30, 10)
            ln = next_line(1)
            self.draw_box(diag)
            self.add_line(f"is sel - {self.tcursor.is_selection()}", diag, next(ln))
            self.add_line(f"start - {self.tcursor.start}", diag, next(ln))
            self.add_line(f"end - {self.tcursor.end}", diag, next(ln))
            self.add_line(f"Undo len - {len(self.undo_stack)}", diag, next(ln))
            self.add_line(f"Redo len - {len(self.redo_stack)}", diag, next(ln))

    def on_input(self, ch):
        if ch == CTRL + "q":
            self.shutdown()
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
                elif ch == Keys.DEL:
                    self.cursor_regulate()
                    if self.tcursor.is_selection():
                        self.tcursor.empty_selection(self.lines)
                    elif self.cx < len(self.cline):
                        self.lines[self.cy] = self.lines[self.cy][: self.cx] + self.lines[self.cy][self.cx + 1 :]
                    elif self.cy < self.nlines - 1:
                        self.lines[self.cy] += self.lines.pop(self.cy + 1)
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

        # check if cursor is on screen
        if self.cy < self.scroll:
            self.scroll = self.cy
        elif self.cy > self.scroll + self.box_height - 1:
            self.scroll = self.cy - self.box_height + 1


if __name__ == "__main__":
    name = "."
    if len(sys.argv) == 2:
        name = sys.argv[1]

    app = TUICSV(name)
    app.mainLoop()
