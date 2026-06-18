#!/usr/bin/python3

import abc
import unicodedata
import enum
import math
import os
import re
import select
import shutil
import signal
import sys
import termios
import traceback
import tty
import importlib
import datetime
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Tuple, List

# TODO better input editing (ctrl-back, del)


def clamp(n: int, minn: int, maxn: int):
    if n < minn:
        return minn
    if n > maxn:
        return maxn
    return n


def ansi(effect: str):
    def wrapper(t: str) -> str:
        return effect + t + ANSI.RESET

    return wrapper


def is_widechar(l: str) -> bool:
    return unicodedata.east_asian_width(l) in ("W", "F")


def next_line(c=0, step=1):
    while True:
        yield c
        c += step


def rgb(r: int, g: int, b: int):
    return ansi(f"\x1b[38;2;{r};{g};{b}m")


def rgb_bg(r: int, g: int, b: int):
    return ansi(f"\x1b[48;2;{r};{g};{b}m")


def noop(arg):
    return arg


ESC = "\x1b"
CSI = "\x1b["

dim = ansi(f"{CSI}2m")
dim_bg = ansi(f"{CSI}48;100;100;100;Bm")
blink = ansi(f"{CSI}5m")
bold = ansi(f"{CSI}1m")
red = ansi(f"{CSI}31m")
green = ansi(f"{CSI}32m")
black = ansi(f"{CSI}38;5;0m")
pale_yellow = ansi(f"{CSI}38;5;106m")
gray_bg = ansi(f"{CSI}37;48;5;236m")
pale_yellow_bg = rgb(156, 196, 102)
orange = rgb(207, 178, 101)
cyan = rgb(0, 255, 255)


