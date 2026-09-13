# ttk_style_probe

Works out, by rendering them, which `ttk.Style` options each ttk widget actually
honours. The results are written up as the vault note `ttk Style Options`; this
directory is the instrument that produced them, kept so the note can be checked
again on a different Tk build or platform.

Nothing here imports `tkfacade`. It is pure `tkinter` against a system Python, and it
needs no dependencies beyond a virtual X display.

## Why it renders instead of asking

`ttk.Style` validates nothing. `configure("TButton", nonsenseoption="hello")` is
accepted, stored, and handed back by both `lookup` and `configure` afterwards,
and the button renders exactly as if the line had never been written. An option
being ignored is indistinguishable, through the API, from one that works.

`Style.element_options` looks like the answer and is not. It gives what a
layout's elements *declare*, which is neither sufficient — `-text` is declared in
44 style/theme pairs and drawn in none — nor complete: `Treeview -rowheight` and
`Entry -foreground` are honoured with no element declaring them.

So each option is set, the widget is drawn, and the pixels are compared.

## Running it

```sh
Xvfb :99 -screen 0 800x600x24 -fbdir /tmp/ttkfb &
cd Projects/tkfacade
DISPLAY=:99 python -m experiments.ttk_style_probe.rules        /tmp/ttkfb/Xvfb_screen0
DISPLAY=:99 python -m experiments.ttk_style_probe.probe        /tmp/ttkfb/Xvfb_screen0
DISPLAY=:99 python -m experiments.ttk_style_probe.entry_family /tmp/ttkfb/Xvfb_screen0
python -m experiments.ttk_style_probe.tables /tmp/ttkfb/results.json > tables.md
```

`-fbdir` is what makes the sweep tractable: Xvfb keeps its screen in a
memory-mapped file, so a grab is a memory read rather than a fork and an exec.
A full sweep is around 8,000 measurements and takes roughly forty minutes; pass a
style name as a second argument to `probe` to do one style across all themes in
seconds. `rules` finishes in about a minute and is the thing to run first.

The measurement files are not committed. `probe` and `entry_family` write them
beside the framebuffer rather than into the working directory, so a run leaves
no untracked files in the checkout: `results.json` (about 1.2 MB) and
`entry_family.json`, which `tables` reads as a pair.

## What is in here

- `capture.py` — reads the Xvfb framebuffer through its backing file.
- `png.py` — writes a grab out as a PNG, for checking a verdict by eye.
- `specs.py` — the styles to probe, the values to try, the states to try them in.
- `probe.py` — the sweep: every option against every style in every theme.
- `entry_family.py` — the selection and insert-cursor options, which need a
  focused widget with a selection and so cannot be measured by the sweep.
- `rules.py` — one check per rule the note states, printing pass or fail.
- `tables.py` — turns the results into markdown.

## Traps

Each of these produced a confidently wrong answer before it was found, and each
is now guarded in the code or pinned by a check in `rules.py`.

- **The pointer is a state.** A widget under the mouse is `active`, and every
  theme maps `-background` for `active` on the root style, so the mapped value
  wins over whatever is being tested. A widget large enough to sit under the
  pointer therefore reports its background as unstyleable. The pointer is warped
  into a corner — and the warp is silently dropped unless the toplevel is already
  mapped, so it happens after the first `update()`.
- **A `map` beats a `configure`, from anywhere up the chain.** Including the root
  style `.`, which every theme configures. Options that look inert are often
  being overridden by a map several levels less specific than the style setting
  them.
- **The sash reads a different name than its layout.** The layout is registered
  as `Horizontal.Sash`, and the widget looks options up under the bare `Sash`.
  Configuring the oriented name changes what `lookup` reports and nothing on
  screen, which reads as "the sash is not styleable" and is not true.
- **Widget options shadow style options.** An option the widget also carries is
  only reachable from the style when the widget's own value is empty, so a probe
  that sets `text="Button"` to have something to look at has already made the
  style's `-text` unreachable.
- **Some options need content.** `-justify` needs a second line, `-space` needs
  an image beside the text, `-indent` needs a branch that is open. Without it
  they read as inert.
- **A focused entry blinks.** Two grabs of one rendering disagree, so anything
  needing focus has to be judged across a blink cycle rather than in one frame.

## What it does not cover

Only the themes a Tk build offers where it runs — under X11 that is `clam`,
`alt`, `default` and `classic`. The Windows themes (`winnative`, `xpnative`,
`vista`) and macOS `aqua` define their own elements and would have to be measured
on those platforms. Running `rules.py` there is the cheap first step: it says
which of the note's rules still hold before any sweep is worth starting.
