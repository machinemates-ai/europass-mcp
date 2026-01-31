"""
Benchmark harness for CV extraction quality.

Run with: pytest tests/benchmarks/ -v --benchmark
Or: python -m pytest tests/benchmarks/test_extraction_quality.py -v -s

This module measures extraction quality against ground truth fixtures.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# Get fixtures path
FIXTURES_DIR = Path(__file__).parent / "fixtures"
RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class BenchmarkCase:
    """A benchmark test case with ground truth."""
    
    name: str
    docx_path: Path
    ground_truth: dict
    description: str = ""


@dataclass
class ExtractionScore:
    """Scores for extraction quality."""
    
    field_completeness: float = 0.0  # % of expected fields present
    value_accuracy: float = 0.0      # % of values matching ground truth
    list_count_accuracy: float = 0.0 # % accuracy in list counts (jobs, skills)
    latency_seconds: float = 0.0
    
    def overall_score(self) -> float:
        """Weighted overall score (0-100)."""
        return (
            self.field_completeness * 0.3 +
            self.value_accuracy * 0.4 +
            self.list_count_accuracy * 0.3
        )


def calculate_field_completeness(extracted: dict, expected: dict, path: str = "") -> tuple[int, int]:
    """
    Calculate how many expected fields are present in extracted.
    
    Returns (present_count, total_expected_count)
    """
    present = 0
    total = 0
    
    for key, expected_value in expected.items():
        current_path = f"{path}.{key}" if path else key
        total += 1
        
        if key in extracted:
            present += 1
            extracted_value = extracted[key]
            
            # Recurse into nested dicts
            if isinstance(expected_value, dict) and isinstance(extracted_value, dict):
                nested_present, nested_total = calculate_field_completeness(
                    extracted_value, expected_value, current_path
                )
                present += nested_present
                total += nested_total
    
    return present, total


def calculate_value_accuracy(extracted: dict, expected: dict) -> tuple[int, int]:
    """
    Calculate how many values match exactly.
    
    Returns (matching_count, total_count)
    """
    matching = 0
    total = 0
    
    for key, expected_value in expected.items():
        if key not in extracted:
            continue
            
        extracted_value = extracted[key]
        
        # Compare strings (case-insensitive, strip whitespace)
        if isinstance(expected_value, str) and isinstance(extracted_value, str):
            total += 1
            if expected_value.strip().lower() == extracted_value.strip().lower():
                matching += 1
        
        # Compare numbers
        elif isinstance(expected_value, (int, float)) and isinstance(extracted_value, (int, float)):
            total += 1
            if expected_value == extracted_value:
                matching += 1
        
        # Recurse into dicts
        elif isinstance(expected_value, dict) and isinstance(extracted_value, dict):
            nested_match, nested_total = calculate_value_accuracy(extracted_value, expected_value)
            matching += nested_match
            total += nested_total
    
    return matching, total


def calculate_list_count_accuracy(extracted: dict, expected: dict) -> tuple[int, int]:
    """
    Calculate accuracy of list counts (jobs, education, skills).
    
    Returns (correct_counts, total_lists)
    """
    list_fields = [
        ("experience.jobs", "jobs"),
        ("knowledge.studies", "education"),
        ("knowledge.hardSkills", "skills"),
        ("knowledge.languages", "languages"),
    ]
    
    correct = 0
    total = 0
    
    for path, name in list_fields:
        parts = path.split(".")
        
        # Navigate to list in expected
        expected_list = expected
        for part in parts:
            expected_list = expected_list.get(part, []) if isinstance(expected_list, dict) else []
        
        # Navigate to list in extracted
        extracted_list = extracted
        for part in parts:
            extracted_list = extracted_list.get(part, []) if isinstance(extracted_list, dict) else []
        
        if isinstance(expected_list, list):
            total += 1
            expected_count = len(expected_list)
            extracted_count = len(extracted_list) if isinstance(extracted_list, list) else 0
            
            # Count is correct if within ±1 of expected
            if abs(expected_count - extracted_count) <= 1:
                correct += 1
    
    return correct, total


def score_extraction(extracted: dict, expected: dict, latency: float) -> ExtractionScore:
    """Calculate extraction quality scores."""
    
    # Field completeness
    present, total_fields = calculate_field_completeness(extracted, expected)
    field_completeness = (present / total_fields * 100) if total_fields > 0 else 0
    
    # Value accuracy
    matching, total_values = calculate_value_accuracy(extracted, expected)
    value_accuracy = (matching / total_values * 100) if total_values > 0 else 0
    
    # List count accuracy
    correct_counts, total_lists = calculate_list_count_accuracy(extracted, expected)
    list_accuracy = (correct_counts / total_lists * 100) if total_lists > 0 else 0
    
    return ExtractionScore(
        field_completeness=field_completeness,
        value_accuracy=value_accuracy,
        list_count_accuracy=list_accuracy,
        latency_seconds=latency,
    )


def load_benchmark_cases() -> list[BenchmarkCase]:
    """Load benchmark cases from fixtures directory."""
    cases = []
    
    if not FIXTURES_DIR.exists():
        return cases
    
    for json_file in FIXTURES_DIR.glob("*.ground_truth.json"):
        docx_name = json_file.name.replace(".ground_truth.json", ".docx")
        docx_path = FIXTURES_DIR / docx_name
        
        if docx_path.exists():
            with open(json_file) as f:
                ground_truth = json.load(f)
            
            cases.append(BenchmarkCase(
                name=docx_name,
                docx_path=docx_path,
                ground_truth=ground_truth,
                description=ground_truth.get("_description", ""),
            ))
    
    return cases


class TestExtractionBenchmark:
    """Benchmark tests for CV extraction quality."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures."""
        self.cases = load_benchmark_cases()
        RESULTS_DIR.mkdir(exist_ok=True)
    
    @pytest.mark.benchmark
    def test_extraction_quality(self):
        """Run extraction benchmark on all fixtures."""
        if not self.cases:
            pytest.skip("No benchmark fixtures found. Add DOCX + ground_truth.json pairs to tests/benchmarks/fixtures/")
        
        # Import extractor
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
        from cv_extractor import extract_cv_from_file
        
        results = []
        
        for case in self.cases:
            print(f"\n📊 Benchmarking: {case.name}")
            
            # Extract
            start = time.time()
            result = extract_cv_from_file(str(case.docx_path))
            latency = time.time() - start
            
            if result.get("status") != "success":
                print(f"  ❌ Extraction failed: {result.get('message')}")
                continue
            
            # Score
            extracted = result.get("mac_json", {})
            score = score_extraction(extracted, case.ground_truth, latency)
            
            print(f"  ✅ Field completeness: {score.field_completeness:.1f}%")
            print(f"  ✅ Value accuracy: {score.value_accuracy:.1f}%")
            print(f"  ✅ List count accuracy: {score.list_count_accuracy:.1f}%")
            print(f"  ⏱️  Latency: {score.latency_seconds:.1f}s")
            print(f"  🎯 Overall: {score.overall_score():.1f}%")
            
            results.append({
                "case": case.name,
                "scores": {
                    "field_completeness": score.field_completeness,
                    "value_accuracy": score.value_accuracy,
                    "list_count_accuracy": score.list_count_accuracy,
                    "overall": score.overall_score(),
                },
                "latency": score.latency_seconds,
            })
        
        # Save results
        results_file = RESULTS_DIR / "benchmark_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📁 Results saved to: {results_file}")
        
        # Assert minimum quality threshold
        for r in results:
            assert r["scores"]["overall"] >= 50, f"Extraction quality too low for {r['case']}"


