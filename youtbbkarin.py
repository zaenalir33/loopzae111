import os
import subprocess
import threading
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# 1. Unduh biner FFmpeg static langsung via curl/tar ke /tmp jika belum ada
temp_ffmpeg_dir = "/tmp/ffmpeg_bin"
ffmpeg_bin = os.path.join(temp_ffmpeg_dir, "ffmpeg")

def prepare_ffmpeg():
    if not os.path.exists(ffmpeg_bin):
        os.makedirs(temp_ffmpeg_dir, exist_ok=True)
        # Unduh biner Linux FFmpeg static 64-bit langsung ke /tmp
        cmd = (
            f"curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz "
            f"| tar -xJ -C {temp_ffmpeg_dir} --strip-components=1"
        )
        subprocess.run(cmd, shell=True, check=True)

prepare_ffmpeg()

# Masukkan folder /tmp/ffmpeg_bin ke PATH sistem
os.environ["PATH"] = temp_ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

# 2. Inisialisasi Session State
if 'logs' not in st.session_state:
    st.session_state['logs'] = []

if 'streaming' not in st.session_state:
    st.session_state['streaming'] = False

def log_callback(msg):
    if 'logs' in st.session_state:
        st.session_state['logs'].append(msg)

def run_ffmpeg(cmd):
    try:
        log_callback("Menjalankan perintah FFmpeg...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        for line in process.stdout:
            log_callback(line.strip())
            
        process.wait()
        log_callback("Streaming selesai atau dihentikan.")
    except Exception as e:
        log_callback(f"Error: {e}")
    finally:
        if 'streaming' in st.session_state:
            st.session_state['streaming'] = False

# --- Antarmuka Streamlit ---
st.set_page_config(page_title="YouTube Live Streamer", layout="wide")
st.title("📹 YouTube Auto Live Streamer")

col1, col2 = st.columns(2)

with col1:
    # Komponen Tombol Upload File Video
    uploaded_file = st.file_uploader("Upload File Video (MP4 / MKV / MOV)", type=["mp4", "mkv", "mov"])

with col2:
    stream_key = st.text_input("YouTube Stream Key", type="password")

shorts_mode = st.checkbox("Mode Shorts (720x1280)")

if st.button("🚀 Mulai Streaming", disabled=st.session_state['streaming']):
    if not stream_key:
        st.error("Harap masukkan Stream Key YouTube terlebih dahulu!")
    elif uploaded_file is None:
        st.error("Harap upload file video terlebih dahulu!")
    else:
        # Simpan file yang di-upload ke /tmp agar bisa dibaca oleh FFmpeg
        target_video_path = "/tmp/uploaded_video.mp4"
        with open(target_video_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.session_state['streaming'] = True
        rtmp_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
        
        if shorts_mode:
            cmd = [
                ffmpeg_bin, "-re", "-stream_loop", "-1",
                "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1",
                "-i", target_video_path,
                "-vf", "scale=720:1280",
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k",
                "-maxrate", "2500k", "-bufsize", "5000k", "-g", "60",
                "-keyint_min", "60", "-c:a", "aac", "-b:a", "128k",
                "-f", "flv", rtmp_url
            ]
        else:
            cmd = [
                ffmpeg_bin, "-re", "-stream_loop", "-1",
                "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1",
                "-i", target_video_path,
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k",
                "-maxrate", "2500k", "-bufsize", "5000k", "-g", "60",
                "-keyint_min", "60", "-c:a", "aac", "-b:a", "128k",
                "-f", "flv", rtmp_url
            ]
        
        thread = threading.Thread(target=run_ffmpeg, args=(cmd,), name="run_ffmpeg")
        add_script_run_ctx(thread)
        thread.start()
        
        st.success("File berhasil diunggah & proses streaming berjalan di background!")

st.divider()
st.subheader("📋 Log Aktivitas Streaming")

if st.button("🔄 Perbarui Log"):
    st.rerun()

if st.session_state['logs']:
    st.code("\n".join(st.session_state['logs'][-50:]), language="bash")
else:
    st.info("Belum ada log aktivitas.")
