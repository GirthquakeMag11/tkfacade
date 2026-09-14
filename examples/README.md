# examples

Functional, interactive examples of tkfacade widgets — each runnable on its
own and usable to live-demo a surface to a person.

- `showcase.py` — a one-window tour of the widget suite: ten tabs, every one
  built and wired through the facade alone. Run it with
  `uv run python examples/showcase.py`. The file is the standing proof of
  the demonstration requirement: it imports tkfacade and the stdlib alone,
  no tkinter, and `tests/test_examples_gate.py` holds it (and every example
  beside it) to that.

The scratch-pad harness for trying things out lives in
`../experiments/fast_testing.py`.
