"""
Video utilities for AI Studio - FFmpeg integration for frame extraction and video stitching.
"""

import subprocess
import shutil
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Union

logger = logging.getLogger(__name__)


class VideoUtils:
    """FFmpeg wrapper for video processing operations."""

    def __init__(self):
        self.ffmpeg_path = shutil.which('ffmpeg')
        self.ffprobe_path = shutil.which('ffprobe')

        if not self.ffmpeg_path:
            raise RuntimeError("FFmpeg not found. Install with: apt install ffmpeg")
        if not self.ffprobe_path:
            raise RuntimeError("FFprobe not found. Install with: apt install ffmpeg")

    def get_video_info(self, video_path: Path) -> Dict:
        """
        Get video metadata including duration, dimensions, fps, and frame count.

        Args:
            video_path: Path to video file

        Returns:
            Dict with keys: duration, width, height, fps, frame_count, codec
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        cmd = [
            self.ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(video_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        # Find video stream
        video_stream = next(
            (s for s in data.get('streams', []) if s.get('codec_type') == 'video'),
            {}
        )

        # Parse frame rate (e.g., "24/1" or "24000/1001")
        fps_str = video_stream.get('r_frame_rate', '24/1')
        try:
            if '/' in fps_str:
                num, den = map(int, fps_str.split('/'))
                fps = num / den if den != 0 else 24
            else:
                fps = float(fps_str)
        except (ValueError, ZeroDivisionError):
            fps = 24.0

        return {
            'duration': float(data.get('format', {}).get('duration', 0)),
            'width': video_stream.get('width'),
            'height': video_stream.get('height'),
            'fps': round(fps, 2),
            'frame_count': int(video_stream.get('nb_frames', 0)),
            'codec': video_stream.get('codec_name'),
            'bit_rate': int(data.get('format', {}).get('bit_rate', 0)),
        }

    def extract_first_frame(self, video_path: Path, output_path: Path) -> Path:
        """
        Extract the first frame from a video file.

        Args:
            video_path: Path to source video
            output_path: Path for output image (should be .png or .jpg)

        Returns:
            Path to extracted frame
        """
        video_path = Path(video_path)
        output_path = Path(output_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path, '-y',
            '-i', str(video_path),
            '-vframes', '1',
            '-q:v', '2',  # High quality
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg error extracting first frame: {result.stderr}")
            raise RuntimeError(f"Failed to extract first frame: {result.stderr}")

        return output_path

    def extract_last_frame(self, video_path: Path, output_path: Path) -> Path:
        """
        Extract the last frame from a video file.

        Args:
            video_path: Path to source video
            output_path: Path for output image (should be .png or .jpg)

        Returns:
            Path to extracted frame
        """
        video_path = Path(video_path)
        output_path = Path(output_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        # Get video info to find duration
        info = self.get_video_info(video_path)
        duration = info['duration']
        fps = info['fps'] or 24

        # Seek to slightly before the end (1-2 frames before)
        seek_time = max(0, duration - (2 / fps))

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path, '-y',
            '-ss', str(seek_time),
            '-i', str(video_path),
            '-vframes', '1',
            '-q:v', '2',  # High quality
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg error extracting last frame: {result.stderr}")
            raise RuntimeError(f"Failed to extract last frame: {result.stderr}")

        return output_path

    def extract_frame_at_time(self, video_path: Path, output_path: Path,
                              time_seconds: float) -> Path:
        """
        Extract a frame at a specific timestamp.

        Args:
            video_path: Path to source video
            output_path: Path for output image
            time_seconds: Timestamp in seconds

        Returns:
            Path to extracted frame
        """
        video_path = Path(video_path)
        output_path = Path(output_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path, '-y',
            '-ss', str(max(0, time_seconds)),
            '-i', str(video_path),
            '-vframes', '1',
            '-q:v', '2',
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg error extracting frame at {time_seconds}s: {result.stderr}")
            raise RuntimeError(f"Failed to extract frame: {result.stderr}")

        return output_path

    def concatenate_videos(self, video_paths: List[Path], output_path: Path,
                          crossfade_frames: int = 0) -> Path:
        """
        Concatenate multiple videos into a single video.

        Args:
            video_paths: List of video file paths in order
            output_path: Path for output video
            crossfade_frames: Number of frames for crossfade transition (0 = hard cut)

        Returns:
            Path to concatenated video
        """
        if len(video_paths) < 2:
            raise ValueError("Need at least 2 videos to concatenate")

        # Validate all videos exist
        for vp in video_paths:
            if not Path(vp).exists():
                raise FileNotFoundError(f"Video not found: {vp}")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if crossfade_frames > 0:
            return self._concatenate_with_crossfade(video_paths, output_path, crossfade_frames)
        else:
            return self._concatenate_simple(video_paths, output_path)

    def _concatenate_simple(self, video_paths: List[Path], output_path: Path) -> Path:
        """Simple concatenation without re-encoding (fast, lossless if same codec)."""

        # Create concat file
        concat_file = output_path.parent / f'concat_{output_path.stem}.txt'

        try:
            with open(concat_file, 'w') as f:
                for vp in video_paths:
                    # Escape single quotes in paths
                    escaped_path = str(vp).replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            cmd = [
                self.ffmpeg_path, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c', 'copy',  # No re-encoding
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"FFmpeg concat error: {result.stderr}")
                raise RuntimeError(f"Failed to concatenate videos: {result.stderr}")

            return output_path

        finally:
            # Clean up concat file
            if concat_file.exists():
                concat_file.unlink()

    def _concatenate_with_crossfade(self, video_paths: List[Path], output_path: Path,
                                    crossfade_frames: int) -> Path:
        """Concatenate with crossfade transitions (requires re-encoding)."""

        # Get info from first video for timing
        info = self.get_video_info(video_paths[0])
        fps = info['fps'] or 24
        crossfade_duration = crossfade_frames / fps

        # Build filter complex for crossfade
        # This is simplified - for full implementation, would need to chain multiple xfade filters
        n = len(video_paths)

        # Build inputs
        inputs = []
        for vp in video_paths:
            inputs.extend(['-i', str(vp)])

        if n == 2:
            # Simple two-video crossfade
            filter_complex = f"xfade=transition=fade:duration={crossfade_duration}:offset=auto"

            cmd = [
                self.ffmpeg_path, '-y',
                *inputs,
                '-filter_complex', filter_complex,
                '-c:v', 'libx264',
                '-crf', '19',
                '-preset', 'fast',
                '-pix_fmt', 'yuv420p',
                str(output_path)
            ]
        else:
            # For 3+ videos, chain xfade filters
            # Build complex filter graph
            filter_parts = []
            current_output = "[0:v]"

            for i in range(1, n):
                next_input = f"[{i}:v]"
                output_label = f"[v{i}]" if i < n - 1 else ""

                # Get duration of current video for offset calculation
                # In practice, would need to track cumulative duration
                filter_parts.append(
                    f"{current_output}{next_input}xfade=transition=fade:duration={crossfade_duration}:offset=auto{output_label}"
                )
                current_output = f"[v{i}]" if i < n - 1 else ""

            filter_complex = ";".join(filter_parts)

            cmd = [
                self.ffmpeg_path, '-y',
                *inputs,
                '-filter_complex', filter_complex,
                '-c:v', 'libx264',
                '-crf', '19',
                '-preset', 'fast',
                '-pix_fmt', 'yuv420p',
                str(output_path)
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg crossfade error: {result.stderr}")
            # Fall back to simple concatenation
            logger.warning("Crossfade failed, falling back to simple concatenation")
            return self._concatenate_simple(video_paths, output_path)

        return output_path

    def create_thumbnail(self, video_path: Path, output_path: Path,
                        width: int = 320, time_seconds: float = 0) -> Path:
        """
        Create a thumbnail image from a video.

        Args:
            video_path: Path to source video
            output_path: Path for output thumbnail
            width: Thumbnail width (height auto-calculated)
            time_seconds: Time to extract thumbnail from

        Returns:
            Path to thumbnail
        """
        video_path = Path(video_path)
        output_path = Path(output_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path, '-y',
            '-ss', str(time_seconds),
            '-i', str(video_path),
            '-vframes', '1',
            '-vf', f'scale={width}:-1',
            '-q:v', '5',
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg thumbnail error: {result.stderr}")
            raise RuntimeError(f"Failed to create thumbnail: {result.stderr}")

        return output_path

    def trim_video(self, video_path: Path, output_path: Path,
                   start_time: float = 0, end_time: Optional[float] = None,
                   start_frames: int = 0, end_frames: int = 0) -> Path:
        """
        Trim a video, optionally removing frames from start/end for overlap handling.

        Args:
            video_path: Path to source video
            output_path: Path for output video
            start_time: Start time in seconds
            end_time: End time in seconds (None = to end)
            start_frames: Number of frames to skip from start
            end_frames: Number of frames to trim from end

        Returns:
            Path to trimmed video
        """
        video_path = Path(video_path)
        output_path = Path(output_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get video info
        info = self.get_video_info(video_path)
        fps = info['fps'] or 24
        duration = info['duration']

        # Calculate times from frame counts
        actual_start = start_time + (start_frames / fps)
        actual_end = (end_time or duration) - (end_frames / fps)

        if actual_end <= actual_start:
            raise ValueError("Trim would result in zero or negative duration")

        cmd = [
            self.ffmpeg_path, '-y',
            '-ss', str(actual_start),
            '-i', str(video_path),
            '-t', str(actual_end - actual_start),
            '-c', 'copy',
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg trim error: {result.stderr}")
            raise RuntimeError(f"Failed to trim video: {result.stderr}")

        return output_path


# Singleton instance
_video_utils = None

def get_video_utils() -> VideoUtils:
    """Get or create the VideoUtils singleton."""
    global _video_utils
    if _video_utils is None:
        _video_utils = VideoUtils()
    return _video_utils
