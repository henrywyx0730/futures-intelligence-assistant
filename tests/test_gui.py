"""Tests for the thin, headless-testable desktop demo controller."""

from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import Mock, patch


class _FakeRoot:
    """Record Tk scheduling calls without creating a display-backed window."""

    def __init__(self) -> None:
        self.after_callbacks: list[object] = []
        self.after_delays: list[int] = []
        self.cancelled_callbacks: list[str] = []
        self.protocols: dict[str, object] = {}
        self.destroyed = False

    def after(self, delay_ms: int, callback: object) -> str:
        self.after_delays.append(delay_ms)
        self.after_callbacks.append(callback)
        return f"after-{len(self.after_callbacks)}"

    def after_cancel(self, callback_id: str) -> None:
        self.cancelled_callbacks.append(callback_id)

    def protocol(self, name: str, callback: object) -> None:
        self.protocols[name] = callback

    def destroy(self) -> None:
        self.destroyed = True


class DemoRunControllerTests(unittest.TestCase):
    """Exercise GUI execution state without creating a Tk window."""

    def test_import_and_controller_construction_do_not_acquire_huatai_reports(
        self,
    ) -> None:
        import futures_intelligence.main as main_module

        with patch.object(
            main_module,
            "_collect_commodity_focused_htfc_demo_information",
            side_effect=AssertionError("GUI startup must not access Huatai"),
        ) as acquisition:
            gui_module = importlib.import_module("futures_intelligence.gui")
            gui_module = importlib.reload(gui_module)
            controller = gui_module.DemoRunController()

        acquisition.assert_not_called()
        self.assertFalse(controller.state.is_running)
        self.assertEqual(controller.state.status, "准备就绪")
        self.assertEqual(controller.state.output, "")

    def test_success_runs_shared_orchestration_once_via_queued_completion(
        self,
    ) -> None:
        from futures_intelligence import gui as gui_module

        workers: list[object] = []
        states: list[object] = []
        with patch.object(
            gui_module,
            "run_htfc_demo",
            return_value="formatted demo output",
        ) as shared_demo:
            controller = gui_module.DemoRunController(
                start_worker=workers.append,
                on_state_change=states.append,
            )

            self.assertTrue(controller.start())
            self.assertFalse(controller.start())
            self.assertTrue(controller.state.is_running)
            self.assertEqual(controller.state.status, "正在获取并分析华泰研报…")
            self.assertEqual(len(workers), 1)
            shared_demo.assert_not_called()

            workers[0]()

            shared_demo.assert_called_once_with()
            self.assertTrue(controller.state.is_running)
            self.assertTrue(controller.process_pending_results())

        self.assertFalse(controller.state.is_running)
        self.assertEqual(controller.state.status, "完成")
        self.assertEqual(controller.state.output, "formatted demo output")
        self.assertEqual(states[-1], controller.state)

    def test_failure_is_concise_and_reenables_run(self) -> None:
        from futures_intelligence import gui as gui_module

        workers: list[object] = []
        controller = gui_module.DemoRunController(
            run_demo=Mock(side_effect=TimeoutError("timed out")),
            start_worker=workers.append,
        )

        self.assertTrue(controller.start())
        workers[0]()
        self.assertTrue(controller.process_pending_results())

        self.assertFalse(controller.state.is_running)
        self.assertEqual(controller.state.status, "运行失败")
        self.assertEqual(controller.state.output, "Demo 运行失败\ntimed out")
        self.assertNotIn("Traceback", controller.state.output)

    def test_clear_only_changes_visible_output(self) -> None:
        from futures_intelligence import gui as gui_module

        workers: list[object] = []
        controller = gui_module.DemoRunController(
            run_demo=lambda: "result",
            start_worker=workers.append,
        )
        controller.start()
        workers[0]()
        controller.process_pending_results()

        controller.clear_output()

        self.assertEqual(controller.state.status, "完成")
        self.assertEqual(controller.state.output, "")
        self.assertFalse(controller.state.is_running)

    def test_worker_completion_after_close_only_enqueues_without_ui_dispatch(
        self,
    ) -> None:
        from futures_intelligence import gui as gui_module

        workers: list[object] = []
        states: list[object] = []
        controller = gui_module.DemoRunController(
            run_demo=lambda: "late result",
            start_worker=workers.append,
            on_state_change=states.append,
        )
        controller.start()
        controller.close()

        workers[0]()

        self.assertTrue(controller.closed)
        self.assertFalse(controller.process_pending_results())
        self.assertEqual(controller.state.status, "正在获取并分析华泰研报…")
        self.assertEqual(controller.state.output, "")
        self.assertFalse(controller.start())
        self.assertEqual(len(states), 1)

    def test_main_thread_poller_stops_and_cancels_on_window_close(self) -> None:
        from futures_intelligence import gui as gui_module

        root = _FakeRoot()
        controller = Mock()
        app = gui_module.FuturesIntelligenceApp.__new__(
            gui_module.FuturesIntelligenceApp
        )
        app.root = root
        app.controller = controller
        app._closed = False
        app._poll_after_id = None

        app._start_result_polling()

        self.assertEqual(len(root.after_callbacks), 1)
        self.assertEqual(root.after_delays, [75])
        self.assertEqual(app._poll_after_id, "after-1")
        close_callback = root.protocols["WM_DELETE_WINDOW"]
        poll_callback = root.after_callbacks[0]
        poll_callback()
        controller.process_pending_results.assert_called_once_with()
        self.assertEqual(len(root.after_callbacks), 2)

        close_callback()

        controller.close.assert_called_once_with()
        self.assertTrue(root.destroyed)
        self.assertEqual(root.cancelled_callbacks, ["after-2"])
        self.assertIsNone(app._poll_after_id)

        poll_callback()
        controller.process_pending_results.assert_called_once_with()
        self.assertEqual(len(root.after_callbacks), 2)

    def test_proxy_defaults_are_narrow_and_preserve_existing_values(self) -> None:
        from futures_intelligence import gui as gui_module

        with patch.dict(os.environ, {}, clear=True):
            gui_module.configure_gui_proxy_bypass()
            self.assertEqual(os.environ["NO_PROXY"], "htfc.com,www.htfc.com")
            self.assertEqual(os.environ["no_proxy"], "htfc.com,www.htfc.com")

        with patch.dict(
            os.environ,
            {"NO_PROXY": "internal.example", "no_proxy": "local.example"},
            clear=True,
        ):
            gui_module.configure_gui_proxy_bypass()
            self.assertEqual(os.environ["NO_PROXY"], "internal.example")
            self.assertEqual(os.environ["no_proxy"], "local.example")


if __name__ == "__main__":
    unittest.main()
