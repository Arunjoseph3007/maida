#!/usr/bin/python3

import base64
import datetime
import enum
import math
import sys
from typing import List
from maida import *

fonts = {
    "ANSI Shadow": """
 █████╗     ██╗ ██████╗ ██████╗ ██╗  ██╗███████╗ ██████╗███████╗ █████╗  █████╗          
██╔═███╗   ███║ ╚════██╗╚════██╗██║  ██║██╔════╝██╔════╝╚════██║██╔══██╗██╔══██╗   ██╗   
██║█╔██║   ╚██║  █████╔╝ █████╔╝███████║███████╗███████╗    ██╔╝╚█████╔╝╚██████║   ╚═╝   
███╔╝██║    ██║ ██╔═══╝  ╚═══██╗╚════██║╚════██║██╔═══██╗  ██╔╝ ██╔══██╗ ╚═══██║   ██╗   
╚█████╔╝    ██║ ███████╗██████╔╝     ██║███████║╚██████╔╝  ██║  ╚█████╔╝ █████╔╝   ╚═╝   
 ╚════╝     ╚═╝ ╚══════╝╚═════╝      ╚═╝╚══════╝ ╚═════╝   ╚═╝   ╚════╝  ╚════╝          
                                                                            """,
    "ANSI Regular": """
 ██████     ██  ██████  ██████  ██   ██ ███████  ██████ ███████  █████   █████           
██  ████   ███       ██      ██ ██   ██ ██      ██           ██ ██   ██ ██   ██    ██    
██ ██ ██    ██   █████   █████  ███████ ███████ ███████     ██   █████   ██████          
████  ██    ██  ██           ██      ██      ██ ██    ██   ██   ██   ██      ██    ██    
 ██████     ██  ███████ ██████       ██ ███████  ██████    ██    █████   █████           
                                                                                 """,
    "Hash": """                                                                                                              
  .####.    .###     . ####:   . ####:       ###   #######      ###:   ########   :####:    :####.            
  ######    ####     #######:  #######:     :###   #######    ######   ########  :######:  :######            
 :##  ##:   #:##     #:.   ##  #:.   ##    .####   ##        :##. .#         #   ##    ##  ##    #            
 ##:  :##     ##           ##        ##    ##.##   ##        ##:            ##.  ##    ##  ##    ##           
 ##    ##     ##          :#         ##   :#: ##   ##### .   ##:###:        ##   ##    ##  ##    ##     ##    
 ## ## ##     ##          ##     #####   .##  ##   #######.  #######:      ##.    ######   ##    ##     ##    
 ## ## ##     ##        .##:     #####.  ##   ##   #:  .###  ##    ##     :##    .######.  :#######     ##    
 ##    ##     ##       .##:          ##  ########        ##  ##    ##     ##:    ##    ##   :###:##           
 ##:  :##     ##      :##:           ##  ########        ##  ##    ##    :##     ##    ##       :##           
 :##  ##:     ##     :##:      #:    ##       ##   #:  .###   #    ##    ##:     ##    ##   #. .##:     ##    
  ######   ########  ########  #######:       ##   #######.   ######:   :##      :######:   ######      ##    
  .####.   ########  ########  :#####:        ##   :#### .    .####:    ##:       :####:    :###        ##    
                                                                                                              """,
}


def block_font(t: str, font):
    index = clamp(ord(t) - ord("0"), 0, 10)
    f = fonts[font]
    lines = f.splitlines()
    cwidth = len(lines[1]) // 11
    char_str = [l[index * cwidth : (index + 1) * cwidth] for l in lines[1:-1]]

    return "\n".join(char_str)


class SelectWG:
    def __init__(self, title: str, options: List[str], on_select):
        super().__init__()
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


