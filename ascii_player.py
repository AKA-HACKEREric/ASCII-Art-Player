#!/usr/bin/env python3
"""ASCII Art Player v6 — Settings panel + Shortcuts UI + Color Grading"""

import os, queue, subprocess, threading, time, types, urllib.parse, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    import cv2
except ImportError:
    cv2=None

try:
    import tkinter as tk
    from tkinter import colorchooser, filedialog, ttk
except ImportError as exc:
    raise SystemExit(f"tkinter is required: {exc}")

try:
    # tkinterdnd2 0.5.0 still imports tkinter.tix, which is gone in
    # newer Python builds. The app only needs TkinterDnD.Tk, so this
    # lightweight shim keeps drag-and-drop working on Python 3.14+.
    if not hasattr(tk, "tix"):
        tk.tix = types.SimpleNamespace(Tk=tk.Tk)
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    HAS_DND = False

CHARS    = "abcdefghijklmopqstuvwxyzABCDEFGHIJKLMOPQRSTUVWXYZ .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$23456789ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄐㄑㄒㄓㄔㄕㄖㄗㄘㄙㄚㄛㄜㄝㄞㄟㄠㄡㄢㄣㄤㄥㄦㄧㄨㄩㄪㄫㄬㄭㄮㄯ㄰ㄱㄲㄳㄴㄵㄶㄷㄸㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅃㅄㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎあいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんアイウエオカキクケコサシセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンがぎぐげござじずぜぞだぢづでどばびぶべぼ"
BG_COLOR = np.array([13,13,13], dtype=np.float32)
BG_HEX   = "#0d0d0d"
_NWIN    = getattr(subprocess, "CREATE_NO_WINDOW", 0)

try:
    RESAMPLE_BILINEAR = Image.Resampling.BILINEAR
    RESAMPLE_NEAREST = Image.Resampling.NEAREST
except AttributeError:
    RESAMPLE_BILINEAR = Image.BILINEAR
    RESAMPLE_NEAREST = Image.NEAREST

IMAGE_EXTS = {".jpg",".jpeg",".png",".bmp",".gif",".webp",".tiff",".tif",".ico"}
VIDEO_EXTS = {".mp4",".mkv",".avi",".mov",".wmv",".flv",".webm",".m4v",".mpeg",".mpg"}
AUDIO_EXTS = {".mp3",".wav",".flac",".m4a",".aac",".ogg",".opus",".wma",".alac"}

SHORTCUTS = [
    (None,        "Playback"),
    ("Space / k", "Play / Pause"),
    ("j",         "Seek back 10 s"),
    ("l",         "Seek forward 10 s"),
    ("← / →",    "Seek back / forward 5 s"),
    (", / .",     "Step frame while paused"),
    ("< / >",     "Speed ±0.25×"),
    ("0 ~ 9",     "Jump to 0 % ~ 90 %"),
    ("m",         "Toggle mute"),
    (None,        "Window"),
    ("f / F11",   "Toggle fullscreen"),
    ("Esc",       "Exit fullscreen"),
]

# ── ffplay ────────────────────────────────────────────────────────────────────
def _has_ffplay():
    try:
        subprocess.run(["ffplay","-version"],capture_output=True,
                       timeout=2,creationflags=_NWIN); return True
    except: return False

def _has_ffmpeg():
    try:
        subprocess.run(["ffmpeg","-version"],capture_output=True,
                       timeout=2,creationflags=_NWIN); return True
    except: return False

HAS_FFPLAY = _has_ffplay()
HAS_FFMPEG = _has_ffmpeg()

def _probe_duration(path):
    if not HAS_FFMPEG:
        return None
    try:
        r=subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1",path],
            capture_output=True,text=True,timeout=5,creationflags=_NWIN)
        duration=float((r.stdout or "").strip())
        return duration if duration>0 else None
    except Exception:
        return None

def _atempo_filter(speed):
    speed=max(0.25,min(4.0,float(speed or 1.0)))
    if abs(speed-1.0)<0.01:
        return None
    parts=[]
    while speed<0.5:
        parts.append("atempo=0.5")
        speed/=0.5
    while speed>2.0:
        parts.append("atempo=2.0")
        speed/=2.0
    parts.append(f"atempo={speed:.6g}")
    return ",".join(parts)

class Audio:
    def __init__(self,path):
        self._path=path; self._proc=None; self._lock=threading.Lock()
    def _stop_locked(self):
        proc,self._proc=self._proc,None
        if proc:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try: proc.wait(timeout=0.35)
                    except subprocess.TimeoutExpired: proc.kill()
            except: pass
    def play(self,t=0.0,speed=1.0):
        if not HAS_FFPLAY: return
        cmd=["ffplay","-nodisp","-autoexit","-hide_banner",
             "-vn","-ss",f"{max(0.0,t):.3f}"]
        af=_atempo_filter(speed)
        if af:
            cmd.extend(["-af",af])
        cmd.append(self._path)
        with self._lock:
            self._stop_locked()
            try:
                self._proc=subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=_NWIN)
            except: pass
    def stop(self):
        with self._lock:
            self._stop_locked()

class AudioWaveform:
    def __init__(self,path,width=140,height=72,fps=20):
        self._path=path
        self._width=max(48,int(width))
        self._height=max(24,int(height))
        self._fps=max(8,int(fps))
        self._sample_rate=22050
        self._chunk_samples=max(1,self._sample_rate//self._fps)
        self._frames=[]
        self._lock=threading.Lock()
        self._stop=threading.Event()
        self._done=threading.Event()
        self._thread=None
        self._proc=None
        self._fallback_phase=0.0

    def start(self):
        self._stop.clear()
        self._done.clear()
        if self._thread and self._thread.is_alive():
            return True
        if not HAS_FFMPEG:
            self._thread=threading.Thread(target=self._synthetic_loop,daemon=True)
            self._thread.start(); return True
        cmd=["ffmpeg","-loglevel","error","-i",self._path,"-f","s16le",
             "-ac","1","-ar",str(self._sample_rate),"-vn","-"]
        try:
            self._proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=_NWIN)
        except Exception:
            self._thread=threading.Thread(target=self._synthetic_loop,daemon=True)
            self._thread.start(); return True
        self._thread=threading.Thread(target=self._stream_loop,daemon=True)
        self._thread.start(); return True

    def stop(self):
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                try: self._proc.wait(timeout=0.25)
                except subprocess.TimeoutExpired: self._proc.kill()
            except: pass
        self._proc=None

    def _stream_loop(self):
        if not self._proc or not self._proc.stdout:
            return
        bytes_per_frame=self._chunk_samples*2
        buf=b""
        try:
            while not self._stop.is_set():
                chunk=self._proc.stdout.read(bytes_per_frame-len(buf))
                if not chunk:
                    break
                buf+=chunk
                if len(buf)<bytes_per_frame:
                    continue
                self._append_samples(buf[:bytes_per_frame])
                buf=buf[bytes_per_frame:]
            if buf and not self._stop.is_set():
                self._append_samples(buf)
        finally:
            self._done.set()

    def _append_samples(self,chunk):
        if len(chunk)<2:
            return
        usable=len(chunk)-(len(chunk)%2)
        samples=np.frombuffer(chunk[:usable],dtype="<i2").astype(np.float32)
        if samples.size==0:
            return
        vals=self._samples_to_bins(samples)
        with self._lock:
            self._frames.append(vals)

    def _samples_to_bins(self,samples):
        samples=np.abs(samples)/32768.0
        if samples.size < self._width:
            if samples.size==1:
                return np.full(self._width,float(samples[0]),dtype=np.float32)
            return np.interp(np.arange(self._width),
                             np.linspace(0,samples.size-1,self._width),
                             samples).astype(np.float32)
        bins=np.array_split(samples,self._width)
        return np.array([float(np.max(b)) if b.size else 0.0 for b in bins],
                        dtype=np.float32)

    def _synthetic_loop(self):
        while not self._stop.is_set():
            time.sleep(0.1)
        self._done.set()

    def next_frame_at(self,seconds=0.0,grade=None):
        idx=max(0,int(float(seconds or 0.0)*self._fps))
        vals=None
        with self._lock:
            if self._frames:
                vals=self._frames[min(idx,len(self._frames)-1)]
        if vals is None:
            vals=np.abs(np.sin(np.linspace(0.0, 2.0*np.pi, self._width) + self._fallback_phase))
            self._fallback_phase+=0.18
        vals=np.clip(vals.astype(np.float32),0.0,1.0)
        img=Image.new("RGB",(self._width,self._height),(13,13,13))
        draw=ImageDraw.Draw(img)
        mid=self._height//2
        draw.line((0,mid,self._width-1,mid),fill=(24,24,24))
        for i,v in enumerate(vals):
            h=max(1,int(v*(self._height*0.45)))
            y0=max(0,mid-h)
            y1=min(self._height-1,mid+h)
            if grade is not None:
                r=max(0,min(255,int(40+180*max(0.0,grade.r_gain-0.2))))
                g=max(0,min(255,int(40+180*max(0.0,grade.g_gain-0.2))))
                b=max(0,min(255,int(40+180*max(0.0,grade.b_gain-0.2))))
                color=(r,g,b)
            else:
                color=(80,140,220)
            draw.line((i,y0,i,y1),fill=color)
        return np.array(img,dtype=np.uint8)

