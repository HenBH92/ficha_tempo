"""Bootstrap hooks run before application imports and never auto-install."""
import ast
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import Mock, patch

import inicializacao


class InicializacaoTests(unittest.TestCase):
    def test_development_does_not_initialize_velopack(self):
        sdk = Mock()
        with patch.object(sys, "frozen", False, create=True), patch.dict(sys.modules, velopack=sdk):
            inicializacao.iniciar_velopack()
        sdk.App.assert_not_called()

    def test_frozen_bootstrap_disables_automatic_apply_before_running_hooks(self):
        sdk = Mock()
        events = []
        app = sdk.App.return_value
        app.set_auto_apply_on_startup.side_effect = lambda enabled: (events.append(("auto_apply", enabled)), app)[1]
        app.run.side_effect = lambda: events.append(("run",))
        with patch.object(sys, "frozen", True, create=True), patch.dict(sys.modules, velopack=sdk):
            inicializacao.iniciar_velopack()
        sdk.App.assert_called_once_with()
        self.assertEqual(events, [("auto_apply", False), ("run",)])

    def test_entry_point_runs_hooks_before_importing_interface_or_state(self):
        root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent('''
            import builtins
            import runpy
            import sys
            from types import SimpleNamespace
            events = []
            class HookFinished(Exception):
                pass
            class App:
                def set_auto_apply_on_startup(self, value):
                    events.append(("auto_apply", value))
                    return self
                def run(self):
                    events.append(("run",))
                    raise HookFinished()
            sys.frozen = True
            sys.modules["velopack"] = SimpleNamespace(App=App)
            original_import = builtins.__import__
            def guarded_import(name, *args, **kwargs):
                assert name not in {"customtkinter", "tkinter", "estado", "advwin", "caminhos"}, name
                return original_import(name, *args, **kwargs)
            builtins.__import__ = guarded_import
            try:
                runpy.run_path("main.py", run_name="__main__")
            except HookFinished:
                pass
            else:
                raise AssertionError("Installer hooks were not invoked")
            assert events == [("auto_apply", False), ("run",)], events
        ''')
        result = subprocess.run([sys.executable, "-c", script], cwd=root, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
