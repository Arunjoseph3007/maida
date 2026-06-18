from maida import *

# TODO probably should convert cursor to its own class


class TUICSV(TUI):
    def __init__(self, filename):
        super().__init__(fps=30, mouse_mode=MouseMode.ALL_SGR)
        self.file = filename
        self.tcursor = [0, 0]
        self.load()
        self.scroll = 0
        self.box_height = 0

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

    @cx.setter
    def cx(self, value: int):
        self.tcursor[0] = value

    @property
    def cy(self):
        return self.tcursor[1]

    @cy.setter
    def cy(self, value: int):
        self.tcursor[1] = value

    @property
    def cline(self):
        return self.lines[self.tcursor[1]]

    def cursor_regulate(self):
        if self.cx > len(self.cline):
            self.tcursor[0] = len(self.cline)

    def render(self):
        sidebar, box = self.box.left(30)
        self.draw_box(sidebar)
        self.draw_box(box)
        self.box_height = box.pad(1).h

        line_no_space = len(str(self.nlines))
        cx, cy = self.tcursor
        cx = min(cx, len(self.cline))
        cy = cy - self.scroll
        cx, cy = box.at(cx, cy)
        self.cursor_loc = [cx + line_no_space + 2, cy + 1]

        lineno = self.scroll
        for i, line in enumerate(self.lines[self.scroll :]):
            ltext = f"{dim(str(lineno + 1).ljust(line_no_space))} {line}"
            self.blit_text_to_box(ltext, box, 1, 1 + i)
            lineno += 1

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

        if ch == Keys.UP and self.cy > 0:
            self.cursor_regulate()
            self.cy -= 1

        elif ch == Keys.DOWN and self.cy < self.nlines - 1:
            self.cursor_regulate()
            self.cy += 1
        elif ch == Keys.LEFT:
            self.cursor_regulate()
            if self.cx > 0:
                self.cx -= 1
            elif self.cy > 0:
                self.cy -= 1
                self.cx = len(self.cline)
        elif ch == Keys.RIGHT:
            self.cursor_regulate()
            if self.cx < len(self.cline):
                self.cx += 1
            elif self.cy < self.nlines:
                self.cy += 1
                self.cx = 0

        elif ch.isprintable():
            self.cursor_regulate()
            self.lines[self.cy] = self.lines[self.cy][: self.cx] + ch.key + self.lines[self.cy][self.cx :]
            self.cx += 1
        elif ch == Keys.BACKSPACE:
            self.cursor_regulate()
            if self.cx > 0:
                self.lines[self.cy] = self.lines[self.cy][: self.cx - 1] + self.lines[self.cy][self.cx :]
                self.cx -= 1
            elif self.cy > 0:
                self.cx = len(self.lines[self.cy - 1])
                self.cy -= 1
                self.lines[self.cy] += self.lines.pop(self.cy + 1)
        elif ch == Keys.DEL:
            self.cursor_regulate()
            if self.cx < len(self.cline):
                self.lines[self.cy] = self.lines[self.cy][: self.cx] + self.lines[self.cy][self.cx + 1 :]
            elif self.cy < self.nlines - 1:
                self.lines[self.cy] += self.lines.pop(self.cy + 1)
        elif ch == Keys.ENTER:
            self.cursor_regulate()
            pre = self.lines[self.cy][: self.cx]
            post = self.lines[self.cy][self.cx :]
            self.lines[self.cy] = pre
            self.lines.insert(self.cy + 1, post)
            self.cy += 1
            self.cx = 0

        # check if cursor is on screen
        if self.cy < self.scroll:
            self.scroll = self.cy
        elif self.cy > self.scroll + self.box_height - 1:
            self.scroll = self.cy - self.box_height + 1


if __name__ == "__main__":
    # app = TUICSV("ignore/t.json")
    app = TUICSV("ignore/text.csv")
    app.mainLoop()
