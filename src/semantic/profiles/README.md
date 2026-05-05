# Semantic Profiles

This directory is the default location for generated semantic data profiles.

Run:

```bash
python -m src.semantic.profile_runner --output src/semantic/profiles/generated_profile.json
```

Generated profiles must be derived from the database only. Do not add benchmark
questions, expected answers, query IDs, or ground-truth SQL to profile files.
