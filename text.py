from maida import *


class TUICSV(TUI):
    def __init__(self, filename):
        super().__init__(fps=30, mouse_mode=MouseMode.ALL_SGR)
        self.file = filename
        self.tcursor = [0, 0]
        self.load()

    def load(self):
        with open(self.file) as f:
            self.lines = f.read().splitlines()


    def save(self):
        with open(self.file, "w") as f:
            f.write("\n".join(self.lines))

    @property
    def nlines(self):
        return len(self.lines)

    @property
    def cx(self):
        return self.tcursor[0]

    @property
    def cy(self):
        return self.tcursor[1]

    @property
    def cline(self):
        return self.lines[self.tcursor[1]]

    def render(self):
        box = self.box
        self.draw_box(box)
        cx, cy = box.at(*self.tcursor)

        line_no_space = len(str(self.nlines))
        self.cursor_loc = [cx + line_no_space + 2, cy + 1]

        for i, line in enumerate(self.lines):
            ltext = f"{dim(str(i).ljust(line_no_space))} {line}"
            self.blit_text_to_box(ltext, box, 1, 1 + i)

    def on_input(self, ch):
        if ch == CTRL + "q":
            self.shutdown()
            return
        if ch == CTRL + "s":
            self.save()
            return
        if ch == CTRL + "r":
            self.load()
            return

        if ch == Keys.UP and self.tcursor[1] > 0:
            self.tcursor[1] -= 1
        elif ch == Keys.DOWN and self.tcursor[1] < self.nlines - 1:
            self.tcursor[1] += 1
        elif ch == Keys.LEFT and self.tcursor[0] > 0:
            self.tcursor[0] -= 1
        elif ch == Keys.RIGHT and self.tcursor[0] < len(self.cline):
            self.tcursor[0] += 1

        elif type(ch.key) == str and ch.key.isprintable():
            self.lines[self.cy] = self.lines[self.cy][: self.cx] + ch.key + self.lines[self.cy][self.cx :]
            self.tcursor[0] += 1
        elif ch == Keys.BACKSPACE:
            if self.cx > 0:
                self.lines[self.cy] = self.lines[self.cy][: self.cx - 1] + self.lines[self.cy][self.cx :]
                self.tcursor[0] -= 1
            elif self.cy > 0:
                last_line_len = len(self.lines[self.cy - 1])
                self.lines = (
                    self.lines[: self.cy - 1] + [self.lines[self.cy - 1] + self.lines[self.cy]] + self.lines[self.cy + 1 :]
                )
                self.tcursor[0] = last_line_len
                self.tcursor[1] -= 1
        elif ch == Keys.ENTER:
            pre = self.lines[self.cy][: self.cx]
            post = self.lines[self.cy][self.cx :]
            self.ldebug(f"l: ")
            self.lines = self.lines[: self.cy] + [pre, post] + self.lines[self.cy + 1 :]
            self.tcursor[1] += 1
            self.tcursor[0] = 0


app = TUICSV("ignore/t.json")
if __name__ == "__main__":
    app.mainLoop()
