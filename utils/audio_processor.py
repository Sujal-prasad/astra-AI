import glob
import os
import subprocess
from pathlib import Path
from shutil import which

DOWNLOAD_DIR = str(Path(__file__).resolve().parents[1] / "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

TARGET_SAMPLE_RATE = 16000


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


def _configure_deno() -> None:
    if which("deno"):
        return

    winget_root = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if not winget_root.is_dir():
        return

    deno_path = next(winget_root.rglob("deno.exe"), None)
    if deno_path:
        os.environ["PATH"] = str(deno_path.parent) + os.pathsep + os.environ.get("PATH", "")


_configure_deno()

import yt_dlp
from pydub import AudioSegment
from yt_dlp.utils import DownloadError


def _run_ffmpeg(arguments: list) -> None:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr.strip()}")


def download_youtube_audio(url:str, progress_callback=None)->str:
    if not which("ffmpeg"):
        raise RuntimeError(
            "FFmpeg is required for YouTube audio. Install FFmpeg and add it to PATH, "
            "then restart Streamlit."
        )

    output_path=os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
    ydl_opts={
        "format":"bestaudio/best",
        "outtmpl":output_path,
        "js_runtimes":{"deno": {}},
        "postprocessors":[
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],"quiet": True
    }
    browser = os.getenv("YOUTUBE_BROWSER", "").strip().lower()
    if browser:
        supported_browsers = {"chrome", "edge", "firefox", "brave", "opera", "vivaldi"}
        if browser not in supported_browsers:
            raise RuntimeError(
                f"Unsupported YOUTUBE_BROWSER={browser!r}. Use chrome, edge, firefox, brave, opera, or vivaldi."
            )
        ydl_opts["cookiesfrombrowser"] = (browser,)
    def run_download(options: dict) -> Path:
        if progress_callback:
            options["progress_hooks"] = [progress_callback]
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            return Path(ydl.prepare_filename(info)).with_suffix(".wav")

    try:
        if progress_callback:
            progress_callback({"stage": "downloading", "status": "starting"})
        filename = run_download(ydl_opts)
    except DownloadError as error:
        message = str(error)
        if "cookie database" in message.lower() or "could not copy chrome" in message.lower():
            ydl_opts.pop("cookiesfrombrowser", None)
            try:
                filename = run_download(ydl_opts)
            except DownloadError as retry_error:
                error = retry_error
                message = str(retry_error)
            else:
                message = ""
        if "decrypt with dpapi" in message.lower() or "failed to decrypt" in message.lower():
            ydl_opts.pop("cookiesfrombrowser", None)
            try:
                filename = run_download(ydl_opts)
            except DownloadError as retry_error:
                error = retry_error
                message = str(retry_error)
            else:
                message = ""
        if "not available" in message.lower() or "private video" in message.lower():
            raise RuntimeError(
                "YouTube could not provide this video. Check that the URL is correct, "
                "the video is public, and it is available in your region."
            ) from error
        if "403" in message or "forbidden" in message.lower():
            raise RuntimeError(
                "YouTube rejected the media download (HTTP 403). Add YOUTUBE_BROWSER=chrome "
                "to .ENV, restart Astra, and retry while Chrome is installed on this computer."
            ) from error
        raise RuntimeError(f"YouTube download failed: {message}") from error

    if not filename.exists():
        raise FileNotFoundError(f"Downloaded audio was not found: {filename}")
    return str(filename)

def convert_to_wav(input_path:str)->str:
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Audio file was not found: {input_path}")

    output_path=os.path.splitext(input_path)[0]+"_converted_form.wav"

    if which("ffmpeg"):
        _run_ffmpeg([
            "-i", input_path,
            "-vn",
            "-ac", "1",
            "-ar", str(TARGET_SAMPLE_RATE),
            "-c:a", "pcm_s16le",
            output_path,
        ])
        return output_path

    if Path(input_path).suffix.lower() != ".wav":
        raise RuntimeError(
            "FFmpeg is required for this file type. Install FFmpeg and add it to PATH, "
            "then restart Streamlit. WAV files do not need FFmpeg."
        )

    audio=AudioSegment.from_file(input_path)
    audio=audio.set_channels(1).set_frame_rate(TARGET_SAMPLE_RATE)
    audio.export(output_path, format="wav")
    return output_path

def chunk_audio(wav_path:str,chunk_min:int=10)->list:
    prefix=f"{wav_path}_chunk_"

    if which("ffmpeg"):
        _run_ffmpeg([
            "-i", wav_path,
            "-f", "segment",
            "-segment_time", str(chunk_min*60),
            "-c", "copy",
            f"{prefix}%03d.wav",
        ])
        chunks=sorted(glob.glob(glob.escape(prefix)+"*.wav"))
        if chunks:
            return chunks

    audio = AudioSegment.from_wav(wav_path)
    chunk_length_ms=chunk_min*60*1000
    chunks=[]
    for i , start in enumerate(range(0,len(audio),chunk_length_ms)):
        chunk=audio[start:start+chunk_length_ms]
        chunk_path=f"{prefix}{i:03d}.wav"
        chunk.export(chunk_path, format="wav")
        chunks.append(chunk_path)

    return chunks


def cleanup_files(paths)->None:
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass


def process_inputs(source:str, progress_callback=None)->list:
    intermediates=[]
    if source.startswith("http://") or source.startswith("https://"):
        downloaded_path=download_youtube_audio(source, progress_callback=progress_callback)
        intermediates.append(downloaded_path)
    else:
        downloaded_path=source

    if progress_callback:
        progress_callback({"stage": "converting", "status": "running"})
    wav_path=convert_to_wav(downloaded_path)
    intermediates.append(wav_path)
    if progress_callback:
        progress_callback({"stage": "converting", "status": "finished"})

    try:
        if progress_callback:
            progress_callback({"stage": "chunking", "status": "running"})
        chunks=chunk_audio(wav_path)
    finally:
        cleanup_files(intermediates)

    if progress_callback:
        progress_callback({"stage": "chunking", "status": "finished", "chunks": len(chunks)})
    return chunks
