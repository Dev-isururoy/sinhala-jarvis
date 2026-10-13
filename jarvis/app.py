import ctypes
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from .core import ROOT, LocalModel, run_loop
from .desktop import Desktop
from .speech import Speech


class App:
    def __init__(self, root):
        self.root = root
        self.config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
        self.stop = threading.Event()
        self.events = queue.Queue()
        self.busy = False
        self.recording = False
        self.approval = None
        self.speech = Speech(self.config)
        root.title('Jarvis • සිංහල Local AI')
        root.geometry('900x720')
        root.minsize(740, 560)
        root.configure(bg='#101827')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#101827')
        style.configure('TLabel', background='#101827', foreground='#e5edf8', font=('Nirmala UI', 11))
        style.configure('TButton', font=('Nirmala UI', 11), padding=8)
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='JARVIS  /  සිංහල', font=('Nirmala UI', 23, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Local AI • Voice + screen + mouse + keyboard').pack(anchor='w', pady=(0, 12))
        ttk.Label(frame, text='ඔබට කිරීමට අවශ්‍ය දේ ලියන්න හෝ කතා කරන්න:').pack(anchor='w')
        self.input = scrolledtext.ScrolledText(frame, height=5, font=('Nirmala UI', 12), wrap='word')
        self.input.pack(fill='x', pady=8)
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        self.mic = ttk.Button(buttons, text='🎤 කතා කරන්න', command=self.record)
        self.mic.pack(side='left')
        self.run_button = ttk.Button(buttons, text='▶ ආරම්භ කරන්න', command=self.start)
        self.run_button.pack(side='left', padx=8)
        ttk.Button(buttons, text='■ නවත්වන්න (Esc)', command=self.cancel).pack(side='left')
        self.check_button = ttk.Button(buttons, text='සම්බන්ධතාව පරීක්ෂා කරන්න', command=self.check)
        self.check_button.pack(side='right')
        self.status = tk.StringVar(value='සූදානම්. හඬ පෙළ පරීක්ෂා කර ආරම්භ කරන්න.')
        ttk.Label(frame, textvariable=self.status, wraplength=820).pack(fill='x', pady=12)
        self.log = scrolledtext.ScrolledText(frame, height=14, font=('Nirmala UI', 11),
                                           bg='#1b283c', fg='#e5edf8', wrap='word', state='disabled')
        self.log.pack(fill='both', expand=True)
        ttk.Label(frame, text='සෑම ක්‍රියාවක්ම ඔබ අනුමත කළ පසු ක්‍රියාත්මක වේ.\n'
                  'හදිසි Stop: Esc හෝ mouse එක ප්‍රධාන තිරයේ කොනකට ගෙන යන්න.',
                  wraplength=820).pack(anchor='w', pady=(12, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Escape>', lambda e: self.cancel())
        from pynput import keyboard
        self.listener = keyboard.Listener(on_press=lambda key: self.stop.set() if key == keyboard.Key.esc else None)
        self.listener.start()
        root.after(100, self.poll)

    def write(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def set_busy(self, value):
        self.busy = value
        for button in (self.run_button, self.mic, self.check_button):
            button.configure(state='disabled' if value else 'normal')

    def check(self):
        if self.busy or self.recording: return
        self.set_busy(True)
        def work():
            try:
                LocalModel(self.config).health()
                self.events.put(('finish', 'Local model සූදානම්: ' + self.config['model']))
            except Exception as exc:
                self.events.put(('finish', 'Ollama/model සූදානම් නැත: ' + str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def record(self):
        if self.busy: return
        if not self.recording:
            try:
                self.speech.start()
                self.recording = True
                self.mic.configure(text='■ හඬ අවසන් කරන්න')
                self.run_button.configure(state='disabled')
                self.check_button.configure(state='disabled')
                self.status.set('කතා කරන්න… උපරිම තත්පර 60.')
                self.record_timer = self.root.after(60000, self.record)
            except Exception as exc:
                self.write('Microphone: ' + str(exc))
        else:
            self.root.after_cancel(self.record_timer)
            self.recording = False
            self.mic.configure(text='🎤 කතා කරන්න')
            self.set_busy(True)
            self.status.set('හඬ පෙළට පරිවර්තනය කරමින්… පළමු වර model download විය හැක.')
            def work():
                try: self.events.put(('transcript', self.speech.transcribe()))
                except Exception as exc: self.events.put(('finish', 'Speech error: ' + str(exc)))
            threading.Thread(target=work, daemon=True).start()

    def start(self):
        task = self.input.get('1.0', 'end').strip()
        if self.busy or self.recording or not task: return
        self.set_busy(True)
        self.stop.clear()
        self.write('ඔබ: ' + task)
        self.status.set('වැඩ කරමින්… Esc මඟින් නවත්වන්න.')
        self.root.iconify()
        self.root.after(800, lambda: threading.Thread(target=self.work, args=(task,), daemon=True).start())

    def work(self, task):
        try:
            model = LocalModel(self.config)
            model.health()
            result = run_loop(task, model, Desktop(), self.approve,
                              lambda text: self.events.put(('log', text)), self.stop,
                              self.config['max_steps'])
        except Exception as exc:
            result = 'ක්‍රියාව නතර විය: ' + str(exc)
        self.events.put(('finish', result))

    def approve(self, action):
        request = {'action': action, 'event': threading.Event(), 'approved': False}
        self.events.put(('approve', request))
        while not request['event'].wait(0.1):
            if self.stop.is_set(): return False
        return request['approved'] and not self.stop.is_set()

    def show_approval(self, request):
        if self.stop.is_set():
            request['event'].set()
            return
        self.approval = request
        dialog = tk.Toplevel(self.root)
        self.dialog = dialog
        dialog.title('ක්‍රියාව පරීක්ෂා කරන්න / Review action')
        dialog.geometry('760x500')
        dialog.attributes('-topmost', True)
        ttk.Label(dialog, text=request['action']['reason'], wraplength=720, padding=16).pack(fill='x')
        preview = scrolledtext.ScrolledText(dialog, font=('Nirmala UI', 11), wrap='word')
        preview.pack(fill='both', expand=True, padx=16)
        preview.insert('1.0', json.dumps(request['action'], ensure_ascii=False, indent=2))
        preview.configure(state='disabled')
        row = ttk.Frame(dialog, padding=16)
        row.pack(fill='x')
        def resolve(approved):
            dialog.destroy()
            self.approval = None
            request['approved'] = approved
            # Allow the review window to disappear before returning target focus.
            self.root.after(300, request['event'].set)
        ttk.Button(row, text='අනුමත කර ක්‍රියාත්මක කරන්න', command=lambda: resolve(True)).pack(side='left')
        ttk.Button(row, text='අවලංගු කරන්න', command=lambda: resolve(False)).pack(side='right')
        dialog.protocol('WM_DELETE_WINDOW', lambda: resolve(False))
        dialog.bind('<Escape>', lambda e: self.cancel())
        dialog.lift()
        dialog.focus_force()

    def poll(self):
        if self.stop.is_set() and self.approval:
            self.dialog.destroy()
            self.approval['event'].set()
            self.approval = None
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'log': self.write(value)
                elif kind == 'approve': self.show_approval(value)
                elif kind == 'transcript':
                    self.set_busy(False)
                    self.input.delete('1.0', 'end')
                    self.input.insert('1.0', value)
                    self.status.set('පෙළ පරීක්ෂා කර ආරම්භ කරන්න.' if value else 'හඬ හඳුනාගත නොහැකි විය. නැවත උත්සාහ කරන්න.')
                elif kind == 'finish':
                    self.set_busy(False)
                    self.root.deiconify()
                    self.status.set('සූදානම්')
                    self.write(value)
        except queue.Empty: pass
        self.root.after(100, self.poll)

    def cancel(self):
        self.stop.set()
        if self.recording:
            self.root.after_cancel(self.record_timer)
            self.speech.close()
            self.recording = False
            self.mic.configure(text='🎤 කතා කරන්න')
            self.set_busy(False)
        self.status.set('නවත්වමින්… දැනට ක්‍රියාත්මක model request එක අවසන් වීමට කාලයක් ගත විය හැක.')

    def close(self):
        self.stop.set()
        self.speech.close()
        self.listener.stop()
        self.root.destroy()


def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__': main()