class ClockWG:
    def __init__(self):
        super().__init__()
        self.font = list(fonts.keys())[0]
        self.on_font_change(self.font)

    def on_font_change(self, opt):
        self.font = opt

        lines = fonts[self.font].splitlines()
        self.cwidth = len(lines[1]) // 11
        self.cheight = len(lines) - 2

    def render(self, box, tui):
        self.font = select_wg(
            tui, box.top_right(15, 3), "Font", self.font, list(fonts.keys()), on_select=self.on_font_change
        )

        clicking = tui.clicking(box)
        hovering = tui.hovering(box)

        col = dim
        if hovering:
            col = red
        if clicking:
            col = pale_yellow

        tui.draw_box(box, effect=col)
        date_str = datetime.datetime.now().strftime("%H:%M:%S")

        total_width = len(date_str) * self.cwidth
        xpad = (box.w - total_width) // 2
        ypad = (box.h - self.cheight) // 2
        for i, c in enumerate(date_str):
            tui.blit_text_to_box(block_font(c, self.font), box, i * self.cwidth + xpad, ypad)


class TUIClock(TUI):
    def __init__(self):
        super().__init__(mouse_mode=MouseMode.ALL_SGR)

        self.clock = ClockWG()

    def on_input(self, ch):
        if ch == "q":
            self.shutdown()

    def on_font_change(self, opt):
        self.log(LogLevels.INFO, f"Font changed to {opt}")

    def render(self):
        b = self.box
        self.draw_box(b)

        b = b.pad(1)
        self.draw_box(b)

        b, c = b.leftP(25)
        self.clock.render(c, self)

        l = "Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, type specimen and bookmark."
        self.draw_box(b)
        self.add_line(l, b, 1, align=TextAlign.LEFT, effect=red)
        self.add_line(l, b, 9, align=TextAlign.CENTER, effect=pale_yellow)
        self.add_line(l, b, 16, align=TextAlign.RIGHT, effect=rgb_bg(104, 161, 212))


class DrawModes(enum.Enum):
    DRAW = "DRAW"
    CIRCLE = "CIRCLE"
    SQUARE = "SQUARE"
    ERASER = "ERASER"


class PenInpWG(InputWG):
    def __init__(self):
        super().__init__("Pen")
        self.value = "█"

    def on_input(self, tui, ch: str):
        if not self.focused:
            return

        if ch == ESC:
            self.focused = False
            return

        if len(ch) == 1 and ch.isprintable():
            self.value = ch

        if self.box:
            tui.cursor_loc = self.box.at(2, 1)


