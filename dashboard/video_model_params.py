"""
Video model parameter definitions for AI Studio.

This module defines model-specific parameters that were previously hard-coded
in the workflow builders, making them user-controllable.
"""

# Model-specific parameter definitions
VIDEO_MODEL_PARAMS = {
    'ltx': {
        'display_name': 'LTX-Video',
        'description': 'Fast, high-quality video generation. Best for general use.',
        'params': {
            'strength': {
                'label': 'Image Fidelity',
                'type': 'slider',
                'min': 0.5,
                'max': 1.0,
                'step': 0.05,
                'default': 0.8,
                'help': 'Higher values = more faithful to input image, less motion',
                'workflow_key': 'strength',
                'advanced': False
            },
            'max_shift': {
                'label': 'Max Shift',
                'type': 'slider',
                'min': 1.0,
                'max': 4.0,
                'step': 0.1,
                'default': 2.05,
                'help': 'Noise schedule maximum shift parameter',
                'workflow_key': 'max_shift',
                'advanced': True
            },
            'base_shift': {
                'label': 'Base Shift',
                'type': 'slider',
                'min': 0.5,
                'max': 2.0,
                'step': 0.05,
                'default': 0.95,
                'help': 'Noise schedule base shift parameter',
                'workflow_key': 'base_shift',
                'advanced': True
            },
            'sampler': {
                'label': 'Sampler',
                'type': 'select',
                'options': ['euler', 'dpmpp_2m', 'dpmpp_2m_sde', 'dpmpp_3m_sde', 'ddim', 'uni_pc'],
                'default': 'euler',
                'help': 'Sampling algorithm - euler is fastest, dpmpp variants may produce different results',
                'workflow_key': 'sampler',
                'advanced': False
            },
        },
        'frame_limits': {
            'min': 9,
            'max': 257,
            'step': 8,
            'formula': '8n+1',
            'presets': [25, 49, 81, 121, 161, 201, 257]
        },
        'recommended': {
            'steps': 25,
            'cfg': 3.5,
            'width': 768,
            'height': 768
        },
        'supports_motion_strength': False,  # Motion mapped to strength
    },

    'wan': {
        'display_name': 'Wan 2.x',
        'description': 'Good motion control with dedicated motion strength parameter.',
        'params': {
            'motion_strength': {
                'label': 'Motion Strength',
                'type': 'slider',
                'min': 0.0,
                'max': 1.0,
                'step': 0.1,
                'default': 0.7,
                'help': 'Higher = more movement and animation',
                'workflow_key': 'motion_strength',
                'advanced': False
            },
            'shift': {
                'label': 'Shift',
                'type': 'slider',
                'min': 1.0,
                'max': 10.0,
                'step': 0.5,
                'default': 5.0,
                'help': 'Controls motion dynamics - higher = more dramatic motion',
                'workflow_key': 'shift',
                'advanced': False
            },
            'scheduler': {
                'label': 'Scheduler',
                'type': 'select',
                'options': ['unipc', 'euler', 'ddim'],
                'default': 'unipc',
                'help': 'unipc is fastest, euler is most stable, ddim for different look',
                'workflow_key': 'scheduler',
                'advanced': False
            }
        },
        'frame_limits': {
            'min': 17,
            'max': 121,
            'step': 4,
            'formula': '4n+1',
            'presets': [17, 25, 49, 81, 121]
        },
        'recommended': {
            'steps': 30,
            'cfg': 5.0,
            'width': 768,
            'height': 768
        },
        'supports_motion_strength': True,
        'supports_flf2v': True,  # First-Last-Frame to Video
    },

    'hunyuan': {
        'display_name': 'HunyuanVideo',
        'description': 'High quality results, higher VRAM requirement.',
        'params': {
            'embedded_cfg_scale': {
                'label': 'Embedded CFG',
                'type': 'slider',
                'min': 1.0,
                'max': 15.0,
                'step': 0.5,
                'default': 6.0,
                'help': 'Secondary guidance scale for quality/creativity balance',
                'workflow_key': 'embedded_cfg_scale',
                'advanced': False
            }
        },
        'frame_limits': {
            'min': 17,
            'max': 129,
            'step': 4,
            'formula': '4n+1',
            'presets': [17, 25, 49, 81, 121, 129]
        },
        'recommended': {
            'steps': 30,
            'cfg': 7.0,
            'width': 720,
            'height': 720
        },
        'supports_motion_strength': False,
    }
}

# Default negative prompts by model type
DEFAULT_NEGATIVE_PROMPTS = {
    'ltx': 'worst quality, inconsistent motion, blurry, jittery, distorted, watermarks, text, logo',
    'wan': 'worst quality, blurry, distorted, deformed, ugly, bad anatomy, disfigured, watermark',
    'hunyuan': 'worst quality, low quality, blurry, distorted, deformed, ugly, watermark, text'
}

