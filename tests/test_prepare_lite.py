from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_lite import prepare


def main() -> None:
    skill_root = Path(__file__).resolve().parents[1]
    sample = skill_root / "handwriting-example.jpg"
    source = sample
    config = {"output": {"default_folder": "{job_id}"}, "handwriting_prompt": "short style"}

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        answers = temp_dir / "answers.json"
        answers.write_text(
            json.dumps({"pages": [{"question_scope": "1", "answer_text": "v=1 V"}]}),
            encoding="utf-8",
        )
        manifest_path = prepare(source, answers, config, sample, temp_dir, None)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        prompt = Path(manifest["prompts"][0]["prompt_path"]).read_text(encoding="utf-8")
        assert manifest["generation"]["status"] == "ready_for_imagegen"
        assert "v=1 V" in prompt
        assert len(prompt) < 200


if __name__ == "__main__":
    main()
    print("ok")
