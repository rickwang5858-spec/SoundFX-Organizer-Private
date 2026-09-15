import subprocess, tempfile
from pathlib import Path

# Finite descriptive labels. These are candidate sounds, not unrestricted captions.
GROUPS={
 'Foley/Doors':['Door_Open','Door_Close','Door_Slam','Door_Knock'],
 'Foley/Footsteps':['Footsteps_Walking','Footsteps_Running'],
 'Foley/Objects':['Paper_Rustling','Glass_Breaking','Keys_Jingling','Coin_Dropping','Cloth_Rustling','Zipper','Typing_Keyboard'],
 'Nature/Weather':['Wind_Blowing','Rain_Falling','Thunder'],
 'Nature/Water':['Ocean_Waves','River_Flowing','Water_Splash','Water_Dripping','Underwater_Bubbling'],
 'Nature/Fire':['Fire_Crackling'],
 'Animals':['Dog_Barking','Cat_Meowing','Bird_Chirping','Horse_Neighing','Horse_Hooves','Insects_Buzzing','Frog_Croaking'],
 'People':['Crowd_Talking','Crowd_Cheering','Applause','Laughter','Crying','Screaming','Whispering','Breathing','Coughing','Baby_Crying'],
 'Vehicles':['Car_Engine','Car_Horn','Car_Braking','Bicycle_Riding','Bicycle_Bell','Motorcycle_Engine','Train_Passing','Airplane_Flying','Helicopter'],
 'Weapons':['Gunshot','Sword_Clashing','Arrow_Release','Explosion'],
 'Design':['Whoosh','Impact','Laser','Magic_Spell','Horror_Drone','Monster_Growl','Musical_Stinger'],
 'Objects':['Bell_Ringing','Clock_Ticking','Telephone_Ringing','Electronic_Beep','Machine_Humming','Projector_Running'],
 'Ambience':['City_Traffic','Forest_Ambience','Restaurant_Ambience'],
 'Other':['Music','Speech','Silence','Noise']}
LABELS=[(cat,label) for cat,labels in GROUPS.items() for label in labels]

class AudioAI:
    def __init__(self):
        import torch
        from transformers import ClapModel, ClapProcessor
        self.torch=torch; torch.set_num_threads(4)
        name='laion/clap-htsat-unfused'
        self.processor=ClapProcessor.from_pretrained(name)
        # Official checkpoint currently provides .bin; use tensor-only loading.
        from huggingface_hub import hf_hub_download
        from transformers import ClapConfig
        self.model=ClapModel(ClapConfig.from_pretrained(name))
        weights=hf_hub_download(name,'pytorch_model.bin')
        state=torch.load(weights,map_location='cpu',weights_only=True)
        self.model.load_state_dict(state,strict=True); self.model.eval()
        with torch.inference_mode():
            tokens=self.processor(text=['The sound of '+label.replace('_',' ').lower()+'.' for _,label in LABELS],return_tensors='pt',padding=True)
            self.text=self.model.get_text_features(**tokens)
            self.text=self.text/self.text.norm(dim=-1,keepdim=True)

    def analyze(self,path):
        import numpy as np
        import soundfile as sf
        from scipy.signal import resample_poly
        from math import gcd
        def extract(p):
            clips=[]
            with sf.SoundFile(str(p)) as f:
                sr=f.samplerate; duration=len(f)/sr
                for t in sorted(set([0,max(0,duration/2-5),max(0,duration-10)])):
                    f.seek(int(t*sr)); a=f.read(sr*10,dtype='float32',always_2d=True).mean(axis=1)
                    if len(a):
                        g=gcd(sr,48000); clips.append(resample_poly(a,48000//g,sr//g).astype('float32'))
            return clips,duration
        try: clips,duration=extract(path)
        except Exception:
            with tempfile.TemporaryDirectory() as td:
                out=Path(td)/'decoded.wav'
                subprocess.run(['/usr/bin/afconvert','-f','WAVE','-d','LEI16',str(path),str(out)],capture_output=True,check=True,timeout=300)
                clips,duration=extract(out)
        if not clips: raise ValueError('空音檔')
        scores=[]
        with self.torch.inference_mode():
            for a in clips:
                inp=self.processor(audios=a,sampling_rate=48000,return_tensors='pt')
                device=next(self.model.parameters()).device
                inp={k:v.to(device) for k,v in inp.items()}
                feat=self.model.get_audio_features(**inp); feat=feat/feat.norm(dim=-1,keepdim=True)
                scores.append((feat@self.text.T).squeeze().cpu().numpy())
        avg=np.mean(scores,axis=0); order=avg.argsort()[::-1]; best=int(order[0]); score=float(avg[best]); margin=score-float(avg[order[1]])
        # Conservative heuristics; similarity is NOT a calibrated confidence probability.
        accepted=score>=0.30 and margin>=0.035 and all(int(s.argmax())==best for s in scores)
        cat,label=LABELS[best]
        return {'cat':cat if accepted else '_待確認','label':label if accepted else 'NeedsReview',
                'suggested':label,'score':score,'margin':margin,'duration':duration,'accepted':accepted}
