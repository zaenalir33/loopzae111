import os
import subprocess
import threading
import static_ffmpeg
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# 1. Inisialisasi biner ffmpeg secara otomatis tanpa butuh apt-get
static_ffmpeg.add_paths()

# 2. Inisialisasi Session State
if 'logs' not in st.session_state:
    st.session_state['logs'] = []

def log_callback(msg):
    if 'logs' in st.session_state:
        st.session_state['logs'].append(msg)

def run_ffmpeg_command(cmd):
    try:
        log_callback(f"Menjalankan: {' '.join(cmd)}")
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

# Interface Streamlit
st.title("YouTube Live Streamer")

video_file = st.text_input("Nama File Video", "video.mp4")
stream_key = st.text_input("Stream Key YouTube", type="password")

if st.button("Mulai Live Stream"):
    if not stream_key:
        st.error("Masukkan Stream Key terlebih dahulu!")
    else:
        rtmp_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
        cmd = [
            "ffmpeg", "-re", "-stream_loop", "-1", "-i", video_file,
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k",
            "-maxrate", "2500k", "-bufsize", "5000k", "-g", "60",
            "-keyint_min", "60", "-c:a", "aac", "-b:a", "128k",
            "-f", "flv", rtmp_url
        ]
        
        # Jalankan eksekusi di thread terpisah dengan ScriptRunContext
        t = threading.Thread(target=run_ffmpeg_command, args=(cmd,), name="run_ffmpeg")
        add_script_run_ctx(t)
        t.start()
        st.success("Proses streaming telah dimulai di background!")

# Menampilkan Logs
st.subheader("Log Output")
if st.session_state['logs']:
    st.code("\n".join(st.session_state['logs']))
