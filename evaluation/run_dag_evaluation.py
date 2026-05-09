import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from evaluation.runners.run_dag_evaluation import (  # noqa: E402
    export_ex_zero_failures,
    main,
    parse_arguments,
)


if __name__ == "__main__":
    main()
