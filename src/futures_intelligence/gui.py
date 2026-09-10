"""Minimal cross-platform desktop launcher for the bounded Huatai demo."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import scrolledtext, ttk

from futures_intelligence.main import run_htfc_demo


READY_STATUS = "准备就绪"
RUNNING_STATUS = "正在获取并分析华泰研报…"
SUCCESS_STATUS = "完成"
FAILURE_STATUS = "运行失败"
_ERROR_MESSAGE_LIMIT = 500
_RESULT_POLL_INTERVAL_MS = 75


@dataclass(frozen=True, slots=True)
class DemoRunState:
    """Immutable GUI state emitted by the demo controller."""

    status: str = READY_STATUS
    output: str = ""
    is_running: bool = False


@dataclass(frozen=True, slots=True)
class _DemoRunResult:
    """One worker result awaiting consumption by the Tk main thread."""

    status: str
    output: str


def _start_daemon_worker(callback: Callable[[], None]) -> None:
    """Run blocking demo work without blocking the Tk event loop."""
    threading.Thread(target=callback, daemon=True).start()


def _concise_error_text(error: Exception) -> str:
    """Return a bounded user-facing message without an internal traceback."""
    message = str(error).strip() or type(error).__name__
    return message[:_ERROR_MESSAGE_LIMIT]


class DemoRunController:
    """Coordinate the bounded demo independently from Tk widgets."""

    def __init__(
        self,
        *,
        run_demo: Callable[[], str] | None = None,
        start_worker: Callable[[Callable[[], None]], None] = _start_daemon_worker,
        on_state_change: Callable[[DemoRunState], None] | None = None,
    ) -> None:
        self._run_demo = run_demo if run_demo is not None else run_htfc_demo
        self._start_worker = start_worker
        self._on_state_change = on_state_change
        self._results: Queue[_DemoRunResult] = Queue()
        self._closed = False
        self.state = DemoRunState()

    @property
    def closed(self) -> bool:
        """Return whether the GUI lifecycle has ended."""
        return self._closed

    def start(self) -> bool:
        """Start one demo run and reject duplicate clicks while it is active."""
        if self._closed or self.state.is_running:
            return False
        self._set_state(DemoRunState(RUNNING_STATUS, self.state.output, True))
        self._start_worker(self._run_in_worker)
        return True

    def close(self) -> None:
        """Prevent future state application without waiting for the worker."""
        self._closed = True

    def process_pending_results(self) -> bool:
        """Apply queued worker results from the GUI main thread."""
        if self._closed:
            return False
        processed = False
        while True:
            try:
                result = self._results.get_nowait()
            except Empty:
                return processed
            self._finish(result.status, result.output)
            processed = True

    def clear_output(self) -> None:
        """Clear only the displayed output while preserving execution status."""
        self._set_state(
            DemoRunState(self.state.status, "", self.state.is_running)
        )

    def _run_in_worker(self) -> None:
        try:
            output = self._run_demo()
        except Exception as error:
            message = f"Demo 运行失败\n{_concise_error_text(error)}"
            self._results.put(_DemoRunResult(FAILURE_STATUS, message))
            return
        self._results.put(_DemoRunResult(SUCCESS_STATUS, output))

    def _finish(self, status: str, output: str) -> None:
        self._set_state(DemoRunState(status, output, False))

    def _set_state(self, state: DemoRunState) -> None:
        self.state = state
        if self._on_state_change is not None:
            self._on_state_change(state)


class FuturesIntelligenceApp:
    """Small Tkinter view for running and copying the bounded demo."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._closed = False
        self._poll_after_id: str | None = None
        root.title("Futures Intelligence Assistant")
        root.geometry("900x700")
        root.minsize(640, 480)

        container = ttk.Frame(root, padding=18)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            text="期货研究情报助手",
            font=("TkDefaultFont", 20, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            container,
            text="Futures Intelligence Assistant",
            font=("TkDefaultFont", 11),
        ).pack(anchor=tk.W, pady=(0, 12))
        ttk.Label(container, text="华泰期货研报 Demo").pack(anchor=tk.W)

        controls = ttk.Frame(container)
        controls.pack(fill=tk.X, pady=(10, 8))
        self.run_button = ttk.Button(
            controls,
            text="运行 Demo",
            command=self._start_demo,
        )
        self.run_button.pack(side=tk.LEFT)
        self.status_variable = tk.StringVar(value=f"状态：{READY_STATUS}")
        ttk.Label(controls, textvariable=self.status_variable).pack(
            side=tk.LEFT, padx=(14, 0)
        )

        self.output = scrolledtext.ScrolledText(
            container,
            wrap=tk.WORD,
            font=tkfont.nametofont("TkFixedFont"),
            state=tk.DISABLED,
        )
        self.output.pack(fill=tk.BOTH, expand=True)

        actions = ttk.Frame(container)
        actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(actions, text="复制结果", command=self._copy_output).pack(
            side=tk.LEFT
        )
        ttk.Button(actions, text="清空", command=self._clear_output).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.controller = DemoRunController(
            on_state_change=self._render_state,
        )
        self._start_result_polling()

    def _start_demo(self) -> None:
        self.controller.start()

    def _copy_output(self) -> None:
        text = self.controller.state.output
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()

    def _clear_output(self) -> None:
        self.controller.clear_output()

    def _start_result_polling(self) -> None:
        """Install close handling and start main-thread result polling."""
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._schedule_result_poll()

    def _schedule_result_poll(self) -> None:
        if self._closed:
            return
        self._poll_after_id = self.root.after(
            _RESULT_POLL_INTERVAL_MS,
            self._poll_results,
        )

    def _poll_results(self) -> None:
        self._poll_after_id = None
        if self._closed:
            return
        self.controller.process_pending_results()
        self._schedule_result_poll()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.controller.close()
        poll_after_id = self._poll_after_id
        self._poll_after_id = None
        if poll_after_id is not None:
            try:
                self.root.after_cancel(poll_after_id)
            except tk.TclError:
                pass
        self.root.destroy()

    def _render_state(self, state: DemoRunState) -> None:
        self.status_variable.set(f"状态：{state.status}")
        self.run_button.configure(
            state=tk.DISABLED if state.is_running else tk.NORMAL
        )
        self.output.configure(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.insert("1.0", state.output)
        self.output.configure(state=tk.DISABLED)


def configure_gui_proxy_bypass() -> None:
    """Add Huatai hosts to empty GUI-process proxy bypass settings only."""
    bypass = "htfc.com,www.htfc.com"
    os.environ.setdefault("NO_PROXY", bypass)
    os.environ.setdefault("no_proxy", bypass)


def main() -> None:
    """Open the desktop launcher without starting network work."""
    configure_gui_proxy_bypass()
    root = tk.Tk()
    FuturesIntelligenceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
