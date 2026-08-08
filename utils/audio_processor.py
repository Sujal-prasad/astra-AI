import os
from pathlib import Path
from shutil import which

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _configure_ffmpeg() -> None:
    if which("ffmpeg") and which("ffprobe"):
        return

    winget_root = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if not winget_root.is_dir():
        return

    ffmpeg_path = next(winget_root.rglob("ffmpeg.exe"), None)
    ffprobe_path = next(winget_root.rglob("ffprobe.exe"), None)
    if ffmpeg_path and ffprobe_path:
        os.environ["PATH"] = str(ffmpeg_path.parent) + os.pathsep + os.environ.get("PATH", "")


_configure_ffmpeg()

import yt_dlp
from pydub import AudioSegment

def download_youtube_audio(url:str)->str:
    if not which("ffmpeg"):
        raise RuntimeError(
            "FFmpeg is required for YouTube audio. Install FFmpeg and add it to PATH, "
            "then restart Streamlit."
        )

    output_path=os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
    ydl_opts={
        "format":"bestaudio/best",
        "outtmpl":output_path,
        "postprocessors":[
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],"quiet": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info=ydl.extract_info(url, download=True)
        filename=Path(ydl.prepare_filename(info)).with_suffix(".wav")

    if not filename.exists():
        raise FileNotFoundError(f"Downloaded audio was not found: {filename}")
    return str(filename)

def convert_to_wav(input_path:str)->str:
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Audio file was not found: {input_path}")

    if not which("ffmpeg") and Path(input_path).suffix.lower() not in {".wav"}:
        raise RuntimeError(
            "FFmpeg is required for this file type. Install FFmpeg and add it to PATH, "
            "then restart Streamlit. WAV files do not need FFmpeg."
        )

    output_path=os.path.splitext(input_path)[0]+"_converted_form.wav"
    audio=AudioSegment.from_file(input_path)
    audio=audio.set_channels(1).set_frame_rate(16000)
    audio.export(output_path, format="wav")
    return output_path

def chunk_audio(wav_path:str,chunk_min:int=10)->list:
    audio = AudioSegment.from_wav(wav_path)
    chunk_length_ms=chunk_min*60*1000
    chunks=[]
    for i , start in enumerate(range(0,len(audio),chunk_length_ms)):
        chunk=audio[start:start+chunk_length_ms]
        chunk_path=f"{wav_path}_chunk_{i}.wav"
        chunk.export(chunk_path, format="wav")
        chunks.append(chunk_path)
    
    return chunks

def process_inputs(source:str)->list:
    if source.startswith("http://") or source.startswith("https://"):
        wav_path=download_youtube_audio(source)
    else:
        converted_path=convert_to_wav(source)
        wav_path=converted_path
        
    chunks=chunk_audio(wav_path)
    return chunks

