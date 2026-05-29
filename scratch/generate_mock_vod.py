import numpy as np
import scipy.io.wavfile as wav
import subprocess
from pathlib import Path

def create_mock_vod():
    print("Creating mock 60-second audio track with a loud spike at t=40s...")
    sample_rate = 16000
    duration = 60
    t = np.linspace(0, duration, sample_rate * duration, endpoint=False)

    # Ambient low volume sound (220 Hz sine)
    audio = 0.05 * np.sin(2 * np.pi * 220 * t)

    # Sudden high energy spike at t=40s to t=42s (1000 Hz loud sine)
    spike_start = 40
    spike_end = 42
    spike_mask = (t >= spike_start) & (t <= spike_end)
    audio[spike_mask] = 0.9 * np.sin(2 * np.pi * 1000 * t[spike_mask])

    tmp_wav = Path("/tmp/mock_audio.wav")
    wav.write(str(tmp_wav), sample_rate, (audio * 32767).astype(np.int16))

    target_dir = Path("/home/yazan/Videos/RawGameplay")
    target_dir.mkdir(parents=True, exist_ok=True)
    video_path = target_dir / "mock_gameplay.mp4"

    print("Muxing audio spike with generated video stream using FFmpeg...")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=60",
        "-i", str(tmp_wav),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        "-t", "60",
        str(video_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if tmp_wav.exists():
        tmp_wav.unlink()

    print(f"Mock video successfully created at: {video_path}")

if __name__ == "__main__":
    create_mock_vod()