# ── GPU ───────────────────────────────────────────────────────────────────────
def detect_gpu():
    try:
        r=subprocess.run(["wmic","path","win32_VideoController","get","Name"],
            capture_output=True,text=True,timeout=3,creationflags=_NWIN)
        names=[l.strip() for l in r.stdout.splitlines()
               if l.strip() and l.strip().lower()!="name"]
        name=names[0] if names else ""
        n=name.lower()
        if any(x in n for x in ["rtx 50","rtx 4090","rtx 4080"]): p,c=5,200
        elif any(x in n for x in ["rtx 40","rtx 30","rx 7900"]):   p,c=4,160
        elif any(x in n for x in ["rtx 20","gtx 16","rx 6"]):      p,c=3,120
        elif any(x in n for x in ["arc","intel","uhd","iris"]):     p,c=2,160
        else:                                                        p,c=3,130
        return (name[:30]+"…" if len(name)>30 else name) or "Unknown",p,c
    except: return "Unknown",2,80

# ── Font + atlas ──────────────────────────────────────────────────────────────
_FONT_SZ = 6

def _load_font(sz):
    for p in ["C:/Windows/Fonts/cour.ttf","C:/Windows/Fonts/consola.ttf",
              "C:/Windows/Fonts/lucon.ttf"]:
        try: return ImageFont.truetype(p,sz)
        except: pass
    return ImageFont.load_default()

def _measure(font):
    try:
        b=font.getbbox("M"); return max(1,b[2]-b[0]),max(1,b[3]-b[1]+1)
    except: return 4,7

def _build_atlas(font,cw,ch):
    atlas=np.zeros((len(CHARS),ch,cw),dtype=np.float32)
    for i,c in enumerate(CHARS):
        img=Image.new("L",(cw*2,ch*2),0)
        ImageDraw.Draw(img).text((0,0),c,fill=255,font=font)
        atlas[i]=np.array(img)[:ch,:cw]/255.0
    return atlas

_G_FONT          = _load_font(_FONT_SZ)
_G_CHAR_W,_G_CHAR_H = _measure(_G_FONT)
_G_ATLAS         = _build_atlas(_G_FONT,_G_CHAR_W,_G_CHAR_H)
_G_AR            = _G_CHAR_W/_G_CHAR_H
_FONT_LOCK       = threading.RLock()

def apply_font_sz(sz):
    global _FONT_SZ,_G_FONT,_G_CHAR_W,_G_CHAR_H,_G_ATLAS,_G_AR
    with _FONT_LOCK:
        _FONT_SZ=sz
        _G_FONT=_load_font(sz)
        _G_CHAR_W,_G_CHAR_H=_measure(_G_FONT)
        _G_ATLAS=_build_atlas(_G_FONT,_G_CHAR_W,_G_CHAR_H)
        _G_AR=_G_CHAR_W/_G_CHAR_H

# ── Color grading ─────────────────────────────────────────────────────────────
class ColorGrade:
    """Bundles the color-adjustment knobs applied before ASCII conversion."""
    __slots__=("exposure","r_gain","g_gain","b_gain","brightness","contrast",
               "gamma","saturation")
    def __init__(self,exposure=0.0,r_gain=1.0,g_gain=1.0,b_gain=1.0,
                 brightness=0.0,contrast=1.0,gamma=1.0,saturation=1.0):
        self.exposure=exposure
        self.r_gain=r_gain; self.g_gain=g_gain; self.b_gain=b_gain
        self.brightness=brightness
        self.contrast=contrast
        self.gamma=gamma
        self.saturation=saturation

DEFAULT_GRADE=ColorGrade()

def apply_color_grade(small,grade):
    """Applies exposure / RGB gain / brightness / contrast / gamma ("Darkness")
    / saturation to a float32 HxWx3 array in the 0-255 range. Returns a
    float32 array, still in the 0-255 range."""
    img=small
    if grade.exposure:
        img=img*(2.0**grade.exposure)
    if grade.r_gain!=1.0 or grade.g_gain!=1.0 or grade.b_gain!=1.0:
        img=img*np.array([grade.r_gain,grade.g_gain,grade.b_gain],dtype=np.float32)
    if grade.brightness:
        img=img+grade.brightness
    if grade.contrast!=1.0:
        img=(img-127.5)*grade.contrast+127.5
    if grade.gamma!=1.0:
        img=255.0*np.power(np.clip(img,0.0,255.0)/255.0,grade.gamma)
    if grade.saturation!=1.0:
        gray=(0.299*img[:,:,0]+0.587*img[:,:,1]+0.114*img[:,:,2])[:,:,np.newaxis]
        img=gray+(img-gray)*grade.saturation
    return np.clip(img,0.0,255.0)

# ── Render ────────────────────────────────────────────────────────────────────
def render_frame(rgb,cols,quality=RESAMPLE_BILINEAR,grade=None):
    h,w=rgb.shape[:2]
    if h==0 or w==0 or cols<4: return None
    with _FONT_LOCK:
        char_w,char_h,char_ar,atlas=_G_CHAR_W,_G_CHAR_H,_G_AR,_G_ATLAS
    cols=min(int(cols),300)
    rows=max(2,min(int(cols*h/w*char_ar),200))
    small=np.array(Image.fromarray(rgb).resize((cols,rows),quality),
                   dtype=np.float32)
    if small.ndim==3 and small.shape[2]==4: small=small[:,:,:3]
    small=apply_color_grade(small,grade or DEFAULT_GRADE)
    lum=0.299*small[:,:,0]+0.587*small[:,:,1]+0.114*small[:,:,2]
    ci =np.clip((lum/255.0*(len(CHARS)-1)).astype(np.int32),0,len(CHARS)-1)
    a  =atlas[ci][:,:,:,:,np.newaxis]
    col=small[:,:,np.newaxis,np.newaxis,:]
    out=np.clip(a*col+(1.0-a)*BG_COLOR,0,255).astype(np.uint8)
    return out.transpose(0,2,1,3,4).reshape(rows*char_h,cols*char_w,3)

