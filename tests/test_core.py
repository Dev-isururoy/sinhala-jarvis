import threading
import unittest
from unittest.mock import Mock
from jsonschema import ValidationError
from jarvis.core import validate, run_loop


class SafetyTests(unittest.TestCase):
    def test_reject_malformed_actions(self):
        for action in [
            {'kind': 'click', 'reason': '', 'args': {'x': -1, 'y': 5}},
            {'kind': 'click', 'reason': '', 'args': {'x': True, 'y': 5}},
            {'kind': 'powershell', 'reason': '', 'args': {'command': 123}},
            {'kind': 'hotkey', 'reason': '', 'args': {'keys': ['ctrl', 'invented']}},
            {'kind': 'open_url', 'reason': '', 'args': {'url': 'file:///C:/Windows'}},
            {'kind': 'write_file', 'reason': '', 'args': {'path': '../foo', 'text': 'a'}},
            {'kind': 'wait', 'reason': '', 'args': {'seconds': 100}},
        ]:
            with self.subTest(action=action), self.assertRaises((ValueError, ValidationError)): validate(action)

    def test_unicode(self):
        action = {'kind': 'type_text', 'reason': 'ලියන්න', 'args': {'text': 'ආයුබෝවන්'}}
        self.assertEqual(validate(action), action)

    def test_denial_never_executes(self):
        model, desktop = Mock(), Mock()
        model.plan.return_value = {'kind': 'click', 'reason': '', 'args': {'x': 5, 'y': 5}}
        run_loop('task', model, desktop, lambda a: False, lambda t: None, threading.Event())
        desktop.execute.assert_not_called()

    def test_stop_during_inference_never_executes(self):
        model, desktop, stop = Mock(), Mock(), threading.Event()
        def plan(*args):
            stop.set()
            return {'kind': 'click', 'reason': '', 'args': {'x': 5, 'y': 5}}
        model.plan.side_effect = plan
        approve = Mock()
        run_loop('task', model, desktop, approve, lambda t: None, stop)
        desktop.execute.assert_not_called()
        approve.assert_not_called()

    def test_new_observation_after_action(self):
        model, desktop = Mock(), Mock()
        model.plan.side_effect = [
            {'kind': 'wait', 'reason': '', 'args': {'seconds': 0}},
            {'kind': 'done', 'reason': 'Done', 'args': {}},
        ]
        self.assertEqual(run_loop('task', model, desktop, lambda a: True, lambda t: None,
                                  threading.Event()), 'Done')
        self.assertEqual(desktop.observe.call_count, 2)
        desktop.execute.assert_called_once()


if __name__ == '__main__': unittest.main()
