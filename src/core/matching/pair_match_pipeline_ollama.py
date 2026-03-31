import logging
from src.core.matching.config import PipelineConfig
from src.core.matching.pipeline import PairMatchPipeline

logger = logging.getLogger("pair_match_pipeline")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    config = PipelineConfig()
    # config.vb1_path = "path/to/real/vb1.docx"  # Update path dynamically if needed
    
    pipeline = PairMatchPipeline(config)
    out_path = pipeline.run()
    
    print(f"Done. Report saved to: {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())