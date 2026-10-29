from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList,projects_root,video_file
from ..adapters.pyscenedetect import detect_cut_times
from ..core import energy
from ..core.fingerprints import file_fingerprint,short
from ..core.media_probe import probe
from ..core.paths import ProjectStore
from ..core.audio_quality import measure_true_peak


class MajoorEnergyReport(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='MajoorEnergyReport',display_name='Reference Energy Report',category='Majoor/VideoTools',is_output_node=True,
            inputs=[io.Video.Input('video'),MajoorShotList.Input('shot_list'),io.Video.Input('reference_video',optional=True)],outputs=[io.Boolean.Output(display_name="report_saved")])

    @classmethod
    def execute(cls,video,shot_list,reference_video=None):
        store=ProjectStore(projects_root(shot_list),shot_list.project_id)
        with video_file(video) as path:
            fingerprint=file_fingerprint(path)
            cache=f'cache/energy/{short(fingerprint,24)}-v2.json'
            result=store.read_json(cache)
            if result is None:
                info=probe(path,with_packets=True)
                frames=energy.read_gray(path,info.fps)
                events=energy.detect_events(energy.measure(frames))
                cuts=[round(t*float(info.fps)) for t in detect_cut_times(path,'adaptive',.5,3)]
                cuts=energy.clean_cuts(cuts,events,frames,[])
                result=energy.summarize_energy(events,cuts,float(info.duration))
                store.write_json(cache,result)
            audio=measure_true_peak(path) if probe(path,with_packets=False).has_audio else {'status':'no_audio'}
        report=energy.compare_energy(shot_list.detection.energy,result)
        if reference_video is not None:
            with video_file(reference_video) as reference_path:
                info=probe(reference_path,with_packets=True)
                frames=energy.read_gray(reference_path,info.fps)
                events=energy.detect_events(energy.measure(frames))
                cuts=[round(t*float(info.fps)) for t in detect_cut_times(reference_path,'adaptive',.5,3)]
                cuts=energy.clean_cuts(cuts,events,frames,[])
                report=energy.compare_energy(energy.summarize_energy(events,cuts,float(info.duration)),result)
                report['reference_fingerprint']=file_fingerprint(reference_path)
        report['audio']=audio
        report['result_fingerprint']=fingerprint
        store.write_json('exports/energy.json',report)
        return io.NodeOutput(True, ui={'text':[str(report)]})
