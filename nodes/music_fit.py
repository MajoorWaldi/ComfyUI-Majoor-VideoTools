import json

import torch
from comfy_api.latest import io

from ..core.music_fit import fit_music


class MajoorMusicFit(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorMusicFit",
            display_name="Music Fit",
            category="Majoor/VideoTools",
            description="Cut a long music to the length of the edit, on its bars: the window starts on a downbeat, on the strongest part (a drop) unless you give a start, "
                        "and a music that is too short is looped by whole bars. Generate a minute or two with ACE-Step, then fit it here before Create Timeline.",
            inputs=[
                io.Audio.Input("music"),
                io.Float.Input("length", default=8.0, min=0.1, max=600.0, step=0.01, tooltip="Seconds of the edit."),
                io.Float.Input("bpm", default=0.0, min=0.0, max=300.0, step=0.1, tooltip="0 detects the tempo; give the BPM the music was made with to skip the detection."),
                io.Float.Input("start", default=-1.0, min=-1.0, max=3600.0, step=0.01, tooltip="-1 picks the strongest window. Otherwise the window starts on the bar closest to this time (seconds)."),
                io.Combo.Input('energy_goal',options=['peak','calm','balanced','intense'],default='peak',optional=True),
                io.String.Input('moments_json',default='[]',multiline=True,optional=True),
            ],
            outputs=[io.Audio.Output(display_name="music"), io.String.Output(display_name="info", tooltip="The tempo, the start that was chosen, the number of bars, and whether the music was looped (JSON).")],
        )

    @classmethod
    def execute(cls, music, length, bpm, start,energy_goal='peak',moments_json='[]') -> io.NodeOutput:
        waveform = music["waveform"][0].detach().cpu().float().numpy().T
        fitted, info = fit_music(waveform, int(music["sample_rate"]), length, bpm=bpm, start=start,energy_goal=energy_goal,moments=json.loads(moments_json))
        out = torch.from_numpy(fitted.T.copy()).unsqueeze(0)
        return io.NodeOutput({"waveform": out, "sample_rate": int(music["sample_rate"])}, json.dumps(info))
