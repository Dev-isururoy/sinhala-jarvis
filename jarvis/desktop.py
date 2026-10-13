import os
import subprocess
import time
import webbrowser
from pathlib import Path

from .core import validate


class Desktop:
    def __init__(self):
        import pyautogui
        self.pg = pyautogui
        self.pg.FAILSAFE = True
        self.pg.PAUSE = 0.2
        self.elements = []
        self.hwnd = None

    def observe(self):
        import win32gui
        self.hwnd = win32gui.GetForegroundWindow()
        image = self.pg.screenshot()
        self.size = image.size
        image.thumbnail((1440, 1000))
        self.elements = []
        descriptions = []
        try:
            from pywinauto import Desktop as UIA
            window = UIA(backend='uia').window(handle=self.hwnd)
            for element in window.descendants()[:400]:
                if len(self.elements) >= 80:
                    break
                name = element.window_text()[:180]
                if name and element.is_visible() and element.is_enabled():
                    rect = element.rectangle()
                    if 0 <= rect.left < rect.right <= self.size[0] and 0 <= rect.top < rect.bottom <= self.size[1]:
                        descriptions.append({'id': len(self.elements), 'name': name,
                                             'type': element.element_info.control_type})
                        self.elements.append(element)
        except Exception as exc:
            descriptions = [{'uia_unavailable': type(exc).__name__}]
        return {'image': image, 'description': {
            'window': win32gui.GetWindowText(self.hwnd), 'primary_screen_size': self.size,
            'elements': descriptions}}

    def execute(self, action, stop):
        validate(action)
        if stop.is_set():
            return 'Stopped'
        kind, args = action['kind'], action['args']
        if kind in ('click', 'double_click', 'right_click', 'move', 'drag', 'scroll', 'type_text', 'hotkey', 'click_element'):
            import win32gui
            if not win32gui.IsWindow(self.hwnd):
                raise RuntimeError('Target window closed. Start again.')
            win32gui.SetForegroundWindow(self.hwnd)
            if stop.wait(0.4):
                return 'Stopped'
            if win32gui.GetForegroundWindow() != self.hwnd:
                raise RuntimeError('Could not focus target window; action cancelled.')
            if tuple(self.pg.size()) != self.size:
                raise RuntimeError('Display size changed; restart the task.')
        if 'x' in args:
            x = round(args['x'] * (self.size[0] - 1) / 1000)
            y = round(args['y'] * (self.size[1] - 1) / 1000)
            if kind == 'click': self.pg.click(x, y)
            elif kind == 'double_click': self.pg.doubleClick(x, y, interval=0.15)
            elif kind == 'right_click': self.pg.click(x, y, button='right')
            elif kind == 'move': self.pg.moveTo(x, y, duration=0.3)
            elif kind == 'drag': self.pg.dragTo(x, y, duration=0.8)
        elif kind == 'click_element':
            if args['id'] >= len(self.elements):
                raise ValueError('Unknown element')
            element = self.elements[args['id']]
            if not element.is_visible() or not element.is_enabled():
                raise RuntimeError('Element changed; restart task')
            element.click_input()
        elif kind == 'scroll': self.pg.scroll(args['amount'])
        elif kind == 'hotkey': self.pg.hotkey(*args['keys'])
        elif kind == 'type_text':
            import pyperclip
            previous = pyperclip.paste()
            try:
                pyperclip.copy(args['text'])
                self.pg.hotkey('ctrl', 'v')
                stop.wait(0.4)
            finally:
                if pyperclip.paste() == args['text']:
                    pyperclip.copy(previous)
        elif kind == 'wait': stop.wait(args['seconds'])
        elif kind == 'open_app':
            app = {'notepad': 'notepad.exe', 'calculator': 'calc.exe',
                   'explorer': 'explorer.exe', 'paint': 'mspaint.exe'}[args['name']]
            subprocess.Popen([str(Path(os.environ['WINDIR']) / 'System32' / app)])
        elif kind == 'open_url': webbrowser.open(args['url'])
        elif kind == 'list_files':
            import itertools
            return '\n'.join(str(p) for p in itertools.islice(Path(args['path']).iterdir(), 200))
        elif kind == 'read_file':
            with Path(args['path']).open(encoding='utf-8') as stream:
                return stream.read(8000)
        elif kind == 'write_file':
            Path(args['path']).write_text(args['text'], encoding='utf-8')
        elif kind == 'powershell':
            return self.shell(args['command'], stop)
        return 'Action executed; verify using the next observation.'

    @staticmethod
    def shell(command, stop):
        import tempfile
        # A file prevents pipe deadlock for verbose commands. Bound process lifetime.
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive',
                                        '-Command', command], stdout=output, stderr=output,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 30
            while process.poll() is None:
                if stop.wait(0.1) or time.monotonic() > deadline:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    process.wait(timeout=5)
                    return 'Command interrupted. Prior side effects may have occurred.'
            output.seek(0)
            return f'Exit {process.returncode}: ' + output.read(16000).decode('utf-8', errors='replace')
