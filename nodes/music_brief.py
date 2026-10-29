from comfy_api.latest import io

from ..core.music_brief import read_brief


class MajoorMusicBrief(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorMusicBrief",
            display_name="Music Brief",
            category="Majoor/VideoTools",
            description="Read the JSON of a music_brief skill: the style, the tempo, the length and, for a song model such as YuE2, the lyrics cut to the length of the edit.",
            inputs=[
                io.String.Input("brief_json", force_input=True, tooltip="The answer of the LLM to the music_brief_from_plan or music_brief_yue2 skill."),
                io.Float.Input("bpm", default=0.0, min=0.0, max=300.0, step=1.0, tooltip="0: the tempo of the brief. Otherwise it replaces it. Give the same tempo to Create Timeline."),
                io.Float.Input("duration", default=0.0, min=0.0, max=600.0, step=0.1, tooltip="0: the length of the brief. Otherwise it replaces it: set the length of the edit."),
                io.Boolean.Input("steady_beat", default=True, tooltip="Add tags that ask for a constant tempo and a kick on every beat, which cuts need."),
            ],
            outputs=[
                io.String.Output(display_name="music_prompt"),
                io.Int.Output(display_name="bpm"),
                io.Float.Output(display_name="duration"),
                io.String.Output(display_name="sfx_json"),
                io.String.Output(display_name="lyrics", tooltip="The lyrics of the brief, cut to the lines that a song of this length needs. Empty when the brief has none."),
            ],
        )

    @classmethod
    def execute(cls, brief_json, bpm, duration, steady_beat) -> io.NodeOutput:
        prompt, tempo, seconds, sfx, lyrics = read_brief(brief_json, bpm, duration, steady_beat)
        return io.NodeOutput(prompt, tempo, seconds, sfx, lyrics, ui={"text": (f"{tempo} BPM · {seconds:g} s\n{prompt}" + (f"\n\n{lyrics}" if lyrics else ""),)})
