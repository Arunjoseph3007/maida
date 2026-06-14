from maida import *
import csv
import sys
import enum


class SortState(enum.Enum):
    NONE = enum.auto()
    ASCE = enum.auto()
    DESC = enum.auto()


class TUICSV(TUI):
    def __init__(self, filename):
        super().__init__(fps=30, mouse_mode=MouseMode.ALL_SGR)
        self.file = filename
        self.process_file()

        self.help_open = False
        self.ctrl_open = False
        self.sort_feild: str | None = 'sid'
        self.sort_state = SortState.ASCE

        self.short_cuts = [
            {"key": CTRL + "q", "func": self.shutdown, "desc": "Exit app"},
            {"key": CTRL + "r", "func": self.process_file, "desc": "Reload file data"},
            {"key": CTRL + "h", "func": self.toggle_help, "desc": "Toggle this help menu"},
            {"key": CTRL + "c", "func": self.toggle_ctrl, "desc": "Toggle Control Panel"},
        ]

        self.find_mode = False
        self.query = ""
        self.query_curs = 0
        self.query_res_lines: List[int] = []
        self.query_res_feild: List[str] = []
        self.active_query_res = 0

    def compute_query(self):
        self.query_res_lines = []
        self.query_res_feild = []
        if not self.query:
            return

        self.active_query_res = 0
        for i, r in enumerate(self.rows):
            for f in self.fieldnames:
                if self.feilds_selected[f]:
                    if self.query in r[f]:
                        self.query_res_lines.append(i)
                        self.query_res_feild.append(f)

    def toggle_ctrl(self):
        self.ctrl_open = not self.ctrl_open

    def toggle_help(self):
        self.help_open = not self.help_open

    def process_file(self):
        with open(self.file) as f:
            self.reader = csv.DictReader(f)
            self.dialect = self.reader.dialect
            self.fieldnames = self.reader.fieldnames
            self.line_num = self.reader.line_num
            self.scroll = 0

            self.rows = list(self.reader)

            self.feildlens = {x: len(x) for x in self.fieldnames}
            for row in self.rows:
                for f in self.fieldnames:
                    self.feildlens[f] = max(self.feildlens[f], len(row[f]))

            self.feildlens = {k: clamp(v, 4, 50) for k, v in self.feildlens.items()}
            self.feilds_selected = {k: True for k in self.fieldnames}

    def format_header(self):
        result = dim("#   ")

        for f in self.fieldnames:
            if self.feilds_selected[f]:
                h = cyan(f[: self.feildlens[f]].ljust(self.feildlens[f])) + "  "

                if self.sort_feild == f:
                    match self.sort_state:
                        case SortState.ASCE:
                            h = h[:-2] + "🔺"
                        case SortState.DESC:
                            h = h[:-2] + "🔻"

                result += h
        return result

    def format_row(self, row, i, effect=noop):
        has_result = i in self.query_res_lines

        result = f"{dim(str(i).ljust(3))} "
        if has_result:
            result = red(result)

        selection_line = -1
        selection_feild = None
        if len(self.query_res_feild):
            selection_line = self.query_res_lines[self.active_query_res]
            selection_feild = self.query_res_feild[self.active_query_res]

        for f in self.fieldnames:
            if self.feilds_selected[f]:
                if has_result and i == selection_line and f == selection_feild:
                    result += gray_bg(red(row[f][: self.feildlens[f]].ljust(self.feildlens[f])))
                elif has_result and self.query in row[f]:
                    result += red(row[f][: self.feildlens[f]].ljust(self.feildlens[f]))
                else:
                    result += effect(row[f][: self.feildlens[f]].ljust(self.feildlens[f]))

                result += "  "

        return result

    def render(self):
        header, b = self.box.top(2)
        b, search = b.bottom(2)

        self.add_line(f"File - {self.file} :: {self.line_num} Rows, Dialect - {self.dialect}", header, 1)

        hrow = {x: x for x in self.fieldnames}
        self.blit_text_to_box(dim("─" * 1000), b, 1, 0)
        self.blit_text_to_box(self.format_header(), b, 1, 1)
        self.blit_text_to_box(dim("─" * 1000), b, 1, 2)

        total_res = "\n".join([self.format_row(r, i) for i, r in enumerate(self.rows)])
        self.blit_text_to_box(total_res, b, 1, 3, scrolly=self.scroll)

        if self.find_mode:
            self.add_line(f"/{self.query}", search, 0)
            self.cursor_loc = search.at(self.query_curs + 2, 0)
        else:
            self.cursor_loc = search.at(0, 0)
        # help panel
        if self.help_open:
            with self.withz(100):
                b = self.box.centered(80, 20)
                self.clean_box(b)
                self.draw_box(b)

                _, rest = b.top(1)
                for shortcut in self.short_cuts:
                    key = shortcut["key"]
                    if key == ESC:
                        key = "ESC"
                    key = f"<{key}>"
                    key = key.ljust(6)
                    key = pale_yellow(key)

                    kb, rest = rest.top(1)
                    effect = None
                    if self.hovering(kb):
                        effect = gray_bg
                    if self.clicking(kb):
                        shortcut["func"]()

                    self.add_line(f"{key} {shortcut['desc']}", kb, 0, effect=effect)

        # control panel
        if self.ctrl_open:
            with self.withz(10):
                b = self.box.rightP(40)[1]

                self.clean_box(b)
                self.draw_box(b, effect=pale_yellow)

                self.add_line("Feilds selection", b, 1, effect=pale_yellow)

                rest = b.pad(top=2)
                feilds = [x for x in self.fieldnames]
                for i, f in enumerate(feilds):
                    tb, rest = rest.top(1)
                    left, right = tb.left(20)
                    self.feilds_selected[f] = toggle(self, left, f, self.feilds_selected[f])

                    upb, right = right.left(4)
                    if button(self, upb, "⬆", disabled=i <= 0):
                        self.fieldnames[i - 1], self.fieldnames[i] = self.fieldnames[i], self.fieldnames[i - 1]

                    downb, right = right.left(4)
                    if button(self, downb, "⬇", disabled=i >= len(feilds) - 1):
                        self.fieldnames[i + 1], self.fieldnames[i] = self.fieldnames[i], self.fieldnames[i + 1]

                    sortb, right = right.left(8)
                    if button(self, sortb, "Sort"):
                        if not self.sort_feild or self.sort_feild != f:
                            self.sort_feild = f
                            self.sort_state = SortState.ASCE
                            self.rows.sort(key=lambda x: x[f])
                        # sort_feild is defined and equla to f
                        elif self.sort_state == SortState.ASCE:
                            self.sort_state = SortState.DESC
                            self.rows.sort(key=lambda x: x[f], reverse=True)
                        elif self.sort_state == SortState.DESC:
                            self.sort_state = SortState.NONE
                        elif self.sort_state == SortState.NONE:
                            self.sort_state = SortState.ASCE
                            self.rows.sort(key=lambda x: x[f])

                self.add_line(f"Dialect - {self.dialect}", rest, 1, effect=pale_yellow)

    def on_input(self, ch):
        if self.find_mode:
            if ch == Keys.UP and self.active_query_res > 0:
                self.active_query_res -= 1
                self.scroll = self.query_res_lines[self.active_query_res]
            if ch == Keys.DOWN and self.active_query_res < len(self.query_res_lines) - 1:
                self.active_query_res += 1
                self.scroll = self.query_res_lines[self.active_query_res]

            if ch == ESC:
                self.query = ""
                self.compute_query()
                self.find_mode = False
            if not self.query and ch == Keys.BACKSPACE:
                self.find_mode = False

            else:
                self.query, self.query_curs, changed = write(self.query, self.query_curs, ch)
                if changed:
                    self.compute_query()
            return

        for sc in self.short_cuts:
            if sc["key"] == ch:
                sc["func"]()
                break

        if ch == "/":
            self.find_mode = True

        if ch == Keys.DOWN:
            if self.scroll < len(self.rows):
                self.scroll += 1
        if ch == Keys.UP:
            if self.scroll > 0:
                self.scroll -= 1


TUICSV("ignore/text.csv").mainLoop()

app = TUICSV("ignore/text.csv")
