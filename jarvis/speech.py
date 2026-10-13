import threading


class Speech:
    def __init__(self, config):
        self.config = config
        self.model = None
        self.frames = []
        self.stream = None
        self.lock = threading.Lock()

    def start(self):
        import sounddevice as sd
        self.frames = []
        def callback(data, count, timing, status):
            with self.lock:
                # Cap recordings to one minute.
                if sum(len(f) for f in self.frames) < 16000 * 60:
                    self.frames.append(data.copy())
        self.stream = sd.InputStream(samplerate=16000, channels=1, dtype='float32', callback=callback)
        self.stream.start()

    def close(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def transcribe(self):
        import numpy as np
        self.close()
        with self.lock:
            audio = np.concatenate(self.frames).flatten() if self.frames else np.array([], dtype=np.float32)
        if len(audio) < 3200 or float(np.max(np.abs(audio))) < 0.005:
            return ''
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.config['whisper_model'], device='cpu', compute_type='int8')
        segments, _ = self.model.transcribe(audio, language=self.config['language'],
                                           beam_size=5, vad_filter=True,
                                           condition_on_previous_text=False)
        return ' '.join(s.text.strip() for s in segments if s.no_speech_prob < 0.6)