def scale_contain(arr,tw,th):
    if arr is None or tw<=0 or th<=0: return arr
    sh,sw=arr.shape[:2]; s=min(tw/sw,th/sh)
    nw,nh=max(1,int(sw*s)),max(1,int(sh*s))
    scaled=np.array(Image.fromarray(arr).resize((nw,nh),RESAMPLE_NEAREST))
    canvas=np.full((th,tw,3),13,dtype=np.uint8)
    canvas[(th-nh)//2:(th-nh)//2+nh,(tw-nw)//2:(tw-nw)//2+nw]=scaled
    return canvas

# ── App ───────────────────────────────────────────────────────────────────────
class App:
    def __init__(self,autostart=True):
        self.root=self._create_root()
        self.root.title("ASCII Art Player")
        self.root.configure(bg=BG_HEX)
        self.root.geometry("960x640")
        self.root.protocol("WM_DELETE_WINDOW",self._close)

        self._stop   =threading.Event()
        self._paused =threading.Event()
        self._thread =None
        self._photo  =None
        self._fs     =False
        self._is_vid =False
        self._is_audio=False
        self._vid_fps=24.0
        self._speed  =1.0
        self._muted  =False
        self._closed =False
        self._session_id=0

        self._fl,self._narr=threading.Lock(),None
        self._pl       =threading.Lock()
        self._pos      =0
        self._total    =0
        self._seek_req =None
        self._uiq      =queue.Queue()

        self._audio    =None
        self._audio_lock=threading.Lock()
        self._vid_path =None
        self._dialog   =None
        self._dialog_lock=threading.Lock()
        self._sw       =None   # settings window
        self._fs_bar_progress=0.0  # 0.0 = fully hidden below, 1.0 = fully visible
        self._fs_bar_shown   =False
        self._fs_anim_id     =None
        self._fs_hide_job    =None
        self._canvas_size=(960,560)

        # ── user-adjustable settings ──
        self._gpu_name,self._gpu_preset,self._gpu_cap=detect_gpu()
        self._preset_cols =None          # None = Auto
        self._render_quality=RESAMPLE_BILINEAR
        self._display_fps  =30           # Hz
        self._max_skip     =4

        # ── color grading (all neutral by default) ──
        self._brightness=0.0             # additive,          -100..100
        self._contrast  =1.0             # multiplier,           0..2
        self._exposure  =0.0             # stops,               -3..3
        self._gamma     =1.0             # "Darkness" curve,   0.2..3
        self._saturation=1.0             # multiplier,           0..2
        self._r_gain    =1.0             # multiplier,           0..2
        self._g_gain    =1.0             # multiplier,           0..2
        self._b_gain    =1.0             # multiplier,           0..2
        self._last_rgb  =None            # cached raw frame, for instant re-grade

        self._build_ui()
        self._bind_keys()
        self.root.after(self._poll_ms(),self._poll)
        if autostart:
            self.run()

    def _create_root(self):
        global HAS_DND
        if HAS_DND and TkinterDnD is not None:
            try:
                return TkinterDnD.Tk()
            except Exception:
                HAS_DND=False
        return tk.Tk()

    def run(self):
        self.root.mainloop()

    def _poll_ms(self): return max(16,int(1000/self._display_fps))

    def _is_session(self,session):
        return not self._closed and session==self._session_id

    def _call_ui(self,func,*args,session=None,**kwargs):
        self._uiq.put((session,func,args,kwargs))

    def _drain_ui(self):
        while True:
            try:
                session,func,args,kwargs=self._uiq.get_nowait()
            except queue.Empty:
                break
            if session is not None and not self._is_session(session):
                continue
            try:
                func(*args,**kwargs)
            except tk.TclError:
                pass

    def _current_audio(self):
        with self._audio_lock:
            return self._audio

    def _set_audio(self,audio,session):
        with self._audio_lock:
            if not self._is_session(session):
                return False
            self._audio=audio
            return True

    def _stop_current_audio(self):
        with self._audio_lock:
            audio,self._audio=self._audio,None
        if audio:
            audio.stop()

    def _discard_audio(self,audio):
        with self._audio_lock:
            if self._audio is audio:
                self._audio=None
        if audio:
            audio.stop()

    def _sync_audio(self,pos=None,session=None):
        audio=self._current_audio()
        if not audio:
            return
        if session is not None and not self._is_session(session):
            audio.stop()
            return
        if (not self._is_vid and not self._is_audio) or self._muted or self._paused.is_set():
            audio.stop()
            return
        if pos is None:
            with self._pl:
                pos=self._pos
        t=max(0.0,float(pos)/max(1.0,self._vid_fps))
        audio.play(t,self._speed)

    def _request_seek(self,frame):
        with self._pl:
            total=self._total
            if total<=1:
                return None
            req=max(0,min(int(frame),total-1))
            self._seek_req=req
        self._sync_audio(pos=req)
        return req

    def _sleep_interruptible(self,seconds,stop_event):
        end=time.perf_counter()+max(0.0,seconds)
        while not stop_event.is_set():
            left=end-time.perf_counter()
            if left<=0:
                return
            time.sleep(min(0.05,left))

    # ── cols ──────────────────────────────────────────────────────────────────
    def _effective_cols(self):
        if self._preset_cols is None:
            w=self._canvas_size[0]
            with _FONT_LOCK:
                char_w=_G_CHAR_W
            return max(20,min(w//char_w,self._gpu_cap)) if w>10 else self._gpu_cap
        return self._preset_cols

    # ── color grading ────────────────────────────────────────────────────────
    def _current_grade(self):
        return ColorGrade(
            exposure=self._exposure,
            r_gain=self._r_gain,g_gain=self._g_gain,b_gain=self._b_gain,
            brightness=self._brightness,contrast=self._contrast,
            gamma=self._gamma,saturation=self._saturation)

    def _redraw_current_frame(self):
        """Re-renders the last decoded frame so color tweaks show up instantly."""
        rgb=self._last_rgb
        if rgb is None: return
        session=self._session_id
        arr=render_frame(rgb,self._effective_cols(),self._render_quality,
                         self._current_grade())
        if arr is not None: self._push(arr,session=session)

    def _make_rgb_wheel(self,size):
        img=Image.new("RGB",(size,size),(20,20,20))
        draw=ImageDraw.Draw(img)
        cx=cy=size/2.0
        radius=(size-4)/2.0
        for y in range(size):
            for x in range(size):
                dx=(x+0.5)-cx; dy=cy-(y+0.5)
                dist=(dx*dx+dy*dy)**0.5
                if dist>radius:
                    continue
                hue=(math.atan2(dy,dx)/(2*math.pi)+1.0)%1.0
                sat=dist/radius
                val=0.5+(sat*0.5)
                r,g,b=self._hsv_to_rgb(hue,sat,val)
                draw.point((x,y),(int(r*255),int(g*255),int(b*255)))
        draw.ellipse((2,2,size-3,size-3),outline=(48,48,48))
        return img

    def _hsv_to_rgb(self,h,s,v):
        if s<=0.0:
            return v,v,v
        i=int(h*6.0)%6
        f=(h*6.0)-i
        p=v*(1.0-s)
        q=v*(1.0-s*f)
        t=v*(1.0-s*(1.0-f))
        if i==0: return v,t,p
        if i==1: return q,v,p
        if i==2: return p,v,t
        if i==3: return p,q,v
        if i==4: return t,p,v
        return v,p,q

    def _rgb_to_hsv(self,r,g,b):
        mx=max(r,g,b); mn=min(r,g,b)
        diff=mx-mn
        if diff<=0.0:
            return 0.0,0.0,mx
        if mx==r:
            h=((g-b)/diff)%6.0
        elif mx==g:
            h=(b-r)/diff+2.0
        else:
            h=(r-g)/diff+4.0
        return h/6.0,diff/mx,mx

    def _palette_rgb_from_gains(self):
        r=int(round(max(0,min(255,self._r_gain*127.5))))
        g=int(round(max(0,min(255,self._g_gain*127.5))))
        b=int(round(max(0,min(255,self._b_gain*127.5))))
        return r,g,b

    def _set_palette_rgb(self,r,g,b,redraw=True):
        self._r_gain=max(0.0,min(2.0,float(r)/127.5))
        self._g_gain=max(0.0,min(2.0,float(g)/127.5))
        self._b_gain=max(0.0,min(2.0,float(b)/127.5))
        self._update_palette_preview()
        if redraw:
            self._redraw_current_frame()

    def _update_palette_preview(self):
        if not hasattr(self, '_palette_preview_canvas'):
            return
        r,g,b=self._palette_rgb_from_gains()
        hex_color=f"#{r:02x}{g:02x}{b:02x}"
        self._palette_preview_canvas.configure(bg=hex_color)
        if hasattr(self,'_palette_hex_var'):
            self._palette_hex_var.set(hex_color.upper())
        self._update_palette_cursor()

    def _update_palette_cursor(self):
        if not hasattr(self,'_palette_canvas'):
            return
        size=getattr(self,'_palette_size',0)
        if not size:
            return
        r,g,b=self._palette_rgb_from_gains()
        hue,sat,_=self._rgb_to_hsv(r/255.0,g/255.0,b/255.0)
        radius=(size-4)/2.0
        dist=radius*max(0.0,min(1.0,sat))
        angle=hue*2*math.pi
        cx=cy=size/2.0
        x=cx+math.cos(angle)*dist
        y=cy-math.sin(angle)*dist
        d=5
        coords=(x-d,y-d,x+d,y+d)
        if getattr(self,'_palette_cursor',None) is None:
            self._palette_cursor_shadow=self._palette_canvas.create_oval(
                x-d-1,y-d-1,x+d+1,y+d+1,outline="#111",width=1)
            self._palette_cursor=self._palette_canvas.create_oval(
                *coords,outline="#f2f2f2",width=2)
        else:
            self._palette_canvas.coords(
                self._palette_cursor_shadow,x-d-1,y-d-1,x+d+1,y+d+1)
            self._palette_canvas.coords(self._palette_cursor,*coords)

    def _on_palette_click(self,e):
        if not hasattr(self, '_palette_size'):
            return
        size=self._palette_size
        cx=cy=size/2
        x=max(0,min(size-1,e.x))
        y=max(0,min(size-1,e.y))
        dx=(x+0.5)-cx; dy=cy-(y+0.5)
        dist=(dx*dx+dy*dy)**0.5
        radius=(size-4)/2.0
        if dist>radius:
            scale=radius/dist
            dx*=scale; dy*=scale; dist=radius
        hue=(math.atan2(dy,dx)/(2*math.pi)+1.0)%1.0
        sat=dist/radius
        val=0.5+(sat*0.5)
        r,g,b=self._hsv_to_rgb(hue,sat,val)
        self._set_palette_rgb(int(r*255),int(g*255),int(b*255))

    def _choose_palette_color(self):
        initial="#%02x%02x%02x"%self._palette_rgb_from_gains()
        picked=colorchooser.askcolor(color=initial,parent=self._sw,
                                     title="Choose color")
        if not picked or picked[0] is None:
            return
        r,g,b=(int(round(c)) for c in picked[0])
        self._set_palette_rgb(r,g,b)

    # ── keyboard ──────────────────────────────────────────────────────────────
    def _bind_keys(self):
        r=self.root
        r.bind("<space>",  lambda e:self._toggle_play())
        r.bind("k",        lambda e:self._toggle_play())
        r.bind("j",        lambda e:self._seek_rel(-10))
        r.bind("l",        lambda e:self._seek_rel(10))
        r.bind("<Left>",   lambda e:self._seek_rel(-5))
        r.bind("<Right>",  lambda e:self._seek_rel(5))
        r.bind("<F11>",    lambda e:self._toggle_fs())
        r.bind("<Escape>", lambda e:self._exit_fs())
        r.bind("f",        lambda e:self._toggle_fs())
        r.bind("m",        lambda e:self._toggle_mute())
        r.bind(",",        lambda e:self._step_frame(-1))
        r.bind(".",        lambda e:self._step_frame(1))
        r.bind("<less>",   lambda e:self._change_speed(-0.25))
        r.bind("<greater>",lambda e:self._change_speed(0.25))
        for i in range(10):
            r.bind(str(i),lambda e,n=i:self._seek_pct(n*10))

    def _seek_rel(self,secs):
        if not (self._is_vid or self._is_audio): return
        with self._pl:
            if self._total<=1: return
            req=self._pos+int(secs*self._vid_fps)
        self._request_seek(req)

    def _seek_pct(self,pct):
        with self._pl:
            if self._total<=1: return
            req=int((self._total-1)*pct/100)
        self._request_seek(req)

    def _step_frame(self,delta):
        with self._pl:
            if self._total<=1: return
            req=self._pos+delta
        self._request_seek(req)

    def _change_speed(self,delta):
        self._speed=max(0.25,min(4.0,round(self._speed+delta,2)))
        self._speed_var.set(f"{self._speed:.2f}×")
        self._sync_audio()

    def _toggle_mute(self):
        self._muted=not self._muted
        self._mute_var.set("🔇" if self._muted else "🔊")
        self._sync_audio()

    # ── interrupt protection ──────────────────────────────────────────────────
    def _is_active(self):
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def _paths_from_drop(self,raw):
        text=str(raw or "").strip()
        if not text:
            return []
        single=text.strip("{}")
        if os.path.exists(single):
            return [single]
        try:
            parts=list(self.root.tk.splitlist(text))
        except Exception:
            parts=[single]
        paths=[]
        for item in parts:
            path=str(item).strip().strip("{}")
            if not path:
                continue
            if path.lower().startswith("file:"):
                u=urllib.parse.urlparse(path)
                path=urllib.parse.unquote(u.path)
                if u.netloc:
                    path=f"//{u.netloc}{path}"
                if os.name=="nt" and len(path)>2 and path[0]=="/" and path[2]==":":
                    path=path[1:]
            paths.append(path)
        return paths

    def _handle(self,raw):
        paths=self._paths_from_drop(raw)
        missing=[]
        unsupported=[]
        for path in paths:
            ext=os.path.splitext(path)[1].lower()
            if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS and ext not in AUDIO_EXTS:
                unsupported.append(ext or "(no ext)")
                continue
            if not os.path.isfile(path):
                missing.append(os.path.basename(path) or path)
                continue
            if self._is_active(): self._show_interrupt(path)
            else: self._load(path)
            return
        if missing:
            self._file_var.set(f"file not found: {missing[0]}")
        elif unsupported:
            self._file_var.set(f"unsupported: {unsupported[0]}")
        else:
            self._file_var.set("no file selected")

    def _show_interrupt(self,path):
        with self._dialog_lock:
            if self._dialog:
                try: self._dialog.destroy()
                except: pass
                self._dialog=None
        d=tk.Frame(self._canvas,bg="#151515",padx=28,pady=18,
                   highlightthickness=1,highlightbackground="#2a2a2a")
        tk.Label(d,text="⚠  Already playing",bg="#151515",fg="#888",
                 font=("Courier New",10)).pack()
        tk.Label(d,text=os.path.basename(path),bg="#151515",fg="#aaa",
                 font=("Courier New",9)).pack(pady=(4,2))
        tk.Label(d,text="Replace current playback?",bg="#151515",fg="#555",
                 font=("Courier New",9)).pack()
        bf=tk.Frame(d,bg="#151515"); bf.pack(pady=10)
        def yes():
            d.destroy(); self._dialog=None; self._load(path)
        def no():
            d.destroy(); self._dialog=None
        for txt,cmd,fg in [("Replace",yes,"#888"),("Cancel",no,"#444")]:
            tk.Button(bf,text=txt,command=cmd,bg="#1e1e1e",fg=fg,
                      activebackground="#2a2a2a",font=("Courier New",9),
                      bd=0,padx=14,pady=5,cursor="hand2",relief="flat"
                      ).pack(side="left",padx=6)
        d.place(relx=0.5,rely=0.5,anchor="center")
        self._dialog=d

    def _load(self,path):
        ext=os.path.splitext(path)[1].lower()
        self._do_stop(wait=True)
        self._session_id+=1
        session=self._session_id
        self._stop=threading.Event()
        self._overlay.place_forget()
        self._file_var.set(os.path.basename(path))
        self._vid_path=path
        self._is_vid=ext in VIDEO_EXTS
        self._is_audio=ext in AUDIO_EXTS
        self._paused.clear()
        self._speed=1.0; self._speed_var.set("1.00×")
        self._pbtn.configure(text="⏸")
        if ext in IMAGE_EXTS:
            tgt=self._play_img
        elif ext in VIDEO_EXTS:
            tgt=self._play_vid
        else:
            tgt=self._play_audio
        self._thread=threading.Thread(target=tgt,args=(path,self._stop,session),daemon=True)
        self._thread.start()

    # ── display poll ──────────────────────────────────────────────────────────
    def _push(self,arr,session=None):
        if session is not None and not self._is_session(session):
            return
        with self._fl: self._narr=arr

    def _poll(self):
        if self._closed:
            return
        self._drain_ui()
        with self._fl: arr,self._narr=self._narr,None
        if arr is not None:
            cw=max(1,self._canvas.winfo_width())
            ch=max(1,self._canvas.winfo_height())
            self._canvas_size=(cw,ch)
            disp=scale_contain(arr,cw,ch)
            pil =Image.fromarray(disp)
            if (self._photo is None or
                    self._photo.width()!=cw or self._photo.height()!=ch):
                self._photo=ImageTk.PhotoImage(pil)
                self._canvas.itemconfigure(self._imgid,image=self._photo)
                self._canvas.configure(scrollregion=(0,0,cw,ch))
            else:
                self._photo.paste(pil)
        with self._pl: pos,total=self._pos,self._total
        if total>1:
            w=self._seekbar.winfo_width()
            den=max(1,total-1)
            self._seekbar.coords(self._seek_fill,0,0,int(w*max(0,min(pos,den))/den),6)
        else:
            self._seekbar.coords(self._seek_fill,0,0,0,6)
        try:
            self.root.after(self._poll_ms(),self._poll)
        except tk.TclError:
            self._closed=True

    # ── UI ────────────────────────────────────────────────────────────────────
    def _on_canvas_configure(self,e):
        self._canvas_size=(max(1,e.width),max(1,e.height))
        self._photo=None

    def _mkbtn(self,parent,text,cmd,w=3,fsz=12,fg="#999"):
        return tk.Button(parent,text=text,command=cmd,bg="#1a1a1a",fg=fg,
                         activebackground="#2a2a2a",activeforeground="#fff",
                         font=("Segoe UI Symbol",fsz),
                         bd=0,padx=6,pady=4,width=w,cursor="hand2",relief="flat")

    def _build_ui(self):
        # top bar
        self._topbar=tk.Frame(self.root,bg="#111",pady=4)
        self._topbar.pack(fill="x",side="top")
        self._file_var=tk.StringVar(value="drop a file or click open")
        tk.Label(self._topbar,textvariable=self._file_var,bg="#111",fg="#444",
                 font=("Courier New",9),anchor="w").pack(side="left",padx=12)
        audio_lbl="ffplay ok" if HAS_FFPLAY else "no audio · install ffmpeg"
        tk.Label(self._topbar,text=audio_lbl,bg="#111",fg="#252525",
                 font=("Courier New",8)).pack(side="right",padx=12)
        self._fps_var=tk.StringVar(value="")
        tk.Label(self._topbar,textvariable=self._fps_var,bg="#111",fg="#334",
                 font=("Courier New",9)).pack(side="right",padx=6)
        tk.Label(self._topbar,text=self._gpu_name,bg="#111",fg="#1e1e1e",
                 font=("Courier New",8)).pack(side="right",padx=12)

        # canvas
        self._canvas=tk.Canvas(self.root,bg=BG_HEX,highlightthickness=0)
        self._canvas.pack(fill="both",expand=True)
        self._canvas.bind("<Configure>",self._on_canvas_configure)
        self._imgid=self._canvas.create_image(0,0,anchor="nw")
        drop_hint="drag & drop  /  open" if HAS_DND else "click to open"
        self._overlay=tk.Label(self._canvas,
            text=f"{drop_hint}\n\n"
                 "supported: images/videos/audio\n\n"
                 "shortcuts: hover here or see settings",
            bg=BG_HEX,fg="#1a1a1a",font=("Courier New",10),justify="center")
        self._overlay.place(relx=0.5,rely=0.5,anchor="center")
        self._overlay.bind("<Button-1>",lambda e:self._browse())
        if HAS_DND:
            for w in (self._canvas,self._overlay):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>",lambda e:self._handle(e.data))
                except Exception:
                    break

        # seekbar
        self._seekbar=tk.Canvas(self.root,bg="#0e0e0e",height=6,
                                 highlightthickness=0,cursor="hand2")
        self._seekbar.pack(fill="x",side="top")
        self._seek_fill=self._seekbar.create_rectangle(0,0,0,6,fill="#3a3a3a",outline="")
        self._seekbar.bind("<Button-1>",  self._on_seek)
        self._seekbar.bind("<B1-Motion>", self._on_seek)

        # control bar
        self._ctrlbar=tk.Frame(self.root,bg="#111",pady=5)
        self._ctrlbar.pack(fill="x",side="bottom")

        # playback buttons
        pbf=tk.Frame(self._ctrlbar,bg="#111"); pbf.pack(side="left",padx=8)
        self._mkbtn(pbf,"⏮",self._restart,w=2).pack(side="left",padx=2)
        self._pbtn=self._mkbtn(pbf,"▶",self._toggle_play,w=2)
        self._pbtn.pack(side="left",padx=2)
        self._mkbtn(pbf,"⏹",self._do_stop,w=2).pack(side="left",padx=2)

        tk.Frame(self._ctrlbar,bg="#222",width=1).pack(side="left",fill="y",padx=8)

        # speed + mute
        self._speed_var=tk.StringVar(value="1.00×")
        tk.Label(self._ctrlbar,textvariable=self._speed_var,bg="#111",fg="#444",
                 font=("Courier New",9),width=6).pack(side="left",padx=2)
        self._mute_var=tk.StringVar(value="🔊")
        tk.Button(self._ctrlbar,textvariable=self._mute_var,command=self._toggle_mute,
                  bg="#1a1a1a",fg="#666",activebackground="#222",
                  font=("Segoe UI Symbol",10),bd=0,padx=4,pady=3,
                  cursor="hand2",relief="flat",width=2).pack(side="left",padx=2)

        tk.Frame(self._ctrlbar,bg="#222",width=1).pack(side="left",fill="y",padx=8)
        self._mkbtn(self._ctrlbar,"open",self._browse,w=4,fsz=9).pack(side="left",padx=4)

        # right side: settings + fullscreen
        tk.Label(self._ctrlbar,text="F11",bg="#111",fg="#1e1e1e",
                 font=("Courier New",8)).pack(side="right",padx=(0,4))
        self._mkbtn(self._ctrlbar,"⛶",self._toggle_fs,w=2,fsz=11).pack(side="right",padx=4)
        tk.Frame(self._ctrlbar,bg="#222",width=1).pack(side="right",fill="y",padx=6)
        self._mkbtn(self._ctrlbar,"⚙",self._open_settings,w=2,fsz=11,fg="#666"
                    ).pack(side="right",padx=4)

    # ── Settings window ───────────────────────────────────────────────────────

    def _open_settings(self):
        if self._sw and self._sw.winfo_exists():
            self._sw.lift(); return

        self._sw=win=tk.Toplevel(self.root)
        win.title("Settings")
        win.configure(bg="#0d0d0d")
        win.geometry("460x600")
        win.resizable(False,False)
        win.transient(self.root)

        # custom tab bar
        tab_bar=tk.Frame(win,bg="#111"); tab_bar.pack(fill="x")
        content=tk.Frame(win,bg="#0d0d0d")
        content.pack(fill="both",expand=True,padx=20,pady=14)

        tabs={n:tk.Frame(content,bg="#0d0d0d") for n in ["Quality","Playback","Color","Shortcuts"]}
        tab_btns={}

        def show_tab(name):
            for f in tabs.values(): f.pack_forget()
            tabs[name].pack(fill="both",expand=True)
            for b in tab_btns.values():
                b.configure(fg="#444",bg="#111",relief="flat")
            tab_btns[name].configure(fg="#ccc",bg="#0d0d0d")

        for name in ["Quality","Playback","Color","Shortcuts"]:
            b=tk.Button(tab_bar,text=f"  {name}  ",
                        command=lambda n=name:show_tab(n),
                        bg="#111",fg="#444",font=("Courier New",10),
                        bd=0,pady=8,cursor="hand2",relief="flat")
            b.pack(side="left")
            tab_btns[name]=b

        self._build_quality_tab(tabs["Quality"])
        self._build_playback_tab(tabs["Playback"])
        self._build_color_tab(tabs["Color"])
        self._build_shortcuts_tab(tabs["Shortcuts"])
        show_tab("Quality")

    def _setting_row(self,frame,label,widget_fn,pady=7):
        """helper: label on left, widget on right"""
        row=tk.Frame(frame,bg="#0d0d0d"); row.pack(fill="x",pady=pady)
        tk.Label(row,text=label,bg="#0d0d0d",fg="#555",
                 font=("Courier New",9),width=12,anchor="w").pack(side="left")
        widget_fn(row)
        return row

    def _build_quality_tab(self,frame):
        tk.Label(frame,text="Quality Settings",bg="#0d0d0d",fg="#333",
                 font=("Courier New",8)).pack(anchor="w",pady=(0,8))

        # Auto cap slider
        cap_var=tk.IntVar(value=self._gpu_cap)
        cap_lbl_var=tk.StringVar(value=str(self._gpu_cap))
        def upd_cap(v):
            self._gpu_cap=int(float(v)); cap_lbl_var.set(str(self._gpu_cap))
        def cap_w(row):
            tk.Scale(row,from_=40,to=300,orient="horizontal",variable=cap_var,
                     command=upd_cap,bg="#0d0d0d",fg="#555",
                     highlightthickness=0,troughcolor="#1a1a1a",
                     activebackground="#444",length=200,showvalue=False
                     ).pack(side="left")
            tk.Label(row,textvariable=cap_lbl_var,bg="#0d0d0d",fg="#888",
                     font=("Courier New",9),width=4).pack(side="left")
        self._setting_row(frame,"Auto Cap",cap_w)

        # Font size
        DETAIL=[("Coarse · 9px",9),("Normal · 7px",7),("Fine   · 6px",6),("Ultra  · 5px",5)]
        d_var=tk.StringVar(value=next((l for l,s in DETAIL if s==_FONT_SZ),"Fine   · 6px"))
        rebuilding=tk.StringVar(value="")
        def upd_font(_=None):
            sz=next((s for l,s in DETAIL if l==d_var.get()),6)
            if sz==_FONT_SZ: return
            rebuilding.set("rebuilding atlas…")
            frame.update()
            apply_font_sz(sz)
            self._photo=None   # force PhotoImage recreate
            rebuilding.set("")
        def font_w(row):
            style=ttk.Style(); style.configure("D.TCombobox",
                fieldbackground="#1a1a1a",background="#1a1a1a",foreground="#777",
                selectbackground="#1a1a1a",selectforeground="#777",arrowcolor="#444")
            style.map("D.TCombobox",fieldbackground=[("readonly","#1a1a1a")],
                      foreground=[("readonly","#777")])
            cb=ttk.Combobox(row,textvariable=d_var,values=[l for l,_ in DETAIL],
                            state="readonly",width=13,style="D.TCombobox",
                            font=("Courier New",9))
            cb.pack(side="left"); cb.bind("<<ComboboxSelected>>",upd_font)
            tk.Label(row,textvariable=rebuilding,bg="#0d0d0d",fg="#555",
                     font=("Courier New",8)).pack(side="left",padx=6)
        self._setting_row(frame,"Char Detail",font_w)

        # Render quality radio
        q_var=tk.StringVar(value="Quality" if self._render_quality==RESAMPLE_BILINEAR else "Fast")
        def upd_q():
            self._render_quality=RESAMPLE_BILINEAR if q_var.get()=="Quality" else RESAMPLE_NEAREST
        def quality_w(row):
            for lbl in ["Fast","Quality"]:
                tk.Radiobutton(row,text=lbl,variable=q_var,value=lbl,
                               command=upd_q,bg="#0d0d0d",fg="#666",
                               selectcolor="#0d0d0d",activebackground="#0d0d0d",
                               font=("Courier New",9)
                               ).pack(side="left",padx=(0,10))
            tk.Label(row,text="← affects char sampling quality",bg="#0d0d0d",fg="#2a2a2a",
                     font=("Courier New",8)).pack(side="left")
        self._setting_row(frame,"Downsampling",quality_w)

    def _build_playback_tab(self,frame):
        tk.Label(frame,text="Playback Settings",bg="#0d0d0d",fg="#333",
                 font=("Courier New",8)).pack(anchor="w",pady=(0,8))

        # Display FPS
        fps_var=tk.IntVar(value=self._display_fps)
        fps_lbl=tk.StringVar(value=str(self._display_fps))
        def upd_fps(v):
            self._display_fps=int(float(v)); fps_lbl.set(str(self._display_fps))
        def fps_w(row):
            tk.Scale(row,from_=10,to=60,orient="horizontal",variable=fps_var,
                     command=upd_fps,bg="#0d0d0d",fg="#555",
                     highlightthickness=0,troughcolor="#1a1a1a",
                     activebackground="#444",length=200,showvalue=False
                     ).pack(side="left")
            tk.Label(row,textvariable=fps_lbl,bg="#0d0d0d",fg="#888",
                     font=("Courier New",9),width=4).pack(side="left")
        self._setting_row(frame,"Display Rate",fps_w)

        # Max skip
        skip_var=tk.IntVar(value=self._max_skip)
        skip_lbl=tk.StringVar(value=str(self._max_skip))
        def upd_skip(v):
            self._max_skip=int(float(v)); skip_lbl.set(str(self._max_skip))
        def skip_w(row):
            tk.Scale(row,from_=1,to=8,orient="horizontal",variable=skip_var,
                     command=upd_skip,bg="#0d0d0d",fg="#555",
                     highlightthickness=0,troughcolor="#1a1a1a",
                     activebackground="#444",length=200,showvalue=False
                     ).pack(side="left")
            tk.Label(row,textvariable=skip_lbl,bg="#0d0d0d",fg="#888",
                     font=("Courier New",9),width=4).pack(side="left")
            tk.Label(row,text="frames",bg="#0d0d0d",fg="#444",
                     font=("Courier New",9)).pack(side="left")
        self._setting_row(frame,"Max Frame Skip",skip_w)

        # Preset resolution
        from_res=[("Auto",None),("Nano 180p",32),("Low 320p",64),
                  ("Medium 480p",96),("High 640p",128),("Ultra 960p",192)]
        res_labels=[r[0] for r in from_res]
        res_cols  =[r[1] for r in from_res]
        cur=next((l for l,c in from_res if c==self._preset_cols),"Auto")
        res_var=tk.StringVar(value=cur)
        def upd_res(_=None):
            idx=res_labels.index(res_var.get()) if res_var.get() in res_labels else 0
            self._preset_cols=res_cols[idx]
        def res_w(row):
            cb=ttk.Combobox(row,textvariable=res_var,values=res_labels,
                            state="readonly",width=14,style="D.TCombobox",
                            font=("Courier New",9))
            cb.pack(side="left"); cb.bind("<<ComboboxSelected>>",upd_res)
        self._setting_row(frame,"Resolution",res_w)

    def _build_color_tab(self,frame):
        tk.Label(frame,text="Color Settings",bg="#0d0d0d",fg="#333",
                 font=("Courier New",8)).pack(anchor="w",pady=(0,8))

        resets=[]   # zero-arg callables, each restores one control to default

        def pct_row(label,attr,lo,hi,default=100,fmt="{}%"):
            init=int(getattr(self,attr)*100)
            var=tk.IntVar(value=init)
            lbl_var=tk.StringVar(value=fmt.format(init))
            def apply(val):
                setattr(self,attr,val/100.0)
                lbl_var.set(fmt.format(val))
            def upd(v):
                apply(int(float(v)))
                self._redraw_current_frame()
            def w(row):
                tk.Scale(row,from_=lo,to=hi,orient="horizontal",variable=var,
                         command=upd,bg="#0d0d0d",fg="#555",
                         highlightthickness=0,troughcolor="#1a1a1a",
                         activebackground="#444",length=170,showvalue=False
                         ).pack(side="left")
                tk.Label(row,textvariable=lbl_var,bg="#0d0d0d",fg="#888",
                         font=("Courier New",9),width=5).pack(side="left")
            self._setting_row(frame,label,w,pady=5)
            def do_reset():
                var.set(default); apply(default)
            resets.append(do_reset)
            return var

        # Brightness is an additive offset, shown as a signed int (not a %)
        bright_var=tk.IntVar(value=int(self._brightness))
        bright_lbl=tk.StringVar(value=f"{int(self._brightness):+d}")
        def apply_bright(val):
            self._brightness=float(val)
            bright_lbl.set(f"{val:+d}")
        def upd_bright(v):
            apply_bright(int(float(v)))
            self._redraw_current_frame()
        def bright_w(row):
            tk.Scale(row,from_=-100,to=100,orient="horizontal",variable=bright_var,
                     command=upd_bright,bg="#0d0d0d",fg="#555",
                     highlightthickness=0,troughcolor="#1a1a1a",
                     activebackground="#444",length=170,showvalue=False
                     ).pack(side="left")
            tk.Label(row,textvariable=bright_lbl,bg="#0d0d0d",fg="#888",
                     font=("Courier New",9),width=5).pack(side="left")
        self._setting_row(frame,"Brightness",bright_w,pady=5)
        def reset_bright():
            bright_var.set(0); apply_bright(0)
        resets.append(reset_bright)

        pct_row("Contrast","_contrast",0,200)

        # Exposure in photographic stops, e.g. "+1.5 EV"
        exp_var=tk.DoubleVar(value=self._exposure)
        exp_lbl=tk.StringVar(value=f"{self._exposure:+.1f} EV")
        def apply_exp(val):
            self._exposure=val
            exp_lbl.set(f"{val:+.1f} EV")
        def upd_exp(v):
            apply_exp(round(float(v),1))
            self._redraw_current_frame()
        def exp_w(row):
            tk.Scale(row,from_=-3.0,to=3.0,resolution=0.1,orient="horizontal",
                     variable=exp_var,command=upd_exp,bg="#0d0d0d",fg="#555",
                     highlightthickness=0,troughcolor="#1a1a1a",
                     activebackground="#444",length=170,showvalue=False
                     ).pack(side="left")
            tk.Label(row,textvariable=exp_lbl,bg="#0d0d0d",fg="#888",
                     font=("Courier New",9),width=8).pack(side="left")
        self._setting_row(frame,"Exposure",exp_w,pady=5)
        def reset_exp():
            exp_var.set(0.0); apply_exp(0.0)
        resets.append(reset_exp)

        pct_row("Darkness","_gamma",20,300)
        pct_row("Saturation","_saturation",0,200)

        tk.Label(frame,text="Color Palette",bg="#0d0d0d",fg="#333",
                 font=("Courier New",8)).pack(anchor="w",pady=(8,1))
        tk.Frame(frame,bg="#1a1a1a",height=1).pack(fill="x",pady=(0,4))

        pal_frame=tk.Frame(frame,bg="#0d0d0d")
        pal_frame.pack(anchor="w",pady=(8,0))
        tk.Label(pal_frame,text="RGB Wheel",bg="#0d0d0d",fg="#555",
                 font=("Courier New",9)).pack(anchor="w",padx=2,pady=(4,2))
        picker_row=tk.Frame(pal_frame,bg="#0d0d0d")
        picker_row.pack(anchor="w")

        self._palette_size=190
        self._palette_cursor=None
        self._palette_cursor_shadow=None
        self._palette_canvas=tk.Canvas(picker_row,width=self._palette_size,
                                       height=self._palette_size,bg="#111",
                                       highlightthickness=0,cursor="hand2")
        self._palette_canvas.pack(side="left")
        self._palette_image=ImageTk.PhotoImage(self._make_rgb_wheel(self._palette_size))
        self._palette_canvas.create_image(0,0,anchor="nw",image=self._palette_image)
        self._palette_canvas.bind("<Button-1>",self._on_palette_click)
        self._palette_canvas.bind("<B1-Motion>",self._on_palette_click)

        side=tk.Frame(picker_row,bg="#0d0d0d")
        side.pack(side="left",padx=(12,0),anchor="n")
        tk.Label(side,text="Selected",bg="#0d0d0d",fg="#555",
                 font=("Courier New",9)).pack(anchor="w")
        self._palette_preview_canvas=tk.Canvas(side,width=36,height=36,
                                               bg="#888",highlightthickness=1,
                                               highlightbackground="#444")
        self._palette_preview_canvas.pack(anchor="w",pady=(4,3))
        self._palette_hex_var=tk.StringVar(value="")
        tk.Label(side,textvariable=self._palette_hex_var,bg="#0d0d0d",fg="#888",
                 font=("Courier New",9),width=8,anchor="w").pack(anchor="w")

        def apply_hex(hex_color):
            rgb=tuple(int(hex_color[i:i+2],16) for i in (1,3,5))
            self._set_palette_rgb(*rgb)

        swatches=["#808080","#ff4d4d","#ffb84d","#fff066",
                  "#6fe36f","#5bd9ff","#6f8cff","#c77dff",
                  "#ff7db8","#ffffff"]
        swatch_grid=tk.Frame(side,bg="#0d0d0d")
        swatch_grid.pack(anchor="w",pady=(9,0))
        for idx,hex_color in enumerate(swatches):
            b=tk.Button(swatch_grid,text="",command=lambda c=hex_color: apply_hex(c),
                        bg=hex_color,activebackground=hex_color,
                        width=2,height=1,bd=0,relief="flat",
                        highlightthickness=1,highlightbackground="#222",
                        cursor="hand2")
            b.grid(row=idx//5,column=idx%5,padx=2,pady=2)

        tk.Button(side,text="Open Palette",command=self._choose_palette_color,
                  bg="#1a1a1a",fg="#888",activebackground="#2a2a2a",
                  activeforeground="#ccc",font=("Courier New",9),
                  bd=0,padx=9,pady=5,cursor="hand2",relief="flat"
                  ).pack(anchor="w",pady=(10,0))
        self._update_palette_preview()

        def reset_palette():
            self._set_palette_rgb(127.5,127.5,127.5,redraw=False)
        resets.append(reset_palette)

        def reset_all():
            for fn in resets: fn()
            self._update_palette_preview()
            self._redraw_current_frame()

        tk.Button(frame,text="Reset to Defaults",command=reset_all,
                  bg="#1a1a1a",fg="#888",activebackground="#2a2a2a",
                  activeforeground="#ccc",font=("Courier New",9),
                  bd=0,padx=12,pady=6,cursor="hand2",relief="flat"
                  ).pack(anchor="w",pady=(12,0))

    def _build_shortcuts_tab(self,frame):
        tk.Label(frame,text="Shortcuts",bg="#0d0d0d",fg="#333",
                 font=("Courier New",8)).pack(anchor="w",pady=(0,8))

        for key,desc in SHORTCUTS:
            row=tk.Frame(frame,bg="#0d0d0d"); row.pack(fill="x",pady=1)
            if key is None:
                # section header
                tk.Label(row,text=desc,bg="#0d0d0d",fg="#333",
                         font=("Courier New",8)).pack(anchor="w",pady=(8,1))
                tk.Frame(frame,bg="#1a1a1a",height=1).pack(fill="x",pady=(0,4))
            else:
                tk.Label(row,text=key,bg="#0d0d0d",fg="#666",
                         font=("Courier New",9),width=14,anchor="w"
                         ).pack(side="left")
                tk.Label(row,text=desc,bg="#0d0d0d",fg="#444",
                         font=("Courier New",9),anchor="w"
                         ).pack(side="left")

    # ── seek ──────────────────────────────────────────────────────────────────
    def _on_seek(self,e):
        with self._pl: total=self._total
        if total<=1: return
        req=int(max(0.0,min(1.0,e.x/max(1,self._seekbar.winfo_width())))*(total-1))
        self._request_seek(req)

    # ── controls ──────────────────────────────────────────────────────────────
    def _toggle_play(self):
        with self._pl:
            has_media=self._total>0 or self._is_audio or self._is_vid or self._is_active()
        if not has_media and not self._is_active():
            return
        if self._paused.is_set():
            self._paused.clear(); self._pbtn.configure(text="⏸")
            self._sync_audio()
        else:
            self._paused.set(); self._pbtn.configure(text="▶")
            self._sync_audio()

    def _restart(self):
        self._request_seek(0)

    def _do_stop(self,wait=False):
        self._stop.set(); self._paused.clear()
        self._session_id+=1
        try:
            self._pbtn.configure(text="▶")
        except (AttributeError,tk.TclError):
            pass
        self._stop_current_audio()
        with self._fl:
            self._narr=None
        self._last_rgb=None
        self._is_vid=False
        self._is_audio=False
        with self._pl: self._pos=0; self._total=0; self._seek_req=None
        try:
            self._fps_var.set("")
        except (AttributeError,tk.TclError):
            pass
        if wait and self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=0.75)

    def _browse(self):
        exts=" ".join(f"*{e}" for e in sorted(IMAGE_EXTS|VIDEO_EXTS|AUDIO_EXTS))
        path=filedialog.askopenfilename(
            title="Select image, video, or audio",
            filetypes=[("Supported",exts),("All","*.*")])
        if path: self._handle(path)

    def _close(self):
        if self._closed:
            return
        self._closed=True
        self._do_stop(wait=True)
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _toggle_fs(self):
        self._fs=not self._fs
        self.root.attributes("-fullscreen",self._fs)
        if self._fs:
            self._topbar.pack_forget()
            self._ctrlbar.pack_forget()
            self._fs_bar_progress=0.0
            self._fs_bar_shown   =False
            self._fs_update_bar_pos()                     # place off-screen immediately
            self._canvas.bind("<Motion>",  self._fs_on_canvas_motion)
            self._ctrlbar.bind("<Enter>",  lambda e: self._fs_cancel_hide())
            self._ctrlbar.bind("<Leave>",  lambda e: self._fs_schedule_hide(900))
        else:
            self._fs_cancel_hide()
            if self._fs_anim_id:
                self.root.after_cancel(self._fs_anim_id)
                self._fs_anim_id=None
            self._canvas.unbind("<Motion>")
            self._ctrlbar.unbind("<Enter>")
            self._ctrlbar.unbind("<Leave>")
            self._ctrlbar.place_forget()
            self._topbar.pack(fill="x",side="top",before=self._canvas)
            self._ctrlbar.pack(fill="x",side="bottom")

    # ── fullscreen bar hover-slide ────────────────────────────────────────────

    def _fs_update_bar_pos(self):
        rh=self.root.winfo_height()
        bh=max(1,self._ctrlbar.winfo_reqheight())
        self._ctrlbar.place(x=0,y=int(rh-self._fs_bar_progress*bh),relwidth=1.0)

    def _fs_animate(self):
        if not self._fs:
            self._fs_anim_id=None; return
        target=1.0 if self._fs_bar_shown else 0.0
        diff  =target-self._fs_bar_progress
        if abs(diff)<0.015:
            self._fs_bar_progress=target
            self._fs_update_bar_pos()
            self._fs_anim_id=None; return
        self._fs_bar_progress+=diff*0.20        # exponential ease-out, ~16 fps frames
        self._fs_update_bar_pos()
        self._fs_anim_id=self.root.after(16,self._fs_animate)

    def _fs_set_shown(self,shown):
        self._fs_bar_shown=shown
        if self._fs_anim_id is None:
            self._fs_animate()

    def _fs_schedule_hide(self,delay=900):
        """Schedule the bar to slide back down after `delay` ms."""
        self._fs_cancel_hide()
        self._fs_hide_job=self.root.after(delay,lambda:self._fs_set_shown(False))

    def _fs_cancel_hide(self):
        if self._fs_hide_job:
            self.root.after_cancel(self._fs_hide_job)
            self._fs_hide_job=None

    def _fs_on_canvas_motion(self,e):
        """Show bar when cursor is near the bottom edge; schedule hide otherwise."""
        if not self._fs: return
        if e.y>=self._canvas.winfo_height()-80:   # 80 px trigger zone
            self._fs_cancel_hide()
            self._fs_set_shown(True)
        else:
            self._fs_schedule_hide(1800)   # linger 1.8 s before sliding down

    def _exit_fs(self):
        if self._fs: self._toggle_fs()

    # ── image playback ────────────────────────────────────────────────────────
    def _play_img(self,path,stop_event,session):
        frames=[]
        try:
            with Image.open(path) as img:
                while True:
                    frames.append((np.array(img.copy().convert("RGB")),
                                   max(20,int(img.info.get("duration",100) or 100))))
                    img.seek(img.tell()+1)
        except EOFError:
            pass
        except Exception as exc:
            self._call_ui(self._file_var.set,f"cannot open image: {exc}",session=session)
            self._call_ui(self._pbtn.configure,session=session,text="▶")
            return

        if not frames or stop_event.is_set() or not self._is_session(session):
            return

        with self._pl:
            self._total=len(frames)
            self._pos=0
            self._seek_req=None

        def show(idx):
            rgb,_=frames[idx]
            self._last_rgb=rgb
            arr=render_frame(rgb,self._effective_cols(),self._render_quality,
                             self._current_grade())
            if arr is not None:
                self._push(arr,session=session)
            with self._pl:
                self._pos=idx

        if len(frames)==1:
            show(0)
            self._call_ui(self._pbtn.configure,session=session,text="▶")
            return

        idx=0
        while not stop_event.is_set() and self._is_session(session):
            with self._pl:
                req,self._seek_req=self._seek_req,None
            if req is not None:
                idx=max(0,min(req,len(frames)-1))

            if self._paused.is_set() and req is None:
                time.sleep(0.05)
                continue

            t=time.perf_counter()
            show(idx)

            if self._paused.is_set():
                continue

            wait=frames[idx][1]/1000.0-(time.perf_counter()-t)
            self._sleep_interruptible(wait,stop_event)
            idx=(idx+1)%len(frames)

    # ── video playback ────────────────────────────────────────────────────────
    def _play_audio(self,path,stop_event,session):
        self._call_ui(self._file_var.set,f"♪ {os.path.basename(path)}",session=session)
        self._call_ui(self._pbtn.configure,session=session,text="⏸")
        duration=_probe_duration(path)
        self._vid_fps=100.0
        with self._pl:
            self._total=max(1,int(duration*self._vid_fps)) if duration else 1
            self._pos=0
            self._seek_req=None
        
        audio=Audio(path)
        if self._set_audio(audio,session):
            self._sync_audio(pos=0,session=session)
        vis=AudioWaveform(path,width=max(72,int(self._canvas_size[0]//3)),
                          height=max(32,int(self._canvas_size[1]//3)))
        vis.start()
        current_t=0.0
        base_t=0.0
        play_started=time.perf_counter()
        speed_at_start=self._speed
        try:
            while not stop_event.is_set() and self._is_session(session):
                with self._pl:
                    req,self._seek_req=self._seek_req,None
                if req is not None and duration:
                    current_t=max(0.0,min(float(req)/self._vid_fps,duration))
                    with self._pl:
                        self._pos=int(current_t*self._vid_fps)
                    base_t=current_t
                    play_started=time.perf_counter()
                    speed_at_start=self._speed
                    self._sync_audio(pos=int(current_t*self._vid_fps),session=session)

                if self._paused.is_set():
                    base_t=current_t
                    play_started=time.perf_counter()
                    speed_at_start=self._speed
                    self._sleep_interruptible(0.05,stop_event)
                    continue

                if abs(self._speed-speed_at_start)>0.01:
                    base_t=current_t
                    play_started=time.perf_counter()
                    speed_at_start=self._speed
                current_t=max(0.0,base_t+(time.perf_counter()-play_started)*speed_at_start)
                if duration:
                    current_t=min(current_t,duration)
                with self._pl:
                    self._pos=int(current_t*self._vid_fps)

                frame=vis.next_frame_at(current_t,self._current_grade())
                if frame is not None:
                    self._last_rgb=frame
                    arr=render_frame(frame,self._effective_cols(),self._render_quality,self._current_grade())
                    if arr is not None:
                        self._push(arr,session=session)

                if duration and current_t>=duration:
                    break
                self._sleep_interruptible(0.05,stop_event)
        finally:
            vis.stop()
            self._discard_audio(audio)
            self._call_ui(self._fps_var.set,"",session=session)
            if self._is_session(session):
                self._call_ui(self._file_var.set,"done.",session=session)
                self._call_ui(self._pbtn.configure,session=session,text="▶")

    def _play_vid(self,path,stop_event,session):
        if cv2 is None:
            self._call_ui(self._file_var.set,"video needs opencv-python",session=session)
            self._call_ui(self._pbtn.configure,session=session,text="▶")
            return
        cap=cv2.VideoCapture(path)
        if not cap.isOpened():
            self._call_ui(self._file_var.set,"cannot open file",session=session)
            self._call_ui(self._pbtn.configure,session=session,text="▶")
            return

        fps=cap.get(cv2.CAP_PROP_FPS) or 24
        self._vid_fps=fps if fps>0 else 24
        total=max(0,int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
        dt=1.0/self._vid_fps
        with self._pl: self._total=total; self._seek_req=None

        audio=Audio(path)
        if self._set_audio(audio,session):
            self._sync_audio(pos=0,session=session)
        t_fps=time.perf_counter(); nf=0
        ended=False

        while not stop_event.is_set() and self._is_session(session):
            if self._paused.is_set():
                with self._pl: req,self._seek_req=self._seek_req,None
                if req is not None:
                    if total>1:
                        req=max(0,min(req,total-1))
                    cap.set(cv2.CAP_PROP_POS_FRAMES,req)
                    ret2,f2=cap.read()
                    if ret2:
                        rgb2=cv2.cvtColor(f2,cv2.COLOR_BGR2RGB)
                        self._last_rgb=rgb2
                        arr=render_frame(rgb2,self._effective_cols(),self._render_quality,
                                         self._current_grade())
                        if arr is not None: self._push(arr,session=session)
                    with self._pl: self._pos=req
                    cap.set(cv2.CAP_PROP_POS_FRAMES,req)
                else:
                    time.sleep(0.05)
                continue

            with self._pl: req,self._seek_req=self._seek_req,None
            if req is not None:
                if total>1:
                    req=max(0,min(req,total-1))
                cap.set(cv2.CAP_PROP_POS_FRAMES,req)
                with self._pl:
                    self._pos=req

            t=time.perf_counter()
            ret,frame=cap.read()
            if not ret:
                ended=True
                break
            with self._pl:
                self._pos=max(0,int(cap.get(cv2.CAP_PROP_POS_FRAMES))-1)

            rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
            self._last_rgb=rgb
            arr=render_frame(rgb,self._effective_cols(),self._render_quality,
                             self._current_grade())
            if arr is not None: self._push(arr,session=session)

            nf+=1
            if (el:=time.perf_counter()-t_fps)>=1.0:
                spd=f" {self._speed:.2f}×" if abs(self._speed-1.0)>0.01 else ""
                self._call_ui(self._fps_var.set,f"{nf/el:.1f} fps{spd}",session=session)
                nf=0; t_fps=time.perf_counter()

            wait=(dt/self._speed)-(time.perf_counter()-t)
            if wait>0: self._sleep_interruptible(wait,stop_event)
            else:
                skip_dt=dt/self._speed
                for _ in range(min(int(-wait/skip_dt),self._max_skip)):
                    if stop_event.is_set() or not self._is_session(session):
                        break
                    ok,_=cap.read()
                    if not ok:
                        ended=True
                        break

        cap.release()
        self._discard_audio(audio)
        self._call_ui(self._fps_var.set,"",session=session)
        if ended and self._is_session(session):
            self._call_ui(self._file_var.set,"done.",session=session)
            self._call_ui(self._pbtn.configure,session=session,text="▶")

if __name__=="__main__":
    App()
