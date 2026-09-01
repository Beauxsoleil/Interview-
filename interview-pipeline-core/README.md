# interview-pipeline-core

Shared, application-independent audio pipeline for the Interview app and its
integration services. It provides deterministic stub output by default when
the optional Whisper/WhisperX and pyannote dependencies are unavailable.

The package deliberately has no FastAPI, database, or application-settings
dependency. Callers pass a `PipelineConfig` when they run the pipeline.

```python
from interview_pipeline_core import PipelineConfig, run_pipeline

result = run_pipeline(
    "interview.m4a",
    config=PipelineConfig(
        pipeline_backend="auto",
        whisper_model="base",
        hf_token=None,
    ),
)
```

Install the lightweight core alone with `pip install -e .`. Install the real
ML stack with `pip install -e ".[ml]"`.