class Box:
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def within(self, x: int, y: int):
        return x >= self.x and x < self.x + self.w and y >= self.y and y < self.y + self.h

    def clamp(self, x: int, y: int):
        return clamp(x, self.x, self.x + self.w - 1), clamp(y, self.y, self.y + self.h - 1)

    def left(self, lf: int):
        nw = lf
        l = Box(self.x, self.y, nw, self.h)
        r = Box(self.x + nw, self.y, self.w - nw, self.h)
        return l, r

    def top(self, to: int):
        nh = to
        t = Box(self.x, self.y, self.w, nh)
        b = Box(self.x, self.y + nh, self.w, self.h - nh)
        return t, b

    def right(self, r: int):
        return self.left(self.w - r)

    def bottom(self, b: int):
        return self.top(self.h - b)

    def leftP(self, pc: int):
        return self.left(round(self.w * pc / 100))

    def rightP(self, pc: int):
        return self.right(round(self.w * pc / 100))

    def topP(self, pc: int):
        return self.top(round(self.h * pc / 100))

    def bottomP(self, pc: int):
        return self.bottom(round(self.h * pc / 100))

    def splith(self):
        return self.left(self.w // 2)

    def splitv(self):
        return self.top(self.h // 2)

    def pad(
        self,
        p: int = 0,
        *,
        x: int = None,
        y: int = None,
        top: int = None,
        bottpm: int = None,
        left: int = None,
        right: int = None,
    ):
        pt = p
        pb = p
        pl = p
        pr = p

        if x is not None:
            pl = x
            pr = x
        if y is not None:
            pt = y
            pb = y

        if top is not None:
            pt = top
        if bottpm is not None:
            pb = bottpm
        if left is not None:
            pl = left
        if right is not None:
            pr = right
        return Box(self.x + pl, self.y + pt, self.w - pl - pr, self.h - pb - pt)

    def at(self, x: int, y: int):
        return self.x + x, self.y + y

    def top_left(self, w: int, h: int, pad: int = 1):
        return Box(*self.at(pad, pad), w, h)

    def top_right(self, w: int, h: int, pad: int = 1):
        return Box(*self.at(self.w - w - pad, pad), w, h)

    def bottom_left(self, w: int, h: int, pad: int = 1):
        return Box(*self.at(pad, self.h - h - pad), w, h)

    def bottom_right(self, w: int, h: int, pad: int = 1):
        return Box(*self.at(self.w - w - pad, self.h - h - pad), w, h)

    def rows(self, r: int):
        rh = self.h // r
        boxes = []

        rest = self
        for i in range(r - 1):
            a, rest = rest.top(rh)
            boxes.append(a)
        boxes.append(rest)
        return boxes

    def cols(self, c: int):
        cw = self.w // c
        boxes = []

        rest = self
        for i in range(c - 1):
            a, rest = rest.left(cw)
            boxes.append(a)
        boxes.append(rest)
        return boxes

    def sub_box(self, x: int, y: int, w: int, h: int):
        return Box(*self.at(x, y), w, h)

    def centered(self, w: int, h: int):
        return Box(self.x + (self.w - w) // 2, self.y + (self.h - h) // 2, w, h)

    def copy(self):
        return Box(self.x, self.y, self.w, self.h)

    def __str__(self):
        return f"Box(x={self.x}, y={self.y}, w={self.w}, h={self.h})"


class TextAlign(enum.Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"


class MouseMode(enum.Enum):
    NONE = "NONE"
    CLICKS = "CLICKS"
    ALL = "ALL"
    CLICKS_SGR = "CLICKS_SGR"
    ALL_SGR = "ALL_SGR"
    SGR_PIXEL = "SGR_PIXEL"  # TODO, WIP

    def tracking_code(self):
        mappings = {
            MouseMode.CLICKS: "\x1b[?1000h",
            MouseMode.ALL: "\x1b[?1003h",
            MouseMode.CLICKS_SGR: "\x1b[?1000h\x1b[?1006h",
            MouseMode.ALL_SGR: "\x1b[?1003h\x1b[?1006h",
            MouseMode.SGR_PIXEL: "\x1b[?1003h\x1b[?1016h",
        }
        return mappings.get(self, "")

    def deactivate_code(self):
        mappings = {
            MouseMode.CLICKS_SGR: "\x1b[?1006l\x1b[?1000l",
            MouseMode.ALL_SGR: "\x1b[?1006l\x1b[?1000l",
            MouseMode.SGR_PIXEL: "\x1b[?1016l",
        }
        return mappings.get(self, "\x1b[?1000l")


class Mouse:
    def __init__(self):
        self.x = 0
        self.y = 0

        self.pixel = [0, 0]

        self.left_down = False
        self.right_down = False
        self.state = None

    def reset(self):
        self.left_down = False
        self.right_down = False

    @property
    def pos(self):
        return self.x, self.y

    @property
    def down(self):
        return self.left_down

    def normal_update(self, evt: bytes):
        self.state = evt[0]
        self.left_down = str(evt[0]) == "32"
        self.x = evt[1] - 32
        self.y = evt[2] - 32

    def sgr_update(self, evt: str):
        state, col, row = evt[:-1].split(";")
        self.state = int(state)
        if state == "0":
            self.left_down = evt[-1] == "M"
        if state == "2":
            self.right_down = evt[-1] == "M"
        self.x = int(col)
        self.y = int(row) - 1

    def sgr_pixel_update(self, evt: str):
        state, col, row = evt[:-1].split(";")
        self.state = int(state)
        if state == "0":
            self.left_down = evt[-1] == "M"
        if state == "2":
            self.right_down = evt[-1] == "M"
        self.x = int(col)
        self.y = int(row) - 1


class LogLevels(enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"

    def get_decoration(self):
        mappings = {
            LogLevels.DEBUG: rgb(20, 150, 20),
            LogLevels.INFO: rgb(80, 80, 200),
            LogLevels.WARN: rgb(180, 180, 20),
            LogLevels.ERROR: rgb(200, 80, 20),
        }

        return mappings.get(self, rgb(0, 255, 255))


@dataclass
class Log:
    level: LogLevels
    message: str

    def format(self, log_len=100):
        log = f"{self.message}"
        if len(log) > log_len:
            log = log[: log_len - 2] + ".."
        return self.level.get_decoration()(log)


class ANSI:
    RE = re.compile(r"\x1b\[[0-9;]*m")
    # RE = re.compile(r"\x1b\[[0-9;]*(m|K)")
    RESET = "\x1b[0m"

    def __init__(self):
        self.codes = []

    def update(self, code: str):
        # can be more sophisticated check for reset
        if code == ANSI.RESET:
            self.codes = []
        else:
            self.codes.append(code)

    def ingest(self, text: str):
        for code in ANSI.RE.findall(text):
            self.update(code)

    @property
    def state_code(self):
        return ANSI.RESET + "".join(self.codes)


class Keys(enum.StrEnum):
    UP = enum.auto()
    DOWN = enum.auto()
    LEFT = enum.auto()
    RIGHT = enum.auto()
    HOME = enum.auto()
    END = enum.auto()
    BACKSPACE = enum.auto()
    DEL = enum.auto()
    ENTER = enum.auto()
    ESC = enum.auto()


class KeyEvent:
    def __init__(self, key: str | Keys, *, ctrl=False, alt=False, shift=False):
        self.key = key
        self.ctrl = ctrl
        self.alt = alt
        self.shift = shift

    def __str__(self):
        result = f"Key({self.key.encode()}"
        if self.ctrl:
            result += " + CTRL"
        if self.shift:
            result += " + SHIFT"
        if self.alt:
            result += " + ALT"
        result += ")"
        return result

    def __eq__(self, value):
        if isinstance(value, Keys):
            return self == KeyEvent(value)

        if type(value) == str:
            return self == KeyEvent.init(value)

        if type(value) == type(self):
            return self.key == value.key and self.alt == value.alt and self.ctrl == value.ctrl and self.shift == value.shift

        raise Exception(f"Cannot eq compare {type(value)} with {type(self)}")

    def __add__(self, value) -> KeyEvent:
        if isinstance(value, Keys):
            return self + KeyEvent(value)

        if type(value) == str:
            return self + KeyEvent.init(value)

        if type(value) == type(self):
            return KeyEvent(
                key=self.key or value.key,
                ctrl=self.ctrl or value.ctrl,
                alt=self.alt or value.alt,
                shift=self.shift or value.shift,
            )

        raise Exception(f"Cannot add {type(value)} with {type(self)}")

    def isprintable(self):
        return type(self.key) == str and self.key.isprintable()

    @staticmethod
    def init(key: str) -> KeyEvent:
        special_key_mappings = {
            "A": Keys.UP,
            "B": Keys.DOWN,
            "C": Keys.RIGHT,
            "D": Keys.LEFT,
            "H": Keys.HOME,
            "F": Keys.END,
        }

        if len(key) == 6 and key.startswith(CSI + "1;"):
            key_iden = key[-1]
            modifier = int(key[-2]) - 1

            shift = (modifier >> 0) & 1
            alt = (modifier >> 1) & 1
            ctrl = (modifier >> 2) & 1

            if key_iden in special_key_mappings:
                return KeyEvent(special_key_mappings[key_iden], ctrl=ctrl, alt=alt, shift=shift)

        if len(key) == 4:
            if key == CSI + "3~":
                return KeyEvent(Keys.DEL)

        if len(key) == 3 and key.startswith(CSI):
            if key[2] in special_key_mappings:
                return KeyEvent(special_key_mappings[key[2]])

        # alt key checking
        if len(key) == 2 and key[0] == ESC and key[1].isprintable():
            evt = KeyEvent.init(key[1])
            if evt:
                evt.alt = True
                return evt

        if len(key) == 1:
            if key.isprintable():
                return KeyEvent(key)

            mappings = {
                "\x7f": Keys.BACKSPACE,
                "\r": Keys.ENTER,
                ESC: Keys.ESC,
            }
            if key in mappings:
                return KeyEvent(mappings[key])

            ch = chr(ord(key) + ord("a") - 1)
            if ch.isprintable():
                return KeyEvent(ch, ctrl=True)

        return KeyEvent(key)


def KE(str):
    return KeyEvent.init(str)


ALT = KeyEvent(None, alt=True)
CTRL = KeyEvent(None, ctrl=True)
SHIFT = KeyEvent(None, shift=True)


class TUI(abc.ABC):
    MAX_LOGS = 100

    def __init__(self, *, fps=1, mouse_mode=MouseMode.NONE, render_diff_only=False):
        self.running = True

        self.init_screen()
        self.logs: List[Log] = []
        self.display_diagnostics = False

        self.render_diff_only = render_diff_only
        self.fps = fps
        self.mouse = Mouse()
        self.mouse_mode = mouse_mode

        self.screensize = (0, 0)

        self.widgets = []
        self.started_rendering = False
        self.ended_rendering = False

    def query_screensize(self):
        self.tty_out.write("\x1b[14t")

    def init_screen(self):
        self.size = shutil.get_terminal_size(fallback=(80, 24))
        self.width = self.size.columns
        self.height = self.size.lines
        self.fresh_frame = True
        self.output = [[" " for _ in range(self.width)] for _ in range(self.height)]
        self.old_output = [[" " for _ in range(self.width)] for _ in range(self.height)]
        self.zindex = 0
        self.zbuffer = [[self.zindex for _ in range(self.width)] for _ in range(self.height)]
        self.old_zbuffer = [[0 for _ in range(self.width)] for _ in range(self.height)]
        self.box = Box(0, 0, self.width, self.height)
        self.cursor_loc = [0, 0]

    def handle_resize(self, _signum, _frame):
        self.init_screen()
        self.query_screensize()
        self.wrapped_render()
        self.print_to_screen()

    def handle_exit(self, _signum, _frame):
        self.shutdown()

    def end_rendering(self):
        if not self.started_rendering:
            return
        if self.ended_rendering:
            return

        termios.tcsetattr(self.tty_in.fileno(), termios.TCSADRAIN, self._old_termios)
        self.tty_out.write("\x1b[?25h")  # show cursor
        self.tty_out.write("\x1b[?7h")  # re-enable autowrap
        self.tty_out.write("\x1b[?1049l")  # exit alternate screen (restores previous terminal content)
        self.tty_out.write(self.mouse_mode.deactivate_code())  # disabling mouse tracking
        self.tty_out.flush()

        self.tty_in.close()
        self.tty_out.close()

        self.ended_rendering = True

    def __del__(self):
        self.end_rendering()

    def mount(self, widget, box):
        self.widgets.append(widget)
        widget.render(self, box)

    def withz(self, zi: int):
        @contextmanager
        def zcontext(tui, newz):
            oldz = tui.zraise(newz)
            yield
            tui.zreset(oldz)

        return zcontext(self, zi)

    def shutdown(self):
        self.running = False

    def cwrite(self, cx: int, cy: int, tx: str):
        """Canvas Write
        takes into account zbuffer
        """
        if self.zindex >= self.zbuffer[cy][cx]:
            self.output[cy][cx] = tx
            self.zbuffer[cy][cx] = self.zindex

    def zraise(self, zi: int):
        old = self.zindex
        self.zindex = zi
        return old

    def zreset(self, zi=0):
        self.zindex = zi

    def error_logging(self, title="untitled"):
        @contextmanager
        def error_logging(tui, group):
            try:
                yield
            except Exception as e:
                _, _, exc_tb = sys.exc_info()
                tb_info = traceback.extract_tb(exc_tb, 10)
                tb_info.reverse()

                for i, tb in enumerate(tb_info):
                    padding = " " + "  " * i
                    tui.log(LogLevels.ERROR, f"[{group}]{padding}{tb.filename}:{tb.name}:{tb.lineno}: {repr(e)}")

        return error_logging(self, title)

    def wrapped_render(self):
        with self.error_logging("render"):
            diag_box = self.box.topP(50)[0]
            if self.display_diagnostics:
                with self.withz(10000):
                    self.render_diagnostics(diag_box)

            self.render()

    def start_rendering(self):
        self.tty_in = open("/dev/tty", "r")
        self.tty_out = open("/dev/tty", "w")

        fd = self.tty_in.fileno()
        self._old_termios = termios.tcgetattr(fd)
        tty.setraw(fd)  # to read char by char instead of buffering

        self.query_screensize()
        self.tty_out.write("\x1b[?1049h")  # enter alternate screen
        self.tty_out.write(self.mouse_mode.tracking_code())  # enable mouse tracking
        self.tty_out.flush()
        signal.signal(signal.SIGWINCH, self.handle_resize)
        signal.signal(signal.SIGINT, self.handle_exit)

        self.wrapped_render()
        self.print_to_screen()

        self.started_rendering = True

    def frame(self):
        self.widgets = []
        self.clean_out()
        self.mouse.reset()

        ch = self.get_char(timeout=1 / self.fps)
        if ch:
            if CTRL + "d" == ch:
                self.display_diagnostics = not self.display_diagnostics

            ke = KeyEvent.init(ch)
            self.on_input(ke)

            with self.error_logging("loop"):
                for w in self.widgets:
                    w.on_input(self, ch)

        self.wrapped_render()
        self.print_to_screen()

    def mainLoop(self):
        self.start_rendering()
        while self.running:
            self.frame()
        self.end_rendering()

    def clean_out(self):
        self.zindex = 0
        self.old_zbuffer = self.zbuffer
        self.zbuffer = [[self.zindex for _ in range(self.width)] for _ in range(self.height)]
        self.output = [[" " for _ in range(self.width)] for _ in range(self.height)]

    @abc.abstractmethod
    def render(self):
        raise "render Not implemented"

    @abc.abstractmethod
    def on_input(self, ch: KeyEvent):
        raise "update Not implemented"

    def beep(self):
        sys.stdout.write("\a")
        sys.stdout.flush()

    def draw_border(self, x: int, y: int, w: int, h: int, *, effect=dim):
        r = x + w - 1
        b = y + h - 1

        for i in range(w):
            self.cwrite(x + i, y, effect("─"))
            self.cwrite(x + i, b, effect("─"))

        for i in range(h):
            self.cwrite(x, y + i, effect("│"))
            self.cwrite(r, y + i, effect("│"))

        self.cwrite(x, y, effect("╭"))
        self.cwrite(r, y, effect("╮"))
        self.cwrite(x, b, effect("╰"))
        self.cwrite(r, b, effect("╯"))

    def clean_box(self, box: Box):
        for y in range(box.y, box.y + box.h):
            for x in range(box.x, box.x + box.w):
                self.cwrite(x, y, " ")

    def draw_box(self, box: Box, *, effect=dim):
        self.draw_border(box.x, box.y, box.w, box.h, effect=effect)

    def add_line(self, text: str, box: Box, row: int, *, align=TextAlign.LEFT, effect=None):
        if not text:
            return

        lines: List[str] = []
        while len(text) > 0:
            lines.append(text[: box.w - 2])
            text = text[box.w - 2 :].strip()

        tw = box.w - 2
        match align:
            case TextAlign.LEFT:
                pass
            case TextAlign.RIGHT:
                lines[-1] = lines[-1].rjust(tw)
            case TextAlign.CENTER:
                lines[-1] = lines[-1].center(tw)

        text = "\n".join(lines)

        if effect:
            text = effect(text)

        self.blit_text_to_box(text, box, 1, row)

    def blit_text_to_box(
        self,
        text: str,
        box: Box,
        bxo: int,
        byo: int,
        *,
        scrollx: int = 0,
        scrolly: int = 0,
    ):
        xo, yo = box.at(bxo, byo)

        lines = text.splitlines()

        ansi = ANSI()
        ansi.ingest("\n".join(lines[:scrolly]))

        lines = lines[scrolly : scrolly + box.h + 1]
        for y, line in enumerate(lines):
            x = 0
            i = 0
            prefix = ansi.state_code
            while i < len(line):
                m = ANSI.RE.match(line, i)
                row = y + yo
                col = x + xo - scrollx
                if m:
                    ansi.update(m.group())
                    prefix = ansi.state_code
                    i = m.end()
                else:
                    iswidechar = is_widechar(line[i])
                    if (
                        row > 0
                        and row < self.height - 1
                        and col >= box.x + bxo
                        and col < self.width - 1
                        and box.within(col, row)
                    ):
                        self.cwrite(col, row, prefix + line[i])
                        if iswidechar:
                            # TODO this might be risky, we need to check all constraints before this write as well
                            self.cwrite(col + 1, row, "")
                        prefix = ""
                    x += 1
                    if iswidechar:
                        x += 1
                    i += 1

            if (
                row > 0
                and row < self.height - 1
                and col >= box.x + bxo
                and col < self.width - 1
                and box.within(col, row)
                and self.zindex >= self.zbuffer[row][col]
            ):
                # TODO this might need some more work and precision
                self.output[row][col] += ANSI.RESET

    def render_diagnostics(self, box: Box):
        self.clean_box(box)
        self.draw_box(box, effect=pale_yellow)

        log_box, settings_box = box.pad(1).leftP(75)
        self.draw_box(log_box)
        self.draw_box(settings_box)

        self.blit_text_to_box(pale_yellow(" Log "), log_box, 1, 0)
        self.blit_text_to_box(pale_yellow(" Settings "), settings_box, 1, 0)

        log_len = log_box.w - 2
        for i, log in enumerate(self.logs[-(log_box.h - 2) :]):
            log_line_box = log_box.sub_box(0, i + 1, log_box.w, 1)

            self.blit_text_to_box(log.format(log_len), log_line_box, 1, 0)

        green = rgb(135, 217, 98)
        ln = next_line(1)
        self.blit_text_to_box(f"{green('Mouse Pos  ')} : {self.mouse.pos}          ".strip(), settings_box, 1, next(ln))
        self.blit_text_to_box(f"{green('Mouse State')} : {self.mouse.state}        ".strip(), settings_box, 1, next(ln))
        self.blit_text_to_box(f"{green('Cursor Pos ')} : {self.cursor_loc}         ".strip(), settings_box, 1, next(ln))
        self.blit_text_to_box(f"{green('Screen Size')} : {self.width}x{self.height}".strip(), settings_box, 1, next(ln))
        self.blit_text_to_box(f"{green('Tracking   ')} : {self.mouse_mode}         ".strip(), settings_box, 1, next(ln))
        self.blit_text_to_box(f"{green('FPS        ')} : {self.fps}                ".strip(), settings_box, 1, next(ln))
        self.blit_text_to_box(f"{green('Screen size')} : {self.screensize}         ".strip(), settings_box, 1, next(ln))
        if self.render_diff_only:
            self.blit_text_to_box(green("Rendering Diffs only"), settings_box, 1, next(ln))
        else:
            self.blit_text_to_box(green("Rendering Full Frames"), settings_box, 1, next(ln))

    def get_diffs(self):
        @dataclass
        class Diff:
            line: int
            start: int
            end: int

        diffs: List[Diff] = []

        for y in range(self.height):
            x = 0
            while x < self.width:
                if self.old_output[y][x] != self.output[y][x]:
                    start = x
                    while x < self.width and self.old_output[y][x] != self.output[y][x]:
                        x += 1
                    end = x
                    diffs.append(Diff(line=y, start=start, end=end))
                x += 1

        if diffs:
            self.log(LogLevels.DEBUG, f"diffs: {len(diffs)}, {diffs[0]}, {diffs[-1]}")
        else:
            self.log(LogLevels.DEBUG, f"no diffs")
        return diffs

    def print_to_screen(self):
        self.tty_out.write("\x1b[?7l")  # disable autowrap
        self.tty_out.write("\x1b[?25l")  # hide cursor during draw

        if self.render_diff_only and not self.fresh_frame:
            self.print_out_diffs()
        else:
            self.print_out_full()
            if self.fresh_frame:
                self.fresh_frame = False

        self.tty_out.write("\x1b[?25h")  # show cursor
        self.tty_out.write("\x1b[?7h")  # re-enable autowrap

        cx, cy = self.cursor_loc
        self.tty_out.write(f"\x1b[{cy+1};{cx+1}H")  # align cursor
        self.tty_out.flush()

    # NOTE diff printing has problems, it doesnt follow ansi coloring anythin written is just white
    # no problem if its pure white
    def print_out_diffs(self):
        diffs = self.get_diffs()
        self.old_output = [x.copy() for x in self.output]

        for diff in diffs:
            self.tty_out.write(f"\x1b[{diff.line + 1};{diff.start + 1}H")  # move cursor to absolute position
            self.tty_out.write("".join(self.output[diff.line][diff.start : diff.end]))

    def print_out_full(self):
        for i, row in enumerate(self.output):
            self.tty_out.write(f"\x1b[{i + 1};1H")  # move cursor to absolute position
            self.tty_out.write("".join(row))

    def get_char(self, *, timeout=2):
        """Read a single raw keypress from /dev/tty, handling multi-byte escape sequences"""
        fd = self.tty_in.fileno()
        wait_dur = min(0.1, 0.5 / self.fps)
        cycles = max(math.floor(timeout / wait_dur), 1)
        for _ in range(cycles):
            if not self.running:
                break
            if not select.select([fd], [], [], wait_dur)[0]:
                continue

            ch = os.read(fd, 1).decode()
            # simple character
            if ch != "\x1b":
                return ch

            # escape codes
            if select.select([fd], [], [], wait_dur / 2)[0]:
                ch += os.read(fd, 1).decode()
                if ch == "\x1b[" and select.select([fd], [], [], wait_dur / 2)[0]:
                    ch += os.read(fd, 1).decode()

                    # Mouse click event
                    if ch == "\x1b[M":
                        pos = os.read(fd, 3)
                        self.mouse.normal_update(pos)
                        return None

                    # SGR mouse tracking
                    elif ch == "\x1b[<":
                        pos_details = os.read(fd, 1).decode()
                        while pos_details[-1].lower() != "m":
                            pos_details += os.read(fd, 1).decode()

                        if self.mouse_mode == MouseMode.ALL_SGR or self.mouse_mode == MouseMode.CLICKS_SGR:
                            self.mouse.sgr_update(pos_details)
                        if self.mouse_mode == MouseMode.SGR_PIXEL:
                            self.mouse.sgr_pixel_update(pos_details)
                        return None

                    # screen size in pixels
                    elif ch == "\x1b[4":
                        size_details = os.read(fd, 1).decode()
                        while size_details[-1] != "t":
                            size_details += os.read(fd, 1).decode()

                        _, height, width = size_details[:-1].split(";")
                        self.screensize = (int(width), int(height))
                        return None

                    # Modified keys
                    elif ch == "\x1b[1":
                        ch += os.read(fd, 1).decode()
                        if ch == "\x1b[1;":
                            ch += os.read(fd, 2).decode()
                            return ch
                        
                    # delete key
                    elif ch == "\x1b[3":
                        ch += os.read(fd, 1).decode()
                        if ch == "\x1b[3~":
                            return ch
            return ch
        return None

    # TODO this is hack (although works nicely, to prevent event propogration to lower components)
    # eventually we will need a better way of hendling this
    def oldz_match(self):
        mx, my = self.mouse.pos
        return self.old_zbuffer[my][mx] <= self.zindex

    def hovering(self, box: Box):
        return box.within(*self.mouse.pos) and self.oldz_match()

    def clicking(self, box: Box):
        return self.mouse.down and box.within(*self.mouse.pos) and self.oldz_match()

    def right_clicking(self, box: Box):
        return self.mouse.right_down and box.within(*self.mouse.pos) and self.oldz_match()

    def get_screen_pos(self, cx, cy):
        cw, ch = self.width, self.height
        sw, sh = self.screensize
        if cw == 0 or ch == 0:
            return 0, 0
        return (cx + 0.5) * sw / cw, (cy + 0.5) * sh / ch

    def get_char_pos(self, sx, sy):
        cw, ch = self.width, self.height
        sw, sh = self.screensize
        if sw == 0 or sh == 0:
            return 0, 0
        return int(sx * cw / sw), int(sy * ch / sh)

    def get_mouse_screen_pos(self):
        return self.get_screen_pos(*self.mouse.pos)

    def log(self, level: LogLevels, msg: str):
        log = Log(level=level, message=str(msg))
        self.logs = self.logs[-self.MAX_LOGS :] + [log]

    def ldebug(self, msg: str):
        self.log(LogLevels.DEBUG, msg)

    def linfo(self, msg: str):
        self.log(LogLevels.INFO, msg)

    def lwarn(self, msg: str):
        self.log(LogLevels.WARN, msg)

    def lerror(self, msg: str):
        self.log(LogLevels.ERROR, msg)


SELECT_OPEN = None


def select_wg(tui: TUI, box: Box, title: str, selected: str, options: List[str], *, on_select=None) -> str:
    global SELECT_OPEN
    accent = rgb(177, 90, 196)

    with tui.withz(10):
        tui.clean_box(box)
        tui.draw_box(box, effect=accent)
        tui.add_line(f"{str(title)} >", box, 1, align=TextAlign.CENTER, effect=accent)

        if tui.clicking(box):
            if SELECT_OPEN == title:
                SELECT_OPEN = None
            else:
                SELECT_OPEN = title

        if SELECT_OPEN == title:
            content_box = Box(box.x, box.y + box.h, box.w, len(options) + 2)
            tui.clean_box(content_box)
            tui.draw_box(content_box)

            rest = content_box.top(1)[1]
            for i, opt in enumerate(options):
                a, rest = rest.top(1)
                if tui.clicking(a):
                    SELECT_OPEN = None
                    if on_select:
                        on_select(opt)
                    return opt
                if tui.hovering(a):
                    tui.add_line(opt, content_box, i + 1, effect=gray_bg)
                else:
                    tui.add_line(opt, content_box, i + 1)

        return selected


def toggle(tui: TUI, box: Box, title: str, selected: bool) -> bool:
    icon = "✅" if selected else "⭕"
    tui.add_line(f"{icon} {title}", box, 0, effect=tui.hovering(box) and gray_bg)

    if tui.clicking(box):
        return not selected
    return selected


def button(tui: TUI, box: Box, title: str, *, disabled=False) -> bool:
    effect = None
    if tui.hovering(box):
        effect = gray_bg
    if disabled:
        effect = dim

    tui.add_line(title, box, 0, align=TextAlign.CENTER, effect=effect)
    return not disabled and tui.clicking(box)


class Widget(abc.ABC):
    @abc.abstractmethod
    def render(self, tui: TUI, box: Box):
        pass

    @abc.abstractmethod
    def on_input(self, tui: TUI, ch: str):
        pass


class InputWG(Widget):
    def __init__(self, title: str):
        self.focused = False
        self.curs = 0
        self.value = ""
        self.box: Box = None
        self.title = title

    def render(self, tui: TUI, box: Box):
        self.box = box

        col = pale_yellow
        if self.focused:
            col = red
        tui.draw_box(box, effect=col)
        tui.blit_text_to_box(self.value, box, 1, 1)
        tui.blit_text_to_box(col(self.title), box, 1, 0)

        if tui.clicking(box):
            self.focused = True
        elif tui.clicking(tui.box):
            self.focused = False

    def on_input(self, tui: TUI, ch: str):
        if not self.focused:
            return

        if ch == ESC:
            self.focused = False
            return
        self.value, self.curs, _ = write(self.value, self.curs, ch)

        if self.box:
            cx, cy = self.box.at(self.curs + 1, 1)
            tui.cursor_loc = [cx, cy]


def write(text: str, cursor: int, ch: KeyEvent) -> Tuple[str, int, bool]:
    handled = True
    if ch == Keys.BACKSPACE:
        if cursor > 0:
            text = text[: cursor - 1] + text[cursor:]
            cursor -= 1
    elif ch == Keys.RIGHT:
        if cursor < len(text):
            cursor += 1
    elif ch == Keys.LEFT:
        if cursor > 0:
            cursor -= 1
    elif type(ch.key) == str and ch.key.isprintable():
        text = text[:cursor] + ch.key + text[cursor:]
        cursor += 1
    else:
        handled = False
    return text, cursor, handled


class SelectWG(Widget):
    def __init__(self, title: str, options: List[str], on_select):
        self.title = title
        self.options = options
        self.on_select = on_select

        self.accent = rgb(255, 0, 255)

    def title_tr(self, text):
        return gray_bg(self.accent(text))

    def render(self, box, tui):
        title_box, rest = box.top(3)
        tui.clean_box(title_box)
        tui.draw_box(title_box, effect=self.accent)

        hovering = tui.hovering(box)
        tui.add_line(f"{self.title} >", title_box, 1, align=TextAlign.CENTER, effect=self.accent)

        if hovering:
            content_box = rest.top(len(self.options) + 2)[0]
            tui.draw_box(content_box)

            rest = content_box.top(1)[1]
            for i, opt in enumerate(self.options):
                a, rest = rest.top(1)
                if tui.clicking(a):
                    self.on_select(opt)
                if tui.hovering(a):
                    tui.add_line(opt, content_box, i + 1, effect=gray_bg)
                else:
                    tui.add_line(opt, content_box, i + 1)

    def on_input(self, tui, ch):
        pass


class FileWatcher(object):
    def __init__(self, filename, interval_sec=1):
        self._cached_stamp = 0
        self.filename = filename
        self.last_checked_timestamp = datetime.datetime.now()
        self.min_interval_sec = interval_sec

    def has_changed(self):
        d = datetime.datetime.now() - self.last_checked_timestamp
        if d < datetime.timedelta(seconds=self.min_interval_sec):
            return False

        self.last_checked_timestamp = datetime.datetime.now()
        stamp = os.stat(self.filename).st_mtime
        if stamp != self._cached_stamp:
            self._cached_stamp = stamp
            return True
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("expected 2 args")
        exit()

    file_name = sys.argv[1]
    object_name = sys.argv[2]
    watcher = FileWatcher(file_name)
    module_name = file_name[:-3]

    mod = importlib.import_module(module_name)
    if not hasattr(mod, object_name):
        print(f"No {object_name} defined in module {module_name}")
        exit()

    tui_obj: TUI = getattr(mod, object_name)

    try:
        tui_obj.start_rendering()

        while tui_obj.running:
            if watcher.has_changed():
                try:
                    mod = importlib.reload(mod)
                    if not hasattr(mod, object_name):
                        print(f"No {object_name} defined in module {module_name}")
                        exit()

                    tui_obj = getattr(mod, object_name)
                    tui_obj.start_rendering()
                except Exception as e:
                    tui_obj.lerror(f"err while trying to reload module - {repr(e)}")
            else:
                tui_obj.frame()
    except Exception as e:
        print(f"error - {repr(e)}")
