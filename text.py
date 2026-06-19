from maida import *
import base64
import pathlib
import os
import sys

# TODO ctrl backspace, del
# TODO undo redo


def dir_entry_sort(k: os.DirEntry[str]):
    if k.is_dir():
        return "0" + k.name
    else:
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


class TUICSV(TUI):
    def __init__(self, name):
        super().__init__(fps=30, mouse_mode=MouseMode.ALL_SGR)
        self.lines = [""]
        self.tcursor = Cursor()
        self.scroll = 0
        self.box_height = 0

        path = pathlib.Path(name)
        self.load_path(path)

    def load_path(self, path: pathlib.Path):
        if not path.exists():
            self.lerror(f"Path {path} does not exist")
        if path.is_dir():
            self.linfo(f"Directory {path} loaded")
            self.dir = path
            self.file = None
            self.load_dir()
        elif path.is_file():
            self.linfo(f"File {path} loaded")
            self.dir = None
            self.file = path
            self.load_file()

    def load_dir(self):
        if not self.dir:
            return

        self.ftree = list(os.scandir(self.dir))
        self.ftree.sort(key=dir_entry_sort)

    def load_file(self):
        self.tcursor = Cursor()
        if not self.file:
            return
        with open(self.file) as f:
            self.lines = f.read().splitlines()

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
                label = "> " if entry.is_dir() else "  "
                label += entry.name
                if button(self, fteb, label, align=TextAlign.LEFT):
                    path = pathlib.Path(self.dir) / pathlib.Path(entry.name)
                    self.load_path(path)

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
            self.draw_box(diag)
            self.add_line(f"is sel - {self.tcursor.is_selection()}", diag, 1)
            self.add_line(f"start - {self.tcursor.start}", diag, 2)
            self.add_line(f"end - {self.tcursor.end}", diag, 3)

    def on_input(self, ch):
        if ch == CTRL + "q":
            self.shutdown()
            return
        if ch == CTRL + "s":
            self.save()
            return
        if ch == CTRL + "r":
            self.load_file()
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
                    # TODO this logic is lacking
                    while self.cx <= len(self.cline) and self.lines[self.cy][self.cx].isalpha():
                        self.tcursor.right(self.lines)

            # selection changing
            elif ch == SHIFT + Keys.UP:
                self.tcursor.end.up(self.lines)
            elif ch == SHIFT + Keys.DOWN:
                self.tcursor.end.down(self.lines)
            elif ch == SHIFT + Keys.LEFT:
                self.tcursor.end.left(self.lines)
            elif ch == SHIFT + Keys.RIGHT:
                self.tcursor.end.right(self.lines)

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
                    self.tcursor.left(self.lines)
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

        # check if cursor is on screen
        if self.cy < self.scroll:
            self.scroll = self.cy
        elif self.cy > self.scroll + self.box_height - 1:
            self.scroll = self.cy - self.box_height + 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Expected one argument")
        exit(1)

    app = TUICSV(sys.argv[1])
    app.mainLoop()
