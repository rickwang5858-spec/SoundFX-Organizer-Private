import os,sys,json,platform
from pathlib import Path
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['OMP_NUM_THREADS']='2'
os.environ['MKL_NUM_THREADS']='2'
from audio_ai import AudioAI
def send(o): print(json.dumps(o,ensure_ascii=False),flush=True)
if __name__=='__main__':
    try:
        try: os.nice(10)
        except OSError: pass
        ai=AudioAI()
        ai.torch.set_num_threads(2)
        # Opt-in MPS acceleration; CPU remains default for interactive editing sessions.
        if '--accelerated' in sys.argv and ai.torch.backends.mps.is_available():
            ai.model.to('mps'); ai.text=ai.text.to('mps')
        send({'ready':True})
        for line in sys.stdin:
            try:
                p=Path(json.loads(line)['path'])
                try: r=ai.analyze(p)
                except RuntimeError:
                    ai.model.to('cpu'); ai.text=ai.text.to('cpu'); r=ai.analyze(p)
                send({'result':r})
            except Exception as e: send({'error':str(e)})
    except Exception as e: send({'error':str(e)})
