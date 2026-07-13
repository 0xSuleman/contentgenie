import asyncio
import os

import edge_tts

from contentgenie.audio.voice_module import VoiceModule


class EdgeTTSVoiceModule(VoiceModule):
    def __init__(self, voiceName, rate="+10%", pitch="+3Hz", volume="+20%"):
        self.voiceName = voiceName
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        super().__init__()

    def update_usage(self):
        return None

    def get_remaining_characters(self):
        return 999999999999

    def generate_voice(self, text, outputfile):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self.async_generate_voice(text, outputfile))
        finally:
            loop.close()
        if not os.path.exists(outputfile):
            print("An error happened during edge_tts audio generation, no output audio generated")
            raise Exception("An error happened during edge_tts audio generation, no output audio generated")
        return outputfile

    async def async_generate_voice(self, text, outputfile):
        try:
            communicate = edge_tts.Communicate(
                text,
                self.voiceName,
                rate=self.rate,
                pitch=self.pitch,
                volume=self.volume,
            )
            with open(outputfile, "wb") as file:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        file.write(chunk["data"])
        except Exception as e:
            print("Error generating audio using edge_tts", e)
            raise Exception("An error happened during edge_tts audio generation, no output audio generated", e)
        return outputfile