# Standalone runner
if __name__ == "__main__":
    """Run benchmarks directly."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    
    cases = load_benchmark_cases()
    
    if not cases:
        print("⚠️  No benchmark fixtures found.")
        print(f"   Add DOCX files and ground truth JSON to: {FIXTURES_DIR}/")
        print()
        print("   Example:")
        print("   - cv_sample.docx")
        print("   - cv_sample.ground_truth.json")
        sys.exit(1)
    
    from cv_extractor import extract_cv_from_file
    
    print("=" * 60)
    print("CV Extraction Benchmark")
    print("=" * 60)
    
    for case in cases:
        print(f"\n📊 {case.name}")
        if case.description:
            print(f"   {case.description}")
        
        start = time.time()
        result = extract_cv_from_file(str(case.docx_path))
        latency = time.time() - start
        
        if result.get("status") == "success":
            extracted = result.get("mac_json", {})
            score = score_extraction(extracted, case.ground_truth, latency)
            
            print(f"   Field completeness: {score.field_completeness:.1f}%")
            print(f"   Value accuracy: {score.value_accuracy:.1f}%")
            print(f"   List count accuracy: {score.list_count_accuracy:.1f}%")
            print(f"   Latency: {score.latency_seconds:.1f}s")
            print(f"   Overall: {score.overall_score():.1f}%")
        else:
            print(f"   ❌ Failed: {result.get('message')}")
