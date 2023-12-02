class TTS:
    def get_voices(self):
        raise NotImplementedError()

    def generate(self, text: str, voice: str, file: str):
        raise NotImplementedError()