**A lightweight, high-performance Python utility for lossless video concatenation and keyframe-based cutting.**

---

## 📌 Overview

**KeyframeMerge** was developed to solve a specific multimedia processing bottleneck: the massive CPU and time overhead required to merge or split large video files. Standard video editors re-encode the entire video stream, taking hours and degrading quality.

This tool operates directly on the video stream level. By calculating and cutting precisely at **I-frames (Keyframes)**, it concatenates and splits video files instantly without re-encoding a single frame. It includes a custom size-thresholding algorithm that automatically splits output files to fit specific platform upload limits (e.g., a strict 500MB cutoff).

## 📸 Application Showcase

### 1. Main Configuration Interface

> The primary dashboard where users can load directories, set maximum output file size thresholds, and arrange the merge order.
> *([Add your image here: e.g., `![Main Interface](assets/screenshot_1_main.png)`])*

### 2. Live Processing State

> Demonstrates the non-blocking background thread in action, parsing media streams and executing the stream-copy commands instantly without freezing the UI.
> *([Add your image here: e.g., `![Processing State](assets/screenshot_2_processing.png)`])*

### 3. Output Generation & Thresholding

> Shows the final generated directory. Notice how a massive batch of source files is neatly packed into seamless output volumes exactly under the user's requested size limit.
> *([Add your image here: e.g., `![Output Result](assets/screenshot_3_output.png)`])*

## 🚀 Technical Highlights

This project was built with a strict focus on resource optimization, I/O efficiency, and autonomous error handling.

* **Zero-Loss Stream Copying:** Bypasses the decoding/encoding matrix entirely. Videos are processed at disk-write speeds using pure stream mapping (`-c copy`).
* **Intelligent Keyframe Snapping:** Automatically detects video I-frames to ensure cuts are clean and playable, preventing the corrupted "grey frames" common in basic stream cutting.
* **Dynamic Size Thresholding:** Implements an algorithmic check that continuously calculates cumulative bitrates/file sizes. When the user-defined threshold (e.g., 2GB) is reached, it seamlessly finalizes the current output and rolls over to the next volume.
* **Asynchronous Architecture:** The UI remains highly responsive while heavy I/O operations and subprocess calls are offloaded to daemon threads.

## 🛠️ Tech Stack & Requirements

* **Language:** Python 3.10+
* **Core Libraries:** `os`, `subprocess`, `threading`, `json`
* **External Dependencies:** `FFmpeg` (must be installed and added to system PATH)

## 🧠 Engineering Philosophy

I built this tool because I believe software should respect the user's hardware. Instead of throwing raw compute power at a simple joining task, this architecture relies on a deep understanding of video container formats to manipulate the data smartly. It reduces a process that typically takes hours and 100% CPU utilization down to seconds and minimal memory overhead.