# Video encoding parameters (applies to all models)
VIDEO_ENCODING_PARAMS = {
    'crf': {
        'label': 'Video Quality (CRF)',
        'type': 'slider',
        'min': 10,
        'max': 35,
        'step': 1,
        'default': 19,
        'help': 'Lower = better quality, larger file. 15-19 = high quality, 20-25 = medium, 26+ = low',
    }
}

# Video model file patterns for detection
VIDEO_MODEL_FILES = {
    'ltx': [
        'ltxv-13b-0.9.8-distilled-fp8.safetensors',
        'ltx-video-2b-v0.9.safetensors',
        'ltxv-13b-0.9.7-dev-fp8.safetensors',
    ],
    'wan': [
        'TI2V/Wan2_2-TI2V-5B_fp8_e4m3fn_scaled_KJ.safetensors',
        'Wan2_1-TI2V-14B-720P_fp8_e4m3fn.safetensors',
    ],
    'hunyuan': [
        'hunyuanvideo1.5_720p_i2v_cfg_distilled_fp16.safetensors',
        'hunyuanvideo_t2v_720p_bf16.safetensors',
    ]
}

# VRAM estimates by model (in GB)
VIDEO_MODEL_VRAM = {
    'ltxv-13b-0.9.8-distilled-fp8.safetensors': 14,
    'ltx-video-2b-v0.9.safetensors': 8,
    'TI2V/Wan2_2-TI2V-5B_fp8_e4m3fn_scaled_KJ.safetensors': 10,
    'hunyuanvideo1.5_720p_i2v_cfg_distilled_fp16.safetensors': 16,
}


def get_model_type(model_filename: str) -> str:
    """
    Detect model type from filename.

    Args:
        model_filename: The model filename

    Returns:
        Model type string: 'ltx', 'wan', or 'hunyuan'
    """
    model_lower = model_filename.lower()

    if 'ltx' in model_lower:
        return 'ltx'
    elif 'wan' in model_lower:
        return 'wan'
    elif 'hunyuan' in model_lower:
        return 'hunyuan'
    else:
        # Default to LTX for unknown models
        return 'ltx'


def get_model_params(model_type: str) -> dict:
    """
    Get parameter definitions for a model type.

    Args:
        model_type: One of 'ltx', 'wan', 'hunyuan'

    Returns:
        Parameter definitions dict
    """
    return VIDEO_MODEL_PARAMS.get(model_type, VIDEO_MODEL_PARAMS['ltx'])


def get_default_negative_prompt(model_type: str) -> str:
    """
    Get default negative prompt for a model type.

    Args:
        model_type: One of 'ltx', 'wan', 'hunyuan'

    Returns:
        Default negative prompt string
    """
    return DEFAULT_NEGATIVE_PROMPTS.get(model_type, DEFAULT_NEGATIVE_PROMPTS['ltx'])


def get_param_defaults(model_type: str) -> dict:
    """
    Get default values for all parameters of a model type.

    Args:
        model_type: One of 'ltx', 'wan', 'hunyuan'

    Returns:
        Dict of param_name -> default_value
    """
    model_config = VIDEO_MODEL_PARAMS.get(model_type, VIDEO_MODEL_PARAMS['ltx'])
    defaults = {}

    for param_name, param_config in model_config.get('params', {}).items():
        defaults[param_name] = param_config.get('default')

    return defaults


def validate_frames(model_type: str, frames: int) -> int:
    """
    Validate and adjust frame count for model constraints.

    Args:
        model_type: One of 'ltx', 'wan', 'hunyuan'
        frames: Requested frame count

    Returns:
        Valid frame count (adjusted if necessary)
    """
    model_config = VIDEO_MODEL_PARAMS.get(model_type, VIDEO_MODEL_PARAMS['ltx'])
    limits = model_config.get('frame_limits', {})

    min_frames = limits.get('min', 17)
    max_frames = limits.get('max', 121)
    step = limits.get('step', 4)

    # Clamp to range
    frames = max(min_frames, min(max_frames, frames))

    # Adjust to valid step
    # For formula like "8n+1", valid frames are: 9, 17, 25, 33...
    # For formula like "4n+1", valid frames are: 5, 9, 13, 17, 21, 25...
    if limits.get('formula') == '8n+1':
        # Round to nearest 8n+1
        n = round((frames - 1) / 8)
        frames = 8 * n + 1
    elif limits.get('formula') == '4n+1':
        # Round to nearest 4n+1
        n = round((frames - 1) / 4)
        frames = 4 * n + 1

    return max(min_frames, min(max_frames, frames))


# Export for use in templates
def get_all_model_params_json() -> dict:
    """
    Get all model parameters in a format suitable for JSON serialization
    to pass to frontend JavaScript.
    """
    return VIDEO_MODEL_PARAMS