class TUIDraw(TUI):
    def __init__(self, *, fps=1):
        super().__init__(fps=fps, mouse_mode=MouseMode.ALL_SGR)

        self.canvas = [[]]
        self.preview = [[]]

        self.ink_mapping = {
            "noop": noop,
            "pale_yellow": pale_yellow,
            "black": black,
            "red": red,
        }
        self.ink_options = list(self.ink_mapping.keys())
        self.mod_options = [dm.value for dm in DrawModes]
        self.ink = self.ink_options[0]
        self.mod = self.mod_options[0]

        self.sq_start = None
        self.circle_c = None

        self.pen_inp = PenInpWG()

    def on_input(self, ch):
        if ch == ESC:
            self.sq_start = None
            self.circle_c = None
        if ch == "q":
            self.shutdown()
        if ch == "b":
            self.beep()
        if ch == "c":
            self.clean_canvas()
        if ch == "r":
            self.render_diff_only = not self.render_diff_only
        if ch == "p":
            try:
                lines = ["".join(row) for row in self.canvas]
                canvas_text = "\n".join(lines).encode()
                encoded = base64.b64encode(canvas_text).decode()
                sys.stdout.write(f"\x1b]52;c;{encoded}\007")
                sys.stdout.flush()
            except Exception as e:
                self.log(LogLevels.ERROR, f"Err: {repr(e)}")

    def get_canvas_size(self):
        return len(self.canvas[0]), len(self.canvas)

    def clean_canvas(self):
        w, h = self.get_canvas_size()
        self.canvas = [[None for _ in range(w)] for _ in range(h)]
        self.preview = [[None for _ in range(w)] for _ in range(h)]

    def resize_canvas_if_needed(self, w, h):
        cw, ch = self.get_canvas_size()

        if cw != w or ch != h:
            self.canvas = [[None for _ in range(w)] for _ in range(h)]
            self.preview = [[None for _ in range(w)] for _ in range(h)]

    def get_paint(self):
        return self.ink_mapping[self.ink](self.pen_inp.value)

    def draw_square(self, a, b, canvas=None):
        if not canvas:
            canvas = self.canvas
        ax, ay = a
        bx, by = b

        sx = min(ax, bx)
        sy = min(ay, by)
        ex = max(ax, bx)
        ey = max(ay, by)

        for i in range(sx, ex + 1):
            canvas[sy][i] = self.get_paint()
            canvas[ey][i] = self.get_paint()
        for i in range(sy, ey + 1):
            canvas[i][sx] = self.get_paint()
            canvas[i][ex] = self.get_paint()

    def draw_circle(self, center, on_perimeter, canvas=None):
        if not canvas:
            canvas = self.canvas

        csx, csy = self.get_screen_pos(*center)
        opx, opy = self.get_screen_pos(*on_perimeter)

        radius_sq = (csx - opx) ** 2 + (csy - opy) ** 2
        radius = math.sqrt(radius_sq)

        sx = csx - radius
        sy = csy - radius
        ex = csx + radius
        ey = csy + radius

        minx, miny = self.get_char_pos(sx, sy)
        maxx, maxy = self.get_char_pos(ex, ey)

        canv_box = Box(0, 0, len(canvas[0]), len(canvas))
        threshold = max(radius_sq / 10, 500)
        for x in range(minx - 5, maxx + 5):
            for y in range(miny - 1, maxy + 2):
                if not canv_box.within(x, y):
                    continue
                psx, psy = self.get_screen_pos(x, y)

                dist_sq = (psx - csx) ** 2 + (psy - csy) ** 2
                if abs(dist_sq - radius_sq) < threshold:
                    canvas[y][x] = self.get_paint()

    def erase_block(self, p, canvas=None):
        if not canvas:
            canvas = self.canvas

        cx, cy = p
        w, h = 12, 4

        for y in range(cy - h // 2, cy + h // 2):
            for x in range(cx - w // 2, cx + w // 2):
                canvas[y][x] = None

    def get_combined_canvas(self):
        w, h = self.get_canvas_size()
        canvas = [[" " for _ in range(w)] for _ in range(h)]

        for y in range(h):
            for x in range(w):
                if self.preview[y][x]:
                    canvas[y][x] = self.preview[y][x]
                elif self.canvas[y][x]:
                    canvas[y][x] = self.canvas[y][x]

        lines = ["".join(row) for row in canvas]
        canvas_text = "\n".join(lines)
        return canvas_text

    def render(self):
        head, canvas = self.box.top(3)
        self.resize_canvas_if_needed(canvas.w - 2, canvas.h - 2)

        # Render Heading
        head, ink_sel_box = head.right(18)
        head, mod_sel_box = head.right(18)
        head, pen_inp_box = head.right(18)

        self.ink = select_wg(self, ink_sel_box, "Ink", self.ink, self.ink_options)
        self.mod = select_wg(self, mod_sel_box, "Mod", self.mod, self.mod_options)
        self.mount(self.pen_inp, pen_inp_box)

        self.draw_box(head)
        self.blit_text_to_box(bold(orange("< ASCI ART School >")), head, 1, 1)

        # rended canvas
        self.draw_box(canvas, effect=pale_yellow)
        self.blit_text_to_box(pale_yellow(" Canvas "), canvas, 1, 0)

        # clean preview
        w, h = self.get_canvas_size()
        self.preview = [[None for _ in range(w)] for _ in range(h)]

        if self.hovering(canvas.pad(1)):
            mx, my = self.mouse.pos
            cx = mx - canvas.x - 2
            cy = my - canvas.y - 1
            if self.mouse.down:
                match self.mod:
                    case DrawModes.DRAW.value:
                        self.canvas[cy][cx] = self.get_paint()
                    case DrawModes.SQUARE.value:
                        if self.sq_start:
                            self.draw_square((cx, cy), self.sq_start)
                            self.sq_start = None
                        else:
                            self.sq_start = (cx, cy)
                    case DrawModes.CIRCLE.value:
                        if self.circle_c:
                            self.draw_circle(self.circle_c, (cx, cy))
                            self.circle_c = None
                        else:
                            self.circle_c = (cx, cy)
                    case DrawModes.ERASER.value:
                        self.erase_block((cx, cy))
            elif self.mouse.right_down:
                self.canvas[cy][cx] = None

            # Render preview
            if self.sq_start:
                self.draw_square((cx, cy), self.sq_start, self.preview)
            elif self.circle_c:
                self.draw_circle(self.circle_c, (cx, cy), self.preview)
            elif self.mod == DrawModes.ERASER.value:
                self.erase_block((cx, cy), self.preview)

        canvas_text = self.get_combined_canvas()
        self.blit_text_to_box(canvas_text, canvas, 1, 1)


def get_ansi_text():
    text = f"""hey
    {noop('Lorem')} Ipsum {pale_yellow('''is simply dummy text 
    of the printing and typesetting industry.
    Lorem Ipsum has been the industry's
    standard dummy text ever since the 1500s,''')}
    type specimen and bookmark.
    Lorem {red('Ipsum')} is simply dummy text 
    of the printing and typesetting industry.
    Lorem Ipsum has been the industry's
    standard dummy text ever since the 1500s,
    type specimen and bookmark.
    Lorem Ipsum is simply dummy text 
    of the printing and typesetting industry.
    Lorem Ipsum has been the industry's
    standard dummy text ever since the 1500s,
    type specimen and bookmark.
    Lorem Ipsum is simply dummy text 
    of the printing and typesetting industry.
    Lorem Ipsum has been the industry's
    standard dummy text ever since the 1500s,
    type specimen and bookmark.
    Lorem Ipsum is simply dummy text 
    of the printing and typesetting industry.
    Lorem Ipsum has been the industry's
    standard dummy text ever since the 1500s,
    type specimen and bookmark.
    Lorem Ipsum is simply dummy text 
    of the printing and typesetting industry.
    Lorem Ipsum has been the industry's
    standard dummy text ever since the 1500s,
    type specimen and bookmark.
    Lorem Ipsum is simply dummy text 
    of the printing and typesetting industry.
    Lorem Ipsum has been the industry's
    standard dummy text ever since the 1500s,
    type specimen and bookmark.
    Lorem Ipsum is simply dummy text 
    of the printing and typesetting industry.
    Lorem Ipsum has been the industry's
    standard dummy text ever since the 1500s,
    type specimen and bookmark.
    """
    text = dim(pale_yellow(text))

    return "\n".join([t.strip() for t in text.splitlines()])


class TUIAnsi(TUI):
    def __init__(self, *, fps=1):
        super().__init__(fps=fps, mouse_mode=MouseMode.NONE)

        self.scroll = [0, 0]

    def on_input(self, ch):
        if ch == "q":
            self.shutdown(2)
        if ch == "s":
            self.scroll[1] += 1
        if ch == "w" and self.scroll[1] > 0:
            self.scroll[1] -= 1
        if ch == "d":
            self.scroll[0] += 1
        if ch == "a" and self.scroll[0] > 0:
            self.scroll[0] -= 1

    def render(self):
        text = get_ansi_text()
        self.draw_box(self.box)

        b = self.box.pad(2)
        self.draw_box(b)

        self.blit_text_to_box(
            text,
            b,
            1,
            1,
            scrollx=self.scroll[0],
            scrolly=self.scroll[1],
        )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(f"Usage: {sys.argv[0]} app")
        exit(1)

    if sys.argv[1] == "clock":
        TUIClock().mainLoop()
    if sys.argv[1] == "draw":
        TUIDraw().mainLoop()
    if sys.argv[1] == "ansi":
        TUIAnsi().mainLoop()
    if sys.argv[1] == "ansi_print":
        print(get_ansi_text())
    else:
        print(f"Unknown app: {sys.argv[1]}")
        exit(2)
